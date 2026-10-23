# RF Sensing Falls Project — Tailscale, N210, and G3 reassessment

Date: 2026-08-07  
Mode: supervised DEVELOPMENT, silent research only  
Framework gate: G3 **FAIL**

## Decision summary

| Item | Verdict | Evidence boundary |
|---|---|---|
| Remote derived dashboard | PASS for controlled tailnet DEVELOPMENT use | Exact bind `100.93.70.68:18090`; internal ZMQ and raw IQ stay on loopback |
| CARAT replay engineering | PASS for controlled silent testing | Current source-bound run is `RUNNING`; preceding 545.55-source-second run closed with exact sample delivery and zero invalid/gapped DSP input |
| N210 discovery/probe | PASS, receive-only | N210 and UBX-40 identities match inventory; no TX streamer or OTA RF action was created |
| OTA N210 operation | NOT RUN | Both inventoried antennas are 2.4–2.5 GHz-only while the legacy carrier is 5.8 GHz; antenna suitability interlock remains unmet |
| Product-A candidate mechanics | PASS as a deterministic experiment | Immutable model JSON rebuild is byte-identical; no production write and no threshold |
| Validated fall detection / G3 | **FAIL** | No independent participant/room/calibration/final test; zero verified lie-down examples; weak grouped discrimination |

This report does not authorise alerts, deployment, promotion, clinical use, or
generalisation. Dashboard values remain uncalibrated silent research outputs.

## Sister-project and N210 handling

The user authorised graceful shutdown of the exact sister-project process for
exclusive N210 access, while forbidding sister-project file or configuration
changes. The pre-existing `python -m uvicorn bridge.server:app ...` process
(PID 470097) received `SIGTERM` and stopped within the bounded wait; no
`SIGKILL` was required. Port 8090 and its UHD UDP sessions closed. No file or
configuration in `/home/sdr-research/n210-sensing-bridge` was read, written,
or changed.

Read-only hardware commands then passed:

- `uhd_find_devices --args=addr=192.168.10.50`
- `uhd_usrp_probe --args=addr=192.168.10.50`

The post-stop transcript is archived at
`docs/evidence/diagnostics/2026-08-07/n210_post_stop_receive_only_probe_2026-08-07.txt`
(SHA-256
`2efd73638851fb33a0c9ebf1175df6fd34b6b8720ce61c534fc49c22937a0e9a`).
It records an empty sister/CW Python process set before discovery, UTC command
times, both zero exit statuses, and no retained UHD UDP session afterward.

Observed identity: N210r4 serial `3253F7C`, firmware 12.4, FPGA 11.1, and
UBX-40 v2 serial `324DE2A` revision 5 with reported 10–6000 MHz RX/TX tuning
range. These commands did not create a TX stream. After the probes, neither
the sister process nor a CARAT UHD process retained the device.

OTA work stopped at the independent technical interlock. The authoritative
inventory marks both DIGITECH antennas as rated only 2.4–2.5 GHz and
`suitable_for_5g8: false`, while the legacy CARAT configuration selects 5.8
GHz. A prior close-range signal does not establish antenna suitability or
human-motion sensitivity. User approval cannot supply missing equipment
characterisation. No OTA RF transmission occurred during this reassessment.

## Remote dashboard restoration

The active URL is:

`http://100.93.70.68:18090/monitor`

The transient user service is `carat-tailscale-poc.service`; active evidence
run `artifacts/runs/20260807T082542.886108Z/run.json` records `RUNNING`, the
exact dashboard bind, component PIDs, configuration/data/model/evaluation
hashes, and source hashes. Health reports:

```json
{"status":"ok","project":"RF Sensing Falls Project","environment":"DEVELOPMENT","mode":"silent_research_poc","access_policy":"tailscale_only","bind_host":"100.93.70.68","upstreams":"not_asserted"}
```

Controls added and tested:

- only the dashboard binds to the exact local Tailscale address; no wildcard
  bind is permitted;
- raw IQ and all internal services remain on `127.0.0.1`;
- only loopback or Tailscale-range client addresses are accepted;
- WebSocket Origin must match the exact server host and port;
- manifest strings are escaped and path traversal is rejected;
- disconnected WebSockets cancel without blocking shutdown;
- the supervisor records `RUNNING` only after every pipeline component and
  replay are alive;
