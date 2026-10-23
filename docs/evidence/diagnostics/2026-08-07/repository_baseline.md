# Repository baseline before Phase 0 edits

- Captured local time: 2026-08-07T13:54:57+10:00
- Root: /home/sdr-research/carat_research
- Branch: main
- Commit: 0e4e519f9f6c410515f41200435103d14dd4cc7b
- Remote: none configured

Initial working tree:

    ## main
     M CLAUDE.md
     M STATE.md
     M logs/live_test_2026-08-02.jsonl
     M logs/tx_log.csv
    ?? RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK_v1_1.md
    ?? RUNBOOK.md
    ?? logs/live_classifier.log
    ?? logs/live_dashboard.log
    ?? logs/live_flowgraph.log
    ?? logs/live_posture.log
    ?? logs/live_spectrogram.log
    ?? logs/live_test_2026-08-04.jsonl
    ?? logs/live_test_logger.log
    ?? logs/live_test_recorder.log

These pre-existing user changes were preserved. The CARAT shutdown added its normal STOPPED row to
the already-modified logs/tx_log.csv. No baseline tag or commit was created because the task is BUILD,
the worktree is dirty, and user changes must not be captured in an inferred commit.

Baseline test command:

    .venv/bin/pytest -m 'not hw' -q

Result: exit 5, three hardware tests deselected, no non-hardware tests collected. This is a baseline
test-coverage gap, not a passing test result.

Initial checksums:

    82d724ee94cb79e7357caad9da6ef46d30d955746d08381138ff85fa6aa809b7  RF_SENSING_FALLS_MULTI_AGENT_FRAMEWORK_v1_1.md
    82efbce1ed528f5d94a3e82f7c191cb1c02e16efa292c42cc6d3e40bd6680518  config/probe.txt
    b42e762467393b64f84a094a43f8edb277f47efb59faa1ef651c89508f9470d5  config/system.yaml
    a8a88c6ae8e7acf6abf05874025c653f71e422d6b5ce2139563f481a0372d142  STATE.md
    1eb104e86709d28e4c6db4144fabe4e7f667bbc2499cb64814e17061608e3857  CLAUDE.md
    5104a930070965a69e939a919cff26e3cc2068c511cc3aff19bc1d57ed06bf5f  logs/tx_log.csv
