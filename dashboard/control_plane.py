"""Typed operations control plane for the CARAT DEVELOPMENT dashboard.

State-changing requests resolve to versioned workflows and are executed either
by the deterministic simulation adapter or by the narrow fixed-argv local
operations gateway.  This layer never accepts a command string and does not
import a process or shell API.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import platform
import re
import secrets
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import jsonschema
import psutil
import pyarrow.parquet as pq
import yaml
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from tools.governance_validation import validate_workflow_semantics, workflow_definition_digest
from dashboard.operations_gateway import GatewayError, OperationsGateway, canonical_digest


PLATFORM_STATES = {
    "UNINITIALISED",
    "STOPPED",
    "MAINTENANCE",
    "PREFLIGHT",
    "STARTING",
    "RUNNING",
    "DEGRADED",
    "STOPPING",
    "FAILED",
}
TERMINAL_RUN_STATES = {
    "COMPLETED",
    "DRY_RUN_COMPLETED",
    "FAILED",
    "ROLLED_BACK",
    "CANCELLED",
}
TOKEN_TTL_HOURS = 8
WS_TICKET_TTL_SECONDS = 30
REDACT_KEYS = {
    "authorization",
    "password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "cookie",
    "patient_id",
    "participant_id",
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc_text(value: datetime | None = None) -> str:
    return (value or _utc_now()).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _redact(value: Any, key: str | None = None) -> Any:
    if key and key.lower() in REDACT_KEYS:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str) and len(value) > 4096:
        return f"{value[:4096]}...[TRUNCATED]"
    return value


@dataclass(frozen=True)
class Actor:
    """Authenticated development actor and immutable scope set."""

    actor_id: str
    display_name: str
    role: str
    scopes: frozenset[str]


class LoginRequest(BaseModel):
    actor_id: str = Field(min_length=3, max_length=64)
    bootstrap_secret: str = Field(min_length=1, max_length=1024)


class WorkflowRunRequest(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False
    confirmed: bool = False
    idempotency_key: str = Field(min_length=8, max_length=128)
    reason: str | None = Field(default=None, max_length=512)
    reference: str | None = Field(default=None, max_length=128)


class WorkflowApprovalRequest(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    reason: str = Field(min_length=10, max_length=512)
    # single_operator mode only: must equal the run's CURRENT bound-parameters digest
    # (as returned by GET /workflow-runs/{run_id}), so approving requires re-fetching
    # and re-reading the exact parameters right before the decision, not just clicking.
    acknowledged_parameters_digest: str | None = Field(default=None, pattern="^[a-f0-9]{64}$")


class ChatSessionRequest(BaseModel):
    mode: str = Field(default="EXPLAIN", pattern="^(EXPLAIN|PLAN)$")


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ToolRunRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=512)
    reference: str | None = Field(default=None, max_length=128)


class ControlPlane:
    """Durable local control plane with simulation and typed operational adapters."""

    LONG_RUNNING_ACTIONS = {
        "data.capture_raw_iq",
        "model.train_candidate",
        "model.evaluate_candidate",
        "model.recalibrate_candidate",
    }

    def __init__(
        self,
        repo_root: Path,
        db_path: Path,
        *,
        auth_secret: str | None,
        gateway: OperationsGateway | None = None,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.db_path = db_path.resolve()
        self.auth_secret = auth_secret
        self.gateway = gateway or OperationsGateway(self.repo_root, execution_mode="simulation")
        self.schema_path = self.repo_root / "schemas" / "workflow.schema.json"
        self.registry_path = self.repo_root / "configs" / "control_plane" / "action_registry.yaml"
        self.workflow_dir = self.repo_root / "configs" / "control_plane" / "workflows"
        self.rbac_path = self.repo_root / "configs" / "control_plane" / "rbac.yaml"
        self.project_path = self.repo_root / "configs" / "project.yaml"
        self._mutex = threading.RLock()
        self._workers: dict[str, threading.Thread] = {}
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise_database()
        self._seed_users()
        self._load_and_validate_workflows()

    @classmethod
    def from_environment(cls, repo_root: Path) -> "ControlPlane":
        configured = os.environ.get("RF_FALLS_CONTROL_DB", "").strip()
        db_path = Path(configured) if configured else repo_root / "artifacts" / "control_plane" / "runtime" / "control-plane.sqlite3"
        return cls(
            repo_root,
            db_path,
            auth_secret=os.environ.get("RF_FALLS_DEV_AUTH_SECRET"),
            gateway=OperationsGateway.from_environment(repo_root),
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialise_database(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS users (
                    actor_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    scopes_json TEXT NOT NULL,
                    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1))
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    actor_id TEXT NOT NULL REFERENCES users(actor_id),
                    issued_at_utc TEXT NOT NULL,
                    expires_at_utc TEXT NOT NULL,
                    revoked_at_utc TEXT
                );
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    run_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    workflow_version INTEGER NOT NULL,
                    workflow_digest TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    dry_run INTEGER NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    reason TEXT,
                    reference TEXT,
                    result_json TEXT,
                    error TEXT,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    UNIQUE(workflow_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS workflow_steps (
                    run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
                    step_id TEXT NOT NULL,
                    action_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at_utc TEXT,
                    completed_at_utc TEXT,
                    result_json TEXT,
                    error TEXT,
                    PRIMARY KEY(run_id, step_id)
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
                    actor_id TEXT NOT NULL REFERENCES users(actor_id),
                    decision TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    decided_at_utc TEXT NOT NULL,
                    acknowledged_parameters_digest TEXT,
                    PRIMARY KEY(run_id, actor_id)
                );
                CREATE TABLE IF NOT EXISTS resource_locks (
                    resource_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
                    acquired_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    timestamp_utc TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    actor_id TEXT,
                    correlation_id TEXT,
                    payload_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    actor_id TEXT NOT NULL REFERENCES users(actor_id),
                    mode TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chat_messages (
                    message_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES chat_sessions(session_id),
                    role TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ws_tickets (
                    ticket_hash TEXT PRIMARY KEY,
                    actor_id TEXT NOT NULL REFERENCES users(actor_id),
                    expires_at_utc TEXT NOT NULL,
                    used_at_utc TEXT
                );
                CREATE TABLE IF NOT EXISTS simulation_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    base_digest TEXT,
                    dataset_ref TEXT,
                    created_by TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                """
            )
            self._migrate_approvals_table(db)
        if self.get_meta("platform_state") is None:
            self.set_meta("platform_state", "STOPPED")
        if self.get_meta("simulation_services") is None:
            self.set_meta(
                "simulation_services",
                {
                    "acquisition": "STOPPED",
                    "preprocessing": "STOPPED",
                    "inference": "STOPPED",
                    "event_aggregation": "STOPPED",
                    "storage": "HEALTHY",
                    "dashboard": "HEALTHY",
                },
            )
        if self.get_meta("detection_mode") is None:
            self.set_meta("detection_mode", "DISABLED")

    def _migrate_approvals_table(self, db: sqlite3.Connection) -> None:
        """Add acknowledged_parameters_digest to a pre-existing approvals table.

        CREATE TABLE IF NOT EXISTS does not alter a table that already exists, so a
        database created before single_operator mode was introduced needs this column
        added explicitly, once, idempotently.
        """

        columns = {row["name"] for row in db.execute("PRAGMA table_info(approvals)").fetchall()}
        if "acknowledged_parameters_digest" not in columns:
            db.execute("ALTER TABLE approvals ADD COLUMN acknowledged_parameters_digest TEXT")

    def _seed_users(self) -> None:
        document = yaml.safe_load(self.rbac_path.read_text(encoding="utf-8"))
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for user in document["development_users"]:
                db.execute(
                    """
                    INSERT INTO users(actor_id, display_name, role, scopes_json, enabled)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(actor_id) DO UPDATE SET
                      display_name=excluded.display_name,
                      role=excluded.role,
                      scopes_json=excluded.scopes_json,
                      enabled=excluded.enabled
                    """,
                    (
                        user["actor_id"],
                        user["display_name"],
                        user["role"],
                        _canonical(user["scopes"]),
                        int(user.get("enabled", True)),
                    ),
                )
            db.commit()

    def _load_and_validate_workflows(self) -> None:
        schema = json.loads(self.schema_path.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
        workflows: dict[str, dict[str, Any]] = {}
        for path in sorted(self.workflow_dir.glob("*.yaml")):
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            errors = sorted(validator.iter_errors(document), key=lambda item: list(item.path))
            if errors:
                detail = "; ".join(error.message for error in errors)
                raise RuntimeError(f"invalid workflow {path.name}: {detail}")
            validate_workflow_semantics(document, self.registry_path)
            if document["id"] in workflows:
                raise RuntimeError(f"duplicate workflow id: {document['id']}")
            definition_digest = workflow_definition_digest(document)
            document["_path"] = str(path.relative_to(self.repo_root))
            document["_digest"] = definition_digest
            workflows[document["id"]] = document
        if not workflows:
            raise RuntimeError("no versioned control-plane workflows were found")
        self.workflows = workflows

    def get_meta(self, key: str) -> Any | None:
        with self._connect() as db:
            row = db.execute("SELECT value_json FROM meta WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value_json"]) if row else None

    def set_meta(self, key: str, value: Any) -> None:
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO meta(key, value_json, updated_at_utc) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at_utc=excluded.updated_at_utc
                """,
                (key, _canonical(value), _utc_text()),
            )

    def list_development_users(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT actor_id, display_name, role, scopes_json FROM users WHERE enabled = 1 ORDER BY actor_id"
            ).fetchall()
        return [
            {
                "actor_id": row["actor_id"],
                "display_name": row["display_name"],
                "role": row["role"],
                "scopes": json.loads(row["scopes_json"]),
            }
            for row in rows
        ]

    def login(self, actor_id: str, bootstrap_secret: str) -> dict[str, Any]:
        if not self.auth_secret:
            raise PermissionError("development authentication is not configured")
        if not hmac.compare_digest(bootstrap_secret, self.auth_secret):
            self.append_audit("auth.login.denied", None, None, {"actor_id": actor_id}, severity="warning")
            raise PermissionError("invalid development credentials")
        with self._connect() as db:
            row = db.execute(
                "SELECT actor_id, display_name, role, scopes_json FROM users WHERE actor_id = ? AND enabled = 1",
                (actor_id,),
            ).fetchone()
        if row is None:
            raise PermissionError("unknown or disabled development actor")
        token = secrets.token_urlsafe(32)
        issued = _utc_now()
        expires = issued + timedelta(hours=TOKEN_TTL_HOURS)
        with self._connect() as db:
            db.execute(
                "INSERT INTO sessions(token_hash, actor_id, issued_at_utc, expires_at_utc) VALUES (?, ?, ?, ?)",
                (_sha256_bytes(token.encode()), actor_id, _utc_text(issued), _utc_text(expires)),
            )
        self.append_audit("auth.login.succeeded", actor_id, None, {"role": row["role"]})
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_at_utc": _utc_text(expires),
            "actor": {
                "actor_id": row["actor_id"],
                "display_name": row["display_name"],
                "role": row["role"],
                "scopes": json.loads(row["scopes_json"]),
            },
        }

    def authenticate(self, token: str) -> Actor:
        digest = _sha256_bytes(token.encode())
        with self._connect() as db:
            row = db.execute(
                """
                SELECT u.actor_id, u.display_name, u.role, u.scopes_json, s.expires_at_utc, s.revoked_at_utc
                FROM sessions s JOIN users u ON u.actor_id = s.actor_id
                WHERE s.token_hash = ? AND u.enabled = 1
                """,
                (digest,),
            ).fetchone()
        if row is None or row["revoked_at_utc"] is not None:
            raise PermissionError("invalid session")
        expires = datetime.fromisoformat(row["expires_at_utc"].replace("Z", "+00:00"))
        if expires <= _utc_now():
            raise PermissionError("expired session")
        return Actor(
            actor_id=row["actor_id"],
            display_name=row["display_name"],
            role=row["role"],
            scopes=frozenset(json.loads(row["scopes_json"])),
        )

    def _current_actor(self, actor_id: str) -> Actor:
        with self._connect() as db:
            row = db.execute(
                "SELECT actor_id, display_name, role, scopes_json FROM users WHERE actor_id = ? AND enabled = 1",
                (actor_id,),
            ).fetchone()
        if row is None:
            raise PermissionError("workflow requester is no longer an enabled actor")
        return Actor(
            actor_id=row["actor_id"],
            display_name=row["display_name"],
            role=row["role"],
            scopes=frozenset(json.loads(row["scopes_json"])),
        )

    def revoke(self, token: str, actor: Actor) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE sessions SET revoked_at_utc = ? WHERE token_hash = ? AND actor_id = ?",
                (_utc_text(), _sha256_bytes(token.encode()), actor.actor_id),
            )
        self.append_audit("auth.logout", actor.actor_id, None, {})

    @staticmethod
    def require_scopes(actor: Actor, required: Iterable[str]) -> None:
        missing = set(required) - set(actor.scopes)
        if missing:
            raise PermissionError(f"missing scopes: {', '.join(sorted(missing))}")

    def append_audit(
        self,
        event_type: str,
        actor_id: str | None,
        correlation_id: str | None,
        payload: dict[str, Any],
        *,
        severity: str = "info",
    ) -> dict[str, Any]:
        timestamp = _utc_text()
        event_id = str(uuid.uuid4())
        safe_payload = _redact(payload)
        with self._mutex, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            previous_hash = previous["event_hash"] if previous else "0" * 64
            material = {
                "event_id": event_id,
                "timestamp_utc": timestamp,
                "event_type": event_type,
                "severity": severity,
                "actor_id": actor_id,
                "correlation_id": correlation_id,
                "payload": safe_payload,
                "previous_hash": previous_hash,
            }
            event_hash = _sha256_bytes(_canonical(material).encode())
            cursor = db.execute(
                """
                INSERT INTO audit_events(
                  event_id, timestamp_utc, event_type, severity, actor_id,
                  correlation_id, payload_json, previous_hash, event_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    timestamp,
                    event_type,
                    severity,
                    actor_id,
                    correlation_id,
                    _canonical(safe_payload),
                    previous_hash,
                    event_hash,
                ),
            )
            sequence = int(cursor.lastrowid)
            db.commit()
        return {**material, "sequence": sequence, "event_hash": event_hash}

    def list_audit(self, *, after: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 1000))
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM audit_events WHERE sequence > ? ORDER BY sequence ASC LIMIT ?",
                (max(0, after), limit),
            ).fetchall()
        return [
            {
                "api_version": "v1",
                "sequence": row["sequence"],
                "event_id": row["event_id"],
                "timestamp": row["timestamp_utc"],
                "type": row["event_type"],
                "severity": row["severity"],
                "source": "control-plane",
                "correlation_id": row["correlation_id"],
                "actor_id": row["actor_id"],
                "payload": json.loads(row["payload_json"]),
                "previous_hash": row["previous_hash"],
                "event_hash": row["event_hash"],
            }
            for row in rows
        ]

    def verify_audit_integrity(self) -> dict[str, Any]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM audit_events ORDER BY sequence ASC").fetchall()
        events = [
            {
                "sequence": row["sequence"],
                "event_id": row["event_id"],
                "timestamp": row["timestamp_utc"],
                "type": row["event_type"],
                "severity": row["severity"],
                "actor_id": row["actor_id"],
                "correlation_id": row["correlation_id"],
                "payload": json.loads(row["payload_json"]),
                "previous_hash": row["previous_hash"],
                "event_hash": row["event_hash"],
            }
            for row in rows
        ]
        previous_hash = "0" * 64
        for event in events:
            material = {
                "event_id": event["event_id"],
                "timestamp_utc": event["timestamp"],
                "event_type": event["type"],
                "severity": event["severity"],
                "actor_id": event["actor_id"],
                "correlation_id": event["correlation_id"],
                "payload": event["payload"],
                "previous_hash": previous_hash,
            }
            expected = _sha256_bytes(_canonical(material).encode())
            if event["previous_hash"] != previous_hash or not hmac.compare_digest(expected, event["event_hash"]):
                return {"status": "FAIL", "failed_sequence": event["sequence"], "events_checked": event["sequence"] - 1}
            previous_hash = event["event_hash"]
        return {"status": "PASS", "events_checked": len(events), "head_hash": previous_hash}

    def public_workflows(self, actor: Actor) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        current_state = self.platform_state()["state"]
        for workflow in self.workflows.values():
            missing = sorted(set(workflow["required_scopes"]) - set(actor.scopes))
            state_allowed = current_state in workflow["allowed_source_states"]
            unavailable_reasons: list[str] = []
            if missing:
                unavailable_reasons.append(f"Missing scope: {', '.join(missing)}")
            if not state_allowed:
                expected = ", ".join(workflow["allowed_source_states"])
                unavailable_reasons.append(f"Available from {expected}; current state is {current_state}")
            output.append(
                {
                    "id": workflow["id"],
                    "display_name": workflow["display_name"],
                    "version": workflow["version"],
                    "digest": workflow["_digest"],
                    "safety_class": workflow["safety_class"],
                    "required_scopes": workflow["required_scopes"],
                    "approval_policy": workflow["approval_policy"],
                    "allowed_source_states": workflow["allowed_source_states"],
                    "locks": workflow["locks"],
                    "parameters": workflow["parameters"],
                    "dry_run_supported": True,
                    "available": not missing and state_allowed,
                    "missing_scopes": missing,
                    "state_allowed": state_allowed,
                    "current_state": current_state,
                    "unavailable_reason": "; ".join(unavailable_reasons) or None,
                    "execution_adapter": "TYPED_OPERATIONAL_GATEWAY" if self.gateway.operational else "SIMULATION_ONLY",
                }
            )
        return output

    def _validate_parameters(self, workflow: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
        definitions = workflow["parameters"]
        unknown = set(parameters) - set(definitions)
        if unknown:
            raise ValueError(f"unknown workflow parameters: {', '.join(sorted(unknown))}")
        resolved: dict[str, Any] = {}
        for name, definition in definitions.items():
            if name in parameters:
                value = parameters[name]
            elif "default" in definition:
                value = definition["default"]
            elif definition["required"]:
                raise ValueError(f"missing required parameter: {name}")
            else:
                continue
            expected = definition["type"]
            valid_type = {
                "string": isinstance(value, str),
                "integer": isinstance(value, int) and not isinstance(value, bool),
                "number": isinstance(value, (int, float)) and not isinstance(value, bool),
                "boolean": isinstance(value, bool),
            }[expected]
            if not valid_type:
                raise ValueError(f"parameter {name} must be {expected}")
            if "enum" in definition and value not in definition["enum"]:
                raise ValueError(f"parameter {name} is outside the allowlist")
            if isinstance(value, str):
                if len(value) < definition.get("min_length", 0) or len(value) > definition.get("max_length", 1024):
                    raise ValueError(f"parameter {name} has invalid length")
                if "pattern" in definition and re.fullmatch(definition["pattern"], value) is None:
                    raise ValueError(f"parameter {name} has invalid format")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if value < definition.get("minimum", float("-inf")) or value > definition.get("maximum", float("inf")):
                    raise ValueError(f"parameter {name} is outside the approved range")
            resolved[name] = value
        return resolved

    def _resolve_arguments(self, arguments: dict[str, Any], parameters: dict[str, Any], run_id: str) -> dict[str, Any]:
        context = {
            "run_id": run_id,
            "actor_id": "redacted-runtime-context",
            "target_environment": self.project()["environment"],
            "workflow_digest": "bound-in-run-record",
            "correlation_id": run_id,
            "approved_model_id": "none",
            "active_config_id": self.project()["config_digest"],
        }
        resolved: dict[str, Any] = {}
        for name, source in arguments.items():
            if "literal" in source:
                resolved[name] = source["literal"]
            elif "parameter_ref" in source:
                resolved[name] = parameters[source["parameter_ref"]]
            else:
                resolved[name] = context[source["context_ref"]]
        return resolved

    def start_workflow(self, workflow_id: str, request: WorkflowRunRequest, actor: Actor) -> dict[str, Any]:
        workflow = self.workflows.get(workflow_id)
        if workflow is None:
            raise KeyError("unknown workflow")
        self.require_scopes(actor, workflow["required_scopes"])
        with self._connect() as db:
            existing = db.execute(
                "SELECT run_id FROM workflow_runs WHERE workflow_id = ? AND idempotency_key = ?",
                (workflow_id, request.idempotency_key),
            ).fetchone()
        if existing:
            return self.get_run(existing["run_id"])
        project = self.project()
        if project["environment"] not in workflow["allowed_environments"]:
            raise PermissionError("workflow is not allowed in this environment")
        current_state = self.get_meta("platform_state")
        if current_state not in workflow["allowed_source_states"]:
            raise RuntimeError(f"workflow {workflow_id} is not allowed from {current_state}")
        parameters = self._validate_parameters(workflow, request.parameters)
        approval = workflow["approval_policy"]
        if approval["reason_required"] and (not request.reason or len(request.reason.strip()) < 10):
            raise ValueError("a reason of at least 10 characters is required")
        if approval["reference_required"] and not request.reference:
            raise ValueError("an approval reference is required")
        if approval["mode"] == "confirmation" and not (request.confirmed or request.dry_run):
            raise PermissionError("explicit confirmation is required")

        run_id = str(uuid.uuid4())
        created = _utc_text()
        if request.dry_run:
            status = "DRY_RUN_COMPLETED"
        elif approval["mode"] in ("two_person", "single_operator"):
            status = "AWAITING_APPROVAL"
        else:
            status = "QUEUED"
        preview = self._preview(workflow, parameters, actor)
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO workflow_runs(
                  run_id, workflow_id, workflow_version, workflow_digest, actor_id,
                  status, parameters_json, dry_run, idempotency_key, reason, reference,
                  result_json, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    workflow_id,
                    workflow["version"],
                    workflow["_digest"],
                    actor.actor_id,
                    status,
                    _canonical(parameters),
                    int(request.dry_run),
                    request.idempotency_key,
                    request.reason,
                    request.reference,
                    _canonical({"preview": preview}) if request.dry_run else None,
                    created,
                    created,
                ),
            )
        self.append_audit(
            "workflow.requested",
            actor.actor_id,
            run_id,
            {
                "workflow_id": workflow_id,
                "workflow_version": workflow["version"],
                "workflow_digest": workflow["_digest"],
                "parameters": parameters,
                "dry_run": request.dry_run,
                "idempotency_key": request.idempotency_key,
                "reason": request.reason,
                "reference": request.reference,
            },
        )
        if request.dry_run:
            self.append_audit("workflow.completed", actor.actor_id, run_id, {"status": status, "preview": preview})
        elif approval["mode"] == "two_person":
            self.append_audit("workflow.approval.required", actor.actor_id, run_id, {"required": 2, "mode": "two_person"})
        elif approval["mode"] == "single_operator":
            self.append_audit(
                "workflow.approval.required",
                actor.actor_id,
                run_id,
                {
                    "required": 1,
                    "mode": "single_operator",
                    "minimum_deliberation_seconds": approval.get("minimum_deliberation_seconds", 0),
                },
            )
        else:
            self._dispatch_run(run_id, workflow, parameters, actor)
        return self.get_run(run_id)

    def _preview(self, workflow: dict[str, Any], parameters: dict[str, Any], actor: Actor) -> dict[str, Any]:
        actions = {step["action"] for step in workflow["steps"]}
        return {
            "workflow_id": workflow["id"],
            "version": workflow["version"],
            "digest": workflow["_digest"],
            "source_state": self.get_meta("platform_state"),
            "target_environment": self.project()["environment"],
            "actor": actor.actor_id,
            "steps": [
                {
                    "id": step["id"],
                    "action": step["action"],
                    "arguments": self._resolve_arguments(step["arguments"], parameters, "dry-run"),
                }
                for step in workflow["steps"]
            ],
            "locks": workflow["locks"],
            "execution_adapter": "TYPED_OPERATIONAL_GATEWAY" if self.gateway.operational else "SIMULATION_ONLY",
            "will_execute_shell": False,
            "will_launch_fixed_argv": self.gateway.operational and bool(
                actions & {"pipeline.start", "pipeline.start_live_sdr", "data.capture_raw_iq", "model.train_candidate", "model.evaluate_candidate"}
            ),
            "will_access_usrp": self.gateway.operational and "pipeline.start_live_sdr" in actions,
            "will_transmit_rf": self.gateway.operational and "pipeline.start_live_sdr" in actions,
            "will_access_raw_iq": self.gateway.operational and "data.capture_raw_iq" in actions,
            "will_modify_active_model": self.gateway.operational and bool(actions & {"model.promote", "model.rollback"}),
            "automatic_rf_timeout_seconds": parameters.get("maximum_duration_seconds") if "pipeline.start_live_sdr" in actions else None,
        }

    def _acquire_locks(self, run_id: str, locks: list[str]) -> None:
        with self._mutex, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            conflict = db.execute(
                f"SELECT resource_id, run_id FROM resource_locks WHERE resource_id IN ({','.join('?' for _ in locks)})",
                tuple(locks),
            ).fetchall()
            if conflict:
                db.rollback()
                resources = ", ".join(row["resource_id"] for row in conflict)
                raise RuntimeError(f"workflow resource lock conflict: {resources}")
            for resource in locks:
                db.execute(
                    "INSERT INTO resource_locks(resource_id, run_id, acquired_at_utc) VALUES (?, ?, ?)",
                    (resource, run_id, _utc_text()),
                )
            db.commit()

    def _preempt_and_acquire_emergency_locks(self, run_id: str, locks: list[str], actor: Actor) -> list[str]:
        """Atomically cancel conflicting runs and reserve their resources for emergency stop."""

        with self._mutex, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                f"SELECT DISTINCT run_id FROM resource_locks WHERE resource_id IN ({','.join('?' for _ in locks)})",
                tuple(locks),
            ).fetchall()
            preempted = [str(row["run_id"]) for row in rows if row["run_id"] != run_id]
            for conflicting_run in preempted:
                db.execute(
                    "UPDATE workflow_runs SET status = 'CANCELLED', error = ?, updated_at_utc = ? "
                    "WHERE run_id = ? AND status NOT IN ('COMPLETED','DRY_RUN_COMPLETED','FAILED','ROLLED_BACK','CANCELLED')",
                    (f"preempted by emergency stop {run_id}", _utc_text(), conflicting_run),
                )
            if preempted:
                db.execute(
                    f"DELETE FROM resource_locks WHERE run_id IN ({','.join('?' for _ in preempted)})",
                    tuple(preempted),
                )
            for resource in locks:
                db.execute("DELETE FROM resource_locks WHERE resource_id = ?", (resource,))
                db.execute(
                    "INSERT INTO resource_locks(resource_id, run_id, acquired_at_utc) VALUES (?, ?, ?)",
                    (resource, run_id, _utc_text()),
                )
            db.commit()
        for conflicting_run in preempted:
            self.gateway.cancel_job(conflicting_run)
            self.append_audit(
                "workflow.preempted",
                actor.actor_id,
                conflicting_run,
                {"emergency_run_id": run_id, "resources": locks},
                severity="warning",
            )
        return preempted

    def _release_locks(self, run_id: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM resource_locks WHERE run_id = ?", (run_id,))

    def _set_run_status(self, run_id: str, status: str, *, result: Any = None, error: str | None = None) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE workflow_runs SET status = ?, result_json = ?, error = ?, updated_at_utc = ? WHERE run_id = ?",
                (status, _canonical(result) if result is not None else None, error, _utc_text(), run_id),
            )

    def _dispatch_run(
        self,
        run_id: str,
        workflow: dict[str, Any],
        parameters: dict[str, Any],
        actor: Actor,
    ) -> None:
        """Run bounded local jobs off the API thread; keep short/simulated work deterministic."""

        actions = {step["action"] for step in workflow["steps"]}
        if not self.gateway.operational or not actions.intersection(self.LONG_RUNNING_ACTIONS):
            self._execute_run(run_id, workflow, parameters, actor)
            return

        def worker() -> None:
            try:
                self._execute_run(run_id, workflow, parameters, actor)
            finally:
                with self._mutex:
                    self._workers.pop(run_id, None)

        thread = threading.Thread(target=worker, name=f"control-run-{run_id[:8]}", daemon=True)
        with self._mutex:
            self._workers[run_id] = thread
        thread.start()

    def _execute_action_bounded(
        self,
        action_id: str,
        arguments: dict[str, Any],
        run_id: str,
        actor: Actor,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        """Execute an action under the declared deadline and trigger typed cleanup on timeout."""

        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"action-{run_id[:8]}")
        future = executor.submit(self._execute_action, action_id, arguments, run_id, actor)
        try:
            return future.result(timeout=max(0.001, timeout_seconds))
        except FutureTimeoutError as exc:
            self.gateway.cancel_job(run_id)
            if action_id.startswith("pipeline."):
                try:
                    self.gateway.stop_pipeline(emergency=True)
                except Exception:
                    pass
                future.add_done_callback(lambda _future: self.gateway.stop_pipeline(emergency=True))
            raise TimeoutError(f"action {action_id} exceeded its {timeout_seconds:g}s execution deadline") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _condition_matches(actual: Any, operator: str, expected: Any) -> bool:
        if operator == "eq": return actual == expected
        if operator == "ne": return actual != expected
        if operator == "lt": return actual < expected
        if operator == "lte": return actual <= expected
        if operator == "gt": return actual > expected
        if operator == "gte": return actual >= expected
        if operator == "in": return actual in expected
        if operator == "not_in": return actual not in expected
        if operator == "is_true": return actual is True
        if operator == "is_false": return actual is False
        raise RuntimeError(f"unsupported postcondition operator: {operator}")

    def _postcondition_facts(
        self,
        workflow: dict[str, Any],
        results: dict[str, Any],
        active_digest_before: str | None,
    ) -> dict[str, Any]:
        actions = {step["id"]: step["action"] for step in workflow["steps"]}
        action_results = [(actions[step_id], result) for step_id, result in results.items() if step_id in actions]
        try:
            active_after = (
                self.gateway.active_pointer().get("metadata_sha256")
                if self.gateway.operational
                else self.get_meta("simulation_active_model_digest") or self.gateway.active_pointer().get("metadata_sha256")
            )
        except Exception:
            active_after = self.get_meta("simulation_active_model_digest")
        pointer_targets = [result.get("after", {}).get("metadata_sha256") for _, result in action_results if isinstance(result, dict)]
        pointer_targets.extend(result.get("simulation_active_model_digest") for _, result in action_results if isinstance(result, dict))
        return {
            "platform.state": self.get_meta("platform_state"),
            "platform.preflight_completed": {action for action, _ in action_results} >= {"config.validate", "health.collect"},
            "health.snapshot_created": any(action == "health.collect" for action, _ in action_results),
            "model.active_changed": active_after != active_digest_before,
            "model.active_pointer_verified": bool(active_after and active_after in pointer_targets),
            "data.raw_session_immutable": any(
                action == "data.capture_raw_iq" and isinstance(result, dict) and bool(result.get("sha256")) and isinstance(result.get("raw_bytes"), int) and result["raw_bytes"] > 0
                for action, result in action_results
            ),
        }

    def _execute_run(self, run_id: str, workflow: dict[str, Any], parameters: dict[str, Any], actor: Actor) -> None:
        if self.get_run(run_id)["status"] == "CANCELLED":
            return
        try:
            if workflow["id"] == "emergency_stop":
                self._preempt_and_acquire_emergency_locks(run_id, workflow["locks"], actor)
            else:
                self._acquire_locks(run_id, workflow["locks"])
        except RuntimeError as exc:
            self._set_run_status(run_id, "FAILED", error=str(exc))
            self.append_audit(
                "workflow.lock.denied",
                actor.actor_id,
                run_id,
                {"locks": workflow["locks"], "error": str(exc)},
                severity="warning",
            )
            return
        results: dict[str, Any] = {}
        completed: set[str] = set()
        degraded_steps: list[str] = []
        rollback_permitted = True
        workflow_started = time.monotonic()
        try:
            active_digest_before = (
                self.gateway.active_pointer().get("metadata_sha256")
                if self.gateway.operational
                else self.get_meta("simulation_active_model_digest") or self.gateway.active_pointer().get("metadata_sha256")
            )
        except Exception:
            active_digest_before = self.get_meta("simulation_active_model_digest")
        self._set_run_status(run_id, "RUNNING")
        self.append_audit("workflow.started", actor.actor_id, run_id, {"workflow_id": workflow["id"]})
        try:
            pending = list(workflow["steps"])
            while pending:
                ready = [step for step in pending if set(step["depends_on"]) <= completed]
                if not ready:
                    raise RuntimeError("workflow dependency graph could not make progress")
                for step in ready:
                    if self.get_run(run_id)["status"] == "CANCELLED":
                        raise RuntimeError("workflow was cancelled before the next step")
                    step_id = step["id"]
                    arguments = self._resolve_arguments(step["arguments"], parameters, run_id)
                    with self._connect() as db:
                        db.execute(
                            "INSERT INTO workflow_steps(run_id, step_id, action_id, status, started_at_utc) VALUES (?, ?, ?, ?, ?)",
                            (run_id, step_id, step["action"], "RUNNING", _utc_text()),
                        )
                    self.append_audit("workflow.step.started", actor.actor_id, run_id, {"step_id": step_id, "action": step["action"]})
                    retry = step["retry"]
                    result: dict[str, Any] | None = None
                    last_error: Exception | None = None
                    for attempt in range(1, int(retry["max_attempts"]) + 1):
                        elapsed = time.monotonic() - workflow_started
                        remaining = float(workflow["timeout_seconds"]) - elapsed
                        if remaining <= 0:
                            last_error = TimeoutError(f"workflow exceeded its {workflow['timeout_seconds']}s execution deadline")
                            break
                        try:
                            result = self._execute_action_bounded(
                                step["action"], arguments, run_id, actor,
                                min(float(step["timeout_seconds"]), remaining),
                            )
                            last_error = None
                            break
                        except Exception as exc:
                            last_error = exc
                            self.append_audit(
                                "workflow.step.attempt_failed",
                                actor.actor_id,
                                run_id,
                                {"step_id": step_id, "action": step["action"], "attempt": attempt, "error": str(exc)},
                                severity="warning",
                            )
                            if attempt < int(retry["max_attempts"]):
                                delay = min(float(retry["backoff_seconds"]), max(0.0, remaining))
                                if delay:
                                    time.sleep(delay)
                    if last_error is not None or result is None:
                        with self._connect() as db:
                            db.execute(
                                "UPDATE workflow_steps SET status = ?, completed_at_utc = ?, error = ? WHERE run_id = ? AND step_id = ?",
                                ("FAILED", _utc_text(), str(last_error), run_id, step_id),
                            )
                        if step["on_failure"] == "continue_degraded":
                            degraded_steps.append(step_id)
                            completed.add(step_id)
                            pending.remove(step)
                            continue
                        rollback_permitted = step["on_failure"] == "rollback"
                        raise last_error or RuntimeError(f"step {step_id} failed")
                    if self.get_run(run_id)["status"] == "CANCELLED":
                        if step["action"].startswith("pipeline.") and self.gateway.operational:
                            self.gateway.stop_pipeline(emergency=True)
                        raise RuntimeError("workflow was cancelled during action execution")
                    results[step_id] = result
                    with self._connect() as db:
                        db.execute(
                            "UPDATE workflow_steps SET status = ?, completed_at_utc = ?, result_json = ? WHERE run_id = ? AND step_id = ?",
                            ("COMPLETED", _utc_text(), _canonical(result), run_id, step_id),
                        )
                    self.append_audit(
                        "workflow.step.completed",
                        actor.actor_id,
                        run_id,
                        {"step_id": step_id, "action": step["action"], "result": result},
                    )
                    completed.add(step_id)
                    pending.remove(step)
            self._apply_workflow_outcome(workflow["id"])
            facts = self._postcondition_facts(workflow, results, active_digest_before)
            for condition in workflow["postconditions"]:
                subject = condition["subject"]
                if subject not in facts:
                    raise RuntimeError(f"no postcondition adapter exists for {subject}")
                if not self._condition_matches(facts[subject], condition["operator"], condition["expected"]):
                    raise RuntimeError(
                        f"postcondition failed: {subject} {condition['operator']} {condition['expected']!r}; observed {facts[subject]!r}"
                    )
            if degraded_steps:
                self.set_meta("platform_state", "DEGRADED")
            execution_result = {"steps": results, "postconditions": facts, "degraded_steps": degraded_steps}
            self._set_run_status(run_id, "COMPLETED", result=execution_result)
            self.append_audit("workflow.completed", actor.actor_id, run_id, {"status": "COMPLETED", "postconditions": facts, "degraded_steps": degraded_steps})
        except Exception as exc:
            if self.get_run(run_id)["status"] == "CANCELLED":
                with self._connect() as db:
                    db.execute(
                        "UPDATE workflow_steps SET status = ?, completed_at_utc = ?, error = ? "
                        "WHERE run_id = ? AND status = 'RUNNING'",
                        ("CANCELLED", _utc_text(), "cancelled by authorised actor", run_id),
                    )
                self.append_audit(
                    "workflow.cancelled",
                    actor.actor_id,
                    run_id,
                    {"while_running": True, "adapter_error": str(exc)},
                    severity="warning",
                )
                return
            rollback_results: list[dict[str, Any]] = []
            rollback_failed = False
            for rollback in reversed(workflow.get("rollback", []) if rollback_permitted else []):
                try:
                    arguments = self._resolve_arguments(rollback["arguments"], parameters, run_id)
                    rollback_results.append(
                        {
                            "action": rollback["action"],
                            "result": self._execute_action_bounded(
                                rollback["action"], arguments, run_id, actor, float(rollback["timeout_seconds"])
                            ),
                        }
                    )
                except Exception as rollback_exc:  # pragma: no cover - retained for audit completeness
                    rollback_failed = True
                    rollback_results.append({"action": rollback["action"], "error": str(rollback_exc)})
            status = "FAILED" if rollback_failed or not workflow.get("rollback") or not rollback_permitted else "ROLLED_BACK"
            self._set_run_status(run_id, status, result={"rollback": rollback_results}, error=str(exc))
            self.append_audit(
                "workflow.failed",
                actor.actor_id,
                run_id,
                {"status": status, "error": str(exc), "rollback": rollback_results},
                severity="error",
            )
        finally:
            self._release_locks(run_id)

    def _apply_workflow_outcome(self, workflow_id: str) -> None:
        state = {
            "preflight": "PREFLIGHT",
            "start_detection": "RUNNING",
            "start_live_sdr": "RUNNING",
            "rerun_live_sdr": "RUNNING",
            "stop_detection_gracefully": "STOPPED",
            "emergency_stop": "FAILED",
            "enter_maintenance": "MAINTENANCE",
            "leave_maintenance": "STOPPED",
        }.get(workflow_id)
        if state:
            self.set_meta("platform_state", state)

    def _runtime_approval_binding(self, run_id: str) -> str:
        """Bind high-risk execution to exact runtime facts and distinct approvals."""

        run = self.get_run(run_id)
        workflow = self.workflows[run["workflow_id"]]
        policy = workflow["approval_policy"]
        approvals = [item for item in run["approvals"] if item["decision"] == "approve"]
        mode = policy["mode"]
        created = datetime.fromisoformat(run["created_at_utc"].replace("Z", "+00:00"))
        if mode in ("two_person", "single_operator"):
            if created + timedelta(seconds=policy["approval_ttl_seconds"]) <= _utc_now():
                raise PermissionError("runtime approval binding has expired")
        if mode == "two_person":
            identities = {item["actor_id"] for item in approvals}
            if len(identities) < 2 or run["actor_id"] in identities:
                raise PermissionError("two distinct non-requester approvals are required")
        elif mode == "single_operator":
            # Belt-and-suspenders re-check, independent of the one already applied in
            # approve_run: this is the last gate before the action actually executes, so
            # it re-derives everything from the recorded approval rather than trusting
            # that approve_run's checks were never bypassed by a direct data change.
            own_approval = next(
                (item for item in approvals if item["actor_id"] == run["actor_id"]), None
            )
            if own_approval is None:
                raise PermissionError("single-operator approval requires the requester's own recorded approval")
            minimum_wait = policy.get("minimum_deliberation_seconds", 0)
            decided_at = datetime.fromisoformat(own_approval["decided_at_utc"].replace("Z", "+00:00"))
            if decided_at < created + timedelta(seconds=minimum_wait):
                raise PermissionError(
                    "single-operator approval was recorded before the required deliberation gap elapsed"
                )
            if own_approval.get("acknowledged_parameters_digest") != canonical_digest(run["parameters"]):
                raise PermissionError("single-operator approval is not bound to the current parameters digest")
        profile_evidence = None
        profile_id = run["parameters"].get("profile_id")
        if profile_id:
            profile_path = (self.repo_root / "configs" / "rf_profiles" / f"{profile_id}.yaml").resolve()
            profiles_root = (self.repo_root / "configs" / "rf_profiles").resolve()
            if not profile_path.is_relative_to(profiles_root) or not profile_path.is_file():
                raise PermissionError("runtime RF profile evidence is unavailable")
            profile_evidence = {"path": str(profile_path.relative_to(self.repo_root)), "sha256": _sha256_file(profile_path)}
        return canonical_digest(
            {
                "run_id": run_id,
                "workflow_id": run["workflow_id"],
                "workflow_version": run["workflow_version"],
                "workflow_digest": run["workflow_digest"],
                "parameters": run["parameters"],
                "environment": self.project()["environment"],
                "requester": run["actor_id"],
                "reason": run["reason"],
                "reference": run["reference"],
                "approvals": approvals,
                "profile_evidence": profile_evidence,
            }
        )

    def _execute_action(self, action_id: str, arguments: dict[str, Any], run_id: str, actor: Actor) -> dict[str, Any]:
        if action_id == "config.validate":
            profile = arguments["profile"]
            if profile not in {"simulation", "replay", "live_sdr"}:
                raise RuntimeError("control profile is not allowlisted")
            paths = [self.project_path, self.repo_root / "config" / "system.yaml", self.registry_path]
            return {
                "status": "PASS",
                "profile": profile,
                "artifacts": [
                    {"path": str(path.relative_to(self.repo_root)), "sha256": _sha256_file(path)} for path in paths
                ],
            }
        if action_id == "state.reconcile":
            target = arguments["target"]
            if target not in {"STOPPED", "MAINTENANCE"}:
                raise RuntimeError("state reconciliation target is not allowlisted")
            self.set_meta("platform_state", target)
            return {"state": target, "adapter": "simulation"}
        if action_id == "health.collect":
            return {"overall_status": self.health_snapshot()["overall_status"], "adapter": "local_read_only"}
        if action_id == "pipeline.start":
            profile = arguments["profile"]
            if profile == "replay":
                result = self.gateway.start_pipeline("replay", replay_session=arguments.get("replay_session"))
                services = {
                    name: item["status"] for name, item in result["services"].items()
                }
                services.update({"storage": "HEALTHY", "dashboard": "HEALTHY"})
                self.set_meta("simulation_services", services)
                self.set_meta("detection_mode", "REPLAY")
                return result
            if profile != "simulation":
                raise RuntimeError("use the separate approval-gated live SDR workflow")
            services = {name: "RUNNING" for name in self.get_meta("simulation_services")}
            services["storage"] = "HEALTHY"
            services["dashboard"] = "HEALTHY"
            self.set_meta("simulation_services", services)
            self.set_meta("detection_mode", "SIMULATION")
            return {"mode": "SIMULATION", "services": services, "rf_transmission": False}
        if action_id == "pipeline.start_live_sdr":
            approval_binding = self._runtime_approval_binding(run_id)
            result = self.gateway.start_pipeline(
                "live_sdr",
                profile_id=arguments["profile_id"],
                tx_gain_db=float(arguments["tx_gain_db"]),
                rx_gain_db=float(arguments["rx_gain_db"]),
                maximum_seconds=int(arguments["maximum_duration_seconds"]),
            )
            self.set_meta("detection_mode", "LIVE_SDR")
            self.set_meta("last_rf_approval_binding", approval_binding)
            return {**result, "approval_binding_sha256": approval_binding}
        if action_id == "pipeline.stop":
            operational = self.gateway.stop_pipeline(emergency=False) if self.gateway.operational else None
            services = {name: "STOPPED" for name in self.get_meta("simulation_services")}
            services["storage"] = "HEALTHY"
            services["dashboard"] = "HEALTHY"
            self.set_meta("simulation_services", services)
            self.set_meta("detection_mode", "DISABLED")
            return {"services": services, "operational": operational, "reason": arguments["reason"]}
        if action_id == "pipeline.emergency_stop":
            operational = self.gateway.stop_pipeline(emergency=True) if self.gateway.operational else None
            services = {name: "STOPPED" for name in self.get_meta("simulation_services")}
            services["storage"] = "HEALTHY"
            services["dashboard"] = "HEALTHY"
            self.set_meta("simulation_services", services)
            self.set_meta("platform_state", "FAILED")
            self.set_meta("detection_mode", "DISABLED")
            return {"services": services, "operational": operational, "rf_stopped": True, "reason": arguments["reason"]}
        if action_id == "data.capture_raw_iq":
            binding = self._runtime_approval_binding(run_id)
            result = self.gateway.capture_raw_iq(
                session_id=arguments["session_id"],
                activity_class=arguments["activity_class"],
                duration_seconds=int(arguments["duration_seconds"]),
                note=arguments["note"],
                occupancy=arguments["occupancy"],
                room=arguments["room"],
                job_id=run_id,
            )
            return {**result, "approval_binding_sha256": binding}
        if action_id == "model.train_candidate":
            if self.gateway.operational:
                return self.gateway.train_candidate(
                    arguments["candidate_id"],
                    arguments["dataset_manifest"],
                    job_id=run_id,
                )
            return self._create_simulation_candidate("training", None, arguments["dataset_manifest"], run_id, actor)
        if action_id == "model.evaluate_candidate":
            if self.gateway.operational:
                return self.gateway.evaluate_candidate(
                    arguments["candidate_id"],
                    arguments["dataset_manifest"],
                    job_id=run_id,
                )
            return {
                "candidate_id": arguments["candidate_id"],
                "status": "SIMULATION_ONLY",
                "active_model_changed": False,
            }
        if action_id == "model.recalibrate_candidate":
            if self.gateway.operational:
                return self.gateway.generate_threshold_study(arguments["candidate_id"], job_id=run_id)
            return {
                "candidate_id": arguments["candidate_id"],
                "status": "SIMULATION_ONLY",
                "active_model_changed": False,
            }
        if action_id == "model.rollback":
            digest = arguments["approved_model_digest"]
            known = {artifact for model in self.model_catalog() for artifact in model.get("artifact_sha256", {}).values()}
            known_metadata = {model.get("metadata_sha256") for model in self.model_catalog()}
            if digest not in known and digest not in known_metadata:
                raise RuntimeError("rollback digest is not present in the immutable model catalog")
            if self.gateway.operational:
                binding = self._runtime_approval_binding(run_id)
                return self.gateway.rollback_model(
                    digest,
                    arguments["expected_active_digest"],
                    actor_id=actor.actor_id,
                    approval_binding=binding,
                )
            self.set_meta("simulation_active_model_digest", digest)
            return {"simulation_active_model_digest": digest, "active_model_files_changed": False}
        if action_id == "model.promote":
            binding = self._runtime_approval_binding(run_id)
            return self.gateway.promote_model(
                arguments["model_id"],
                arguments["expected_active_digest"],
                actor_id=actor.actor_id,
                approval_binding=binding,
            )
        if action_id == "rf.conducted_bounded_test":
            raise RuntimeError("use the bounded start_live_sdr workflow; direct RF tools are never exposed")
        raise RuntimeError(f"no typed control adapter exists for {action_id}")

    def _create_simulation_candidate(
        self,
        kind: str,
        base_digest: str | None,
        dataset_ref: str,
        run_id: str,
        actor: Actor,
    ) -> dict[str, Any]:
        if Path(dataset_ref).is_absolute() or ".." in Path(dataset_ref).parts:
            raise RuntimeError("dataset reference must remain repository relative")
        source = (self.repo_root / dataset_ref).resolve()
        if not source.is_relative_to(self.repo_root) or not source.exists() or source.suffix != ".json":
            raise RuntimeError("dataset manifest does not exist or is not a JSON artifact")
        candidate_id = f"simulation-{kind}-{run_id[:8]}"
        metadata = {
            "candidate_id": candidate_id,
            "kind": kind,
            "base_digest": base_digest,
            "dataset_ref": dataset_ref,
            "dataset_sha256": _sha256_file(source),
            "deployment_status": "SIMULATED_CANDIDATE",
            "promotion_eligible": False,
            "performance_gate_passed": False,
            "active_model_files_changed": False,
        }
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO simulation_candidates(
                  candidate_id, kind, base_digest, dataset_ref, created_by,
                  created_at_utc, status, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (candidate_id, kind, base_digest, dataset_ref, actor.actor_id, _utc_text(), "SIMULATED", _canonical(metadata)),
            )
        return metadata

    def approve_run(self, run_id: str, request: WorkflowApprovalRequest, actor: Actor) -> dict[str, Any]:
        self.require_scopes(actor, {"workflow:approve"})
        run = self.get_run(run_id)
        if run["status"] != "AWAITING_APPROVAL":
            raise RuntimeError("run is not awaiting approval")
        policy = self.workflows[run["workflow_id"]]["approval_policy"]
        mode = policy["mode"]
        created_at = datetime.fromisoformat(run["created_at_utc"].replace("Z", "+00:00"))
        if created_at + timedelta(seconds=policy["approval_ttl_seconds"]) <= _utc_now():
            self._set_run_status(run_id, "CANCELLED", error="approval window expired")
            raise RuntimeError("approval window expired")
        if mode == "two_person":
            if run["actor_id"] == actor.actor_id:
                raise PermissionError("the requester cannot approve their own two-person workflow")
        elif mode == "single_operator":
            # The requester IS the expected approver here -- that is the entire point of
            # this mode -- but the approval must still be a genuinely separate, later,
            # informed act: a real deliberation gap, and a fresh look at the exact
            # parameters, not the same click that made the request.
            minimum_wait = policy.get("minimum_deliberation_seconds", 0)
            earliest = created_at + timedelta(seconds=minimum_wait)
            if _utc_now() < earliest:
                remaining = (earliest - _utc_now()).total_seconds()
                raise PermissionError(
                    f"single-operator approval requires a {minimum_wait}s deliberation gap; "
                    f"{remaining:.0f}s remaining before this request may be approved"
                )
            current_digest = canonical_digest(run["parameters"])
            if request.acknowledged_parameters_digest != current_digest:
                raise PermissionError(
                    "single-operator approval must re-acknowledge the exact current parameters digest "
                    "(fetch the run detail immediately before approving; the digest changes if the run does)"
                )
        with self._connect() as db:
            db.execute(
                "INSERT INTO approvals(run_id, actor_id, decision, reason, decided_at_utc, acknowledged_parameters_digest) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    actor.actor_id,
                    request.decision,
                    request.reason,
                    _utc_text(),
                    request.acknowledged_parameters_digest,
                ),
            )
        self.append_audit(
            "workflow.approval.decided",
            actor.actor_id,
            run_id,
            {"decision": request.decision, "reason": request.reason, "mode": mode},
        )
        if request.decision == "reject":
            self._set_run_status(run_id, "CANCELLED", error="approval rejected")
            return self.get_run(run_id)
        required_distinct_approvals = 1 if mode == "single_operator" else 2
        should_dispatch = False
        with self._mutex, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            approvals = db.execute(
                "SELECT COUNT(DISTINCT actor_id) AS count FROM approvals WHERE run_id = ? AND decision = 'approve'",
                (run_id,),
            ).fetchone()["count"]
            if approvals >= required_distinct_approvals:
                claimed = db.execute(
                    "UPDATE workflow_runs SET status = ?, updated_at_utc = ? "
                    "WHERE run_id = ? AND status = 'AWAITING_APPROVAL'",
                    ("QUEUED", _utc_text(), run_id),
                )
                should_dispatch = claimed.rowcount == 1
            db.commit()
        if should_dispatch:
            workflow = self.workflows[run["workflow_id"]]
            requester = self._current_actor(run["actor_id"])
            self.require_scopes(requester, workflow["required_scopes"])
            self._dispatch_run(run_id, workflow, run["parameters"], requester)
        return self.get_run(run_id)

    def cancel_run(self, run_id: str, actor: Actor) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run["actor_id"] != actor.actor_id and "workflow:cancel_any" not in actor.scopes:
            raise PermissionError("only the requester or an authorised administrator may cancel this run")
        if run["status"] in TERMINAL_RUN_STATES:
            return run
        if run["status"] == "RUNNING":
            if not self.gateway.job_running(run_id):
                raise RuntimeError("the running workflow is not at a cancellable gateway operation")
            self._set_run_status(run_id, "CANCELLED")
            self.gateway.cancel_job(run_id)
        else:
            self._set_run_status(run_id, "CANCELLED")
        self._release_locks(run_id)
        self.append_audit("workflow.cancelled", actor.actor_id, run_id, {})
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM workflow_runs WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                raise KeyError("unknown workflow run")
            steps = db.execute(
                "SELECT * FROM workflow_steps WHERE run_id = ? ORDER BY started_at_utc, step_id", (run_id,)
            ).fetchall()
            approvals = db.execute(
                "SELECT actor_id, decision, reason, decided_at_utc, acknowledged_parameters_digest "
                "FROM approvals WHERE run_id = ? ORDER BY decided_at_utc",
                (run_id,),
            ).fetchall()
        return {
            "run_id": row["run_id"],
            "workflow_id": row["workflow_id"],
            "workflow_version": row["workflow_version"],
            "workflow_digest": row["workflow_digest"],
            "actor_id": row["actor_id"],
            "status": row["status"],
            "parameters": json.loads(row["parameters_json"]),
            "dry_run": bool(row["dry_run"]),
            "idempotency_key": row["idempotency_key"],
            "reason": row["reason"],
            "reference": row["reference"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error": row["error"],
            "created_at_utc": row["created_at_utc"],
            "updated_at_utc": row["updated_at_utc"],
            "steps": [
                {
                    "step_id": step["step_id"],
                    "action": step["action_id"],
                    "status": step["status"],
                    "started_at_utc": step["started_at_utc"],
                    "completed_at_utc": step["completed_at_utc"],
                    "result": json.loads(step["result_json"]) if step["result_json"] else None,
                    "error": step["error"],
                }
                for step in steps
            ],
            "approvals": [dict(approval) for approval in approvals],
            **self._approval_status_fields(row),
        }

    def _approval_status_fields(self, row: sqlite3.Row) -> dict[str, Any]:
        """Surface the exact digest an approver must re-acknowledge, and the earliest
        moment a single_operator approval is allowed, so the API never depends on a
        client already having the right values in hand."""

        parameters = json.loads(row["parameters_json"])
        digest = canonical_digest(parameters)
        workflow = self.workflows.get(row["workflow_id"])
        fields: dict[str, Any] = {"parameters_digest": digest}
        if workflow is None:
            return fields
        policy = workflow["approval_policy"]
        fields["approval_mode"] = policy["mode"]
        if policy["mode"] == "single_operator" and row["status"] == "AWAITING_APPROVAL":
            created_at = datetime.fromisoformat(row["created_at_utc"].replace("Z", "+00:00"))
            earliest = created_at + timedelta(seconds=policy.get("minimum_deliberation_seconds", 0))
            fields["single_operator_approval"] = {
                "acknowledged_parameters_digest_required": digest,
                "earliest_approval_at_utc": _utc_text(earliest),
                "deliberation_remaining_seconds": max(0.0, (earliest - _utc_now()).total_seconds()),
            }
        return fields

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as db:
            ids = db.execute(
                "SELECT run_id FROM workflow_runs ORDER BY created_at_utc DESC LIMIT ?", (max(1, min(limit, 500)),)
            ).fetchall()
        return [self.get_run(row["run_id"]) for row in ids]

    def project(self) -> dict[str, Any]:
        config = yaml.safe_load(self.project_path.read_text(encoding="utf-8"))["project"]
        return {
            "display_name": config["display_name"],
            "slug": config["slug"],
            "environment": config["active_environment"],
            "naming_status": config["naming_status"],
            "governing_framework": config["governing_framework"],
            "config_digest": _sha256_file(self.project_path),
        }

    def platform_state(self) -> dict[str, Any]:
        project = self.project()
        services = self.get_meta("simulation_services")
        operational_services = self.gateway.service_status() if self.gateway.operational else {}
        external_services = self.gateway.external_service_status() if self.gateway.operational else {}
        current_state = self.get_meta("platform_state")
        detection_mode = self.get_meta("detection_mode")
        runtime_model_override = None
        if external_services:
            signature = _sha256_bytes(
                _canonical(
                    {
                        name: {
                            "pid": item.get("pid"),
                            "create_time": item.get("create_time"),
                            "argv_digest": item.get("argv_digest"),
                        }
                        for name, item in external_services.items()
                    }
                ).encode()
            )
            current_state = "DEGRADED"
            detection_mode = "LEGACY_LIVE_SDR_UNMANAGED"
            self.set_meta("platform_state", current_state)
            self.set_meta("detection_mode", detection_mode)
            if self.get_meta("external_pipeline_signature") != signature:
                self.set_meta("external_pipeline_signature", signature)
                self.append_audit(
                    "pipeline.external.detected",
                    None,
                    None,
                    {
                        "services": {
                            name: {"pid": item.get("pid"), "status": item.get("status")}
                            for name, item in external_services.items()
                        },
                        "reconciled_state": current_state,
                    },
                    severity="warning",
                )
            runtime_model_override = external_services.get("inference", {}).get("runtime_model_dir")
        elif detection_mode == "LEGACY_LIVE_SDR_UNMANAGED":
            current_state = "FAILED"
            detection_mode = "DISABLED"
            self.set_meta("platform_state", current_state)
            self.set_meta("detection_mode", detection_mode)
            self.set_meta("external_pipeline_signature", None)
            self.append_audit(
                "pipeline.external.exited",
                None,
                None,
                {"reconciled_state": current_state},
                severity="warning",
            )
        if (
            self.gateway.operational
            and current_state == "RUNNING"
            and detection_mode in {"REPLAY", "LIVE_SDR"}
            and operational_services.get("acquisition", {}).get("status") != "RUNNING"
        ):
            self.gateway.stop_pipeline(emergency=False)
            current_state = "STOPPED" if detection_mode == "LIVE_SDR" else "FAILED"
            self.set_meta("platform_state", current_state)
            self.set_meta("detection_mode", "DISABLED")
            self.append_audit(
                "pipeline.source.exited",
                None,
                None,
                {"mode": detection_mode, "reconciled_state": current_state},
                severity="warning",
            )
            detection_mode = "DISABLED"
            operational_services = self.gateway.service_status()
        if operational_services:
            services = {
                **services,
                **{name: item["status"] for name, item in operational_services.items()},
            }
        if external_services:
            services = {
                **services,
                **{name: item["status"] for name, item in external_services.items()},
            }
        runs = self.list_runs(limit=1)
        active_model = self.gateway.active_pointer()
        return {
            "api_version": "v1",
            "project": project,
            "state": current_state,
            "mode": detection_mode,
            "control_plane_status": "DEVELOPMENT_TYPED_OPERATIONAL" if self.gateway.operational else "DEVELOPMENT_SIMULATION_ONLY",
            "services": services,
            "active_locks": self.active_locks(),
            "last_workflow": runs[0] if runs else None,
            "rf_transmission_enabled": self.gateway.operational,
            "privileged_helper_connected": False,
            "privileged_helper_kind": "LOCAL_FIXED_ARGV_GATEWAY" if self.gateway.operational else None,
            "active_model_mutation_enabled": self.gateway.operational,
            "active_model": active_model,
            "runtime_model_override": runtime_model_override,
            "external_services": {
                name: {
                    "pid": item.get("pid"),
                    "status": item.get("status"),
                    "supervision": item.get("supervision"),
                }
                for name, item in external_services.items()
            },
            "clinical_alerting_enabled": False,
            "updated_at_utc": _utc_text(),
        }

    def active_locks(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT resource_id, run_id, acquired_at_utc FROM resource_locks ORDER BY resource_id").fetchall()
        return [dict(row) for row in rows]

    def host_health(self) -> dict[str, Any]:
        observed = _utc_text()
        virtual = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_usage(str(self.repo_root))
        network = psutil.net_io_counters()
        temperatures = psutil.sensors_temperatures(fahrenheit=False) if hasattr(psutil, "sensors_temperatures") else {}
        temperature_values = [entry.current for entries in temperatures.values() for entry in entries if entry.current is not None]
        affinity = psutil.Process().cpu_affinity() if hasattr(psutil.Process(), "cpu_affinity") else list(range(psutil.cpu_count() or 1))
        return {
            "subject_type": "host",
            "subject_id": platform.node() or "local-host",
            "status": "HEALTHY" if disk.percent < 90 and virtual.percent < 95 else "DEGRADED",
            "observed_at_utc": observed,
            "source": "PSUTIL",
            "cpu": {
                "physical_cores": psutil.cpu_count(logical=False),
                "logical_cpus": psutil.cpu_count(logical=True),
                "available_cpus": len(affinity),
                "affinity": affinity,
                "per_core_percent": psutil.cpu_percent(interval=None, percpu=True),
                "load_average": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
            },
            "memory": {"total_bytes": virtual.total, "available_bytes": virtual.available, "percent": virtual.percent},
            "swap": {"total_bytes": swap.total, "used_bytes": swap.used, "percent": swap.percent},
            "disk": {"total_bytes": disk.total, "free_bytes": disk.free, "percent": disk.percent},
            "network": {"bytes_sent": network.bytes_sent, "bytes_recv": network.bytes_recv, "packets_sent": network.packets_sent, "packets_recv": network.packets_recv},
            "temperature_c": max(temperature_values) if temperature_values else None,
            "process": {"pid": os.getpid(), "rss_bytes": psutil.Process().memory_info().rss, "threads": psutil.Process().num_threads()},
        }

    def service_health(self) -> dict[str, Any]:
        services = self.get_meta("simulation_services")
        operational = self.gateway.service_status() if self.gateway.operational else {}
        external = self.gateway.external_service_status() if self.gateway.operational else {}
        if operational or external:
            items = [
                {
                    "service_id": name,
                    "status": item["status"],
                    "mode": "SUPERVISED_PROCESS",
                    "pid": item.get("pid"),
                    "rss_bytes": item.get("rss_bytes"),
                    "cpu_percent": item.get("cpu_percent"),
                    "log_path": item.get("log_path"),
                }
                for name, item in operational.items()
            ]
            items.extend(
                {
                    "service_id": name,
                    "status": item["status"],
                    "mode": "DISCOVERED_LEGACY_PROCESS",
                    "pid": item.get("pid"),
                    "rss_bytes": item.get("rss_bytes"),
                    "cpu_percent": item.get("cpu_percent"),
                    "runtime_model_dir": item.get("runtime_model_dir"),
                }
                for name, item in external.items()
                if name not in operational
            )
            items.extend(
                {"service_id": name, "status": status, "mode": "CONTROL_PLANE"}
                for name, status in services.items()
                if name not in operational and name not in external
            )
            return {
                "observed_at_utc": _utc_text(),
                "source": "TYPED_PROCESS_GATEWAY_AND_DISCOVERY",
                "status": "HEALTHY" if all(item["status"] in {"RUNNING", "HEALTHY", "STOPPED"} for item in items) else "DEGRADED",
                "services": items,
            }
        return {
            "observed_at_utc": _utc_text(),
            "source": "CONTROL_PLANE_SIMULATION_STATE",
            "status": "HEALTHY" if all(value in {"RUNNING", "HEALTHY", "STOPPED"} for value in services.values()) else "DEGRADED",
            "services": [
                {"service_id": name, "status": status, "mode": "SIMULATION"} for name, status in services.items()
            ],
        }

    def usrp_health(self) -> dict[str, Any]:
        system = yaml.safe_load((self.repo_root / "config" / "system.yaml").read_text(encoding="utf-8"))
        usrp = system["usrp"]
        return {
            "subject_type": "usrp",
            "subject_id": "n210_primary",
            "status": "UNKNOWN",
            "observed_at_utc": _utc_text(),
            "live_probe_performed": False,
            "live_access_enabled": self.gateway.operational,
            "identity_source": "CONFIG_AND_ARCHIVED_PROBE_NOT_LIVE_TELEMETRY",
            "configured_identity": {
                "serial": usrp.get("serial"),
                "mboard": usrp.get("mboard"),
                "firmware_version": usrp.get("fw_version"),
                "fpga_version": usrp.get("fpga_version"),
                "daughterboard": usrp.get("daughterboard"),
            },
            "configured_runtime": {
                "frequency_hz": system["carrier"]["f0_hz"],
                "sample_rate_hz": system["sample_rates"]["capture_hz"],
                "tx_gain_db": system["gains"]["tx_gain_db"],
                "rx_gain_db": system["gains"]["rx_gain_db"],
                "tx_port": system["antenna"]["tx_port_antenna"],
                "rx_port": system["antenna"]["rx_port_antenna"],
            },
            "runtime_counters": {"availability": "unavailable", "reason": "no acquisition telemetry adapter is connected"},
            "unavailable_on_device": {
                "cpu_utilisation": None,
                "ram_utilisation": None,
                "process_list": None,
                "filesystem_utilisation": None,
            },
            "last_live_probe": self.get_meta("last_usrp_probe"),
            "warning": "Configured and archived identity is not current live health. Use the stopped-state registered probe for a current observation.",
        }

    def flowgraph_topology(self) -> dict[str, Any]:
        """Describe the deployed GNU Radio top block and its downstream graph."""

        system = yaml.safe_load((self.repo_root / "config" / "system.yaml").read_text(encoding="utf-8"))
        profile_path = self.repo_root / "configs" / "rf_profiles" / "lab_cw_2462.yaml"
        profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        managed = self.gateway.service_status() if self.gateway.operational else {}
        external = self.gateway.external_service_status() if self.gateway.operational else {}
        observed = external or managed
        acquisition_argv = observed.get("acquisition", {}).get("argv", [])

        def argv_value(flag: str, fallback: float) -> float:
            try:
                return float(acquisition_argv[acquisition_argv.index(flag) + 1])
            except (ValueError, IndexError, TypeError):
                return fallback

        tx_gain = argv_value("--tx-gain", float(system["gains"].get("tx_gain_db") or 0))
        rx_gain = argv_value("--rx-gain", float(system["gains"].get("rx_gain_db") or 20))
        nodes = [
            {
                "id": "constant_source",
                "group": "GNU Radio top block",
                "kind": "analog.sig_source_c",
                "label": "Constant complex source",
                "description": "Generates a unit-amplitude constant complex waveform for CW transmission.",
                "status": observed.get("acquisition", {}).get("status", "STOPPED"),
                "parameters": [
                    {"id": "waveform", "label": "Waveform", "value": "GR_CONST_WAVE", "editable": False, "reason": "Bound by the reviewed CW sensing profile."},
                    {"id": "amplitude", "label": "Amplitude", "value": 1.0, "editable": False, "reason": "Digital full-scale is fixed; RF power is controlled by TX gain."},
                ],
            },
            {
                "id": "usrp_sink",
                "group": "GNU Radio top block",
                "kind": "uhd.usrp_sink",
                "label": "N210 RF transmitter",
                "description": "Tunes the N210 TX chain and sends the constant envelope through RF1 TX/RX.",
                "status": observed.get("acquisition", {}).get("status", "STOPPED"),
                "parameters": [
                    {"id": "device", "label": "Device", "value": system["usrp"]["addr"], "editable": False, "reason": "Hardware identity is configuration-bound."},
                    {"id": "centre_frequency_hz", "label": "Centre frequency", "value": profile["centre_frequency_hz"], "unit": "Hz", "editable": False, "reason": "Frequency is locked to the reviewed RF profile."},
                    {"id": "sample_rate_hz", "label": "Sample rate", "value": profile["sample_rate_hz"], "unit": "S/s", "editable": False, "reason": "The downstream model and DSP contract are trained at this rate."},
                    {"id": "tx_gain_db", "label": "TX gain", "value": tx_gain, "unit": "dB", "editable": True, "minimum": 0, "maximum": profile["maximum_tx_gain_db"], "step": 1},
                    {"id": "tx_port", "label": "Antenna port", "value": profile["tx_port"], "editable": False, "reason": "Physical antenna inventory binding."},
                ],
            },
            {
                "id": "usrp_source",
                "group": "GNU Radio top block",
                "kind": "uhd.usrp_source",
                "label": "N210 RF receiver",
                "description": "Receives reflected complex baseband samples from RF2 RX2.",
                "status": observed.get("acquisition", {}).get("status", "STOPPED"),
                "parameters": [
                    {"id": "centre_frequency_hz", "label": "Centre frequency", "value": profile["centre_frequency_hz"], "unit": "Hz", "editable": False, "reason": "Co-tuned with the transmitter profile."},
                    {"id": "sample_rate_hz", "label": "Sample rate", "value": profile["sample_rate_hz"], "unit": "S/s", "editable": False, "reason": "Bound to the DSP/model feature contract."},
                    {"id": "rx_gain_db", "label": "RX gain", "value": rx_gain, "unit": "dB", "editable": True, "minimum": 0, "maximum": profile["maximum_rx_gain_db"], "step": 1},
                    {"id": "rx_port", "label": "Antenna port", "value": profile["rx_port"], "editable": False, "reason": "Physical antenna inventory binding."},
                ],
            },
            {
                "id": "zmq_iq_pub",
                "group": "GNU Radio top block",
                "kind": "zeromq.pub_sink",
                "label": "Raw IQ publisher",
                "description": "Publishes complex64 receive samples to the loopback-only DSP boundary.",
                "status": observed.get("acquisition", {}).get("status", "STOPPED"),
                "parameters": [
                    {"id": "endpoint", "label": "Endpoint", "value": "tcp://127.0.0.1:5580", "editable": False, "reason": "Internal endpoint is fixed to prevent network IQ egress."},
                    {"id": "dtype", "label": "Item type", "value": "complex64", "editable": False, "reason": "Wire-contract field."},
                ],
            },
            {
                "id": "spectrogram",
                "group": "CARAT downstream services",
                "kind": "Python DSP service",
                "label": "Clutter removal + STFT",
                "description": "Continuous DC/clutter removal, 256 ms Hann STFT, 50 ms hop and ±300 Hz Doppler crop.",
                "status": observed.get("preprocessing", {}).get("status", "STOPPED"),
                "parameters": [
                    {"id": "window_ms", "label": "STFT window", "value": 256, "unit": "ms", "editable": False, "reason": "Training/serving feature contract."},
                    {"id": "hop_ms", "label": "STFT hop", "value": 50, "unit": "ms", "editable": False, "reason": "Training/serving feature contract."},
                ],
            },
            {
                "id": "classifier",
                "group": "CARAT downstream services",
                "kind": "ONNX hierarchical inference",
                "label": "Activity classifier",
                "description": "Runs the active research model and emits typed heartbeat, state and transient events.",
                "status": observed.get("inference", {}).get("status", "STOPPED"),
                "parameters": [
                    {"id": "model_dir", "label": "Runtime model", "value": observed.get("inference", {}).get("runtime_model_dir") or self.gateway.active_pointer()["bundle_path"], "editable": False, "reason": "Model changes use the separately audited promotion workflow."},
                ],
            },
            {
                "id": "state_machine",
                "group": "CARAT downstream services",
                "kind": "Typed state aggregator",
                "label": "Posture state machine",
                "description": "Preserves uncertainty, publishes current-state heartbeats and marks fall outputs as research candidates.",
                "status": observed.get("event_aggregation", {}).get("status", "STOPPED"),
                "parameters": [],
            },
            {
                "id": "dashboard_streams",
                "group": "CARAT downstream services",
                "kind": "WebSocket bridge",
                "label": "Dashboard streams",
                "description": "Relays derived waterfall and typed activity frames to authenticated/local dashboard views.",
                "status": "HEALTHY",
                "parameters": [],
            },
        ]
        return {
            "schema_version": "1.0",
            "title": "CARAT live CW Doppler acquisition and inference graph",
            "implementation": "Python-authored GNU Radio top_block plus isolated Python services",
            "source": "sdr/cw_doppler_tx_rx.py",
            "source_sha256": _sha256_file(self.repo_root / "sdr" / "cw_doppler_tx_rx.py"),
            "profile_id": profile["profile_id"],
            "profile_sha256": _sha256_file(profile_path),
            "runtime_supervision": "DISCOVERED_LEGACY_PROCESS" if external else "SUPERVISED_PROCESS" if managed else "STOPPED",
            "nodes": nodes,
            "edges": [
                {"from": "constant_source", "to": "usrp_sink", "label": "complex CW"},
                {"from": "usrp_source", "to": "zmq_iq_pub", "label": "complex64 IQ"},
                {"from": "zmq_iq_pub", "to": "spectrogram", "label": "loopback ZMQ :5580"},
                {"from": "spectrogram", "to": "classifier", "label": "Doppler frames :5591"},
                {"from": "classifier", "to": "state_machine", "label": "typed events :5593"},
                {"from": "spectrogram", "to": "dashboard_streams", "label": "waterfall"},
                {"from": "state_machine", "to": "dashboard_streams", "label": "activity :5594"},
            ],
            "controls": {
                "workflow_id": "rerun_live_sdr",
                "tx_gain_db": tx_gain,
                "rx_gain_db": rx_gain,
                "maximum_duration_seconds": min(300, int(profile["maximum_duration_seconds"])),
                "requires_restart": True,
                "approval_mode": self.workflows["rerun_live_sdr"]["approval_policy"]["mode"],
                "reference_required": True,
            },
            "observed_at_utc": _utc_text(),
        }

    def health_snapshot(self) -> dict[str, Any]:
        host = self.host_health()
        services = self.service_health()
        usrp = self.usrp_health()
        statuses = {host["status"], services["status"], usrp["status"]}
        overall = "FAILED" if "FAILED" in statuses else "DEGRADED" if "DEGRADED" in statuses else "UNKNOWN" if "UNKNOWN" in statuses else "HEALTHY"
        return {
            "api_version": "v1",
            "snapshot_id": str(uuid.uuid4()),
            "collected_at_utc": _utc_text(),
            "overall_status": overall,
            "host": host,
            "services": services,
            "usrp": usrp,
        }

    def model_catalog(self) -> list[dict[str, Any]]:
        active_pointer = self.gateway.active_pointer()
        locations = [self.repo_root / "models" / "production"] + sorted((self.repo_root / "models" / "candidates").glob("*"))
        evaluations_by_model: dict[str, tuple[int, dict[str, Any]]] = {}
        for evaluation_path in (self.repo_root / "artifacts" / "evaluations").glob("*.json"):
            try:
                report = json.loads(evaluation_path.read_text(encoding="utf-8"))
                model_id = report.get("candidate_id", report.get("model_id"))
                if not isinstance(model_id, str):
                    continue
                modified = evaluation_path.stat().st_mtime_ns
                if model_id not in evaluations_by_model or modified > evaluations_by_model[model_id][0]:
                    evaluations_by_model[model_id] = (modified, report)
            except (OSError, ValueError):
                continue
        output: list[dict[str, Any]] = []
        for location in locations:
            metadata_path = location / "metadata.json"
            if not metadata_path.exists():
                continue
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            evaluation: dict[str, Any] | None = None
            evaluation_ref = metadata.get("evaluation_artifact")
            if isinstance(evaluation_ref, str):
                candidate = (self.repo_root / evaluation_ref).resolve()
                if candidate.is_relative_to(self.repo_root) and candidate.exists() and candidate.suffix == ".json":
                    try:
                        evaluation = json.loads(candidate.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        evaluation = None
            model_id = metadata.get("model_id", location.name)
            if evaluation is None and model_id in evaluations_by_model:
                candidate_evaluation = evaluations_by_model[model_id][1]
                bound_digest = candidate_evaluation.get("candidate_bundle", {}).get("metadata_sha256")
                if bound_digest in {None, _sha256_file(metadata_path)}:
                    evaluation = candidate_evaluation
            output.append(
                {
                    "model_id": model_id,
                    "location": str(location.relative_to(self.repo_root)),
                    "deployment_status": metadata.get("deployment_status", "UNKNOWN"),
                    "promotion_eligible": bool(metadata.get("promotion_eligible", False)),
                    "performance_gate_passed": bool(metadata.get("performance_gate_passed", False)),
                    "score_semantics": metadata.get("score_semantics"),
                    "dataset": metadata.get("dataset"),
                    "artifact_sha256": metadata.get("artifact_sha256", {}),
                    "evaluation": evaluation,
                    "limitations": metadata.get("limitations", []),
                    "metadata_sha256": _sha256_file(metadata_path),
                    "active": _sha256_file(metadata_path) == active_pointer["metadata_sha256"],
                }
            )
        with self._connect() as db:
            rows = db.execute("SELECT metadata_json FROM simulation_candidates ORDER BY created_at_utc DESC").fetchall()
        output.extend(json.loads(row["metadata_json"]) for row in rows)
        return output

    def dataset_catalog(self) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for path in sorted((self.repo_root / "data" / "processed").glob("*.parquet")):
            try:
                metadata = pq.read_metadata(path)
                schema = pq.read_schema(path)
            except Exception as exc:
                output.append({"dataset_id": path.stem, "path": str(path.relative_to(self.repo_root)), "status": "INVALID", "error": str(exc)})
                continue
            output.append(
                {
                    "dataset_id": path.stem,
                    "path": str(path.relative_to(self.repo_root)),
                    "status": "DEVELOPMENT_DERIVED_DATA",
                    "rows": metadata.num_rows,
                    "row_groups": metadata.num_row_groups,
                    "columns": schema.names,
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256_file(path),
                    "raw_iq_exposed": False,
                }
            )
        return output

    def validate_dataset(self, dataset_id: str, actor: Actor) -> dict[str, Any]:
        self.require_scopes(actor, {"data:validate"})
        matches = [item for item in self.dataset_catalog() if item["dataset_id"] == dataset_id]
        if not matches:
            raise KeyError("unknown processed dataset")
        item = matches[0]
        checks = {
            "parquet_readable": item["status"] != "INVALID",
            "non_empty": item.get("rows", 0) > 0,
            "has_session_or_group_column": any(name in set(item.get("columns", [])) for name in ("session_id", "group", "date_group")),
            "raw_iq_absent": not any("iq" in name.lower() for name in item.get("columns", [])),
        }
        status = "PASS" if all(checks.values()) else "CONDITIONAL"
        result = {"dataset_id": dataset_id, "status": status, "checks": checks, "sha256": item.get("sha256")}
        self.append_audit("dataset.validation.completed", actor.actor_id, None, result)
        return result

    def create_chat_session(self, actor: Actor, mode: str) -> dict[str, Any]:
        required = "chat:explain" if mode == "EXPLAIN" else "chat:plan"
        self.require_scopes(actor, {required})
        session_id = str(uuid.uuid4())
        with self._connect() as db:
            db.execute(
                "INSERT INTO chat_sessions(session_id, actor_id, mode, created_at_utc) VALUES (?, ?, ?, ?)",
                (session_id, actor.actor_id, mode, _utc_text()),
            )
        self.append_audit("chat.session.created", actor.actor_id, session_id, {"mode": mode})
        return {"session_id": session_id, "mode": mode, "execution_enabled": False, "terminal_enabled": False}

    def chat_message(self, session_id: str, actor: Actor, message: str) -> dict[str, Any]:
        with self._connect() as db:
            session = db.execute(
                "SELECT actor_id, mode FROM chat_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if session is None or session["actor_id"] != actor.actor_id:
            raise PermissionError("chat session is unavailable")
        mode = session["mode"]
        required = "chat:explain" if mode == "EXPLAIN" else "chat:plan"
        self.require_scopes(actor, {required})
        user_id = str(uuid.uuid4())
        with self._connect() as db:
            db.execute(
                "INSERT INTO chat_messages(message_id, session_id, role, body, created_at_utc) VALUES (?, ?, 'user', ?, ?)",
                (user_id, session_id, message, _utc_text()),
            )
        response = self._safe_chat_response(mode, message, actor)
        with self._connect() as db:
            db.execute(
                "INSERT INTO chat_messages(message_id, session_id, role, body, created_at_utc) VALUES (?, ?, 'assistant', ?, ?)",
                (str(uuid.uuid4()), session_id, _canonical(response), _utc_text()),
            )
        self.append_audit(
            "chat.message.completed",
            actor.actor_id,
            session_id,
            {"mode": mode, "message_length": len(message), "resolved_workflow": response.get("resolved_workflow")},
        )
        return response

    def _safe_chat_response(self, mode: str, message: str, actor: Actor) -> dict[str, Any]:
        lowered = message.lower()
        matches = [
            ("emergency", "emergency_stop"),
            ("live sdr", "start_live_sdr"),
            ("live rf", "start_live_sdr"),
            ("raw capture", "capture_raw_iq"),
            ("capture iq", "capture_raw_iq"),
            ("promot", "promote_model"),
            ("rollback", "rollback_model"),
            ("evaluate", "evaluate_candidate"),
            ("start", "start_detection"),
            ("stop", "stop_detection_gracefully"),
            ("health", "comprehensive_health_check"),
            ("preflight", "preflight"),
            ("train", "train_candidate_model"),
            ("recalibr", "recalibrate_candidate"),
            ("maintenance", "enter_maintenance"),
        ]
        workflow_id = next((workflow for needle, workflow in matches if needle in lowered), None)
        if mode == "EXPLAIN":
            state = self.platform_state()
            return {
                "mode": mode,
                "answer": (
                    f"The platform is {state['state']} in {state['mode']} mode. "
                    "Replay, supervised RF, raw capture, candidate operations, promotion, rollback, "
                    "and registered diagnostics are available only through their named workflow or tool controls. "
                    "Clinical alerting and arbitrary shell execution remain disabled."
                ),
                "observed_sources": ["control-plane SQLite state", "configs/project.yaml", "config/system.yaml"],
                "resolved_workflow": workflow_id,
                "execution_performed": False,
            }
        if workflow_id is None:
            return {
                "mode": mode,
                "answer": "No named allowlisted workflow matched this request. Rephrase using preflight, replay, live SDR, raw capture, stop, emergency stop, health, maintenance, train, evaluate, promote, rollback, or recalibrate.",
                "resolved_workflow": None,
                "execution_performed": False,
            }
        workflow = self.workflows[workflow_id]
        missing = sorted(set(workflow["required_scopes"]) - set(actor.scopes))
        return {
            "mode": mode,
            "answer": "A non-executing workflow plan was prepared. Use the Command Centre to review a dry-run and separately confirm it.",
            "resolved_workflow": workflow_id,
            "workflow_version": workflow["version"],
            "workflow_digest": workflow["_digest"],
            "required_scopes": workflow["required_scopes"],
            "missing_scopes": missing,
            "locks": workflow["locks"],
            "steps": [{"id": step["id"], "action": step["action"]} for step in workflow["steps"]],
            "execution_adapter": "TYPED_OPERATIONAL_GATEWAY" if self.gateway.operational else "SIMULATION_ONLY",
            "execution_performed": False,
        }

    def issue_ws_ticket(self, actor: Actor) -> dict[str, Any]:
        ticket = secrets.token_urlsafe(24)
        expires = _utc_now() + timedelta(seconds=WS_TICKET_TTL_SECONDS)
        with self._connect() as db:
            db.execute(
                "INSERT INTO ws_tickets(ticket_hash, actor_id, expires_at_utc) VALUES (?, ?, ?)",
                (_sha256_bytes(ticket.encode()), actor.actor_id, _utc_text(expires)),
            )
        return {"ticket": ticket, "expires_at_utc": _utc_text(expires)}

    def consume_ws_ticket(self, ticket: str) -> Actor:
        digest = _sha256_bytes(ticket.encode())
        with self._mutex, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                """
                SELECT t.actor_id, t.expires_at_utc, t.used_at_utc, u.display_name, u.role, u.scopes_json
                FROM ws_tickets t JOIN users u ON u.actor_id = t.actor_id
                WHERE t.ticket_hash = ? AND u.enabled = 1
                """,
                (digest,),
            ).fetchone()
            if row is None or row["used_at_utc"] is not None:
                db.rollback()
                raise PermissionError("invalid WebSocket ticket")
            expires = datetime.fromisoformat(row["expires_at_utc"].replace("Z", "+00:00"))
            if expires <= _utc_now():
                db.rollback()
                raise PermissionError("expired WebSocket ticket")
            db.execute("UPDATE ws_tickets SET used_at_utc = ? WHERE ticket_hash = ?", (_utc_text(), digest))
            db.commit()
        return Actor(row["actor_id"], row["display_name"], row["role"], frozenset(json.loads(row["scopes_json"])))


def create_router(service: ControlPlane) -> APIRouter:
    """Create the v1 API router bound to a specific durable service."""

    router = APIRouter(prefix="/api/v1")

    def bearer_token(request: Request) -> str:
        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Bearer authentication required")
        return header[7:]

    def actor_dependency(request: Request) -> Actor:
        try:
            return service.authenticate(bearer_token(request))
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    def translate_error(exc: Exception) -> HTTPException:
        if isinstance(exc, KeyError):
            return HTTPException(status_code=404, detail=str(exc.args[0]))
        if isinstance(exc, PermissionError):
            return HTTPException(status_code=403, detail=str(exc))
        if isinstance(exc, (ValueError, RuntimeError)):
            return HTTPException(status_code=409 if isinstance(exc, RuntimeError) else 422, detail=str(exc))
        return HTTPException(status_code=500, detail="control-plane request failed")

    @router.get("/auth/config")
    def auth_config() -> dict[str, Any]:
        return {
            "mode": "DEVELOPMENT_BOOTSTRAP_SECRET",
            "enabled": bool(service.auth_secret),
            "users": service.list_development_users(),
            "warning": "Development identity bootstrap only; configure a production identity provider before deployment.",
        }

    @router.post("/auth/session")
    def login(body: LoginRequest) -> dict[str, Any]:
        try:
            return service.login(body.actor_id, body.bootstrap_secret)
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    @router.delete("/auth/session")
    def logout(request: Request, actor: Actor = Depends(actor_dependency)) -> dict[str, str]:
        service.revoke(bearer_token(request), actor)
        return {"status": "revoked"}

    @router.get("/platform/state")
    def platform_state(actor: Actor = Depends(actor_dependency)) -> dict[str, Any]:
        service.require_scopes(actor, {"detection:read"})
        return service.platform_state()

    @router.get("/platform/capabilities")
    def capabilities(actor: Actor = Depends(actor_dependency)) -> dict[str, Any]:
        service.require_scopes(actor, {"detection:read"})
        gateway = service.gateway.capabilities()
        return {
            "environment": "DEVELOPMENT",
            "execution_adapter": "TYPED_OPERATIONAL_GATEWAY" if service.gateway.operational else "SIMULATION_ONLY",
            "operational_actions_enabled": service.gateway.operational,
            "arbitrary_shell": False,
            "registered_operations_console": service.gateway.operational,
            "usrp": service.gateway.operational,
            "rf_transmission": service.gateway.operational,
            "systemd_helper": False,
            "local_fixed_argv_gateway": service.gateway.operational,
            "model_promotion": service.gateway.operational,
            "raw_iq_capture_and_server_side_processing": service.gateway.operational,
            "raw_iq_browser_egress": False,
            "chat_modes": ["EXPLAIN", "PLAN"],
            "gateway": gateway,
        }

    @router.get("/workflows")
    def workflows(actor: Actor = Depends(actor_dependency)) -> list[dict[str, Any]]:
        return service.public_workflows(actor)

    @router.post("/workflows/{workflow_id}/runs")
    def start_workflow(workflow_id: str, body: WorkflowRunRequest, actor: Actor = Depends(actor_dependency)) -> dict[str, Any]:
        try:
            return service.start_workflow(workflow_id, body, actor)
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.get("/workflow-runs")
    def workflow_runs(limit: int = 100, actor: Actor = Depends(actor_dependency)) -> list[dict[str, Any]]:
        service.require_scopes(actor, {"detection:read"})
        return service.list_runs(limit)

    @router.get("/workflow-runs/{run_id}")
    def workflow_run(run_id: str, actor: Actor = Depends(actor_dependency)) -> dict[str, Any]:
        service.require_scopes(actor, {"detection:read"})
        try:
            return service.get_run(run_id)
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/workflow-runs/{run_id}/cancel")
    def cancel(run_id: str, actor: Actor = Depends(actor_dependency)) -> dict[str, Any]:
        try:
            return service.cancel_run(run_id, actor)
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/workflow-runs/{run_id}/approve")
    def approve(run_id: str, body: WorkflowApprovalRequest, actor: Actor = Depends(actor_dependency)) -> dict[str, Any]:
        try:
            return service.approve_run(run_id, body, actor)
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.get("/health")
    def health(actor: Actor = Depends(actor_dependency)) -> dict[str, Any]:
        service.require_scopes(actor, {"health:read"})
        return service.health_snapshot()

    @router.get("/health/host")
    def host_health(actor: Actor = Depends(actor_dependency)) -> dict[str, Any]:
        service.require_scopes(actor, {"health:read"})
        return service.host_health()

    @router.get("/health/services")
    def service_health(actor: Actor = Depends(actor_dependency)) -> dict[str, Any]:
        service.require_scopes(actor, {"health:read"})
        return service.service_health()

    @router.get("/health/usrp")
    def usrp_health(actor: Actor = Depends(actor_dependency)) -> dict[str, Any]:
        service.require_scopes(actor, {"health:read"})
        return service.usrp_health()

    @router.get("/health/pipeline")
    def pipeline_health(actor: Actor = Depends(actor_dependency)) -> dict[str, Any]:
        service.require_scopes(actor, {"health:read"})
        state = service.platform_state()
        return {"state": state["state"], "mode": state["mode"], "services": state["services"], "observed_at_utc": _utc_text()}

    @router.get("/flowgraph")
    def flowgraph(actor: Actor = Depends(actor_dependency)) -> dict[str, Any]:
        service.require_scopes(actor, {"detection:read"})
        return service.flowgraph_topology()

    @router.get("/services/{service_id}/logs")
    def service_logs(service_id: str, actor: Actor = Depends(actor_dependency)) -> dict[str, Any]:
        service.require_scopes(actor, {"maintenance:execute"})
        try:
            result = service.gateway.read_service_log(service_id)
            service.append_audit("service.log.viewed", actor.actor_id, None, {"service_id": service_id, "bytes": result["bytes"]})
            return result
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.get("/models")
    def models(actor: Actor = Depends(actor_dependency)) -> list[dict[str, Any]]:
        service.require_scopes(actor, {"model:read"})
        return service.model_catalog()

    @router.get("/datasets")
    def datasets(actor: Actor = Depends(actor_dependency)) -> list[dict[str, Any]]:
        service.require_scopes(actor, {"data:read"})
        return service.dataset_catalog()

    @router.get("/data/raw-sessions")
    def raw_sessions(actor: Actor = Depends(actor_dependency)) -> list[dict[str, Any]]:
        service.require_scopes(actor, {"data:raw_read"})
        records = service.gateway.raw_inventory()
        service.append_audit("data.raw_inventory.viewed", actor.actor_id, None, {"session_count": len(records)})
        return records

    @router.post("/datasets/{dataset_id}/validate")
    def validate_dataset(dataset_id: str, actor: Actor = Depends(actor_dependency)) -> dict[str, Any]:
        try:
            return service.validate_dataset(dataset_id, actor)
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.get("/audit/events")
    def audit_events(after: int = 0, limit: int = 200, actor: Actor = Depends(actor_dependency)) -> list[dict[str, Any]]:
        service.require_scopes(actor, {"audit:read"})
        return service.list_audit(after=after, limit=limit)

    @router.get("/audit/integrity")
    def audit_integrity(actor: Actor = Depends(actor_dependency)) -> dict[str, Any]:
        service.require_scopes(actor, {"audit:read"})
        return service.verify_audit_integrity()

    @router.post("/chat/sessions")
    def chat_session(body: ChatSessionRequest, actor: Actor = Depends(actor_dependency)) -> dict[str, Any]:
        try:
            return service.create_chat_session(actor, body.mode)
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/chat/sessions/{session_id}/messages")
    def chat_message(session_id: str, body: ChatMessageRequest, actor: Actor = Depends(actor_dependency)) -> dict[str, Any]:
        try:
            return service.chat_message(session_id, actor, body.message)
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.get("/tools")
    def registered_tools(actor: Actor = Depends(actor_dependency)) -> list[dict[str, Any]]:
        service.require_scopes(actor, {"terminal:restricted"})
        return service.gateway.registered_tools()

    @router.post("/tools/{tool_id}/runs")
    def execute_tool(tool_id: str, body: ToolRunRequest, actor: Actor = Depends(actor_dependency)) -> dict[str, Any]:
        service.require_scopes(actor, {"terminal:restricted"})
        try:
            result = service.gateway.execute_tool(tool_id)
            if tool_id in {"usrp.discover", "usrp.probe"}:
                service.set_meta(
                    "last_usrp_probe",
                    {"tool_id": tool_id, "observed_at_utc": _utc_text(), "status": "PASS", "output_digest": canonical_digest(result)},
                )
            service.append_audit(
                "tool.execution.completed",
                actor.actor_id,
                None,
                {"tool_id": tool_id, "reason": body.reason, "reference": body.reference, "result": result},
            )
            return result
        except Exception as exc:
            service.append_audit(
                "tool.execution.failed",
                actor.actor_id,
                None,
                {"tool_id": tool_id, "reason": body.reason, "reference": body.reference, "error": str(exc)},
                severity="error",
            )
            raise translate_error(exc) from exc

    @router.post("/ws-ticket")
    def ws_ticket(actor: Actor = Depends(actor_dependency)) -> dict[str, Any]:
        return service.issue_ws_ticket(actor)

    @router.get("/metrics", response_class=PlainTextResponse)
    def metrics(actor: Actor = Depends(actor_dependency)) -> str:
        service.require_scopes(actor, {"health:read"})
        host = service.host_health()
        state = service.get_meta("platform_state")
        state_value = 1 if state == "RUNNING" else 0
        return (
            "# HELP carat_platform_running Control-plane RUNNING state.\n"
            "# TYPE carat_platform_running gauge\n"
            f"carat_platform_running {state_value}\n"
            "# HELP carat_host_memory_percent Host memory utilisation.\n"
            "# TYPE carat_host_memory_percent gauge\n"
            f"carat_host_memory_percent {host['memory']['percent']}\n"
            "# HELP carat_host_disk_percent Repository filesystem utilisation.\n"
            "# TYPE carat_host_disk_percent gauge\n"
            f"carat_host_disk_percent {host['disk']['percent']}\n"
        )

    return router


async def websocket_events(service: ControlPlane, websocket: WebSocket) -> None:
    """Authenticated, ordered audit/event replay WebSocket using one-time tickets."""

    protocols = [item.strip() for item in websocket.headers.get("sec-websocket-protocol", "").split(",")]
    ticket_protocol = next((item for item in protocols if item.startswith("ticket.")), "")
    ticket = ticket_protocol.removeprefix("ticket.")
    after_text = websocket.query_params.get("after", "0")
    try:
        after = max(0, int(after_text))
        actor = service.consume_ws_ticket(ticket)
    except (ValueError, PermissionError):
        await websocket.close(code=1008, reason="invalid event-stream ticket")
        return
    try:
        service.require_scopes(actor, {"audit:read"})
    except PermissionError:
        await websocket.close(code=1008, reason="audit scope required")
        return
    await websocket.accept(subprotocol="carat.v1")
    cursor = after
    try:
        while True:
            events = service.list_audit(after=cursor, limit=200)
            for event in events:
                await websocket.send_json(event)
                cursor = event["sequence"]
            if not events:
                await websocket.send_json(
                    {
                        "api_version": "v1",
                        "type": "stream.heartbeat",
                        "timestamp": _utc_text(),
                        "sequence": cursor,
                        "source": "control-plane",
                        "severity": "info",
                        "payload": {},
                    }
                )
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
            except TimeoutError:
                pass
    except (WebSocketDisconnect, asyncio.CancelledError):
        return
