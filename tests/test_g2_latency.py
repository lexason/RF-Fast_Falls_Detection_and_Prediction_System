"""G2 latency benchmark: measures end-to-end delay from spectrogram frame
timestamp (embedded at dsp/spectrogram_service.py) to receipt by a ZMQ SUB
consumer, as a proxy for acquisition -> DSP -> viewer latency. CLAUDE.md §6
G2 AC: "<500ms latency (measured, benchmark in tests/)".

Requires the live pipeline already running (sdr/cw_doppler_tx_rx.py ->
dsp/spectrogram_service.py) -- this measures, it doesn't launch them, since
the USRP only supports one active streaming session and the live pipeline
is likely already attached to the real device.

Usage:
    python tests/test_g2_latency.py --addr tcp://127.0.0.1:5591 --duration-s 20
"""
import argparse
import sys
import time

import numpy as np
import zmq


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--addr", default="tcp://127.0.0.1:5591", help="spectrogram service ZMQ PUB address")
    ap.add_argument("--duration-s", type=float, default=20.0)
    ap.add_argument("--max-latency-ms", type=float, default=500.0, help="AC threshold")
    args = ap.parse_args()

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(args.addr)
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    sub.setsockopt(zmq.RCVTIMEO, 5000)

    latencies_ms = []
    t_start = time.time()
    try:
        while time.time() - t_start < args.duration_s:
            msg = sub.recv()
            recv_time = time.time()
            frame_ts = np.frombuffer(msg[:8], dtype=np.float64)[0]
            latencies_ms.append((recv_time - frame_ts) * 1000)
    except zmq.Again:
        pass

    if not latencies_ms:
        sys.exit("FAIL: no frames received -- is the live pipeline running?")

    arr = np.array(latencies_ms)
    print(f"n={len(arr)} frames over {args.duration_s:.0f}s")
    print(f"latency (ms): min={arr.min():.1f} p50={np.percentile(arr, 50):.1f} "
          f"p95={np.percentile(arr, 95):.1f} max={arr.max():.1f}")

    p95 = np.percentile(arr, 95)
    ok = p95 < args.max_latency_ms
    print(f"AC: p95 < {args.max_latency_ms:.0f}ms -> {'PASS' if ok else 'FAIL'} (p95={p95:.1f}ms)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
