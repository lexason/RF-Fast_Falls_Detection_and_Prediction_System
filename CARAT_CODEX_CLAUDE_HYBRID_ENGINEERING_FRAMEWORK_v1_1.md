# CARAT Codex + Claude Code Harmonized Engineering Framework

**Version:** 1.1  
**Date:** 2026-08-19  
**Status:** Canonical repository-level routing, review, execution-capability, and handoff instruction  
**Workspace root:** `~/carat_research/`  
**Domain framework:** `RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK_v1_4.md`  
**Live project ledger:** `STATE.md`

---

# 0. Purpose

This framework defines how CARAT work is routed among Codex, Claude Code, humans, and deterministic local tools without making any vendor the project authority.

It exists to ensure that:

1. work can begin from Codex, Claude Code, or the terminal;
2. the project protocol, not a model identity, determines authority;
3. routing reflects task difficulty, risk, evidence needs, and the capabilities of the actual execution environment;
4. R2-material, R3, and R4 changes cannot self-certify;
5. disagreements are settled by falsifiable tests and evidence rather than confidence or voting;
6. mutable operational truth lives in evidence, config, state, and runbooks rather than vendor-specific instruction files;
7. deterministic local tools are preferred whenever they can answer a question more directly than an LLM;
8. human approval remains mandatory at RF, clinical, protected-data, destructive, publication, model-promotion, and other R4 boundaries.

> **Protocol governs. Evidence adjudicates. Capabilities constrain execution. Humans control critical actions.**

---

# 1. Two authority planes

A single undifferentiated precedence list is unsafe because `STATE.md` is both useful and mutable. CARAT therefore uses two authority planes.

## 1.1 Normative / policy authority

Highest to lowest:

1. applicable law, ethics approval, RF authorisation, institutional policy, and explicit human approval;
2. `RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK_v1_4.md`;
3. this hybrid framework;
4. root adapters `AGENTS.md`, `CLAUDE.md`, and `CODEX.md`;
5. task-local plans, prompts, chat history, and model memory.

A lower source may narrow permissions but may not weaken a higher safety, governance, or evidence requirement.

## 1.2 Factual / state authority

Highest to lowest for claims about what is actually true now:

1. direct measurement and immutable raw evidence for the relevant run/device;
2. approved deployed configuration, probe output, experiment manifests, hashes, and signed/approved artifacts;
3. ADRs and `STATE.md` summaries that point to those artifacts;
4. runbooks and documentation;
5. framework examples and defaults;
6. conversational memory and unstored assumptions.

Consequences:

- `STATE.md` can correct stale documentation but cannot waive an approval requirement.
- A framework hardware example can be superseded by a current `uhd_usrp_probe`, but that probe cannot authorise RF transmission.
- A model's remembered IP address, sample rate, threshold, or model version is never operational truth until resolved from current state/evidence.

---

# 2. Canonical project sources

| Source | Purpose |
|---|---|
| `RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK_v1_4.md` | Domain, safety, science, clinical boundaries, 18 logical agents, G0-G8 gates |
| `CARAT_CODEX_CLAUDE_HYBRID_ENGINEERING_FRAMEWORK_v1_1.md` | Routing, risk, capability, review, disagreement, handoff, concurrency |
| `RUNBOOK_AGENT_OPERATIONS.md` | Vendor-neutral operating loop, verification recipes, milestone execution guidance |
| `STATE.md` | Concise current gate/milestone, active work, risks, evidence pointers, routing/review status |
| `config/` and `configs/` | Operational and experiment configuration |
| `docs/decisions/` | Approved consequential decisions |
| `docs/evidence/`, `reports/`, `artifacts/` | Evidence, validation, model/data records, agent-run artifacts |
| Git | Code provenance, diffs, commits, rollback points |

Root adapters must not duplicate these sources.

---

# 3. Logical roles, backends, environments, and capabilities

A **logical agent** is a project responsibility such as RF architect, DSP engineer, ML engineer, security reviewer, dashboard engineer, or independent critic.

An **execution backend** is the mechanism performing that responsibility:

