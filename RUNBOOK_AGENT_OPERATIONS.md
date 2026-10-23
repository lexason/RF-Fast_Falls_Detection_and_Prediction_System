# CARAT Agent Operations Runbook

**Version:** 1.0  
**Purpose:** Operational procedures that should not live in `AGENTS.md`, `CLAUDE.md`, or `CODEX.md`.

This document is subordinate to the RF domain framework and hybrid framework. It contains practical workflows and starter acceptance criteria. It is not a second source of safety policy or hardware truth.

---

# 1. Operating loop

Every substantive engineering session follows:

```text
PLAN → ACT → OBSERVE → REASON → RECORD → REPEAT
```

## PLAN

- Read `STATE.md`, current Git state, applicable gate criteria, current config, and relevant evidence.
- Resolve execution environment/capabilities.
- Pick the smallest step that can change what you know.
- Define the expected observable result before acting.

## ACT

- Make one bounded change, run one measurement, or execute one controlled experiment.
- Prefer replay/simulation before live hardware when it answers the same engineering question.

## OBSERVE

Capture actual output: tests, logs, plots, throughput, latency, RF probe output, confusion matrices, checksums, or errors.

## REASON

Compare observation against the stated acceptance criterion. Separate facts, interpretation, and uncertainty.

## RECORD

- Store detailed evidence under `artifacts/`, `experiments/`, `reports/`, or `logs/`.
- Update `STATE.md` only with concise state changes and evidence pointers.
- Commit a coherent completed unit of work when appropriate. A commit is provenance, not evidence by itself.

## REPEAT

After two unsuccessful repair attempts on the same hypothesis, stop thrashing. Record what failed, generate competing hypotheses, and run the smallest discriminating test.

---

# 2. Environment and capability probe

Before hardware/protected-data/deployment work, create or update an execution-context record from `config/agent_capabilities.example.yaml`.

Useful checks may include:

```bash
pwd
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git status --short
hostname
ip addr
```

Do not probe protected resources merely to discover whether you are allowed to access them. Policy/approval comes first where required.

---

# 3. Hardware verification pattern

Resolve device address and parameters from current config rather than this runbook. Example pattern:

```bash
# Replace <USRP_ARGS> with the current approved/configured device args.
uhd_find_devices --args '<USRP_ARGS>'
uhd_usrp_probe --args '<USRP_ARGS>' | tee artifacts/hardware/uhd_usrp_probe.txt
```

For RX throughput testing, use the installed UHD benchmark tool and record exact version, rate, duration, output, overflows, host/NIC state, and commit/config hash.

TX-capable commands require the RF framework's approval boundary. Never copy an old frequency, gain, antenna assumption, or IP address from this runbook into an active command without resolving current state.

---

# 4. Software verification pattern

Start with deterministic checks:

```bash
pytest tests/ -m 'not hw'
ruff check .
```

Run only checks actually configured in the repository. If `mypy`, integration tests, benchmarks, schema validators, or hardware tests exist, invoke the relevant ones and archive outputs for material tasks.

For a code change, the evidence packet should include at minimum:

- input commit and diff;
- exact test commands and outputs;
- changed behaviour demonstrated by regression test or benchmark;
- unresolved warnings/failures.

---

# 5. Capture/replay discipline

Hardware-dependent downstream code should, where practical, have a replay path so Codex/Claude/cloud/CI sessions without live hardware can still reproduce DSP/ML behaviour.

Recommended capture provenance:

```text
session_id
start_time_utc
device/probe identifier
carrier/sample rate/bandwidth/gain
antenna geometry
room/site/session metadata
software commit
config hash
operator/protocol
raw-data hash
label-manifest hash
```

Raw participant/protected data must stay within authorised storage and contexts.

---

# 6. Implementation milestones M0-M6

These are operational milestones only. G0-G8 remain authoritative.

## M0 Environment and hardware verification

Goal: prove that the configured hardware/software environment exists and can produce reproducible RX evidence without pretending that documentation equals measurement.

Typical evidence:

- UHD/GNU Radio/Python versions;
- device probe archived;
- current daughterboard/ports/frequency coverage verified from probe and official documentation;
- stable RX throughput at the rate required by the current design;
- safe RX-only sanity capture;
- hardware smoke tests where available.

Feeds primarily G1.

