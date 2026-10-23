"""Offline validation for the framework v1.1 Phase 0 foundation."""

from __future__ import annotations

import csv
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from tools.governance_validation import (
    GovernanceValidationError,
    manifest_payload_digest,
    validate_cross_artifact_integrity,
    validate_health_semantics,
    validate_recording_semantics,
    validate_workflow_semantics,
    workflow_arguments_digest,
    workflow_definition_digest,
)


ROOT = Path(__file__).resolve().parents[2]

REQUIRED_FILES = (
    "AGENTS.md",
    "README.md",
    "configs/project.yaml",
    "configs/hardware/n210_ubx40.yaml",
    "configs/control_plane/action_registry.yaml",
    "docs/decisions/0000-project-naming.md",
    "docs/decisions/0001-intended-use.md",
    "docs/evidence/evidence_ledger.md",
    "docs/evidence/literature_matrix.csv",
    "docs/evidence/requirements_traceability_matrix.csv",
    "docs/evidence/external_sources_2026-08-07.md",
    "docs/architecture/system_context.md",
    "docs/architecture/control_plane.md",
    "docs/protocols/n210_bringup.md",
    "docs/clinical/ethics_pathway.md",
    "docs/clinical/alert_response_protocol.md",
    "docs/regulatory/tga_applicability.md",
    "docs/regulatory/rf_compliance_checklist.md",
    "risk/risk_register.csv",
    "risk/hazard_log.csv",
    "risk/privacy_impact_assessment.md",
    "risk/threat_model.md",
    "schemas/recording.schema.json",
    "schemas/workflow.schema.json",
    "schemas/health_snapshot.schema.json",
    "reports/validation/2026-08-07_initial_gate_gap_report.md",
    "docs/evidence/diagnostics/2026-08-07/repository_baseline.md",
    "tools/governance_validation.py",
    ".env.template",
    "Makefile",
)


def load_json(relative_path: str) -> dict[str, Any]:
    """Load a repository JSON document."""

    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def validator(relative_path: str) -> Draft202012Validator:
    """Build a draft-2020-12 validator and assert the schema itself is valid."""

    schema = load_json(relative_path)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def positive_workflow() -> dict[str, Any]:
    """Return a minimal valid, non-shell declarative workflow."""

    return {
        "api_version": "v1",
        "id": "preflight_check",
        "display_name": "Preflight Check",
        "version": 1,
        "safety_class": "operational",
        "required_scopes": ["detection:read"],
        "approval_policy": {
            "mode": "confirmation",
            "reason_required": True,
            "reference_required": False,
            "distinct_approvers": False,
            "approval_ttl_seconds": 900,
        },
        "allowed_environments": ["DEVELOPMENT"],
        "allowed_source_states": ["STOPPED"],
        "locks": ["pipeline:preflight"],
        "timeout_seconds": 60,
        "dry_run_supported": True,
        "idempotency": {
            "scope": "workflow_and_parameters",
            "duplicate_behavior": "return_existing",
        },
        "parameters": {
            "profile": {
                "type": "string",
                "required": True,
                "enum": ["simulation"],
                "max_length": 32,
            }
        },
        "steps": [
            {
                "id": "validate_config",
                "action": "config.validate",
                "arguments": {"profile": {"parameter_ref": "profile"}},
                "depends_on": [],
                "timeout_seconds": 15,
                "retry": {"max_attempts": 1, "backoff_seconds": 0},
                "cancellable": True,
                "on_failure": "fail",
            }
        ],
        "postconditions": [
            {
                "subject": "config.valid",
                "operator": "is_true",
                "expected": True,
            }
        ],
        "rollback": [
            {
                "action": "state.reconcile",
                "arguments": {"target": {"literal": "STOPPED"}},
                "timeout_seconds": 15,
            }
        ],
        "audit": {
            "event_types": [
                "workflow.requested",
                "workflow.step.completed",
                "workflow.completed",
            ],
            "redact_fields": ["secret", "participant_id"],
            "reason_field": "reason",
        },
    }


