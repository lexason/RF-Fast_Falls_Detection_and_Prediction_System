# Errata vs RF-FAST Framework Docs

Deviations from `RF_FAST_Complete_Framework.docx` (and related framework docs) forced by
hardware reality on the USRP N210, per CLAUDE.md §4. Hardware wins; this file is the
authoritative record of where and why.

| doc §  | original claim | correction | reason |
|---|---|---|---|
| Sensing architecture (FMCW sweep) | 200 MHz FMCW sweep for fine range resolution | Not attempted. Primary mode is CW Doppler (micro-Doppler only, no range). Secondary mode is narrowband FMCW, B ≤ 20 MHz, for coarse presence gating only. | N210 GigE streaming caps at ~25 MS/s (complex16) / 50 MS/s (sc8). WiTrack's 200 MHz sweep used a custom analog FMCW front end, not a general-purpose SDR like the N210. |
| Fall/posture detection | Radar directly senses posture (sitting, lying) | Posture is inferred via a state machine over discrete motion *events* (sit_down, stand_up, lie_down, fall) that hold state until the next transition. | Doppler radar only sees motion; a stationary person produces no signal after clutter removal. |
| `FMCWGaitNet` architecture (RF_FAST_Enhanced_Architecture.md) | Input `(B, 1, 128, 256)` — Doppler bins × **range** bins | Input `(B, 1, 154, 60)` — Doppler bins × **time** frames within a 3s window. Same 4-conv-block philosophy, kernel sizes, channel progression, and 1024-dim flattened embedding preserved; only the second spatial axis's meaning changes. | The sketch's second axis assumes FMCW range resolution. This project's primary/only mode is CW Doppler (see the FMCW-sweep row above) — there is no range axis to feed it. Adapted 2026-07-29 for G3 classifier v2 (`models/cnn_v2.py`). |

_Add new rows as further deviations are discovered during G0–G6._
