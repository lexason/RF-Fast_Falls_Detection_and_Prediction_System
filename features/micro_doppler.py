"""G3 classifier v1 feature library: per-window micro-Doppler features.

CLAUDE.md §6 G3 task 2 specifies six base features per window (Doppler
bandwidth, spectral centroid/entropy, energy, torso-line strength, transient
score) feeding a gradient-boosted-tree classifier. Operates on the same
clutter-removed, noise-floor-normalized STFT frames that
dsp/spectrogram_service.py streams live and scripts/label_tool.py uses for
offline event detection -- one DSP front end, three consumers.

Two more features added 2026-07-29 after v1's first LOSO run (macro-F1=0.42,
confusion concentrated in sit_down/stand_up/lie_down/fall) confirmed the exact
failure CLAUDE.md §9 warned about: "sitting vs falling confusion... the
speed-of-descent + post-stillness features are what separate them -- make
sure they're in the feature set." They weren't, until now -- see STATE.md
2026-07-29 entry for the root-cause analysis.

A ninth feature (event_duration_s) added the same day after the researcher
explained that "stand_up" as recorded is not one homogeneous motion: a quick,
sharp recovery immediately after a fall; a normal-paced rise from a chair;
and a slow, multi-phase rise off the floor (knees, then flat, then reverse)
recorded during lie_down sessions. This directly explained why falls were
being predicted as stand_up so often (a fall's own quick recovery phase looks
similar to a generic "rising" transient) -- event duration is the most direct
available signal for which of these three "stand_up" variants a given window
actually is.

2026-09-12: the three Doppler-frequency features (spectral centroid, Doppler
bandwidth, descent rate) were converted from raw Hz to velocity (m/s and
m/s^2) because Doppler shift scales with carrier frequency
(f_d = 2*v*f0/c) -- a raw-Hz feature trained on one carrier is quantitatively
wrong on another (e.g. 1 m/s is ~38.7 Hz at 5.8 GHz but only ~16.4 Hz at
2.462 GHz, the carrier this project switched to the same day for antenna-
frequency-rating reasons -- see STATE.md decision log). f0_hz is now a
required argument specifically so this can never be silently defaulted to
the wrong carrier for a given session's actual capture (or live) frequency.
"""
import numpy as np

TORSO_BAND_HZ = 15.0  # narrow band around each frame's peak bin -- concentrated single-reflector energy
C_LIGHT_M_PER_S = 299792458.0


