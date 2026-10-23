#!/usr/bin/env python3
"""Train an immutable, unevaluated DEVELOPMENT candidate bundle.

This command never writes ``models/production`` and never invents or copies a
fall threshold.  Evaluation/calibration and promotion are separate workflows.
"""

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
import onnxmltools
import pandas as pd
import xgboost as xgb
from onnxmltools import convert_xgboost
from onnxmltools.convert.common.data_types import FloatTensorType

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "features"))
from micro_doppler import FEATURE_NAMES  # noqa: E402

TRANSIENT_CLASSES = ["sit_down", "stand_up", "lie_down", "fall"]
STAGE1_CLASSES = ["idle", "walk", "transient"]
CANDIDATE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def train_stage(data: pd.DataFrame, classes: list[str], labels: pd.Series) -> xgb.XGBClassifier:
    class_index = {name: index for index, name in enumerate(classes)}
    encoded = np.asarray([class_index[value] for value in labels])
    counts = labels.value_counts()
    weights = {name: len(labels) / (len(classes) * count) for name, count in counts.items()}
    sample_weights = np.asarray([weights[value] for value in labels])
    classifier = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.1,
        objective="multi:softmax",
        num_class=len(classes),
        eval_metric="mlogloss",
        random_state=0,
        n_jobs=1,
    )
    classifier.fit(data[FEATURE_NAMES].values, encoded, sample_weight=sample_weights)
    return classifier


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
    candidates_root.mkdir(parents=True, exist_ok=True)
    temporary_dir.mkdir()

    frame = pd.read_parquet(dataset)
    required_columns = set(FEATURE_NAMES) | {"label", "session_id", "day", "label_confidence"}
    missing = sorted(required_columns - set(frame.columns))
    if missing:
        raise SystemExit(f"dataset missing required columns: {', '.join(missing)}")
    values = frame[FEATURE_NAMES].to_numpy(dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise SystemExit("dataset feature matrix contains NaN or infinity")
    if not set(frame["label"]).issubset({"idle", "walk", *TRANSIENT_CLASSES}):
        raise SystemExit("dataset contains unsupported labels")

    stage1_labels = frame["label"].map(lambda value: value if value in {"idle", "walk"} else "transient")
    stage1 = train_stage(frame, STAGE1_CLASSES, stage1_labels)
    transient = frame[frame["label"].isin(TRANSIENT_CLASSES)].copy()
    stage2 = train_stage(transient, TRANSIENT_CLASSES, transient["label"])

    initial_type = [("input", FloatTensorType([None, len(FEATURE_NAMES)]))]
    paths = {
        "stage1_idle_walk_transient.onnx": convert_xgboost(stage1, initial_types=initial_type),
        "stage2_transient_subclass.onnx": convert_xgboost(stage2, initial_types=initial_type),
    }
    for filename, model in paths.items():
        # onnxmltools otherwise generates a random UUID graph name, making
        # byte-identical rebuilds impossible even when every tree is identical.
        model.graph.name = Path(filename).stem
        (temporary_dir / filename).write_bytes(model.SerializeToString())

    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    try:
        worktree_dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=normal"],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError):
        worktree_dirty = None
    source_files = [
        Path(__file__).resolve(),
        REPO_ROOT / "features" / "micro_doppler.py",
        REPO_ROOT / "models" / "build_dataset.py",
    ]
    metadata = {
        "schema_version": "1.0",
        "model_id": args.candidate_id,
        "deployment_status": "CANDIDATE_UNEVALUATED",
        "promotion_eligible": False,
        "performance_gate_passed": False,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": commit,
        "source_worktree_dirty": worktree_dirty,
        "source_file_sha256": {
            str(path.relative_to(REPO_ROOT)): sha256_file(path) for path in source_files
        },
        "dataset": {
            "path": str(dataset.relative_to(REPO_ROOT)) if dataset.is_relative_to(REPO_ROOT) else str(dataset),
            "sha256": sha256_file(dataset),
            "usage": "legacy_development_only",
            "n_windows": len(frame),
            "n_sessions": int(frame["session_id"].nunique()),
            "groups": sorted(map(str, frame["day"].unique())),
        },
        "feature_names": FEATURE_NAMES,
        "stage1_classes": STAGE1_CLASSES,
        "stage2_classes": TRANSIENT_CLASSES,
        "fall_decision_threshold": None,
        "evaluation_artifact": None,
        "score_semantics": "uncalibrated_model_score_not_probability",
        "onnx_output_transform": "softmax_raw_margins",
        "artifact_sha256": {filename: sha256_file(temporary_dir / filename) for filename in paths},
        "training": {
            "algorithm": "xgboost_hierarchical_legacy_baseline",
            "seed": 0,
            "xgboost_version": xgb.__version__,
            "onnxmltools_version": onnxmltools.__version__,
            "numpy_version": np.__version__,
            "pandas_version": pd.__version__,
        },
        "limitations": [
            "single apparent researcher and single laboratory",
            "no independent calibration or final test set",
            "legacy label provenance remains; selected windows passed the zero cross-label-overlap check",
            "candidate must not be served before separate grouped evaluation and calibration",
        ],
    }
    (temporary_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary_dir, final_dir)
    print(json.dumps({"candidate": str(final_dir), "status": "CANDIDATE_UNEVALUATED"}, sort_keys=True))


if __name__ == "__main__":
    main()