def positive_rf_workflow() -> dict[str, Any]:
    """Return a non-executable RF workflow whose approval binds exact values."""

    workflow = positive_workflow()
    workflow["safety_class"] = "rf_transmission"
    workflow["required_scopes"] = ["rf:transmit", "detection:read"]
    workflow["locks"] = ["usrp:n210_primary", "pipeline:preflight"]
    workflow["approval_policy"] = {
        "mode": "two_person",
        "reason_required": True,
        "reference_required": True,
        "distinct_approvers": True,
        "approval_ttl_seconds": 900,
    }
    workflow["steps"][0] = {
        "id": "bounded_rf",
        "action": "rf.conducted_bounded_test",
        "arguments": {
            "signed_profile_digest": {"literal": "a" * 64},
            "approval_digest": {"literal": "b" * 64},
            "maximum_duration_seconds": {"literal": 5},
        },
        "depends_on": [],
        "timeout_seconds": 10,
        "retry": {"max_attempts": 1, "backoff_seconds": 0},
        "cancellable": True,
        "on_failure": "rollback",
    }
    workflow["approval_binding"] = {
        "approval_id": "rf_approval_01",
        "approval_digest": "b" * 64,
        "workflow_definition_sha256": workflow_definition_digest(workflow),
        "approved_arguments_sha256": workflow_arguments_digest(workflow),
        "approved_profile_sha256": "a" * 64,
        "signature_file": "approvals/rf_approval_01.sig",
        "approved_at_utc": "2026-08-07T04:00:00Z",
        "expires_at_utc": "2026-08-08T04:00:00Z",
        "approver_ids": ["rf_owner_01", "lab_owner_01"],
    }
    return workflow


def positive_health_snapshot() -> dict[str, Any]:
    """Return a minimal truthful snapshot with unavailable N210 host fields."""

    unavailable = [
        "cpu_utilisation",
        "ram_utilisation",
        "process_list",
        "filesystem_utilisation",
    ]
    checks = []
    for name in unavailable:
        checks.append(
            {
                "check_id": f"usrp.{name}",
                "availability": "unavailable",
                "status": "NOT_APPLICABLE",
                "value": None,
                "unit": None,
                "observed_at_utc": "2026-08-07T04:00:00Z",
                "freshness_seconds": 0,
                "source": {
                    "kind": "CONFIG_STORE",
                    "reference": "n210_capability_matrix_v1",
                    "captured_at_utc": "2026-08-07T04:00:00Z",
                    "disruptive": False,
                },
                "reason": "The N210 is an FPGA radio peripheral, not a Linux host.",
                "evidence_refs": ["docs/architecture/control_plane.md"],
            }
        )
    return {
        "api_version": "v1",
        "snapshot_id": "2f930f2d-8f47-4fa8-8b72-6f3942efaf44",
        "collected_at_utc": "2026-08-07T04:00:00Z",
        "environment": "DEVELOPMENT",
        "collector": {
            "service": "health_collector",
            "version": "0.1.0",
            "host_id": "research_host_01",
        },
        "aggregation_policy": {
            "id": "phase1_policy",
            "version": 1,
            "critical_check_ids": ["usrp.cpu_utilisation"],
        },
        "overall_status": "UNKNOWN",
        "capability_matrix_ref": {
            "id": "n210_capabilities",
            "version": 1,
            "sha256": "a" * 64,
        },
        "n210_capability_matrix": {
            "available_from_stopped_probe": ["device_identity", "firmware_version"],
            "available_from_runtime_instrumentation": ["rx_overflow_count"],
            "derived_from_host_or_samples": ["network_throughput"],
            "unavailable_on_device": unavailable,
        },
        "subjects": [
            {
                "subject_type": "usrp",
                "subject_id": "n210_primary",
                "status": "UNKNOWN",
                "observed_at_utc": "2026-08-07T04:00:00Z",
                "stale_after_seconds": 30,
                "checks": checks,
            }
        ],
    }


