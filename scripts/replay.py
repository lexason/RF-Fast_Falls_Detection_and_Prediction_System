#!/usr/bin/env python3
"""Deterministically replay a local SigMF complex64 recording over ZMQ.

This implementation is pure Python, terminates at EOF when ``--repeat`` is
absent, has no stdin lifecycle dependency, and never opens UHD or RF hardware.
The default endpoint is loopback-only.
"""

from __future__ import annotations

import argparse
import json
import math
import signal
import struct
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import zmq

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPLEX64_BYTES = 8
IQ_MESSAGE_MAGIC = b"RFIQv1\x00\x00"


def is_loopback_tcp(endpoint: str) -> bool:
    parsed = urlparse(endpoint)
    return parsed.scheme == "tcp" and parsed.hostname in {"127.0.0.1", "localhost", "::1"} and parsed.port is not None


def resolve_session(session_dir: Path) -> tuple[dict[str, object], Path, float]:
    session_dir = session_dir.resolve()
    manifest_path = session_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read legacy manifest {manifest_path}: {exc}") from exc
    session_id = manifest.get("session_id")
    sample_rate = manifest.get("sample_rate_hz")
    if not isinstance(session_id, str) or not session_id or Path(session_id).name != session_id:
        raise ValueError("manifest session_id is missing or unsafe")
    if isinstance(sample_rate, bool) or not isinstance(sample_rate, (int, float)) or not math.isfinite(float(sample_rate)):
        raise ValueError("manifest sample_rate_hz is invalid")
    if float(sample_rate) <= 0:
        raise ValueError("manifest sample_rate_hz must be positive")
    iq_path = session_dir / f"{session_id}.sigmf-data"
    if not iq_path.is_file():
        raise ValueError(f"recording data is missing: {iq_path}")
    if iq_path.stat().st_size % COMPLEX64_BYTES:
        raise ValueError("recording byte length is not aligned to complex64")
    return manifest, iq_path, float(sample_rate)


def replay_file(
    iq_path: Path,
    sample_rate: float,
    endpoint: str,
    *,
    chunk_samples: int = 12500,
    speed: float = 1.0,
    repeat: bool = False,
    max_seconds: float | None = None,
    startup_delay_s: float = 0.5,
) -> dict[str, float | int | bool]:
    if chunk_samples <= 0:
        raise ValueError("chunk_samples must be positive")
    if speed < 0 or not math.isfinite(speed):
        raise ValueError("speed must be finite and >= 0")
    if max_seconds is not None and (max_seconds <= 0 or not math.isfinite(max_seconds)):
        raise ValueError("max_seconds must be finite and positive")

    stopping = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    previous_handlers: dict[int, object] = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, stop)

    context = zmq.Context()
    publisher = context.socket(zmq.PUB)
    publisher.setsockopt(zmq.LINGER, 0)
    publisher.setsockopt(zmq.SNDHWM, 100)
    publisher.bind(endpoint)
    bytes_per_chunk = chunk_samples * COMPLEX64_BYTES
    samples_sent = 0
    cycles_completed = 0
    started = time.monotonic()
    source_seconds_limit = max_seconds
    next_deadline = started + startup_delay_s

    try:
        if startup_delay_s:
            time.sleep(startup_delay_s)
        while not stopping:
            reached_limit = False
            with iq_path.open("rb") as handle:
                while not stopping:
                    if source_seconds_limit is not None:
                        remaining_samples = max(0, int(round(source_seconds_limit * sample_rate)) - samples_sent)
                        if remaining_samples == 0:
                            reached_limit = True
                            break
                        read_bytes = min(bytes_per_chunk, remaining_samples * COMPLEX64_BYTES)
                    else:
                        read_bytes = bytes_per_chunk
                    chunk = handle.read(read_bytes)
                    if not chunk:
                        break
                    if len(chunk) % COMPLEX64_BYTES:
                        raise ValueError("recording ended with a partial complex64 sample")
                    publisher.send(IQ_MESSAGE_MAGIC + struct.pack("<Q", samples_sent) + chunk)
                    sent_now = len(chunk) // COMPLEX64_BYTES
                    samples_sent += sent_now
                    if speed > 0:
                        next_deadline += sent_now / sample_rate / speed
                        delay = next_deadline - time.monotonic()
                        if delay > 0:
                            time.sleep(delay)
                if reached_limit or stopping:
                    break
            cycles_completed += 1
            if not repeat:
                break
    finally:
        publisher.close(0)
        context.term()
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)

    return {
        "samples_sent": samples_sent,
        "source_seconds_sent": samples_sent / sample_rate,
        "cycles_completed": cycles_completed,
        "repeat": repeat,
        "stopped_by_signal": stopping,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("--zmq-addr", default="tcp://127.0.0.1:5555")
    parser.add_argument("--repeat", action="store_true")
    parser.add_argument("--speed", type=float, default=1.0, help="1=realtime, 0=unpaced")
    parser.add_argument("--chunk-samples", type=int, default=12500)
    parser.add_argument("--max-seconds", type=float)
    parser.add_argument("--allow-nonloopback", action="store_true")
    args = parser.parse_args()

    if not args.allow_nonloopback and not is_loopback_tcp(args.zmq_addr):
        raise SystemExit("refused: offline replay endpoint must use TCP loopback")
    try:
        manifest, iq_path, sample_rate = resolve_session(args.session_dir)
        result = replay_file(
            iq_path,
            sample_rate,
            args.zmq_addr,
            chunk_samples=args.chunk_samples,
            speed=args.speed,
            repeat=args.repeat,
            max_seconds=args.max_seconds,
        )
    except ValueError as exc:
        raise SystemExit(f"replay refused: {exc}") from exc
    result.update({"session_id": manifest["session_id"], "endpoint": args.zmq_addr})
    print(json.dumps(result, sort_keys=True), file=sys.stderr)


if __name__ == "__main__":
    main()
