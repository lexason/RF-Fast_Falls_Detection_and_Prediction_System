"""G2 soak test: sustained live pipeline run, checked for overflow and memory
growth. Run at gates, not every commit -- this takes ~30 minutes wall-clock
against real hardware. CLAUDE.md §6 G2 AC: "runs >=30 min without overflow
or memory growth."

Attaches to an already-running flowgraph + spectrogram service pair by PID
(the USRP only supports one active streaming session -- this must NOT spawn
a second one alongside whatever's already live).

Usage:
    python tests/test_g2_soak.py --flowgraph-pid 1066022 --spec-pid 1065993 \
        --flowgraph-log logs/cw_doppler_live.log --spec-log logs/spectrogram_service.log \
        --duration-min 30
"""
import argparse
import re
import sys
import time
from pathlib import Path

import psutil

REPO_ROOT = Path(__file__).resolve().parent.parent
OVERFLOW_PATTERN = re.compile(r"(?<![A-Za-z])O+(?![A-Za-z])|(?<![A-Za-z])U+(?![A-Za-z])|overflow|underflow", re.IGNORECASE)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--flowgraph-pid", type=int, required=True)
    ap.add_argument("--spec-pid", type=int, required=True)
    ap.add_argument("--flowgraph-log", required=True)
    ap.add_argument("--spec-log", required=True)
    ap.add_argument("--duration-min", type=float, default=30.0)
    ap.add_argument("--sample-interval-s", type=float, default=30.0)
    args = ap.parse_args()

    flowgraph_log = Path(args.flowgraph_log)
    spec_log = Path(args.spec_log)
    log_read_offset = {str(flowgraph_log): 0, str(spec_log): 0}

    def scan_new_log_content():
        found = False
        for log_path in [flowgraph_log, spec_log]:
            if not log_path.exists():
                continue
            text = log_path.read_text()
            key = str(log_path)
            new_text = text[log_read_offset[key]:]
            log_read_offset[key] = len(text)
            if OVERFLOW_PATTERN.search(new_text):
                found = True
        return found

    scan_new_log_content()  # baseline: don't flag pre-existing content

    try:
        p1 = psutil.Process(args.flowgraph_pid)
        p2 = psutil.Process(args.spec_pid)
    except psutil.NoSuchProcess as e:
        sys.exit(f"FAIL: target process not found: {e}")

    samples = []
    t_start = time.time()
    duration_s = args.duration_min * 60
    overflow_detected = False

    while time.time() - t_start < duration_s:
        time.sleep(args.sample_interval_s)
        elapsed = time.time() - t_start

        if not p1.is_running() or not p2.is_running():
            sys.exit("FAIL: a monitored process exited during the soak test")

        rss_mb = (p1.memory_info().rss + p2.memory_info().rss) / 1e6
        samples.append((elapsed, rss_mb))
        print(f"t={elapsed:.0f}s  combined_rss={rss_mb:.1f}MB", file=sys.stderr)

        if scan_new_log_content():
            overflow_detected = True

    if not samples:
        sys.exit("FAIL: no samples collected")

    rss_values = [rss for _, rss in samples]
    rss_start, rss_end = rss_values[0], rss_values[-1]
    growth_mb = rss_end - rss_start
    growth_pct = (growth_mb / rss_start) * 100 if rss_start else 0

    print(f"\nDuration: {samples[-1][0]:.0f}s ({samples[-1][0] / 60:.1f} min)")
    print(f"RSS start: {rss_start:.1f}MB, end: {rss_end:.1f}MB, growth: {growth_mb:+.1f}MB ({growth_pct:+.1f}%)")
    print(f"Overflow/underflow detected in logs during run: {overflow_detected}")

    ok = not overflow_detected and growth_pct < 20.0  # generous threshold, real leaks grow much faster
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
