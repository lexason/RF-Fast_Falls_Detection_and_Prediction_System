# Migration Guide: Harmonized v1.0 / v2 → Harmonized v1.1

## 1. Back up current instruction files

From `~/carat_research`:

```bash
stamp=$(date +%Y%m%d_%H%M%S)
mkdir -p "docs/instruction_backups/$stamp"
cp -a AGENTS.md CLAUDE.md CODEX.md AGENT_ORCHESTRATION.md \
  CARAT_CODEX_CLAUDE_HYBRID_ENGINEERING_FRAMEWORK_v1_0.md \
  RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK_v1_2.md \
  RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK_v1_3.md \
  "docs/instruction_backups/$stamp/" 2>/dev/null || true
```

Do **not** back up or replace `STATE.md` by copying a template over it.

## 2. Copy canonical files

Copy these to repository root:

```text
AGENTS.md
CLAUDE.md
CODEX.md
CARAT_CODEX_CLAUDE_HYBRID_ENGINEERING_FRAMEWORK_v1_1.md
RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK_v1_4.md
RUNBOOK_AGENT_OPERATIONS.md
```

Copy the optional templates under `.agent/`, `config/`, `examples/`, and `tools/` without overwriting active local configuration unless reviewed.

## 3. Retire conflicting root authority files

After reviewing the migration, archive/remove active copies of:

```text
AGENT_ORCHESTRATION.md
CARAT_CODEX_CLAUDE_HYBRID_ENGINEERING_FRAMEWORK_v1_0.md
RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK_v1_2.md
RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK_v1_3.md
```

Do not keep multiple active orchestration constitutions at repository root.

## 4. Migrate operational facts out of old CLAUDE/CODEX files

Verify, then move still-current facts into the right factual source:

| Legacy fact | Destination |
|---|---|
| USRP address/device/daughterboard | config + archived probe output |
| GNU Radio/UHD/Python versions | environment lock/STATE/evidence |
| current carrier/sample rate/gain | approved experiment/system config |
| antenna geometry | system config/session manifest |
| milestone status | STATE.md |
| technical decision + rationale | ADR |
| reusable operational procedure | RUNBOOK_AGENT_OPERATIONS.md or subsystem runbook |
| measured acceptance result | experiment/report/artifact |

Do not blindly migrate an old claim as truth.

## 5. Resolve execution capabilities

Create a real local execution-context record from `config/agent_capabilities.example.yaml` if useful. Do not commit secrets. A local Codex session and a Codex Cloud task should have different contexts if their access differs.

## 6. Correct Codex user configuration only if needed

The package includes `examples/codex_config.example.toml`. Current documented keys are `approval_policy`, `sandbox_mode`, and `[agents].max_concurrent_threads_per_session`. Merge cautiously into your actual Codex configuration after checking the installed version and existing settings.

## 7. Keep Claude instructions thin

`CLAUDE.md` imports `@AGENTS.md`. Do not paste the long runbook or RF framework into `CLAUDE.md`. Use scoped rules/skills if a subsystem needs persistent special procedures.

## 8. Validate

```bash
python tools/validate_instruction_stack.py .
```

Then audit from Codex:

```bash
codex --ask-for-approval never "List the instruction sources active for this repository, summarize the authority hierarchy, and identify any conflicts. Do not edit files."
```

Inside interactive Codex, `/status` should show the expected workspace/session configuration.

For Claude Code, start from repository root and use `/context` to confirm `CLAUDE.md` is loaded and that it imports `AGENTS.md`.

## 9. First live task

Use:

```text
MODE=CONTINUE. INTENT=PLAN.
Read STATE.md, current Git/config/evidence, and the applicable gate criteria.
Resolve this session's execution environment/capabilities.
Identify the smallest next verifiable task, its risk tier/R2 materiality, deterministic validation, and required reviewer/human approval.
Do not edit yet.
```
