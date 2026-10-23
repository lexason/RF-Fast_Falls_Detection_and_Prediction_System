# Offline DEVELOPMENT POC Remediation and Validation Report

Date: 2026-08-07  
Project: RF Sensing Falls Project  
Operating mode: BUILD, offline-only, silent research POC  
Stage-gate decision: G3 **FAIL** for validated fall detection; silent offline engineering POC **PASS WITH LIMITATIONS**

## Scope and authority

The sponsor's approval override was accepted for repository-local technical
remediation, existing-data analysis, model training, and offline recalibration.
No N210/UHD/RF operation was attempted. No sister-project file, configuration,
process, port, or service was changed. The completed POC reads only existing
local recordings and uses loopback networking.

The user requested a proof of concept suitable for testing and recalibration.
This has been achieved as a deterministic **silent offline engineering POC**.
It has not been achieved as a dependable fall-alert system, and the interface
now makes that distinction explicit.

## Starting defects confirmed

Independent data, ML, DSP/runtime, deployment, dashboard, and validation audits
confirmed the following critical/high defects:

1. `models/train_production.py` hard-coded the rejected threshold `0.0004`
   and overwrote the active bundle. The locally corrected metadata used `0.50`.
2. The streaming classifier finalized events before the future portion of its
   three-second training window existed. About 93% of transient training rows
   were affected.
3. Staged v4/v5 bundles had a null fall threshold and crashed on the first
   transient if selected as suggested by the old runbook.
4. Replay ignored its non-repeat setting, repeated forever, and depended on
   stdin to terminate.
5. Posture initialized as standing, converted missing source data into person
   absence, and displayed uncalibrated model output as confidence.
6. The dashboard interpolated manifests into HTML, used an unapproved legacy
   project name, bound remotely by default, and could hang during WebSocket
   shutdown when upstream disappeared.
7. The processed dataset implicitly filled annotation gaps as idle and reused
   overlapping raw intervals under different labels.
8. Existing evaluation was one apparent researcher/one room with no independent
   participant, site, room, calibration, or final test cohort.

## Repairs implemented

### Model lifecycle and serving contract

- Added a fail-closed ONNX loader that verifies metadata schema, status,
  threshold type/range, feature/class shapes, CPU provider, and SHA-256 for both
  model artifacts.
- Frozen v3 as `rf-sensing-falls-v3-legacy-baseline`, `OFFLINE_BASELINE`, with
  `promotion_eligible=false` and `performance_gate_passed=false`.
- Scores are now declared `uncalibrated_model_score_not_probability`.
- Direct production training now refuses execution. New training writes an
  immutable, threshold-free candidate under `models/candidates/` and never
  changes the frozen baseline.
- Added a grouped DEVELOPMENT evaluator that writes a separate evidence
  artifact and cannot promote or edit a candidate.

### Causal DSP/inference path

- Completed events enter a queue and are classified only when the full
  event-centred three-second window exists, restoring train/serve time support.
- Malformed, non-finite, changed-bin-count, and non-monotonic spectrogram frames
  fail closed. Invalid/non-finite IQ chunks are discarded and logged.
- Replay IQ messages carry a source sample index; DSP detects sequence gaps and
  timestamps frames from the source sample clock, so replay speed/jitter cannot
  distort timing features. The supervisor binds DSP to the session sample rate.
- DSP, serving, and dataset construction now share exact cropped FFT-bin
  centres and frame-centre timing rather than reconstructing an approximate
  frequency axis.
- Added model/data/quality/operating-mode fields and classification-window
  timestamps to events.
- Added classifier heartbeats so model warm-up is not mistaken for an outage.
- Replaced fall alerts with silent probable-fall candidates and replaced
  confidence with research score.

### State and dashboard behavior

- State begins `unknown`; walking followed by no motion becomes
  `static_posture_unknown`; missing input becomes `sensor_unavailable`; person
  absence is never inferred from missing Doppler data.