def positive_recording() -> dict[str, Any]:
    """Return a receive-only bench recording manifest."""

    recording = {
        "schema_version": "1.0",
        "recording_id": "b1261233-966c-40a3-af95-7300c293ad18",
        "session_id": "21da8db8-f635-43c1-a07f-88531d73ed62",
        "participant_id": None,
        "site_id": "site_01",
        "room_id": "bench_01",
        "started_at_utc": "2026-08-07T04:00:00Z",
        "ended_at_utc": "2026-08-07T04:00:10Z",
        "data_class": "bench",
        "hardware": {
            "platform": "N210",
            "device_inventory_id": "n210_primary",
            "daughterboard": "UBX-40",
            "uhd_version": "4.9.0",
            "firmware_version": "12.4",
            "fpga_version": "11.1",
            "fpga_image_sha256": "b" * 64,
        },
        "rf": {
            "centre_frequency_hz": 2437000000,
            "sample_rate_sps": 1000000,
            "occupied_bandwidth_hz": 1000000,
            "waveform": "receive_only",
            "tx_enabled": False,
            "tx_gain_db": None,
            "rx_gain_db": 5,
            "tx_antenna_inventory_id": None,
            "rx_antenna_inventory_id": "rx_ant_01",
            "tx_port": "DISABLED",
            "rx_port": "RX2",
            "geometry_file": "artifacts/manifests/geometry.json",
            "rf_profile_id": "receive_only_2g4",
            "rf_approval": None,
        },
        "environment": {
            "room_layout_version": "bench_layout_01",
            "wifi_channel_occupancy_file": None,
            "people_count": 0,
            "known_movers": [],
        },
        "protocol": {
            "protocol_id": "receive_baseline",
            "protocol_version": "1",
            "activity_label": "bench",
            "trial_number": 1,
            "scripted": True,
            "safety_supervisor_id": None,
            "safety_protocol_reference": None,
            "label_quality_tier": 3,
            "ethics_reference": None,
            "site_approval_reference": None,
            "consent_or_legal_authority_reference": None,
        },
        "quality": {
            "rx_overflows": 0,
            "tx_underflows": 0,
            "late_commands": 0,
            "sequence_discontinuities": 0,
            "clipped_sample_fraction": 0,
            "packet_or_frame_loss_fraction": 0,
            "mean_snr_db": None,
            "quality_status": "unknown",
        },
        "files": {
            "raw_iq": "data/raw/session/recording.sigmf-data",
            "annotations": "data/labels/session.jsonl",
            "manifest": "data/raw/session/manifest.json",
            "channel_estimates": None,
        },
        "checksums": {
            "raw_iq_sha256": "c" * 64,
            "annotations_sha256": "f" * 64,
            "geometry_file_sha256": "1" * 64,
        },
        "provenance": {
            "repository_commit": "d" * 40,
            "config_sha256": "e" * 64,
            "operator_id": "operator_01",
            "created_at_utc": "2026-08-07T04:00:11Z",
        },
    }
    recording["checksums"]["manifest_payload_sha256"] = manifest_payload_digest(recording)
    return recording


def test_required_foundation_files_exist() -> None:
    """All artifacts mandated by the initial task must be present."""

    missing = [name for name in REQUIRED_FILES if not (ROOT / name).is_file()]
    assert not missing, f"missing Phase 0 files: {missing}"


def test_project_name_remains_unapproved_working_title() -> None:
    """The framework forbids silently approving a legacy name or acronym."""

    config = yaml.safe_load((ROOT / "configs/project.yaml").read_text(encoding="utf-8"))
    project = config["project"]
    assert project["display_name"] == "RF Sensing Falls Project"
    assert project["naming_status"] == "working-title"
    assert project["acronym"] is None
    assert project["acronym_expansion"] is None
    assert project["approved_by"] is None
    assert project["approved_at"] is None


