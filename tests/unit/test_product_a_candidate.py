"""Regression evidence for the promotion-blocked Product-A experiment."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from models.product_a_logistic import (
    PHYSICS_FEATURE_NAMES,
    binary_target,
    build_pipeline,
    grouped_oof_scores,
    positive_scores,
    score_exported_model,
    transient_frame,
)

CANDIDATE = ROOT / "models" / "candidates" / "rf-sensing-falls-product-a-physics6-dev-001"
REPRODUCTION = ROOT / "models" / "candidates" / "rf-sensing-falls-product-a-physics6-repro-001"
EVALUATION = (
    ROOT
    / "artifacts"
    / "evaluations"
    / "rf-sensing-falls-product-a-physics6-dev-001-grouped-development-v1.json"
)
ADJUDICATION = ROOT / "artifacts" / "adjudications" / "2026-07-18_fall_gain5-review-v1.json"
DATASET = ROOT / "data" / "processed" / "g3_features_v2_conflict_free.parquet"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_product_a_export_matches_training_pipeline_and_has_no_threshold():
    frame = transient_frame(pd.read_parquet(DATASET))
    truth = binary_target(frame)
    values = frame[PHYSICS_FEATURE_NAMES].to_numpy(dtype=np.float64)
    pipeline = build_pipeline().fit(values, truth)
    artifact = json.loads((CANDIDATE / "product_a_fall_logistic.json").read_text(encoding="utf-8"))
    exported_score = score_exported_model(artifact, frame.iloc[0].to_dict())
    assert exported_score == pytest.approx(positive_scores(pipeline, values[:1])[0], rel=0.0, abs=1e-14)
    assert artifact["fall_decision_threshold"] is None
    assert artifact["score_semantics"] == "uncalibrated_development_score_not_probability"


def test_product_a_grouped_metrics_are_frozen_development_diagnostics():
    truth, scores, folds = grouped_oof_scores(pd.read_parquet(DATASET))
    assert len(truth) == 216
    assert int(truth.sum()) == 30
    assert [fold["held_out_day_or_geometry"] for fold in folds] == [
        "2026-07-25",
        "2026-07-27",
        "2026-07-28",
        "2026-07-29",
        "2026-07-29-floor",
    ]
    from sklearn.metrics import average_precision_score, roc_auc_score

    assert roc_auc_score(truth, scores) == pytest.approx(0.6774193548387097)
    assert average_precision_score(truth, scores) == pytest.approx(0.32730600852302305)
    predicted = scores >= 0.5
    assert int(np.sum(predicted & (truth == 1))) == 18
    assert int(np.sum(~predicted & (truth == 1))) == 12
    assert int(np.sum(predicted & (truth == 0))) == 47
    assert int(np.sum(~predicted & (truth == 0))) == 139


def test_product_a_bundle_is_reproducible_and_evaluation_stays_failed():
    artifact_name = "product_a_fall_logistic.json"
    assert (CANDIDATE / artifact_name).read_bytes() == (REPRODUCTION / artifact_name).read_bytes()
    metadata = json.loads((CANDIDATE / "metadata.json").read_text(encoding="utf-8"))
    evaluation = json.loads(EVALUATION.read_text(encoding="utf-8"))
    assert metadata["artifact_sha256"][artifact_name] == sha256(CANDIDATE / artifact_name)
    assert metadata["promotion_eligible"] is False
    assert metadata["performance_gate_passed"] is False
    assert metadata["fall_decision_threshold"] is None
    assert evaluation["status"] == "FAILED_ACCEPTANCE_CRITERIA"
    assert evaluation["promotion_eligible"] is False
    assert evaluation["performance_gate_passed"] is False
    assert evaluation["fall_decision_threshold"] is None
    assert evaluation["primary_verified_only"]["n_verified_lie_down"] == 0
    assert "not estimable" in evaluation["primary_verified_only"]["scope"]


def test_pilot_clip_is_quarantined_as_one_unresolved_episode():
    adjudication = json.loads(ADJUDICATION.read_text(encoding="utf-8"))
    evaluation = json.loads(EVALUATION.read_text(encoding="utf-8"))
    target = evaluation["quarantined_pilot_error_analysis"]
    assert adjudication["status"] == "PROVISIONAL_QUARANTINED"
    assert adjudication["permitted_use"] == "development_error_analysis_only"
    assert adjudication["documented_episode_count"] == 1
    assert adjudication["source_automatic_fragment_count"] == 2
    assert adjudication["independent_fall_count"] is None
    assert target["documented_episode_count"] == 1
    assert target["independent_fall_count"] is None
    assert target["centered_window_overlap_s"] == pytest.approx(1.45)
    assert [row["direction_sign_diagnostic"] for row in target["fragments"]] == [-1.0, 1.0]
    assert [row["strong_direction_frames"] for row in target["fragments"]] == [7, 3]