- Dashboard identity comes from `configs/project.yaml`, manifests are escaped,
  path traversal is rejected, and `/healthz` reports process health without
  claiming upstream health.
- POC dashboard binding is loopback-only on port 18090.
- WebSocket bridges cancel on client disconnect or application shutdown rather
  than blocking forever on ZMQ receive.

### Deterministic replay and supervision

- Replaced GNU Radio/stdin replay with a pure-Python, EOF-terminating,
  exact-sample-count publisher. Repeat is explicit and bounded repeat requires
  a maximum duration.
- Added a dry-run-by-default supervisor with port preflight, loopback policy,
  consumer-first startup, readiness check, replay-last ordering, reverse bounded
  shutdown, and per-run evidence.
- No supervisor command contains UHD, the hardware address, an RF/TX source, a
  non-loopback endpoint, or a sister-project path.

### Data and recalibration path

- Created and verified a non-mutating catalog of all 53 raw sessions.
- Rebuilt features from explicit annotations only; unknown gaps are omitted.
- All candidate windows sharing raw-time support with a different label are
  excluded.
- Added content hashes for raw, processed, candidate, evaluation, and model
  artifacts and pinned the observed offline dependency versions.

## Evidence

### Raw integrity and provenance

Artifact: `artifacts/datasets/legacy-development-snapshot-v3.json`  
SHA-256: `2e13fec7da78b61089f76a6502f816aa274d93561e0adfcfede36c65818a6daa`

- 53 sessions: 50 real, 3 synthetic.
- 12,064,000,000 raw bytes; 6,032 seconds (1.676 hours).
- 53/53 embedded SigMF SHA-512 hashes recomputed and verified.
- No whole-file duplicate groups and zero non-finite complex samples; these
  counts, plus hashes for every legacy manifest, SigMF metadata file, and label
  file, are stored in the source-bound v3 snapshot.
- 46/53 sessions have label files.
- 0/53 legacy manifests validate the current recording schema. Historical
  fields that were never collected remain unknown rather than fabricated.

### Conflict-free feature artifact

Artifact: `data/processed/g3_features_v2_conflict_free.parquet`  
SHA-256: `b8797febb691ce177c2e6f34750f3c61cc15bd85f98641cf340e97b6e5ccdff4`

- 1,825 finite windows across 35 recordings.
- Labels: walk 1,259; idle 350; stand-up 104; sit-down 51; lie-down 31; fall 30.
- 143 candidate windows excluded because of cross-label raw-time conflict.
- Verified post-build cross-label overlap pairs: **0**.
- 74 retained windows still have legacy `unverified` annotation status.

### Model evaluation

Frozen v3 evaluation:

- transient-window AUROC 0.539; AUPRC 0.180; Brier 0.147; ECE10 0.135;
- threshold 0.50: recall 0.170, specificity 0.917, PPV 0.235;
- the former 0.0004 threshold is explicitly deprecated and blocked.

Cleaned-data v6 candidate (`rf-sensing-falls-v6-dev-003`):

- authoritative evaluation artifact:
  `artifacts/evaluations/rf-sensing-falls-v6-dev-003-grouped-development-v3.json`
  (SHA-256 `f4a720c4549919b78b40279d7933698f27c38b0f144b1b8c84e3902d52870a40`),
  bound to candidate metadata, both ONNX hashes, the dataset hash, exact
  evaluator source hash, and dependency versions;
- candidate artifacts:
  - metadata SHA-256 `cf837d4c6d99a4549750c90026fba8a2e45833100da3600da6bfd2618cf6881b`;
  - stage 1 SHA-256 `8e0fc96a320e86f24a01d68893fe6ef35b59e76613bd1c838621aad8b516f352`;
  - stage 2 SHA-256 `ecafd19279e67326403190dfe19eac0cbe0780b67a0a4001e25cc7a1d62f26e5`.