def test_hardware_profile_denies_transmission() -> None:
    """A foundation profile cannot silently enable RF."""

    config = yaml.safe_load(
        (ROOT / "configs/hardware/n210_ubx40.yaml").read_text(encoding="utf-8")
    )
    assert config["profile"]["state"] == "DISABLED"
    assert config["candidate_rf_profile"]["transmission_enabled"] is False
    assert config["approvals"]["rf_transmission"]["approved"] is False
    assert config["approvals"]["conducted_test"]["approved"] is False
    assert config["rf_inventory"]["attenuator_chain"]["status"] == "NOT_VERIFIED"


@pytest.mark.parametrize(
    "relative_path",
    (
        "schemas/recording.schema.json",
        "schemas/workflow.schema.json",
        "schemas/health_snapshot.schema.json",
    ),
)
def test_json_schemas_are_valid(relative_path: str) -> None:
    """Each schema must be valid Draft 2020-12 JSON Schema."""

    validator(relative_path)


def test_workflow_accepts_only_registry_actions() -> None:
    """Workflow syntax and semantics accept only closed registry actions."""

    schema_validator = validator("schemas/workflow.schema.json")
    workflow = positive_workflow()
    schema_validator.validate(workflow)
    validate_workflow_semantics(workflow)

    for unsafe_action in ("bash.exec", "os.exec", "arbitrary.run", "shell.run"):
        workflow["steps"][0]["action"] = unsafe_action
        with pytest.raises(ValidationError):
            schema_validator.validate(workflow)


def test_workflow_rejects_unknown_command_field() -> None:
    """No command field may be smuggled into a declarative step."""

    schema_validator = validator("schemas/workflow.schema.json")
    workflow = positive_workflow()
    workflow["steps"][0]["command"] = "id; uname -a"
    with pytest.raises(ValidationError):
        schema_validator.validate(workflow)


def test_workflow_semantics_reject_graph_and_parameter_bypasses() -> None:
    """Unknown references, missing dependencies, and cycles fail closed."""

    workflow = positive_workflow()
    workflow["steps"][0]["arguments"]["profile"] = {"parameter_ref": "missing"}
    with pytest.raises(GovernanceValidationError):
        validate_workflow_semantics(workflow)

    workflow = positive_workflow()
    workflow["steps"][0]["depends_on"] = ["missing_step"]
    with pytest.raises(GovernanceValidationError):
        validate_workflow_semantics(workflow)

    workflow = positive_workflow()
    second = deepcopy(workflow["steps"][0])
    second["id"] = "validate_again"
    workflow["steps"][0]["depends_on"] = ["validate_again"]
    second["depends_on"] = ["validate_config"]
    workflow["steps"].append(second)
    with pytest.raises(GovernanceValidationError):
        validate_workflow_semantics(workflow)


def test_workflow_semantics_reject_approval_free_rf_and_unsafe_retry() -> None:
    """High-risk actions require bound approval and non-idempotent actions cannot retry."""

    workflow = positive_workflow()
    workflow["safety_class"] = "rf_transmission"
    workflow["required_scopes"] = ["rf:transmit", "detection:read"]
    workflow["locks"] = ["usrp:n210_primary", "pipeline:preflight"]
    workflow["approval_policy"] = {
        "mode": "none",
        "reason_required": False,
        "reference_required": False,
        "distinct_approvers": False,
        "approval_ttl_seconds": 0,
    }
    workflow["steps"][0] = {
        "id": "bounded_rf",
        "action": "rf.conducted_bounded_test",
        "arguments": {
            "signed_profile_digest": {"literal": "a" * 64},
            "approval_digest": {"literal": "b" * 64},
            "maximum_duration_seconds": {"literal": 5},
        },
        "depends_on": [],
        "timeout_seconds": 10,
        "retry": {"max_attempts": 1, "backoff_seconds": 0},
        "cancellable": True,
        "on_failure": "rollback",
    }
    with pytest.raises(GovernanceValidationError):
        validate_workflow_semantics(workflow)

    workflow = positive_workflow()
    workflow["safety_class"] = "maintenance"
    workflow["required_scopes"] = ["model:train", "detection:read"]
    workflow["locks"] = ["model:candidate", "pipeline:preflight"]
    workflow["steps"][0] = {
        "id": "train_candidate",
        "action": "model.train_candidate",
        "arguments": {
            "dataset_manifest": {"literal": "dataset.json"},
            "config_digest": {"literal": "a" * 64},
        },
        "depends_on": [],
        "timeout_seconds": 10,
        "retry": {"max_attempts": 2, "backoff_seconds": 0},
        "cancellable": True,
        "on_failure": "rollback",
    }
    with pytest.raises(GovernanceValidationError):
        validate_workflow_semantics(workflow)


