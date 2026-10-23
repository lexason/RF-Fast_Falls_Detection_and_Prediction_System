# Initial framework v1.1 gate gap report

Date: 2026-08-07
Mode: BUILD
Assessed gates: G0, G1, G1A
Repository commit at baseline: 0e4e519f9f6c410515f41200435103d14dd4cc7b
Environment: DEVELOPMENT

## Decision

| Gate | Decision | Rationale |
|---|---|---|
| G0 Intended use and governance | FAIL | Hazard/evidence foundations now exist, but research purpose, intended use, clinical workflow, owners, ethics, regulatory position, privacy, RF approval, and partner appointments are not approved. |
| G1 Hardware integrity | FAIL | Electronic identity and GigE link are observed; framework v1.1 streaming, external attenuated loopback, clipping/error/repeatability, suitable antenna, exclusive ownership, and RF/OTA approval evidence are absent. |
| G1A Operations control-plane integrity | FAIL | Schemas, a closed non-executable action registry, semantic validators, and architecture form a tested offline foundation, but no executable state machine/workflows, RBAC, privilege helper, durable locks/audit/recovery, or integration suite exists. |

Historical G0/G1/G2 checkmarks in STATE.md use a legacy gate system and are preserved as historical
technical evidence only. They do not transfer into these decisions.

## Immediate safety state

- The CARAT continuous 5.8 GHz acquisition/TX process was stopped at
  2026-08-07T03:55:18.514893Z, and the CARAT preprocessing/inference/logger chain was stopped.
- The CARAT dashboard did not shut down cleanly after upstream loss; its closed-listener orphan was
  terminated. CARAT live operation was not restarted.
- No CARAT streaming benchmark, hardware test, loopback, or later N210 command is authorised by this
  report.
- Further staged falls or hazardous human collection are paused pending institutional and clinical
  safety governance.
- Sister-project files, configuration, and operations are outside the scope of this report.

## G0 criterion review

| Criterion | Evidence | Status | Required correction |
|---|---|---|---|
| Approved research purpose | ADR 0001 is proposed only | FAIL | Accountable sponsor and clinical governance approval |
| User and decision identified | Clinician/research review and no autonomous care are drafted | PARTIAL | Name authorised users, setting, exact decision, timing, alternatives, fallback |
| Products A-D separated | ADR 0001 and system context separate them | DOCUMENTED | Clinical/governance approval and claim inventory |
| Ethics pathway defined | Draft ethics_pathway.md | PARTIAL | Written institutional determination, HREC/site approvals, protocol IDs, owners |
| Initial TGA applicability memo | Preliminary memo created | PARTIAL | Qualified claim-specific regulatory review and decision |
| Privacy and RF owners assigned | Roles are unassigned | FAIL | Named accountable owners and accepted responsibilities |
| Clinical partners and escalation workflow | No approved partner; alert protocol is non-operational | FAIL | Formal partner appointments and approved response/fallback workflow |
| Hazard log opened | Twelve initial hazards recorded | PASS | Current risk is not reduced by planned controls; accountable people, due dates, verification, and residual-risk approval remain explicitly unassigned/open |

G0 remains failed because its acceptance conditions require approvals, not draft documents.

## G1 criterion review

| Criterion | Evidence | Status | Limitation |
|---|---|---|---|
| N210/UBX inventory | Electronic identity in probe and new hardware manifest | PARTIAL | Physical power supply, antennas, cables, attenuators, filters, calibration and hashes incomplete |
| UHD/GNU Radio versions | Archived under diagnostics | PASS | Mixed active/source and distribution UHD installations require provenance review |
| Gigabit Ethernet | 1 Gb/s full duplex, 0/20 ping loss | PASS | Observed MTU 1500 conflicts with legacy 9000; no sample-stream evidence |
| Streaming benchmark | Historical narrative only | FAIL | No current exclusive v1.1 raw output, counters, or repeatability |
| Conducted loopback | Historical internal CAL and OTA tests only | FAIL | No external measured attenuator chain or independently calculated RX margin |
| No clipping/overflow/underflow | No current intended-geometry evidence | FAIL | Must be demonstrated under an approved bounded profile |
| RF safety and OTA approval | Checklist open; owner unassigned | FAIL | Exact ACMA/technical/EME/EIRP/duty-cycle/location evidence absent |
| Correct full-duplex topology | TX/RX and RX2 confirmed | PASS | Capability only; does not authorise transmission |
| Frequency-suitable antennas | Legacy antennas labelled 2.4-2.5 GHz | FAIL for legacy 5.8 GHz | Candidate 2.4 GHz use still requires inventory and RF approval |

The full probe preceded exclusive-ownership verification. This is recorded as a diagnostic
nonconformance and retained only for identity provenance; it is not an authorised exception or G1
streaming evidence.

G1 evidence collection stops here. Hardware work resumes only after explicit task authority,
exclusive access, component/safety review, and current approval.

## G1A criterion review