- A second clean candidate build produced byte-identical stage 1 and stage 2
  ONNX hashes after canonicalising the converter's otherwise-random graph name.
- grouped day/geometry macro-F1 0.510;
- transient-window fall AUROC 0.562;
- diagnostic balanced point 0.02: recall 0.500, specificity 0.581, PPV 0.161;
- no threshold is approved; promotion remains blocked.

Cleaning removed contradictory data but did not make the small single-person
fall problem separable. This is evidence against threshold tuning as a remedy.

### Full offline replay

Completed source-bound and loss-gated final run: `artifacts/runs/20260807T072549.279872Z/run.json`

- Full 15.0-second recording replayed exactly once: 3,750,000 samples.
- Dashboard health passed with configured project/environment/mode.
- The run manifest binds the nine runtime sources (including the shared feature
  implementation), dependency lock, POC configuration, model metadata, bound
  evaluation, both ONNX files, raw manifest/SigMF metadata, and the raw data
  SHA-512; all hashes were re-verified against the final files after shutdown.
- DSP received all 3,750,000 samples in 300 chunks and published 295 frames,
  with zero sequence gaps, invalid chunks, or invalid frames. The supervisor's
  exact-delivery/zero-loss policy passed; a violation now fails the run.
- All processes exited or were terminated cleanly; no repository-local POC
  listener remained.
- Two transient events completed with full training-equivalent windows.
- Classification delays from event end were 1.350 s and 1.400 s.
- Both labeled fall events were predicted as `lie_down`; zero fall candidates
  were emitted. This confirms causal runtime operation and also confirms that
  the current model is not a dependable fall detector.

An earlier run safely failed because port 8090 was already in use; the
supervisor stopped all children without changing the owning service. The POC
was moved to isolated loopback port 18090 and now preflights every bind port.

### Automated validation

- Python source compilation: pass.
- Cross-artifact governance semantics: pass.
- Offline pytest: **47 passed, 3 hardware tests deselected**.
- Tests cover model hash/metadata rejection, null-threshold rejection, causal
  event waiting, malformed IQ/frames, unknown/stale states, overlap exclusion,
  replay EOF, dashboard escaping/path traversal, production-training refusal,
  injected sequence gaps, exact train/serve Doppler-axis and feature parity,
  and hardware-free loopback supervisor planning.
- The independent A15 closure audit found no remaining offline-POC defect or
  blocker and recorded `PASS` in
  `docs/agents/handoffs/2026-08-07_a15_offline_poc_closure.yaml`.

## Gate decision and permitted use

The POC is usable for:

- deterministic local raw-IQ replay;
- DSP/inference integration and latency regression;
- dashboard and lifecycle testing;
- label/data cleaning experiments;
- immutable candidate training and grouped development comparison;
- silent capture of research candidates for later adjudication.

It is not usable for:

- dependable fall alerts or emergency response;
- calibrated risk/probability display;
- clinical, diagnostic, or participant-facing decisions;
- claims about unseen participants, rooms, sites, devices, or real-world PPV;
- model promotion from the current dataset.

Therefore G3 remains **FAIL** for fall-detection validation. The offline
engineering/deployment path is **PASS with stated limitations** for controlled
testing and recalibration development.

## Required next evidence

1. Predeclare participant/session/room/site/device/time splits before further
   collection or windowing.
2. Collect independent participants and rooms plus continuous hard negatives;
   preserve an untouched temporal/final test cohort.
3. Add external/reference timing and tiered double-adjudicated annotations.
4. Separate Product A binary fall-event/hard-negative evaluation from Product B
   activity recognition.
5. Evaluate event sensitivity, PPV, false candidates per monitored hour/day,
   latency distribution, uptime, and abstention with cluster-level uncertainty.
6. Recalibrate only on a distinct calibration set after the event detector and
   causal feature contract are frozen.
7. Keep the POC silent until a locked threshold passes the intended-use gate on
   independent data.