```text
CODEX
CLAUDE_CODE
HUMAN
LOCAL_NON_LLM_TOOL
```

An **execution environment** describes where the backend is actually running:

```text
LOCAL
CLOUD
REMOTE
CI
```

Capabilities are resolved facts, not inferred from the vendor name.

## 3.1 Minimum execution-context record

```yaml
execution_context_id: EC-YYYYMMDD-NNN
backend: CODEX | CLAUDE_CODE | HUMAN | LOCAL_NON_LLM_TOOL
environment: LOCAL | CLOUD | REMOTE | CI
host: optional-hostname
capabilities:
  repository_read: true | false
  repository_write: true | false
  local_shell: true | false
  network_access: true | false
  usrp_access: true | false
  rf_tx_capable: true | false
  protected_data_access: true | false
  secrets_access: true | false
  external_publish: true | false
constraints: []
verified_by: command | config | human | platform
verified_at: ISO-8601
```

Use `config/agent_capabilities.example.yaml` as a template. Do not commit secrets into this record.

## 3.2 Hard rule

> **Never route hardware, data, deployment, or network work solely because the backend is named Codex or Claude Code. Route only when the active execution context has the required capability and policy permits the action.**

Examples:

- Local Codex with shell and N210 network access may perform approved RX-only diagnostics.
- Codex Cloud without N210 access may implement and test replay/DSP code but cannot run the hardware check.
- Claude Code running remotely may also lack the N210 path.
- A deterministic `pytest`, `uhd_usrp_probe`, benchmark, static analyser, or measurement script may be the best primary executor or validator for a narrow claim.

Technical access never substitutes for required human approval.

---

# 4. Master gates versus implementation milestones

The only project gates are G0-G8 from the RF framework:

```text
G0   Intended use and governance
G1   Hardware integrity
G1A  Operations control-plane integrity
G2   Signal observability
G3   Dataset validity
G4   Research baseline
G5   Cross-domain robustness
G6   External and prospective validation
G7   Silent clinical deployment
G8   Controlled decision-support evaluation
```

M0-M6 are implementation milestones described in the vendor-neutral runbook. They produce evidence for gates but cannot pass a gate themselves.

---

# 5. Modes and intents

Modes:

```text
BUILD      create or extend
AUDIT      inspect without assuming correctness
REPAIR     reproduce, fix, regress
VALIDATE   test a claim or gate against evidence
CONTINUE   resume from recorded state
```

Intents:

```text
EXPLAIN | PLAN | EXECUTE | REVIEW
```

`CONTINUE` is the normal start for an existing project. Determine the last valid state from Git/config/evidence, not from the previous chat summary.

---

# 6. Task intake contract

Use this full envelope for substantive work. R0/R1 work may use a compact version.

```yaml
task_id: CARAT-YYYYMMDD-NNN
mode: BUILD | AUDIT | REPAIR | VALIDATE | CONTINUE
intent: EXPLAIN | PLAN | EXECUTE | REVIEW
master_gate: G0 | G1 | G1A | G2 | G3 | G4 | G5 | G6 | G7 | G8
milestone: M0 | M1 | M2 | M3 | M4 | M5 | M6 | NA
objective: concise objective
risk_tier: R0 | R1 | R2 | R3 | R4
r2_material: true | false | null

repo_state:
  branch: string
  head_commit: string
  dirty: true | false

assumptions: []
unknowns: []
logical_agents: []

primary_backend: AUTO | CODEX | CLAUDE_CODE | HUMAN | LOCAL_NON_LLM_TOOL
primary_execution_context: string | null
review_backend: NONE | CODEX | CLAUDE_CODE | HUMAN
validator_backend: NONE | LOCAL_NON_LLM_TOOL | HUMAN

files_to_inspect: []
files_allowed_to_change: []
protected_paths: []
commands_to_run: []
expected_outputs: []
acceptance_evidence: []
safety_constraints: []
human_approvals_required: []
```

---

# 7. Risk tiers

## R0: read-only explanation

Examples: explain code, summarise a log, map a module.

