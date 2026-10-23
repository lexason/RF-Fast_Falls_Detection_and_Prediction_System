# Changelog — CARAT Harmonized Agent Framework v1.1

**Date:** 2026-08-19

## Architecture

- Split normative/policy authority from factual/state authority.
- Added explicit execution-environment and capability model.
- Kept `MASTER_ORCHESTRATOR` vendor-neutral.
- Restored `LOCAL_NON_LLM_TOOL` as executor/validator.
- Prevented backend identity from implying hardware/data access.

## Risk and assurance

- Added explicit `r2_material` classification.
- Independent reviewer required for R2-material and R3; R4 retains human approval boundary.
- Preserved no-self-PASS rule.
- Made deterministic validation a separate first-class concept from independent review.
- Strengthened evidence-based disagreement protocol.

## Instruction hygiene

- Root adapters remain concise.
- `CLAUDE.md` imports `@AGENTS.md` instead of duplicating shared rules.
- Added `CODEX.md` as a thin mechanics note only, not a second authority layer.
- Moved operational loop, milestones, hardware verification patterns, and failure modes to a vendor-neutral runbook.

## Current product mechanics

- Removed `Codex = cloud` assumption.
- Removed hard ban on Codex hardware interaction; access is capability-based and policy-constrained.
- Corrected Codex keys to `approval_policy`, `sandbox_mode`, and `agents.max_concurrent_threads_per_session`.
- Removed `codex --print-instructions`; documented current instruction/status verification patterns.
- Kept `codex exec`, `claude -p`, Claude `@AGENTS.md`, and `/context` based on current official docs.

## Dashboard/orchestration

- Restored routing mode, environment, primary, reviewer, validator, evidence, approval, and handoff-card concepts.
- Natural-language actions resolve to named/versioned workflows, never unrestricted shell text.

## Validation

- Added `tools/validate_instruction_stack.py` for static checks against duplicated gates, stale filenames, known obsolete Codex mechanics, vendor/cloud assumptions, adapter bloat, and missing references.
