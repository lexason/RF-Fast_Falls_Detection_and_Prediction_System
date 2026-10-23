# Operations control-plane architecture

Status: DEVELOPMENT TYPED OPERATIONAL VERTICAL SLICE IMPLEMENTED (2026-09-20).
Gate status: G1A remains FAIL until production boundaries and complete integration evidence pass.

This document defines the target and the boundary of the implemented DEVELOPMENT slice. The current
operations dashboard executes simulation and supervised local operations through versioned,
scope-checked workflows. It implements RF, raw-capture, candidate, promotion/rollback, and
registered-diagnostic paths; it does not provide arbitrary shell, data deletion, or clinical action.

## Implemented DEVELOPMENT slice

- `dashboard/control_plane.py` provides a durable SQLite workflow/audit service, simulation and
  fixed-argv adapters, environment-secret bootstrap authentication, expiring hashed sessions,
  declarative RBAC, parameter validation, state/resource locks, idempotency, dry runs,
  cancellation, rollback, two-person approval, hash-linked audit integrity, health, catalog, and
  Explain/Plan chat APIs.
- Fourteen versioned workflows under `configs/control_plane/workflows/` validate against
  `schemas/workflow.schema.json` and the closed action registry.
- `dashboard/frontend/` is a compiled local React/TypeScript interface with the ten framework panels,
  responsive layout, explicit evidence limits, and no CDN/runtime network dependency.
- `dashboard/operations_gateway.py` owns every executable and argument. It uses no shell, accepts no
  command string, closes stdin, bounds output/runtime, supervises process groups, and validates
  recorded PID creation time and argv digest before status/stop.
- Replay and live SDR start the actual acquisition/replay, spectrogram, classifier, and posture-state
  components downstream-first. Live RF is bound to a checked profile, two distinct approvals, exact
  parameters/reference/reason, a resource lock, and an automatic stop.
- Raw-IQ controls can capture and inventory data on the workstation and feed server-side replay, but
  no API returns sample bytes or absolute raw paths.
- Candidate training/evaluation are cancellable jobs. Promotion is a separate two-person,
  digest-verified compare-and-swap pointer update; rollback accepts only previously approved bundles.
- The registered operations console exposes five parameter-free tools, never a general shell.
- One-time WebSocket tickets are carried in the subprotocol header, consumed once, and expire after
  30 seconds; they are not placed in request URLs.
- `tests/unit/test_control_plane.py` supplies deterministic evidence for workflow validation, RBAC,
  idempotency, stop/emergency behavior, locks, rollback, two-person approval, cancellation, model
  isolation, audit redaction/integrity, N210 truthfulness, safe catalog access, chat injection, and
  event-ticket single use.

## Remaining deployment gaps

- The legacy `/monitor`, `/live`, and session views remain research views; the new gateway supervises
  processes it starts, not unrelated pre-existing processes.
- The API runs as the interactive account rather than a dedicated least-privilege service identity.
- CSV/JSONL operational logs are mutable and do not record complete actors, authorisations,
  approvals, steps, denial events, rollback, or integrity.
- Legacy `models/train_production.py` can still write the mutable production directory but is not
  exposed by any dashboard workflow.
- A CARAT dashboard shutdown on 2026-08-07 remained blocked in WebSocket background tasks after its
  upstream publishers stopped; the closed-listener orphan required force termination.
- No host-wide N210 ownership daemon or privileged helper exists. The SQLite RF lock coordinates
  dashboard workflows but cannot exclude unrelated host processes.
- The six high-impact scopes are defined but not assigned to a role pending explicit authorisation.

## Target service dependency graph

    Authenticated browser
      -> unprivileged Operations API
          -> durable audit/config/workflow database
          -> event broker and WebSocket replay
          -> workflow workers
              -> unprivileged model/data adapters
              -> narrow privileged helper
                  -> fixed systemd units only

    acquisition -> preprocessing -> inference -> event aggregation -> storage/notifications

The detection chain does not depend on the browser or API staying available. API restart reconstructs
state from systemd, persisted workflow state, locks, configuration, and heartbeats.

## Authoritative state

Primary states:

    UNINITIALISED -> STOPPED <-> MAINTENANCE
                         |
                     PREFLIGHT
                         |
                     STARTING
                         |
               RUNNING <-> DEGRADED
                  |           |
               STOPPING ----> FAILED
                  |
               STOPPED

Independent supervised jobs are TRAINING, EVALUATING, RECALIBRATING, REPLAYING, and BACKING_UP.
Every transition declares allowed source states, role/scope, approvals, locks, preconditions,
timeout, postconditions, cancellation, audit events, and safe compensation. Emergency stop has
priority over non-security work. Model/data jobs cannot acquire the N210 lock.

## Declarative workflow boundary

schemas/workflow.schema.json is the bounded syntax contract, and
configs/control_plane/action_registry.yaml is the closed action vocabulary; it remains declarative
and non-executable by itself. `dashboard/operations_gateway.py` is the separate bounded runtime.
tools/governance_validation.py provides offline semantic rejection tests for registry actions,
scopes, locks, approval strength, arguments, parameter references, graph cycles, retries, rollback,
and audit events. The runtime enforces these rules and additionally:

- verify the canonical registry and workflow digests before resolving an allowlisted action;
- reject unknown actions, dependency cycles, missing locks, unsafe retries, approval mismatches,
  unbounded output, and any string interpolation or shell/command field;