- one backend is sufficient;
- no project write required;
- independent review optional.

## R1: low-risk local engineering

Examples: isolated documentation fix, helper, unit test, small refactor with no scientific or safety consequence.

- one primary backend;
- behavioural changes require tests;
- review optional unless an interface or protected boundary changes.

## R2: cross-module or scientifically meaningful engineering

Examples: DSP implementation, feature logic, API contract, model feature extraction, dashboard command workflow, data-processing semantics.

Classify `r2_material=true` when failure could materially alter any of:

- scientific interpretation or reported result;
- data lineage, splits, labels, feature semantics, thresholds, or calibration;
- RF/DSP signal interpretation;
- a safety/security boundary;
- an inter-service or dashboard control-plane contract;
- reproducibility or model/data provenance;
- a downstream gate decision.

For R2-material:

- independent review by a backend other than the primary builder is required when an LLM/human judgement is part of the claim;
- deterministic validation is required whenever a direct test exists;
- the primary builder cannot issue the sole final PASS.

Non-material R2 may use single-backend review when evidence is strong and the rationale is recorded.

## R3: high-impact technical or research operation

Examples:

- changes to data split logic or clinical labels;
- model threshold/calibration changes used in evaluation;
- RF configuration with meaningful hardware or compliance impact;
- protected-data pipeline changes;
- security/privacy architecture;
- gate-validation code;
- consequential control-plane changes;
- publication-critical analyses.

Requirements:

- independent alternate reviewer mandatory;
- deterministic validation where feasible;
- explicit evidence packet;
- no self-PASS;
- human consultation when domain authority is required.

## R4: human-controlled critical action

Examples:

- authorising or executing RF transmission where approval is required;
- human-subject collection or protocol change;
- clinical/public claims beyond approved evidence;
- destructive protected-data operations;
- credential rotation or privileged secret handling;
- model promotion to an approved/controlled environment;
- release, publication, merge, or external deployment when governed as controlled;
- ethics, regulatory, or clinical sign-off.

Requirements:

- human approval must be explicit and recorded;
- agents may prepare evidence, plans, diffs, dry-runs, and rollback procedures;
- silence is never approval;
- independent technical review does not replace the human decision.

---

# 8. Routing policy

Routing is a constrained optimisation problem:

```text
task + gate + risk + evidence need + execution capabilities + data boundary
                              ↓
                         backend route
```

## 8.1 Prefer deterministic/local tools when

- the question can be answered directly by a test, benchmark, probe, schema check, compiler, linter, static analyser, RF measurement, or statistical script;
- reproducibility matters more than prose judgement;
- the tool can produce machine-verifiable evidence.

Examples: `pytest`, `ruff`, `mypy`, `uhd_usrp_probe`, `benchmark_rate`, checksum tools, leakage checks, split validators, latency benchmarks.

## 8.2 Codex routing default

Prefer Codex when the dominant difficulty is executable implementation or diagnosis, for example:

- repository inspection tied to commands/tests;
- implementation and refactoring;
- debugging through reproduction;
- unit/integration/regression tests;
- CI/build/dependency repair;
- API/control-plane implementation;
- repeatable automation;
- local hardware diagnostics when the resolved Codex execution context actually has the required access and policy allows it.

These are defaults, not permanent role assignments.

## 8.3 Claude Code routing default

Prefer Claude Code when the dominant difficulty is synthesis or design, for example:

- requirements decomposition;
- architecture and trade-off analysis;
- cross-domain RF/DSP/ML/clinical reasoning;
- scientific-method critique;
- evidence synthesis;
- failure-mode/adversarial analysis;
- competing root-cause hypotheses;
- policy, human-factors, or clinical-safety reasoning;
- independent conceptual review of implementation work.

These are defaults, not permanent role assignments.

## 8.4 Dual path

Use builder + independent reviewer for:

- every R2-material task;
- every R3 task;
- R4 preparation where technical review is meaningful;
- ambiguous failures after two reasonable unsuccessful repair attempts;
- stage-gate validation;
- publication-critical claims;
- model/data methodology changes;
- high-impact dashboard/control-plane changes.

