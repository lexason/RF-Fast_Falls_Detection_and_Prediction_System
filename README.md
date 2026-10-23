# CARAT Harmonized Agent Framework v1.1

This package is the recommended successor to the earlier Harmonized v1.0 and the later v2 instruction stack.

## Canonical architecture

```text
                 POLICY / GOVERNANCE PLANE
 law + ethics + RF approvals + explicit human controls
                         |
 RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK_v1_4.md
                         |
 CARAT_CODEX_CLAUDE_HYBRID_ENGINEERING_FRAMEWORK_v1_1.md
                         |
                 thin root adapters
                 /       |       \
           AGENTS.md  CLAUDE.md  CODEX.md

                  FACTUAL / STATE PLANE
 measurements + approved config + manifests + hashes
                         |
                  ADRs + STATE.md
                         |
                 runbooks / docs
```

Neither plane replaces the other: factual evidence can correct stale assumptions, but it cannot waive a policy/approval boundary.

## What v1.1 fixes

- removes the false `Codex = cloud` / `Claude = local` assumption;
- routes on actual execution capabilities;
- restores `LOCAL_NON_LLM_TOOL` as a first-class executor/validator;
- explicitly separates normative authority from factual truth;
- applies independent review to R2-material as well as R3/R4;
- preserves the no-self-PASS rule;
- keeps `AGENTS.md`, `CLAUDE.md`, and `CODEX.md` thin;
- moves operational detail into `RUNBOOK_AGENT_OPERATIONS.md`;
- corrects current Codex configuration/verification mechanics;
- restores dashboard routing/environment/reviewer/validator/handoff controls;
- adds a machine-checkable instruction-stack linter.

## Files

- `RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK_v1_4.md` — domain/safety/science/G0-G8 constitution.
- `CARAT_CODEX_CLAUDE_HYBRID_ENGINEERING_FRAMEWORK_v1_1.md` — orchestration, risk, capabilities, review, evidence adjudication.
- `AGENTS.md` — shared short coding-agent entry point.
- `CLAUDE.md` — thin Claude Code adapter importing `@AGENTS.md`.
- `CODEX.md` — thin Codex-specific mechanics; not a second authority layer.
- `RUNBOOK_AGENT_OPERATIONS.md` — operational loop, milestones, verification patterns, failure-mode checklist.
- `config/agent_capabilities.example.yaml` — execution-context template.
- `.agent/routing.example.yaml` and `.agent/routing_ledger.example.csv` — adaptive routing templates.
- `STATE_AGENT_SECTIONS_TEMPLATE.md` — optional additions to existing `STATE.md`.
- `examples/codex_config.example.toml` — current Codex config-key example.
- `tools/validate_instruction_stack.py` — static consistency checker.
- `MIGRATION_GUIDE_v1_1.md` — installation/migration sequence.

## Recommended install approach

Do not overwrite live state/config blindly. Back up the old instruction files, copy the new root framework/adapters/runbook, review the diff, migrate still-current operational facts into config/evidence/STATE, then run:

```bash
python tools/validate_instruction_stack.py .
```

Detailed commands are in `MIGRATION_GUIDE_v1_1.md`.
