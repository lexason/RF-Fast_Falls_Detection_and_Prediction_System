#!/usr/bin/env python3
"""Create immutable, non-deployable threshold evidence from an evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--candidate-metadata", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit(f"refused: threshold-study artifact already exists: {args.out}")
    evaluation = json.loads(args.evaluation.read_text(encoding="utf-8"))
    if evaluation.get("candidate_id", evaluation.get("model_id")) != args.candidate_id:
        raise SystemExit("evaluation identity does not match --candidate-id")
    expected_metadata = evaluation.get("candidate_bundle", {}).get("metadata_sha256")
    observed_metadata = sha256_file(args.candidate_metadata)
    if expected_metadata and expected_metadata != observed_metadata:
        raise SystemExit("evaluation is not bound to the current candidate metadata")
    sweep = evaluation.get("fall_transient_subset", {}).get("threshold_sweep")
    if not isinstance(sweep, list) or not sweep:
        raise SystemExit("evaluation has no threshold sweep")
    feasible = [
        row for row in sweep
        if isinstance(row.get("recall"), (int, float))
        and isinstance(row.get("specificity"), (int, float))
        and row["recall"] >= 0.90
        and row["specificity"] >= 0.90
    ]
    balanced = max(
        sweep,
        key=lambda row: min(float(row.get("recall", 0.0)), float(row.get("specificity", 0.0))),
    )
    report = {
        "schema_version": "1.0",
        "artifact_type": "DEVELOPMENT_THRESHOLD_STUDY",
        "candidate_id": args.candidate_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_evaluation": str(args.evaluation),
        "source_evaluation_sha256": sha256_file(args.evaluation),
        "candidate_metadata_sha256": observed_metadata,
        "balanced_development_point": balanced,
        "target_recall_and_specificity": 0.90,
        "target_feasible": bool(feasible),
        "feasible_points": feasible,
        "promotion_eligible": False,
        "performance_gate_passed": False,
        "active_model_changed": False,
        "limitations": [
            "This is a diagnostic threshold study, not independent calibration.",
            "A deployment threshold requires participant, room, site, and final-test independence.",
            "The candidate bundle and active model pointer were not modified.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.out), "target_feasible": bool(feasible)}))


if __name__ == "__main__":
    main()