The reviewer should normally be different from the primary LLM backend. A human may serve as reviewer/adjudicator where appropriate.

## 8.5 Adaptive routing ledger

Record measured outcomes in `.agent/routing_ledger.csv` and update `.agent/routing.yaml` only when the project has evidence that a route should change.

Suggested fields:

```text
task_id,date,domain,task_type,risk_tier,r2_material,primary_backend,environment,review_backend,validator,first_pass_tests,regressions_found,rework_rounds,human_acceptance,reviewer_findings_accepted,notes
```

Do not change routing merely because a vendor releases a new model.

---

# 9. Independent review protocol

For R2-material/R3/R4 technical work, the reviewer receives a bounded evidence packet, not the builder's private reasoning transcript.

Minimum packet:

- task envelope;
- applicable gate/acceptance criteria;
- input and output Git commits or diff;
- changed files;
- exact commands/tests;
- logs/metrics/plots/checksums;
- known assumptions and unresolved risks;
- builder's concise claimed result.

The reviewer must:

1. reconstruct the problem independently;
2. inspect the actual change/evidence;
3. challenge the reported root cause and scientific interpretation;
4. check for missing failure modes, leakage, unsafe assumptions, or unjustified claims;
5. run or request discriminating validation where feasible;
6. return one of `PASS`, `CONDITIONAL`, `FAIL`, `BLOCKED`;
7. cite reproducible evidence for material findings.

The reviewer is read-only by default. If repair is needed, return the task to the builder or create a new repair task.

---

# 10. Disagreement protocol

Do not resolve disagreement by model confidence, vote, averaging conclusions, or letting the builder overrule the reviewer.

```text
state the falsifiable disagreement
        ↓
define the minimum discriminating test
        ↓
run the test with a deterministic tool or controlled experiment
        ↓
archive the evidence
        ↓
update the conclusion
```

If evidence remains insufficient:

- mark the result `BLOCKED` or `CONDITIONAL`;
- state exactly what evidence is missing;
- escalate to the human/domain authority when the decision cannot safely be automated.

---

# 11. Handoff contract

Use for every cross-backend material handoff.

```yaml
handoff_id: UUID
task_id: string
logical_agent: string
executor_backend: CODEX | CLAUDE_CODE | HUMAN | LOCAL_NON_LLM_TOOL
execution_context_id: string | null
role_in_task: PRIMARY | REVIEWER | VALIDATOR | ADJUDICATOR
timestamp_utc: ISO-8601
mode: BUILD | AUDIT | REPAIR | VALIDATE | CONTINUE
master_gate: G0 | G1 | G1A | G2 | G3 | G4 | G5 | G6 | G7 | G8
risk_tier: R0 | R1 | R2 | R3 | R4
r2_material: true | false | null

repository:
  branch: string
  input_commit: string
  output_commit: string | null
  dirty_before: true | false
  dirty_after: true | false

scope:
  objective: string
  files_inspected: []
  files_changed: []
  protected_paths: []

execution:
  commands: []
  tests: []
  deterministic_validators: []
  evidence_paths: []
  metrics: {}
  checksums: {}

result:
  status: PASS | CONDITIONAL | FAIL | BLOCKED
  concise_rationale: string
  unresolved_risks: []

independent_review:
  required: true | false
  reviewer_backend: CODEX | CLAUDE_CODE | HUMAN | null
  review_status: PENDING | PASS | CONDITIONAL | FAIL | BLOCKED | NOT_REQUIRED

human_approval:
  required: true | false
  action: string | null
  status: NOT_REQUIRED | PENDING | APPROVED | REJECTED
  evidence: string | null
```

Never store private chain-of-thought. Store concise rationale, evidence, decisions, and reproducible commands.

---

# 12. Operating loop

All substantive work follows:

```text
PLAN → ACT → OBSERVE → REASON → RECORD → REPEAT
```

