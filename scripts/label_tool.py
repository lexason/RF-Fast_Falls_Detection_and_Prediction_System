#!/usr/bin/env python3
"""G3: semi-automated event labeling for recorded sessions.

CLAUDE.md §5 names this tool ("overlays the spectrogram for human labeling")
but it wasn't needed until G3's multi-rep dataset collection: G1's sessions
were one label per whole clip (scripts/capture.py handled that inline).
Discrete-event classes (sit_down, stand_up, lie_down, fall) need per-rep
timing, and hand-timing 20+ reps live via chat cues is unreliable (human
reaction time, countdown slop) -- but the *timing* is readily recoverable
from the signal itself, since motion transients are large, clearly separated
from baseline (established visually in G1/G2 validation). What the signal
*can't* tell you is which class each transient belongs to (e.g. sit_down vs
stand_up look like generic transients without direction-of-motion analysis
we haven't built) -- that comes from the researcher's known, scripted rep
sequence. So: detect timing from the waveform, assign labels from protocol.

Runs the same clutter-removal (single-pole IIR, alpha=0.995) + STFT
(256ms window / 50ms hop, +/-300Hz crop, per-frame median-normalized dB)
as dsp/spectrogram_service.py, offline over the whole recording, so detected
timing lines up with what the live/replay dashboard would have shown.

Three modes:
  whole      -- one label for the entire recording (e.g. idle, empty_room).
  continuous -- detect the overall active envelope (first onset to last
                offset) and label that whole span as one activity; internal
                brief pauses (e.g. turning around mid-walk) don't split it.
  discrete   -- detect each individual transient event (hysteresis + min-gap
                merge + min-duration filter) and assign labels round-robin
                from --sequence in temporal order (e.g. "sit_down,stand_up"
                for an alternating sit/stand block).

Writes data/labels/<session_id>.jsonl, patches the session's manifest.json
scripted_activity_timeline to match, and saves a QA plot (spectrogram +
energy trace + detected boundaries) to experiments/g3_dataset/figs/ so a
human can visually confirm the auto-labels before they're trusted for
training.

Usage:
    python scripts/label_tool.py --session-id 2026-07-25_sit_stand_reps \
        --mode discrete --sequence sit_down,stand_up --expected-reps 20

    python scripts/label_tool.py --session-id 2026-07-25_walk_reps \
        --mode continuous --label walk

    python scripts/label_tool.py --session-id 2026-07-25_empty_room \
        --mode whole --label empty_room
"""
import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import lfilter

REPO_ROOT = Path(__file__).resolve().parent.parent
STFT_WINDOW_S = 0.256
STFT_HOP_S = 0.050


def clutter_remove(iq, alpha=0.995):
    b = np.array([1.0, -1.0])
    a = np.array([1.0, -alpha])
    y, _ = lfilter(b, a, iq, zi=np.zeros(1, dtype=np.complex128))
    return y


def compute_energy_trace(iq, fs):
    """Returns (frame_times_s, energy_db, full_spectrogram [n_frames, n_bins], lo, hi, nperseg)."""
    nperseg = int(round(STFT_WINDOW_S * fs))
    hop = int(round(STFT_HOP_S * fs))
    window = np.hanning(nperseg)

    doppler_range_hz = 300.0
    freq_res = fs / nperseg
    crop_bins = int(round(doppler_range_hz / freq_res))
    center = nperseg // 2
    lo, hi = center - crop_bins, center + crop_bins

    clean = clutter_remove(iq).astype(np.complex64)

    times, energies, frames = [], [], []
    n = len(clean)
    pos = 0
    while pos + nperseg <= n:
        segment = clean[pos:pos + nperseg]
        spectrum = np.fft.fftshift(np.fft.fft(segment * window))
        mag_db = 20 * np.log10(np.abs(spectrum) + 1e-12)
        noise_floor = np.median(mag_db)
        mag_db_norm = (mag_db[lo:hi] - noise_floor).astype(np.float32)
        times.append((pos + nperseg / 2) / fs)
        energies.append(float(np.max(mag_db_norm)))
        frames.append(mag_db_norm)
        pos += hop

    return np.array(times), np.array(energies), np.array(frames), lo, hi, nperseg


