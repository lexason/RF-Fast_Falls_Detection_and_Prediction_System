# RF Sensing for Falls: Multi-Agent Engineering and Clinical Research Framework

**Version:** 1.1  
**Status:** Research and development master instruction  
**Primary use:** VS Code with Codex, Claude Code, GitHub Copilot, or another repository-aware coding agent  
**Target platform:** Ettus USRP N210 with UBX-40, Ubuntu, UHD, GNU Radio, Python, PyTorch  
**Initial bands:** 2.4 GHz first; 5 GHz/5.8 GHz after suitable antennas, RF components, and regulatory checks  
**Clinical context:** Fall event detection, activity recognition, longitudinal mobility assessment, and clinician-facing fall-risk decision support  
**Project naming:** Configurable. No project acronym is assumed or approved by this framework.  
**Version 1.1 additions:** Operations and maintenance dashboard, executable multi-step workflows, workstation and N210 health telemetry, model training and recalibration controls, RBAC, audit, agent chat, and restricted terminal design.  

---

## 0. How to use this file in VS Code

Place this file at the repository root as:

```text
RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK.md
```

Create a second lightweight pointer file named `AGENTS.md` containing:

```markdown
Read and follow `RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK.md` as the governing engineering,
research, clinical-safety, and validation instruction for this repository.
Start every task by declaring the operating mode, current stage gate, assumptions,
files to inspect, tests to run, and evidence required for completion.
```

Then invoke the coding assistant with one of these commands.

### Build from scratch

```text
Read RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK.md.
Act as MASTER_ORCHESTRATOR.
MODE=BUILD.
Begin at G0 and create the repository structure, evidence ledger, risk register,
requirements traceability matrix, and Phase 1 N210 bring-up plan.
Do not proceed past a gate without its specified evidence.
```

### Audit an existing repository

```text
Read RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK.md.
Act as MASTER_ORCHESTRATOR.
MODE=AUDIT.
Inspect the entire repository before changing code.
Reproduce the current baseline, identify RF, data, ML, statistical, clinical,
security, and deployment defects, and write a prioritised audit report with
file-and-line evidence. Do not modify files until the baseline is preserved.
```

### Repair an existing implementation

```text
Read RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK.md.
Act as MASTER_ORCHESTRATOR.
MODE=REPAIR.
Use the latest approved audit report.
Fix issues in risk order, preserve reproducibility, add tests, and produce
before-versus-after evidence for every material change.
```

### Run a stage-gate review

```text
Read RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK.md.
Act as MASTER_ORCHESTRATOR.
MODE=VALIDATE.
Evaluate readiness for G<number>.
Return PASS, CONDITIONAL PASS, or FAIL with evidence, unresolved risks,
required corrections, and exact commands needed to reproduce the decision.
```

### Continue a partially completed project

```text
Read RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK.md and all files under
docs/evidence, docs/decisions, reports, and risk.
Act as MASTER_ORCHESTRATOR.
MODE=CONTINUE.
Determine the last valid stage gate from evidence, not from claims.
Resume from the first incomplete acceptance criterion.
```


## 0.1 Project naming, provenance, and context isolation

This framework must not silently invent, import, or approve a project name.

Create `configs/project.yaml` before substantive implementation:

```yaml
project:
  display_name: "RF Sensing Falls Project"
  slug: "rf-sensing-falls"
  python_package: "rf_sensing_falls"
  acronym: null
  acronym_expansion: null
  naming_status: "working-title"
  approved_by: null
  approved_at: null
```

Rules:

1. Treat every acronym as unapproved until the user or project governance group explicitly approves it.
2. Record the source of a proposed name in `docs/decisions/0000-project-naming.md`.
3. Do not import a name from another chat, document, grant, repository, or remembered context without stating its source.
4. Do not assume that a prior collaboration name is the correct software product, clinical study, dataset, or repository name.
5. Use the configured `display_name`, `slug`, and `python_package` in generated files.
6. Preserve legacy paths only when required for compatibility, and document the alias and migration plan.
7. The dashboard must display the configured project name and the active environment, such as `DEVELOPMENT`, `SILENT PILOT`, or `CLINICAL EVALUATION`.


---

# 1. Mission

Build a privacy-preserving and clinically responsible RF sensing platform that can:

1. Detect human presence and motion.
2. Classify walking, sitting, standing, lying, transitions, and fall-like events.
3. Detect probable falls rapidly with a controlled false-alert burden.
4. Extract longitudinal mobility and functional markers from everyday behaviour.
5. Combine RF-derived markers with clinically relevant information to estimate a person's fall risk over a clearly defined future horizon.
6. Present calibrated risk, uncertainty, data quality, and modifiable contributors to a clinician as decision support.
7. Operate using low-cost hardware and, where practical, existing Wi-Fi infrastructure.
8. Support reproducible research, external validation, safe deployment, and eventual regulatory translation.

The project must never equate laboratory classification accuracy with clinical effectiveness.

---

# 2. The four products must remain separate

The system contains four related but distinct products. They require different labels, models, evaluation designs, and claims.

## Product A: Fall event detection

**Question:** Did a fall probably occur during this short time interval?

**Time scale:** Seconds.

**Output:** Event probability, event start and end, time-to-alert, uncertainty, and sensor-quality status.

**Primary metrics:** Event sensitivity, positive predictive value, false alerts per resident-day, missed falls, detection latency, alert delivery latency, and uptime.

## Product B: Activity and mobility state recognition

**Question:** What activity or transition is occurring?

**Classes:** Walking, standing, sitting, lying, sit-to-stand, stand-to-sit, bed exit, chair exit, turning, bending, kneeling, picking up an object, near-fall or loss of balance, and unknown.

**Time scale:** Seconds to minutes.

**Primary metrics:** Macro F1, per-class recall, balanced accuracy, segment overlap, transition timing error, and unknown-class performance.

## Product C: Long-horizon fall-risk forecasting

**Question:** What is the estimated probability that this person will fall within a defined horizon such as 7, 30, 90, or 180 days?

**Inputs:** Longitudinal RF-derived mobility measures plus appropriate clinical, medication, functional, historical, and environmental variables.

**Output:** Calibrated absolute risk, uncertainty interval, data sufficiency, trajectory, and the leading potentially modifiable contributors.

**Primary metrics:** Calibration, Brier score, time-dependent discrimination, precision-recall performance, decision-curve net benefit, sensitivity at an acceptable alert budget, subgroup performance, and external validation.

## Product D: Imminent fall warning

**Question:** Is a person likely to fall in the next few seconds?

This is a high-risk research objective, not an assumed capability. It requires pre-fall signatures, reliable person tracking, very low latency, and prospective evidence. It must not be advertised or deployed until independently validated. Near-fall and instability detection can be developed first as an exploratory surrogate, but a near-fall classifier is not proof of imminent-fall prediction.

---

# 3. Intended-use boundary

The initial intended use is:

> The system is an investigational, non-contact platform that estimates human activity, probable fall events, and longitudinal fall-risk indicators for clinician review. It does not diagnose a condition, prescribe treatment, replace clinical assessment, or autonomously determine care.

Any change to the intended use must trigger a regulatory, clinical-safety, and validation review.

A system intended to monitor, predict, prevent, or support treatment of injury or disability may fall within Australian medical-device regulation. The TGA pathway must be assessed from the exact intended purpose and claims, not postponed until commercialisation [R6, R7].

---

# 4. Non-negotiable principles

1. **No autonomous clinical decisions.** A clinician remains responsible for interpretation and action.
2. **No induced falls in vulnerable participants.** Staged falls are performed only by appropriately screened, trained participants using mats, spotters, and an approved protocol.
3. **No random-window leakage.** Split by participant, session, room, site, and time before window generation.
4. **No accuracy-only reporting.** Report prevalence-sensitive event and prediction metrics.
5. **No hidden test-set tuning.** Lock analysis plans, thresholds, and evaluation sets.
6. **No unqualified “high confidence” claim.** Output calibrated probabilities and uncertainty.
7. **No assumption that ordinary Wi-Fi traffic is a stable illuminator.** Measure packet rate, occupancy, channel changes, retransmissions, and missingness.
8. **No unsupported hardware claim.** Confirm every RF capability with official documentation and bench evidence.
9. **No over-the-air transmission before compliance review.** Check the current ACMA class licence, EME requirements, frequency, bandwidth, antenna gain, conducted power, EIRP, and operating location [R10, R11].
10. **No direct USRP TX-to-RX cable connection without adequate attenuation.**
11. **No clinical deployment without human research ethics approval and governance.** The 2025 National Statement took effect on 23 June 2026 [R5].
12. **No raw identity in research features.** Use coded participant identifiers and segregated linkage data.
13. **No silent model updates in clinical use.** Every model version is immutable, traceable, validated, and approved.
14. **No gate passing on documentation alone.** Evidence must be reproducible.
15. **Unknown is a valid output.** The system must abstain when signal quality, coverage, identity association, or model confidence is inadequate.

---

# 5. Current hardware truth and implications

## 5.1 Ettus N210 and UBX-40

The UBX-40 is a full-duplex transceiver covering 10 MHz to 6 GHz with up to 40 MHz instantaneous daughterboard bandwidth [R12]. The N210 host interface is 1 Gigabit Ethernet. In 16-bit sample mode it supports about 25 MS/s host streaming, corresponding to roughly 20 MHz usable bandwidth; higher rates require 8-bit samples and careful host tuning [R13, R14].

For UBX full-duplex operation, UHD uses the `TX/RX` connector for transmit and forces receive to `RX2` [R15].

### Consequences

- One N210 with one UBX-40 provides **one transmit chain and one receive chain**.
- It does **not** provide simultaneous 2 x 2 MIMO.
- It does **not** provide two simultaneous coherent receive channels.
- The current setup can support an active single-input single-output sensing link.
- A second synchronised USRP, a multi-channel coherent USRP, or a purpose-built CSI/radar device is required for simultaneous spatial diversity, angle estimation, or receive-antenna phase difference.
- The N210 can be a controlled research reference platform, but it is not itself a low-cost deployment endpoint.
- Existing 2.4 GHz antennas must not be assumed suitable at 5 GHz. Start at 2.4 GHz and procure verified dual-band or 5 GHz antennas, cables, attenuators, and filters before 5 GHz experiments.

## 5.2 Recommended two-track architecture

### Track 1: Active SDR research track

Use the N210 as a deterministic transmitter and receiver. Generate known OFDM, multitone, PN, or pilot-rich waveforms, then estimate the channel response.

Advantages:

- Controlled packet or frame rate.
- Known waveform.
- Repeatable timing.
- Tunable frequency and bandwidth.
- Access to raw IQ and calibrated RF measurements.
- Useful for physics experiments, algorithm development, and benchmark datasets.

Limitation:

- This is not automatically commodity IEEE 802.11 CSI.
- A custom waveform may not be deployable over ordinary routers.
- Host bandwidth and single-channel limitations must be respected.

### Track 2: Commodity Wi-Fi sensing track

Use a Wi-Fi router or access point as transmitter and a CSI-capable receiver such as an ESP32-class device, supported network interface card, or another verified platform.

Advantages:

- Low cost.
- Closer to the eventual infrastructure model.
- Easier multi-room scale-out.
- Commodity 2.4 GHz and, with suitable hardware, 5 GHz operation.

Limitations:

- CSI access is chipset and firmware dependent.
- Ordinary network traffic may be sparse or variable.
- Clock, carrier-frequency offset, sampling-frequency offset, automatic gain control, packet loss, and rate adaptation affect measurements.
- Some low-cost CSI devices support only 2.4 GHz or limited antenna configurations.
- A dedicated probe stream may still be needed for stable sensing cadence.

### Recommended strategy

Use Track 1 to understand the physics, establish channel and motion features, and build reproducible baselines. In parallel, build Track 2 as the cost-reduction and translational path. Models should not be assumed portable across tracks without transfer evaluation.

---

# 6. Reference system architecture

```text
                       CLINICAL AND RESEARCH GOVERNANCE
              ethics | intended use | safety | privacy | regulation
                                      |
                                      v
+----------------------+      +-------------------------+
| RF illumination      |      | Clinical and context    |
| N210 active waveform |      | fall history            |
| or Wi-Fi AP/prober   |      | medication and changes  |
+----------+-----------+      | mobility assessments    |
           |                  | diagnoses and symptoms  |
           v                  | environment and care    |
+----------------------+      +------------+------------+
| RF receiver          |                   |
| N210 RX2 raw IQ      |                   |
| or CSI receiver      |                   |
+----------+-----------+                   |
           v                               |
+----------------------+                   |
| Acquisition service  |                   |
| timestamping          |                   |
| metadata              |                   |
| integrity checks      |                   |
| immutable raw storage |                   |
+----------+-----------+                   |
           v                               |
+----------------------+                   |
| Signal quality gate  |                   |
| saturation            |                   |
| packet/sample loss    |                   |
| interference          |                   |
| clock/CFO/SFO         |                   |
| coverage              |                   |
+----------+-----------+                   |
           v                               |
+----------------------+                   |
| Signal processing     |                   |
| channel estimation    |                   |
| denoising             |                   |
| phase sanitisation    |                   |
| Doppler/time-frequency|                   |
| segmentation          |                   |
+----------+-----------+                   |
           v                               |
+----------------------+                   |
| Representation layer |                   |
| interpretable physics |                   |
| learned embeddings    |                   |
| data-quality features |                   |
+-----+------------+---+                   |
      |            |                       |
      v            v                       v
+-----------+ +-------------+   +-----------------------+
| Activity  | | Fall event  |   | Longitudinal feature  |
| model     | | detector    |   | store and trend engine|
+-----+-----+ +------+------+   +-----------+-----------+
      |              |                      |
      +------+-------+                      |
             v                              v
      +------------------+       +-----------------------+
      | Event fusion and |       | Clinical risk model   |
      | state machine    |       | defined time horizons |
      +--------+---------+       +-----------+-----------+
               |                             |
               +--------------+--------------+
                              v
                +----------------------------+
                | Clinician decision support |
                | probability and uncertainty|
                | evidence and data quality  |
                | modifiable contributors    |
                | trend and event timeline   |
                | acknowledgement and audit  |
                +----------------------------+
```

