# ADR 0003: Supervised local operations gateway

- Status: Accepted for DEVELOPMENT engineering use
- Date: 2026-09-20
- Supersedes: ADR 0002's simulation-only execution decision
- Gate: G1A integration evidence remains incomplete; this ADR does not pass G1A

## Decision

Retain the versioned workflow/RBAC/audit control plane from ADR 0002 and add a narrow local
operations gateway for the CARAT development workstation. The gateway constructs every executable
and argument in code, uses `shell=False`, closes stdin, supplies a minimal environment, bounds
runtime/output, launches managed services in process groups, reconciles their recorded identities,
and supports cancellation and emergency termination. No HTTP, chat, or form field is interpreted as
a command, executable, working directory, environment variable, or shell fragment.

The dashboard may orchestrate:

- simulation and recorded replay;
- the existing N210 CW acquisition, DSP, inference, and state-aggregation chain;
- bounded local raw-IQ capture and inventory;
- immutable candidate training and evaluation;
- compare-and-swap active-model promotion and approved rollback; and
- a closed registry of read-only or disruptive-read diagnostics.

RF start, raw capture, promotion, and rollback bind execution to the exact workflow digest,
parameters, environment, requester, reason, reference, expiry, distinct non-requester approvals,
and (for RF) the selected profile digest. Live RF always has an automatic stop bound. Promotion
re-verifies the candidate metadata, artifact/evaluation hashes, passing gates, threshold policy,
model card, active-pointer generation, and expected prior digest. Training never promotes.

Raw sample bytes remain workstation-local. The browser can request capture, list safe inventory and
integrity metadata, and initiate server-side replay/processing, but no API serves SigMF data bytes or
absolute raw-data paths.

## Rationale

The dashboard's purpose is whole-system orchestration. The simulation slice proved the policy and
UI contracts, but leaving real work to CLI commands split authority and audit across two surfaces.
The fixed-argv gateway closes that gap without introducing a generic remote shell or allowing model
training to mutate serving state.

Direct local supervision is proportionate for the current single-workstation DEVELOPMENT system and
uses the repository's real entry points. A root-owned systemd/PolicyKit helper remains the preferred
deployment boundary where stronger host-level separation is required.

## Consequences

- Operational workflows run from the dashboard and long candidate/capture jobs do not block the API
  request thread; tracked jobs can be cancelled by authorised users.
- The local process registry validates PID creation time and argv digest before status or stop.
- The browser cannot invoke arbitrary shell commands or download raw IQ.
- Current model evidence remains failed and promotion-ineligible; having a promotion workflow does
  not make any current candidate promotable.
- The high-impact scopes `rf:transmit`, `data:capture_raw`, `data:raw_read`, `model:evaluate`,
  `model:promote_approve`, and `terminal:restricted` require an explicit role assignment. They are
  defined but not silently added to a role by this ADR.
- PostgreSQL/durable workers, production identity, external append-only audit, dedicated service
  identities, host-wide N210 ownership, and a privileged helper remain deployment hardening work.
- Clinical alerting and arbitrary shell execution remain out of scope.

## Evidence

The implementation is in `dashboard/operations_gateway.py`, `dashboard/control_plane.py`, the
fourteen workflow files under `configs/control_plane/workflows/`, the action/workflow schemas, and
the React controls. Deterministic evidence is recorded in the task artifact and validation report
under `artifacts/agent_runs/CARAT-20260920-001/`.
