#!/usr/bin/env python3
"""Parameterised CW Doppler capture session recorder (G1).

Implements CLAUDE.md's Prime Directive 1 (never transmit blind) directly in
code, not just policy:
  - refuses to run unless config/system.yaml records a verified daughterboard
  - refuses any --f0 outside the configured ISM bands
  - every session, successful or not, is appended to logs/tx_log.csv
  - TX gain is a required, explicit argument (no silent default)

Usage:
    python scripts/capture.py --f0 5.8e9 --duration 30 --tx-gain 5 \
        --rx-gain 20 --note "walk test" --activity walk
"""
import argparse
import csv
import datetime as dt
import sys
import time
from pathlib import Path

import numpy as np
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "system.yaml"


def load_config():
    return yaml.safe_load(CONFIG_PATH.read_text())


def validate_ism_band(f0_hz, ism_bands):
    for lo, hi in ism_bands:
        if lo <= f0_hz <= hi:
            return True
    return False


def log_tx_session(log_path, session_id, f0_hz, tx_gain_db, rx_gain_db, duration_s, note, status):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not log_path.exists()
    with open(log_path, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["timestamp_utc", "session_id", "f0_hz", "tx_gain_db", "rx_gain_db", "duration_s", "note", "status"])
        writer.writerow([dt.datetime.now(dt.timezone.utc).isoformat(), session_id, f0_hz, tx_gain_db, rx_gain_db, duration_s, note, status])


def run_capture(cfg, args, session_id):
    """CW Doppler capture: TX a constant tone at f0, RX at cfg sample rate,
    write raw IQ to SigMF. Requires `uhd` python bindings and live hardware.
    """
    from gnuradio import analog, blocks, gr, uhd

    fs = cfg["sample_rates"]["capture_hz"]
    n_samples = int(round(args.duration * fs))

    tb = gr.top_block()

    usrp_sink = uhd.usrp_sink(f"addr={cfg['usrp']['addr']}", uhd.stream_args(cpu_format="fc32", channels=[0]))
    usrp_sink.set_samp_rate(fs)
    usrp_sink.set_center_freq(args.f0)
    usrp_sink.set_gain(args.tx_gain)
    usrp_sink.set_antenna(cfg["antenna"]["tx_port_antenna"])
    tone_src = analog.sig_source_c(fs, analog.GR_CONST_WAVE, 0, 1.0, 0)  # CW: constant-envelope carrier

    usrp_source = uhd.usrp_source(f"addr={cfg['usrp']['addr']}", uhd.stream_args(cpu_format="fc32", channels=[0]))
    usrp_source.set_samp_rate(fs)
    usrp_source.set_center_freq(args.f0)
    usrp_source.set_gain(args.rx_gain)
    usrp_source.set_antenna(cfg["antenna"]["rx_port_antenna"])

    head = blocks.head(gr.sizeof_gr_complex, n_samples)
    vec_sink = blocks.vector_sink_c()

    tb.connect(tone_src, usrp_sink)
    tb.connect(usrp_source, head, vec_sink)

    # tb.wait() alone would hang forever: tone_src is an infinite source with
    # no natural stop signal, so the flowgraph never fully quiesces on its
    # own even though the RX side's blocks.head stops after n_samples.
    tb.start()
    time.sleep(args.duration + 1.0)
    tb.stop()
    tb.wait()

    return np.array(vec_sink.data(), dtype=np.complex64)


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
    meta.add_capture(0, metadata={sigmf.FREQUENCY_KEY: args.f0})
    meta.add_annotation(0, len(iq), metadata={sigmf.LABEL_KEY: args.activity})
    meta.tofile(session_dir / f"{session_id}.sigmf-meta")

    import json
    manifest = {
        "session_id": session_id,
        "synthetic": False,
        "carrier_hz": args.f0,
        "sample_rate_hz": fs,
        "tx_gain_db": args.tx_gain,
        "rx_gain_db": args.rx_gain,
        "antenna_geometry": cfg["antenna"]["geometry"],
        "occupancy": args.occupancy,
        "scripted_activity_timeline": [{"t_start": 0.0, "t_end": len(iq) / fs, "label": args.activity}],
        "room": args.room,
    }
    (session_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    labels_dir = out_root / cfg["paths"]["data_labels"]
    labels_dir.mkdir(parents=True, exist_ok=True)
    with open(labels_dir / f"{session_id}.jsonl", "w") as f:
        f.write(json.dumps(manifest["scripted_activity_timeline"][0]) + "\n")

    return session_dir


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--f0", type=float, required=True, help="carrier frequency, Hz (must fall inside a configured ISM band)")
    ap.add_argument("--duration", type=float, required=True, help="capture duration, seconds")
    ap.add_argument("--tx-gain", type=float, required=True, help="TX gain, dB (start at minimum, raise incrementally)")
    ap.add_argument("--rx-gain", type=float, required=True, help="RX gain, dB")
    ap.add_argument("--note", required=True, help="free-text session description")
    ap.add_argument("--activity", default="other", choices=["walk", "sit_down", "stand_up", "lie_down", "fall", "idle", "other"])
    ap.add_argument("--occupancy", default="researcher (self-test)")
    ap.add_argument("--room", default="unspecified")
    ap.add_argument("--session-id", default=None)
    ap.add_argument("--out-root", default=str(REPO_ROOT))
    args = ap.parse_args()

    cfg = load_config()
    out_root = Path(args.out_root)
    log_path = out_root / cfg["paths"]["tx_log"]

    # --- Safety gate (Prime Directive 1: never transmit blind) ---
    if not cfg["usrp"].get("daughterboard_verified", False):
        log_tx_session(log_path, args.session_id or "REJECTED", args.f0, args.tx_gain, args.rx_gain, args.duration, args.note, "REJECTED: daughterboard unverified")
        sys.exit(
            "refusing to transmit: config/system.yaml usrp.daughterboard_verified is false.\n"
            "Complete G0 (uhd_usrp_probe) and record the confirmed daughterboard/band in "
            "config/system.yaml before running a live capture. See STATE.md and "
            "docs/n210_fpga_compat_fix_guide.md for the current blocker."
        )
    if not validate_ism_band(args.f0, cfg["ism_bands_hz"]):
        log_tx_session(log_path, args.session_id or "REJECTED", args.f0, args.tx_gain, args.rx_gain, args.duration, args.note, "REJECTED: f0 outside ISM bands")
        sys.exit(f"refusing to transmit: f0={args.f0:.0f} Hz is outside the configured ISM bands {cfg['ism_bands_hz']}")

    session_id = args.session_id or f"{dt.date.today().isoformat()}_{args.activity}_{int(args.f0)}"

    log_tx_session(log_path, session_id, args.f0, args.tx_gain, args.rx_gain, args.duration, args.note, "STARTED")
    try:
        fs = cfg["sample_rates"]["capture_hz"]
        iq = run_capture(cfg, args, session_id)
        session_dir = write_session(session_id, iq, fs, cfg, args, out_root)
        log_tx_session(log_path, session_id, args.f0, args.tx_gain, args.rx_gain, args.duration, args.note, "COMPLETED")
        print(f"wrote {session_dir} ({len(iq)} samples, {len(iq) / fs:.1f}s)")
    except Exception as e:
        log_tx_session(log_path, session_id, args.f0, args.tx_gain, args.rx_gain, args.duration, args.note, f"FAILED: {e}")
        raise


if __name__ == "__main__":
    main()