def event_direction_signs(times, frames, freqs, timeline, strong_db=28.0):
    """Per-event direction check: median sign of the per-frame peak-Doppler-bin
    frequency, across all frames in the event whose peak exceeds strong_db
    (weak/noisy frames excluded rather than diluting the vote). This is an
    independent check on the discrete-mode round-robin label assignment --
    for a fixed antenna geometry within one session, "moving down" (sit_down,
    lie_down) and "moving up" (stand_up) should each show a consistent
    Doppler-shift sign, so a session where sit_down and stand_up cleanly
    separate by sign is strong evidence the alternating labels are correctly
    assigned; found via a real desync bug in 2026-07-27_sit_stand_reps
    (CLAUDE.md's round-robin discrete labeling has no other way to catch a
    missed/spurious detection silently shifting every label after it).

    Returns per-event (sign, n_strong_frames); sign is +1.0/-1.0/0.0 (tie) or
    None if no frame in the event was strong enough to vote.
    """
    results = []
    for seg in timeline:
        mask = (times >= seg["t_start"]) & (times <= seg["t_end"])
        sub = frames[mask]
        if len(sub) == 0:
            results.append((None, 0))
            continue
        peak_bins = np.argmax(sub, axis=1)
        peak_mags = np.max(sub, axis=1)
        strong = peak_mags > strong_db
        if strong.sum() == 0:
            results.append((None, 0))
            continue
        peak_freqs = freqs[peak_bins[strong]]
        results.append((float(np.median(np.sign(peak_freqs))), int(strong.sum())))
    return results


def verify_direction(session_id, root, min_votes=5, min_frames=4):
    """Checks an already-labeled discrete-mode session for direction-sign
    desyncs. Establishes each label's dominant sign from events with enough
    supporting frames, then flags any event whose own sign contradicts it.
    Returns (dominant_signs: {label: sign}, per_event: [(seg, sign, n, flagged)])."""
    session_dir = root / "data" / "raw" / session_id
    manifest = json.loads((session_dir / "manifest.json").read_text())
    fs = manifest["sample_rate_hz"]
    iq = np.fromfile(session_dir / f"{session_id}.sigmf-data", dtype=np.complex64)
    times, energy, frames, lo, hi, nperseg = compute_energy_trace(iq, fs)
    freq_res = fs / nperseg
    n_bins = hi - lo
    freqs = (np.arange(n_bins) - n_bins / 2) * freq_res

    timeline = [json.loads(l) for l in open(root / "data" / "labels" / f"{session_id}.jsonl") if l.strip()]
    signs = event_direction_signs(times, frames, freqs, timeline)

    by_label = {}
    for seg, (sign, n) in zip(timeline, signs):
        if sign is not None and sign != 0 and n >= min_frames:
            by_label.setdefault(seg["label"], []).append(sign)

    dominant = {}
    for label, votes in by_label.items():
        if len(votes) >= min_votes:
            dominant[label] = 1.0 if sum(votes) > 0 else -1.0

    per_event = []
    for seg, (sign, n) in zip(timeline, signs):
        expected = dominant.get(seg["label"])
        flagged = (expected is not None and sign is not None and sign != 0
                   and n >= min_frames and sign != expected)
        per_event.append((seg, sign, n, flagged))

    return dominant, per_event


def save_qa_plot(session_id, root, timeline, mode_label, times, energy, frames, lo, hi, nperseg, fs, high_db, low_db):
    figs_dir = root / "experiments" / "g3_dataset" / "figs"
    figs_dir.mkdir(parents=True, exist_ok=True)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 7), sharex=True, height_ratios=[3, 1])

    freq_res = fs / nperseg
    n_bins = hi - lo
    freqs = (np.arange(n_bins) - n_bins / 2) * freq_res
    ax1.imshow(frames.T, aspect="auto", origin="lower",
               extent=[times[0], times[-1], freqs[0], freqs[-1]],
               cmap="viridis", vmin=10, vmax=45)
    ax1.set_ylabel("Doppler (Hz)")
    ax1.set_title(f"{session_id} -- mode={mode_label}, {len(timeline)} labeled segment(s)")

    ax2.plot(times, energy, lw=0.8, color="tab:blue", label="peak energy (dB above frame floor)")
    ax2.axhline(high_db, color="red", ls="--", lw=0.8, label=f"high={high_db}dB")
    ax2.axhline(low_db, color="orange", ls="--", lw=0.8, label=f"low={low_db}dB")
    ax2.set_ylabel("dB")
    ax2.set_xlabel("time (s)")
    ax2.legend(loc="upper right", fontsize=7)

    for seg in timeline:
        for ax in (ax1, ax2):
            ax.axvline(seg["t_start"], color="white", lw=1.0, alpha=0.8)
            ax.axvline(seg["t_end"], color="black", lw=1.0, alpha=0.5)
        ax1.text(seg["t_start"], freqs[-1] * 0.9, seg["label"], color="white", fontsize=7, rotation=90, va="top")

    fig.tight_layout()
    out_png = figs_dir / f"{session_id}_labels.png"
    fig.savefig(out_png, dpi=120)
    plt.close(fig)
    return out_png