## M1 Capture and replay pipeline

Goal: reproduce downstream processing from a recorded session without live hardware.

Evidence:

- parameterised capture;
- self-describing manifest;
- replay command;
- reference sessions;
- deterministic PSD/spectrogram output;
- checksums.

Feeds G2 and early G3.

## M2 Real-time DSP core

Goal: demonstrate the selected sensing waveform/channel-processing path with measured latency, stability, signal observability, and replay equivalence.

Evidence should explicitly validate rather than assume clutter removal, STFT/channel estimation, frame timing, buffer behaviour, and expected human-motion signatures.

Feeds G2.

## M3 Activity/fall research baseline and live viewer

Goal: create a leakage-controlled research baseline and live visualization. Do not confuse the live viewer with the G1A administrative/operations control plane.

Evidence:

- split manifests created before windows;
- per-class metrics and confusion matrix;
- fall-event sensitivity/PPV/false-alert burden/latency where applicable;
- unknown/abstention behaviour;
- continuous-run stability;
- reproducible experiment directory.

Feeds G3/G4.

## M4 Gait/mobility feature library and personal baseline

Goal: establish repeatable longitudinal features, test-retest behaviour, sensitivity to controlled perturbation, and missingness/quality handling.

Feeds G4.

## M5 Fall-risk research pipeline

Goal: integrate longitudinal RF-derived mobility markers with the Product C methodology in the RF framework without claiming future-fall prediction before appropriate outcomes exist.

When true fall-outcome labels are unavailable, label proxy outcomes explicitly as proxies and prohibit clinical-risk claims.

Feeds G4 initially; G5-G8 require the population/external/prospective evidence defined by the RF framework.

## M6 Research outputs

Goal: make figures/tables/methods regenerate from versioned code/config/evidence. Every publication claim must map to evidence and the correct Product A/B/C/D boundary.

---

# 7. Known RF/DSP/ML failure modes to test, not merely remember

- UHD overflows/underflows can invalidate downstream conclusions.
- TX leakage can consume analog headroom before digital clutter cancellation.
- Operator motion, fans, pets, curtains, and other movers can create confounds.
- Static posture is not directly observable from a pure motion-only Doppler signal after clutter removal; posture claims need an explicit state/measurement model.
- Random-window splits can create severe temporal/session/participant leakage.
- One-room or one-person performance does not imply cross-room/population generalisation.
- Sitting/lying transitions may resemble fall-like vertical motion; post-event context and event-level false-alert burden matter.
- Alert fatigue is an operational outcome, not just a classifier threshold issue.
- Commodity Wi-Fi traffic is not automatically a stable illuminator; packet/channel/missingness behaviour must be measured.

Turn each relevant pitfall into a test or experiment. Do not encode it as an unquestioned assumption.

---

# 8. Independent review checklist

For R2-material/R3/R4 technical work, the reviewer checks:

- Does the diff match the task?
- Did the builder reproduce the baseline/defect first?
- Are tests capable of failing for the claimed defect?
- Is there data leakage, circular evaluation, hidden threshold tuning, or split contamination?
- Are RF/DSP assumptions physically plausible and measured where necessary?
- Are metrics prevalence-appropriate and uncertainty reported?
- Are claims narrower than or equal to the evidence?
- Are protected-data and security boundaries respected?
- Can a deterministic experiment decide any remaining disagreement?

---

# 9. Operational command safety

Buttons/chat commands on the future dashboard should call versioned workflows such as:

```text
start_detection
stop_detection
run_health_check
capture_rx_session
replay_session
train_candidate_model
validate_candidate_model
recalibrate_personal_baseline
promote_model_candidate   # R4 approval required
run_hardware_probe
collect_diagnostics
```

Each workflow defines parameters, preconditions, permissions, timeout, audit log, expected artifacts, cancellation, and rollback. A natural-language request resolves to a named workflow rather than becoming raw shell text.

---

# 10. What this runbook must never contain as canonical truth

Do not make this file authoritative for:

- current USRP IP/device serial/daughterboard;
- current carrier/gain/sample rate;
- current trained model/checkpoint;
- approved clinical threshold/risk horizon;
- participant identifiers or secrets;
- gate PASS state;
- ethics/RF approval status.

Those belong in current evidence, approved config, governance records, and `STATE.md` pointers.