def _with_single_operator_policy(minimum_deliberation_seconds: Any, distinct_approvers: bool) -> dict[str, Any]:
    workflow = positive_rf_workflow()
    workflow["approval_policy"] = {
        "mode": "single_operator",
        "reason_required": True,
        "reference_required": True,
        "distinct_approvers": distinct_approvers,
        "approval_ttl_seconds": 900,
    }
    if minimum_deliberation_seconds is not None:
        workflow["approval_policy"]["minimum_deliberation_seconds"] = minimum_deliberation_seconds
    workflow["approval_binding"]["workflow_definition_sha256"] = workflow_definition_digest(workflow)
    return workflow


def test_workflow_semantics_accept_single_operator_high_risk_approval() -> None:
    """The 2026-09-22 single-operator provision: a correctly-configured high-risk
    workflow using single_operator instead of two_person passes validation."""

    workflow = _with_single_operator_policy(minimum_deliberation_seconds=60, distinct_approvers=False)
    validator("schemas/workflow.schema.json").validate(workflow)
    validate_workflow_semantics(workflow)


def test_workflow_semantics_reject_single_operator_below_deliberation_floor() -> None:
    """single_operator without a real deliberation gap is indistinguishable from no
    approval at all, and must be rejected."""

    too_short = _with_single_operator_policy(minimum_deliberation_seconds=59, distinct_approvers=False)
    with pytest.raises(GovernanceValidationError, match="minimum_deliberation_seconds"):
        validate_workflow_semantics(too_short)

    missing = _with_single_operator_policy(minimum_deliberation_seconds=None, distinct_approvers=False)
    with pytest.raises(GovernanceValidationError, match="minimum_deliberation_seconds"):
        validate_workflow_semantics(missing)


def test_workflow_semantics_reject_single_operator_claiming_distinct_approvers() -> None:
    """single_operator and distinct_approvers: true contradict each other -- a workflow
    cannot claim both that one operator suffices and that approvers are distinct."""

    contradictory = _with_single_operator_policy(minimum_deliberation_seconds=60, distinct_approvers=True)
    with pytest.raises(GovernanceValidationError, match="distinct approvers"):
        validate_workflow_semantics(contradictory)


def test_workflow_semantics_two_person_still_requires_distinct_approvers() -> None:
    """Unrelated action classes (raw-IQ capture, rollback) were not touched by the
    single-operator provision -- two_person workflows still reject distinct_approvers:
    false."""

    workflow = positive_rf_workflow()
    workflow["approval_policy"]["distinct_approvers"] = False
    workflow["approval_binding"]["workflow_definition_sha256"] = workflow_definition_digest(workflow)
    with pytest.raises(GovernanceValidationError, match="distinct approvers"):
        validate_workflow_semantics(workflow)