- **PLAN:** read `STATE.md`, Git state, gate criteria, relevant config/evidence; choose the smallest verifiable step.
- **ACT:** make one bounded change or run one controlled measurement.
- **OBSERVE:** capture actual tests, plots, metrics, probe output, errors, or diffs.
- **REASON:** compare observation against acceptance criteria; do not convert expectations into facts.
- **RECORD:** write durable evidence and update the concise project ledger when state materially changed.
- **REPEAT:** continue until the task is complete or blocked.

After two failed repair attempts on the same hypothesis, stop patching blindly. Generate competing hypotheses and run a discriminating test.

---

# 13. Context-loading discipline

## Every substantive task

Read:

1. `STATE.md`;
2. current Git status/head;
3. this framework's relevant sections;
4. the relevant RF framework sections;
5. affected code/tests/config/evidence.

Do not load the entire 3,000+ line RF framework for a tiny local edit.

## Root adapters

`AGENTS.md`, `CLAUDE.md`, and `CODEX.md` must remain short. They may contain routing mechanics and tool-specific verification, but not mutable hardware truth, full milestones, gate definitions, or scientific claims.

Long procedures belong in `RUNBOOK_AGENT_OPERATIONS.md`, scoped skills/rules, or subsystem documentation that loads only when relevant.

---

# 14. Protected data and privacy

- Never assume a cloud execution environment is authorised for raw IQ, participant, clinical, credential, or secret material.
- Resolve `protected_data_access` and policy before access.
- Use de-identified/minimised artifacts where possible.
- Do not put secrets, participant identifiers, raw sensitive data, or credentials into handoff prompts or agent logs.
- Preserve the RF framework's data-separation, ethics, and privacy rules.

---

# 15. RF and hardware controls

Hardware access is capability-based, not vendor-based.

Before any hardware-affecting task:

1. resolve the active execution context;
2. read current device/network configuration from repository state;
3. distinguish RX-only observation from TX-capable action;
4. verify the command's expected effect;
5. for TX-capable action, apply the RF framework's human/regulatory approval boundary;
6. archive probe/measurement evidence.

A local Codex or Claude session may run approved hardware diagnostics if it has the path and permissions. A cloud session of either product may not. The actual environment decides.

---

# 16. Data, ML, and scientific controls

At minimum:

- split by participant/session/site/time before window generation where required;
- record immutable split manifests and hashes;
- do not silently relabel, change thresholds, alter risk horizons, or redefine features;
- model training never auto-promotes a model;
- evaluation code and gate-validation logic are R3 when they can change a consequential conclusion;
- every reported result points to commit, config, dataset/split, model, and metric artifacts;
- distinguish Product A/B/C/D claims as defined in the RF framework.

---

# 17. Git and concurrency

- One writer per overlapping file set.
- Significant parallel work uses branches/worktrees.
- Independent reviewers are read-only by default.
- Capture `git status --short`, branch, and `git rev-parse HEAD` before material work.
- Do not automatically push, force-push, merge, tag, publish, release, or promote a model unless the current workflow explicitly authorises it.
- A clean Git history is not proof that scientific evidence is valid.

---

# 18. Dashboard and orchestration control plane

Expose logical controls, not vendor mythology:

```text
Routing:        AUTO | CODEX | CLAUDE | DUAL | TOOL
Environment:    LOCAL | CLOUD | REMOTE | CI
Mode:           BUILD | AUDIT | REPAIR | VALIDATE | CONTINUE
Intent:         EXPLAIN | PLAN | EXECUTE | REVIEW
Risk:           R0-R4, auto-proposed and visible
R2 material:    yes/no when R2
Primary:        backend + execution context
Reviewer:       backend
Validator:      deterministic tool/human
Evidence:       required / pending / complete
Human approval: not required / pending / approved / rejected
```

The dashboard should show agent handoff cards containing task IDs, diffs/commits, commands, evidence, review status, and approvals. It must not expose or depend on private chain-of-thought.

Natural-language commands must resolve to named/versioned workflows with validated parameters, least privilege, timeout, protected-path checks, preview/approval, audit logging, cancellation, and rollback where possible. Do not feed arbitrary natural language directly to an unrestricted shell.

