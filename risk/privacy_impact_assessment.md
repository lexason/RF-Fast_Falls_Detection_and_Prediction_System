# Privacy impact assessment

Status: Draft scoping assessment; not approved. Privacy owner: Unassigned.

## Data inventory

- Raw RF/IQ: potentially rich environmental signal; it must become immutable
  under an approved retention and integrity design and must never be served to a browser.
- Derived movement/activity: occupancy, routines, transitions, night movement, possible intimate
  behaviour; may be personal or sensitive information even without names.
- Protocol and annotation: coded participant, site, room, assistance, mobility aid, event and notes.
- Future clinical data: fall history, medication, function, symptoms, environment, preferences.
- Operational data: users, sessions, access, configuration, alerts, acknowledgements, audit events.
- Identity linkage: not implemented; must be a segregated service controlled by the data custodian.

## Purpose and minimisation

Collection is limited to approved fall/activity/mobility research. Direct RF identity recognition,
unrelated behaviour, diagnosis, treatment selection, employee surveillance, and secondary use are
prohibited without a separate purpose, assessment, and approval. Raw IQ retention and sampling must
be justified per protocol; derived exports use the minimum necessary fields.

## People and zones

Risks affect participants, cohabitants, visitors, staff, carers, and people outside the intended
zone. Future governance must cover notices, consent/legal authority, bystanders, excluded zones,
bedroom/bathroom/nocturnal sensitivity, visible monitoring state, pause/opt-out, and withdrawal.

## Current positive controls

- data/raw is excluded from Git;
- the legacy dashboard does not intentionally serve raw IQ;
- new recording schema uses coded IDs and provenance;
- this Phase 0 work adds no participant data.

Git exclusion and the current dashboard route inspection are not immutability,
access-control, retention, or deletion evidence.

## Open controls

- APP/lawful-basis mapping, collection notice, access/correction, automated-decision transparency;
- encryption at rest/in transit, dedicated identities, RBAC, session control, audit, export approval;
- retention schedules, backup lifecycle, verified deletion/withdrawal, legal holds;
- segregated identity linkage, device/room association, purpose-limited clinical integration;
- privacy-zone enforcement, pause/status, bystander handling, prohibited-inference tests;
- diagnostic-bundle redaction and secret/direct-identity scanning.

## Preliminary risk decision

Residual risk is not accepted. The current unauthenticated dashboard and absence of governed
retention, identity, consent, and access controls prevent participant or clinical deployment.
