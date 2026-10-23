# AGENTS.md — CARAT Shared Coding-Agent Adapter

This file is intentionally short. It is a repository entry point, not the project specification.

## Authority

For substantive work:

1. obey applicable law, ethics/RF approvals, explicit human controls, and protected-data rules;
2. use `RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK_v1_4.md` for domain, safety, science, and G0-G8 gates;
3. use `CARAT_CODEX_CLAUDE_HYBRID_ENGINEERING_FRAMEWORK_v1_1.md` for risk, capability-aware routing, review, disagreement, and handoffs;
4. use `STATE.md`, current config, probe/experiment evidence, ADRs, and Git for current factual state;
5. use `RUNBOOK_AGENT_OPERATIONS.md` only for operational procedures.

If the active backend is Codex and Codex-specific CLI/config mechanics matter, consult `CODEX.md`; it has no independent project authority.

`MASTER_ORCHESTRATOR` is a protocol role, not a permanent model identity.

## Start substantive work

- Default to `MODE=CONTINUE` for existing work unless another mode is explicit.
- Inspect `STATE.md`, Git state, relevant config/evidence, and applicable gate criteria.
- Resolve the active execution environment and required capabilities. Never infer hardware/data access from the backend name.
- Assign R0-R4 and resolve `r2_material` for R2.
- Define acceptance evidence before material edits.
- Prefer a deterministic local tool when it can answer the question directly.
- Route to the most suitable backend. Do not preserve ownership for its own sake.

## Independent assurance

- R2-material and R3 changes require an independent reviewer other than the primary builder.
- R4 actions require the explicit human approval defined by the governing frameworks.
- The builder never supplies the sole final PASS for its own R2-material/R3/R4 work.
- Resolve disagreements with a discriminating test and archived evidence, not confidence or voting.

## Non-negotiable boundaries

- No autonomous RF-transmission authorisation.
- No unauthorised exposure of raw IQ, participant/clinical data, credentials, or secrets.
- No forbidden random-window leakage or silent split/label/threshold changes.
- No model promotion as a side effect of training.
- No implicit push, merge, release, publication, destructive protected-data operation, credential rotation, or other controlled R4 action.
- No repository reorganisation merely to match a reference tree.
- No stale chat/model memory over current Git/config/evidence.

## Completion

Material work ends with reproducible evidence, provenance, required review/approval, and a concise `STATE.md` update when project state changed. Detailed run records belong under `artifacts/agent_runs/`.