---

# 19. Use from Codex

Codex reads `AGENTS.md` as its repository instruction entry point. Current Codex CLI can operate against a local repository and run local tools when the execution environment permits it. Codex Cloud is a different environment and must not be conflated with local CLI execution.

Interactive:

```bash
cd ~/carat_research
codex
```

Inside the TUI, `/status` shows session configuration and `/permissions` shows/changes permissions. To verify instruction discovery, ask Codex to list/summarise the active instruction sources; the official AGENTS guidance also documents non-interactive checks.

Repeatable:

```bash
codex exec "Read AGENTS.md and STATE.md. MODE=CONTINUE. INTENT=PLAN. Determine the next smallest verifiable task."
```

Do not use obsolete project guidance such as `approval_mode`, `sandbox =`, `parallel_task_cap`, or `codex --print-instructions` as if they were current Codex controls.

Current documented configuration names include:

```toml
approval_policy = "on-request"
sandbox_mode = "workspace-write"

[agents]
enabled = true
max_concurrent_threads_per_session = 3
```

Treat these as an example, not a mandate. Resolve the installed version and current policy before changing user configuration.

---

# 20. Use from Claude Code

Claude Code reads `CLAUDE.md`; the root file imports `@AGENTS.md` so shared instructions are not duplicated.

Interactive:

```bash
cd ~/carat_research
claude
```

Use `/context` to confirm project memory/instruction files when debugging instruction loading. Keep `CLAUDE.md` concise because persistent instructions consume context and long files reduce adherence.

Non-interactive:

```bash
claude -p "Read CLAUDE.md and STATE.md. MODE=VALIDATE. INTENT=REVIEW. Independently review task <id>."
```

Long repeatable procedures should become scoped skills or runbook sections rather than continuously loaded root instructions.

---

# 21. Terminal and local wrapper

For repeatable cross-agent execution, use a local wrapper that creates the task envelope, resolves capabilities, captures Git state, writes evidence, invokes the selected backend, and enforces review/approval.

Reference structure:

```text
tools/carat_agent/
├── router.py
├── capability_probe.py
├── task_packet.py
├── policy.py
├── evidence.py
├── reviewer.py
├── backends/
│   ├── codex_cli.py
│   ├── claude_cli.py
│   └── local_tool.py
└── cli.py
```

Conceptual routing:

```python
ctx = resolve_execution_context()
task = classify_task(request, gate, repo_state)
route = route_by(task, risk=task.risk, capabilities=ctx.capabilities)

primary = execute(route.primary, task)
validation = run_deterministic_validators(task, primary)
review = None
if route.independent_review_required:
    review = run_independent_reviewer(task, primary, validation)

result = adjudicate_from_evidence(primary, validation, review)
require_human_approval_if_needed(task, result)
record(result)
```

The wrapper must not forward protected data or secrets into a backend that is not authorised to receive them.

---

# 22. STATE.md additions

Keep `STATE.md` concise. Detailed run artifacts belong under `artifacts/agent_runs/`.

Recommended sections:

```markdown
## Active agent task
- Task ID:
- Mode / intent:
- Gate / milestone:
- Risk / R2 material:
- Primary backend / execution context:
- Reviewer / validator:
- Input commit:
- Status:
- Evidence path:

## Agent routing decisions
| date | task | primary/context | reviewer | validator | reason | outcome |

## Pending independent reviews
| task_id | primary | reviewer | status | evidence |

## Pending human approvals
| task_id | action | status | evidence |
```

---

# 23. Definition of done

A material hybrid task is complete only when:

- task/scope and input repository state are known;
- risk is assigned and R2 materiality is resolved;
- required capabilities were verified;
- required tests/measurements and evidence exist;
- assumptions and unresolved risks are explicit;
- the primary did not self-certify R2-material/R3/R4 work;
- independent review is complete where required;
- deterministic validation ran where appropriate;
- disagreements are evidence-resolved or marked blocked;
- required R4 human approval is explicitly `APPROVED`;
- protected data remained within authorised contexts;
- artifacts identify relevant commits/config/datasets/models/logs;
- `STATE.md` is updated when project state materially changed;
- relevant RF-framework acceptance criteria are satisfied.

