# CODEX.md — CARAT Codex Adapter Notes

Codex is a complementary execution backend, not a bounded subordinate to Claude Code and not a permanent implementation-only agent.

`AGENTS.md` is the shared repository entry point. This file contains only Codex-specific mechanics and routing defaults.

## Codex-specific defaults

Prefer Codex when the task is dominated by repository implementation, refactoring, command-driven diagnosis, reproduction, test generation/repair, CI/build/dependency work, API/control-plane implementation, automation, or measurable local engineering.

A local Codex CLI session may use local tools and hardware paths that are genuinely available to that session. A Codex Cloud session may not have those same capabilities. **Never infer the environment from the name Codex.** Resolve capabilities using the hybrid framework before hardware, protected-data, network, or deployment work.

## Review behaviour

Codex may be an independent reviewer when another backend built the change. Review the diff/evidence independently; do not inherit the builder's root-cause narrative as fact. Do not self-issue the sole final PASS for your own R2-material/R3/R4 work.

## Current Codex mechanics

Interactive local CLI:

```bash
cd ~/carat_research
codex
```

Useful TUI commands include `/status`, `/permissions`, and `/review`.

Repeatable execution:

```bash
codex exec "Read AGENTS.md and STATE.md. MODE=CONTINUE. INTENT=PLAN. <task>"
```

Current documented configuration names include:

```toml
approval_policy = "on-request"
sandbox_mode = "workspace-write"

[agents]
enabled = true
max_concurrent_threads_per_session = 3
```

Do not use legacy/incorrect project guidance such as `approval_mode`, `sandbox =`, `parallel_task_cap`, or `codex --print-instructions` as current Codex controls.

To verify instruction discovery, ask Codex to list/summarise its active instruction sources or follow the current official AGENTS.md verification guidance.
