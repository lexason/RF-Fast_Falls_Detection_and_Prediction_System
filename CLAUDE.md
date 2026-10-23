# CLAUDE.md — CARAT Claude Code Adapter

@AGENTS.md

Claude Code is a complementary execution backend, not the permanent master orchestrator.

## Claude-specific defaults

Prefer Claude Code when the task is dominated by architecture, requirements decomposition, cross-domain reasoning, methodology critique, evidence synthesis, competing hypotheses, failure-mode analysis, human factors, clinical/safety reasoning, or independent conceptual review.

If the task becomes primarily implementation, executable debugging, test repair, CI/build work, or repeatable automation, follow the hybrid router rather than preserving Claude ownership.

## Context discipline

Keep this file thin. Mutable hardware facts, milestones, thresholds, model versions, and long procedures belong in current config/evidence, `STATE.md`, `RUNBOOK_AGENT_OPERATIONS.md`, ADRs, or scoped skills/rules.

For local coding, load only the relevant RF/hybrid sections. For architecture, safety, validation, or publication work, broaden context as needed.

## Review behaviour

When independently reviewing another backend: reconstruct the problem, inspect the actual diff and evidence, challenge assumptions/root cause, check gate criteria and failure modes, and return `PASS`, `CONDITIONAL`, `FAIL`, or `BLOCKED` with reproducible evidence. Do not merely endorse the builder.

## Claude Code mechanics

Use `/context` when debugging which project instruction/memory files loaded. `claude -p "..."` is available for repeatable non-interactive work. Use permissions/sandbox controls appropriate to the current task and environment; technical access never waives CARAT approval boundaries.
