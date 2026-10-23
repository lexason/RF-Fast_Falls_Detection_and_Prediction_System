#!/usr/bin/env python3
"""One-command replay -> ZMQ -> PSD/spectrogram pipeline check (G1 acceptance test).

Launches sdr/replay_source.py against a recorded session, subscribes to its
ZMQ PUB output (the same interface a live G2 DSP service will consume),
collects the full session, and plots a PSD + spectrogram. This exercises the
exact capture-format -> replay -> downstream-consumer path end to end, not
just a direct file read, so a failure here would also flag a real replay/ZMQ
plumbing problem.

Usage:
    python scripts/psd_plot.py data/raw/2026-07-17_synthetic_walking
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import zmq

REPO_ROOT = Path(__file__).resolve().parent.parent

# Locked-in spectrogram parameters (CLAUDE.md §7): 256 ms Hann window, 50 ms hop.
STFT_WINDOW_S = 0.256
STFT_HOP_S = 0.050


def collect_via_zmq(session_dir, manifest, zmq_addr, idle_timeout_s=5.0):
    fs = manifest["sample_rate_hz"]
    total_samples = int(round(sum(seg["t_end"] - seg["t_start"] for seg in manifest["scripted_activity_timeline"]) * fs))

    # Connect+subscribe before the publisher starts (ZMQ "slow joiner": messages
    # published before a SUB socket finishes connecting are silently dropped).
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_addr)
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    sub.setsockopt(zmq.RCVTIMEO, int(idle_timeout_s * 1000))
    time.sleep(0.5)

    replay_proc = subprocess.Popen(
        [
            sys.executable, str(REPO_ROOT / "sdr" / "replay_source.py"),
            "--iq-file", str(session_dir / f"{manifest['session_id']}.sigmf-data"),
            "--samp-rate", str(fs),
            "--zmq-addr", zmq_addr,
            "--repeat", "False",
        ],
        # stdin=PIPE (left open, not closed) so the flowgraph's blocking
        # input('Press Enter to quit: ') hangs until we terminate() it,
        # instead of hitting immediate EOF on an inherited closed stdin.
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    try:
        chunks = []
        n_collected = 0
        while n_collected < total_samples:
            try:
                msg = sub.recv()
            except zmq.Again:
                break
            chunks.append(np.frombuffer(msg, dtype=np.complex64))
            n_collected += len(chunks[-1])
        sub.close()
        ctx.term()
    finally:
        replay_proc.terminate()
        try:
            replay_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            replay_proc.kill()

    if not chunks:
        stderr = replay_proc.stderr.read() if replay_proc.stderr else ""
        sys.exit(f"error: received no samples over ZMQ from replay flowgraph.\nreplay stderr:\n{stderr}")

    iq = np.concatenate(chunks)[:total_samples]
    if len(iq) < total_samples:
        print(f"warning: collected {len(iq)}/{total_samples} samples before idle timeout", file=sys.stderr)
    return iq, fs


def plot_psd_and_spectrogram(iq, fs, session_id, labels, out_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy import signal

    out_dir.mkdir(parents=True, exist_ok=True)

    # PSD (Welch)
    freqs, psd = signal.welch(iq, fs=fs, nperseg=min(4096, len(iq)), return_onesided=False)
    freqs = np.fft.fftshift(freqs)
    psd = np.fft.fftshift(psd)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(freqs, 10 * np.log10(psd + 1e-20))
    ax.set_xlabel("Doppler frequency offset (Hz)")
    ax.set_ylabel("PSD (dB/Hz)")
    ax.set_title(f"PSD - {session_id}")
    ax.grid(True, alpha=0.3)
    psd_path = out_dir / f"{session_id}_psd.png"
    fig.tight_layout()
    fig.savefig(psd_path, dpi=120)
    plt.close(fig)

    # Spectrogram at the locked-in window/hop
    nperseg = int(round(STFT_WINDOW_S * fs))
    noverlap = nperseg - int(round(STFT_HOP_S * fs))
    f, t, Sxx = signal.spectrogram(iq, fs=fs, window="hann", nperseg=nperseg,
                                    noverlap=noverlap, return_onesided=False)
    f = np.fft.fftshift(f)
    Sxx = np.fft.fftshift(Sxx, axes=0)

    fig, ax = plt.subplots(figsize=(10, 4))
    mesh = ax.pcolormesh(t, f, 10 * np.log10(Sxx + 1e-20), shading="auto", cmap="viridis")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Doppler frequency offset (Hz)")
    ax.set_ylim(-300, 300)
    ax.set_title(f"Micro-Doppler spectrogram - {session_id}")
    fig.colorbar(mesh, ax=ax, label="dB")
    for seg in labels:
        ax.axvline(seg["t_start"], color="white", linestyle="--", alpha=0.5, linewidth=0.8)
        ax.text(seg["t_start"], 280, seg["label"], color="white", fontsize=7, rotation=90, va="top")
    spec_path = out_dir / f"{session_id}_spectrogram.png"
    fig.tight_layout()
    fig.savefig(spec_path, dpi=120)
    plt.close(fig)

    return psd_path, spec_path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session_dir")
    ap.add_argument("--zmq-addr", default="tcp://127.0.0.1:5556")
    ap.add_argument("--out-dir", default=str(REPO_ROOT / "experiments" / "g1_pipeline_check" / "figs"))
    args = ap.parse_args()

    session_dir = Path(args.session_dir)
    manifest = json.loads((session_dir / "manifest.json").read_text())
    session_id = manifest["session_id"]

    if manifest.get("synthetic"):
        print(f"NOTE: {manifest.get('synthetic_warning', 'synthetic session')}", file=sys.stderr)

    print(f"replaying {session_id} over {args.zmq_addr} and collecting via ZMQ SUB...", file=sys.stderr)
    t0 = time.time()
    iq, fs = collect_via_zmq(session_dir, manifest, args.zmq_addr)
    print(f"collected {len(iq)} samples in {time.time() - t0:.1f}s wall time", file=sys.stderr)

    psd_path, spec_path = plot_psd_and_spectrogram(iq, fs, session_id, manifest["scripted_activity_timeline"], Path(args.out_dir))
    print(f"wrote {psd_path}")
    print(f"wrote {spec_path}")


if __name__ == "__main__":
    main()
