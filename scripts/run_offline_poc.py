#!/usr/bin/env python3
"""Supervise one isolated RF Sensing Falls offline replay run.

The plan contains no UHD, GNU Radio hardware, N210, transmit, or sister-project
command.  It defaults to dry-run and binds the dashboard and ZMQ endpoints to
loopback.  ``--run`` starts only repository-local offline processes and records a
run manifest plus per-process logs under ``artifacts/runs``.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "configs" / "poc" / "offline_replay.yaml"
DSP_HEALTH_PREFIX = "DSP_HEALTH_JSON="


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha512_file(path: Path) -> str:
    digest = hashlib.sha512()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def loopback_endpoint(endpoint: str) -> bool:
    parsed = urlparse(endpoint)
    return parsed.scheme == "tcp" and parsed.hostname in {"127.0.0.1", "localhost", "::1"} and parsed.port is not None


def ensure_bind_ports_available(config: dict[str, object], dashboard_host: str = "127.0.0.1") -> None:
    """Fail before starting children if any local publisher/dashboard port is occupied."""
    pipeline = config["pipeline"]
    endpoints = [pipeline["raw_iq"], pipeline["spectrogram"], pipeline["classifier"], pipeline["activity"]]
    ports = [int(urlparse(str(endpoint)).port) for endpoint in endpoints]
    bind_targets = [("127.0.0.1", port) for port in ports]
    bind_targets.append((dashboard_host, int(config["dashboard"]["port"])))
    for host, port in bind_targets:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, port))
            except OSError as exc:
                raise ValueError(f"required bind {host}:{port} is unavailable") from exc


def load_config(path: Path) -> dict[str, object]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("mode") != "silent_research_poc":
        raise ValueError("configuration must declare silent_research_poc mode")
    if config.get("network_policy") != "loopback_only":
        raise ValueError("offline POC requires loopback_only network policy")
    pipeline = config.get("pipeline")
    if not isinstance(pipeline, dict) or not all(loopback_endpoint(str(value)) for value in pipeline.values()):
        raise ValueError("every pipeline endpoint must be TCP loopback")
    dashboard = config.get("dashboard")
    if not isinstance(dashboard, dict) or dashboard.get("host") != "127.0.0.1":
        raise ValueError("dashboard host must be 127.0.0.1")
    return config


def command_plan(
    config: dict[str, object],
    session: Path,
    sample_rate_hz: float,
    max_seconds: float | None,
    speed: float,
    repeat: bool,
    run_dir: Path,
    dashboard_host: str = "127.0.0.1",
) -> list[dict[str, object]]:
    pipeline = config["pipeline"]
    dashboard = config["dashboard"]
    python = sys.executable
    model_dir = (REPO_ROOT / str(config["model_dir"])).resolve()
    commands = [
        {
            "name": "spectrogram",
            "argv": [python, str(REPO_ROOT / "dsp" / "spectrogram_service.py"), "--in-addr", pipeline["raw_iq"], "--out-addr", pipeline["spectrogram"], "--samp-rate", str(sample_rate_hz)],
        },
        {
            "name": "classifier",
            "argv": [python, str(REPO_ROOT / "inference" / "realtime_classifier.py"), "--in-addr", pipeline["spectrogram"], "--out-addr", pipeline["classifier"], "--model-dir", str(model_dir), "--samp-rate", str(sample_rate_hz)],
        },
        {
            "name": "posture",
            "argv": [python, str(REPO_ROOT / "inference" / "posture_state_machine.py"), "--in-addr", pipeline["classifier"], "--out-addr", pipeline["activity"]],
        },
        {
            "name": "event_logger",
            "argv": [python, str(REPO_ROOT / "scripts" / "live_test_logger.py"), "--in-addr", pipeline["activity"], "--out", str(run_dir / "events.jsonl")],
        },
        {
            "name": "dashboard",
            "argv": [python, "-m", "uvicorn", "dashboard.app:app", "--host", dashboard_host, "--port", str(dashboard["port"]), "--log-level", "warning"],
            "env": {
                "RF_FALLS_SPECTROGRAM_ADDR": pipeline["spectrogram"],
                "RF_FALLS_ACTIVITY_ADDR": pipeline["activity"],
                "RF_FALLS_DASHBOARD_ACCESS": "tailscale" if dashboard_host != "127.0.0.1" else "loopback",
                "RF_FALLS_DASHBOARD_BIND_HOST": dashboard_host,
                "RF_FALLS_TAILSCALE_IPV4": dashboard_host if dashboard_host != "127.0.0.1" else "",
            },
        },
    ]
    replay = [
        python,
        str(REPO_ROOT / "scripts" / "replay.py"),
        str(session),
        "--zmq-addr",
        pipeline["raw_iq"],
        "--speed",
        str(speed),
    ]
    if max_seconds is not None:
        replay.extend(["--max-seconds", str(max_seconds)])
    if repeat:
        replay.append("--repeat")
    commands.append({"name": "replay", "argv": replay})
    return commands


def wait_dashboard(host: str, port: int, timeout_s: float = 10.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout_s
    url = f"http://{host}:{port}/healthz"
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1.0) as response:
                if response.status == 200:
                    return json.loads(response.read())
        except Exception as exc:  # bounded local readiness probe
            last_error = exc
        time.sleep(0.1)
    raise RuntimeError(f"dashboard readiness failed: {last_error}")


def validated_tailscale_ipv4(value: str | None) -> str:
    if value is None:
        return "127.0.0.1"
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError("--tailscale-dashboard-ip must be a valid IPv4 address") from exc
    if not isinstance(address, ipaddress.IPv4Address) or address not in ipaddress.ip_network("100.64.0.0/10"):
        raise ValueError("--tailscale-dashboard-ip must be in Tailscale's 100.64.0.0/10 range")
    return str(address)


def terminate_process(process: subprocess.Popen[bytes], timeout_s: float = 5.0) -> None:
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout_s)


def summarize_events(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"events": 0, "fall_candidates": 0, "quality_changes": 0, "classification_delays_s": []}
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    delays = sorted(
        float(event["classification_delay_s"])
        for event in events
        if isinstance(event.get("classification_delay_s"), (int, float))
    )
    return {
        "events": len(events),
        "fall_candidates": sum(event.get("type") == "fall_candidate" for event in events),
        "quality_changes": sum(event.get("type") == "quality_change" for event in events),
        "classification_delays_s": delays,
        "classification_delay_max_s": max(delays) if delays else None,
    }


def read_last_json_line(path: Path, prefix: str = "") -> dict[str, object]:
    """Read the final structured record matching ``prefix`` from a component log."""
    matches = [line[len(prefix):] for line in path.read_text(encoding="utf-8").splitlines() if line.startswith(prefix)]
    if not matches:
        raise ValueError(f"missing structured record {prefix!r} in {path.name}")
    value = json.loads(matches[-1])
    if not isinstance(value, dict):
        raise ValueError(f"structured record in {path.name} is not an object")
    return value


def evaluate_dsp_health(health: dict[str, object], replay: dict[str, object]) -> dict[str, object]:
    """Apply the offline evidence policy: exact delivery and zero rejected DSP input."""
    counter_names = (
        "input_chunks",
        "input_samples",
        "frames_published",
        "invalid_chunks",
        "invalid_frames",
        "sequence_gaps",
    )
    counters: dict[str, int] = {}
    for name in counter_names:
        value = health.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"DSP health counter {name} is invalid")
        counters[name] = value
    samples_sent = replay.get("samples_sent")
    if not isinstance(samples_sent, int) or isinstance(samples_sent, bool) or samples_sent < 1:
        raise ValueError("replay samples_sent is invalid")
    violations = []
    if counters["input_samples"] != samples_sent:
        violations.append(f"input_samples={counters['input_samples']} differs from replay samples_sent={samples_sent}")
    for name in ("invalid_chunks", "invalid_frames", "sequence_gaps"):
        if counters[name] != 0:
            violations.append(f"{name}={counters[name]} exceeds zero-loss policy")
    if counters["input_chunks"] < 1 or counters["frames_published"] < 1:
        violations.append("DSP processed no chunks or published no frames")
    return {
        **counters,
        "policy": "exact_replay_sample_delivery_and_zero_invalid_or_gapped_input",
        "policy_passed": not violations,
        "violations": violations,
    }


def assert_pipeline_alive(processes: list[tuple[str, subprocess.Popen[bytes], object]]) -> None:
    early_exits = [(name, process.returncode) for name, process, _ in processes if process.poll() is not None]
    if early_exits:
        raise RuntimeError(f"pipeline process exited early: {early_exits}")


def wait_for_replay_or_child_exit(
    processes: list[tuple[str, subprocess.Popen[bytes], object]],
    *,
    poll_interval_s: float = 0.2,
) -> int:
    """Wait for replay while failing immediately if a supervised child exits."""
    if not processes or processes[-1][0] != "replay":
        raise ValueError("the final supervised process must be replay")
    replay_process = processes[-1][1]
    while True:
        replay_status = replay_process.poll()
        if replay_status is not None:
            return replay_status
        unexpected = []
        for name, process, _ in processes[:-1]:
            status = process.poll()
            if status is not None:
                unexpected.append((name, status))
        if unexpected:
            raise RuntimeError(f"pipeline process exited during replay: {unexpected}")
        time.sleep(poll_interval_s)


def main() -> None:
    def graceful_stop(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, graceful_stop)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--session", type=Path)
    parser.add_argument("--max-seconds", type=float)
    parser.add_argument("--speed", type=float)
    parser.add_argument("--repeat", action="store_true")
    parser.add_argument("--tailscale-dashboard-ip", help="bind derived dashboard only to this local Tailscale IPv4")
    parser.add_argument("--run", action="store_true", help="execute the offline plan; default is dry-run")
    args = parser.parse_args()

    try:
        dashboard_host = validated_tailscale_ipv4(args.tailscale_dashboard_ip)
    except ValueError as exc:
        raise SystemExit(f"offline POC configuration refused: {exc}") from exc

    try:
        config = load_config(args.config.resolve())
    except (OSError, ValueError) as exc:
        raise SystemExit(f"offline POC configuration refused: {exc}") from exc
    replay_config = config["replay"]
    session = (args.session or REPO_ROOT / str(config["default_session"])).resolve()
    max_seconds = args.max_seconds if args.max_seconds is not None else replay_config.get("max_seconds")
    speed = args.speed if args.speed is not None else float(replay_config["speed"])
    repeat = bool(args.repeat or replay_config.get("repeat", False))
    if repeat and max_seconds is None:
        raise SystemExit("repeat mode requires --max-seconds for bounded supervision")
    if not (session / "manifest.json").is_file():
        raise SystemExit(f"session is invalid: {session}")
    try:
        session_manifest = json.loads((session / "manifest.json").read_text(encoding="utf-8"))
        sample_rate_hz = float(session_manifest["sample_rate_hz"])
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise SystemExit(f"session sample rate is invalid: {exc}") from exc
    if not (sample_rate_hz > 0 and sample_rate_hz < 25_000_000):
        raise SystemExit("session sample rate must be in (0, 25 MHz)")
    session_id = session_manifest.get("session_id")
    if not isinstance(session_id, str) or Path(session_id).name != session_id:
        raise SystemExit("session_id is invalid")
    input_data_path = session / f"{session_id}.sigmf-data"
    input_metadata_path = session / f"{session_id}.sigmf-meta"
    if not input_data_path.is_file() or not input_metadata_path.is_file():
        raise SystemExit("session SigMF data/metadata are incomplete")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    run_dir = REPO_ROOT / "artifacts" / "runs" / run_id
    plan = command_plan(config, session, sample_rate_hz, max_seconds, speed, repeat, run_dir, dashboard_host)
    model_dir = (REPO_ROOT / str(config["model_dir"])).resolve()
    model_metadata = json.loads((model_dir / "metadata.json").read_text(encoding="utf-8"))
    if model_metadata.get("promotion_eligible") is not False or model_metadata.get("performance_gate_passed") is not False:
        raise SystemExit("offline POC requires an explicitly promotion-blocked failed-gate research model")

    dry_run = {
        "mode": config["mode"],
        "network_policy": config["network_policy"],
        "network_policy_scope": "internal_pipeline_only",
        "internal_pipeline_network_policy": config["network_policy"],
        "dashboard_access": "tailscale_only" if dashboard_host != "127.0.0.1" else "loopback_only",
        "dashboard_bind_host": dashboard_host,
        "session": str(session),
        "sample_rate_hz": sample_rate_hz,
        "model_id": model_metadata.get("model_id"),
        "performance_gate_passed": False,
        "commands": plan,
    }
    if not args.run:
        print(json.dumps(dry_run, indent=2))
        return

    try:
        ensure_bind_ports_available(config, dashboard_host)
    except ValueError as exc:
        raise SystemExit(f"offline POC preflight refused: {exc}") from exc
    run_dir.mkdir(parents=True, exist_ok=False)
    source_paths = [
        Path(__file__).resolve(),
        REPO_ROOT / "scripts" / "replay.py",
        REPO_ROOT / "dsp" / "spectrogram_service.py",
        REPO_ROOT / "inference" / "model_runtime.py",
        REPO_ROOT / "inference" / "realtime_classifier.py",
        REPO_ROOT / "inference" / "posture_state_machine.py",
        REPO_ROOT / "scripts" / "live_test_logger.py",
        REPO_ROOT / "dashboard" / "app.py",
        REPO_ROOT / "features" / "micro_doppler.py",
    ]
    model_evaluation_path = (REPO_ROOT / model_metadata["evaluation_artifact"]).resolve()
    manifest = {
        **dry_run,
        "run_id": run_id,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "config_sha256": sha256_file(args.config.resolve()),
        "dependency_lock_sha256": sha256_file(REPO_ROOT / "requirements-poc.lock"),
        "source_sha256": {
            str(path.relative_to(REPO_ROOT)): sha256_file(path) for path in source_paths
        },
        "input_artifact": {
            "session_id": session_id,
            "manifest_sha256": sha256_file(session / "manifest.json"),
            "sigmf_metadata_sha256": sha256_file(input_metadata_path),
            "sigmf_data_sha512": sha512_file(input_data_path),
            "sigmf_data_bytes": input_data_path.stat().st_size,
        },
        "model_metadata_sha256": sha256_file(model_dir / "metadata.json"),
        "model_evaluation": {
            "path": model_metadata["evaluation_artifact"],
            "sha256": sha256_file(model_evaluation_path),
        },
        "model_artifact_sha256": model_metadata["artifact_sha256"],
        "status": "STARTING",
    }
    manifest_path = run_dir / "run.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    processes: list[tuple[str, subprocess.Popen[bytes], object]] = []
    replay_return_code: int | None = None
    try:
        for item in plan[:-1]:
            log_handle = (run_dir / f"{item['name']}.log").open("ab", buffering=0)
            child_environment = {**os.environ, **item.get("env", {})}
            process = subprocess.Popen(
                item["argv"],
                cwd=REPO_ROOT,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=child_environment,
            )
            processes.append((item["name"], process, log_handle))
        health = wait_dashboard(dashboard_host, int(config["dashboard"]["port"]))
        time.sleep(1.0)
        assert_pipeline_alive(processes)
        replay_item = plan[-1]
        replay_log = (run_dir / "replay.log").open("ab", buffering=0)
        replay_process = subprocess.Popen(replay_item["argv"], cwd=REPO_ROOT, stdout=replay_log, stderr=subprocess.STDOUT)
        processes.append(("replay", replay_process, replay_log))
        time.sleep(0.1)
        assert_pipeline_alive(processes)
        manifest["dashboard_health"] = health
        manifest["status"] = "RUNNING"
        manifest["runtime_started_at_utc"] = datetime.now(timezone.utc).isoformat()
        manifest["component_pids"] = {name: process.pid for name, process, _ in processes}
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        replay_return_code = wait_for_replay_or_child_exit(processes)
        time.sleep(2.0)
        if replay_return_code != 0:
            raise RuntimeError(f"replay exited with status {replay_return_code}")
        assert_pipeline_alive(processes[:-1])
        manifest["event_summary"] = summarize_events(run_dir / "events.jsonl")
        manifest["status"] = "COMPLETED"
    except KeyboardInterrupt:
        manifest["status"] = "INTERRUPTED"
    except Exception as exc:
        manifest["status"] = "FAILED"
        manifest["error"] = str(exc)
    finally:
        for _, process, _ in reversed(processes):
            terminate_process(process)
        for _, _, handle in processes:
            handle.close()
        try:
            replay_summary = read_last_json_line(run_dir / "replay.log")
            manifest["replay_summary"] = replay_summary
            dsp_health = evaluate_dsp_health(
                read_last_json_line(run_dir / "spectrogram.log", DSP_HEALTH_PREFIX),
                replay_summary,
            )
            manifest["dsp_health"] = dsp_health
            if manifest["status"] == "COMPLETED" and not dsp_health["policy_passed"]:
                manifest["status"] = "FAILED"
                manifest["error"] = "DSP loss policy failed: " + "; ".join(dsp_health["violations"])
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            manifest["dsp_health_error"] = str(exc)
            if manifest["status"] == "COMPLETED":
                manifest["status"] = "FAILED"
                manifest["error"] = f"DSP health evidence missing or invalid: {exc}"
        manifest["replay_return_code"] = replay_return_code
        manifest["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"run_dir": str(run_dir), "status": manifest["status"]}, sort_keys=True))
    if manifest["status"] != "COMPLETED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
