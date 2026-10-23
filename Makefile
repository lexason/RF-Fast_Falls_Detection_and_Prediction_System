PYTHON := .venv/bin/python
PYTEST := $(PYTHON) -m pytest

.PHONY: help validate-governance test test-poc test-dashboard build-dashboard poc-dry-run test-hardware diagnostics-readonly audit

help:
	@echo 'validate-governance: .venv/bin/python -m pytest -q tests/unit/test_phase0_governance.py'
	@echo 'test: .venv/bin/python -m pytest -q tests/unit tests -m "not hw"'
	@echo 'test-poc: run offline POC runtime/model/data regression tests'
	@echo 'test-dashboard: run deterministic simulation control-plane tests'
	@echo 'build-dashboard: type-check and compile the React operations UI'
	@echo 'poc-dry-run: print the loopback-only offline deployment plan'
	@echo 'test-hardware: disabled; hardware and TX execution is intentionally unavailable from this Makefile'
	@echo 'diagnostics-readonly: print the exact non-transmitting discovery commands'
	@echo 'audit: run Phase 0 validation and show repository status'

validate-governance:
	@echo 'Running offline semantic cross-artifact validation'
	$(PYTHON) -m tools.governance_validation cross-artifacts
	@echo 'Running: $(PYTEST) -q tests/unit/test_phase0_governance.py'
	$(PYTEST) -q tests/unit/test_phase0_governance.py

test:
	@echo 'Running: $(PYTEST) -q tests/unit tests -m "not hw"'
	$(PYTEST) -q tests/unit tests -m "not hw"

test-poc:
	$(PYTEST) -q tests/unit/test_offline_poc.py

test-dashboard:
	$(PYTEST) -q tests/unit/test_control_plane.py

build-dashboard:
	npm --prefix dashboard/frontend run build

poc-dry-run:
	$(PYTHON) scripts/run_offline_poc.py

test-hardware:
	@echo 'REFUSED: no repository Make target may start an N210 or RF/TX test.'
	@echo 'A future hardware runner requires an implemented signed-approval verifier, exclusive host lock, verified inventory, and separate operator-authorised workflow.'
	@exit 2

diagnostics-readonly:
	@echo 'date --iso-8601=seconds'
	@echo 'uname -a'
	@echo 'python --version'
	@echo 'uhd_config_info --version'
	@echo 'gnuradio-config-info --version'
	@echo 'ip -br link; ip -br addr; ip route get $${RF_FALLS_USRP_ADDR}'
	@echo 'uhd_find_devices --args=addr=$${RF_FALLS_USRP_ADDR}'
	@echo 'uhd_usrp_probe --args=addr=$${RF_FALLS_USRP_ADDR} (only while device is exclusively STOPPED)'

audit: validate-governance
	@echo 'Running: git status --short --branch'
	git status --short --branch
