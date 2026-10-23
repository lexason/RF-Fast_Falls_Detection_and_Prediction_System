# CARAT RF stop and shutdown evidence

At 2026-08-07T03:54Z, process inspection found the following CARAT chain running from the
carat_research working directory:

- PID 5412: sdr/cw_doppler_tx_rx.py --tx-gain 5 --rx-gain 20
- PID 5455: dsp/spectrogram_service.py
- PID 5487: inference/realtime_classifier.py using models/production
- PID 5553: inference/posture_state_machine.py
- PID 5577: dashboard.app on port 8080
- PID 5608: scripts/live_test_logger.py

The acquisition code and configuration established continuous 5.800 GHz OTA TX at 5 dB. No current
framework v1.1 RF approval artifact was present, and the configured antennas are labelled for
2.4-2.5 GHz. A00 issued SIGTERM to the exact TX-owning PID. logs/tx_log.csv recorded:

    2026-08-07T03:55:18.514893+00:00,live_cw_doppler_20260804T012555Z,5800000000,5.0,20.0,continuous,"live G2/G3 acquisition flowgraph, stopped",STOPPED

The acquisition process exited after UHD destructor warnings. Preprocessing, inference, posture,
and logging processes then exited on SIGTERM.

The dashboard received SIGTERM but closed its listener while remaining blocked in WebSocket
background tasks waiting for absent upstream ZMQ data. After confirming port 8080 was closed, A00
force-terminated the already-shutting-down orphan. This is evidence for risk R-015 and the required
bounded WebSocket cancellation test.

CARAT RF and live detection were not restarted. No raw recording was deleted or modified.