def test_workflow_rf_arguments_are_typed_bounded_and_digest_bound() -> None:
    """RF digests and duration cannot bypass the per-action registry contract."""

    workflow = positive_rf_workflow()
    validator("schemas/workflow.schema.json").validate(workflow)
    validate_workflow_semantics(workflow)

    negative_duration = deepcopy(workflow)
    negative_duration["steps"][0]["arguments"]["maximum_duration_seconds"] = {"literal": -999}
    negative_duration["approval_binding"]["workflow_definition_sha256"] = workflow_definition_digest(negative_duration)
    negative_duration["approval_binding"]["approved_arguments_sha256"] = workflow_arguments_digest(negative_duration)
    with pytest.raises(GovernanceValidationError, match="below the action minimum"):
        validate_workflow_semantics(negative_duration)

    invalid_digests = deepcopy(workflow)
    invalid_digests["steps"][0]["arguments"]["signed_profile_digest"] = {"literal": "x"}
    invalid_digests["steps"][0]["arguments"]["approval_digest"] = {"literal": "y"}
    invalid_digests["approval_binding"]["approved_profile_sha256"] = "x"
    invalid_digests["approval_binding"]["approval_digest"] = "y"
    invalid_digests["approval_binding"]["workflow_definition_sha256"] = workflow_definition_digest(invalid_digests)
    invalid_digests["approval_binding"]["approved_arguments_sha256"] = workflow_arguments_digest(invalid_digests)
    with pytest.raises(GovernanceValidationError, match="action pattern"):
        validate_workflow_semantics(invalid_digests)

    mismatched_binding = deepcopy(workflow)
    mismatched_binding["approval_binding"]["approved_profile_sha256"] = "c" * 64
    with pytest.raises(GovernanceValidationError, match="signed profile digest"):
        validate_workflow_semantics(mismatched_binding)


def test_workflow_parameter_default_cannot_bypass_action_path_rule() -> None:
    """A referenced default must satisfy the exact registry type and path rule."""

    workflow = positive_workflow()
    workflow["safety_class"] = "maintenance"
    workflow["required_scopes"] = ["model:train", "detection:read"]
    workflow["locks"] = ["model:candidate", "pipeline:preflight"]
    workflow["parameters"]["dataset_manifest"] = {
        "type": "string",
        "required": True,
        "pattern": r"^(?!/)(?!.*\.\./).+\.json$",
        "max_length": 256,
        "default": "datasets/training.json",
    }
    workflow["parameters"]["candidate_id"] = {
        "type": "string",
        "required": True,
        "pattern": r"^[a-z0-9][a-z0-9._-]{2,63}$",
        "max_length": 64,
        "default": "test-candidate",
    }
    workflow["steps"][0] = {
        "id": "train_candidate",
        "action": "model.train_candidate",
        "arguments": {
            "candidate_id": {"parameter_ref": "candidate_id"},
            "dataset_manifest": {"parameter_ref": "dataset_manifest"},
            "config_digest": {"literal": "a" * 64},
        },
        "depends_on": [],
        "timeout_seconds": 10,
        "retry": {"max_attempts": 1, "backoff_seconds": 0},
        "cancellable": True,
        "on_failure": "rollback",
    }
    validator("schemas/workflow.schema.json").validate(workflow)
    validate_workflow_semantics(workflow)

    bypass = deepcopy(workflow)
    bypass["parameters"]["dataset_manifest"]["default"] = "/etc/passwd"
    with pytest.raises(GovernanceValidationError, match="action pattern"):
        validate_workflow_semantics(bypass)


def test_health_snapshot_requires_truthful_n210_unavailable_fields() -> None:
    """N210 CPU/RAM/process/storage fields must remain explicitly unavailable."""

    schema_validator = validator("schemas/health_snapshot.schema.json")
    snapshot = positive_health_snapshot()
    schema_validator.validate(snapshot)

    snapshot["n210_capability_matrix"]["unavailable_on_device"].remove(
        "cpu_utilisation"
    )
    with pytest.raises(ValidationError):
        schema_validator.validate(snapshot)


