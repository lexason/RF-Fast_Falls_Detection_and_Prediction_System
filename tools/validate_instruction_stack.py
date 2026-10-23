#!/usr/bin/env python3
"""Static consistency checks for the CARAT harmonized instruction stack.

Uses stdlib only. It cannot prove semantic correctness, but it catches common
regressions that previously caused conflicting authority or stale tool advice.
"""
from pathlib import Path
import re, sys

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
CANON = {
    'rf': 'RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK_v1_4.md',
    'hybrid': 'CARAT_CODEX_CLAUDE_HYBRID_ENGINEERING_FRAMEWORK_v1_1.md',
    'agents': 'AGENTS.md',
    'claude': 'CLAUDE.md',
    'codex': 'CODEX.md',
    'runbook': 'RUNBOOK_AGENT_OPERATIONS.md',
}
errors, warnings = [], []

def text(name):
    p = ROOT / name
    if not p.exists():
        errors.append(f'MISSING: {name}')
        return ''
    return p.read_text(errors='replace')

files = {k: text(v) for k,v in CANON.items()}

# Required thin import pattern.
if '@AGENTS.md' not in files['claude']:
    errors.append('CLAUDE.md must import @AGENTS.md')

# Adapter bloat thresholds: warn early, error at clearly excessive sizes.
for key in ('agents','claude','codex'):
    lines = files[key].count('\n') + 1
    if lines > 160:
        errors.append(f'{CANON[key]} is too large for a root adapter ({lines} lines > 160)')
    elif lines > 100:
        warnings.append(f'{CANON[key]} is growing ({lines} lines); consider runbook/scoped rules')

# Known obsolete/conflicting phrases/keys from prior stacks.
forbidden = {
    r'Codex runs in a cloud sandbox': 'backend identity must not imply cloud environment',
    r'Codex never touches RF hardware': 'hardware access must be capability-based',
    r'Claude Code, always': 'MASTER_ORCHESTRATOR cannot be permanently vendor-bound',
    r'approval_mode\s*=': 'obsolete/incorrect Codex key: use approval_policy',
    r'^\s*sandbox\s*=': 'obsolete/incorrect Codex key: use sandbox_mode',
    r'^\s*parallel_task_cap\s*=': 'non-current Codex concurrency key',
    r'^\s*codex\s+--print-instructions(?:\s|$)': 'non-current Codex instruction verification command',
}
for path in ROOT.rglob('*'):
    if not path.is_file() or path.suffix not in {'.md','.toml','.yaml','.yml','.json'}:
        continue
    if 'instruction_backups' in path.parts:
        continue
    s = path.read_text(errors='replace')
    for pat, msg in forbidden.items():
        if re.search(pat, s, flags=re.I|re.M):
            errors.append(f'{path.relative_to(ROOT)}: {msg} [{pat}]')

# Stale canonical filenames should not be active references.
stale = [
    'CARAT_CODEX_CLAUDE_HYBRID_ENGINEERING_FRAMEWORK_v1_0.md',
    'RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK_v1_2.md',
    'RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK_v1_3.md',
    'AGENT_ORCHESTRATION.md',
]
for path in [ROOT/CANON['agents'], ROOT/CANON['claude'], ROOT/CANON['codex'], ROOT/CANON['hybrid'], ROOT/CANON['rf']]:
    if not path.exists():
        continue
    s = path.read_text(errors='replace')
    for old in stale:
        if old in s:
            errors.append(f'{path.name}: stale active framework reference {old}')

# Gate definitions should live only in RF domain framework. Mentions are fine;
# actual markdown headings like "## G3 ..." elsewhere are suspicious.
for key in ('agents','claude','codex','hybrid','runbook'):
    for m in re.finditer(r'^#{1,4}\s+G(?:0|1A?|2|3|4|5|6|7|8)\b', files[key], flags=re.M):
        errors.append(f'{CANON[key]}: duplicate gate-definition heading near line {files[key][:m.start()].count(chr(10))+1}')

# Vendor adapters should not become hardware-truth stores.
hardware_truth_patterns = [
    r'192\.168\.\d+\.\d+',
    r'\b(?:TX|RX)\s+gain\s*=\s*\d',
    r'\bsample[_ -]?rate\s*=\s*\d',
]
for key in ('agents','claude','codex'):
    for pat in hardware_truth_patterns:
        if re.search(pat, files[key], flags=re.I):
            warnings.append(f'{CANON[key]} may contain mutable hardware truth matching {pat}')

# Expected current mechanics.
if 'approval_policy' not in files['hybrid'] or 'sandbox_mode' not in files['hybrid']:
    warnings.append('Hybrid framework does not document current Codex config names')
if 'LOCAL_NON_LLM_TOOL' not in files['hybrid'] or 'LOCAL_NON_LLM_TOOL' not in files['rf']:
    errors.append('LOCAL_NON_LLM_TOOL must remain first-class in both hybrid and RF frameworks')
if 'r2_material' not in files['hybrid']:
    errors.append('Hybrid framework must define R2 materiality')
if 'execution_context' not in files['hybrid']:
    errors.append('Hybrid framework must define execution-context/capability routing')

print(f'CARAT instruction-stack validation: {ROOT}')
for w in warnings:
    print('WARN :', w)
for e in errors:
    print('ERROR:', e)
print(f'\nSummary: {len(errors)} error(s), {len(warnings)} warning(s)')
sys.exit(1 if errors else 0)
