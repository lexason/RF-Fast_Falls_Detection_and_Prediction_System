#!/usr/bin/env python3
"""Disabled legacy entry point.

Direct training into the active model directory previously restored a known
invalid 0.0004 fall threshold.  Candidate training is now isolated and never
updates the frozen baseline bundle.
"""

raise SystemExit(
    "REFUSED: direct production training is disabled. "
    "Use `python models/train_candidate.py --candidate-id <id>`; evaluate and review the candidate separately."
)
