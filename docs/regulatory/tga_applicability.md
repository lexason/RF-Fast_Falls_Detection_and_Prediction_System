# Preliminary Australian TGA applicability memo

Status: Preliminary internal assessment; not legal advice and not an approved regulatory
determination. Regulatory owner and qualified reviewer: Unassigned.
Reviewed against official TGA guidance on 2026-08-07.

## Frozen working intended purpose

The proposed investigational system estimates activity, probable fall events, and longitudinal
fall-risk indicators for clinician review. It does not diagnose, prescribe, replace clinical
assessment, or autonomously determine care. Products A-D remain separate, and Product D is not an
available capability.

## Preliminary analysis

TGA guidance states that software/AI status is determined by the manufacturer's intended purpose
and supplied claims. Software intended for monitoring or prediction of disease, injury, or
disability may meet the medical-device definition. Products A and C contemplate monitoring or
prediction related to fall injury and clinical decisions. Describing the system as research or
decision support does not by itself exclude it.

The project is therefore potentially within Australian medical-device regulation if supplied or
deployed with those intended purposes. Exact inclusion/exclusion, classification, sponsor or
manufacturer obligations, conformity assessment, and ARTG pathway remain unresolved. Product B may
have a different analysis when limited to non-medical activity research. Product D would require a
separate high-risk determination and evidence package.

## Required qualified review

- exact claims in UI, model cards, protocols, papers, websites, demonstrations, and instructions;
- population, setting, users, decisions, timing, alert consequences, and fallback;
- distinction between laboratory research, clinical investigation, and supply;
- medical-device definition, relevant exclusions, classification rules, and essential principles;
- ISO 14971, IEC 62304, IEC 62366-1, ISO 13485, clinical evidence, cybersecurity, and change control;
- whether hardware/software combination and adaptive or updated models change obligations;
- clinical investigation and HREC/site-governance implications.

## Controls pending determination

Keep all environments DEVELOPMENT, show no clinical readiness, make no imminent-warning or treatment
claim, preserve immutable model versions, prevent silent updates, and trigger a fresh review when
intended use, claims, population, workflow, outputs, performance, or deployment changes.

Official source:
https://www.tga.gov.au/resources/guidance/understanding-how-we-regulate-software-based-medical-devices
