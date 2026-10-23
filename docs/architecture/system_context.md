# System context

Status: Proposed architecture foundation. Environment: DEVELOPMENT.
Configured name: RF Sensing Falls Project (working title; not approved).

## Evidence boundary

The repository already implements experimental CW acquisition, preprocessing, classifiers, a
posture state machine, and a research dashboard. Those components are DEVELOPMENT artifacts under a
legacy architecture. They do not establish clinical safety, regulatory status, external
generalisation, or passage of framework v1.1 gates.

## Actors

- Participant or resident: may be sensed only under an approved purpose, consent/legal-authority
  basis, monitoring zone, and withdrawal process.
- Researcher: conducts approved bench or participant protocols and cannot self-approve clinical,
  ethics, privacy, or RF compliance.
- Clinician: may review authorised decision support in later stages; remains responsible for action.
- Operator: manages approved acquisition/detection workflows without access to clinical identity.
- ML engineer: creates candidate models but cannot promote them.
- Data custodian: controls coded data, linkage, retention, export, and withdrawal.
- Governance bodies: HREC/site governance, privacy and security reviewers, RF compliance owner,
  regulatory reviewer, and independent gate reviewer.

## Product boundaries

| Product | Output | Current status | Claim boundary |
|---|---|---|---|
| A: fall event detection | Probable event, timing, uncertainty, quality, latency | Experimental legacy code only | No clinical alert or injury claim |
| B: activity and mobility recognition | Activity/transition plus unknown | Experimental legacy code only | No validated static posture or disease inference |
| C: long-horizon fall-risk forecasting | Calibrated absolute risk at a named horizon | Not implemented | No risk score without validated RF markers and clinical baseline |
| D: imminent fall warning | Probability in the next seconds | Out of scope/high-risk research | Must not be advertised or deployed |

Labels, models, evaluation plans, thresholds, and claims are separate for each product.

## Target data and decision flow

    Approved RF illumination or receive-only source
      -> acquisition and immutable raw storage
      -> signal-quality gate
      -> channel/signal processing
      -> physics features and learned representations
      -> Product B activity model
      -> Product A probable-event model
      -> event aggregation and abstention
      -> authorised clinician/research review

    Longitudinal validated RF mobility features
      + separately governed clinical observations
      -> Product C calibrated horizon-specific risk
      -> uncertainty, data sufficiency, trajectory, and associations
      -> authorised clinician review
      -> local human decision and documented action

Product D has no operational path.

## Trust boundaries and data classes

1. RF and device boundary: N210 commands require exclusive ownership, an approved profile, and a
   deny-by-default TX interlock.
2. Acquisition boundary: raw IQ is immutable, checksummed, local/object-stored, and never served by
   the dashboard.
3. Research boundary: coded participant IDs, labels, derived movement, room and protocol metadata.
4. Identity-linkage boundary: future direct identity is segregated under the data custodian; it does
   not enter model features or general operational logs.
5. Clinical boundary: authorised clinical context and source observations remain distinct from
   derived features and predictions.
6. Control boundary: browser/chat requests invoke typed allowlisted workflows, never shell content.
7. External export boundary: only approved, de-identified packages with provenance and audit.

## Current component mapping

| Component | Current path | Evidence status |
|---|---|---|
| Hardware configuration | config/system.yaml; configs/rf_profiles/lab_cw_2462.yaml | 2.462 GHz supervised profile; no host-wide ownership daemon |
| Live acquisition | sdr/cw_doppler_tx_rx.py | Experimental; available only through approval-gated bounded workflow; not executed during this task |
| Offline/replay acquisition | scripts/replay.py; sdr/replay_source.py | Available for safe development |
| Signal processing | dsp/spectrogram_service.py; features/micro_doppler.py | Experimental; requires versioned validation |
| Activity/fall inference | inference/realtime_classifier.py | Experimental; metadata shows unsafe fall recall for clinical use |
| State aggregation | inference/posture_state_machine.py | Activity state only, not platform operational state |
| Dashboard | dashboard/app.py; dashboard/control_plane.py; dashboard/operations_gateway.py; dashboard/frontend | Authenticated DEVELOPMENT typed operational control plane plus separate legacy research views; not a G1A pass |
| Model storage | models/production; models/candidates; models/registry/active.json | Immutable candidates and optional atomic active pointer; legacy production fallback remains |
| Evidence and governance | docs/evidence; docs/decisions; risk; artifacts/agent_runs | Operational slice updated 2026-09-20 |

## Human decision and fallback

No operational clinical alert is authorised. A future probable event must show uncertainty, data
quality, coverage, model version, limitations, and the statement that it is not proof of injury.
No alert must never be represented as safety. Low-quality, missing, stale, multi-person, unknown
configuration, or out-of-distribution input produces abstention. Loss of the research dashboard or
detector does not alter ordinary care or emergency pathways.

## Prohibited scope

- autonomous diagnosis, treatment, medication change, restrictive practice, or care determination;
- direct RF identity recognition or unrelated intimate-behaviour inference;
- raw RF data in the clinical record;
- Product D claims;
- clinical deployment before ethics, privacy, security, regulatory, human-factors, and validation
  gates pass.