def detect_events(times, energy, high, low, min_dur_s, merge_gap_s):
    events = []
    state = "quiet"
    start = None
    for t, e in zip(times, energy):
        if state == "quiet" and e >= high:
            state, start = "active", t
        elif state == "active" and e < low:
            events.append([start, t])
            state = "quiet"
    if state == "active":
        events.append([start, times[-1]])

    merged = []
    for ev in events:
        if merged and ev[0] - merged[-1][1] < merge_gap_s:
            merged[-1][1] = ev[1]
        else:
            merged.append(ev)

    return [ev for ev in merged if ev[1] - ev[0] >= min_dur_s]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--session-id", required=True)
    ap.add_argument("--mode", required=True, choices=["whole", "continuous", "discrete", "verify"])
    ap.add_argument("--fix", choices=["report", "swap", "exclude"], default="report",
                     help="verify mode only: report=print findings only (default); "
                          "swap=flip flagged events' labels in place; exclude=drop flagged events from the labels file")
    ap.add_argument("--label", help="activity label for whole/continuous modes")
    ap.add_argument("--sequence", help="comma-separated label cycle for discrete mode, e.g. sit_down,stand_up")
    ap.add_argument("--expected-reps", type=int, default=None, help="warn (not fail) if detected event count differs")
    ap.add_argument("--high-db", type=float, default=30.0, help="hysteresis high threshold, dB above frame noise floor")
    ap.add_argument("--low-db", type=float, default=25.0, help="hysteresis low threshold")
    ap.add_argument("--min-event-s", type=float, default=0.15, help="calibrated against real G1 data: a real stand_up transient measured only ~0.15s above threshold, weaker/briefer than sit_down's -- don't filter it out")
    ap.add_argument("--merge-gap-s", type=float, default=0.6, help="merge detections closer than this (discrete/continuous)")
    ap.add_argument("--data-root", default=str(REPO_ROOT))
    args = ap.parse_args()

    root = Path(args.data_root)
    session_dir = root / "data" / "raw" / args.session_id
    manifest_path = session_dir / "manifest.json"
    if not manifest_path.exists():
        sys.exit(f"no such session: {manifest_path}")

    if args.mode == "verify":
        dominant, per_event = verify_direction(args.session_id, root)
        print(f"{args.session_id}: dominant sign by label (from events with >=5 confident votes): "
              f"{ {k: ('+' if v>0 else '-') for k,v in dominant.items()} }")
        if not dominant:
            print("  no label had enough confident (n>=4 strong frames) events to establish a dominant sign -- "
                  "this session's direction check is INCONCLUSIVE, not confirmed-clean. Do not treat silence as verification.")
        n_flagged = sum(1 for _, _, _, f in per_event if f)
        for seg, sign, n, flagged in per_event:
            marker = "  <-- FLAGGED" if flagged else ""
            s = "?" if sign is None else ("+" if sign > 0 else ("-" if sign < 0 else "0"))
            print(f"  {seg['t_start']:7.2f}s-{seg['t_end']:7.2f}s  {seg['label']:10s} sign={s} n={n}{marker}")
        print(f"{n_flagged} of {len(per_event)} events flagged as direction-inconsistent with their session's dominant pattern.")

        if args.fix != "report" and n_flagged:
            timeline = [json.loads(l) for l in open(root / "data" / "labels" / f"{args.session_id}.jsonl") if l.strip()]
            other_label = {}
            labels_present = list(dominant.keys())
            if len(labels_present) == 2:
                other_label = {labels_present[0]: labels_present[1], labels_present[1]: labels_present[0]}
            new_timeline = []
            for seg, (_, _, _, flagged) in zip(timeline, per_event):
                if not flagged:
                    new_timeline.append(seg)
                elif args.fix == "swap" and seg["label"] in other_label:
                    new_timeline.append({**seg, "label": other_label[seg["label"]]})
                elif args.fix == "exclude":
                    pass  # dropped
                else:
                    new_timeline.append(seg)  # can't swap without a known label pair -- leave as-is
            labels_path = root / "data" / "labels" / f"{args.session_id}.jsonl"
            with open(labels_path, "w") as f:
                for seg in new_timeline:
                    f.write(json.dumps(seg) + "\n")
            manifest = json.loads(manifest_path.read_text())
            manifest["scripted_activity_timeline"] = new_timeline
            manifest_path.write_text(json.dumps(manifest, indent=2))
            print(f"applied --fix {args.fix}: {labels_path} now has {len(new_timeline)} segments (was {len(timeline)})")

            session_dir_v = root / "data" / "raw" / args.session_id
            manifest_v = json.loads((session_dir_v / "manifest.json").read_text())
            fs_v = manifest_v["sample_rate_hz"]
            iq_v = np.fromfile(session_dir_v / f"{args.session_id}.sigmf-data", dtype=np.complex64)
            times_v, energy_v, frames_v, lo_v, hi_v, nperseg_v = compute_energy_trace(iq_v, fs_v)
            out_png = save_qa_plot(args.session_id, root, new_timeline, f"verify --fix {args.fix}",
                                    times_v, energy_v, frames_v, lo_v, hi_v, nperseg_v, fs_v,
                                    args.high_db, args.low_db)
            print(f"updated QA plot: {out_png}")
        return

    manifest = json.loads(manifest_path.read_text())
    fs = manifest["sample_rate_hz"]

    data_path = session_dir / f"{args.session_id}.sigmf-data"
    iq = np.fromfile(data_path, dtype=np.complex64)
    duration_s = len(iq) / fs

    times, energy, frames, lo, hi, nperseg = compute_energy_trace(iq, fs)

    if args.mode == "whole":
        if not args.label:
            sys.exit("--mode whole requires --label")
        timeline = [{"t_start": 0.0, "t_end": duration_s, "label": args.label}]
        detected_spans = []
    else:
        raw_events = detect_events(times, energy, args.high_db, args.low_db, args.min_event_s, args.merge_gap_s)
        if not raw_events:
            sys.exit(f"FAIL: no motion events detected above {args.high_db}dB threshold in {args.session_id} -- "
                      f"check the recording captured real motion (max energy observed: {energy.max():.1f}dB)")
        detected_spans = raw_events

        if args.mode == "continuous":
            if not args.label:
                sys.exit("--mode continuous requires --label")
            timeline = [{"t_start": raw_events[0][0], "t_end": raw_events[-1][1], "label": args.label}]
        else:  # discrete
            if not args.sequence:
                sys.exit("--mode discrete requires --sequence, e.g. sit_down,stand_up")
            seq = args.sequence.split(",")
            timeline = [
                {"t_start": ev[0], "t_end": ev[1], "label": seq[i % len(seq)]}
                for i, ev in enumerate(raw_events)
            ]
            if args.expected_reps is not None and len(raw_events) != args.expected_reps:
                print(f"WARNING: detected {len(raw_events)} events, expected {args.expected_reps} -- "
                      f"inspect the QA plot before trusting these labels.", file=sys.stderr)

    labels_dir = root / "data" / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)
    with open(labels_dir / f"{args.session_id}.jsonl", "w") as f:
        for seg in timeline:
            f.write(json.dumps(seg) + "\n")

    manifest["scripted_activity_timeline"] = timeline
    manifest_path.write_text(json.dumps(manifest, indent=2))

    out_png = save_qa_plot(args.session_id, root, timeline, args.mode, times, energy, frames, lo, hi,
                            nperseg, fs, args.high_db, args.low_db)

    print(f"wrote {labels_dir / f'{args.session_id}.jsonl'} ({len(timeline)} segments)")
    print(f"patched {manifest_path}")
    print(f"QA plot: {out_png}")
    for seg in timeline:
        print(f"  {seg['t_start']:6.2f}s - {seg['t_end']:6.2f}s  {seg['label']}")


if __name__ == "__main__":
    main()