- ONNX Runtime is limited to one intra-op and one inter-op thread, removing
  the observed multi-core thread explosion.

Tailscale itself reports local IPv4 `100.93.70.68` and backend state
`Running`. The dashboard is plain HTTP with no separate application login or
TLS, so tailnet identity is the access boundary; port 18090 must not be
forwarded or exposed publicly.

The immediately preceding run
`artifacts/runs/20260807T081439.948160Z/run.json` was gracefully interrupted
for the continuous-monitor and exact-Origin fixes after 43 replay cycles and
659.75 seconds of source data. Its closeout records 164,937,500 samples sent
and received, 13,190 DSP frames, zero invalid chunks, zero invalid frames, zero sequence
gaps, and `policy_passed: true`.

## G3 defect correction and Product-A experiment

The earlier statement “both labeled falls were classified as lie_down” was
too strong. The source contains two automatic `fall` labels at 8.028–8.428 s
and 9.678–9.878 s, but the contemporaneous capture log and STATE record call
the recording one uncontrolled researcher fall sample. The centered
three-second windows overlap by 1.45 seconds. Direction diagnostics are -1
(7 strong frames) then +1 (3 strong frames), consistent with separate motion
phases or fall/recovery. There is no independent human adjudication proving
two separate falls.

The immutable sidecar
`artifacts/adjudications/2026-07-18_fall_gain5-review-v1.json` therefore marks
the clip `PROVISIONAL_QUARANTINED`, permits development error analysis only,
and cryptographically binds the raw IQ, SigMF metadata, manifest, and label
file. It is prohibited from training, model/threshold selection, calibration,
final testing, and validated claims.

A separate simple Product-A candidate was built with six physics-oriented
features, a standard scaler, and balanced L2 logistic regression. It does not
replace or modify `models/production`, contains `fall_decision_threshold:
null`, and is not loadable by the serving runtime.

Primary verified-only grouped DEVELOPMENT analysis (fall versus verified
sit-down/stand-up) has 142 windows: 30 fall, 42 sit-down, and 70 stand-up.
There are **zero verified lie-down windows**, so primary fall-versus-lie-down
performance is not estimable. Results:

- AUROC 0.58125; AUPRC 0.33934; Brier 0.25199;
- fixed 0.5 diagnostic: recall 0.60, specificity 0.72321, PPV 0.36735;
- no threshold was selected or approved.

Secondary legacy-label sensitivity includes all 31 unverified lie-down
windows (216 total transient windows). This is not a primary validation
claim:

- AUROC 0.67742; AUPRC 0.32731; Brier 0.19808;
- fixed 0.5 diagnostic: TP 18, FN 12, FP 47, TN 139; recall 0.60,
  specificity 0.74731, PPV 0.27692;
- a descriptive balance point at 0.408 has recall 0.66667, specificity
  0.63441, and PPV 0.22727, and is explicitly not a serving threshold.

On the quarantined pilot fragments, the full-fit Product-A scores are
0.32336 and 0.75287. The first is below and the second above a diagnostic
0.5, but these inspected target values were not used to choose the six-feature
recipe or any threshold. Treating “catch both automatic labels” as the
objective would be target leakage and would not validate fall detection.

The candidate artifact was independently rebuilt as
`rf-sensing-falls-product-a-physics6-repro-001`; both model JSON files have
SHA-256
`ab60a615fdc4c9b2ef707e57624966bd06e3264d7981da63cf28d3d796ca16f4`.
The bound evaluation remains `FAILED_ACCEPTANCE_CRITERIA`, promotion false,
performance gate false, and threshold null.

## Required evidence before G3 can pass

1. Protocol-controlled, ethically reviewed and physically supervised staged
   data with one episode identifier and explicit descent, impact/landing,
   stillness, and recovery phases.
2. Multiple independent participants, rooms, geometries, days, and hard
   negatives, including source-grounded verified lie-down examples.
3. Participant/site-separated training, calibration, and untouched final-test
   partitions fixed before model selection.
4. Pre-specified acceptance metrics for event sensitivity, false alarms per
   hour, latency, calibration, uncertainty/abstention, and subgroup reporting.
5. A frequency-rated antenna/profile (or a separately reviewed 2.4 GHz
   configuration) before any OTA N210 collection.

Until those conditions are met, the usable proof of concept is the controlled
silent engineering pipeline and dashboard—not validated fall detection.