---

# 7. Repository structure

The orchestrator must create or reconcile the following structure.

```text
<project-root>/
├── AGENTS.md
├── RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK.md
├── README.md
├── LICENSE
├── CITATION.cff
├── Makefile
├── pyproject.toml
├── uv.lock or poetry.lock
├── .env.template
├── .gitignore
├── .pre-commit-config.yaml
├── .github/
│   └── workflows/
│       ├── ci.yml
│       ├── security.yml
│       └── reproducibility.yml
├── .vscode/
│   ├── settings.json
│   ├── tasks.json
│   └── launch.json
├── configs/
│   ├── hardware/
│   ├── acquisition/
│   ├── experiments/
│   ├── preprocessing/
│   ├── models/
│   ├── clinical/
│   ├── deployment/
│   ├── dashboard/
│   ├── runbooks/
│   ├── services/
│   ├── observability/
│   └── policies/
├── src/<python_package>/
│   ├── acquisition/
│   ├── hardware/
│   ├── waveforms/
│   ├── channel/
│   ├── preprocessing/
│   ├── segmentation/
│   ├── features/
│   ├── models/
│   │   ├── activity/
│   │   ├── fall_detection/
│   │   ├── risk_prediction/
│   │   └── calibration/
│   ├── evaluation/
│   ├── data/
│   ├── serving/
│   ├── monitoring/
│   ├── clinical/
│   ├── control/
│   ├── orchestration/
│   ├── telemetry/
│   ├── chat/
│   ├── auth/
│   ├── security/
│   └── common/
├── gnuradio/
│   ├── grc/
│   ├── generated/
│   └── blocks/
├── apps/
│   ├── operations_dashboard/
│   │   ├── frontend/
│   │   ├── backend/
│   │   └── shared/
│   ├── operator_console/
│   ├── clinician_dashboard/
│   ├── annotation_tool/
│   └── chat_console/
├── schemas/
│   ├── recording.schema.json
│   ├── annotation.schema.json
│   ├── participant.schema.json
│   ├── clinical_profile.schema.json
│   ├── prediction.schema.json
│   ├── alert.schema.json
│   ├── agent_handoff.schema.json
│   ├── workflow.schema.json
│   ├── workflow_run.schema.json
│   ├── command_request.schema.json
│   ├── health_snapshot.schema.json
│   └── audit_event.schema.json
├── data/
│   ├── README.md
│   ├── raw/            # immutable; normally excluded from Git
│   ├── interim/
│   ├── processed/
│   ├── external/
│   └── synthetic/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── hardware/
│   ├── data_quality/
│   ├── model/
│   ├── clinical_safety/
│   ├── dashboard/
│   ├── orchestration/
│   ├── security/
│   └── end_to_end/
├── scripts/
│   ├── hardware/
│   ├── acquisition/
│   ├── dataset/
│   ├── train/
│   ├── evaluate/
│   ├── deploy/
│   ├── operations/
│   ├── maintenance/
│   └── audit/
├── docs/
│   ├── architecture/
│   ├── protocols/
│   ├── evidence/
│   │   ├── evidence_ledger.md
│   │   └── literature_matrix.csv
│   ├── decisions/
│   ├── clinical/
│   ├── regulatory/
│   ├── security/
│   ├── user_guides/
│   └── agents/
├── deploy/
│   ├── systemd/
│   ├── containers/
│   ├── reverse_proxy/
│   └── observability/
├── runbooks/
│   ├── operations/
│   ├── training/
│   ├── maintenance/
│   └── diagnostics/
├── risk/
│   ├── risk_register.csv
│   ├── hazard_log.csv
│   ├── threat_model.md
│   └── privacy_impact_assessment.md
├── reports/
│   ├── audits/
│   ├── experiments/
│   ├── validation/
│   ├── model_cards/
│   └── data_sheets/
└── artifacts/
    ├── models/
    ├── metrics/
    ├── figures/
    ├── manifests/
    └── checksums/
```

---

# 8. Multi-agent operating model

## 8.1 Master orchestrator

The `MASTER_ORCHESTRATOR` owns sequencing, traceability, conflict resolution, and stage gates. It delegates specialised tasks but does not accept specialist claims without evidence.

### Required first response to every task

```yaml
mode: BUILD | AUDIT | REPAIR | VALIDATE | CONTINUE
current_gate: G0-G8
objective: concise task objective
assumptions:
  - explicit assumption
unknowns:
  - material unknown
agents_activated:
  - agent_id
files_to_inspect:
  - path
commands_to_run:
  - command
outputs:
  - expected artifact
acceptance_evidence:
  - required proof
safety_constraints:
  - constraint
```

### Orchestrator rules

- Read existing evidence before creating new claims.
- Prefer small, testable changes.
- Keep raw data immutable.
- Record every consequential design decision in an architecture decision record.
- Maintain a requirements traceability matrix from intended use to requirement, implementation, verification, validation, risk control, and evidence.
- Stop when required evidence is unavailable.
- Escalate contradictions between technical performance and clinical safety.
- Never let the ML agent choose clinical labels alone.
- Never let the clinical agent approve RF compliance.
- Never let the deployment agent promote a model that the evaluation agent has not approved.

## 8.2 Agent handoff contract

Every agent writes a handoff in YAML.

```yaml
handoff_id: UUID
agent_id: RF_ARCHITECT
timestamp_utc: ISO-8601
task:
  objective: string
  scope: string
inputs:
  files: []
  data_versions: []
  model_versions: []
  assumptions: []
work_performed:
  commands: []
  files_changed: []
  analyses: []
findings:
  confirmed: []
  uncertain: []
  defects: []
risks:
  new: []
  changed: []
evidence:
  logs: []
  reports: []
  plots: []
  checksums: []
decision:
  status: PASS | CONDITIONAL | FAIL | BLOCKED
  rationale: string
next_actions:
  required: []
  optional: []
reviewers_required: []
```

---

# 9. Agent roster and charters

## A00. MASTER_ORCHESTRATOR

**Mission:** Direct the programme, enforce gates, integrate specialist outputs, and prevent unsupported claims.

**Primary outputs:**

- Programme plan.
- Prioritised backlog.
- Gate review reports.
- Decision register.
- Requirements traceability matrix.
- Consolidated evidence package.

**Stop conditions:**

- Intended use is ambiguous.
- Ethics or RF authorisation is absent for the proposed activity.
- Dataset provenance is unknown.
- Test leakage is suspected.
- Hardware safety is uncertain.
- Clinical claims exceed evidence.

---

## A01. EVIDENCE_AND_LITERATURE_AGENT

**Mission:** Maintain a living, critical evidence base across RF sensing, Wi-Fi CSI, fall detection, fall-risk prediction, gerontology, rehabilitation, clinical guidelines, and regulation.

**Required methods:**

1. Prefer guidelines, systematic reviews, prospective cohorts, external validation studies, and official technical documentation.
2. Record study population, setting, sample size, label definition, hardware, frequency, bandwidth, split strategy, prevalence, metrics, external validation, and limitations.
3. Distinguish:
   - staged fall detection;
   - retrospective faller classification;
   - prospective future-fall prediction;
   - near-fall detection;
   - imminent-fall prediction.
4. Assign evidence confidence:
   - A: guideline or high-quality systematic review;
   - B: prospective multi-site study or external validation;
   - C: prospective single-site study;
   - D: retrospective or cross-sectional study;
   - E: laboratory proof of concept;
   - F: preprint, simulation, vendor claim, or unverified result.
5. Never transfer results from young staged-fall volunteers directly to frail older populations.

**Outputs:**

- `docs/evidence/literature_matrix.csv`
- `docs/evidence/evidence_ledger.md`
- Critical synthesis.
- Research gap map.
- Source-to-requirement links.

**Acceptance criteria:**

- Every clinical predictor has a source and rationale.
- Every performance claim records the evaluation design.
- Current guidelines and regulation are date-checked.
- Conflicting evidence is represented, not averaged away.

---

## A02. CLINICAL_INTENDED_USE_AND_SAFETY_AGENT

**Mission:** Define safe clinical purpose, workflows, hazards, outcomes, escalation pathways, and human oversight.

**Responsibilities:**

- Co-design with clinicians, aged-care staff, physiotherapists, occupational therapists, nurses, patients, carers, human-factors specialists, and Aboriginal and Torres Strait Islander health representatives where relevant.
- Define exactly who uses the output, for what decision, at what time, and with what alternative information.
- Define alert response protocols and acceptable alert burden.
- Define ground truth and event adjudication.
- Maintain a clinical hazard log.
- Prevent treatment recommendations from being generated directly by the model.
- Link risk contributors to guideline-supported assessment or intervention categories, while leaving selection to clinicians.

**Clinical safety constraints:**

- A fall alert is not proof of injury.
- Absence of an alert is not proof of safety.
- Risk categories must not replace multifactorial assessment.
- A resident in aged care may already be considered high risk; the model's value may be prioritisation, trajectory, and modifiable-factor detection rather than binary screening [R1, R2].
- Dignity, autonomy, consent, and the right to decline monitoring must be preserved.
- Monitoring must not justify restrictive practice without separate lawful clinical assessment.

**Outputs:**

- Intended-use statement.
- Clinical workflow map.
- Hazard log.
- Alert response protocol.
- Clinical evaluation protocol.
- Human-factors requirements.
- Clinician-facing model card.

---

## A03. RF_SYSTEMS_ARCHITECT_AGENT

**Mission:** Design the RF sensing architecture from propagation physics through antenna placement, waveform, receiver topology, interference, calibration, and coverage.

**Responsibilities:**

- Link required motion scales to wavelength, bandwidth, coherent processing interval, aperture, and SNR.
- Select active SDR, ambient Wi-Fi, or hybrid mode.
- Define centre frequency, occupied bandwidth, sample rate, frame rate, transmit duty cycle, gain, antenna type, polarisation, geometry, and room coverage.
- Model direct-path leakage, multipath, near-field effects, Fresnel zones, body blockage, and static clutter.
- Define calibration procedures.
- Define coexistence tests with Wi-Fi.
- Specify when a second receiver or additional node is required.

**Required analyses:**

- Link budget.
- Receiver saturation margin.
- Thermal-noise and quantisation budget.
- Dynamic range.
- Expected Doppler range for target activities.
- Coherence and phase stability.
- Range or delay resolution where applicable.
- Coverage and blind-zone map.
- Antenna placement sensitivity.

**Outputs:**

- System architecture.
- RF configuration schema.
- Antenna and room-layout plan.
- Link budget.
- Calibration plan.
- RF risk controls.
- Upgrade decision tree.

---

## A04. SDR_HARDWARE_AND_BRINGUP_AGENT

**Mission:** Make the N210/UBX-40 chain safe, measurable, repeatable, and observable.

**Baseline commands:**

```bash
uhd_find_devices
uhd_usrp_probe --args="addr=${USRP_ADDR:-192.168.10.2}"
ip link show "${USRP_NIC:-ens33}"
ethtool "${USRP_NIC:-ens33}"
ping -c 20 "${USRP_ADDR:-192.168.10.2}"
uhd_benchmark_rate \
  --args="addr=${USRP_ADDR:-192.168.10.2}" \
  --rx_rate 20e6 \
  --tx_rate 20e6 \
  --duration 60
```

Use the current UHD syntax available on the installed release. Capture version information:

```bash
uhd_config_info --version
gnuradio-config-info --version
python --version
uname -a
```

**Bring-up sequence:**

1. Inventory serial numbers, revisions, daughterboard, firmware, FPGA image, antennas, cables, attenuators, filters, and power supply.
2. Confirm Gigabit Ethernet negotiation.
3. Benchmark receive-only, transmit-only, and full-duplex streaming.
4. Conducted loopback through a suitable attenuator chain.
5. Verify frequency, gain, sample rate, clipping, noise floor, and known-tone recovery.
6. Move to low-power over-the-air tests after compliance approval.
7. Measure direct leakage with no person present.
8. Measure static-room stability.
9. Measure controlled movement response.
10. Save logs, IQ snapshots, PSD plots, and configuration manifests.

**Never do:**

- Direct cable TX to RX without attenuation.
- Begin at high gain.
- Ignore UHD overflow or underflow messages.
- Assume the GUI is evidence.
- Change firmware or FPGA images without recording versions and rollback.
- Transmit on an unapproved centre frequency or power.

**Acceptance criteria:**

- Zero unexplained overflows or underflows during the benchmark interval.
- No ADC clipping in the intended geometry.
- Known tone or waveform detected at expected offset and power trend.
- Repeated runs have bounded noise-floor and amplitude variation.
- Full-duplex path correctly uses TX/RX and RX2.
- Hardware manifest and checksums archived.

---

## A05. WAVEFORM_AND_CHANNEL_ESTIMATION_AGENT

**Mission:** Create repeatable sensing waveforms and convert raw IQ or Wi-Fi packets into physically meaningful channel measurements.

**Waveform candidates:**

1. Repeated single tone for early Doppler and phase experiments.
2. Multitone waveform for frequency-selective channel change.
3. PN or Zadoff-Chu-like sequence for timing and channel impulse response.
4. Custom OFDM with known pilots for channel-frequency response.
5. IEEE 802.11 packet capture and long-training-field channel estimation where feasible.

**Recommendation:**

- Begin with a low-complexity single tone or multitone to validate motion sensitivity.
- Progress to pilot-rich OFDM for subcarrier channel estimation.
- Treat raw 802.11 decoding as a separate engineering workstream.

**Required processing:**

- Packet/frame detection.
- Coarse and fine timing.
- Carrier-frequency offset correction.
- Sampling-frequency offset correction where relevant.
- Automatic-gain-control state capture if accessible.
- Channel estimation.
- Phase unwrapping and sanitisation.
- Static-path subtraction or high-pass clutter filtering.
- Missing-frame handling.
- Quality scores.

**Outputs:**

- Reusable waveform generator.
- Channel-estimation library.
- Synthetic reference signals.
- Unit tests with known impairments.
- Estimation-error report.
- Runtime quality flags.

---

