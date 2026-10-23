#!/usr/bin/env python3
"""Real-antenna sanity check: TX a brief, minimum-gain CW tone through the
physical antenna on RF1 (antenna="TX/RX") and confirm RX (same port, shared
antenna -- standard single-antenna monostatic CW radar config) sees it.

Distinct from scripts/tone_loopback_test.py, which used the internal CAL
path and radiates nothing. This one genuinely transmits, at minimum gain,
briefly, inside the confirmed 5.8 GHz ISM band -- Prime Directive 1 applies
in full: TX gain starts at minimum, session logged to logs/tx_log.csv.

Usage:
    python scripts/tone_antenna_test.py
"""
import csv
import datetime as dt
import sys
import threading
from pathlib import Path

import numpy as np
import uhd

REPO_ROOT = Path(__file__).resolve().parent.parent

F0 = 5.8e9
TONE_OFFSET_HZ = 100e3
SAMP_RATE = 1e6
TX_GAIN_DB = 0.0  # minimum -- Prime Directive 1
RX_GAIN_DB = 20.0
DURATION_S = 2.0
N_RX_SAMPLES = int(SAMP_RATE * DURATION_S)


def log_tx_session(status):
    log_path = REPO_ROOT / "logs" / "tx_log.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not log_path.exists()
    with open(log_path, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["timestamp_utc", "session_id", "f0_hz", "tx_gain_db", "rx_gain_db", "duration_s", "note", "status"])
        writer.writerow([dt.datetime.now(dt.timezone.utc).isoformat(), "g0_real_antenna_test", F0, TX_GAIN_DB, RX_GAIN_DB, DURATION_S, "real-antenna (RF1, TX/RX) tone sanity check", status])


def main():
    usrp = uhd.usrp.MultiUSRP("addr=192.168.10.50")

    usrp.set_tx_antenna("TX/RX", 0)
    usrp.set_rx_antenna("TX/RX", 0)
    usrp.set_tx_rate(SAMP_RATE, 0)
    usrp.set_rx_rate(SAMP_RATE, 0)
    usrp.set_tx_freq(uhd.types.TuneRequest(F0), 0)
    usrp.set_rx_freq(uhd.types.TuneRequest(F0), 0)
    usrp.set_tx_gain(TX_GAIN_DB, 0)
    usrp.set_rx_gain(RX_GAIN_DB, 0)

    log_tx_session("STARTED")
    try:
        tx_streamer = usrp.get_tx_stream(uhd.usrp.StreamArgs("fc32", "sc16"))
        rx_streamer = usrp.get_rx_stream(uhd.usrp.StreamArgs("fc32", "sc16"))

        t = np.arange(4096) / SAMP_RATE
        tone = 0.3 * np.exp(1j * 2 * np.pi * TONE_OFFSET_HZ * t).astype(np.complex64)

        stop_flag = threading.Event()

        def tx_worker():
            tx_md = uhd.types.TXMetadata()
            while not stop_flag.is_set():
                tx_streamer.send(tone, tx_md)

        tx_thread = threading.Thread(target=tx_worker, daemon=True)
        tx_thread.start()

        rx_md = uhd.types.RXMetadata()
        buf = np.zeros(N_RX_SAMPLES, dtype=np.complex64)
        rx_streamer.issue_stream_cmd(uhd.types.StreamCMD(uhd.types.StreamMode.start_cont))
        recv_buffer = np.zeros(rx_streamer.get_max_num_samps(), dtype=np.complex64)
        n_received = 0
        while n_received < N_RX_SAMPLES:
            n = rx_streamer.recv(recv_buffer, rx_md)
            n_copy = min(n, N_RX_SAMPLES - n_received)
            buf[n_received:n_received + n_copy] = recv_buffer[:n_copy]
            n_received += n_copy
        rx_streamer.issue_stream_cmd(uhd.types.StreamCMD(uhd.types.StreamMode.stop_cont))

        stop_flag.set()
        tx_thread.join(timeout=2)

        log_tx_session("COMPLETED")
    except Exception as e:
        log_tx_session(f"FAILED: {e}")
        raise

    spectrum = np.fft.fftshift(np.fft.fft(buf * np.hanning(len(buf))))
    freqs = np.fft.fftshift(np.fft.fftfreq(len(buf), d=1 / SAMP_RATE))
    mag_db = 20 * np.log10(np.abs(spectrum) + 1e-12)

    peak_idx = np.argmax(mag_db)
    peak_freq = freqs[peak_idx]
    peak_db = mag_db[peak_idx]
    noise_floor_db = np.median(mag_db)

    print(f"Expected tone offset: {TONE_OFFSET_HZ / 1e3:.1f} kHz")
    print(f"Detected peak offset: {peak_freq / 1e3:.1f} kHz")
    print(f"Peak level: {peak_db:.1f} dB, noise floor (median): {noise_floor_db:.1f} dB, SNR: {peak_db - noise_floor_db:.1f} dB")

    freq_error_hz = abs(peak_freq - TONE_OFFSET_HZ)
    tolerance_hz = 5e3
    snr_db = peak_db - noise_floor_db

    if freq_error_hz <= tolerance_hz and snr_db > 10:
        print(f"PASS: tone detected within {freq_error_hz:.0f} Hz of expected offset, SNR {snr_db:.1f} dB")
        sys.exit(0)
    else:
        print(f"FAIL: freq_error={freq_error_hz:.0f} Hz (tolerance {tolerance_hz:.0f} Hz), SNR={snr_db:.1f} dB")
        sys.exit(1)


if __name__ == "__main__":
    main()