- bind approvals to workflow ID/version/digest, resolved parameters, environment, reason, and expiry;
- persist idempotency keys, step state, stdout/stderr digests, artifacts, cancellation, and rollback;
- require dry-run preview for every workflow;
- return the existing run for a duplicate idempotent start rather than launching a second job.

Natural language is never passed to a shell. Explain and Plan chat modes never execute. The
operations console is a closed registry of parameter-free fixed tools with authentication,
authorisation, timeout/output limits, and audit; a free-form terminal is not implemented.

## Privilege boundary

The API must run as a dedicated unprivileged identity with no sudo, Docker, administrator, or USRP
membership. Acquisition receives only the device/network access it needs. Training receives compute
and candidate-artifact access but no RF privilege.

If privileged service control is needed, use a small root-owned helper over a protected Unix socket
or PolicyKit/systemd D-Bus. It authenticates peer credentials and accepts only typed named actions
on fixed units. It has no network listener, general executable parameter, cwd/environment injection,
or generic command function. The helper returns bounded structured results for audit.

## N210 ownership and RF interlocks

The dashboard obtains a resource lock before CARAT device access and reconciles gateway-owned
processes. This is not a host-wide exclusion mechanism: unrelated applications can still own the
device. A shared host-enforced ownership boundary remains required for stronger deployment claims.

CARAT TX start additionally requires a signed, unexpired RF profile with approved location,
frequency, occupied bandwidth, waveform, duty cycle, conducted power, EIRP, antenna IDs and band
ratings, and approval reference. No broad ISM-band check substitutes for authorisation. A stopped
probe is potentially disruptive and is not a live-health action.

## Role and scope foundation

| Role | Permitted foundation scope | Explicit exclusions |
|---|---|---|
| Viewer | de-identified health read | no patient context or execution |
| Clinician | separately authorised clinical review | no infrastructure secrets, RF, or terminal |
| Operator | approved preflight/start/stop/emergency stop | no model training/promotion or arbitrary RF |
| ML engineer | candidate train/recalibrate/evaluate | no active-model write or RF |
| Administrator | bounded maintenance and governed approvals | no patient access unless separately authorised |
| Auditor | immutable audit read/verification | no execution |

Fine-grained scopes follow the framework matrix. Two-person approval requires distinct identities
for model promotion, governed data deletion, and other policy-defined high-risk actions.

## Audit contract

The authoritative store is append-only to application identities and records:

- request, actor, session, authentication and authorisation result;
- workflow ID/version/digest, resolved parameters, environment, reason, and idempotency key;
- dry run, confirmation, each approval and expiry;
- every step start/end, redacted output digest, artifact, timeout, retry, denial, cancellation,
  compensation, rollback, and final result;
- configuration/model before and after digests and correlation IDs.

Secrets, direct identity, raw clinical data, and unrestricted filesystem paths are redacted.
Integrity is independently verifiable through sequencing/hash linkage or an equivalent control.

## Health and N210 truthfulness

schemas/health_snapshot.schema.json distinguishes direct, derived, and unavailable measurements,
including observation time, freshness, source, derivation, and whether collection is disruptive.
N210 CPU utilisation, RAM utilisation, process list, and device filesystem are always unavailable:
the N210 is an FPGA radio peripheral, not a Linux host. Host-interface throughput is a host/network
measurement. Archived probe identity must never be displayed as current live telemetry.
The offline semantic validator rejects contradictory capability classes, missing critical checks,
duplicate check IDs, impossible status aggregation, and inconsistent observation/source times.
This remains fixture-level evidence, not a deployed collector or G1A pass.

## Model lifecycle

Training and recalibration write content-addressed CANDIDATE artifacts only. Recalibration links to
an unchanged base-model digest. Evaluation uses locked data and emits an immutable report and model
card. Promotion is a separate approved compare-and-swap workflow that changes an active pointer only
if the expected prior digest matches. Rollback names an exact previously approved artifact and
configuration. Legacy direct writes to models/production are excluded from future workflows.

## Threat summary

| Threat | Required control |
|---|---|
| Command/prompt injection | structured allowlisted actions; no shell; negative fixtures |
| Privilege escalation | dedicated identities and narrow peer-authenticated helper |
| Duplicate/conflicting jobs | durable idempotency and resource/state locks |
| RF bypass | signed profile, approval expiry, exclusive ownership, emergency stop |
| Stored HTML/script injection | template escaping and restricted IDs/paths |
| WebSocket/session hijack | authenticated upgrade, origin policy, revocation |
| Audit tampering | append-only permissions, integrity verification, independent export |
| Model replacement | digests, signatures, immutable registry, separate approval |
| Stale/fabricated telemetry | sources, timestamps, freshness, capability matrix |
| Shutdown/restart failure | cancellation-aware I/O, bounded shutdown, state reconstruction |

## Required acceptance evidence

G1A remains failed until simulation and integration tests prove schema rejection, semantic action
validation, authentication/RBAC, two-person approval, idempotency, locks, start/stop/emergency stop,
worker/API recovery, detector independence, bounded WebSocket shutdown, privilege separation,
command/prompt/path/HTML injection resistance, audit completeness/redaction/integrity, health
accuracy, N210 truthfulness, candidate isolation, promotion, and rollback.

No G1A claim may rely on this document alone.
