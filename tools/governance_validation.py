"""Semantic validators for safety-critical Phase 0 governance artifacts.

JSON Schema supplies bounded syntax. These validators enforce relationships
that Draft 2020-12 cannot express safely: registry membership, graph validity,
approval class, timestamp ordering, checksum coverage, truthful aggregation,
and cross-ledger foreign keys. Nothing in this module executes a workflow or
accesses hardware.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import yaml


ROOT = Path(__file__).resolve().parents[1]
HIGH_RISK_CLASSES = {"rf_transmission", "clinical", "destructive"}
APPROVAL_RANK = {"none": 0, "confirmation": 1, "single_operator": 2, "two_person": 3}
# Floor for single_operator's enforced request-to-approval wait. This is what makes
# single_operator mode a real second look rather than one motion: below this floor
# there is no meaningful gap between requesting and approving the same action.
MINIMUM_SINGLE_OPERATOR_DELIBERATION_SECONDS = 60
REQUIRED_AUDIT_EVENTS = {
    "workflow.requested",
    "workflow.step.completed",
    "workflow.completed",
}
N210_UNAVAILABLE = {
    "cpu_utilisation",
    "ram_utilisation",
    "process_list",
    "filesystem_utilisation",
}


class GovernanceValidationError(ValueError):
    """Raised when one or more semantic governance invariants are violated."""


def _raise(errors: Iterable[str]) -> None:
    material = sorted(set(errors))
    if material:
        raise GovernanceValidationError("; ".join(material))


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise GovernanceValidationError(f"timestamp lacks timezone: {value}")
    return parsed


def workflow_definition_digest(workflow: dict[str, Any]) -> str:
    """Hash the canonical definition while excluding its external approval binding."""

    canonical = deepcopy(workflow)
    canonical.pop("approval_binding", None)
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def workflow_arguments_digest(workflow: dict[str, Any]) -> str:
    """Hash the exact structured forward and rollback action arguments."""

    payload = {
        "steps": [
            {"action": step["action"], "arguments": step["arguments"]}
            for step in workflow["steps"]
        ],
        "rollback": [
            {"action": step["action"], "arguments": step["arguments"]}
            for step in workflow.get("rollback", [])
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _value_errors(value: Any, rule: dict[str, Any], location: str) -> list[str]:
    errors: list[str] = []
    expected_type = rule["type"]
    type_matches = {
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
    }[expected_type]
    if not type_matches:
        return [f"{location}: value is not {expected_type}"]
    if "enum" in rule and value not in rule["enum"]:
        errors.append(f"{location}: value is outside the action enum")
    if isinstance(value, str):
        if len(value) < rule.get("min_length", 0):
            errors.append(f"{location}: string is shorter than the action minimum")
        if len(value) > rule.get("max_length", 2**31):
            errors.append(f"{location}: string exceeds the action maximum")
        if "pattern" in rule and re.fullmatch(rule["pattern"], value) is None:
            errors.append(f"{location}: string does not match the action pattern")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < rule.get("minimum", float("-inf")):
            errors.append(f"{location}: number is below the action minimum")
        if value > rule.get("maximum", float("inf")):
            errors.append(f"{location}: number exceeds the action maximum")
    return errors


def _parameter_rule_errors(
    definition: dict[str, Any], rule: dict[str, Any], location: str
) -> list[str]:
    errors: list[str] = []
    if definition["type"] != rule["type"]:
        errors.append(f"{location}: parameter type is broader than the action rule")
    if "enum" in rule:
        if "enum" not in definition or not set(definition["enum"]) <= set(rule["enum"]):
            errors.append(f"{location}: parameter enum is absent or broader than the action enum")
    if "minimum" in rule and definition.get("minimum", float("-inf")) < rule["minimum"]:
        errors.append(f"{location}: parameter minimum is broader than the action minimum")
    if "maximum" in rule and definition.get("maximum", float("inf")) > rule["maximum"]:
        errors.append(f"{location}: parameter maximum is broader than the action maximum")
    if "min_length" in rule and definition.get("min_length", 0) < rule["min_length"]:
        errors.append(f"{location}: parameter minimum length is broader than the action rule")
    if "max_length" in rule and definition.get("max_length", float("inf")) > rule["max_length"]:
        errors.append(f"{location}: parameter length is broader than the action maximum")
    if "pattern" in rule and definition.get("pattern") != rule["pattern"]:
        errors.append(f"{location}: parameter pattern does not equal the action pattern")
    if "default" in definition:
        errors.extend(_value_errors(definition["default"], rule, f"{location}.default"))
    return errors


def _action_errors(
    action: dict[str, Any],
    workflow: dict[str, Any],
    registry: dict[str, Any],
    location: str,
    retry_attempts: int = 1,
) -> list[str]:
    errors: list[str] = []
    action_id = action["action"]
    registered = registry.get(action_id)
    if registered is None:
        return [f"{location}: action is not in the versioned registry: {action_id}"]

    arguments = set(action.get("arguments", {}))
    allowed_arguments = set(registered["allowed_arguments"])
    required_arguments = set(registered["required_arguments"])
    if not arguments <= allowed_arguments:
        errors.append(f"{location}: arguments are not allowlisted: {sorted(arguments - allowed_arguments)}")
    if not required_arguments <= arguments:
        errors.append(f"{location}: required arguments are absent: {sorted(required_arguments - arguments)}")

    if workflow["safety_class"] not in registered["allowed_safety_classes"]:
        errors.append(f"{location}: safety class is not allowed for {action_id}")
    if not set(registered["required_scopes"]) <= set(workflow["required_scopes"]):
        errors.append(f"{location}: required action scopes are absent")
    if not set(registered["required_locks"]) <= set(workflow["locks"]):
        errors.append(f"{location}: required action locks are absent")
    if APPROVAL_RANK[workflow["approval_policy"]["mode"]] < APPROVAL_RANK[registered["minimum_approval"]]:
        errors.append(f"{location}: approval mode is weaker than the action registry")
    if retry_attempts > 1 and not registered["idempotent"]:
        errors.append(f"{location}: a non-idempotent action cannot be retried")

    parameters = set(workflow["parameters"])
    for argument_name, argument in action.get("arguments", {}).items():
        rule = registered["argument_rules"].get(argument_name)
        if rule is None:
            continue
        reference = argument.get("parameter_ref")
        argument_location = f"{location}.{argument_name}"
        if reference is not None:
            if reference not in parameters:
                errors.append(f"{argument_location}: unknown parameter_ref {reference}")
            elif rule.get("literal_only"):
                errors.append(f"{argument_location}: safety-bound value must be literal")
            else:
                errors.extend(
                    _parameter_rule_errors(
                        workflow["parameters"][reference], rule, argument_location
                    )
                )
        elif "literal" in argument:
            errors.extend(_value_errors(argument["literal"], rule, argument_location))
        else:
            errors.append(f"{argument_location}: context_ref is not allowed for this action")
    return errors


def validate_workflow_semantics(
    workflow: dict[str, Any], registry_path: Path | None = None
) -> None:
    """Validate a schema-valid workflow against the closed action registry."""

    registry_document = yaml.safe_load(
        (registry_path or ROOT / "configs/control_plane/action_registry.yaml").read_text(encoding="utf-8")
    )
    if registry_document["execution_enabled"] is not False:
        raise GovernanceValidationError("the Phase 0 action registry must remain non-executable")
    registry = registry_document["actions"]
    errors: list[str] = []

    step_ids = [step["id"] for step in workflow["steps"]]
    if len(step_ids) != len(set(step_ids)):
        errors.append("workflow step identifiers must be unique")
    known_steps = set(step_ids)
    graph: dict[str, set[str]] = {}
    for index, step in enumerate(workflow["steps"]):
        location = f"steps[{index}]"
        dependencies = set(step["depends_on"])
        missing = dependencies - known_steps
        if missing:
            errors.append(f"{location}: unknown dependencies: {sorted(missing)}")
        if step["id"] in dependencies:
            errors.append(f"{location}: step depends on itself")
        graph[step["id"]] = dependencies
        errors.extend(
            _action_errors(
                step,
                workflow,
                registry,
                location,
                retry_attempts=step["retry"]["max_attempts"],
            )
        )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            errors.append("workflow dependency graph contains a cycle")
            return
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph.get(node, set()):
            if dependency in graph:
                visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for step_id in graph:
        visit(step_id)

    for index, step in enumerate(workflow.get("rollback", [])):
        errors.extend(_action_errors(step, workflow, registry, f"rollback[{index}]"))

    approval = workflow["approval_policy"]
    if workflow["safety_class"] in HIGH_RISK_CLASSES:
        mode = approval["mode"]
        if mode not in {"two_person", "single_operator"}:
            errors.append("high-risk workflow requires two-person or single-operator-deliberate approval")
        if not all([approval["reason_required"], approval["reference_required"]]):
            errors.append("high-risk workflow requires reason and reference")
        if mode == "two_person" and not approval["distinct_approvers"]:
            errors.append("two-person high-risk workflow requires distinct approvers")
        if mode == "single_operator":
            # single_operator is a project-level substitution for a second human approver
            # (RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK_v1_4.md, single-operator approval
            # provision): the same operator may request and approve, but only across an
            # enforced deliberation gap, never as the same motion, and never claiming a
            # second identity it does not have.
            if approval["distinct_approvers"]:
                errors.append("single-operator approval must not also claim distinct approvers")
            if approval.get("minimum_deliberation_seconds", 0) < MINIMUM_SINGLE_OPERATOR_DELIBERATION_SECONDS:
                errors.append(
                    "single-operator approval requires minimum_deliberation_seconds >= "
                    f"{MINIMUM_SINGLE_OPERATOR_DELIBERATION_SECONDS}"
                )
        if approval["approval_ttl_seconds"] <= 0:
            errors.append("high-risk workflow approval must expire")
        if not workflow.get("rollback"):
            errors.append("high-risk workflow requires an allowlisted rollback")
        binding = workflow.get("approval_binding")
        if not isinstance(binding, dict):
            errors.append("high-risk workflow lacks a digest-bound approval")
        elif binding.get("binding_mode") == "runtime":
            required_runtime_bindings = {
                "workflow_digest_bound",
                "parameters_bound",
                "environment_bound",
                "reason_and_reference_bound",
                "approver_sessions_bound",
            }
            if not all(binding.get(field) is True for field in required_runtime_bindings):
                errors.append("runtime approval binding is incomplete")
        else:
            if binding["workflow_definition_sha256"] != workflow_definition_digest(workflow):
                errors.append("approval is not bound to the canonical workflow definition")
            if binding["approved_arguments_sha256"] != workflow_arguments_digest(workflow):
                errors.append("approval is not bound to the exact structured arguments")
            approved_at = _utc(binding["approved_at_utc"])
            expires_at = _utc(binding["expires_at_utc"])
            if approved_at >= expires_at:
                errors.append("approval expiry must follow approval time")
            if len(set(binding["approver_ids"])) < 2:
                errors.append("high-risk approval requires two distinct identities")

            rf_steps = [step for step in workflow["steps"] if step["action"] == "rf.conducted_bounded_test"]
            for step in rf_steps:
                profile_digest = step["arguments"]["signed_profile_digest"].get("literal")
                approval_digest = step["arguments"]["approval_digest"].get("literal")
                if binding.get("approved_profile_sha256") != profile_digest:
                    errors.append("RF approval is not bound to the signed profile digest")
                if binding["approval_digest"] != approval_digest:
                    errors.append("RF action approval_digest does not match the signed binding")

    audit_events = set(workflow["audit"]["event_types"])
    if not REQUIRED_AUDIT_EVENTS <= audit_events:
        errors.append("workflow audit contract omits required lifecycle events")
    _raise(errors)


def manifest_payload_digest(recording: dict[str, Any]) -> str:
    canonical = deepcopy(recording)
    canonical["checksums"].pop("manifest_payload_sha256", None)
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_recording_semantics(recording: dict[str, Any]) -> None:
    """Validate temporal, RF, human-governance, and checksum relationships."""

    errors: list[str] = []
    started = _utc(recording["started_at_utc"])
    ended = _utc(recording["ended_at_utc"])
    created = _utc(recording["provenance"]["created_at_utc"])
    if not started < ended:
        errors.append("recording ended_at_utc must be later than started_at_utc")
    if created < ended:
        errors.append("manifest creation cannot precede recording completion")

    rf = recording["rf"]
    if rf["tx_enabled"]:
        if rf["waveform"] == "receive_only" or rf["tx_port"] == "DISABLED":
            errors.append("transmitting recording has incoherent waveform or port")
        approval = rf.get("rf_approval")
        if not isinstance(approval, dict):
            errors.append("transmitting recording lacks a structured RF approval")
        else:
            approved = _utc(approval["approved_at_utc"])
            expires = _utc(approval["expires_at_utc"])
            if approved > started:
                errors.append("RF approval was issued after recording started")
            if expires < ended:
                errors.append("RF approval expired before recording ended")
            if approved >= expires:
                errors.append("RF approval expiry must follow approval time")
    else:
        expected = {
            "waveform": "receive_only",
            "tx_gain_db": None,
            "tx_antenna_inventory_id": None,
            "tx_port": "DISABLED",
            "rf_approval": None,
        }
        for name, value in expected.items():
            if rf.get(name) != value:
                errors.append(f"receive-only recording has incoherent {name}")

    human_classes = {
        "healthy_adult_controlled",
        "older_adult_functional",
        "silent_observational",
        "prospective_clinical",
    }
    protocol = recording["protocol"]
    if recording["data_class"] in human_classes:
        for field in (
            "participant_id",
            "ethics_reference",
            "site_approval_reference",
            "consent_or_legal_authority_reference",
        ):
            value = recording.get(field) if field == "participant_id" else protocol.get(field)
            if not value:
                errors.append(f"human-data recording lacks {field}")
    if protocol["activity_label"] in {"near_fall", "fall_like"}:
        if not protocol.get("safety_supervisor_id"):
            errors.append("fall-like protocol lacks a safety supervisor")
        if not protocol.get("safety_protocol_reference"):
            errors.append("fall-like protocol lacks an approved safety protocol")

    checksums = recording["checksums"]
    references: dict[str, Any] = {
        "raw_iq_sha256": recording["files"].get("raw_iq"),
        "annotations_sha256": recording["files"].get("annotations"),
        "channel_estimates_sha256": recording["files"].get("channel_estimates"),
        "geometry_file_sha256": rf.get("geometry_file"),
        "wifi_channel_occupancy_file_sha256": recording["environment"].get("wifi_channel_occupancy_file"),
    }
    if isinstance(rf.get("rf_approval"), dict):
        references["rf_approval_signature_file_sha256"] = rf["rf_approval"]["signature_file"]
    for checksum_name, path in references.items():
        if path is not None and checksum_name not in checksums:
            errors.append(f"referenced artifact lacks {checksum_name}")
    expected_manifest_digest = manifest_payload_digest(recording)
    if checksums.get("manifest_payload_sha256") != expected_manifest_digest:
        errors.append("manifest_payload_sha256 does not match canonical self-excluded payload")
    _raise(errors)


def validate_health_semantics(snapshot: dict[str, Any]) -> None:
    """Validate capability truth, time ordering, and health aggregation."""

    errors: list[str] = []
    collected = _utc(snapshot["collected_at_utc"])
    capabilities = snapshot["n210_capability_matrix"]
    capability_sets = [set(capabilities[name]) for name in capabilities]
    for left_index, left in enumerate(capability_sets):
        for right in capability_sets[left_index + 1 :]:
            if left & right:
                errors.append("N210 capability categories must be disjoint")

    check_ids: list[str] = []
    subject_ids: list[str] = []
    expected_subject_statuses: list[str] = []
    critical_stale = False
    critical_ids = set(snapshot["aggregation_policy"]["critical_check_ids"])
    for subject in snapshot["subjects"]:
        subject_ids.append(subject["subject_id"])
        subject_observed = _utc(subject["observed_at_utc"])
        if subject_observed > collected:
            errors.append(f"subject {subject['subject_id']} was observed after snapshot collection")
        subject_age = (collected - subject_observed).total_seconds()
        subject_stale = subject_age > subject["stale_after_seconds"]
        if subject_stale and subject["status"] == "HEALTHY":
            errors.append(f"stale subject {subject['subject_id']} cannot be HEALTHY")
        check_statuses: list[str] = []
        for check in subject["checks"]:
            check_ids.append(check["check_id"])
            check_statuses.append(check["status"])
            observed = _utc(check["observed_at_utc"])
            captured = _utc(check["source"]["captured_at_utc"])
            if observed > collected:
                errors.append(f"check {check['check_id']} was observed after snapshot collection")
            if captured > observed:
                errors.append(f"check {check['check_id']} source was captured after its observation")
            observed_age = (collected - observed).total_seconds()
            if observed_age >= 0 and abs(check["freshness_seconds"] - observed_age) > 1:
                errors.append(f"check {check['check_id']} freshness_seconds contradicts its timestamp")
            if check["check_id"] in critical_ids and (
                observed_age > subject["stale_after_seconds"] or subject_stale
            ):
                critical_stale = True
            capability_name = check["check_id"].split(".")[-1]
            if subject["subject_type"] == "usrp" and capability_name in N210_UNAVAILABLE:
                if check["availability"] != "unavailable" or check["value"] is not None:
                    errors.append(f"N210 device field {capability_name} must be unavailable")
            if check["availability"] == "derived" and check["source"]["kind"] != "DERIVATION":
                errors.append(f"derived check {check['check_id']} must use a DERIVATION source")
        if "FAIL" in check_statuses:
            expected = "FAILED"
        elif "WARN" in check_statuses:
            expected = "DEGRADED"
        elif "UNKNOWN" in check_statuses or all(status == "NOT_APPLICABLE" for status in check_statuses):
            expected = "UNKNOWN"
        else:
            expected = "HEALTHY"
        expected_subject_statuses.append(expected)
        if subject["status"] != expected:
            errors.append(f"subject {subject['subject_id']} status contradicts its checks")

    if len(subject_ids) != len(set(subject_ids)):
        errors.append("subject identifiers must be unique")
    if len(check_ids) != len(set(check_ids)):
        errors.append("check identifiers must be unique within a snapshot")
    critical = critical_ids
    missing_critical = critical - set(check_ids)
    if missing_critical:
        errors.append(f"critical checks are absent: {sorted(missing_critical)}")

    if "FAILED" in expected_subject_statuses:
        expected_overall = "FAILED"
    elif "DEGRADED" in expected_subject_statuses:
        expected_overall = "DEGRADED"
    elif "UNKNOWN" in expected_subject_statuses:
        expected_overall = "UNKNOWN"
    else:
        expected_overall = "HEALTHY"
    if snapshot["overall_status"] != expected_overall:
        errors.append("overall_status contradicts subject aggregation")
    if snapshot["overall_status"] == "HEALTHY":
        status_by_id = {
            check["check_id"]: check["status"]
            for subject in snapshot["subjects"]
            for check in subject["checks"]
        }
        if any(status_by_id.get(check_id) != "PASS" for check_id in critical):
            errors.append("HEALTHY requires every critical check to PASS")
        if critical_stale:
            errors.append("HEALTHY is prohibited when a critical check or subject is stale")
    _raise(errors)


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _split_links(value: str) -> set[str]:
    return {part.strip() for part in value.replace(",", ";").split(";") if part.strip()}


def validate_cross_artifact_integrity(root: Path = ROOT) -> None:
    """Validate IDs, status values, mandatory fields, and foreign keys."""

    errors: list[str] = []
    rtm = _csv_rows(root / "docs/evidence/requirements_traceability_matrix.csv")
    risks = _csv_rows(root / "risk/risk_register.csv")
    hazards = _csv_rows(root / "risk/hazard_log.csv")
    literature = _csv_rows(root / "docs/evidence/literature_matrix.csv")
    requirement_ids = {row["requirement_id"] for row in rtm}
    risk_ids = {row["risk_id"] for row in risks}
    hazard_ids = {row["hazard_id"] for row in hazards}

    required_fields = {
        "RTM": (rtm, {"requirement_id", "requirement", "source", "implementation", "verification", "validation", "evidence", "status", "owner", "reviewer"}),
        "risk": (risks, {"risk_id", "description", "source", "initial_rating", "further_controls", "accountable_owner", "due_date", "verification_method", "current_residual_rating", "status", "last_reviewed", "residual_risk_approved_by"}),
        "hazard": (hazards, {"hazard_id", "hazard", "harm", "control_measure", "control_status", "requirement_id", "verification_method", "current_residual_risk", "accountable_owner", "due_date", "status"}),
        "literature": (literature, {"source_id", "citation", "source_type", "evidence_grade", "limitations", "requirement_links", "status"}),
    }
    for label, (rows, fields) in required_fields.items():
        for row_index, row in enumerate(rows, start=2):
            for field in fields:
                if field not in row or not row[field].strip():
                    errors.append(f"{label} row {row_index}: mandatory field {field} is blank")

    for row in rtm:
        unknown_risks = _split_links(row["risk_control"]) - risk_ids
        unknown_hazards = _split_links(row["hazard_ids"]) - hazard_ids
        if unknown_risks:
            errors.append(f"{row['requirement_id']}: unknown risks {sorted(unknown_risks)}")
        if unknown_hazards:
            errors.append(f"{row['requirement_id']}: unknown hazards {sorted(unknown_hazards)}")
    for row in hazards:
        if row["requirement_id"] not in requirement_ids:
            errors.append(f"{row['hazard_id']}: unknown requirement {row['requirement_id']}")
    for row in literature:
        unknown = _split_links(row["requirement_links"]) - requirement_ids
        if unknown:
            errors.append(f"{row['source_id']}: unknown requirements {sorted(unknown)}")

    ledger_text = (root / "docs/evidence/evidence_ledger.md").read_text(encoding="utf-8")
    for line in ledger_text.splitlines():
        if line.startswith("| EV-"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            unknown = _split_links(cells[-1]) - requirement_ids
            if unknown:
                errors.append(f"{cells[0]}: unknown requirements {sorted(unknown)}")

    allowed_statuses = {
        "RTM": {"planned", "partial", "implemented", "verified", "blocked"},
        "risk": {"open", "mitigating", "closed", "accepted"},
        "hazard": {"open", "controlled", "closed", "accepted"},
        "literature": {"date_checked", "needs_full_extraction", "superseded"},
    }
    for label, (rows, _) in required_fields.items():
        for row in rows:
            if row["status"] not in allowed_statuses[label]:
                errors.append(f"{label}: invalid status {row['status']}")
    _raise(errors)


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline CARAT governance semantic validation")
    parser.add_argument("command", choices=["cross-artifacts"])
    args = parser.parse_args()
    if args.command == "cross-artifacts":
        validate_cross_artifact_integrity()
    print("semantic governance validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
