#!/usr/bin/env python3
"""G3: multi-rep dataset session recorder.

Unlike scripts/capture.py (opens its own USRP TX/RX session, one-shot,
whole-clip label), this taps the raw IQ ZMQ PUB stream of the already-running
live flowgraph (sdr/cw_doppler_tx_rx.py) -- the USRP only supports one active
streaming session, and G3 dataset collection needs multi-minute continuous
recordings of many repetitions while the live dashboard keeps running, so
recording must not open a second UHD connection. This is exactly the
GNU-Radio-acquisition / ZMQ-decoupled-consumers architecture locked in at
CLAUDE.md §7 -- record_session.py is just another ZMQ SUB consumer.

Produces a raw SigMF session like capture.py, but with an EMPTY
scripted_activity_timeline -- scripts/label_tool.py fills that in afterward
by detecting motion-transient boundaries in the clutter-removed signal and
assigning labels according to the known rep sequence the researcher performed
(e.g. "sit_down,stand_up" repeated), since the *timing* of each rep is more
reliably recovered from the signal itself than from live human-reaction-time
cues, but the *label* of each event depends on the scripted protocol the
detector can't infer from the waveform alone.

Usage:
    python scripts/record_session.py --session-id 2026-07-25_walk_reps \
        --activity-class walk --duration 180 --occupancy "researcher (self-test)" \
        --note "20+ walking passes, varied speed/path"
"""
import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np
import yaml
import zmq

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "system.yaml"


def load_config():
    return yaml.safe_load(CONFIG_PATH.read_text())


def log_tx_session(log_path, session_id, f0_hz, tx_gain_db, rx_gain_db, duration_s, note, status):
    import csv
    log_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not log_path.exists()
    with open(log_path, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["timestamp_utc", "session_id", "f0_hz", "tx_gain_db", "rx_gain_db", "duration_s", "note", "status"])
        writer.writerow([dt.datetime.now(dt.timezone.utc).isoformat(), session_id, f0_hz, tx_gain_db, rx_gain_db, duration_s, note, status])


def record_from_zmq(zmq_addr, fs, duration_s):
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_addr)
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    sub.setsockopt(zmq.RCVTIMEO, 5000)

    n_target = int(round(duration_s * fs))
    chunks = []
    n_collected = 0
    t0 = time.time()
    try:
        while n_collected < n_target:
            msg = sub.recv()
            chunk = np.frombuffer(msg, dtype=np.complex64)
            chunks.append(chunk)
            n_collected += len(chunk)
    except zmq.Again:
        sys.exit(f"FAIL: no data received from {zmq_addr} for 5s -- is the live flowgraph "
                  f"(sdr/cw_doppler_tx_rx.py) running? (check `ps` / STATE.md for its PID)")
    elapsed = time.time() - t0
    iq = np.concatenate(chunks)[:n_target]
    return iq, elapsed


def write_session(session_id, iq, fs, cfg, args, out_root):
    import sigmf
    from sigmf import SigMFFile

    session_dir = out_root / cfg["paths"]["data_raw"] / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    data_path = session_dir / f"{session_id}.sigmf-data"
    iq.astype(np.complex64).tofile(data_path)

    meta = SigMFFile(
        data_file=data_path,
        global_info={
            sigmf.DATATYPE_KEY: "cf32_le",
            sigmf.SAMPLE_RATE_KEY: fs,
            sigmf.DESCRIPTION_KEY: args.note,
            sigmf.AUTHOR_KEY: "carat-research",
            "carat:synthetic": False,
        },
    )
    meta.add_capture(0, metadata={sigmf.FREQUENCY_KEY: cfg["carrier"]["f0_hz"]})
    meta.add_annotation(0, len(iq), metadata={sigmf.LABEL_KEY: f"{args.activity_class}_multi_rep_unlabeled"})
    meta.tofile(session_dir / f"{session_id}.sigmf-meta")

    manifest = {
        "session_id": session_id,
        "synthetic": False,
        "carrier_hz": cfg["carrier"]["f0_hz"],
        "sample_rate_hz": fs,
        "tx_gain_db": args.tx_gain,
        "rx_gain_db": args.rx_gain,
        "antenna_geometry": cfg["antenna"]["geometry"],
        "occupancy": args.occupancy,
        "room": args.room,
        "activity_class": args.activity_class,
        "multi_rep": True,
        "scripted_activity_timeline": [],  # filled in by scripts/label_tool.py
        "recorded_via": "record_session.py tap on live flowgraph ZMQ PUB (no new UHD session opened)",
    }
    (session_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return session_dir


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--session-id", required=True)
    ap.add_argument("--activity-class", required=True, choices=["walk", "sit_stand", "lie_down", "fall", "idle", "empty_room"])
    ap.add_argument("--duration", type=float, required=True, help="recording duration, seconds")
    ap.add_argument("--note", required=True)
    ap.add_argument("--occupancy", default="researcher (self-test)")
    ap.add_argument("--room", default="lab, bench setup")
    ap.add_argument("--zmq-addr", default="tcp://127.0.0.1:5580", help="live flowgraph raw-IQ ZMQ PUB address")
    ap.add_argument("--tx-gain", type=float, default=5.0, help="record-keeping only -- actual gain is set by the already-running live flowgraph")
    ap.add_argument("--rx-gain", type=float, default=20.0, help="record-keeping only -- actual gain is set by the already-running live flowgraph")
    ap.add_argument("--out-root", default=str(REPO_ROOT))
    args = ap.parse_args()

    cfg = load_config()
    out_root = Path(args.out_root)
    log_path = out_root / cfg["paths"]["tx_log"]
    fs = cfg["sample_rates"]["capture_hz"]

    if not cfg["usrp"].get("daughterboard_verified", False):
        sys.exit("refusing to record: config/system.yaml usrp.daughterboard_verified is false.")

    log_tx_session(log_path, args.session_id, cfg["carrier"]["f0_hz"], args.tx_gain, args.rx_gain,
                    args.duration, f"[TAP on live flowgraph, no new TX] {args.note}", "STARTED")
    try:
        iq, elapsed = record_from_zmq(args.zmq_addr, fs, args.duration)
        session_dir = write_session(args.session_id, iq, fs, cfg, args, out_root)
        log_tx_session(log_path, args.session_id, cfg["carrier"]["f0_hz"], args.tx_gain, args.rx_gain,
                        args.duration, f"[TAP on live flowgraph, no new TX] {args.note}", "COMPLETED")
        print(f"wrote {session_dir} ({len(iq)} samples, {len(iq)/fs:.1f}s, wall-clock {elapsed:.1f}s)")
    except SystemExit:
        log_tx_session(log_path, args.session_id, cfg["carrier"]["f0_hz"], args.tx_gain, args.rx_gain,
                        args.duration, f"[TAP on live flowgraph, no new TX] {args.note}", "FAILED: no data from live flowgraph")
        raise
    except Exception as e:
        log_tx_session(log_path, args.session_id, cfg["carrier"]["f0_hz"], args.tx_gain, args.rx_gain,
                        args.duration, f"[TAP on live flowgraph, no new TX] {args.note}", f"FAILED: {e}")
        raise


if __name__ == "__main__":
    main()