## A06. DATA_PROTOCOL_ETHICS_AND_ANNOTATION_AGENT

**Mission:** Design ethical, representative, leakage-resistant data collection and annotation.

**Required protocol layers:**

### Layer 1: Bench and phantom validation

- Known mechanical motion.
- Pendulum, rotating reflector, linear translation stage, or repeatable actuator.
- Known speed, displacement, and timing.
- No human participants.

### Layer 2: Healthy adult controlled activities

- Walking at varied speeds.
- Sitting and standing.
- Lying down normally.
- Picking up objects.
- Kneeling.
- Slips, trips, stumbles, and recoveries simulated safely.
- Staged falls with mats and trained supervision.

### Layer 3: Older adult functional assessment

- No induced falls.
- Clinician-approved mobility tasks.
- Timed Up and Go-like sequence.
- Sit-to-stand.
- Turning.
- Comfortable walking.
- Use of usual mobility aids.
- Balance tasks only where clinically safe and approved.

### Layer 4: Silent observational deployment

- No active alerts initially.
- Natural daily activities.
- Prospective incident capture.
- Clinical or care-record adjudication.
- Privacy-preserving contextual annotation.

### Layer 5: Prospective clinical evaluation

- Locked model.
- Defined workflow.
- Human-factors evaluation.
- Pre-specified outcomes and analysis.

**Ground truth hierarchy:**

1. Multi-rater adjudication using synchronised reference sensors and event records.
2. Single expert adjudication with synchronised reference.
3. Structured protocol label.
4. Self-report or care-record label.
5. Weak or inferred label.

The model must know the label-quality tier.

**Critical split rules:**

- Assign participant, site, room, device, and time blocks before windowing.
- All overlapping windows from a source recording remain in one partition.
- No participant appears in both development and independent evaluation sets unless the purpose is explicitly personalisation testing.
- Keep an untouched external-site test set.
- Maintain a prospective temporal test set.
- Document all exclusions.

**Dataset representativeness:**

Include variation in:

- Age and functional ability.
- Body size and clothing.
- Mobility aids.
- Gait impairments.
- Room size and layout.
- Bed and chair types.
- Antenna geometry.
- Doors opening.
- Visitors, staff, pets, fans, curtains, and moving equipment.
- Single-person and multi-person conditions.
- Different Wi-Fi traffic loads and interference states.
- Line-of-sight and non-line-of-sight.
- Day and night.

**Outputs:**

- Ethics-ready protocol.
- Participant information and consent requirements.
- Data-management plan.
- Annotation ontology.
- Dataset card.
- Split manifest.
- Adjudication guide.
- Data-quality report.

---

## A07. SIGNAL_PROCESSING_AND_FEATURE_AGENT

**Mission:** Produce robust, interpretable, and learnable representations while preserving raw data.

**Candidate representations:**

### Raw and channel-domain

- Complex IQ.
- Channel-frequency response.
- Channel impulse response.
- Subcarrier amplitude.
- Sanitised phase.
- Differential phase where multiple coherent channels become available.
- CSI ratios.
- Principal components.

### Time-frequency and motion-domain

- Short-time Fourier transform.
- Doppler spectrogram.
- Continuous wavelet transform.
- Cadence-velocity diagram.
- Autocorrelation.
- Energy and entropy trajectories.
- Motion onset and offset.
- Velocity and acceleration proxies.
- Transition duration.
- Periodicity and gait-cycle stability.

### Longitudinal mobility features

- Walking-bout count and duration.
- Estimated gait speed trend.
- Cadence trend.
- Stride or step-time variability proxy.
- Turning frequency and duration.
- Sit-to-stand duration.
- Stand-to-sit control proxy.
- Bed and chair exit frequency.
- Night-time mobility.
- Activity fragmentation.
- Sedentary duration.
- Day-to-day variability.
- Deviation from personal baseline.
- Recovery after illness or hospitalisation.
- Missingness and signal-quality burden.

**Processing requirements:**

- Filtering parameters must be configurable and recorded.
- Fit PCA, scalers, imputers, and feature selection only on training data.
- Include signal-quality features so the model can abstain.
- Compare physics-based and learned representations.
- Validate extracted measures against reference instruments where possible.
- Quantify measurement error and repeatability.

**Outputs:**

- Reproducible preprocessing pipeline.
- Feature definitions and units.
- Validation against controlled motion.
- Ablation study.
- Feature stability report.

---

## A08. ACTIVITY_AND_FALL_DETECTION_ML_AGENT

**Mission:** Build clinically relevant activity and fall-event models without leakage or brittle shortcut learning.

**Baseline ladder:**

1. Rule-based energy and Doppler thresholds.
2. Logistic regression.
3. Random forest or gradient boosting.
4. 1D CNN.
5. Temporal convolutional network.
6. CNN-LSTM or GRU.
7. Compact transformer.
8. Self-supervised encoder plus calibrated task head.
9. One-class or anomaly-detection model for rare or unknown falls.
10. Ensemble only if it improves external performance and remains deployable.

**Required modelling choices:**

- Hierarchical classification:
  1. no motion versus motion;
  2. normal versus potentially hazardous;
  3. activity class;
  4. probable fall versus fall-like event.
- Explicit unknown or abstain class.
- Temporal state machine to suppress impossible transitions.
- Event aggregation across windows.
- Optional multi-node fusion.
- Cost-sensitive learning, not artificial balancing alone.
- Hard-negative mining using lying down quickly, sitting abruptly, kneeling, dropped objects, staff assistance, bed making, and mobility aids.

**Fall detector evaluation:**

- Event-level sensitivity.
- Event-level positive predictive value.
- False alerts per resident-day and per room-day.
- Detection latency.
- Alert delivery latency.
- Missed event review.
- Performance by fall direction, occlusion, room, participant, mobility aid, and multi-person condition.
- Confidence interval by participant or event cluster.
- Calibration.
- Failure-mode catalogue.

**Prohibited shortcuts:**

- Random sample split.
- Reporting window accuracy as event accuracy.
- Evaluating on equal fall and non-fall prevalence only.
- Selecting threshold on the final test set.
- Using floor impact sound or video-derived artefacts unless explicitly intended.
- Treating a staged young-adult fall as equivalent to an older adult's real fall.

**Outputs:**

- Baseline report.
- Model card.
- Locked threshold policy.
- External evaluation report.
- Error-analysis dashboard.
- Edge deployment benchmark.

---

## A09. FALL_RISK_AND_CLINICAL_FUSION_AGENT

**Mission:** Build transparent, calibrated, longitudinal risk profiles that combine RF-derived mobility with clinically credible variables.

## 9.1 Risk profile domains

The profile must store values, timestamps, source, units, data quality, missingness, and whether the factor is potentially modifiable.

| Domain | Candidate variables | Rationale and cautions |
|---|---|---|
| Fall history | Falls in previous 12 months, recurrent falls, injurious falls, near-falls, circumstances, location, time, recovery | Previous falls are highly relevant, but recall can be incomplete. Verify with incident records where possible. |
| Mobility and balance | Gait speed, cadence, variability, asymmetry, turning, transfers, TUG-like phases, walking-aid use, balance assessment | Guidelines emphasise gait, balance, strength, and functional mobility. RF proxies require validation against reference measures [R1, R2]. |
| Functional status | ADLs, transfer assistance, continence-related transfers, recent decline, frailty measure, chair-rise ability | Functional decline can be more informative than a static score. |
| Medication | Fall-risk-increasing drugs, sedatives, hypnotics, opioids, benzodiazepines, antipsychotics, antidepressants, selected cardiovascular medicines, polypharmacy, dose changes, new medicines | Medication review must be conducted by qualified clinicians. The system should flag change and association, not recommend unilateral cessation [R1]. |
| Cardiovascular | Orthostatic blood pressure, syncope, dizziness, palpitations, arrhythmia history | Requires clinical measurement and interpretation. |
| Neurological | Stroke, Parkinsonism, neuropathy, seizure history, cognitive impairment, delirium | Diagnosis is external clinical data, not inferred from RF alone. |
| Musculoskeletal | Pain, arthritis, weakness, lower-limb impairment, prior fracture | May affect gait and transfers. |
| Vision and hearing | Visual impairment, cataract status, hearing impairment, recent change | Include only current, clinically recorded information. |
| Feet and footwear | Foot pain, deformity, footwear suitability, podiatry findings | Usually clinician or allied-health entered. |
| Continence | Urgency, nocturia, toileting assistance, night-time transfer frequency | Avoid stigmatising presentation. |
| Sleep and fatigue | Sleep disruption, night-time wandering, daytime inactivity, sedating medication, fatigue | RF can estimate patterns, not sleep stages unless validated. |
| Nutrition and bone health | Weight loss, malnutrition risk, vitamin D status where clinically indicated, osteoporosis, fracture risk | The dashboard should reference assessment categories, not prescribe supplements. |
| Acute change | Infection, post-operative state, hospital discharge, new confusion, recent illness | Dynamic risk models should treat acute change as time-varying. |
| Environment | Lighting, clutter, floor hazards, bathroom configuration, bed/chair height, footwear access, mobility aid placement | Environmental review must be human-verified. |
| Care context | Supervision, transfer plan, call-bell access, response time, staffing context | Sensitive operational variables require careful governance. |
| RF longitudinal markers | Activity decline, slower transfers, increased variability, unstable turns, increased night exits, reduced walking, near-fall signatures, personal-baseline deviation | Use trends and uncertainty. Do not label disease from these features. |
| Preferences and goals | Desired independence, privacy preferences, accepted monitoring zones, care goals | Required for person-centred use. |

## 9.2 Model architecture

Use a staged modelling strategy.

### Baseline clinical model

Develop an interpretable model with pre-specified variables:

- Regularised logistic regression for a fixed horizon.
- Discrete-time survival model for multiple horizons.
- Cox or flexible parametric survival model where assumptions are appropriate.
- Recurrent-event model when repeated falls are the outcome.
- Competing-risk methods where death or permanent transition materially affects observation.

### RF mobility model

Use validated longitudinal RF features or an encoder that produces a mobility embedding. Test whether it adds value beyond the clinical baseline.

### Fusion model

Prefer late fusion initially:

```text
clinical baseline probability
+ RF mobility summary
+ recent trajectory
+ signal quality and missingness
+ site/resident random effects where justified
= calibrated horizon-specific risk
```

Only use complex deep multimodal fusion after demonstrating incremental value over simpler models.

### Personal baseline layer

Compute deviations from the individual's stable baseline:

- robust z-scores;
- exponentially weighted trends;
- Bayesian change points;
- state-space models;
- clinically reviewed threshold crossings.

Personalisation must not hide population-level bias or remove external evaluation.

## 9.3 Required outputs

For each horizon:

```json
{
  "risk_horizon_days": 30,
  "estimated_probability": 0.18,
  "uncertainty_interval": [0.11, 0.27],
  "calibration_version": "site_external_v1",
  "data_sufficiency": "adequate",
  "rf_signal_quality": 0.93,
  "trajectory": "increasing",
  "top_contributors": [
    {
      "factor": "sit_to_stand_duration_trend",
      "direction": "higher risk",
      "modifiable": "possibly",
      "evidence_source": "RF longitudinal"
    }
  ],
  "limitations": [
    "No valid orthostatic blood pressure measurement in the current review period"
  ],
  "recommended_action_type": "clinical review",
  "not_a_diagnosis": true
}
```

Do not present feature attribution as causal explanation. Label it as model contribution.

## 9.4 Prediction evaluation

Required:

- AUROC.
- Area under the precision-recall curve.
- Calibration plot.
- Calibration intercept and slope.
- Brier score.
- Horizon-specific sensitivity and PPV.
- Decision-curve net benefit.
- Risk distribution by outcome.
- Reclassification and incremental value over the baseline model.
- External-site evaluation.
- Temporal evaluation.
- Subgroup performance and uncertainty.
- Sensitivity to missing data.
- Clinical alert workload.

Accuracy and F1 are insufficient for clinical risk prediction. Follow TRIPOD+AI for reporting and PROBAST+AI for bias and applicability assessment [R17, R18].

---

## A10. BIOSTATISTICS_AND_VALIDATION_AGENT

**Mission:** Protect the project from optimistic bias, inadequate sample size, invalid inference, and misleading metrics.

**Responsibilities:**

- Write a statistical analysis plan before final evaluation.
- Define unit of analysis: window, event, participant-day, participant, or site.
- Account for repeated measures and clustering.
- Estimate effective sample size, not only number of windows.
- Plan sample size from event count, model complexity, calibration precision, and site heterogeneity.
- Use nested cross-validation only inside development data.
- Use participant-grouped bootstrapping for confidence intervals.
- Predefine thresholds based on clinical utility and alert capacity.
- Compare against strong simple baselines.
- Test calibration transportability.
- Quantify incremental value of RF data over clinical data.
- Perform decision-curve analysis.
- Conduct missing-data analysis.
- Audit fairness and subgroup uncertainty.
- Maintain a locked evaluation script.

**Required validation hierarchy:**

1. Internal grouped validation.
2. Leave-one-participant-out sensitivity analysis.
3. Leave-one-room or environment-out.
4. Leave-one-device/configuration-out.
5. Temporal holdout.
6. External-site validation.
7. Silent prospective validation.
8. Interventional clinical evaluation.

**Acceptance criteria:**

- Test set never used for design.
- Confidence intervals reflect clustering.
- Prevalence in deployment is represented.
- Calibration is acceptable at clinically relevant thresholds.
- Net benefit exceeds relevant alternatives.
- The evaluation report includes all exclusions and failed analyses.

---

## A11. DATA_ENGINEERING_AND_MLOPS_AGENT

**Mission:** Build immutable, versioned, reproducible data and model pipelines.

**Required properties:**

- Raw RF data is write-once.
- Every recording has a manifest and checksum.
- Dataset versions are content-addressed or managed with DVC, lakeFS, or equivalent.
- Configurations are YAML or TOML, not hidden constants.
- Every training run records code commit, data version, seed, environment, config, metrics, and artefact hash.
- Pipelines are restartable and idempotent.
- Schema validation occurs at ingestion.
- Model registry separates research, candidate, silent, and approved states.
- CI executes unit tests, linting, type checking, security checks, and a small deterministic training smoke test.
- Production inference is deterministic within documented tolerances.
- Logs never contain direct patient identifiers.

