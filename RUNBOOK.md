# RF Sensing Falls Project — Offline DEVELOPMENT POC Runbook

This runbook operates only the repository-local replay pipeline. It does not
open UHD, contact an N210, transmit RF, or touch the sister project. The model
performance gate is currently **FAILED**; dashboard outputs are silent research
candidates and uncalibrated research scores, not alerts or probabilities.

## Pipeline

```text
local SigMF file -> replay :15880 -> DSP :15991 -> classifier :15993
                 -> unknown-aware state aggregator :15994 -> logger/dashboard :18090
```

All internal endpoints bind to `127.0.0.1`. The dashboard also defaults to
loopback. The authoritative configuration is
`configs/poc/offline_replay.yaml`.

## Validate before a run

From `/home/sdr-research/carat_research`:

```bash
make test
.venv/bin/python scripts/run_offline_poc.py
```

The second command is a dry-run. Inspect the JSON plan and confirm it contains
only the six repository-local Python services. In particular, it must contain
no UHD command, hardware address, RF/TX process, or non-loopback endpoint.

## Run a bounded replay

```bash
.venv/bin/python scripts/run_offline_poc.py --run --max-seconds 30
```

While it runs, open `http://127.0.0.1:18090/monitor`. The supervisor waits for
dashboard readiness, starts replay last, and terminates every child in reverse
order at EOF. Every run receives an immutable directory under
`artifacts/runs/<UTC-run-id>/` containing:

- `run.json`: source/data/configuration/model hashes, commands, lifecycle,
  replay totals, and DSP integrity counters/result;
- `events.jsonl`: derived state/candidate messages;
- one log per process.

Use another existing recording without modifying it:

```bash
.venv/bin/python scripts/run_offline_poc.py --run \
  --session data/raw/2026-07-29_floor_fall_reps_b --max-seconds 60
```

## Recalibration development path

The legacy feature table and v3 model bundle are frozen comparison artifacts.
Do not run `models/train_production.py`; it deliberately refuses direct active
training.

Build the conflict-free dataset from explicit annotations only:

```bash
.venv/bin/python models/build_dataset.py
```

This writes `data/processed/g3_features_v2_conflict_free.parquet`, never the
legacy feature table. It drops unknown annotation gaps and all cross-label
raw-time overlaps.

Train an immutable unevaluated candidate:

```bash
.venv/bin/python models/train_candidate.py \
  --candidate-id rf-sensing-falls-v6-dev-20260808-001
```

Candidates are created under `models/candidates/`, have no fall threshold, and
cannot be loaded by the runtime. A separate grouped evaluation and calibration
artifact is required before any future promotion review. Current data must be
treated as train/development-only; new independent participant/room/time data is
required for credible calibration and testing.

Build and evaluate the smaller Product-A error-analysis recipe without
touching `models/production`:

```bash
.venv/bin/python models/train_product_a_candidate.py \
  --candidate-id rf-sensing-falls-product-a-physics6-dev-YYYYMMDD-NNN
.venv/bin/python models/evaluate_product_a_development.py \
  --candidate-id rf-sensing-falls-product-a-physics6-dev-YYYYMMDD-NNN
```

This workflow always emits a null threshold and a failed promotion gate. It
does not fix the missing independent participants, rooms, verified lie-down
examples, calibration set, or final test set.

## Tailscale-only derived dashboard

Remote access is opt-in and binds only the dashboard to the machine's exact
local Tailscale IPv4 address. Raw IQ and every ZMQ pipeline endpoint remain on
loopback:

```bash
.venv/bin/python scripts/run_offline_poc.py --run --repeat \
  --max-seconds 86400 --speed 1 \
  --tailscale-dashboard-ip 100.93.70.68
```

Then visit `http://100.93.70.68:18090/monitor` from an authenticated peer on
the same tailnet. The HTTP service has no independent application login or
TLS; the Tailscale network identity is the access boundary. Do not expose or
forward port 18090 to a public or non-tailnet interface. The server rejects
non-tailnet clients and WebSocket origins that do not match the exact server
address.

For a supervised transient user service:

```bash
systemd-run --user --unit=carat-tailscale-poc --collect \
  --property=KillMode=mixed \
  --working-directory=/home/sdr-research/carat_research \
  .venv/bin/python scripts/run_offline_poc.py --run --repeat \
  --max-seconds 86400 --speed 1 \
  --tailscale-dashboard-ip 100.93.70.68
```

Graceful stop:

```bash
systemctl --user stop carat-tailscale-poc.service
```

## Failure handling

- A model hash, null threshold, wrong class/feature shape, NaN, or modified
  artifact fails at classifier startup.
- Malformed IQ/spectrogram messages are discarded and logged. A supervised
  evidence run is marked `FAILED` unless DSP receives exactly the replayed
  sample count with zero sequence gaps, invalid chunks, and invalid frames.
- The session sample rate configures both DSP and classifier; dataset building
  and serving share the exact cropped FFT-bin frequency axis.
- Missing upstream messages become `sensor_unavailable`, never person absence.
- A disconnected WebSocket no longer blocks dashboard shutdown.
- If a bounded run fails, inspect `artifacts/runs/<id>/run.json` and component
  logs. The supervisor records `FAILED` and still performs bounded shutdown.

Hardware or RF work is outside this runbook and requires a separately scoped
instruction. Do not substitute a live source into this offline configuration.