---

# 24. Anti-patterns

Do not:

- make Claude or Codex the permanent master orchestrator;
- equate Codex with cloud or Claude with local;
- hard-code logical agent roles to one vendor;
- put hardware truth, current IPs, thresholds, model versions, or milestones into root vendor adapters;
- let `STATE.md` override a safety rule;
- let stale documentation override current measured evidence;
- ask Codex to read Claude-only operating detail or vice versa unless review requires it;
- remove deterministic tools from the backend/validation model;
- self-PASS R2-material/R3/R4 work;
- treat model confidence, voting, or consensus as evidence;
- let two agents edit the same files concurrently;
- expose raw IQ/protected data/secrets to an unauthorised context;
- automatically transmit RF, collect human-subject data, promote a model, publish, release, or perform destructive R4 actions;
- keep debating when a small discriminating experiment can settle the issue;
- restructure the repository just to match a diagram.

---

# 25. Minimal recipes

## PLAN

```text
1. Read STATE.md, Git state, relevant gate/config/evidence.
2. Resolve execution context and capabilities.
3. Classify risk and R2 materiality.
4. Choose the simplest suitable backend or deterministic tool.
5. Define acceptance evidence before editing.
```

## IMPLEMENT

```text
1. Capture input commit and dirty state.
2. Make the smallest testable change.
3. Run direct deterministic validation first.
4. Archive evidence.
5. Get independent review for R2-material/R3/R4.
6. Update STATE.md if project state changed.
```

## DEBUG

```text
1. Reproduce before patching.
2. Form a testable root-cause hypothesis.
3. Run the discriminating test.
4. After two failed repair attempts, generate competing hypotheses rather than thrash.
5. Repair, regress, review if material.
```

## VALIDATE A GATE

```text
1. Freeze candidate commit/model/config/data manifest.
2. Collect every required acceptance artifact.
3. Run deterministic checks.
4. Independent reviewer audits evidence and claims.
5. Resolve disagreement by experiment.
6. Return PASS / CONDITIONAL / FAIL / BLOCKED.
7. Obtain explicit human approval for controlled decisions.
```

---

# 26. Product-integration facts verified for this revision

Verified against official documentation on 2026-08-19:

- Codex CLI works against a local repository and can run tools installed on the local machine; Codex Cloud is a separate execution context.
- Codex uses `AGENTS.md` instruction discovery and supports `codex exec`.
- Current Codex configuration uses `approval_policy`, `sandbox_mode`, and `agents.max_concurrent_threads_per_session`.
- Codex TUI exposes `/status` and `/permissions`.
- Claude Code reads `CLAUDE.md`; when sharing `AGENTS.md`, Anthropic documents `@AGENTS.md` import.
- Claude Code supports `claude -p` for non-interactive queries and `/context` for inspecting context/instruction loading.
- Claude Code guidance recommends concise persistent instructions and moving procedures into scoped mechanisms such as skills when appropriate.

Official references:

- OpenAI Codex CLI: `https://developers.openai.com/codex/cli`
- OpenAI Codex AGENTS.md: `https://developers.openai.com/codex/guides/agents-md`
- OpenAI Codex config reference: `https://developers.openai.com/codex/config-reference`
- Anthropic Claude Code memory/instructions: `https://code.claude.com/docs/en/memory`
- Anthropic Claude Code best practices: `https://code.claude.com/docs/en/best-practices`
- Anthropic Claude Code CLI reference: `https://code.claude.com/docs/en/cli-reference`

Re-verify product-specific mechanics before building long-lived automation around CLI flags or settings.

---

# 27. Final rule

Use the least complicated arrangement that can produce trustworthy evidence.

- One backend for R0/R1 when sufficient.
- Deterministic tool first when it can directly answer the question.
- Builder + independent reviewer for R2-material/R3 and technical R4 preparation.
- Human decision at every R4 approval boundary.
- Evidence, not agent identity, decides what is true.
