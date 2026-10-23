#!/usr/bin/env python3
"""Evaluate a Product-A candidate without calibrating or promoting it.

The grouped metrics are DEVELOPMENT diagnostics.  The pilot 2026-07-18 clip
is used only for error analysis because its two automatically labelled motion
fragments belong to one uncontrolled episode and have not been adjudicated as
two independent falls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from dsp.spectrogram_service import doppler_frequencies  # noqa: E402
from features.micro_doppler import window_features  # noqa: E402
from models.product_a_logistic import (  # noqa: E402
    PHYSICS_FEATURE_NAMES,
    diagnostic_balanced_point,
    discrimination_metrics,
    grouped_oof_scores,
    score_exported_model,
    threshold_metrics,
    transient_frame,
)
from scripts.label_tool import compute_energy_trace, event_direction_signs  # noqa: E402

ARTIFACT_NAME = "product_a_fall_logistic.json"
TARGET_SESSION_ID = "2026-07-18_fall_gain5"


def hash_file(path: Path, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path)


def load_bound_candidate(candidate_dir: Path, candidate_id: str, dataset: Path) -> tuple[dict, dict]:
    try:
        metadata = json.loads((candidate_dir / "metadata.json").read_text(encoding="utf-8"))
        artifact = json.loads((candidate_dir / ARTIFACT_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"candidate bundle cannot be read: {exc}") from exc
    if metadata.get("model_id") != candidate_id:
        raise SystemExit("candidate model_id does not match --candidate-id")
    if metadata.get("promotion_eligible") is not False or metadata.get("performance_gate_passed") is not False:
        raise SystemExit("Product-A DEVELOPMENT candidate must remain promotion-blocked")
    if metadata.get("fall_decision_threshold") is not None or artifact.get("fall_decision_threshold") is not None:
        raise SystemExit("Product-A DEVELOPMENT candidate must not contain a decision threshold")
    expected_artifact = metadata.get("artifact_sha256", {}).get(ARTIFACT_NAME)
    if not expected_artifact or hash_file(candidate_dir / ARTIFACT_NAME) != expected_artifact:
        raise SystemExit("candidate model artifact hash mismatch")
    if metadata.get("dataset", {}).get("sha256") != hash_file(dataset):
        raise SystemExit("candidate training dataset hash mismatch")
    if artifact.get("feature_names") != PHYSICS_FEATURE_NAMES:
        raise SystemExit("candidate feature contract mismatch")
    return metadata, artifact


def target_error_analysis(artifact: dict, adjudication_path: Path) -> dict:
    try:
        adjudication = json.loads(adjudication_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"target adjudication cannot be read: {exc}") from exc
    if adjudication.get("status") != "PROVISIONAL_QUARANTINED":
        raise SystemExit("pilot target must remain quarantined")
    if adjudication.get("permitted_use") != "development_error_analysis_only":
        raise SystemExit("pilot target use is not limited to error analysis")

    session_dir = REPO_ROOT / "data" / "raw" / TARGET_SESSION_ID
    manifest_path = session_dir / "manifest.json"
    label_path = REPO_ROOT / "data" / "labels" / f"{TARGET_SESSION_ID}.jsonl"
    raw_path = session_dir / f"{TARGET_SESSION_ID}.sigmf-data"
    meta_path = session_dir / f"{TARGET_SESSION_ID}.sigmf-meta"
    bound = adjudication.get("source_hashes", {})
    observed = {
        "manifest_sha256": hash_file(manifest_path),
        "labels_sha256": hash_file(label_path),
        "sigmf_meta_sha256": hash_file(meta_path),
        "sigmf_data_sha256": hash_file(raw_path),
        "sigmf_data_sha512": hash_file(raw_path, "sha512"),
    }
    if observed != bound:
        raise SystemExit("pilot target hash does not match quarantine sidecar")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    with label_path.open(encoding="utf-8") as handle:
        labels = [json.loads(line) for line in handle if line.strip()]
    if labels != manifest.get("scripted_activity_timeline"):
        raise SystemExit("pilot manifest and label file disagree")
    fs = float(manifest["sample_rate_hz"])
    f0_hz = float(manifest["carrier_hz"])
    iq = np.fromfile(raw_path, dtype=np.complex64)
    times, _energy, frames, _lo, _hi, _nperseg = compute_energy_trace(iq, fs)
    freqs = doppler_frequencies(fs, expected_bins=frames.shape[1])
    directions = event_direction_signs(times, frames, freqs, labels, strong_db=28.0)

    fragments = []
    for index, (label, direction) in enumerate(zip(labels, directions), start=1):
        event_t0 = float(label["t_start"])
        event_t1 = float(label["t_end"])
        center = (event_t0 + event_t1) / 2.0
        mask = (times >= center - 1.5) & (times < center + 1.5)
        features = window_features(
            frames[mask],
            freqs,
            f0_hz,
            frame_times=times[mask].copy(),
            event_t0=event_t0,
            event_t1=event_t1,
        )
        score = score_exported_model(artifact, features)
        fragments.append(
            {
                "fragment": index,
                "source_automatic_label": label["label"],
                "t_start": event_t0,
                "t_end": event_t1,
                "development_score": score,
                "fixed_0_5_diagnostic_only": bool(score >= 0.5),
                "direction_sign_diagnostic": direction[0],
                "strong_direction_frames": direction[1],
                "features": {name: float(features[name]) for name in PHYSICS_FEATURE_NAMES},
            }
        )
    first, second = labels
    first_window_end = (float(first["t_start"]) + float(first["t_end"])) / 2.0 + 1.5
    second_window_start = (float(second["t_start"]) + float(second["t_end"])) / 2.0 - 1.5
    return {
        "session_id": TARGET_SESSION_ID,
        "adjudication": relative(adjudication_path),
        "adjudication_sha256": hash_file(adjudication_path),
        "permitted_use": "development_error_analysis_only",
        "independent_fall_count": None,
        "source_automatic_fragment_count": len(labels),
        "documented_episode_count": 1,
        "centered_window_overlap_s": first_window_end - second_window_start,
        "fragments": fragments,
        "interpretation": (
            "The two source labels are unresolved motion phases in one uncontrolled pilot episode; "
            "their scores must not select a model, threshold, calibration point, or performance claim."
        ),
        "source_hashes": observed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--candidate-dir", type=Path)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=REPO_ROOT / "data" / "processed" / "g3_features_v2_conflict_free.parquet",
    )
    parser.add_argument(
        "--adjudication",
        type=Path,
        default=REPO_ROOT / "artifacts" / "adjudications" / f"{TARGET_SESSION_ID}-review-v1.json",
    )
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    dataset = args.dataset.resolve()
    candidate_dir = (args.candidate_dir or REPO_ROOT / "models" / "candidates" / args.candidate_id).resolve()
    adjudication = args.adjudication.resolve()
    metadata, artifact = load_bound_candidate(candidate_dir, args.candidate_id, dataset)
    frame = pd.read_parquet(dataset)

    secondary = transient_frame(frame)
    secondary_truth, secondary_scores, secondary_folds = grouped_oof_scores(frame)
    secondary_metrics = discrimination_metrics(secondary_truth, secondary_scores)
    secondary_fixed = threshold_metrics(secondary_truth, secondary_scores, 0.5)
    secondary_diagnostic = diagnostic_balanced_point(secondary_truth, secondary_scores)

    primary_frame = frame[
        frame["label"].isin({"fall", "sit_down", "stand_up"}) & (frame["label_confidence"] == "verified")
    ].copy()
    primary_truth, primary_scores, primary_folds = grouped_oof_scores(primary_frame, require_all_labels=False)
    primary_metrics = discrimination_metrics(primary_truth, primary_scores)
    primary_fixed = threshold_metrics(primary_truth, primary_scores, 0.5)
    primary_diagnostic = diagnostic_balanced_point(primary_truth, primary_scores)

    target = target_error_analysis(artifact, adjudication)
    report = {
        "schema_version": "1.0",
        "evaluation_id": f"{args.candidate_id}-grouped-development-v1",
        "candidate_id": args.candidate_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "FAILED_ACCEPTANCE_CRITERIA",
        "promotion_eligible": False,
        "performance_gate_passed": False,
        "fall_decision_threshold": None,
        "candidate_bundle": {
            "path": relative(candidate_dir),
            "metadata_sha256": hash_file(candidate_dir / "metadata.json"),
            "artifact_sha256": metadata["artifact_sha256"],
        },
        "dataset": {
            "path": relative(dataset),
            "sha256": hash_file(dataset),
            "split": "grouped leave-one-day-or-geometry-out; not participant/site/room independent",
        },
        "evaluator": {
            "path": relative(Path(__file__).resolve()),
            "sha256": hash_file(Path(__file__).resolve()),
            "numpy_version": np.__version__,
            "pandas_version": pd.__version__,
            "scikit_learn_version": sklearn.__version__,
        },
        "primary_verified_only": {
            "scope": "fall vs verified sit_down/stand_up; fall-vs-lie_down is not estimable",
            "n": len(primary_frame),
            "n_falls": int(primary_truth.sum()),
            "n_sit_down": int((primary_frame["label"] == "sit_down").sum()),
            "n_stand_up": int((primary_frame["label"] == "stand_up").sum()),
            "n_verified_lie_down": 0,
            **primary_metrics,
            "fixed_0_5_diagnostic": primary_fixed,
            "balanced_development_point_descriptive_only": primary_diagnostic,
            "folds": primary_folds,
        },
        "secondary_legacy_label_sensitivity": {
            "scope": "fall vs sit_down/stand_up/unverified lie_down; not a primary validation claim",
            "n": len(secondary),
            "n_falls": int(secondary_truth.sum()),
            "n_hard_negatives": int((secondary_truth == 0).sum()),
            "n_unverified_lie_down": int(
                ((secondary["label"] == "lie_down") & (secondary["label_confidence"] != "verified")).sum()
            ),
            **secondary_metrics,
            "fixed_0_5_diagnostic": secondary_fixed,
            "balanced_development_point_descriptive_only": secondary_diagnostic,
            "folds": secondary_folds,
        },
        "quarantined_pilot_error_analysis": target,
        "threshold_policy": None,
        "failure_reasons": [
            "no participant, room, site, calibration, or final-test independence",
            "single apparent researcher and one laboratory",
            "no verified lie_down examples; fall-vs-lie_down performance is not estimable",
            "candidate scores are uncalibrated and no deployment threshold is approved",
            "the inspected pilot clip is quarantined error-analysis evidence, not test data",
        ],
    }
    output = (
        args.out.resolve()
        if args.out
        else REPO_ROOT / "artifacts" / "evaluations" / f"{args.candidate_id}-grouped-development-v1.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise SystemExit(f"refused: evaluation artifact already exists: {output}")
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output),
                "status": report["status"],
                "primary_auroc": primary_metrics["auroc"],
                "secondary_auroc": secondary_metrics["auroc"],
                "fall_decision_threshold": None,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