**Suggested stack:**

- Python 3.11 or a pinned supported version.
- `uv` or Poetry for dependencies.
- NumPy, SciPy, pandas or Polars.
- PyTorch.
- scikit-learn.
- MLflow or an equivalent experiment registry.
- DVC for data manifests where suitable.
- Pydantic for schemas.
- FastAPI for services.
- PostgreSQL for structured metadata.
- Object storage for raw recordings.
- Prometheus and Grafana for operational metrics.
- Docker or Podman for reproducible services.

Choose the smallest stack that meets requirements.

---

## A12. SECURITY_PRIVACY_AND_REGULATORY_AGENT

**Mission:** Apply privacy by design, cybersecurity engineering, RF compliance, research governance, and medical-device pathway planning.

**Privacy controls:**

- Data minimisation.
- Separate identity-linkage service.
- Pseudonymised research IDs.
- Explicit purpose and retention schedule.
- Consent and withdrawal workflow.
- Role-based access.
- Encryption in transit and at rest.
- Audit trail.
- Controlled export.
- Privacy impact assessment.
- No RF-based identity recognition unless separately justified and approved.
- No inference of intimate or unrelated behaviour.
- Zone-level privacy controls, pause function, and visible status.

Australian Privacy Principles govern collection, use, disclosure, security, access, and correction of personal information. Updated APP guidance should be reviewed during design [R8]. Automated-decision transparency obligations commencing in December 2026 may also be relevant to significant decisions [R9].

**Cybersecurity controls:**

- Threat model using STRIDE or equivalent.
- Secure boot and signed artefacts where supported.
- Secrets outside source control.
- Mutual authentication for sensors.
- Device inventory and certificate rotation.
- Network segmentation.
- Software bill of materials.
- Dependency and container scanning.
- Signed model artefacts.
- Replay and tamper detection.
- Denial-of-service and jamming monitoring.
- Safe degradation if connectivity fails.
- Incident response and vulnerability disclosure process.

**Regulatory controls:**

- Intended-purpose analysis.
- TGA software and AI pathway assessment.
- Essential Principles mapping.
- Medical-device risk management aligned with ISO 14971.
- Software lifecycle planning aligned with IEC 62304 where applicable.
- Usability engineering aligned with IEC 62366-1 where applicable.
- Quality-management pathway aligned with ISO 13485 where applicable.
- Clinical evidence plan.
- Post-market and change-control concept.
- ACMA LIPD and technical-standard review before transmission.
- ARPANSA RF exposure review.
- Human research governance under the NHMRC National Statement.

**Outputs:**

- Regulatory determination memo.
- Privacy impact assessment.
- Threat model.
- Cybersecurity plan.
- RF compliance checklist.
- Standards applicability matrix.
- Security verification report.

---

## A13. CLINICIAN_UX_AND_INTEROPERABILITY_AGENT

**Mission:** Turn model outputs into usable, non-coercive, auditable clinical decision support.

**Dashboard must show:**

- Current risk by defined horizon.
- Trend over time.
- Data-quality and coverage status.
- Recent probable falls and near-fall-like events.
- Changes in mobility markers.
- Clinical variables that are missing or stale.
- Model contributors labelled as associations, not causes.
- Uncertainty.
- Model version.
- Last successful sensor contact.
- Clinician acknowledgement and action record.
- Clear limitations.

**Dashboard must not show:**

- A single unexplained red score.
- Treatment prescriptions generated by the model.
- “Safe” status based on no recent alert.
- False precision.
- Permanent labels such as “faller” without context.
- Sensitive behavioural inferences unrelated to falls.

**Interoperability:**

Evaluate HL7 FHIR resources such as:

- `Patient`
- `Device`
- `Observation`
- `DetectedIssue`
- `RiskAssessment`
- `CarePlan`
- `Provenance`
- `AuditEvent`

Use terminology mappings and local governance. Do not place raw RF data in the clinical record.

**Human-factors tests:**

- Time to interpret.
- Correct understanding of probability and uncertainty.
- Alert acknowledgement.
- Escalation correctness.
- Alarm fatigue.
- Trust calibration.
- Override and disagreement recording.
- Accessibility.
- Workflow fit during busy periods.

---

## A14. DEPLOYMENT_AND_MONITORING_AGENT

**Mission:** Deploy safely, monitor drift and reliability, and provide rollback.

**Deployment stages:**

1. Offline replay.
2. Lab real-time.
3. Controlled room real-time.
4. Silent field deployment.
5. Clinician-visible but non-actionable pilot.
6. Controlled decision-support evaluation.
7. Broader deployment only after approval.

**Operational metrics:**

- Sensor uptime.
- Packet or sample loss.
- RF interference.
- Saturation.
- Signal-quality distribution.
- Coverage gaps.
- Inference latency.
- Alert latency.
- False alerts per resident-day.
- Model abstention.
- Feature drift.
- Calibration drift.
- Data missingness.
- Service errors.
- Clinician acknowledgements.
- Overrides and disagreements.

**Rollback triggers:**

- Alert rate exceeds the approved budget.
- Signal-quality failure is systematic.
- Model artefact hash is unexpected.
- Calibration materially degrades.
- Critical subgroup performance is unsafe.
- Cybersecurity incident.
- Incorrect identity-room association.
- Unexplained data pipeline change.

---

## A15. RED_TEAM_AND_INDEPENDENT_AUDIT_AGENT

**Mission:** Attempt to falsify performance and safety claims.

**Attack surfaces:**

- Train-test leakage.
- Duplicate recordings.
- Subject identity shortcuts.
- Room or antenna-position shortcuts.
- Time-of-day shortcuts.
- Mat or staged-fall artefacts.
- Video or audio leakage.
- Background people.
- Pets.
- Dropped objects.
- Bed making.
- Wheelchairs and walking frames.
- Staff assisting a resident.
- Two people crossing.
- Person outside the monitored zone.
- Router rate adaptation.
- Wi-Fi channel switch.
- Interference and jamming.
- Sensor disconnection.
- Clock drift.
- ADC clipping.
- Gain changes.
- Firmware update.
- Missing clinical values.
- Stale medication list.
- Demographic subgroup imbalance.
- Dashboard misinterpretation.
- Alert fatigue.

**Outputs:**

- Reproducible defect report.
- Severity and likelihood.
- Exploit or failure demonstration.
- Required risk control.
- Regression test.
- Residual-risk decision.


## A16. OPERATIONS_DASHBOARD_AND_CONTROL_PLANE_AGENT

**Mission:** Build the secure one-stop operations interface used to start, stop, inspect, maintain, train, recalibrate, and troubleshoot the platform.

**Responsibilities:**

- Build the dashboard frontend and backend control plane.
- Define the platform state machine and service dependencies.
- Map every state-changing button to a versioned, validated workflow.
- Implement preconditions, postconditions, timeouts, cancellation, rollback, and audit logging.
- Integrate systemd-managed services without running the web application as root.
- Implement live host, service, acquisition, USRP, model, data, and alert telemetry.
- Implement role-based permissions and two-person approval for high-risk actions where required.
- Prevent conflicting operations, such as training against a dataset that is still being mutated or starting two acquisition processes against the same USRP.
- Provide a read-only simulation mode and a dry-run preview for every workflow.
- Maintain accessibility, responsive layout, keyboard operation, and clear degraded-state communication.

**Non-negotiable control principle:**

A dashboard button must never contain an arbitrary shell string. It invokes a named, allowlisted action or a signed declarative workflow. The privileged control boundary must be a small root-owned service or systemd/PolicyKit integration, not the main web API.

**Required outputs:**

- Operations-dashboard architecture decision record.
- Service dependency graph.
- Platform state machine.
- Workflow schema and action registry.
- RBAC matrix.
- Dashboard wireframes and implemented panels.
- Control-plane threat model.
- End-to-end workflow tests.
- Operator and administrator runbooks.

---

## A17. CONVERSATIONAL_ORCHESTRATION_AND_TERMINAL_AGENT

**Mission:** Provide a safe chat and command interface that can explain system state, prepare plans, invoke approved tools, and stream execution results.

**Interaction modes:**

1. **Explain:** Answer questions from telemetry, logs, configurations, model cards, and approved evidence without changing system state.
2. **Plan:** Convert a natural-language request into a proposed workflow with exact steps, expected effects, permissions, risks, estimated resource demand, rollback, and required approvals.
3. **Execute:** Invoke only registered tools and workflows after authorisation and any required confirmation.
4. **Terminal:** Provide an optional administrator-only pseudo-terminal for local or tightly controlled access. It is disabled by default in clinical and remote deployments.

**Safety rules:**

- Chat cannot bypass role permissions, stage gates, RF interlocks, maintenance locks, or clinical approvals.
- Natural language is never passed directly to a shell.
- The agent must show the resolved action, arguments, target environment, and state change before execution.
- Destructive, RF-transmitting, model-promoting, data-deleting, credential-changing, or software-update actions require explicit confirmation and may require a second approver.
- Commands are executed with least privilege and finite timeouts.
- Every user instruction, tool call, command output, approval, cancellation, and final result is written to an append-only audit record.
- Patient identifiers and raw health data must not be exposed to infrastructure or general-purpose coding agents.
- The chat must distinguish observed facts from hypotheses and show the source of operational claims.

**Required outputs:**

- Tool registry.
- Intent-to-workflow resolver.
- Chat session and transcript schema.
- WebSocket event protocol.
- Command preview and approval UI.
- Terminal isolation design.
- Prompt-injection and command-injection tests.
- Audit and retention policy.


---


# 9A. Operations dashboard and administrative control plane

The dashboard is a first-class product, not a cosmetic wrapper around scripts. It must remain useful when models fail, RF data are unavailable, the USRP is disconnected, or the system is in maintenance.

## 9A.1 Reference implementation stack

Use a modular local-first architecture:

```text
Browser
  |
  | HTTPS + WebSocket
  v
Operations Dashboard UI
React + TypeScript
  |
  v
FastAPI Control API  ---------------------> PostgreSQL audit/config store
  |                    \
  |                     +------------------> WebSocket event broker
  |                     +------------------> Prometheus metrics endpoint
  |
  +--> Workflow Queue and Workers ----------> Redis or another approved broker
  |
  +--> Unprivileged tool adapters ----------> MLflow/DVC/object storage
  |
  +--> Privileged Control Helper -----------> systemd D-Bus / PolicyKit
  |                                            acquisition and inference services
  |
  +--> UHD Adapter --------------------------> Ettus N210 over dedicated Ethernet
```

Recommended baseline:

- React and TypeScript for the dashboard.
- FastAPI and Pydantic for typed APIs and schemas.
- WebSockets for live job output, alerts, logs, and health updates.
- Celery workers with `chain`, `group`, and `chord`, or an equivalently capable durable workflow engine, for multi-step and parallel jobs.
- PostgreSQL for users, permissions, configuration versions, workflow runs, approvals, audit events, and model metadata.
- Redis as a task broker and short-lived event cache, not the sole authoritative record.
- systemd units for long-running acquisition, inference, API, worker, and monitoring services.
- Prometheus and node exporter for host and service metrics; Grafana may be embedded or linked for deep diagnostics.
- `psutil` for low-latency host and process snapshots exposed by the API.
- MLflow or an equivalent registry for experiments and model lifecycle.
- DVC or immutable manifests for dataset versions.

A lightweight prototype may initially run on one Ubuntu workstation, but interfaces, schemas, audit records, and privilege boundaries must be designed so the components can later be separated.

## 9A.2 Platform state machine

The control plane must maintain one authoritative operational state:

```text
UNINITIALISED
    |
    v
STOPPED <---------> MAINTENANCE
  |                     |
  v                     |
PREFLIGHT                |
  |                      |
  v                      |
STARTING ----------------+
  |
  v
RUNNING <-----------> DEGRADED
  |                      |
  v                      v
STOPPING -------------> FAILED

Independent supervised states:
TRAINING | EVALUATING | RECALIBRATING | REPLAYING | BACKING_UP
```

Rules:

- Only one process may own the N210 at a time unless a tested architecture explicitly supports shared access.
- `RUNNING` requires healthy acquisition, preprocessing, inference, event aggregation, storage, and dashboard heartbeat.
- `DEGRADED` means the service may continue but one or more quality or redundancy criteria have failed. The dashboard must state exactly which capability is affected.
- `FAILED` must be safe: transmission stops where required, partial files are finalised or quarantined, and operators receive actionable diagnostics.
- Training, evaluation, and recalibration must not replace the active model.
- Maintenance mode blocks live detection start until released by an authorised user.
- Every transition has allowed source states, required role, preconditions, timeout, postconditions, and rollback.

## 9A.3 Required dashboard panels

### Panel 1: Command Centre

Display:

- Current state and environment.
- Active project configuration.
- Detection mode: `LIVE_SDR`, `COMMODITY_CSI`, `REPLAY`, `SIMULATION`, or `DISABLED`.
- Active RF profile, model version, dataset version, and configuration hash.
- Start time, uptime, last heartbeat, last event, and last successful recording.
- System-wide data-quality and coverage indicators.
- Active maintenance lock, experiment lock, or clinical deployment lock.

Controls:

- **Preflight Check**.
- **Start Detection**.
- **Graceful Stop**.
- **Pause Alerts** without discarding data, subject to clinical policy.
- **Restart Failed Services**.
- **Enter Maintenance Mode**.
- **Emergency Stop RF and Detection**.
- **Switch to Replay or Simulation**.

The primary start and stop controls must be visually distinct and must show the exact target environment. Emergency stop must remain available when other workflows are blocked.

### Panel 2: Live Detection and Event Timeline

Display:

- Current activity state and confidence.
- Fall-event probability and event-state machine.
- Unknown or abstention state.
- Recent events and acknowledgements.
- Detection and alert latency.
- RF signal-quality timeline.
- Data gaps, packet loss, clipping, saturation, and model input validity.
- Optional privacy-preserving motion visualisation derived from features, not raw video.