def test_unavailable_health_measurement_cannot_have_value() -> None:
    """Unavailable telemetry cannot fabricate a value."""

    schema_validator = validator("schemas/health_snapshot.schema.json")
    snapshot = positive_health_snapshot()
    snapshot["subjects"][0]["checks"][0]["value"] = 42
    with pytest.raises(ValidationError):
        schema_validator.validate(snapshot)


def test_health_semantics_reject_contradictory_capability_and_aggregation() -> None:
    """Unavailable capabilities and aggregate status cannot contradict checks."""

    snapshot = positive_health_snapshot()
    validate_health_semantics(snapshot)

    contradiction = deepcopy(snapshot)
    contradiction["subjects"][0]["checks"][0].update(
        availability="available", status="PASS", value=99
    )
    contradiction["subjects"][0]["status"] = "HEALTHY"
    contradiction["overall_status"] = "HEALTHY"
    with pytest.raises(GovernanceValidationError):
        validate_health_semantics(contradiction)

    missing = deepcopy(snapshot)
    missing["aggregation_policy"]["critical_check_ids"] = ["usrp.reachability"]
    with pytest.raises(GovernanceValidationError):
        validate_health_semantics(missing)

    failed = deepcopy(snapshot)
    failed["subjects"][0]["checks"][0]["status"] = "FAIL"
    failed["subjects"][0]["status"] = "FAILED"
    failed["overall_status"] = "HEALTHY"
    with pytest.raises(GovernanceValidationError):
        validate_health_semantics(failed)


def test_health_semantics_reject_stale_critical_healthy_snapshot() -> None:
    """A critical value older than the subject freshness bound cannot be HEALTHY."""

    snapshot = positive_health_snapshot()
    snapshot["collected_at_utc"] = "2026-08-07T04:00:31Z"
    snapshot["aggregation_policy"]["critical_check_ids"] = ["usrp.reachability"]
    first = snapshot["subjects"][0]["checks"][0]
    first.update(
        check_id="usrp.reachability",
        availability="available",
        status="PASS",
        value=True,
        unit=None,
        freshness_seconds=31,
        source={
            "kind": "UHD_RUNTIME",
            "reference": "runtime_instrumentation",
            "captured_at_utc": "2026-08-07T04:00:00Z",
            "disruptive": False,
        },
    )
    for check in snapshot["subjects"][0]["checks"][1:]:
        check["freshness_seconds"] = 31
    snapshot["subjects"][0]["status"] = "HEALTHY"
    snapshot["overall_status"] = "HEALTHY"
    validator("schemas/health_snapshot.schema.json").validate(snapshot)
    with pytest.raises(GovernanceValidationError, match="stale"):
        validate_health_semantics(snapshot)


def test_recording_schema_requires_approval_when_tx_enabled() -> None:
    """A transmitting recording cannot validate without an approval reference."""

    schema_validator = validator("schemas/recording.schema.json")
    recording = positive_recording()
    schema_validator.validate(recording)

    recording["rf"]["tx_enabled"] = True
    recording["rf"]["tx_port"] = "TX/RX"
    recording["rf"]["tx_gain_db"] = 0
    recording["rf"]["tx_antenna_inventory_id"] = "tx_ant_01"
    with pytest.raises(ValidationError):
        schema_validator.validate(recording)


