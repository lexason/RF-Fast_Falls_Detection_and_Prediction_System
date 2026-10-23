# Evidence ledger

Last reviewed: 2026-08-07. Status values describe evidence, not approval.
Framework references were checked against current official sources where noted.
The exact official URLs and access dates are archived in
`docs/evidence/external_sources_2026-08-07.md`; no web snapshot is claimed.

| ID | Claim | Type | Status | Confidence | Source and date | Applicability and limitation | Requirement links |
|---|---|---|---|---|---|---|---|
| EV-001 | Framework v1.1 governs this repository. | requirement | verified | n/a | RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK_v1_1.md; SHA-256 82d724ee94cb79e7357caad9da6ef46d30d955746d08381138ff85fa6aa809b7 | Governance instruction, not performance evidence. | GOV-001, SYS-001 |
| EV-002 | The host can identify an N210r4 and UBX-40 v2 at 192.168.10.50. | local fact | verified | local-high | Probe observed 2026-08-07; config/probe.txt historical copy | Establishes identity only; no current streaming, clipping, or repeatability result. | HW-001 |
| EV-003 | The N210 interface negotiated 1 Gb/s full duplex and was reachable with 0/20 lost pings. | local fact | verified | local-high | ethtool and ping, 2026-08-07 | Does not establish sustained sample streaming. Observed MTU 1500 conflicts with legacy configuration 9000. | HW-002 |
| EV-004 | Existing historical G0/G1/G2 checkmarks use different gate definitions. | local fact | verified | local-high | CLAUDE.md and STATE.md, inspected 2026-08-07 | Historical artifacts remain useful but do not pass framework v1.1 gates. | GOV-002 |
| EV-005 | The active legacy model is clinically ready for fall alerts. | local claim | contradicted | local-high | models/production/metadata.json and dashboard/app.py | Metadata reports fall recall 0.170 and uncalibrated outputs; no deployment-prevalence PPV or external validation. | CLIN-001, ML-001 |
| EV-006 | Current antennas are suitable at the legacy 5.8 GHz carrier. | local claim | contradicted | local-high | config/system.yaml | Antennas are labelled 2.4-2.5 GHz; close-range SNR does not establish antenna suitability or compliance at 5.8 GHz. | RF-002 |
| EV-007 | A broad ISM-band check is sufficient RF authorisation. | local claim | contradicted | A | ACMA LIPD class-licence page, checked 2026-08-07 | Exact device class, frequency, power/EIRP, technical standards, EME, location, and interference conditions still require review. | RF-001 |
| EV-008 | The NHMRC National Statement 2025 is current. | external fact | verified | A | NHMRC official page and HREA update, checked 2026-08-07 | Effective 23 June 2026; institutional advice and approvals remain project-specific. | ETH-001 |
| EV-009 | Intended purpose determines Australian software/AI medical-device status. | external fact | verified | A | TGA official guidance published 24 February 2026 and AI page updated 5 February 2026; checked 2026-08-07 | A project disclaimer does not resolve status. Formal claim-specific review is pending. | REG-001 |
| EV-010 | Additional APP transparency duties for significant automated decisions commence 10 December 2026. | external fact | verified | A | OAIC APP 1 guidance, checked 2026-08-07 | Applicability depends on entity, personal information, arrangement, and decision effect. | PRIV-001 |
| EV-011 | ARPANSA RPS S-1 covers RF exposure from 100 kHz to 300 GHz. | external fact | verified | A | ARPANSA official RPS S-1 page, checked 2026-08-07 | A project-specific EME assessment has not been completed. | RF-003 |
| EV-012 | UBX supports 10 MHz-6 GHz, 40 MHz bandwidth, and full-duplex RX on RX2. | external fact | verified | official technical | Ettus UHD daughterboard manual, checked 2026-08-07; current probe | Capability does not establish lawful transmission, antenna suitability, or N210 host-streaming bandwidth. | HW-001, RF-004 |
| EV-013 | Chen et al. 2024 establishes clinical fall-detection generalisation. | external claim | contradicted | E | Framework synthesis of Chen et al. 2024 | Young volunteers, one room, balanced data, and within-volunteer random split are proof of concept only. | EVID-001, ML-002 |
| EV-014 | Existing RF-FAST/CARAT proposal documents prove future capabilities. | local claim | contradicted | n/a | docs proposal corpus | Treat as hypotheses and provenance, not implementation or validation evidence. | EVID-002, NAME-001 |
| EV-015 | A clinician-facing fall-risk forecast can be represented without a horizon. | requirement claim | contradicted | A | Framework v1.1 and TGA intended-purpose principles | Any Product C output requires a defined horizon, calibration, uncertainty, data sufficiency, and external validation. | CLIN-002 |

## Evidence gaps

- No approved intended use, clinical workflow, partner appointment, or escalation protocol.
- No HREC or institutional research-governance determination linked in the repository.
- No claim-specific TGA determination, approved privacy impact assessment, or approved RF/EME profile.
- No current v1.1 streaming, external attenuated-loopback, clipping, repeatability, or OTA evidence.
- No independent-site, prospective, realistic-prevalence, or clinical-utility evidence.

## Source handling rules

Proposal text, historical ledgers, screenshots, dashboards, and model filenames are not proof of
capability. Every new performance claim must record population, setting, labels, hardware,
frequency, bandwidth, split strategy, prevalence, metrics, uncertainty, external validation, and
limitations. Conflicting evidence remains visible rather than being averaged away.