Controls:

- Acknowledge alert.
- Mark event outcome under approved annotation workflow.
- Open corresponding evidence window.
- Temporarily silence duplicate notification channels without suppressing event recording.
- Escalate a system fault to the administrator.

### Panel 3: RF and USRP Control

Display:

- N210 discovery and IP reachability.
- UHD version, device serial, motherboard, FPGA image, firmware identity, and UBX subdevice.
- Configured centre frequency, sample rate, RF bandwidth, TX/RX gain, antenna ports, clock source, and time source.
- LO lock where exposed.
- Acquisition state and sample counter.
- RX overflow count, TX underflow count, late-command count, sequence discontinuities, dropped frames, and host receive-buffer pressure.
- Ethernet link rate, host interface throughput, packet loss, and round-trip time.
- Last successful `uhd_usrp_probe` and configuration-drift result.
- Spectrum, power, clipping, and noise-floor summaries.

Controls:

- Discover device.
- Run safe probe while stopped.
- Run receive-only diagnostic.
- Tune an approved RF profile.
- Apply an approved gain profile.
- Start a controlled calibration capture.
- Reset runtime counters.
- Restart the acquisition service.

**Hardware truth:** The N210 is an FPGA-based radio peripheral, not a general-purpose Linux host. It does not expose an application process list, host RAM utilisation, or CPU-core utilisation. Do not fabricate these fields. During streaming, prefer telemetry emitted by the acquisition process and UHD asynchronous metadata; a full probe may be disruptive and should normally run only while stopped.

### Panel 4: Workstation and Service Health

Display at one-second to five-second cadence, with longer-term trends stored separately:

- Physical cores, logical CPUs, and CPUs available under process affinity or cgroup limits.
- Per-core utilisation.
- Configurable `active cores`, defined as cores above a stated utilisation threshold over a stated interval.
- Load average and run queue.
- RAM, swap, cache, and memory pressure.
- Disk capacity, inode availability, read/write throughput, I/O wait, and forecast time-to-full.
- Network throughput, errors, drops, interface state, and N210-link status.
- CPU, motherboard, disk, and GPU temperatures where available.
- GPU utilisation and memory where a supported GPU exists.
- Top processes by CPU, memory, disk I/O, and open file handles.
- Required systemd units and their active, failed, restarting, or activating state.
- Celery workers, queue depth, oldest job age, and failed-job count.
- API latency, error rates, WebSocket clients, database pool, and storage availability.
- Detection pipeline heartbeat and stage-level latency.

Controls:

- Run comprehensive health check.
- View service logs.
- Restart an allowlisted service.
- Download a redacted diagnostic bundle.
- Clear a resolved fault after verification.

### Panel 5: Model Operations

Separate **training**, **calibration**, **evaluation**, **approval**, and **deployment**.

Display:

- Active approved model and checksum.
- Candidate, silent, rejected, and archived models.
- Training dataset version and cohort summary.
- Feature schema and preprocessing version.
- Metrics with confidence intervals, calibration plots, subgroup results, failure envelope, and comparison against the approved model.
- Training job progress, GPU/CPU/RAM use, logs, checkpoints, and estimated remaining work units.
- Drift and calibration-monitoring status.

Controls:

- Validate selected dataset.
- Train candidate model.
- Resume interrupted training from an approved checkpoint.
- Evaluate candidate on locked validation data.
- Recalibrate probability outputs using a designated calibration set.
- Compare candidate with approved model.
- Run shadow or silent deployment.
- Request approval.
- Promote after approval.
- Roll back to a named previous model.

Rules:

- **Train** changes model parameters.
- **Recalibrate** changes only the probability mapping unless a separately named workflow is used.
- The test set cannot be selected for training or calibration.
- New data must pass schema, consent, provenance, label, leakage, and quality checks.
- No training or recalibration job automatically promotes a model.
- Promotion requires an immutable evaluation report, model card, approval record, and rollback target.

### Panel 6: Data, Annotation, and Retention

Display:

- Recording inventory and immutable raw-data hashes.
- Dataset versions and lineage.
- Annotation status and inter-rater agreement.
- Missing manifests, corrupt files, label conflicts, duplicate windows, and leakage risks.
- Storage usage by data class and retention deadline.
- Backup and restore verification.
- Data-access events and exports.

Controls:

- Import and validate new recordings.
- Create a frozen dataset version.
- Open annotation workflow.
- Run quality and leakage audit.
- Quarantine suspect recordings.
- Export an approved de-identified research package.
- Start backup and test restore.
- Execute approved retention or deletion workflow with required authorisation.

### Panel 7: Clinical Risk and Decision Support

This panel remains logically and permission-wise separate from infrastructure administration.

Display:

- Patient or resident selected through an authorised clinical context.
- Risk horizon and calibrated probability.
- Trend, uncertainty, data sufficiency, and stale inputs.
- RF-derived mobility changes.
- Fall history and relevant clinical contributors.
- Recent probable falls, near-fall-like events, and clinician annotations.
- Model version and limitations.
- Acknowledgement, disagreement, and action record.

Controls must support review and documentation, not autonomous treatment selection.

### Panel 8: Maintenance and Configuration

Display:

- Installed application, UHD, GNU Radio, Python, model, firmware, and FPGA versions.
- Available approved updates.
- Configuration differences from the signed baseline.
- Certificates, credential-expiry dates, storage lifecycle, backups, and log rotation.
- Hardware maintenance schedule and last verification.

Controls:

- Run dependency and vulnerability scan.
- Rotate logs.
- Clean approved temporary data.
- Verify checksums.
- Back up configuration and database.
- Restore into a test namespace.
- Apply a signed configuration bundle.
- Schedule or apply an approved software update.
- Roll back the application version.
- Run N210 network and receive-chain diagnostics.

### Panel 9: Security, Users, and Audit

Display:

- Users, roles, scopes, active sessions, failed logins, and privileged actions.
- Current deployment environment and access policy.
- Audit event stream with filters.
- Configuration and model approval history.
- Security alerts, certificate status, and integrity checks.

Controls:

- Create, disable, and role-limit users.
- Revoke sessions.
- Rotate service credentials through the approved secret-management path.
- Export signed audit reports.
- Review pending approvals.
- Lock the system for incident response.

### Panel 10: Agent Chat and Controlled Terminal

The chat window should resemble a high-quality coding-assistant interface while remaining bound to operational policy.

Required features:

- Conversation history and named sessions.
- Streaming responses and command output.
- File, log, metric, experiment, model-card, and configuration citations.
- Tool-call cards showing action, arguments, target, role, and result.
- Plan preview before state changes.
- Buttons for **Approve**, **Reject**, **Modify**, **Dry Run**, **Execute**, and **Cancel**.
- Job progress, sub-step status, and rollback status.
- Ability to ask questions such as:
  - `Why is detection degraded?`
  - `Show the processes consuming the most RAM.`
  - `Run a receive-only N210 health check.`
  - `Train a candidate using dataset v12 and compare it with the approved model.`
  - `Stop detection gracefully and archive the current session.`
- Saved, reusable prompts that resolve to versioned workflows.

The optional terminal must:

- Be administrator-only.
- Be disabled by default outside development.
- Use a restricted service account or container namespace.
- Display the current user, host, working directory, and environment prominently.
- Record input and output to the audit log.
- Block or require elevated approval for dangerous command classes.
- Never provide unrestricted root shell access through the public dashboard.

## 9A.4 Multi-command buttons as declarative workflows

Every multi-command button maps to a workflow stored under `runbooks/` and validated against `schemas/workflow.schema.json`.

Example:

```yaml
api_version: "v1"
id: "start_detection"
display_name: "Start Detection"
version: 1
safety_class: "operational"
required_scopes:
  - "detection:start"
requires_confirmation: true
requires_second_approval: false
allowed_source_states:
  - "STOPPED"
locks:
  - "usrp:n210:primary"
  - "pipeline:live-detection"
timeout_seconds: 180
parameters:
  profile:
    type: "string"
    enum: ["lab_2g4", "replay", "simulation"]
steps:
  - id: "validate_config"
    action: "config.validate"
    with:
      profile: "${parameters.profile}"
  - id: "check_storage"
    action: "host.assert_storage"
    with:
      minimum_free_gib: 50
  - id: "check_usrp"
    action: "usrp.preflight"
    when: "${parameters.profile == 'lab_2g4'}"
  - id: "start_acquisition"
    action: "service.start"
    with:
      unit: "rf-acquisition.service"
  - id: "await_acquisition"
    action: "service.await_health"
    with:
      unit: "rf-acquisition.service"
      timeout_seconds: 30
  - id: "start_inference"
    action: "service.start"
    with:
      unit: "rf-inference.service"
  - id: "verify_pipeline"
    action: "pipeline.smoke_test"
  - id: "set_running"
    action: "state.transition"
    with:
      target: "RUNNING"
rollback:
  - action: "service.stop"
    with:
      unit: "rf-inference.service"
  - action: "service.stop"
    with:
      unit: "rf-acquisition.service"
  - action: "state.transition"
    with:
      target: "FAILED"
```

Workflow requirements:

- Schema validation before execution.
- Unique run identifier and idempotency key.
- Immutable workflow version.
- Parameter type validation and approved ranges.
- Role and scope checks.
- State and resource-lock checks.
- Dry-run mode.
- Dependency graph with serial and parallel steps.
- Step-level timeout, retry, and retry backoff.
- Cancellation points.
- Captured stdout, stderr, structured events, and artefact paths.
- Explicit postconditions.
- Compensating rollback where technically safe.
- Append-only audit event for every step.
- Redaction of secrets and patient identifiers.
- No `shell: true` and no unsanitised command interpolation.

## 9A.5 Required initial workflows

### `start_detection`

1. Acquire exclusive hardware and pipeline locks.
2. Validate configuration and signed model artefact.
3. Check disk space, database, broker, and network interface.
4. Check N210 reachability and UHD compatibility when using SDR mode.
5. Verify RF profile and transmission approval.
6. Start acquisition.
7. Verify sample flow and signal quality.
8. Start preprocessing and inference.
9. Start event aggregation and notification adapters.
10. Verify end-to-end heartbeat.
11. Transition to `RUNNING` or roll back safely.

### `stop_detection_gracefully`

1. Transition to `STOPPING` and prevent new starts.
2. Stop new alert emission while retaining event records according to policy.
3. Drain inference and event queues.
4. Flush and checksum current recordings.
5. Stop inference, preprocessing, and acquisition in dependency order.
6. Persist final counters, logs, and configuration snapshot.
7. Release hardware locks.
8. Transition to `STOPPED`.

### `emergency_stop`

1. Stop TX immediately where active.
2. Stop acquisition and inference without waiting for normal draining.
3. Mark incomplete artefacts as quarantined.
4. Transition to `FAILED` or `MAINTENANCE`.
5. Notify the operator and record the reason.

### `train_candidate_model`

1. Freeze and validate the selected dataset version.
2. Run leakage, label, consent, and quality checks.
3. Resolve the approved training configuration.
4. Reserve compute resources.
5. Train with resumable checkpoints.
6. Evaluate only on designated development validation data.
7. Produce model artefact, metrics, model card draft, logs, and hashes.
8. Register as `CANDIDATE` without changing the active model.

### `recalibrate_model`

1. Verify that the selected calibration dataset is independent of training and final testing.
2. Load the immutable base model.
3. Fit the approved calibration method.
4. Compare calibration intercept, slope, Brier score, reliability, and decision thresholds.
5. Test subgroup and temporal stability.
6. Register a new calibrated candidate with linkage to the unchanged base model.
7. Require approval before deployment.

### `comprehensive_health_check`

Run independent checks in parallel where safe:

- Host resources and temperatures.
- Required processes and systemd units.
- Database, broker, storage, and API.
- Data-pipeline heartbeat and queues.
- N210 reachability, UHD discovery, device identity, and runtime counters.
- Network path and packet continuity.
- Active model integrity and registry state.
- Configuration drift.
- Security and certificate state.

Aggregate findings into `HEALTHY`, `DEGRADED`, or `FAILED`, with evidence and remediation steps.

### `restart_failed_pipeline`

Restart only failed components after dependency analysis. Do not restart a healthy acquisition process merely because a downstream UI component failed.

### `create_diagnostic_bundle`

Collect redacted versions, configuration hashes, system metrics, service states, bounded logs, USRP status, workflow history, and recent errors into a timestamped checksum-protected archive.

### `backup_and_verify`

Back up configurations, metadata, audit database, model registry metadata, and required manifests, then restore into an isolated verification namespace and report whether the restore is usable.

## 9A.6 API and event contracts

Minimum API surface:

```text
GET    /api/v1/platform/state
GET    /api/v1/platform/capabilities
POST   /api/v1/workflows/{workflow_id}/runs
GET    /api/v1/workflow-runs/{run_id}
POST   /api/v1/workflow-runs/{run_id}/cancel
POST   /api/v1/workflow-runs/{run_id}/approve
GET    /api/v1/health/host
GET    /api/v1/health/services
GET    /api/v1/health/usrp
GET    /api/v1/health/pipeline
GET    /api/v1/models
POST   /api/v1/models/train
POST   /api/v1/models/{model_id}/recalibrate
POST   /api/v1/models/{model_id}/evaluate
POST   /api/v1/models/{model_id}/request-promotion
POST   /api/v1/models/{model_id}/rollback
GET    /api/v1/datasets
POST   /api/v1/datasets/{dataset_id}/validate
GET    /api/v1/audit/events
POST   /api/v1/chat/sessions
POST   /api/v1/chat/sessions/{session_id}/messages
WS     /api/v1/ws/events
WS     /api/v1/ws/chat/{session_id}
WS     /api/v1/ws/terminal/{session_id}
```

WebSocket events must be typed and versioned:

```json
{
  "api_version": "v1",
  "event_id": "uuid",
  "timestamp": "2026-08-07T00:00:00+10:00",
  "type": "workflow.step.completed",
  "severity": "info",
  "source": "workflow-worker",
  "correlation_id": "run-uuid",
  "payload": {
    "workflow_id": "start_detection",
    "step_id": "check_usrp",
    "status": "succeeded",
    "duration_ms": 1834
  }
}
```

