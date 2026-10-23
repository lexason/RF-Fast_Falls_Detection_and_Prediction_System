#!/usr/bin/env python3
"""Finalize an evaluated, failing candidate into a loadable OFFLINE_BASELINE
bundle -- the same non-passing category models/production (v3) already
occupies.

This script can NEVER produce a bundle that claims to pass G3's acceptance
criteria: deployment_status, promotion_eligible, and performance_gate_passed
are hardcoded below, not accepted as arguments. Its only job is to attach an
honest, evaluation-derived operating threshold to a candidate that has
already been run through models/evaluate_development.py and confirmed
FAILED_ACCEPTANCE_CRITERIA, producing inference/model_runtime.py's exact
required schema (see models/production/metadata.json and
artifacts/evaluations/rf-sensing-falls-v3-oof-transient-2026-08-07.json for
the precedent this mirrors). It never touches models/production or any
existing candidate/evaluation artifact.

Usage:
    python models/finalize_offline_baseline.py \\
        --candidate-id rf-sensing-falls-v8-velocity-normalized-dev-001 \\
        --source-evaluation artifacts/evaluations/rf-sensing-falls-v8-velocity-normalized-dev-001-grouped-development-v1.json \\
        --threshold 0.5 \\
        --out-id rf-sensing-falls-v8-velocity-normalized-baseline-001
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CANDIDATE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
ARTIFACT_FILES = ("stage1_idle_walk_transient.onnx", "stage2_transient_subclass.onnx")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidate-id", required=True, help="An already-trained candidate in models/candidates/")
    parser.add_argument("--source-evaluation", required=True, type=Path,
                         help="That candidate's models/evaluate_development.py output JSON")
    parser.add_argument("--threshold", required=True, type=float,
                         help="Fall-decision threshold to bind; must exactly match a row in the "
                              "evaluation's fall_transient_subset.threshold_sweep")
    parser.add_argument("--out-id", required=True, help="Model ID for the new OFFLINE_BASELINE bundle")
    args = parser.parse_args()

    if not CANDIDATE_ID.fullmatch(args.out_id):
        raise SystemExit("out-id must be 3-64 lowercase safe characters")
    if not 0.0 <= args.threshold <= 1.0:
        raise SystemExit("threshold must be in [0, 1]")

    candidate_dir = (REPO_ROOT / "models" / "candidates" / args.candidate_id).resolve()
    candidate_metadata_path = candidate_dir / "metadata.json"
    try:
        candidate_metadata = json.loads(candidate_metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"cannot read candidate metadata: {exc}") from exc
    if candidate_metadata.get("model_id") != args.candidate_id:
        raise SystemExit("candidate metadata model_id does not match --candidate-id")
    if candidate_metadata.get("promotion_eligible") is not False:
        raise SystemExit("refusing: source candidate is not promotion-blocked")

    source_evaluation_path = args.source_evaluation.resolve()
    try:
        source_evaluation = json.loads(source_evaluation_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"cannot read source evaluation: {exc}") from exc
    if source_evaluation.get("candidate_id") != args.candidate_id:
        raise SystemExit("source evaluation candidate_id does not match --candidate-id")
    if source_evaluation.get("status") != "FAILED_ACCEPTANCE_CRITERIA":
        raise SystemExit("refusing: source evaluation does not report FAILED_ACCEPTANCE_CRITERIA")
    if source_evaluation.get("promotion_eligible") is not False:
        raise SystemExit("refusing: source evaluation does not confirm promotion_eligible=false")
    bundle_ref = source_evaluation.get("candidate_bundle", {})
    if bundle_ref.get("metadata_sha256") != sha256_file(candidate_metadata_path):
        raise SystemExit("source evaluation does not match the current candidate metadata (hash mismatch)")
    for filename in ARTIFACT_FILES:
        expected = bundle_ref.get("artifact_sha256", {}).get(filename)
        observed = sha256_file(candidate_dir / filename)
        if expected != observed or candidate_metadata.get("artifact_sha256", {}).get(filename) != observed:
            raise SystemExit(f"candidate artifact hash mismatch: {filename}")

    subset = source_evaluation.get("fall_transient_subset", {})
    sweep = subset.get("threshold_sweep", [])
    matches = [row for row in sweep if math_isclose(row.get("threshold"), args.threshold)]
    if len(matches) != 1:
        raise SystemExit(
            f"--threshold {args.threshold} is not an exact row in the evaluation's threshold_sweep; "
            f"pick one of: {sorted({row.get('threshold') for row in sweep})}"
        )
    row = matches[0]

    candidates_root = (REPO_ROOT / "models" / "candidates").resolve()
    out_dir = candidates_root / args.out_id
    if out_dir.exists():
        raise SystemExit("out-id already exists; immutable bundles cannot be overwritten")

    evaluations_root = (REPO_ROOT / "artifacts" / "evaluations").resolve()
    date_tag = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_evaluation_path = evaluations_root / f"{args.out_id}-oof-transient-{date_tag}.json"
    if out_evaluation_path.exists():
        raise SystemExit("evaluation artifact output path already exists")

    out_evaluation = {
        "schema_version": "1.0",
        "evaluation_id": f"{args.out_id}-oof-transient-{date_tag}",
        "model_id": args.out_id,
        "environment": "DEVELOPMENT",
        "status": "FAILED_ACCEPTANCE_CRITERIA",
        "population": "pooled leave-one-day-or-geometry-out transient windows "
                       f"(derived from {source_evaluation_path.relative_to(REPO_ROOT)})",
        "population_limitations": [
            "single apparent researcher",
            "single laboratory",
            "no independent participant, room, site, calibration, or final test set",
            "correlated and repeatedly reused development folds",
        ],
        "n_transient_windows": subset.get("n"),
        "n_fall_windows": subset.get("n_falls"),
        "fall_prevalence": (subset.get("n_falls") / subset.get("n")) if subset.get("n") else None,
        "score_semantics": "uncalibrated_model_score_not_probability",
        "discrimination": {
            "auroc": subset.get("auroc"),
            "auprc": subset.get("auprc"),
            "brier": subset.get("brier"),
            "ece_10_bins": subset.get("ece_10_bins"),
        },
        "threshold_policy": {
            "threshold": args.threshold,
            "selection_status": "legacy_conservative_development_setting_not_independently_calibrated",
            "recall": row.get("recall"),
            "specificity": row.get("specificity"),
            "positive_predictive_value": row.get("ppv"),
            "confusion": {"tp": row.get("tp"), "fn": row.get("fn"), "fp": row.get("fp"), "tn": row.get("tn")},
            "performance_gate_passed": False,
        },
        "intended_use": "offline replay, engineering regression, and silent research demonstration only",
        "prohibited_claims": [
            "validated fall detector",
            "calibrated probability",
            "clinical alerting",
            "unseen-participant generalisation",
        ],
        "derived_from": {
            "candidate_id": args.candidate_id,
            "source_evaluation": str(source_evaluation_path.relative_to(REPO_ROOT)),
            "source_evaluation_sha256": sha256_file(source_evaluation_path),
        },
    }
    evaluations_root.mkdir(parents=True, exist_ok=True)
    out_evaluation_path.write_text(json.dumps(out_evaluation, indent=2) + "\n", encoding="utf-8")
    out_evaluation_sha256 = sha256_file(out_evaluation_path)

    temporary_dir = candidates_root / f".{args.out_id}.partial-{__import__('os').getpid()}"
    temporary_dir.mkdir(parents=True)
    for filename in ARTIFACT_FILES:
        shutil.copyfile(candidate_dir / filename, temporary_dir / filename)

    out_metadata = dict(candidate_metadata)
    out_metadata["model_id"] = args.out_id
    out_metadata["deployment_status"] = "OFFLINE_BASELINE"
    out_metadata["promotion_eligible"] = False
    out_metadata["performance_gate_passed"] = False
    out_metadata["fall_decision_threshold"] = args.threshold
    out_metadata["evaluation_artifact"] = str(out_evaluation_path.relative_to(REPO_ROOT))
    out_metadata["evaluation_artifact_sha256"] = out_evaluation_sha256
    out_metadata["created_at_utc"] = datetime.now(timezone.utc).isoformat()
    out_metadata["derived_from_candidate_id"] = args.candidate_id
    out_metadata.setdefault("limitations", [])
    if "candidate must not be served before separate grouped evaluation and calibration" in out_metadata["limitations"]:
        out_metadata["limitations"] = [
            item for item in out_metadata["limitations"]
            if item != "candidate must not be served before separate grouped evaluation and calibration"
        ]
    out_metadata["limitations"].append(
        "threshold is a fixed legacy-conservative operating point chosen from an honest pooled LOSO sweep, "
        "not an independent calibration; fall recall remains far below the 0.90 G3 acceptance target"
    )
    (temporary_dir / "metadata.json").write_text(json.dumps(out_metadata, indent=2) + "\n", encoding="utf-8")

    import os
    os.replace(temporary_dir, out_dir)
    print(json.dumps({"bundle": str(out_dir), "evaluation": str(out_evaluation_path),
                       "status": "OFFLINE_BASELINE", "promotion_eligible": False,
                       "performance_gate_passed": False}, sort_keys=True))


def math_isclose(a, b, tol=1e-9) -> bool:
    if a is None:
        return False
    return abs(float(a) - float(b)) <= tol


if __name__ == "__main__":
    main()
