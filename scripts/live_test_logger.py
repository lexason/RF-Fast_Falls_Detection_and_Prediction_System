#!/usr/bin/env python3
"""Append local research-state events to a JSONL evidence log.
the posture state machine's ZMQ output (same stream the dashboard consumes)
and appends every state change/fall-candidate event to a JSONL log with a
wall-clock timestamp, so predictions can be cross-referenced against
whatever the researcher actually did once they report it back.

Read-only observer -- does not touch the live pipeline, model, or any
system file. Safe to run alongside the dashboard without interference
(ZMQ PUB/SUB supports multiple subscribers).

Usage:
    python scripts/live_test_logger.py --out logs/live_test_2026-08-02.jsonl
"""
import argparse
import datetime as dt
import json
import zmq

ACTIVITY_ZMQ_ADDR = "tcp://127.0.0.1:5594"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-addr", default=ACTIVITY_ZMQ_ADDR)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(args.in_addr)
    sub.setsockopt(zmq.SUBSCRIBE, b"")

    with open(args.out, "a", encoding="utf-8") as f:
        print(f"logging {args.in_addr} -> {args.out}")
        while True:
            msg = sub.recv_string()
            evt = json.loads(msg)
            evt["logged_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
            f.write(json.dumps(evt) + "\n")
            f.flush()
            print(f"{evt['logged_at_utc']}  {evt['type']:16s} state={evt['state']:10s} "
                  f"score={evt.get('research_score')} quality={evt.get('quality_status')}")


if __name__ == "__main__":
    main()