## 9A.7 Privilege and service-control design

The web API must run as an unprivileged account.

Use one of these controlled patterns:

- systemd D-Bus calls authorised by PolicyKit;
- a small root-owned control helper exposed over a Unix-domain socket with strict request schemas;
- narrowly scoped `sudoers` entries for fixed wrappers as a temporary laboratory implementation.

Preferred production pattern:

1. Long-running components are systemd units.
2. The API requests a named action.
3. The privileged helper validates caller identity, action, parameters, current state, and policy.
4. The helper calls systemd through D-Bus.
5. systemd tracks processes through service units and cgroups.
6. The helper returns a structured result.
7. The API records the audit event and streams progress.

Never run `sudo bash -c <user-content>` or expose `/bin/bash` through a normal API route.

## 9A.8 Role-based access matrix

Minimum roles:

| Capability | Viewer | Clinician | Operator | ML engineer | Administrator | Auditor |
|---|---:|---:|---:|---:|---:|---:|
| View de-identified system health | Yes | Limited | Yes | Yes | Yes | Yes |
| View authorised patient risk | No | Yes | Limited | No | Configurable | Audited only |
| Start or stop detection | No | No | Yes | No | Yes | No |
| Emergency stop | No | Configurable | Yes | No | Yes | No |
| Change RF configuration | No | No | Limited approved profiles | No | Yes | No |
| Train candidate model | No | No | No | Yes | Yes | No |
| Recalibrate candidate | No | No | No | Yes | Yes | No |
| Promote model | No | No | No | Request only | Approve according to governance | Verify |
| Delete governed data | No | No | No | No | Two-person workflow | Verify |
| Open restricted terminal | No | No | No | Development only | Yes | No |
| View audit trail | Limited | Own actions | Operational | Model actions | Yes | Yes |

Use fine-grained scopes such as:

```text
detection:read
detection:start
detection:stop
rf:diagnose
rf:configure-approved
model:train
model:recalibrate
model:evaluate
model:promote-request
model:promote-approve
data:export
data:delete
maintenance:execute
terminal:restricted
audit:read
```

## 9A.9 Safety, concurrency, and failure handling

- Use distributed or database-backed locks for the USRP, live pipeline, dataset mutation, active-model promotion, backup, and software update.
- A workflow that loses its worker must be recoverable from persisted step state.
- A second start request returns the existing run rather than launching duplicate services.
- Stop operations take precedence over normal start and training actions.
- Emergency stop takes precedence over every non-security workflow.
- Dashboard loss must not stop a healthy detector.
- API restart must reconstruct current state from systemd, worker state, database, and heartbeats rather than assuming `STOPPED`.
- Network loss to the dashboard must not create repeated commands when the browser reconnects.
- Model and configuration changes use compare-and-swap or version checks.
- All timestamps use UTC internally and display the configured local timezone.
- High-risk workflows require a reason and ticket or protocol reference.

## 9A.10 Dashboard acceptance criteria

The operations dashboard is not complete until all of the following pass:

1. Start detection from `STOPPED` and verify end-to-end data and inference.
2. Repeated start requests are idempotent.
3. Graceful stop flushes and checksums data.
4. Emergency stop halts RF and pipeline processes within the approved bound.
5. The dashboard accurately reports a deliberately failed service.
6. Host CPU, per-core use, RAM, disk, network, temperatures, and process data match independent command-line measurements within documented tolerance.
7. N210 health fields never claim unavailable CPU, RAM, or process information.
8. A simulated UHD overflow or recorded sequence discontinuity appears in health and audit views.
9. Train and recalibrate create candidates but cannot silently change the approved model.
10. Failed training can resume or terminate without corrupting the registry.
11. Chat can explain and plan without permission to execute.
12. Chat cannot bypass an approval, state lock, role, or parameter limit.
13. Dangerous terminal commands are blocked or require approved escalation.
14. Every button and chat-executed workflow creates a complete audit chain.
15. Browser refresh and API restart do not duplicate jobs.
16. A rollback returns the service to the last known-good model and configuration.
17. Clinical users cannot access infrastructure secrets or unrestricted terminal functions.
18. Administrators cannot access patient records unless separately authorised.
19. Diagnostic bundles contain no direct patient identifiers or secrets.
20. Accessibility and human-factors tests are passed by representative users.

## 9A.11 VS Code implementation task for the dashboard

Use this instruction after the base repository and control requirements exist:

```text
Read RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK.md in full.
Act as MASTER_ORCHESTRATOR with A16 and A17 as lead specialists.
MODE=BUILD.

Build the minimum secure operations-dashboard vertical slice.

Required scope:
1. Create the project naming configuration and ADR.
2. Implement the platform state model and workflow schemas.
3. Implement an allowlisted action registry.
4. Create systemd unit templates for acquisition, inference, API, worker, and monitoring.
5. Implement FastAPI endpoints for platform state, host health, service health,
   N210 health, workflow execution, cancellation, and audit queries.
6. Implement WebSocket streaming for workflow and health events.
7. Implement the React dashboard shell with Command Centre, System Health,
   RF/USRP, Model Operations, Maintenance, Audit, and Chat panels.
8. Implement the workflows: preflight, start detection, graceful stop,
   comprehensive health check, train candidate, and recalibrate candidate.
9. Use simulation adapters when physical hardware or training data are unavailable.
10. Add RBAC with development users and explicit scopes.
11. Add integration tests for idempotency, state locks, rollback, audit logging,
    parameter validation, privilege separation, and command injection.
12. Do not expose an unrestricted shell and do not run the API as root.
13. Return architecture, changed files, exact commands, screenshots or test
    evidence, unresolved risks, and the next smallest safe action.
```


---

# 10. Stage gates

## G0. Intended use and governance

**Pass requires:**

- Approved research purpose.
- User and decision identified.
- Products A to D separated.
- Ethics pathway defined.
- Initial TGA applicability memo.
- Privacy and RF compliance owners assigned.
- Clinical partners and escalation workflow identified.
- Hazard log opened.

## G1. Hardware integrity

**Pass requires:**

- N210 and UBX-40 inventory.
- UHD and GNU Radio versions archived.
- GigE verified.
- Streaming benchmark passed.
- Conducted loopback passed.
- No unexplained clipping, overflow, or underflow.
- RF safety and OTA test approval.


## G1A. Operations control-plane integrity

**Required evidence:**

- Platform state machine and service dependency graph.
- Privilege-boundary design and threat model.
- Signed or versioned workflow definitions.
- RBAC and approval matrix.
- Start, stop, emergency-stop, health-check, training, recalibration, and rollback integration tests.
- Audit-log completeness test.
- Dashboard-to-command injection test.
- N210 telemetry capability matrix distinguishing available, derived, and unavailable fields.

**Acceptance:**

- No dashboard endpoint or chat message can execute arbitrary shell content.
- Repeated start and stop requests are idempotent.
- Conflicting workflows are locked.
- The detector remains independent of dashboard availability.
- All privileged actions are authorised, bounded, and audited.
- Model training or recalibration cannot alter the approved model without a separate approval workflow.
- The system exposes truthful host and N210 health information.


## G2. Signal observability

**Pass requires:**

- Controlled moving target produces repeatable measurable change.
- Static baseline quantified.
- Direct leakage and noise characterised.
- Channel-estimation error quantified.
- Quality-gating logic implemented.
- Raw and derived data reproduce from manifest.

## G3. Dataset validity

**Pass requires:**

- Approved protocol.
- Annotation ontology.
- Split manifest created before modelling.
- No leakage.
- Diverse hard negatives.
- Label quality tracked.
- Dataset card and limitations.
- Realistic prevalence evaluation set planned.

## G4. Research baseline

**Pass requires:**

- Rule-based and simple ML baselines.
- Grouped internal evaluation.
- Event-level fall metrics.
- Error analysis.
- Reproducible training and evaluation.
- No claim beyond the study population.

## G5. Cross-domain robustness

**Pass requires:**

- Unseen participant evaluation.
- Unseen room or environment evaluation.
- Device/configuration sensitivity.
- Interference and multi-person tests.
- Calibration and abstention.
- Defined failure envelope.

## G6. External and prospective validation

**Pass requires:**

- Locked model.
- Independent site or temporal cohort.
- Prospective outcomes.
- Pre-specified analysis.
- Clinically realistic prevalence.
- External calibration assessment.
- Subgroup and alert-workload analysis.

## G7. Silent clinical deployment

**Pass requires:**

- Ethics and site governance.
- Cybersecurity and privacy review.
- No operational alerts.
- Incident-report adjudication.
- Coverage and uptime evidence.
- Human-factors dry run.
- Safety monitoring committee or equivalent oversight.

## G8. Controlled decision-support evaluation

**Pass requires:**

- Regulatory status resolved.
- Clinician training.
- Alert protocol and fallback.
- DECIDE-AI-aligned early clinical evaluation plan.
- Prospective safety and utility outcomes.
- Monitoring and rollback.
- Patient and carer involvement.
- No autonomous treatment.

---

# 11. RF experimental programme

## Experiment E0: Receive-chain baseline

**Purpose:** Characterise noise and environmental RF occupancy.

**Conditions:**

- Terminated input where safe and available.
- Antenna connected in empty room.
- Multiple gains.
- Multiple times of day.
- 2.4 GHz channels of interest.

**Outputs:**

- Noise floor.
- Occupancy plot.
- Interference map.
- ADC histogram.
- Gain linearity.
- Recommended initial gain.

## Experiment E1: Conducted waveform recovery

**Purpose:** Verify transmit and receive chains.

**Setup:** TX/RX to attenuator chain to RX2. Attenuation is selected from measured power and safe input levels.

**Outputs:**

- Frequency error.
- SNR.
- EVM or channel-estimation error.
- Clipping margin.
- Repeatability.
- UHD error count.

## Experiment E2: Static over-the-air channel

**Purpose:** Measure phase and amplitude stability without deliberate motion.

**Outputs:**

- Allan-like stability analysis where useful.
- Drift.
- phase noise.
- interference sensitivity.
- confidence limits for change detection.

## Experiment E3: Mechanical target

**Purpose:** Validate Doppler and displacement physics.

Use a target with known velocity or periodic motion.

**Checks:**

\[
f_D \approx \frac{2v_r}{\lambda}
\]

Compare measured and expected Doppler. Record geometry and uncertainty.

## Experiment E4: Human primitives

Record isolated primitives:

- walk toward and away;
- transverse walk;
- sit;
- stand;
- lie down;
- turn;
- bend;
- arm movement.

Vary position, orientation, speed, and range.

## Experiment E5: Fall and hard-negative protocol

Staged falls use approved safeguards. Hard negatives must outnumber fall types in scenario diversity, even if training batches later use sampling or weighting.

## Experiment E6: Room and configuration transfer

Repeat a fixed protocol across:

- rooms;
- antenna positions;
- furniture layouts;
- participants;
- channels;
- days;
- RF traffic loads.

## Experiment E7: Commodity Wi-Fi comparison

Capture the same activities using the N210 track and the commodity CSI track. Compare:

- data completeness;
- signal quality;
- feature stability;
- classification;
- compute;
- installation burden;
- cost;
- privacy;
- scalability.

---

# 12. Suggested signal and data specifications

These are starting hypotheses, not fixed truths.

## 12.1 N210 active waveform

```yaml
centre_frequency_hz: 2.437e9
sample_rate_sps: 20e6
occupied_bandwidth_hz: <= 18e6
waveform: pilot_ofdm
frame_rate_hz: 100
tx_gain_db: start_low_and_measure
rx_gain_db: start_low_and_measure
tx_port: TX/RX
rx_port: RX2
clock_source: internal
time_source: internal
capture:
  raw_iq: true
  channel_estimates: true
  metadata: true
```

The exact centre frequency and transmission parameters require current regulatory and coexistence approval.

## 12.2 Recording manifest

```yaml
recording_id: UUID
participant_id: coded_id
session_id: UUID
site_id: coded_site
room_id: coded_room
started_at_utc: ISO-8601
ended_at_utc: ISO-8601
hardware:
  usrp_model: N210
  usrp_serial: encrypted_or_restricted
  daughterboard: UBX-40
  uhd_version: string
  fpga_image_hash: sha256
rf:
  centre_frequency_hz: float
  sample_rate_sps: float
  occupied_bandwidth_hz: float
  tx_gain_db: float
  rx_gain_db: float
  tx_antenna: inventory_id
  rx_antenna: inventory_id
  geometry_file: path
environment:
  room_layout_version: string
  wifi_channel_occupancy: path
  people_count: integer
  known_movers: []
protocol:
  activity_label: string
  trial_number: integer
  scripted: boolean
  safety_supervisor: coded_id
quality:
  overflows: integer
  underflows: integer
  clipped_sample_fraction: float
  packet_or_frame_loss: float
  mean_snr_db: float
files:
  raw_iq: path
  annotations: path
checksums:
  raw_iq_sha256: string
```

## 12.3 Annotation ontology

Each event must include:

- activity.
- transition.
- direction.
- start and end.
- confidence.
- annotator.
- ground-truth source.
- assistance.
- mobility aid.
- fall direction.
- impact surface.
- recovery.
- occlusion.
- number of people.
- label-quality tier.
- notes.

Use `unknown`, `ambiguous`, and `not observable` explicitly.

---

# 13. Machine-learning design

## 13.1 Recommended first model stack

### Activity model

- Input: channel amplitude/phase or Doppler representation.
- Encoder: compact temporal convolutional network.
- Output: per-frame activity probabilities plus unknown.
- Decoder: constrained temporal state machine.

### Fall event model

- Input: 2 to 5 second multi-resolution window.
- Branch 1: Doppler-time representation.
- Branch 2: channel-change energy and duration.
- Branch 3: signal quality.
- Fusion: compact MLP or attention pooling.
- Output: fall-event probability and quality-aware abstention.
- Event logic: onset, persistence, lying-state confirmation where observable, and refractory period.

Do not require lying confirmation for all falls because a person may recover quickly, be assisted, or fall against furniture.

