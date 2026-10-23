#!/usr/bin/env python3
"""G2: live CW Doppler acquisition flowgraph.

Continuously TXs a CW tone (antenna="TX/RX", RF1) and RXs the reflected
signal (antenna="RX2", RF2), publishing raw complex64 samples over ZMQ PUB
-- the standard GNU-Radio-is-acquisition-only, ZMQ-PUB-to-Python-services
decoupling locked in at CLAUDE.md §7. Downstream DSP services (clutter
removal, STFT spectrogram) subscribe to this stream; they don't care
whether it's this live flowgraph or sdr/replay_source.py underneath, same
interface either way.

Unlike scripts/capture.py (one-shot, fixed duration, writes to disk), this
runs indefinitely until stopped (Ctrl-C or SIGTERM) -- it's the acquisition
half of G2's real-time pipeline, not a session recorder.

Reads carrier/gains/antenna config from config/system.yaml so this and
capture.py never drift apart on RF settings.

Usage:
    python sdr/cw_doppler_tx_rx.py [--tx-gain 5] [--zmq-addr tcp://127.0.0.1:5580]
"""
import argparse
import csv
import datetime as dt
import signal
import sys
from pathlib import Path

import yaml
from gnuradio import analog, gr, uhd, zeromq

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_config():
    return yaml.safe_load((REPO_ROOT / "config" / "system.yaml").read_text())


def log_tx_session(log_path, session_id, f0_hz, tx_gain_db, rx_gain_db, duration_s, note, status):
    """Prime Directive 1: log every TX session. Unlike scripts/capture.py's
    fixed-duration sessions, this flowgraph runs indefinitely, so duration_s
    is 'continuous' until a STOPPED entry is logged on clean shutdown."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not log_path.exists()
    with open(log_path, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["timestamp_utc", "session_id", "f0_hz", "tx_gain_db", "rx_gain_db", "duration_s", "note", "status"])
        writer.writerow([dt.datetime.now(dt.timezone.utc).isoformat(), session_id, f0_hz, tx_gain_db, rx_gain_db, duration_s, note, status])


def build_flowgraph(cfg, tx_gain_db, rx_gain_db, zmq_addr):
    fs = cfg["sample_rates"]["capture_hz"]
    f0 = cfg["carrier"]["f0_hz"]

    tb = gr.top_block()

    tone_src = analog.sig_source_c(fs, analog.GR_CONST_WAVE, 0, 1.0, 0)

    usrp_sink = uhd.usrp_sink(f"addr={cfg['usrp']['addr']}", uhd.stream_args(cpu_format="fc32", channels=[0]))
    usrp_sink.set_samp_rate(fs)
    usrp_sink.set_center_freq(f0)
    usrp_sink.set_gain(tx_gain_db)
    usrp_sink.set_antenna(cfg["antenna"]["tx_port_antenna"])

    usrp_source = uhd.usrp_source(f"addr={cfg['usrp']['addr']}", uhd.stream_args(cpu_format="fc32", channels=[0]))
    usrp_source.set_samp_rate(fs)
    usrp_source.set_center_freq(f0)
    usrp_source.set_gain(rx_gain_db)
    usrp_source.set_antenna(cfg["antenna"]["rx_port_antenna"])

    zmq_pub = zeromq.pub_sink(gr.sizeof_gr_complex, 1, zmq_addr, 100, False, -1, "", True)

    tb.connect(tone_src, usrp_sink)
    tb.connect(usrp_source, zmq_pub)

    return tb


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tx-gain", type=float, default=5.0, help="TX gain, dB (default: 5, matches the gain-matched G1 reference sessions)")
    ap.add_argument("--rx-gain", type=float, default=20.0)
    ap.add_argument("--zmq-addr", default="tcp://127.0.0.1:5580", help="ZMQ PUB bind address for downstream DSP services")
    args = ap.parse_args()

    cfg = load_config()
    if not cfg["usrp"].get("daughterboard_verified", False):
        sys.exit("refusing to transmit: config/system.yaml usrp.daughterboard_verified is false.")

    log_path = REPO_ROOT / cfg["paths"]["tx_log"]
    session_id = f"live_cw_doppler_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    f0 = cfg["carrier"]["f0_hz"]

    tb = build_flowgraph(cfg, args.tx_gain, args.rx_gain, args.zmq_addr)

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()
        log_tx_session(log_path, session_id, f0, args.tx_gain, args.rx_gain, "continuous", "live G2/G3 acquisition flowgraph, stopped", "STOPPED")
        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    log_tx_session(log_path, session_id, f0, args.tx_gain, args.rx_gain, "continuous", "live G2/G3 acquisition flowgraph, indefinite run", "STARTED")
    print(f"streaming live CW Doppler on {args.zmq_addr} (f0={cfg['carrier']['f0_hz']/1e9:.3f} GHz, "
          f"tx_gain={args.tx_gain}dB, rx_gain={args.rx_gain}dB)", file=sys.stderr)
    tb.start()
    tb.wait()


if __name__ == "__main__":
    main()
