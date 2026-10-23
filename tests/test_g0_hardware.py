"""G0 hardware-in-the-loop smoke tests. Run at gates only: pytest -m hw tests/test_g0_hardware.py

Requires the live N210 at 192.168.10.50 with a working FPGA/firmware image
(see docs/n210_fpga_compat_fix_guide.md and STATE.md for how that was
resolved). Encodes CLAUDE.md's G0 acceptance criteria as executable checks.
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_RATE = "/usr/local/lib/uhd/examples/benchmark_rate"


@pytest.mark.hw
def test_probe_succeeds_and_identifies_ubx40():
    result = subprocess.run(
        ["uhd_usrp_probe", "--args", "addr=192.168.10.50"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"uhd_usrp_probe failed:\n{result.stdout}\n{result.stderr}"
    assert "UBX-40" in result.stdout, "expected UBX-40 daughterboard in probe output"
    assert "N210r4" in result.stdout


@pytest.mark.hw
def test_rx_benchmark_10msps_60s_zero_overflows():
    result = subprocess.run(
        [BENCHMARK_RATE, "--args", "addr=192.168.10.50", "--rx_rate", "10e6", "--duration", "60"],
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, f"benchmark_rate failed:\n{result.stdout}\n{result.stderr}"
    assert "Num dropped samples:      0" in result.stdout
    assert "Num overruns detected:    0" in result.stdout


@pytest.mark.hw
def test_tone_loopback_via_cal_path():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "tone_loopback_test.py")],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"tone loopback test failed:\n{result.stdout}\n{result.stderr}"
    assert "PASS" in result.stdout