### Risk model

- Clinical baseline: regularised survival or discrete-time model.
- RF mobility model: longitudinal feature summaries.
- Fusion: calibrated late fusion.
- Output: horizon-specific absolute risk.

## 13.2 Self-supervised learning

Useful pretext tasks:

- masked subcarrier or time reconstruction;
- temporal order;
- contrastive augmentation;
- next-window prediction;
- cross-node agreement;
- same-activity consistency.

Augmentations must remain physically plausible. Do not use transformations that alter the meaning of Doppler direction, time scale, or phase without justification.

## 13.3 Domain robustness

Test:

- normalisation per session versus global;
- domain adversarial training;
- CORAL or feature alignment;
- meta-learning;
- test-time calibration;
- personal baseline adaptation;
- invariant physics features;
- multi-environment training.

No domain-adaptation method may access labels from the final evaluation domain unless the protocol explicitly tests supervised adaptation.

## 13.4 Uncertainty and abstention

Use one or more:

- calibrated softmax.
- conformal prediction with appropriate exchangeability assumptions.
- deep ensemble.
- Monte Carlo dropout for research comparison.
- out-of-distribution score.
- signal-quality gate.

The system must abstain when:

- signal is saturated;
- frame loss is high;
- RF configuration is unknown;
- person count exceeds validated conditions;
- input is outside the training envelope;
- risk profile is too incomplete;
- model versions are inconsistent.

---

# 14. Clinical risk-profile data model

## 14.1 Required fields

```yaml
profile_id: UUID
participant_id: coded_id
as_of_utc: ISO-8601
care_setting: home | hospital | residential_aged_care
prediction_horizons_days: [7, 30, 90, 180]
fall_history:
  falls_12m: integer_or_unknown
  recurrent_falls: boolean_or_unknown
  injurious_fall: boolean_or_unknown
  near_falls_30d: integer_or_unknown
mobility:
  walking_aid: value
  clinical_gait_measure: value_with_date
  balance_measure: value_with_date
  tug_seconds: value_with_date
  sit_to_stand: value_with_date
rf_longitudinal:
  observation_days: integer
  coverage_fraction: float
  gait_speed_proxy_trend: value
  cadence_proxy_trend: value
  gait_variability_proxy: value
  turning_duration_trend: value
  sit_to_stand_duration_trend: value
  night_exit_rate: value
  activity_fragmentation: value
  personal_baseline_deviation: value
medication:
  source_date: date
  frid_categories: []
  recent_changes: []
clinical:
  orthostatic_bp: value_with_date
  dizziness_or_syncope: value_with_date
  vision: value_with_date
  hearing: value_with_date
  cognition: value_with_date
  continence: value_with_date
  neurological_conditions: []
  musculoskeletal_conditions: []
  acute_changes: []
environment:
  assessment_date: date
  hazards: []
preferences:
  monitoring_consent: value
  excluded_zones: []
  care_goals: []
data_quality:
  completeness: float
  stale_fields: []
  conflicting_fields: []
provenance:
  sources: []
```

## 14.2 Data governance

- Separate source observations from derived features.
- Never overwrite history.
- Every correction creates a new version.
- Record who entered or confirmed clinical data.
- Record consent and legal authority.
- Use local terminology services where integrated with a health record.
- Maintain provenance for model inputs and outputs.

---

# 15. Clinical decision-support output and action mapping

The dashboard may map contributors to **review categories**, not treatments.

| Observed pattern | Permitted support output | Prohibited output |
|---|---|---|
| Increased transfer duration | “Consider clinical review of transfers, strength, pain, and assistance needs.” | “Start strength programme X.” |
| New night-time exits | “Review toileting, sleep, environment, medication changes, and supervision needs.” | “Restrict bed exit.” |
| Recent medication change plus mobility decline | “Medication and clinical review may be warranted.” | “Stop medication.” |
| Increased dizziness recorded | “Prompt assessment according to local clinical pathway.” | Diagnosis of orthostatic hypotension. |
| New fall-like event | “Probable fall event. Follow local response and post-fall protocol.” | “No injury detected.” |
| Low data quality | “Risk estimate unavailable or unreliable.” | Imputed confident risk score. |

The 2025 Australian Falls Guidelines support multifactorial, individually tailored prevention rather than a single universal intervention [R1]. Therefore, the system should improve prioritisation, longitudinal visibility, and review, not replace person-centred assessment.

---

# 16. Evaluation design in realistic conditions

## 16.1 Activity classification

Report:

- macro F1;
- balanced accuracy;
- per-class sensitivity;
- confusion matrix;
- segment IoU;
- transition onset error;
- unknown detection;
- results by participant and environment.

## 16.2 Fall event detection

The primary unit is the event or resident-day, not the window.

Report:

- event sensitivity;
- PPV;
- false alerts per 1,000 monitored hours;
- false alerts per resident-day;
- missed falls;
- median and 95th percentile detection latency;
- uptime and coverage;
- proportion of time abstaining;
- performance in multi-person conditions;
- performance under interference;
- adjudication disagreement.

## 16.3 Fall-risk prediction

Report:

- outcome definition;
- horizon;
- censoring;
- event count;
- participant count;
- site count;
- missing data;
- AUROC;
- AUPRC;
- Brier score;
- calibration;
- net benefit;
- sensitivity and PPV at operational thresholds;
- alert volume;
- confidence intervals;
- external evaluation;
- subgroup uncertainty;
- incremental performance over clinical baseline.

## 16.4 Required comparisons

1. Clinical variables only.
2. RF variables only.
3. Clinical plus RF.
4. Simple model.
5. Complex model.
6. Static snapshot.
7. Longitudinal trend.
8. Population model.
9. Population plus personal baseline.

The combined model is justified only if it adds calibrated clinical value.

---

# 17. Audit mode for an existing implementation

The orchestrator must perform these phases in order.

## Phase A: Preserve and reproduce

- Record repository URL, branch, commit, dirty state, submodules, large-file pointers, environment, data version, and model artefacts.
- Create a read-only baseline tag or archive.
- Run existing tests.
- Reproduce reported metrics.
- Record all failures without immediately fixing them.

## Phase B: Architecture mapping

Create:

- component diagram;
- data-flow diagram;
- trust-boundary diagram;
- model lifecycle;
- deployment topology;
- clinical workflow;
- file-to-responsibility map.

## Phase C: RF audit

Check:

- centre frequency and bandwidth;
- sample rate;
- aliases;
- gain;
- clipping;
- saturation;
- DC offset;
- LO leakage;
- CFO and SFO;
- direct-path leakage;
- antenna suitability;
- port selection;
- timing;
- packet loss;
- interference;
- metadata completeness;
- regulatory compliance.

## Phase D: Data audit

Check:

- provenance;
- participant consent and governance;
- duplicates;
- overlapping windows;
- split leakage;
- class construction;
- label balance;
- hard negatives;
- participant and environment distribution;
- label quality;
- missingness;
- annotation agreement;
- code that silently drops samples.

## Phase E: ML and statistics audit

Check:

- preprocessing fit on full data;
- hyperparameter tuning on test;
- threshold selection on test;
- window versus event metrics;
- unrealistic prevalence;
- ungrouped confidence intervals;
- data augmentation leakage;
- pretrained-model contamination;
- calibration;
- subgroup performance;
- external validation;
- reproducibility.

## Phase F: Clinical and safety audit

Check:

- intended use;
- user;
- action pathway;
- harm from false positive and false negative;
- alert fatigue;
- overreliance;
- stale clinical data;
- inappropriate treatment advice;
- dignity and autonomy;
- monitoring zones;
- ethics and regulatory status.

## Phase G: Security and deployment audit

Check:

- secrets;
- access;
- encryption;
- logging;
- identity linkage;
- model signing;
- dependency vulnerabilities;
- rollback;
- monitoring;
- fail-safe behaviour;
- software bill of materials.

## Phase H: Prioritised remediation

Each defect contains:

```yaml
defect_id: string
severity: critical | high | medium | low
domain: RF | DATA | ML | STATISTICS | CLINICAL | SECURITY | REGULATORY | UX
evidence:
  files: []
  logs: []
impact: string
root_cause: string
fix: string
verification: string
residual_risk: string
owner: agent_id
```

Fix critical evidence-integrity and safety defects before model optimisation.

---

# 18. Code quality requirements

All production or research-critical Python must have:

- type hints;
- docstrings for public interfaces;
- explicit exceptions;
- structured logging;
- configuration validation;
- deterministic seeds where possible;
- unit tests;
- integration tests;
- no hard-coded patient identifiers;
- no hidden environment assumptions;
- no silent fallback that changes scientific meaning;
- bounded memory for long recordings;
- graceful interruption and resumable outputs;
- checksum verification;
- CLI `--dry-run`;
- CLI `--config`;
- CLI `--output`;
- version metadata.

Suggested commands:

```bash
make setup
make lint
make typecheck
make test
make test-hardware
make acquire-smoke
make preprocess-smoke
make train-baseline
make evaluate
make audit
make reproduce
make docs
```

The `Makefile` must print exact underlying commands.

---

# 19. Testing strategy

## Unit tests

- signal generators;
- filters;
- channel estimator;
- phase unwrap;
- windowing;
- label alignment;
- feature extraction;
- schemas;
- calibration;
- event aggregator.

## Synthetic signal tests

Inject known:

- delay;
- Doppler;
- amplitude;
- phase drift;
- CFO;
- SFO;
- noise;
- dropped frames;
- clipping;
- multipath.

Assert bounded estimation error.

## Integration tests

- GNU Radio to storage.
- Storage to preprocessing.
- Preprocessing to model.
- Model to event aggregator.
- Event to dashboard.
- Clinical profile to prediction.
- Model registry to serving.
- Rollback.


## Dashboard and orchestration tests

- Button-to-workflow mapping.
- Workflow schema rejection.
- Idempotency keys.
- Serial and parallel workflow execution.
- Cancellation and rollback.
- Resource and state locks.
- API and worker restart recovery.
- Browser reconnect without duplicate execution.
- Role and scope enforcement.
- Two-person approval.
- Privileged-helper isolation.
- Command and prompt injection.
- WebSocket event ordering and replay.
- Audit completeness and secret redaction.
- Host metric accuracy.
- N210 capability truthfulness.
- Training and recalibration isolation.
- Model promotion and rollback.
- Diagnostic bundle privacy.


## Hardware-in-the-loop tests

- N210 discovery.
- RX only.
- TX only.
- full duplex.
- safe conducted loopback.
- no-motion baseline.
- controlled mover.
- network interruption.
- sensor restart.

## Clinical safety tests

- stale input.
- missing input.
- conflicting medication data.
- no signal.
- ambiguous event.
- multiple people.
- delayed alert.
- clinician disagreement.
- user withdrawal.
- restricted monitoring zone.
- model version mismatch.

---

# 20. First implementation roadmap

## Phase 0: Governance and measurement plan

Deliver:

- intended use;
- clinical problem statement;
- system requirements;
- risk register;
- evidence ledger;
- ethics roadmap;
- RF compliance checklist;
- acceptance metrics.

## Phase 1: N210 2.4 GHz reference testbed and control-plane foundation

Deliver:

- safe hardware setup;
- UHD benchmark;
- GNU Radio flowgraph;
- raw IQ writer;
- known waveform;
- channel estimator;
- static and mechanical-target results;
- reproducible experiment bundle.

## Phase 2: Controlled human activity dataset

Deliver:

- approved protocol;
- walking, sitting, standing, lying, transitions;
- hard negatives;
- grouped split;
- baseline activity model;
- event-level fall baseline.

## Phase 3: Robustness and commodity CSI

Deliver:

- second room;
- unseen participants;
- multi-person tests;
- interference tests;
- low-cost CSI receiver path;
- cross-platform comparison;
- domain-robust model.

## Phase 4: Mobility measurement validation

Deliver:

- RF-derived walking and transfer features;
- agreement with reference measurement;
- test-retest reliability;
- personal-baseline model;
- longitudinal feature store.

## Phase 5: Silent aged-care or clinical pilot

Deliver:

- no induced falls;
- naturalistic monitoring;
- incident adjudication;
- coverage and alarm simulation;
- patient, staff, and clinician feedback;
- external validation.

## Phase 6: Fall-risk model

Deliver:

- pre-specified outcome and horizons;
- clinical baseline model;
- RF incremental-value analysis;
- calibration;
- decision-curve analysis;
- clinician dashboard prototype;
- productionised operations, maintenance, model-operations, audit, and chat panels;
- prospective validation plan.

## Phase 7: Controlled decision-support evaluation

Deliver:

- locked software;
- regulatory determination;
- cybersecurity evidence;
- human-factors evaluation;
- early live evaluation aligned with DECIDE-AI;
- rollback and monitoring.

---

# 21. Ninety-day execution plan

## Days 1 to 15

- Establish repository and governance files.
- Verify N210/UBX hardware.
- Perform network and streaming benchmarks.
- Audit antennas and RF components.
- Build conducted-loopback test.
- Define 2.4 GHz experiment channel after compliance review.
- Implement recording manifest and raw IQ format.

## Days 16 to 30

- Implement deterministic waveform.
- Implement timing, CFO correction, and channel estimation.
- Characterise static channel.
- Run mechanical-motion experiments.
- Create signal-quality gate.
- Lock Phase 1 reproducibility bundle.

## Days 31 to 50

- Finalise human-activity protocol and approvals.
- Build annotation tool.
- Collect pilot primitives from a small healthy-adult sample.
- Establish rule-based and classical ML baselines.
- Audit leakage and label alignment.

## Days 51 to 70

- Expand hard negatives and environment variation.
- Train compact temporal models.
- Add event aggregation and abstention.
- Report event-level metrics.
- Conduct red-team tests.

## Days 71 to 90

- Build initial commodity CSI receiver track.
- Compare N210 and commodity measurements.
- Draft older-adult non-fall functional protocol.
- Define clinical profile schema.
- Co-design dashboard wireframes.
- Prepare the next ethics and funding package.

---

# 22. Key strategic recommendations

