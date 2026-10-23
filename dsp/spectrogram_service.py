#!/usr/bin/env python3
"""G2: real-time clutter removal + STFT micro-Doppler spectrogram service.

Subscribes to raw IQ over ZMQ SUB (from sdr/cw_doppler_tx_rx.py live, or
sdr/replay_source.py for file-backed dev -- same interface, this service
doesn't care which). Applies continuous clutter/DC removal (slow-time
high-pass / frame-to-frame subtraction, WiTrack method, per CLAUDE.md §7's
locked-in decision), then computes a sliding STFT (256ms Hann window,
50ms hop -> 20fps target) with per-frame noise-floor normalization, and
publishes spectrogram columns over a second ZMQ PUB for the live waterfall
viewer.

Wire format out: each message is a float64 source-sample-clock frame-centre
timestamp (8 bytes) followed by a float32 array of normalized dB magnitude
values, cropped to +/-300 Hz around DC (CLAUDE.md §4: human motion Doppler
spans roughly +/-250 Hz) -- keeps frames small for the live WebSocket
viewer instead of shipping the full FFT width.

Usage:
    python dsp/spectrogram_service.py --in-addr tcp://127.0.0.1:5580 \
        --out-addr tcp://127.0.0.1:5581
"""
import argparse
import json
import math
import signal
import struct
import sys
import time
from dataclasses import asdict, dataclass

import numpy as np
import zmq
from scipy.signal import lfilter

STFT_WINDOW_S = 0.256
STFT_HOP_S = 0.050
IQ_MESSAGE_MAGIC = b"RFIQv1\x00\x00"


def doppler_frequencies(sample_rate_hz: float, expected_bins: int | None = None) -> np.ndarray:
    """Return the exact cropped FFT-bin centres shared by training and serving."""
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample rate must be finite and positive")
    nperseg = int(round(STFT_WINDOW_S * sample_rate_hz))
    frequency_resolution_hz = sample_rate_hz / nperseg
    crop_bins = int(round(300.0 / frequency_resolution_hz))
    bin_count = 2 * crop_bins
    if expected_bins is not None and expected_bins != bin_count:
        raise ValueError(f"expected {bin_count} Doppler bins at {sample_rate_hz:g} Hz, got {expected_bins}")
    return (np.arange(bin_count) - bin_count / 2) * frequency_resolution_hz


@dataclass
class StreamHealth:
    """Deterministic input-integrity counters emitted when the service stops."""

    input_chunks: int = 0
    input_samples: int = 0
    frames_published: int = 0
    invalid_chunks: int = 0
    invalid_frames: int = 0
    sequence_gaps: int = 0


@dataclass
class SourceSequenceTracker:
    expected_source_index: int | None = None
    sequence_gaps: int = 0

    def observe(self, source_index: int, chunk_samples: int) -> bool:
        """Advance the sample counter and report whether this chunk is discontinuous."""
        discontinuous = self.expected_source_index is not None and source_index != self.expected_source_index
        if discontinuous:
            self.sequence_gaps += 1
        self.expected_source_index = source_index + chunk_samples
        return discontinuous


class ClutterRemover:
    """Single-pole DC-blocker / high-pass IIR filter, applied continuously
    across the raw IQ stream -- WiTrack's frame-to-frame subtraction
    (CLAUDE.md §7: "slow-time high-pass / frame subtraction"), vectorized
    via scipy.signal.lfilter with persistent state (zi) across chunks so
    it stays real-time at 250 kS/s (a pure-Python per-sample loop would not).

    y[n] = x[n] - x[n-1] + alpha*y[n-1]  =>  b=[1,-1], a=[1,-alpha]
    """
    def __init__(self, alpha=0.995):
        self.b = np.array([1.0, -1.0])
        self.a = np.array([1.0, -alpha])
        self.zi = np.zeros(1, dtype=np.complex128)

    def process(self, x):
        if x.ndim != 1 or x.size == 0:
            raise ValueError("IQ chunk must be a non-empty vector")
        if not np.all(np.isfinite(x)):
            raise ValueError("IQ chunk contains NaN or infinity")
        y, self.zi = lfilter(self.b, self.a, x, zi=self.zi)
        return y


def decode_iq_chunk(message):
    """Validate and decode the internal complex64 replay/acquisition payload."""
    if not message or len(message) % np.dtype(np.complex64).itemsize:
        raise ValueError("IQ message is empty or not aligned to complex64")
    chunk = np.frombuffer(message, dtype=np.complex64)
    if not np.all(np.isfinite(chunk)):
        raise ValueError("IQ message contains NaN or infinity")
    return chunk


