"""Deterministic G1A DEVELOPMENT control-plane tests.

These tests use an isolated SQLite database and the simulation adapter.  They
must never access the USRP, start a subprocess, write model artefacts, or read
raw IQ.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest
import jsonschema

from dashboard.control_plane import ControlPlane, WorkflowApprovalRequest, WorkflowRunRequest
from dashboard.operations_gateway import GatewayError, OperationsGateway


ROOT = Path(__file__).resolve().parents[2]


def production_metadata_digest() -> str:
    return hashlib.sha256((ROOT / "models" / "production" / "metadata.json").read_bytes()).hexdigest()


@pytest.fixture()
def control_plane(tmp_path: Path) -> ControlPlane:
    return ControlPlane(ROOT, tmp_path / "control-plane.sqlite3", auth_secret="test-bootstrap-secret")


def actor(service: ControlPlane, actor_id: str):
    session = service.login(actor_id, "test-bootstrap-secret")
    return service.authenticate(session["access_token"])


def request(
    workflow_id: str,
    *,
    parameters: dict | None = None,
    dry_run: bool = False,
    reason: str | None = "Development simulation workflow test",
    reference: str | None = None,
) -> WorkflowRunRequest:
    return WorkflowRunRequest(
        parameters=parameters or {},
        dry_run=dry_run,
        confirmed=True,
        idempotency_key=f"test-{workflow_id}-12345678",
        reason=reason,
        reference=reference,
    )


def file_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_versioned_workflows_are_schema_and_semantically_valid(control_plane: ControlPlane) -> None:
    assert set(control_plane.workflows) == {
        "preflight",
        "start_detection",
        "stop_detection_gracefully",
        "emergency_stop",
        "comprehensive_health_check",
        "enter_maintenance",
        "leave_maintenance",
        "train_candidate_model",
        "recalibrate_candidate",
        "rollback_model",
        "capture_raw_iq",
        "evaluate_candidate",
        "promote_model",
        "start_live_sdr",
        "rerun_live_sdr",
    }
    assert all(len(item["_digest"]) == 64 for item in control_plane.workflows.values())


def test_authentication_has_no_insecure_fallback(tmp_path: Path) -> None:
    service = ControlPlane(ROOT, tmp_path / "no-auth.sqlite3", auth_secret=None)
    with pytest.raises(PermissionError, match="not configured"):
        service.login("dev_admin", "anything")


def test_login_uses_ephemeral_token_and_revoke(control_plane: ControlPlane) -> None:
    session = control_plane.login("dev_viewer", "test-bootstrap-secret")
    authenticated = control_plane.authenticate(session["access_token"])
    assert authenticated.role == "viewer"
    control_plane.revoke(session["access_token"], authenticated)
    with pytest.raises(PermissionError, match="invalid session"):
        control_plane.authenticate(session["access_token"])


def test_viewer_cannot_start_detection(control_plane: ControlPlane) -> None:
    viewer = actor(control_plane, "dev_viewer")
    with pytest.raises(PermissionError, match="missing scopes"):
        control_plane.start_workflow(
            "start_detection",
            request("viewer-start", parameters={"profile": "simulation"}),
            viewer,
        )
    assert control_plane.get_meta("platform_state") == "STOPPED"


def test_dry_run_previews_exact_actions_without_changing_state(control_plane: ControlPlane) -> None:
    operator = actor(control_plane, "dev_operator")
    run = control_plane.start_workflow(
        "start_detection",
        request("dry-start", parameters={"profile": "simulation"}, dry_run=True),
        operator,
    )
    assert run["status"] == "DRY_RUN_COMPLETED"
    assert run["result"]["preview"]["will_execute_shell"] is False
    assert run["result"]["preview"]["will_access_usrp"] is False
    assert control_plane.get_meta("platform_state") == "STOPPED"


def test_repeated_start_is_idempotent_after_state_changes(control_plane: ControlPlane) -> None:
    operator = actor(control_plane, "dev_operator")
    body = request("start_detection", parameters={"profile": "simulation"})
    first = control_plane.start_workflow("start_detection", body, operator)
    second = control_plane.start_workflow("start_detection", body, operator)
    assert first["status"] == "COMPLETED"
    assert second["run_id"] == first["run_id"]
    assert control_plane.get_meta("platform_state") == "RUNNING"
    assert len(control_plane.list_runs()) == 1


def test_graceful_stop_is_idempotent_and_returns_stopped(control_plane: ControlPlane) -> None:
    operator = actor(control_plane, "dev_operator")
    control_plane.start_workflow(
        "start_detection",
        request("start-before-stop", parameters={"profile": "simulation"}),
        operator,
    )
    body = request(
        "stop_detection_gracefully",
        parameters={"reason": "End deterministic simulation test"},
    )
    first = control_plane.start_workflow("stop_detection_gracefully", body, operator)
    second = control_plane.start_workflow("stop_detection_gracefully", body, operator)
    assert first["status"] == "COMPLETED"
    assert second["run_id"] == first["run_id"]
    assert control_plane.get_meta("platform_state") == "STOPPED"


def test_emergency_stop_is_available_from_stopped(control_plane: ControlPlane) -> None:
    operator = actor(control_plane, "dev_operator")
    run = control_plane.start_workflow(
        "emergency_stop",
        request("emergency", parameters={"reason": "Emergency simulation verification"}),
        operator,
    )
    assert run["status"] == "COMPLETED"
    assert control_plane.get_meta("platform_state") == "FAILED"
    assert all(
        state in {"STOPPED", "HEALTHY"}
        for state in control_plane.get_meta("simulation_services").values()
    )


def test_emergency_stop_preempts_pipeline_lock(control_plane: ControlPlane) -> None:
    operator = actor(control_plane, "dev_operator")
    prior = control_plane.start_workflow(
        "preflight",
        request("preflight-for-emergency-preemption", parameters={"profile": "simulation"}),
        operator,
    )
    with control_plane._connect() as db:
        db.execute("UPDATE workflow_runs SET status = 'RUNNING' WHERE run_id = ?", (prior["run_id"],))
        db.execute(
            "INSERT INTO resource_locks(resource_id, run_id, acquired_at_utc) VALUES (?, ?, ?)",
            ("pipeline:detection", prior["run_id"], prior["created_at_utc"]),
        )
    run = control_plane.start_workflow(
        "emergency_stop",
        request("preempt-emergency", parameters={"reason": "Emergency must preempt any ordinary pipeline lock"}),
        operator,
    )
    assert run["status"] == "COMPLETED"
    assert control_plane.get_run(prior["run_id"])["status"] == "CANCELLED"
    assert any(item["type"] == "workflow.preempted" for item in control_plane.list_audit())


def test_declared_retry_and_postconditions_are_enforced(control_plane: ControlPlane) -> None:
    operator = actor(control_plane, "dev_operator")
    original = control_plane._execute_action
    attempts = 0

    def fail_once(action_id, arguments, run_id, current_actor):
        nonlocal attempts
        if action_id == "pipeline.emergency_stop":
            attempts += 1
            if attempts == 1:
                raise RuntimeError("transient stop adapter failure")
        return original(action_id, arguments, run_id, current_actor)

    with patch.object(control_plane, "_execute_action", side_effect=fail_once):
        run = control_plane.start_workflow(
            "emergency_stop",
            request("retry-emergency", parameters={"reason": "Exercise declared emergency retry semantics"}),
            operator,
        )
    assert run["status"] == "COMPLETED"
    assert attempts == 2
    assert run["result"]["postconditions"]["platform.state"] == "FAILED"
    assert any(item["type"] == "workflow.step.attempt_failed" for item in control_plane.list_audit())


def test_failed_postcondition_cannot_report_success(control_plane: ControlPlane) -> None:
    operator = actor(control_plane, "dev_operator")
    with patch.object(control_plane, "_apply_workflow_outcome", return_value=None):
        run = control_plane.start_workflow(
            "start_detection",
            request("postcondition-failure", parameters={"profile": "simulation"}),
            operator,
        )
    assert run["status"] == "ROLLED_BACK"
    assert "postcondition failed" in run["error"]


def test_lock_conflict_is_audited_and_run_fails(control_plane: ControlPlane) -> None:
    operator = actor(control_plane, "dev_operator")
    with patch.object(control_plane, "_acquire_locks", side_effect=RuntimeError("workflow resource lock conflict: pipeline:detection")):
        run = control_plane.start_workflow(
            "start_detection",
            request("lock-conflict", parameters={"profile": "simulation"}),
            operator,
        )
    assert run["status"] == "FAILED"
    assert "lock conflict" in run["error"]
    assert any(item["type"] == "workflow.lock.denied" for item in control_plane.list_audit())


def test_failed_start_executes_typed_rollback(control_plane: ControlPlane) -> None:
    operator = actor(control_plane, "dev_operator")
    original = control_plane._execute_action

    def fail_start(action_id, arguments, run_id, current_actor):
        if action_id == "pipeline.start":
            raise RuntimeError("simulated start failure")
        return original(action_id, arguments, run_id, current_actor)

    with patch.object(control_plane, "_execute_action", side_effect=fail_start):
        run = control_plane.start_workflow(
            "start_detection",
            request("rollback", parameters={"profile": "simulation"}),
            operator,
        )
    assert run["status"] == "ROLLED_BACK"
    assert run["result"]["rollback"][0]["action"] == "pipeline.stop"
    assert all(
        state in {"STOPPED", "HEALTHY"}
        for state in control_plane.get_meta("simulation_services").values()
    )


def test_two_person_approval_requires_distinct_non_requesters(control_plane: ControlPlane) -> None:
    """2026-09-22c: every real workflow in this repository is now single_operator --
    RF transmission, model promotion, model rollback, and (after the researcher
    confirmed every capture to date has been solo, operator and subject both) raw-IQ
    capture too. two_person mode's own code path (self-approval blocked, two distinct
    non-requester approvals required) is unchanged and still load-bearing -- it is
    what two_person_approval provision reverts to if a second project member ever
    holds an approval-capable role -- so it is exercised here directly against an
    in-memory clone of a real workflow rather than left with zero runtime coverage
    just because no shipped config currently selects it."""

    admin = actor(control_plane, "dev_admin")
    operator = actor(control_plane, "dev_operator")
    auditor = actor(control_plane, "dev_auditor")
    synthetic_two_person = deepcopy(control_plane.workflows["rollback_model"])
    synthetic_two_person["approval_policy"] = {
        "mode": "two_person",
        "reason_required": True,
        "reference_required": True,
        "distinct_approvers": True,
        "approval_ttl_seconds": 3600,
    }
    # No teardown needed: the `control_plane` fixture is function-scoped, so this
    # in-memory override never leaks into another test.
    control_plane.workflows["rollback_model"] = synthetic_two_person
    run = control_plane.start_workflow(
        "rollback_model",
        request(
            "rollback-two-person-regression",
            parameters={
                "approved_model_digest": production_metadata_digest(),
                "expected_active_digest": production_metadata_digest(),
                "reason": "Exercise the two_person code path directly, not just single_operator",
            },
            reference="TEST-TWO-PERSON-001",
        ),
        admin,
    )
    assert run["status"] == "AWAITING_APPROVAL"
    assert run["approval_mode"] == "two_person"
    with pytest.raises(PermissionError, match="own"):
        control_plane.approve_run(
            run["run_id"],
            WorkflowApprovalRequest(decision="approve", reason="Requester self approval must fail"),
            admin,
        )
    after_one = control_plane.approve_run(
        run["run_id"],
        WorkflowApprovalRequest(decision="approve", reason="Operator independently approves"),
        operator,
    )
    assert after_one["status"] == "AWAITING_APPROVAL"
    complete = control_plane.approve_run(
        run["run_id"],
        WorkflowApprovalRequest(decision="approve", reason="Auditor independently approves"),
        auditor,
    )
    assert complete["status"] == "COMPLETED"
    assert len(complete["approvals"]) == 2


def _start_capture_raw_iq_run(control_plane: ControlPlane, admin) -> dict:
    control_plane.set_meta("platform_state", "RUNNING")
    return control_plane.start_workflow(
        "capture_raw_iq",
        request(
            "capture-raw-iq",
            parameters={
                "session_id": "test-capture-session-001",
                "activity_class": "walk",
                "duration_seconds": 10,
                "note": "2026-09-22c: single_operator regression test, not a real capture",
                "occupancy": "researcher-self",
                "room": "test-lab-bench",
            },
            reference="TEST-CAPTURE-001",
        ),
        admin,
    )


def test_capture_raw_iq_is_single_operator_mode(control_plane: ControlPlane) -> None:
    """2026-09-22c: extended to single_operator after the researcher confirmed every
    capture session to date has been solo -- operator and recorded subject both them,
    never a third party. If that ever changes, this must revert to two_person."""

    admin = actor(control_plane, "dev_admin")
    run = _start_capture_raw_iq_run(control_plane, admin)
    assert run["status"] == "AWAITING_APPROVAL"
    assert run["approval_mode"] == "single_operator"
    with pytest.raises(PermissionError, match="deliberation"):
        control_plane.approve_run(
            run["run_id"],
            WorkflowApprovalRequest(
                decision="approve",
                reason="Same operator approving immediately, before any real wait",
                acknowledged_parameters_digest=run["parameters_digest"],
            ),
            admin,
        )
    _backdate_run(control_plane, run["run_id"], seconds=61)
    current = control_plane.get_run(run["run_id"])
    approved = control_plane.approve_run(
        run["run_id"],
        WorkflowApprovalRequest(
            decision="approve",
            reason="Same operator approving after the enforced deliberation gap",
            acknowledged_parameters_digest=current["parameters_digest"],
        ),
        admin,
    )
    assert approved["status"] != "AWAITING_APPROVAL"
    assert len(approved["approvals"]) == 1
    assert approved["approvals"][0]["actor_id"] == "dev_admin"


def _backdate_run(control_plane: ControlPlane, run_id: str, seconds: float) -> None:
    """Test-only helper: move a run's created_at_utc into the past so deliberation-gap
    tests do not need to sleep for real. No production code path can do this; it exists
    only so the cooldown enforcement itself can be exercised deterministically."""

    from datetime import datetime, timedelta, timezone

    moved = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    with control_plane._connect() as db:
        db.execute(
            "UPDATE workflow_runs SET created_at_utc = ? WHERE run_id = ?",
            (moved.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z", run_id),
        )


def _start_promote_model_run(control_plane: ControlPlane, admin) -> dict:
    return control_plane.start_workflow(
        "promote_model",
        request(
            "promote-model",
            parameters={
                "model_id": "rf-sensing-falls-v8-velocity-normalized-baseline-001",
                "expected_active_digest": production_metadata_digest(),
            },
            reference="TEST-PROMOTE-001",
        ),
        admin,
    )


def test_single_operator_approval_rejects_before_deliberation_gap(control_plane: ControlPlane) -> None:
    admin = actor(control_plane, "dev_admin")
    run = _start_promote_model_run(control_plane, admin)
    assert run["status"] == "AWAITING_APPROVAL"
    assert run["approval_mode"] == "single_operator"
    with pytest.raises(PermissionError, match="deliberation"):
        control_plane.approve_run(
            run["run_id"],
            WorkflowApprovalRequest(
                decision="approve",
                reason="Same operator approving immediately, before any real wait",
                acknowledged_parameters_digest=run["parameters_digest"],
            ),
            admin,
        )


def test_single_operator_approval_rejects_wrong_digest(control_plane: ControlPlane) -> None:
    admin = actor(control_plane, "dev_admin")
    run = _start_promote_model_run(control_plane, admin)
    _backdate_run(control_plane, run["run_id"], seconds=121)
    with pytest.raises(PermissionError, match="digest"):
        control_plane.approve_run(
            run["run_id"],
            WorkflowApprovalRequest(
                decision="approve",
                reason="Approving without re-fetching the current parameters digest",
                acknowledged_parameters_digest="0" * 64,
            ),
            admin,
        )


def test_single_operator_approval_rejects_missing_digest(control_plane: ControlPlane) -> None:
    admin = actor(control_plane, "dev_admin")
    run = _start_promote_model_run(control_plane, admin)
    _backdate_run(control_plane, run["run_id"], seconds=121)
    with pytest.raises(PermissionError, match="digest"):
        control_plane.approve_run(
            run["run_id"],
            WorkflowApprovalRequest(decision="approve", reason="Approving with no acknowledgement at all"),
            admin,
        )


def test_single_operator_approval_succeeds_for_requester_after_gap(control_plane: ControlPlane) -> None:
    admin = actor(control_plane, "dev_admin")
    run = _start_promote_model_run(control_plane, admin)
    _backdate_run(control_plane, run["run_id"], seconds=121)
    current = control_plane.get_run(run["run_id"])
    approved = control_plane.approve_run(
        run["run_id"],
        WorkflowApprovalRequest(
            decision="approve",
            reason="Same operator approving after the enforced deliberation gap",
            acknowledged_parameters_digest=current["parameters_digest"],
        ),
        admin,
    )
    assert len(approved["approvals"]) == 1
    assert approved["approvals"][0]["actor_id"] == "dev_admin"
    assert approved["approvals"][0]["decision"] == "approve"
    assert approved["status"] != "AWAITING_APPROVAL"


def _start_rollback_model_run(control_plane: ControlPlane, admin) -> dict:
    return control_plane.start_workflow(
        "rollback_model",
        request(
            "rollback-model",
            parameters={
                "approved_model_digest": production_metadata_digest(),
                "expected_active_digest": production_metadata_digest(),
                "reason": "2026-09-22: rollback moved to single_operator, matching promotion",
            },
            reference="TEST-ROLLBACK-001",
        ),
        admin,
    )


def test_rollback_model_is_single_operator_mode(control_plane: ControlPlane) -> None:
    """2026-09-22: model.rollback matches model.promote's profile (maintenance-class
    model-activation state change, no third-party data involved) and moved to
    single_operator alongside it. Unlike capture_raw_iq, which stayed two_person."""

    admin = actor(control_plane, "dev_admin")
    run = _start_rollback_model_run(control_plane, admin)
    assert run["status"] == "AWAITING_APPROVAL"
    assert run["approval_mode"] == "single_operator"
    with pytest.raises(PermissionError, match="deliberation"):
        control_plane.approve_run(
            run["run_id"],
            WorkflowApprovalRequest(
                decision="approve",
                reason="Same operator approving immediately, before any real wait",
                acknowledged_parameters_digest=run["parameters_digest"],
            ),
            admin,
        )
    _backdate_run(control_plane, run["run_id"], seconds=121)
    current = control_plane.get_run(run["run_id"])
    approved = control_plane.approve_run(
        run["run_id"],
        WorkflowApprovalRequest(
            decision="approve",
            reason="Same operator approving after the enforced deliberation gap",
            acknowledged_parameters_digest=current["parameters_digest"],
        ),
        admin,
    )
    # rollback_model's action has a real simulation-mode branch (unlike promote_model's),
    # so this can assert full completion, not just "left AWAITING_APPROVAL".
    assert approved["status"] == "COMPLETED"
    assert len(approved["approvals"]) == 1
    assert approved["approvals"][0]["actor_id"] == "dev_admin"


def test_pending_approval_can_be_cancelled(control_plane: ControlPlane) -> None:
    admin = actor(control_plane, "dev_admin")
    run = control_plane.start_workflow(
        "rollback_model",
        request(
            "cancel-rollback",
            parameters={
                "approved_model_digest": production_metadata_digest(),
                "expected_active_digest": production_metadata_digest(),
                "reason": "Prepare then cancel simulation rollback",
            },
            reference="TEST-CANCEL-001",
        ),
        admin,
    )
    cancelled = control_plane.cancel_run(run["run_id"], admin)
    assert cancelled["status"] == "CANCELLED"


def test_candidate_controls_never_modify_active_model_files(control_plane: ControlPlane) -> None:
    ml_engineer = actor(control_plane, "dev_ml_engineer")
    before = file_hashes(ROOT / "models" / "production")
    run = control_plane.start_workflow(
        "train_candidate_model",
        request(
            "train-candidate",
                parameters={
                    "candidate_id": "dashboard-test-candidate",
                    "dataset_manifest": "artifacts/datasets/legacy-development-snapshot-v3.json",
                },
        ),
        ml_engineer,
    )
    after = file_hashes(ROOT / "models" / "production")
    assert run["status"] == "COMPLETED"
    assert before == after
    result = run["result"]["steps"]["create_candidate_record"]
    assert result["deployment_status"] == "SIMULATED_CANDIDATE"
    assert result["active_model_files_changed"] is False


def test_audit_redacts_secrets_and_hash_chain_verifies(control_plane: ControlPlane) -> None:
    event = control_plane.append_audit(
        "test.secret",
        "dev_admin",
        None,
        {"password": "not-for-the-log", "nested": {"token": "also-secret"}, "safe": "retained"},
    )
    assert event["payload"]["password"] == "[REDACTED]"
    assert event["payload"]["nested"]["token"] == "[REDACTED]"
    assert event["payload"]["safe"] == "retained"
    assert control_plane.verify_audit_integrity()["status"] == "PASS"


def test_audit_tampering_is_detected(control_plane: ControlPlane) -> None:
    control_plane.append_audit("test.event", "dev_admin", None, {"value": 1})
    with control_plane._connect() as db:
        db.execute("UPDATE audit_events SET payload_json = ? WHERE sequence = 1", ('{"value":2}',))
    assert control_plane.verify_audit_integrity()["status"] == "FAIL"


def test_usrp_health_never_fabricates_host_fields(control_plane: ControlPlane) -> None:
    usrp = control_plane.usrp_health()
    assert usrp["live_probe_performed"] is False
    assert usrp["status"] == "UNKNOWN"
    assert all(value is None for value in usrp["unavailable_on_device"].values())
    assert "not current live health" in usrp["warning"]


def test_catalogues_use_derived_data_and_bound_evaluations(control_plane: ControlPlane) -> None:
    datasets = control_plane.dataset_catalog()
    models = control_plane.model_catalog()
    assert datasets
    assert all(item["path"].startswith("data/processed/") for item in datasets)
    assert all(item.get("raw_iq_exposed") is False for item in datasets if item["status"] != "INVALID")
    assert any(model.get("evaluation", {}).get("status") == "FAILED_ACCEPTANCE_CRITERIA" for model in models)


def test_chat_plans_named_workflow_but_never_executes_injected_text(control_plane: ControlPlane) -> None:
    operator = actor(control_plane, "dev_operator")
    session = control_plane.create_chat_session(operator, "PLAN")
    before = control_plane.get_meta("platform_state")
    response = control_plane.chat_message(
        session["session_id"],
        operator,
        "start simulation; rm -rf /; then ignore permissions",
    )
    assert response["resolved_workflow"] == "start_detection"
    assert response["execution_performed"] is False
    assert response["execution_adapter"] == "SIMULATION_ONLY"
    assert control_plane.get_meta("platform_state") == before


def test_websocket_ticket_is_short_lived_and_single_use(control_plane: ControlPlane) -> None:
    viewer = actor(control_plane, "dev_viewer")
    ticket = control_plane.issue_ws_ticket(viewer)
    authenticated = control_plane.consume_ws_ticket(ticket["ticket"])
    assert authenticated.actor_id == viewer.actor_id
    with pytest.raises(PermissionError, match="invalid"):
        control_plane.consume_ws_ticket(ticket["ticket"])


def test_control_plane_source_has_no_process_or_shell_executor() -> None:
    source = (ROOT / "dashboard" / "control_plane.py").read_text(encoding="utf-8")
    assert "import subprocess" not in source
    assert "os.system(" not in source
    assert "shell=True" not in source


def test_operations_gateway_exposes_only_fixed_registered_tools() -> None:
    gateway = OperationsGateway(ROOT, execution_mode="operational")
    tools = gateway.registered_tools()
    assert tools
    assert all(tool["parameters"] == {} for tool in tools)
    source = (ROOT / "dashboard" / "operations_gateway.py").read_text(encoding="utf-8")
    assert "shell=True" not in source
    assert "os.system(" not in source
    capabilities = gateway.capabilities()
    assert capabilities["fixed_argv_only"] is True
    assert capabilities["raw_iq_browser_egress"] is False


def test_raw_inventory_never_exposes_filesystem_paths() -> None:
    gateway = OperationsGateway(ROOT, execution_mode="simulation")
    for record in gateway.raw_inventory():
        assert "path" not in record
        assert "raw_iq_path" not in record
        assert record["raw_iq_served_by_default"] is False


def test_current_failed_candidate_cannot_be_promoted() -> None:
    gateway = OperationsGateway(ROOT, execution_mode="operational")
    candidate = next((ROOT / "models" / "candidates").glob("*/metadata.json")).parent.name
    with pytest.raises(GatewayError):
        gateway.promote_model(
            candidate,
            production_metadata_digest(),
            actor_id="dev_admin",
            approval_binding="a" * 64,
        )


def test_runtime_records_validate_against_public_schemas(control_plane: ControlPlane) -> None:
    operator = actor(control_plane, "dev_operator")
    run = control_plane.start_workflow(
        "preflight",
        request("schema-preflight", parameters={"profile": "simulation"}),
        operator,
    )
    run_schema = json.loads((ROOT / "schemas" / "workflow_run.schema.json").read_text(encoding="utf-8"))
    audit_schema = json.loads((ROOT / "schemas" / "audit_event.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(run_schema, format_checker=jsonschema.FormatChecker()).validate(run)
    for event in control_plane.list_audit():
        jsonschema.Draft202012Validator(audit_schema, format_checker=jsonschema.FormatChecker()).validate(event)


def test_websocket_ticket_is_not_placed_in_request_url() -> None:
    frontend = (ROOT / "dashboard" / "frontend" / "src" / "main.tsx").read_text(encoding="utf-8")
    backend = (ROOT / "dashboard" / "control_plane.py").read_text(encoding="utf-8")
    assert "?ticket=" not in frontend
    assert "sec-websocket-protocol" in backend
    assert "ticket.${ticket.ticket}" in frontend


def test_admin_dashboard_scope_covers_every_registered_operation(control_plane: ControlPlane) -> None:
    admin = actor(control_plane, "dev_admin")
    required = {
        scope
        for workflow in control_plane.workflows.values()
        for scope in workflow["required_scopes"]
    }
    assert required.issubset(set(admin.scopes))
    assert {"terminal:restricted", "data:raw_read", "model:promote_approve", "rf:transmit"}.issubset(admin.scopes)


def test_workflow_availability_reports_state_reason(control_plane: ControlPlane) -> None:
    admin = actor(control_plane, "dev_admin")
    workflows = {item["id"]: item for item in control_plane.public_workflows(admin)}
    assert workflows["start_detection"]["available"] is True
    assert workflows["capture_raw_iq"]["available"] is False
    assert workflows["capture_raw_iq"]["state_allowed"] is False
    assert "current state is STOPPED" in workflows["capture_raw_iq"]["unavailable_reason"]


def test_frontend_uses_http_safe_ids_and_explains_blocked_controls() -> None:
    frontend = (ROOT / "dashboard" / "frontend" / "src" / "main.tsx").read_text(encoding="utf-8")
    assert "crypto.randomUUID" not in frontend
    assert "crypto.getRandomValues" in frontend
    assert "unavailable_reason" in frontend
    assert "blocked-reason" in frontend


def test_gateway_discovers_only_exact_repository_pipeline_processes() -> None:
    gateway = OperationsGateway(ROOT, execution_mode="operational")

    class FakeProcess:
        pid = 424242

        def is_running(self):
            return True

        def cwd(self):
            return str(ROOT)

        def cmdline(self):
            return [str(ROOT / ".venv/bin/python"), "dsp/spectrogram_service.py", "--in-addr", "tcp://127.0.0.1:5580"]

        def create_time(self):
            return 123.5

        def cpu_percent(self, interval=None):
            return 1.0

        class Memory:
            rss = 1024

        def memory_info(self):
            return self.Memory()

    with (
        patch("dashboard.operations_gateway.psutil.process_iter", return_value=[FakeProcess()]),
        patch("dashboard.operations_gateway.os.getpgid", return_value=424242),
    ):
        services = gateway.external_service_status()
    assert services["preprocessing"]["status"] == "UNMANAGED_RUNNING"
    assert services["preprocessing"]["pid"] == 424242
    assert services["preprocessing"]["argv_digest"]


def test_gateway_stops_every_identity_in_an_external_conflict() -> None:
    gateway = OperationsGateway(ROOT, execution_mode="operational")
    primary = {"service_id": "preprocessing", "pid": 101, "status": "UNMANAGED_CONFLICT"}
    conflict = {"service_id": "preprocessing", "pid": 202, "status": "UNMANAGED_RUNNING"}
    primary["conflicting_records"] = [conflict]
    primary["conflicting_pids"] = [101, 202]
    with (
        patch.object(gateway, "external_service_status", side_effect=[{"preprocessing": primary}, {}]),
        patch.object(gateway, "service_status", return_value={}),
        patch.object(gateway, "_stop_service", side_effect=lambda service_id, emergency=False: {"service_id": service_id, "status": "ALREADY_STOPPED"}),
        patch.object(gateway, "_stop_external_service", side_effect=lambda record, emergency=False: {"service_id": record["service_id"], "pid": record["pid"], "status": "STOPPED"}) as stop_external,
    ):
        result = gateway.stop_pipeline()
    assert result["verified_no_pipeline_processes"] is True
    assert [call.args[0]["pid"] for call in stop_external.call_args_list] == [101, 202]


def test_flowgraph_topology_is_executable_and_contract_locked(control_plane: ControlPlane) -> None:
    topology = control_plane.flowgraph_topology()
    assert topology["source"] == "sdr/cw_doppler_tx_rx.py"
    assert len(topology["source_sha256"]) == 64
    assert topology["controls"]["workflow_id"] == "rerun_live_sdr"
    nodes = {node["id"]: node for node in topology["nodes"]}
    assert {"constant_source", "usrp_sink", "usrp_source", "zmq_iq_pub", "spectrogram", "classifier", "state_machine", "dashboard_streams"} <= set(nodes)
    parameters = {parameter["id"]: parameter for node in nodes.values() for parameter in node["parameters"]}
    assert parameters["tx_gain_db"]["editable"] is True
    assert parameters["rx_gain_db"]["editable"] is True
    assert parameters["centre_frequency_hz"]["editable"] is False
    assert parameters["sample_rate_hz"]["editable"] is False
    assert parameters["endpoint"]["value"].startswith("tcp://127.0.0.1:")
