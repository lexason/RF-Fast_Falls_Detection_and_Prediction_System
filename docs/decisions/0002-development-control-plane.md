# ADR 0002: Simulation-first development control plane

- Status: Superseded by ADR 0003 for execution; retained as the simulation-foundation record
- Date: 2026-09-20
- Gate: G1A foundation; this ADR does not pass G1A

## Decision

Implement the first operations-dashboard vertical slice as a local FastAPI API, a React and
TypeScript single-page interface, and a durable SQLite store. Every state-changing control resolves
to a versioned workflow under `configs/control_plane/workflows/`, validates against the workflow
schema and closed action registry, and calls a typed Python simulation adapter.

The adapter cannot invoke a subprocess or shell, connect to UHD or systemd, transmit RF, access raw
IQ, write serving model files, promote a model, or emit a clinical alert. The dashboard presents
current repository configuration, processed-dataset metadata, immutable model/evaluation artifacts,
local host health, source-labelled service simulation state, and explicitly unavailable N210 fields.

Development authentication requires an environment-supplied bootstrap secret and issues random,
hashed, expiring bearer sessions. Roles and scopes are declarative. Event-stream access uses a
single-use 30-second ticket carried in the WebSocket subprotocol header rather than the URL. Audit
events are recursively redacted and hash chained.

## Rationale

The existing dashboard was a useful research viewer but could not safely support controls. Wiring
buttons directly to legacy scripts would cross the privilege, approval, audit, and command-injection
boundaries before those controls existed. A simulation adapter makes the complete contract testable
now while keeping hardware and active-model side effects impossible.

SQLite is deliberately a development implementation of the authoritative store interface. It is
adequate for deterministic local tests and restart persistence, but it is not claimed to provide the
deployment separation or append-only database permissions required for production.

## Consequences

- Operators can test preflight, start, stop, emergency-stop, maintenance, health, training,
  recalibration, rollback approval, cancellation, and audit flows end to end.
- The UI uses repository data and evidence without reading or serving raw IQ.
- No dashboard control manages the live N210 or legacy pipeline.
- PostgreSQL, a durable worker queue, a production identity provider, HTTPS termination, and the
  narrow privileged systemd/PolicyKit helper remain required before operational execution.
- G1A remains failed until the full framework integration and human-factors evidence exists.
