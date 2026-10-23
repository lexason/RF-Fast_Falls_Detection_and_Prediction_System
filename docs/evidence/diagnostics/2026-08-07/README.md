# Phase 0 diagnostic evidence: 2026-08-07

Mode: BUILD at framework v1.1 G0. All times are UTC unless marked otherwise.

## Scope

Repository, host, CARAT process state, network link, and N210 identity were inspected. No CARAT
streaming benchmark, conducted loopback, firmware change, network reconfiguration, or intentional
test transmission was performed. CARAT live TX was found running and was stopped. No later N210
command is authorised by this evidence bundle.

Exclusive N210 access was not established. Current hardware evidence therefore supports identity
and link reachability only, not framework G1 passage.

## Files

- repository_baseline.md: initial commit, branch, dirty-state preservation, and test baseline.
- host_environment.txt: OS, Python, UHD, and GNU Radio versions.
- network_and_usrp.txt: route, link, ping, discovery, and probe summary.
- uhd_usrp_probe_2026-08-07.txt: current probe transcript.
- carat_rf_stop.md: CARAT-only stop and shutdown evidence.

The complete historical probe remains at config/probe.txt. The initial framework SHA-256 is
82d724ee94cb79e7357caad9da6ef46d30d955746d08381138ff85fa6aa809b7.

## Commands deliberately not run

- Any uhd_benchmark_rate invocation, because exclusive device ownership was unavailable.
- tests/test_g0_hardware.py, because it includes a transmitting CAL-loopback test.
- Any loopback or OTA test, because attenuation, antenna suitability, and approvals are incomplete.
- Any firmware, FPGA, gain, RF profile, MTU, buffer, or interface change.
