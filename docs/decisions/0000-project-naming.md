# ADR 0000: Project naming and legacy aliases

- Status: Proposed; governance approval pending
- Date: 2026-08-07
- Decision owners: Unassigned
- Source: RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK_v1_1.md, section 0.1

## Context

Existing repository files use CARAT and RF-FAST. No evidence was found that either acronym was
approved as the software product, clinical study, dataset, or repository name. The governing
framework forbids silently importing or approving a name from older context.

## Decision

Use RF Sensing Falls Project as a working display name, rf-sensing-falls as the slug, and
rf_sensing_falls as the future Python package. No acronym is approved. The dashboard must read
the name and environment from configs/project.yaml rather than hard-coding a legacy name.

CARAT and RF-FAST are legacy aliases only. Existing paths and historical records retain those
strings for provenance; new user-facing material must not imply that either alias is approved.

## Consequences

- A governance owner must approve or replace the working name.
- Any later acronym approval records approver, timestamp, scope, and migration plan here.
- Renaming existing files is deferred because it could break reproducibility and provenance.

## Verification

The Phase 0 test checks that the naming status remains working-title while approved_by and
approved_at are null.