1. **Start at 2.4 GHz with the current verified antennas.** Do not compromise the early experiments by using antennas outside their intended band.
2. **Use the N210 as a research-grade reference, not the final cost target.**
3. **Use deterministic probe traffic or a controlled waveform.** Ordinary home traffic alone may not provide the cadence needed for safety-relevant sensing.
4. **Collect raw IQ and derived channel estimates.** Future algorithms may need information discarded by early features.
5. **Prioritise false-alert burden.** A detector with impressive balanced-test accuracy can still be unusable in a home where falls are rare.
6. **Model the unknown class.** Real homes contain activities absent from training.
7. **Treat cross-room and cross-person generalisation as a core requirement, not a later enhancement.**
8. **Validate motion measurements before building risk scores.** A risk model cannot be clinically credible if its RF gait and transfer features are not reliable.
9. **Build a clinical baseline before adding AI complexity.** Demonstrate incremental value of RF sensing.
10. **Forecast defined horizons.** “Fall risk” without a time horizon is not an actionable probability.
11. **Prefer calibrated risk and net benefit over a target of “high confidence.”**
12. **Deploy silently before exposing alerts.**
13. **Keep treatment outside the model.** Present evidence and review prompts to clinicians.
14. **Design for consent, privacy zones, and dignity from the beginning.**
15. **Plan for medical-device and cybersecurity obligations early.**

---

# 23. Evidence-grounded interpretation of the literature

Commodity Wi-Fi CSI is promising because human motion changes the multipath channel, and CSI provides finer subcarrier-level information than RSSI. However, access to CSI is platform dependent, and performance commonly degrades across environments [R19, R20].

A representative 2024 commodity Wi-Fi fall study used an inexpensive ESP32S3 receiver, 2.4 GHz, 20 MHz bandwidth, and approximately 100 Hz ping traffic. Its dataset had 10 young volunteers in one room, 928 balanced samples, and a within-volunteer random train/test split [R21]. This is useful proof of concept, but it does not establish clinical generalisation. Balanced scripted data can conceal the false-alert burden under real fall prevalence, and within-volunteer random splitting can overestimate performance.

Research systems such as FallDeFi, RT-Fall, Anti-Fall, and DeFall demonstrate that CSI amplitude, phase, Doppler-like patterns, and environment-invariant features can identify fall-like events in controlled studies [R22-R25]. Their methods should be reproduced as baselines, not accepted as deployment evidence.

SenseFi provides a useful open benchmark and codebase for comparing deep models across Wi-Fi sensing datasets [R20]. It should be used to test implementation correctness and representation choices, while local data and external clinical validation remain necessary.

Clinical guidance is equally important. Australian and international guidelines emphasise multifactorial, person-centred assessment and intervention. Relevant domains include fall history, gait, balance, mobility, medication, cardiovascular symptoms, cognition, vision, hearing, feet and footwear, continence, environment, nutrition, and bone health [R1-R4]. In residential aged care, all residents may reasonably be treated as being at elevated baseline risk, so a useful system must show changes, trajectories, and actionable contributors rather than merely assign a binary “high risk” label [R1, R2].

Sensor-derived gait and mobility measures show potential for fall-risk assessment, but evidence is heterogeneous. Radar studies have demonstrated measurement of TUG-like tasks and differences associated with previous falls, while prospective wearable studies and recent meta-analysis support the potential of continuous mobility measures [R26-R29]. These findings justify a rigorous research programme, not a claim that RF alone can already predict an individual's future fall with clinical certainty.

---

# 24. Definition of done

A feature, model, or stage is done only when:

- requirement is identified;
- risk is assessed;
- implementation is reviewed;
- tests pass;
- data and code versions are recorded;
- results reproduce from a clean environment;
- performance is reported with uncertainty;
- failure modes are documented;
- clinical claim matches evidence;
- privacy and security controls are verified;
- artefact checksums are stored;
- an independent agent reviews the result;
- the relevant stage gate is passed.

---

# 25. Initial master-orchestrator task

Use this exact task after adding the framework to the repository:

```text
Read RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK.md in full.

Act as MASTER_ORCHESTRATOR in MODE=BUILD at G0.

1. Inspect the repository and host environment without making destructive changes.
2. Create the minimum repository structure required for Phase 1.
3. Create:
   - docs/evidence/evidence_ledger.md
   - docs/decisions/0001-intended-use.md
   - risk/risk_register.csv
   - risk/hazard_log.csv
   - docs/architecture/system_context.md
   - docs/protocols/n210_bringup.md
   - configs/hardware/n210_ubx40.yaml
   - schemas/recording.schema.json
   - .env.template
   - Makefile
   - configs/project.yaml
   - docs/decisions/0000-project-naming.md
   - schemas/workflow.schema.json
   - schemas/health_snapshot.schema.json
   - docs/architecture/control_plane.md
4. Run and archive N210, UHD, GNU Radio, OS, Python, and network diagnostics.
5. Do not transmit over the air.
6. Produce a G0, G1, and G1A gap report.
7. Stop before conducted or over-the-air transmission if attenuator values,
   RF limits, antenna suitability, or approvals are not verified.
8. Return changed files, exact commands, test results, evidence paths,
   unresolved risks, and the next smallest safe action.
```

---

# 26. Reference sources

## Clinical falls guidance and ethics

**[R1]** Australian Commission on Safety and Quality in Health Care. *Preventing Falls and Harm from Falls in Older People: Best Practice Guidelines for Australian Residential Aged Care Services*. 2025.  
https://www.safetyandquality.gov.au/resources/falls-guidelines-australian-residential-aged-care-services

**[R2]** Montero-Odasso M, et al. *World guidelines for falls prevention and management for older adults: a global initiative*. Age and Ageing. 2022;51(9):afac205.  
https://doi.org/10.1093/ageing/afac205

**[R3]** National Institute for Health and Care Excellence. *Falls: assessment and prevention in older people and in people 50 and over at higher risk*. NG249. 2025.  
https://www.nice.org.uk/guidance/ng249

**[R4]** Centers for Disease Control and Prevention. *STEADI: Older Adult Fall Prevention*. Updated 2025.  
https://www.cdc.gov/steadi/

**[R5]** National Health and Medical Research Council, Australian Research Council and Universities Australia. *National Statement on Ethical Conduct in Human Research 2025*. Effective 23 June 2026.  
https://www.nhmrc.gov.au/research-policy/ethics/national-statement-ethical-conduct-human-research

## Australian regulation, privacy, and RF safety

**[R6]** Therapeutic Goods Administration. *Understanding how we regulate software-based medical devices*. 2026.  
https://www.tga.gov.au/resources/guidance/understanding-how-we-regulate-software-based-medical-devices

**[R7]** Therapeutic Goods Administration. *An overview of software and artificial intelligence*. 2026.  
https://www.tga.gov.au/products/medical-devices/software-and-artificial-intelligence-ai/overview

**[R8]** Office of the Australian Information Commissioner. *Australian Privacy Principles Guidelines*. Updated 13 May 2026.  
https://www.oaic.gov.au/privacy/australian-privacy-principles/australian-privacy-principles-guidelines

**[R9]** Office of the Australian Information Commissioner. *APP 1: Open and transparent management of personal information*. Includes automated-decision transparency changes commencing 10 December 2026.  
https://www.oaic.gov.au/privacy/australian-privacy-principles/australian-privacy-principles-guidelines/chapter-1-app-1-open-and-transparent-management-of-personal-information

**[R10]** Australian Communications and Media Authority. *Low interference potential devices class licence*. 2025.  
https://www.acma.gov.au/licences/low-interference-potential-devices-lipd-class-licence

**[R11]** Australian Radiation Protection and Nuclear Safety Agency. *Radiation Protection Standard for Limiting Exposure to Radiofrequency Fields, 100 kHz to 300 GHz*. 2021.  
https://www.arpansa.gov.au/regulation-and-licensing/regulatory-publications/radiation-protection-series/codes-and-standards/rpss-1

## Hardware documentation

**[R12]** Ettus Research. *UBX 10-6000 MHz Rx/Tx, 40 MHz*.  
https://www.ettus.com/all-products/ubx40/

**[R13]** Ettus Research Knowledge Base. *About USRP Bandwidths and Sampling Rates*.  
https://kb.ettus.com/About_USRP_Bandwidths_and_Sampling_Rates

**[R14]** Ettus Research Knowledge Base. *N200/N210*.  
https://kb.ettus.com/N200/N210

**[R15]** Ettus Research. *UHD and USRP Manual: Daughterboards*.  
https://files.ettus.com/manual/page_dboards.html

**[R16]** Ettus Research Knowledge Base. *Synchronization and MIMO Capability with USRP Devices*.  
https://kb.ettus.com/Synchronization_and_MIMO_Capability_with_USRP_Devices

## Prediction-model and clinical-AI methodology

**[R17]** Collins GS, et al. *TRIPOD+AI statement: updated guidance for reporting clinical prediction models that use regression or machine learning methods*. BMJ. 2024;385:e078378.  
https://doi.org/10.1136/bmj-2023-078378

**[R18]** Moons KGM, et al. *PROBAST+AI: an updated quality, risk of bias, and applicability assessment tool for prediction models using regression or artificial intelligence methods*. BMJ. 2025;388:e082505.  
https://doi.org/10.1136/bmj-2024-082505

**[R19]** Vasey B, et al. *Reporting guideline for the early-stage clinical evaluation of decision support systems driven by artificial intelligence: DECIDE-AI*. Nature Medicine. 2022;28:924-933.  
https://doi.org/10.1038/s41591-022-01772-9

## Wi-Fi sensing and fall detection

**[R20]** Yang J, et al. *SenseFi: A library and benchmark on deep-learning-empowered WiFi human sensing*. Patterns. 2023;4(3):100703.  
https://doi.org/10.1016/j.patter.2023.100703

**[R21]** Chen T, et al. *Deep learning-based fall detection using commodity Wi-Fi*. Journal of Information and Intelligence. 2024;2:355-364.  
https://doi.org/10.1016/j.jiixd.2024.04.001

**[R22]** Palipana S, Rojas D, Agrawal P, Pesch D. *FallDeFi: Ubiquitous Fall Detection using Commodity Wi-Fi Devices*. Proceedings of the ACM on Interactive, Mobile, Wearable and Ubiquitous Technologies. 2018;1(4).  
https://doi.org/10.1145/3161183

**[R23]** Wang H, et al. *RT-Fall: A Real-Time and Contactless Fall Detection System with Commodity WiFi Devices*. IEEE Transactions on Mobile Computing. 2017;16(2):511-526.  
https://doi.org/10.1109/TMC.2016.2557795

**[R24]** Zhang D, Wang H, Wang Y, Ma J. *Anti-Fall: A Non-intrusive and Real-time Fall Detector Leveraging CSI from Commodity WiFi Devices*. 2015.  
https://arxiv.org/abs/1507.01057

**[R25]** Hu Y, Zhang F, Wu C, Wang B, Liu KJR. *DeFall: Environment-Independent Passive Fall Detection Using WiFi*. IEEE Internet of Things Journal. 2022;9(11):8515-8530.  
https://doi.org/10.1109/JIOT.2021.3116136

## Sensor-derived mobility and fall-risk evidence

**[R26]** Howcroft J, et al. *Prospective Fall-Risk Prediction Models for Older Adults Based on Wearable Sensors*. IEEE Journal of Biomedical and Health Informatics. 2017.  
https://pubmed.ncbi.nlm.nih.gov/28358689/

**[R27]** Saho K, et al. *Experimental Verification of Micro-Doppler Radar Measurements of Fall-Risk-Related Gait Differences for Community-Dwelling Elderly Adults*. Sensors. 2022;22(3):930.  
https://doi.org/10.3390/s22030930

**[R28]** Bordat A, et al. *Towards automated fall risk assessment: validation of an FMCW radar-based Timed Up and Go test*. 2025.  
https://eprints.gla.ac.uk/361235/

**[R29]** *Accuracy of wearable devices in predicting falls in older adults: a systematic review and meta-analysis*. Frontiers in Public Health. 2026.  
https://doi.org/10.3389/fpubh.2026.1778750


## Operations, orchestration, and telemetry

**[R30]** Ettus Research. *UHD and USRP Manual: Device Identification*. Current UHD manual. `uhd_usrp_probe` is the standard utility for inspecting a connected USRP.  
https://files.ettus.com/manual/page_identification.html

**[R31]** Ettus Research. *UHD and USRP Manual: General Application Notes*. Documents receive overflow, transmit underflow, asynchronous metadata, and lock-sensor patterns.  
https://files.ettus.com/manual/page_general.html

**[R32]** systemd. *D-Bus interface and service management documentation*. Supports structured start, stop, restart, status, and cgroup-tracked service control.  
https://www.freedesktop.org/software/systemd/man/latest/org.freedesktop.systemd1.html

**[R33]** FastAPI. *WebSockets*. Official guide for bidirectional real-time API communication.  
https://fastapi.tiangolo.com/advanced/websockets/

**[R34]** Celery. *Canvas: Designing Workflows*. Official documentation for task chains, groups, and chords.  
https://docs.celeryq.dev/en/main/userguide/canvas.html

**[R35]** psutil. *Process and System Utilities for Python*. Official documentation for CPU, memory, disk, network, sensor, and process telemetry.  
https://psutil.readthedocs.io/stable/

**[R36]** Prometheus. *Monitoring Linux host metrics with node exporter*. Official guide for machine-level metrics.  
https://prometheus.io/docs/guides/node-exporter/

**[R37]** FastAPI. *OAuth2 scopes*. Official guide for fine-grained API permissions.  
https://fastapi.tiangolo.com/advanced/security/oauth2-scopes/


---

# 27. Final instruction to all agents

The objective is not to create the most complex RF or AI system. The objective is to create the simplest system that can produce reliable, reproducible, clinically meaningful information under realistic conditions, with an explicit failure envelope and a safe human decision pathway.

When evidence is weak, say so.  
When data are insufficient, abstain.  
When a simple baseline performs as well as a complex model, keep the simple model.  
When the laboratory result does not survive an unseen room, participant, or site, treat it as a research finding rather than a product capability.  
When a clinical claim cannot be supported prospectively, do not make it.
