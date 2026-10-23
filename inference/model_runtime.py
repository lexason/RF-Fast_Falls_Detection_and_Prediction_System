"""Fail-closed loader for RF Sensing Falls DEVELOPMENT model bundles.

The legacy ONNX exports contain raw class margins in their output named
``probabilities``.  This module owns that compatibility detail and prevents
callers from treating an incomplete or modified bundle as usable.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort

REPO_ROOT = Path(__file__).resolve().parent.parent


class ModelContractError(RuntimeError):
    """Raised when a model bundle is incomplete, inconsistent, or modified."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - np.max(values, axis=-1, keepdims=True)
    exp = np.exp(shifted)
    denominator = np.sum(exp, axis=-1, keepdims=True)
    if not np.all(np.isfinite(exp)) or np.any(denominator <= 0):
        raise ModelContractError("model produced non-finite class scores")
    return exp / denominator


class ProductionModel:
    """Validated, CPU-only runtime for the frozen hierarchical baseline."""

    STAGE1_FILE = "stage1_idle_walk_transient.onnx"
    STAGE2_FILE = "stage2_transient_subclass.onnx"
    RESEARCH_STATUS = {"DEVELOPMENT_POC_ONLY", "OFFLINE_BASELINE"}
    APPROVED_STATUS = {"APPROVED", "ACTIVE"}

    def __init__(self, model_dir: Path | str):
        self.model_dir = Path(model_dir).resolve()
        metadata_path = self.model_dir / "metadata.json"
        try:
            self.metadata: dict[str, Any] = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ModelContractError(f"cannot read model metadata: {metadata_path}: {exc}") from exc

        self._validate_metadata()
        self._verify_artifacts()

        self.feature_names = tuple(self.metadata["feature_names"])
        self.stage1_classes = tuple(self.metadata["stage1_classes"])
        self.stage2_classes = tuple(self.metadata["stage2_classes"])
        self.fall_threshold = float(self.metadata["fall_decision_threshold"])
        self.model_id = str(self.metadata["model_id"])
        self.score_kind = str(self.metadata["score_semantics"])
        self.quality_gate_passed = bool(self.metadata["performance_gate_passed"])

        providers = ["CPUExecutionProvider"]
        session_options = ort.SessionOptions()
        session_options.intra_op_num_threads = 1
        session_options.inter_op_num_threads = 1
        session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.sess1 = ort.InferenceSession(
            str(self.model_dir / self.STAGE1_FILE),
            sess_options=session_options,
            providers=providers,
        )
        self.sess2 = ort.InferenceSession(
            str(self.model_dir / self.STAGE2_FILE),
            sess_options=session_options,
            providers=providers,
        )
        self._stage1_io = self._validate_session(self.sess1, len(self.stage1_classes), "stage1")
        self._stage2_io = self._validate_session(self.sess2, len(self.stage2_classes), "stage2")

    def _validate_metadata(self) -> None:
        required = {
            "schema_version",
            "model_id",
            "deployment_status",
            "promotion_eligible",
            "performance_gate_passed",
            "feature_names",
            "stage1_classes",
            "stage2_classes",
            "fall_decision_threshold",
            "score_semantics",
            "onnx_output_transform",
            "artifact_sha256",
            "dataset",
            "evaluation_artifact",
            "evaluation_artifact_sha256",
        }
        missing = sorted(required - self.metadata.keys())
        if missing:
            raise ModelContractError(f"metadata missing required fields: {', '.join(missing)}")
        if self.metadata["schema_version"] != "1.0":
            raise ModelContractError("unsupported model metadata schema_version")
        deployment_status = self.metadata["deployment_status"]
        promotion_eligible = self.metadata["promotion_eligible"]
        performance_gate_passed = self.metadata["performance_gate_passed"]
        if promotion_eligible is True and performance_gate_passed is True:
            if deployment_status not in self.APPROVED_STATUS:
                raise ModelContractError("promotion-eligible model must have APPROVED or ACTIVE status")
        elif promotion_eligible is False and performance_gate_passed is False:
            if deployment_status not in self.RESEARCH_STATUS:
                raise ModelContractError("promotion-blocked model is not an accepted research baseline")
        else:
            raise ModelContractError("promotion and performance gates must agree")
        if self.metadata["onnx_output_transform"] != "softmax_raw_margins":
            raise ModelContractError("unsupported ONNX output transform")

        feature_names = self.metadata["feature_names"]
        stage1_classes = self.metadata["stage1_classes"]
        stage2_classes = self.metadata["stage2_classes"]
        if not isinstance(feature_names, list) or not feature_names or len(set(feature_names)) != len(feature_names):
            raise ModelContractError("feature_names must be a non-empty unique list")
        if stage1_classes != ["idle", "walk", "transient"]:
            raise ModelContractError("stage1 class contract mismatch")
        if "fall" not in stage2_classes or len(set(stage2_classes)) != len(stage2_classes):
            raise ModelContractError("stage2 class contract mismatch")

        threshold = self.metadata["fall_decision_threshold"]
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise ModelContractError("fall_decision_threshold must be numeric")
        if not math.isfinite(float(threshold)) or not 0.0 <= float(threshold) <= 1.0:
            raise ModelContractError("fall_decision_threshold must be finite and in [0, 1]")

        artifact_hashes = self.metadata["artifact_sha256"]
        if not isinstance(artifact_hashes, dict):
            raise ModelContractError("artifact_sha256 must be an object")
        for filename in (self.STAGE1_FILE, self.STAGE2_FILE):
            value = artifact_hashes.get(filename)
            if not isinstance(value, str) or len(value) != 64:
                raise ModelContractError(f"missing SHA-256 for {filename}")

        evaluation_hash = self.metadata["evaluation_artifact_sha256"]
        if not isinstance(evaluation_hash, str) or len(evaluation_hash) != 64:
            raise ModelContractError("evaluation_artifact_sha256 must be a SHA-256 digest")

    def _verify_artifacts(self) -> None:
        for filename, expected in self.metadata["artifact_sha256"].items():
            path = self.model_dir / filename
            if not path.is_file():
                raise ModelContractError(f"model artifact is missing: {path}")
            observed = sha256_file(path)
            if observed != expected:
                raise ModelContractError(
                    f"model artifact hash mismatch for {filename}: expected {expected}, observed {observed}"
                )
        self._verify_evaluation_policy()

    def _verify_evaluation_policy(self) -> None:
        reference = self.metadata["evaluation_artifact"]
        if not isinstance(reference, str) or not reference or Path(reference).is_absolute():
            raise ModelContractError("evaluation_artifact must be a repository-relative path")
        evaluation_path = (REPO_ROOT / reference).resolve()
        if not evaluation_path.is_relative_to(REPO_ROOT):
            raise ModelContractError("evaluation_artifact escapes the repository")
        if not evaluation_path.is_file():
            raise ModelContractError(f"evaluation artifact is missing: {evaluation_path}")
        observed_hash = sha256_file(evaluation_path)
        if observed_hash != self.metadata["evaluation_artifact_sha256"]:
            raise ModelContractError("evaluation artifact hash mismatch")
        try:
            evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ModelContractError(f"evaluation artifact cannot be read: {exc}") from exc
        evaluation_model_id = evaluation.get("model_id", evaluation.get("candidate_id"))
        if evaluation_model_id != self.metadata["model_id"]:
            raise ModelContractError("evaluation policy model_id mismatch")
        policy = evaluation.get("threshold_policy")
        expected_gate = bool(self.metadata["performance_gate_passed"])
        if not isinstance(policy, dict) or policy.get("performance_gate_passed") is not expected_gate:
            raise ModelContractError("evaluation threshold policy is missing or incorrectly gated")
        policy_threshold = policy.get("threshold")
        if not isinstance(policy_threshold, (int, float)) or isinstance(policy_threshold, bool):
            raise ModelContractError("evaluation threshold policy is not numeric")
        if not math.isclose(float(policy_threshold), float(self.metadata["fall_decision_threshold"]), abs_tol=1e-12):
            raise ModelContractError("fall threshold does not match the bound evaluation policy")
        deprecated = evaluation.get("deprecated_policy", {})
        if deprecated.get("must_not_be_used") is True and math.isclose(
            float(deprecated.get("threshold")), float(self.metadata["fall_decision_threshold"]), abs_tol=1e-12
        ):
            raise ModelContractError("fall threshold is explicitly deprecated by the evaluation policy")

    def _validate_session(self, session: ort.InferenceSession, class_count: int, stage: str) -> tuple[str, str]:
        inputs = session.get_inputs()
        outputs = session.get_outputs()
        if len(inputs) != 1:
            raise ModelContractError(f"{stage} must expose exactly one input")
        input_shape = inputs[0].shape
        if len(input_shape) != 2 or input_shape[1] != len(self.feature_names):
            raise ModelContractError(f"{stage} feature dimension does not match metadata")
        score_outputs = [output for output in outputs if output.name == "probabilities"]
        if len(score_outputs) != 1:
            raise ModelContractError(f"{stage} must expose one probabilities output")
        shape = score_outputs[0].shape
        if len(shape) != 2 or shape[1] != class_count:
            raise ModelContractError(f"{stage} class dimension does not match metadata")
        return inputs[0].name, score_outputs[0].name

    def _feature_array(self, features: dict[str, float]) -> np.ndarray:
        missing = [name for name in self.feature_names if name not in features]
        if missing:
            raise ModelContractError(f"feature vector missing: {', '.join(missing)}")
        values = np.asarray([[features[name] for name in self.feature_names]], dtype=np.float32)
        if not np.all(np.isfinite(values)):
            raise ModelContractError("feature vector contains NaN or infinity")
        return values

    @staticmethod
    def _proba(session: ort.InferenceSession, io_names: tuple[str, str], values: np.ndarray) -> np.ndarray:
        input_name, output_name = io_names
        raw = np.asarray(session.run([output_name], {input_name: values})[0], dtype=np.float64)
        if raw.ndim != 2 or raw.shape[0] != values.shape[0] or not np.all(np.isfinite(raw)):
            raise ModelContractError("model returned an invalid score tensor")
        return _softmax(raw)

    def classify_continuous(self, features: dict[str, float]) -> tuple[str, float]:
        values = self._feature_array(features)
        scores = self._proba(self.sess1, self._stage1_io, values)[0]
        index = int(np.argmax(scores))
        return self.stage1_classes[index], float(scores[index])

    def classify_transient(self, features: dict[str, float]) -> tuple[str, float]:
        values = self._feature_array(features)
        stage1 = self._proba(self.sess1, self._stage1_io, values)[0]
        stage2 = self._proba(self.sess2, self._stage2_io, values)[0]
        transient_score = float(stage1[self.stage1_classes.index("transient")])
        fall_score = transient_score * float(stage2[self.stage2_classes.index("fall")])
        if fall_score >= self.fall_threshold:
            return "fall", fall_score

        other_indices = [index for index, name in enumerate(self.stage2_classes) if name != "fall"]
        other_scores = stage2[other_indices]
        denominator = float(np.sum(other_scores))
        if denominator <= 0 or not math.isfinite(denominator):
            raise ModelContractError("non-fall class scores cannot be normalized")
        best_local = int(np.argmax(other_scores / denominator))
        best_index = other_indices[best_local]
        return self.stage2_classes[best_index], float(other_scores[best_local] / denominator)