def decode_iq_message(message):
    """Return optional source sample index and a validated complex64 chunk."""
    if message.startswith(IQ_MESSAGE_MAGIC):
        if len(message) < 16:
            raise ValueError("typed IQ message is truncated")
        source_sample_index = struct.unpack("<Q", message[8:16])[0]
        return source_sample_index, decode_iq_chunk(message[16:])
    return None, decode_iq_chunk(message)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in-addr", default="tcp://127.0.0.1:5580", help="ZMQ SUB address for raw IQ input")
    ap.add_argument("--out-addr", default="tcp://127.0.0.1:5581", help="ZMQ PUB address for spectrogram output")
    ap.add_argument("--samp-rate", type=float, default=250000.0)
    args = ap.parse_args()

    fs = args.samp_rate
    if not math.isfinite(fs) or fs <= 0:
        raise SystemExit("sample rate must be finite and positive")
    nperseg = int(round(STFT_WINDOW_S * fs))
    hop = int(round(STFT_HOP_S * fs))
    window = np.hanning(nperseg)

    doppler_range_hz = 300.0
    frequencies = doppler_frequencies(fs)
    crop_bins = len(frequencies) // 2
    center = nperseg // 2
    lo, hi = center - crop_bins, center + crop_bins

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(args.in_addr)
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    sub.setsockopt(zmq.RCVTIMEO, 1000)
    sub.setsockopt(zmq.LINGER, 0)

    pub = ctx.socket(zmq.PUB)
    pub.setsockopt(zmq.LINGER, 0)
    pub.bind(args.out_addr)

    clutter = ClutterRemover()
    buf = np.zeros(0, dtype=np.complex64)

    print(f"spectrogram service: {args.in_addr} -> {args.out_addr}, "
          f"window={nperseg} samples ({STFT_WINDOW_S*1000:.0f}ms), hop={hop} samples ({STFT_HOP_S*1000:.0f}ms), "
          f"output cropped to +/-{doppler_range_hz:.0f}Hz ({hi - lo} bins)",
          file=sys.stderr)

    n_frames = 0
    next_log_frame = 100
    health = StreamHealth()
    sequence = SourceSequenceTracker()
    buffer_start_index = None
    timestamp_origin = None
    explicit_sample_clock = None
    t_start = time.time()
    stop_requested = False

    def request_stop(_signum, _frame):
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        while not stop_requested:
            try:
                msg = sub.recv()
            except zmq.Again:
                continue
            try:
                source_index, decoded = decode_iq_message(msg)
            except ValueError as exc:
                health.invalid_chunks += 1
                print(f"discarded invalid IQ chunk #{health.invalid_chunks}: {exc}", file=sys.stderr)
                continue
            is_explicit = source_index is not None
            if explicit_sample_clock is None:
                explicit_sample_clock = is_explicit
                timestamp_origin = 0.0 if is_explicit else time.time()
            elif explicit_sample_clock != is_explicit:
                health.invalid_chunks += 1
                print("discarded IQ chunk after time-basis change", file=sys.stderr)
                continue
            if source_index is None:
                source_index = sequence.expected_source_index if sequence.expected_source_index is not None else 0
            if sequence.observe(source_index, len(decoded)):
                health.sequence_gaps = sequence.sequence_gaps
                print(
                    f"IQ sequence gap #{health.sequence_gaps}: expected sample continuity, got {source_index}; resetting DSP state",
                    file=sys.stderr,
                )
                buf = np.zeros(0, dtype=np.complex64)
                buffer_start_index = None
                clutter = ClutterRemover()
            try:
                chunk = clutter.process(decoded).astype(np.complex64)
            except ValueError as exc:
                health.invalid_chunks += 1
                print(f"discarded invalid IQ chunk #{health.invalid_chunks}: {exc}", file=sys.stderr)
                continue
            health.input_chunks += 1
            health.input_samples += len(decoded)
            if buffer_start_index is None:
                buffer_start_index = source_index
            buf = np.concatenate([buf, chunk])

            while len(buf) >= nperseg:
                assert buffer_start_index is not None and timestamp_origin is not None
                frame_time = timestamp_origin + (buffer_start_index + nperseg / 2) / fs
                segment = buf[:nperseg]
                spectrum = np.fft.fftshift(np.fft.fft(segment * window))
                mag_db = 20 * np.log10(np.abs(spectrum) + 1e-12)
                noise_floor = np.median(mag_db)
                mag_db_norm = (mag_db[lo:hi] - noise_floor).astype(np.float32)
                if not np.all(np.isfinite(mag_db_norm)):
                    health.invalid_frames += 1
                    print("discarded non-finite spectrogram frame", file=sys.stderr)
                    buf = buf[hop:]
                    continue

                header = np.array([frame_time], dtype=np.float64).tobytes()
                pub.send(header + mag_db_norm.tobytes())
                health.frames_published += 1

                buf = buf[hop:]
                buffer_start_index += hop
                n_frames += 1

            if n_frames >= next_log_frame:
                elapsed = time.time() - t_start
                print(f"{n_frames} frames, {n_frames / elapsed:.1f} fps avg", file=sys.stderr)
                next_log_frame = ((n_frames // 100) + 1) * 100
    except KeyboardInterrupt:
        pass
    finally:
        health.sequence_gaps = sequence.sequence_gaps
        print("DSP_HEALTH_JSON=" + json.dumps(asdict(health), sort_keys=True), file=sys.stderr)
        sub.close(0)
        pub.close(0)
        ctx.term()


if __name__ == "__main__":
    main()
