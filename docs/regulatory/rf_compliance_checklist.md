# RF compliance and EME checklist

Status: OPEN. CARAT OTA transmission authorised: NO. RF compliance owner: Unassigned.
Official sources checked on 2026-08-07.

| Item | Required evidence | Current status |
|---|---|---|
| Exact regulatory arrangement | Current ACMA LIPD item/conditions or other licence basis | Missing |
| Device/equipment standards | Applicable General Equipment Rules and technical standards | Missing |
| Location | Approved site, indoor/outdoor, controlled area, restrictions | Missing |
| Frequency | Approved centre/range for exact transmitter class | Proposed 2.437 GHz only |
| Waveform and occupied bandwidth | Measured definition, emission mask, spurious evidence | Missing |
| Conducted power | Calibrated measurement with uncertainty | Missing |
| Antenna and feeder | Inventory ID, rating, gain at frequency, cable loss | Incomplete |
| EIRP | Worst-case calculation/measurement with uncertainty | Missing |
| Duty cycle | Approved bound; no indefinite profile by default | Missing |
| Coexistence/interference | Occupancy, affected services, mitigation, incident path | Missing |
| EME | ARPANSA RPS S-1 assessment and separation/exposure scenario | Missing |
| Approval record | Named approver, signed profile/hash, date and expiry | Missing |
| Emergency stop | Tested bounded stop and TX audit completion | Not implemented under G1A |

The ACMA LIPD class licence permits specified short-range uses on shared frequencies subject to its
exact rules, power limits, places, interference obligations, and technical/EME standards. Merely
falling inside an ISM frequency range is not approval. ARPANSA RPS S-1 sets RF exposure requirements
from 100 kHz to 300 GHz; project-specific compliance remains to be assessed.

No OTA, TX benchmark, or conducted loopback may proceed until the applicable row is complete and
independently reviewed. Conducted testing additionally requires a measured attenuator chain,
worst-case RX input and safety margin, frequency/power ratings, and a prohibition on direct
unattenuated TX/RX-to-RX2 connection.

Official sources:

- https://www.acma.gov.au/licences/low-interference-potential-devices-lipd-class-licence
- https://www.acma.gov.au/technical-standards
- https://www.arpansa.gov.au/regulation-and-licensing/regulatory-publications/radiation-protection-series/codes-and-standards/rpss-1