def test_recording_rejects_incoherent_tx_human_and_temporal_manifests() -> None:
    """Adversarial RF, human-data, time, and checksum manifests fail closed."""

    schema_validator = validator("schemas/recording.schema.json")

    incoherent_tx = positive_recording()
    incoherent_tx["rf"]["tx_enabled"] = True
    incoherent_tx["rf"]["rf_approval"] = "bogus"
    with pytest.raises(ValidationError):
        schema_validator.validate(incoherent_tx)

    ungoverned_human = positive_recording()
    ungoverned_human["data_class"] = "prospective_clinical"
    ungoverned_human["protocol"]["activity_label"] = "fall_like"
    with pytest.raises(ValidationError):
        schema_validator.validate(ungoverned_human)

    reversed_time = positive_recording()
    reversed_time["ended_at_utc"] = "2026-08-07T03:59:00Z"
    reversed_time["checksums"]["manifest_payload_sha256"] = manifest_payload_digest(reversed_time)
    with pytest.raises(GovernanceValidationError):
        validate_recording_semantics(reversed_time)

    missing_checksum = positive_recording()
    del missing_checksum["checksums"]["geometry_file_sha256"]
    missing_checksum["checksums"]["manifest_payload_sha256"] = manifest_payload_digest(missing_checksum)
    with pytest.raises(GovernanceValidationError):
        validate_recording_semantics(missing_checksum)


def test_recording_positive_fixture_passes_semantic_validation() -> None:
    """The receive-only bench fixture has coherent times and checksum coverage."""

    recording = positive_recording()
    validator("schemas/recording.schema.json").validate(recording)
    validate_recording_semantics(recording)


def test_hardware_target_cannot_execute_pytest_or_hardware_commands() -> None:
    """Environment strings cannot reach a hardware or TX command through Make."""

    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    match = re.search(
        r"(?ms)^test-hardware:\n(?P<recipe>.*?)(?=^[A-Za-z0-9_-]+:|\Z)", makefile
    )
    assert match is not None
    target = match.group("recipe")
    assert "exit 2" in target
    assert "pytest" not in target
    assert "uhd_" not in target
    assert "RF_FALLS_RF_TX_ENABLED" not in target


def test_cross_artifact_foreign_keys_and_mandatory_fields() -> None:
    """Requirements, risks, hazards, evidence, and literature remain linked."""

    validate_cross_artifact_integrity(ROOT)


def test_agent_handoffs_follow_framework_contract() -> None:
    """Every specialist handoff contains the framework v1.1 top-level contract."""

    required = {
        "handoff_id",
        "agent_id",
        "timestamp_utc",
        "task",
        "inputs",
        "work_performed",
        "findings",
        "risks",
        "evidence",
        "decision",
        "next_actions",
        "reviewers_required",
    }
    paths = sorted((ROOT / "docs/agents/handoffs").glob("*.yaml"))
    assert paths
    for path in paths:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert required <= set(document), f"{path} is missing {sorted(required - set(document))}"
        assert document["decision"]["status"] in {"PASS", "CONDITIONAL", "FAIL", "BLOCKED"}


@pytest.mark.parametrize(
    ("relative_path", "id_column", "expected_columns"),
    (
        (
            "risk/risk_register.csv",
            "risk_id",
            {
                "risk_id",
                "description",
                "accountable_owner",
                "current_residual_rating",
                "projected_post_control_rating",
                "status",
                "last_reviewed",
            },
        ),
        (
            "risk/hazard_log.csv",
            "hazard_id",
            {
                "hazard_id",
                "hazard",
                "harm",
                "control_measure",
                "control_status",
                "current_residual_risk",
                "projected_post_control_risk",
                "status",
            },
        ),
        (
            "docs/evidence/requirements_traceability_matrix.csv",
            "requirement_id",
            {"requirement_id", "requirement", "verification", "evidence", "status"},
        ),
        (
            "docs/evidence/literature_matrix.csv",
            "source_id",
            {"source_id", "evidence_grade", "limitations", "status"},
        ),
    ),
)
def test_governance_csvs_have_unique_ids_and_required_columns(
    relative_path: str, id_column: str, expected_columns: set[str]
) -> None:
    """Governance ledgers must remain machine-readable and uniquely keyed."""

    with (ROOT / relative_path).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert expected_columns.issubset(rows[0])
    assert all(value is not None for row in rows for value in row.values())
    ids = [row[id_column] for row in rows]
    assert len(ids) == len(set(ids))
    assert all(ids)
