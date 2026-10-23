# N210 and UBX-40 Phase 1 bring-up protocol

Status: Draft. No transmission or conducted test is authorised by this document.

## Confirmed baseline

A CARAT-stopped diagnostic probe on 7 August 2026 identified an N210r4 with an
UBX-40 v2. Exclusive device access was not established, so the probe supports
identity only and no streaming or gate claim.
The dedicated interface enp128s31f6 negotiated 1 Gb/s full duplex and reached
192.168.10.50 with zero loss over 20 pings. The active tools reported UHD
4.9.0.HEAD and GNU Radio 3.10.9.2. Full duplex uses TX/RX for transmit and RX2
for receive. These facts establish identity and reachability only.

Historical evidence is retained in config/probe.txt and STATE.md but does not by
itself pass framework v1.1 G1. The current 5.8 GHz legacy profile uses antennas
labelled only for 2.4-2.5 GHz and must not be resumed.

## Diagnostic nonconformance recorded on 2026-08-07

The archived full probe was run before exclusive ownership had been established.
That violated the conservative precondition below once another owner was found.
The output is retained as identity-only evidence so the sequence remains
auditable; it is not a precedent or an authorised discovery exception. Future
`uhd_find_devices`, full probes, streaming, and RF commands all require the
exclusive host lock and explicit task authority. Passive host-side inspection
that does not contact the N210 may be used to determine whether ownership is
unknown; if it is unknown, work stops.

## Immediate stop conditions

Stop before any device command or physical test if any of these is true:

- the N210 has another owner or ownership is unknown;
- a current RF approval, location, waveform, bandwidth, power, EIRP, duty cycle,
  approved antenna, or expiry is missing;
- the antenna is not verified for the selected OTA frequency;
- attenuation, power rating, frequency rating, worst-case RX input, or safety
  margin is unknown for a conducted test;
- direct TX-to-RX cabling is proposed without adequate verified attenuation;
- clipping, overflow, underflow, late commands, sequence discontinuity, or
  configuration drift is observed.

## Sequence

1. Establish exclusive ownership. Put CARAT in STOPPED or MAINTENANCE, acquire
   the hardware lock, and independently confirm no other process owns the N210.
2. Inventory the motherboard, daughterboard, power supply, antennas, cables,
   attenuators, filters, connectors, port assignment, and geometry. Photograph
   labels and record calibration or inspection dates.
3. Complete ACMA LIPD, technical-standard, coexistence, and ARPANSA EME review
   for the exact proposed waveform and location. Sign a bounded RF profile.
4. Reconcile the active /usr/local UHD 4.9 build with installed distribution UHD
   4.6 packages. Reconcile observed MTU 1500 with the legacy claim of MTU 9000.
5. While exclusively stopped, capture versions and device identity:

       date --iso-8601=seconds
       uname -a
       python --version
       uhd_config_info --version
       gnuradio-config-info --version
       ip -br link
       ip -br addr
       ip route get 192.168.10.50
       ethtool enp128s31f6
       ping -c 20 192.168.10.50
       uhd_find_devices --args="addr=192.168.10.50"
       uhd_usrp_probe --args="addr=192.168.10.50"

6. With TX disabled, run approved receive-only rates and durations. Archive
   complete stdout and stderr, exit status, host and interface counters, drops,
   overruns, sample discontinuities, and configuration.
7. Design a conducted TX/RX-to-RX2 loopback only after an independent reviewer
   verifies the measured attenuator chain and worst-case RX input. Start at the
   minimum gain. The UBX internal CAL path is supplemental evidence, not a
   substitute for the required external attenuated path.
8. Conduct bounded TX-only and full-duplex benchmarks through the approved
   conducted path. Capture clipping margin, frequency error, SNR or EVM,
   channel-estimation error, overflows, underflows, late commands, and repeatability.
9. Move to low-power OTA only with a signed, unexpired approval and verified
   antennas. Begin at the lowest approved gain and duration; characterise
   occupancy, leakage, static stability, saturation margin, and coexistence.
10. Checksum all configurations, logs, IQ snapshots, and reports. Require A03,
    A04, A12, and independent A15 review before a G1 decision.

## Required archive layout

Each run must create an immutable manifest containing command, start/end UTC,
operator, host, commit, config hash, device identity, approvals, result, error
counters, artifact paths, and SHA-256 values. Raw IQ remains outside Git.

## Current decision

Do not run receive streaming, benchmark, loopback, or OTA steps now. Exclusive
device access is unavailable and required safety/compliance evidence is incomplete.
