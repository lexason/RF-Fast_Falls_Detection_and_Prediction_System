#!/bin/bash
# Background chunked recorder for live pre-demo testing (2026-08-02).
# Calls the EXISTING, already-approved scripts/record_session.py in a loop
# with sequential session IDs and a fixed block duration -- no core system
# files modified. Chunking (not one open-ended recording) means a graceful
# stop between blocks never loses more than one block's worth of data,
# since record_session.py only writes its output after a block completes.
set -u
cd "$(dirname "$0")/.."
source .venv/bin/activate

BLOCK_S=300  # 5 minutes per block
i=1
while true; do
  session_id="2026-08-02_live_test_block${i}"
  python scripts/record_session.py --session-id "$session_id" --activity-class idle \
    --duration "$BLOCK_S" --occupancy "researcher (self-test, live pre-demo testing)" \
    --room "lab, floor-level antenna geometry" \
    --note "Background recording during live pre-demo testing, block ${i}, unscripted activities (see STATE.md for context)"
  i=$((i+1))
done