| Required evidence/control | Current evidence | Status |
|---|---|---|
| Platform state machine and dependency graph | Proposed in control_plane.md | DOCUMENTED ONLY |
| Privilege boundary and threat model | Proposed design and draft threat model | DOCUMENTED ONLY |
| Versioned workflows and action registry | Closed proposed action registry plus syntax/semantic validators; no executable definitions or runtime | PARTIAL FOUNDATION |
| RBAC and approval matrix | Proposed role table; no enforcement | FAIL |
| Start/stop/emergency/health/train/recalibrate/rollback tests | None | FAIL |
| Durable locks and idempotency | None | FAIL |
| Audit completeness, integrity, and redaction | Existing mutable logs only | FAIL |
| Dashboard/chat-to-command injection protection | Closed action enum and offline semantic validator reject shell/arbitrary actions, unsafe arguments, graph, scope, lock, approval, retry, rollback, and audit bypasses; no runtime path | PARTIAL FOUNDATION |
| N210 capability truthfulness | Health schema plus adversarial offline semantic tests reject unavailable-field, critical-check, time, duplicate, and aggregate contradictions | PARTIAL FOUNDATION |
| Candidate/promotion/rollback isolation | Target design only; legacy direct-active writes remain | FAIL |
| Dashboard independence and recovery | Process decoupling exists; shutdown hang observed | FAIL |

The Phase 0 unit suite proves only document/schema invariants. It is not G1A integration evidence.

## Highest-priority defects

1. Critical: governance gate collision permits unsupported advancement.
2. Critical: CARAT RF start lacks signed approval, antenna/EIRP, expiry, and exclusive-owner interlocks.
3. Critical: staged-fall ethics and physical-safety governance are absent.
4. Critical: current fall recall and uncalibrated UI language are unsafe for clinical reliance.
5. High: dashboard authentication/RBAC and privacy governance are absent.
6. High: platform state, durable workflow locks, idempotency, audit, and recovery are absent.
7. High: model training can target a mutable active directory.
8. High: WebSocket upstream loss can block dashboard shutdown.
9. High: evidence, data provenance, realistic-prevalence evaluation, and external validation remain incomplete.

The first independent A15 review rejected the initial foundation after demonstrating environment-
flag hardware execution and syntactically valid but unsafe workflow, recording, and health
documents. The correction cycle removed Makefile hardware execution, added the closed action
registry and semantic validator, added adversarial regressions, repaired cross-ledger foreign keys,
separated current from projected residual risk, and recorded the probe nonconformance. These
corrections strengthen the baseline but do not pass G0, G1, or G1A.
Two further focused A15 replays found and then closed typed action-value, approval-binding,
stale-health, Make-recipe test, and parameter-default bypasses. The final A15 decision accepts only
the non-executable documentation baseline; every operational gate remains failed.

Details and owners are in risk/risk_register.csv, risk/hazard_log.csv, and the specialist handoffs.

## Verification completed

Baseline:

    .venv/bin/pytest -m 'not hw' -q

Result: exit 5; three hardware tests deselected and no non-hardware tests collected.

After Phase 0 foundation:

    make validate-governance

Result: 26 passed.

The tests validate the expanded required-file set, project naming, deny-by-default hardware
configuration, removal of executable hardware targets, all three JSON schemas, the closed action
registry and semantic workflow rules, adversarial health aggregation/capability cases, RF and
human-governance recording conditions, timestamp and checksum coverage, and cross-ledger foreign
keys/mandatory fields. These are offline foundation tests, not runtime safety evidence.

## Reproduction commands

Offline commands authorised for this report:

    git rev-parse HEAD
    git status --short --branch
    make validate-governance
    make test
    sha256sum RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK_v1_1.md

Read-only evidence inspection:

    sed -n '1,240p' configs/project.yaml
    sed -n '1,320p' configs/hardware/n210_ubx40.yaml
    sed -n '1,320p' reports/validation/2026-08-07_initial_gate_gap_report.md
    python -m json.tool schemas/recording.schema.json
    python -m json.tool schemas/workflow.schema.json
    python -m json.tool schemas/health_snapshot.schema.json

Future hardware commands are documented in docs/protocols/n210_bringup.md but must not be run from
this report. They require separate explicit authority, exclusive ownership, and all listed
preconditions.

## Evidence paths

- docs/evidence/diagnostics/2026-08-07/
- docs/evidence/evidence_ledger.md
- docs/evidence/literature_matrix.csv
- docs/evidence/requirements_traceability_matrix.csv
- docs/agents/handoffs/
- docs/decisions/0000-project-naming.md
- docs/decisions/0001-intended-use.md
- docs/architecture/system_context.md
- docs/architecture/control_plane.md
- docs/clinical/ethics_pathway.md
- docs/clinical/alert_response_protocol.md
- docs/regulatory/tga_applicability.md
- docs/regulatory/rf_compliance_checklist.md
- risk/risk_register.csv
- risk/hazard_log.csv
- risk/privacy_impact_assessment.md
- risk/threat_model.md

## Next smallest safe action

Convene a G0 approval review without hardware access. The accountable sponsor should choose or
confirm the working project name; approve the research purpose, population, users, decision, claims,
and Product A-D boundaries; assign clinical, ethics, privacy, RF, regulatory, security, data, and
statistical owners; obtain written institutional determination for existing/future human data; and
commission qualified TGA and RF/EME reviews.

Until that review, continue only offline replay, synthetic tests, schema/control-plane simulation,
documentation, and non-human analysis that does not require N210 access.
