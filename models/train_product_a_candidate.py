#!/usr/bin/env python3
"""Build an immutable, threshold-free Product-A DEVELOPMENT candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from models.product_a_logistic import (  # noqa: E402
    PHYSICS_FEATURE_NAMES,
    binary_target,
    build_pipeline,
    export_pipeline,
    transient_frame,
)

CANDIDATE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
ARTIFACT_NAME = "product_a_fall_logistic.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=REPO_ROOT / "data" / "processed" / "g3_features_v2_conflict_free.parquet",
    )
    args = parser.parse_args()
    if not CANDIDATE_ID.fullmatch(args.candidate_id):
        raise SystemExit("candidate-id must be 3-64 lowercase safe characters")
    dataset = args.dataset.resolve()
    if not dataset.is_file():
        raise SystemExit(f"dataset does not exist: {dataset}")
    candidates_root = (REPO_ROOT / "models" / "candidates").resolve()
    final_dir = candidates_root / args.candidate_id
    temporary_dir = candidates_root / f".{args.candidate_id}.partial-{os.getpid()}"
    if final_dir.exists() or temporary_dir.exists():
        raise SystemExit("candidate output already exists; immutable bundles cannot be overwritten")

    frame = pd.read_parquet(dataset)
    required = set(PHYSICS_FEATURE_NAMES) | {"label", "session_id", "day", "label_confidence"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise SystemExit(f"dataset missing required columns: {', '.join(missing)}")
    selected = transient_frame(frame)
    truth = binary_target(selected)
    model = build_pipeline()
    model.fit(selected[PHYSICS_FEATURE_NAMES].to_numpy(dtype=np.float64), truth)

    candidates_root.mkdir(parents=True, exist_ok=True)
    temporary_dir.mkdir()
    artifact_path = temporary_dir / ARTIFACT_NAME
    artifact_path.write_text(json.dumps(export_pipeline(model), indent=2) + "\n", encoding="utf-8")
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True, capture_output=True, text=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    source_files = [
        Path(__file__).resolve(),
        REPO_ROOT / "models" / "product_a_logistic.py",
        REPO_ROOT / "features" / "micro_doppler.py",
        REPO_ROOT / "models" / "build_dataset.py",
    ]
    metadata = {
        "schema_version": "1.0",
        "model_id": args.candidate_id,
        "product": "A_probable_fall_event_research",
        "deployment_status": "CANDIDATE_UNEVALUATED",
        "promotion_eligible": False,
        "performance_gate_passed": False,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": commit,
        "source_worktree_dirty": True,
        "source_file_sha256": {str(path.relative_to(REPO_ROOT)): sha256_file(path) for path in source_files},
        "dataset": {
            "path": str(dataset.relative_to(REPO_ROOT)) if dataset.is_relative_to(REPO_ROOT) else str(dataset),
            "sha256": sha256_file(dataset),
            "usage": "legacy_development_only_secondary_label_sensitivity",
            "n_transient_windows": len(selected),
            "n_falls": int(truth.sum()),
            "n_hard_negatives": int((truth == 0).sum()),
            "groups": sorted(map(str, selected["day"].unique())),
            "unverified_lie_down_windows": int(
                ((selected["label"] == "lie_down") & (selected["label_confidence"] != "verified")).sum()
            ),
        },
        "feature_names": PHYSICS_FEATURE_NAMES,
        "negative_classes": ["sit_down", "stand_up", "lie_down"],
        "positive_class": "fall",
        "score_semantics": "uncalibrated_development_score_not_probability",
        "fall_decision_threshold": None,
        "evaluation_artifact": None,
        "artifact_sha256": {ARTIFACT_NAME: sha256_file(artifact_path)},
        "training": {
            "algorithm": "standard_scaler_plus_balanced_l2_logistic_regression",
            "C": 1.0,
            "solver": "liblinear",
            "max_iter": 2000,
            "seed": 0,
            "scikit_learn_version": sklearn.__version__,
            "numpy_version": np.__version__,
            "pandas_version": pd.__version__,
        },
        "limitations": [
            "single apparent researcher and one laboratory",
            "no independent calibration or final test set",
            "all retained lie_down labels are unverified legacy annotations",
            "candidate has no approved threshold and must not be served or promoted",
        ],
    }
    (temporary_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary_dir, final_dir)
    print(json.dumps({"candidate": str(final_dir), "status": "CANDIDATE_UNEVALUATED"}, sort_keys=True))


if __name__ == "__main__":
    main()