def window_features(frames, freqs, f0_hz, frame_times=None, event_t0=None, event_t1=None):
    """frames: [n_frames, n_bins] per-frame magnitude, dB above that frame's own
    noise floor (dsp/spectrogram_service.py's mag_db_norm convention).
    freqs: [n_bins] Doppler frequency axis, Hz.
    f0_hz: the radar carrier frequency (Hz) this data was captured/streamed
        at -- e.g. a session's manifest.json "carrier_hz", or the live
        config's carrier.f0_hz. Required (no default) so callers can't
        silently mix data from different carriers into the same raw-Hz
        feature space; see the 2026-09-12 module docstring note above.
    frame_times: [n_frames] absolute timestamps (s) of each frame, needed for
        the two rate/post-event features below. If omitted, those two
        features fall back to 0.0 (e.g. not meaningful/available).
    event_t0, event_t1: the labeled event's own boundaries (s, same clock as
        frame_times), when this window was built around a discrete transient
        (scripts/build_dataset.py's window_for_event). None for continuous-
        class windows (walk/idle), which have no single "event end" -- post-
        stillness falls back to using the window midpoint as a boundary.

    Returns a dict of eight scalar features summarizing the whole window.
    """
    doppler_to_velocity = C_LIGHT_M_PER_S / (2.0 * f0_hz)  # v = f_d * c / (2*f0)

    lin = 10 ** (frames / 10.0)  # dB -> linear power-like weight; negative dB (below frame's own
    agg_power = lin.sum(axis=0)  # median) contributes almost nothing, positive dB dominates
    total_power = agg_power.sum() + 1e-12

    spectral_centroid_hz = float((agg_power * freqs).sum() / total_power)
    doppler_bandwidth_hz = float(np.sqrt((agg_power * (freqs - spectral_centroid_hz) ** 2).sum() / total_power))
    spectral_centroid_mps = spectral_centroid_hz * doppler_to_velocity
    doppler_bandwidth_mps = doppler_bandwidth_hz * doppler_to_velocity

    p = agg_power / total_power
    p = p[p > 0]
    spectral_entropy = float(-(p * np.log2(p)).sum() / np.log2(len(agg_power)))  # normalized to [0,1]

    energy_db = float(np.mean(np.max(frames, axis=1)))

    freq_res = freqs[1] - freqs[0]
    band_bins = max(1, int(round(TORSO_BAND_HZ / freq_res)))
    peak_bins = np.argmax(frames, axis=1)
    torso_power = 0.0
    for i, pb in enumerate(peak_bins):
        lo, hi = max(0, pb - band_bins), min(frames.shape[1], pb + band_bins + 1)
        torso_power += lin[i, lo:hi].sum()
    torso_line_strength = float(torso_power / total_power)

    peak_env = np.max(frames, axis=1)
    transient_score_db = float(np.max(np.abs(np.diff(peak_env)))) if len(peak_env) > 1 else 0.0

    descent_accel_mps2 = 0.0
    post_event_stillness_db = 0.0
    if frame_times is not None and len(frame_times) > 1:
        # Descent rate: fastest Doppler-frequency swing in the window (Hz/s),
        # using each frame's peak-bin frequency as the instantaneous velocity
        # proxy, then converted to m/s^2 via the same Doppler-to-velocity
        # scale as the other two frequency-derived features above. A fall's
        # rapid, largely-uncontrolled drop should swing much faster than a
        # controlled sit_down/lie_down; stand_up swings the opposite
        # direction but at a comparable controlled pace to sit_down.
        peak_freqs = freqs[peak_bins]
        dt = np.diff(frame_times)
        dt[dt <= 0] = np.median(dt[dt > 0]) if (dt > 0).any() else 0.05
        rate = np.diff(peak_freqs) / dt
        descent_accel_mps2 = float(np.max(np.abs(rate))) * doppler_to_velocity

        # Post-event stillness: mean energy in the window AFTER the event
        # ends (or after the window midpoint, for continuous-class windows
        # with no single event boundary). CLAUDE.md §4: a fall is "a
        # high-energy broadband transient AND post-event stillness" -- low
        # value here means quiet/still afterward (expected for a real fall),
        # a higher value means continued motion (e.g. settling into a chair,
        # or getting back up), which is exactly the sit_down/fall
        # discriminator CLAUDE.md §9 calls out.
        boundary = event_t1 if event_t1 is not None else (frame_times[0] + frame_times[-1]) / 2
        post_mask = frame_times >= boundary
        if post_mask.sum() >= 2:
            post_event_stillness_db = float(np.mean(np.max(frames[post_mask], axis=1)))
        else:
            post_event_stillness_db = float(np.max(frames[-1])) if len(frames) else 0.0

    # Event duration: the labeled event's own span (not the window's, which is
    # always WINDOW_S by construction). Fast/sharp motions (fall, and its
    # immediate quick recovery) should be short; the slow multi-phase lie_down
    # transition should be long; sit_stand's normal-paced stand_up in between.
    # No single event boundary for continuous-class windows (walk/idle) --
    # falls back to the full window span, a distinct, consistently-large value
    # those classes will always share (harmless: they're already well-separated
    # from the discrete classes on other features).
    if event_t0 is not None and event_t1 is not None:
        event_duration_s = float(event_t1 - event_t0)
    elif frame_times is not None and len(frame_times) > 1:
        event_duration_s = float(frame_times[-1] - frame_times[0])
    else:
        event_duration_s = 0.0

    return {
        "spectral_centroid_mps": spectral_centroid_mps,
        "doppler_bandwidth_mps": doppler_bandwidth_mps,
        "spectral_entropy": spectral_entropy,
        "energy_db": energy_db,
        "torso_line_strength": torso_line_strength,
        "transient_score_db": transient_score_db,
        "descent_accel_mps2": descent_accel_mps2,
        "post_event_stillness_db": post_event_stillness_db,
        "event_duration_s": event_duration_s,
    }


FEATURE_NAMES = ["spectral_centroid_mps", "doppler_bandwidth_mps", "spectral_entropy",
                  "energy_db", "torso_line_strength", "transient_score_db",
                  "descent_accel_mps2", "post_event_stillness_db", "event_duration_s"]
