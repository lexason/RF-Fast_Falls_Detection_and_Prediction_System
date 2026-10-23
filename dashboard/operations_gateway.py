"""Typed local operations gateway for the CARAT DEVELOPMENT workstation.

The gateway is deliberately *not* a generic command runner.  Every executable,
argument, working directory, endpoint and output bound is constructed here from
validated values.  Commands are launched with ``shell=False`` in their own
process groups and can be reconciled after an API restart from a small runtime
registry.  This is the laboratory implementation of the framework's narrow
control-helper boundary; production deployment should replace it with the
documented systemd/PolicyKit service while keeping this interface.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import psutil
import yaml


OUTPUT_LIMIT_BYTES = 128 * 1024
SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,95}$")
CANDIDATE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
PROFILE_ID = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


class GatewayError(RuntimeError):
    """A typed operational action was rejected or failed."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CommandResult:
    argv_id: str
    returncode: int
    duration_ms: int
    stdout: str
    stderr: str
    output_truncated: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.argv_id,
            "returncode": self.returncode,
            "duration_ms": self.duration_ms,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "output_truncated": self.output_truncated,
        }


class OperationsGateway:
    """Fixed-command process supervisor and data/model operations adapter."""

    SERVICE_ORDER = ("event_aggregation", "inference", "preprocessing", "acquisition")
    LEGACY_SERVICE_SCRIPTS = {
        "acquisition": "sdr/cw_doppler_tx_rx.py",
        "preprocessing": "dsp/spectrogram_service.py",
        "inference": "inference/realtime_classifier.py",
        "event_aggregation": "inference/posture_state_machine.py",
    }

    def __init__(
        self,
        repo_root: Path,
        *,
        execution_mode: str = "simulation",
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        if execution_mode not in {"simulation", "operational"}:
            raise ValueError("execution mode must be simulation or operational")
        self.repo_root = repo_root.resolve()
        self.execution_mode = execution_mode
        self.python = self.repo_root / ".venv" / "bin" / "python"
        if not self.python.exists():
            self.python = Path(sys.executable).resolve()
        self.runtime_dir = self.repo_root / "artifacts" / "control_plane" / "runtime"
        self.log_dir = self.runtime_dir / "logs"
        self.registry_path = self.runtime_dir / "processes.json"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._runner = runner or subprocess.run
        self._uses_default_runner = runner is None
        self._children: dict[str, subprocess.Popen[bytes]] = {}
        self._log_handles: dict[str, Any] = {}
        self._jobs: dict[str, subprocess.Popen[str]] = {}
        self._mutex = threading.RLock()
        self.instance_id = str(uuid.uuid4())
        self._records = self._load_records()

    @classmethod
    def from_environment(cls, repo_root: Path) -> "OperationsGateway":
        mode = os.environ.get("RF_FALLS_EXECUTION_MODE", "operational").strip().lower()
        return cls(repo_root, execution_mode=mode)

    @property
    def operational(self) -> bool:
        return self.execution_mode == "operational"

    def capabilities(self) -> dict[str, Any]:
        required = {
            "python": self.python,
            "uhd_find_devices": Path(shutil.which("uhd_find_devices") or "/nonexistent"),
            "uhd_usrp_probe": Path(shutil.which("uhd_usrp_probe") or "/nonexistent"),
        }
        return {
            "execution_mode": self.execution_mode.upper(),
            "operational_actions_enabled": self.operational,
            "fixed_argv_only": True,
            "shell_interpolation": False,
            "process_group_supervision": True,
            "restart_reconciliation": True,
            "executables": {name: path.exists() for name, path in required.items()},
            "pipelines": ["SIMULATION", "REPLAY", "LIVE_SDR"],
            "raw_iq_inventory": True,
            "raw_iq_server_side_processing": True,
            "raw_iq_browser_egress": False,
            "model_pointer_compare_and_swap": True,
        }

    def _require_operational(self) -> None:
        if not self.operational:
            raise GatewayError("operational adapter is disabled; select simulation or enable supervised operational mode")

    def _load_records(self) -> dict[str, dict[str, Any]]:
        try:
            document = json.loads(self.registry_path.read_text(encoding="utf-8"))
            return document if isinstance(document, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_records(self) -> None:
        temporary = self.registry_path.with_suffix(f".tmp-{os.getpid()}")
        temporary.write_text(json.dumps(self._records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, self.registry_path)

    @staticmethod
    def _argv_digest(argv: list[str]) -> str:
        return canonical_digest(argv)

    @staticmethod
    def _bounded(text: str) -> tuple[str, bool]:
        encoded = text.encode("utf-8", errors="replace")
        if len(encoded) <= OUTPUT_LIMIT_BYTES:
            return text, False
        suffix = b"\n...[OUTPUT TRUNCATED]"
        return (encoded[: OUTPUT_LIMIT_BYTES - len(suffix)] + suffix).decode("utf-8", errors="replace"), True

    def _minimal_environment(self) -> dict[str, str]:
        allowed = ("PATH", "LANG", "LC_ALL", "TZ", "PYTHONPATH", "LD_LIBRARY_PATH", "UHD_IMAGES_DIR")
        environment = {name: os.environ[name] for name in allowed if name in os.environ}
        environment["PYTHONUNBUFFERED"] = "1"
        return environment

    def run_fixed(
        self,
        tool_id: str,
        argv: list[str],
        *,
        timeout_seconds: float = 30,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        """Run an already-constructed argv without a shell, stdin, cwd, or env injection."""

        self._require_operational()
        started = time.monotonic()
        if self._uses_default_runner:
            process = subprocess.Popen(
                argv,
                cwd=self.repo_root,
                env=self._minimal_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
                shell=False,
            )
            if job_id:
                with self._mutex:
                    if job_id in self._jobs:
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                        raise GatewayError("a job with this workflow identifier is already running")
                    self._jobs[job_id] = process
            try:
                stdout_text, stderr_text = process.communicate(timeout=timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    process.communicate(timeout=5)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    try:
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.communicate()
                raise GatewayError(f"{tool_id} exceeded its {timeout_seconds:g}s timeout") from exc
            finally:
                if job_id:
                    with self._mutex:
                        self._jobs.pop(job_id, None)
            returncode = int(process.returncode)
        else:
            try:
                completed = self._runner(
                    argv,
                    cwd=self.repo_root,
                    env=self._minimal_environment(),
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                    shell=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise GatewayError(f"{tool_id} exceeded its {timeout_seconds:g}s timeout") from exc
            stdout_text = completed.stdout or ""
            stderr_text = completed.stderr or ""
            returncode = int(completed.returncode)
        stdout, stdout_cut = self._bounded(stdout_text or "")
        stderr, stderr_cut = self._bounded(stderr_text or "")
        result = CommandResult(
            tool_id,
            returncode,
            int((time.monotonic() - started) * 1000),
            stdout,
            stderr,
            stdout_cut or stderr_cut,
        )
        if returncode:
            detail = stderr.strip() or stdout.strip() or f"exit {returncode}"
            raise GatewayError(f"{tool_id} failed: {detail[:1000]}")
        return result.as_dict()

    def cancel_job(self, job_id: str) -> bool:
        """Terminate one tracked long-running fixed-argv job and its descendants."""

        with self._mutex:
            process = self._jobs.get(job_id)
        if process is None or process.poll() is not None:
            return False
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass

        def force_after_grace() -> None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass

        threading.Thread(target=force_after_grace, name=f"cancel-{job_id[:8]}", daemon=True).start()
        return True

    def job_running(self, job_id: str) -> bool:
        with self._mutex:
            process = self._jobs.get(job_id)
        return process is not None and process.poll() is None

    def _spawn_service(self, service_id: str, argv: list[str], *, maximum_seconds: int | None = None) -> dict[str, Any]:
        self._require_operational()
        current = self.service_status().get(service_id)
        if current and current["status"] == "RUNNING":
            return current
        command = list(argv)
        if maximum_seconds is not None:
            timeout_binary = shutil.which("timeout")
            if not timeout_binary:
                raise GatewayError("bounded RF execution requires the system timeout executable")
            command = [timeout_binary, "--signal=TERM", "--kill-after=5s", str(maximum_seconds), *command]
        log_path = self.log_dir / f"{service_id}.log"
        log_handle = log_path.open("ab", buffering=0)
        try:
            process = subprocess.Popen(
                command,
                cwd=self.repo_root,
                env=self._minimal_environment(),
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                shell=False,
            )
        except Exception:
            log_handle.close()
            raise
        time.sleep(0.1)
        if process.poll() is not None:
            log_handle.close()
            tail = self.read_service_log(service_id, max_bytes=8192)
            raise GatewayError(f"{service_id} exited during startup: {tail['content'][-1000:]}")
        ps_process = psutil.Process(process.pid)
        record = {
            "service_id": service_id,
            "pid": process.pid,
            "pgid": os.getpgid(process.pid),
            "create_time": ps_process.create_time(),
            "argv_digest": self._argv_digest(command),
            "argv": command,
            "cwd": str(self.repo_root),
            "log_path": str(log_path.relative_to(self.repo_root)),
            "started_at_unix": time.time(),
            "owner_instance_id": self.instance_id,
            "maximum_seconds": maximum_seconds,
        }
        with self._mutex:
            self._children[service_id] = process
            self._log_handles[service_id] = log_handle
            self._records[service_id] = record
            self._save_records()
        if maximum_seconds is not None:
            def stop_dependants_when_bounded_source_exits() -> None:
                process.wait()
                with self._mutex:
                    current = self._records.get(service_id)
                if current and current.get("pid") == process.pid:
                    self.stop_pipeline(emergency=False)

            threading.Thread(
                target=stop_dependants_when_bounded_source_exits,
                name=f"bounded-{service_id}-{process.pid}",
                daemon=True,
            ).start()
        return {**record, "status": "RUNNING"}

    def _validated_process(self, record: dict[str, Any]) -> psutil.Process | None:
        try:
            process = psutil.Process(int(record["pid"]))
            if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
                return None
            if abs(process.create_time() - float(record["create_time"])) > 0.01:
                return None
            if self._argv_digest(process.cmdline()) != record["argv_digest"]:
                return None
            return process
        except (KeyError, TypeError, ValueError, psutil.Error):
            return None

    def service_status(self) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}
        changed = False
        with self._mutex:
            for service_id, record in list(self._records.items()):
                process = self._validated_process(record)
                if process is None:
                    output[service_id] = {**record, "status": "STOPPED"}
                    self._records.pop(service_id, None)
                    child = self._children.pop(service_id, None)
                    if child is not None:
                        child.poll()
                    handle = self._log_handles.pop(service_id, None)
                    if handle is not None:
                        handle.close()
                    changed = True
                else:
                    output[service_id] = {
                        **record,
                        "status": "RUNNING",
                        "cpu_percent": process.cpu_percent(interval=None),
                        "rss_bytes": process.memory_info().rss,
                    }
            if changed:
                self._save_records()
        return output

    def external_service_status(self) -> dict[str, dict[str, Any]]:
        """Discover exact, repository-local pipeline processes not owned by this gateway.

        This intentionally is not a broad process-name search. A process is reported
        only when its cwd is this repository and its argv contains one of the fixed,
        allowlisted script tokens. Immutable identity fields are retained so a later
        stop request can revalidate the process before signalling it.
        """

        managed_pids = {int(item["pid"]) for item in self._records.values() if item.get("pid")}
        discovered: dict[str, dict[str, Any]] = {}
        for process in psutil.process_iter(["pid", "create_time", "cmdline"]):
            try:
                if process.pid in managed_pids or not process.is_running():
                    continue
                if process.cwd() != str(self.repo_root):
                    continue
                cmdline = process.cmdline()
                service_id = next(
                    (
                        name
                        for name, script in self.LEGACY_SERVICE_SCRIPTS.items()
                        if script in cmdline
                    ),
                    None,
                )
                if service_id is None:
                    continue
                pgid = os.getpgid(process.pid)
                record: dict[str, Any] = {
                    "service_id": service_id,
                    "pid": process.pid,
                    "pgid": pgid,
                    "create_time": process.create_time(),
                    "argv_digest": self._argv_digest(cmdline),
                    "argv": cmdline,
                    "cwd": str(self.repo_root),
                    "status": "UNMANAGED_RUNNING",
                    "supervision": "DISCOVERED_LEGACY_PROCESS",
                    "cpu_percent": process.cpu_percent(interval=None),
                    "rss_bytes": process.memory_info().rss,
                }
                if service_id == "inference" and "--model-dir" in cmdline:
                    index = cmdline.index("--model-dir")
                    if index + 1 < len(cmdline):
                        record["runtime_model_dir"] = cmdline[index + 1]
                # Multiple matches are a conflict, never an arbitrary selection.
                if service_id in discovered:
                    existing = discovered[service_id]
                    existing["status"] = "UNMANAGED_CONFLICT"
                    existing.setdefault("conflicting_records", []).append(record)
                    existing["conflicting_pids"] = [existing["pid"], *[item["pid"] for item in existing["conflicting_records"]]]
                else:
                    discovered[service_id] = record
            except (psutil.Error, ProcessLookupError, PermissionError):
                continue
        return discovered

    def _stop_external_service(self, record: dict[str, Any], *, emergency: bool = False) -> dict[str, Any]:
        """Stop one previously-discovered exact process after identity revalidation."""

        service_id = str(record["service_id"])
        try:
            process = psutil.Process(int(record["pid"]))
            live_create_time = process.create_time()
            delta = abs(live_create_time - float(record["create_time"]))
            if delta > 0.01:
                raise GatewayError(
                    f"refusing to stop {service_id}: process identity changed "
                    f"(record.create_time={record['create_time']!r}, live={live_create_time!r}, delta={delta!r}, "
                    f"record.pid={record['pid']!r}, live.pid={process.pid!r})"
                )
            if process.cwd() != str(self.repo_root):
                raise GatewayError(
                    f"refusing to stop {service_id}: working directory changed "
                    f"(record.cwd={record.get('cwd')!r}, live.cwd={process.cwd()!r}, expected={str(self.repo_root)!r})"
                )
            live_argv = process.cmdline()
            live_argv_digest = self._argv_digest(live_argv)
            if live_argv_digest != record["argv_digest"]:
                raise GatewayError(
                    f"refusing to stop {service_id}: command identity changed "
                    f"(record.argv={record.get('argv')!r}, live.argv={live_argv!r}, "
                    f"record.digest={record['argv_digest']!r}, live.digest={live_argv_digest!r})"
                )
            pgid = os.getpgid(process.pid)
            if pgid != int(record["pgid"]) or pgid != process.pid:
                raise GatewayError(
                    f"refusing to stop {service_id}: unsafe shared process group "
                    f"(record.pgid={record['pgid']!r}, live.pgid={pgid!r}, live.pid={process.pid!r})"
                )
        except psutil.NoSuchProcess:
            return {"service_id": service_id, "status": "ALREADY_STOPPED", "source": "legacy"}
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + (1.0 if emergency else 8.0)
        while time.monotonic() < deadline:
            try:
                if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
                    break
            except psutil.NoSuchProcess:
                break
            time.sleep(0.05)
        forced = False
        try:
            still_running = process.is_running() and process.status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            still_running = False
        if still_running:
            forced = True
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        return {"service_id": service_id, "status": "STOPPED", "forced": forced, "source": "legacy"}

    def _stop_service(self, service_id: str, *, emergency: bool = False) -> dict[str, Any]:
        with self._mutex:
            record = self._records.get(service_id)
        if record is None:
            return {"service_id": service_id, "status": "ALREADY_STOPPED"}
        process = self._validated_process(record)
        if process is None:
            with self._mutex:
                self._records.pop(service_id, None)
                child = self._children.pop(service_id, None)
                if child is not None:
                    child.poll()
                handle = self._log_handles.pop(service_id, None)
                if handle is not None:
                    handle.close()
                self._save_records()
            return {"service_id": service_id, "status": "ALREADY_STOPPED"}
        pgid = int(record["pgid"])
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + (1.0 if emergency else 8.0)
        while time.monotonic() < deadline and self._validated_process(record) is not None:
            time.sleep(0.05)
        forced = False
        if self._validated_process(record) is not None:
            forced = True
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        with self._mutex:
            self._records.pop(service_id, None)
            child = self._children.pop(service_id, None)
            if child is not None:
                try:
                    child.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
            handle = self._log_handles.pop(service_id, None)
            if handle is not None:
                handle.close()
            self._save_records()
        return {"service_id": service_id, "status": "STOPPED", "forced": forced}

    def start_pipeline(
        self,
        profile: str,
        *,
        profile_id: str | None = None,
        replay_session: str | None = None,
        tx_gain_db: float | None = None,
        rx_gain_db: float = 20.0,
        maximum_seconds: int | None = None,
    ) -> dict[str, Any]:
        self._require_operational()
        if profile not in {"replay", "live_sdr"}:
            raise GatewayError("operational pipeline profile must be replay or live_sdr")
        active = [item for item in self.service_status().values() if item["status"] == "RUNNING"]
        if active:
            raise GatewayError("a managed pipeline is already running; stop it before starting another")
        external = self.external_service_status()
        if external:
            services = ", ".join(sorted(external))
            raise GatewayError(
                f"an existing repository pipeline is already running ({services}); stop it from the dashboard first"
            )

        raw_endpoint = "tcp://127.0.0.1:5580"
        spectrogram_endpoint = "tcp://127.0.0.1:5591"
        classifier_endpoint = "tcp://127.0.0.1:5593"
        activity_endpoint = "tcp://127.0.0.1:5594"
        model_dir = self.resolve_active_model_dir()
        commands: dict[str, list[str]] = {
            "event_aggregation": [
                str(self.python), "inference/posture_state_machine.py",
                "--in-addr", classifier_endpoint, "--out-addr", activity_endpoint,
            ],
            "inference": [
                str(self.python), "inference/realtime_classifier.py",
                "--in-addr", spectrogram_endpoint, "--out-addr", classifier_endpoint,
                "--model-dir", str(model_dir),
            ],
            "preprocessing": [
                str(self.python), "dsp/spectrogram_service.py",
                "--in-addr", raw_endpoint, "--out-addr", spectrogram_endpoint,
            ],
        }
        if profile == "replay":
            if not replay_session or not SESSION_ID.fullmatch(replay_session):
                raise GatewayError("a safe replay session identifier is required")
            session_dir = (self.repo_root / "data" / "raw" / replay_session).resolve()
            if not session_dir.is_relative_to(self.repo_root / "data" / "raw") or not session_dir.is_dir():
                raise GatewayError("replay session does not exist")
            commands["acquisition"] = [
                str(self.python), "scripts/replay.py", str(session_dir),
                "--zmq-addr", raw_endpoint, "--repeat", "--speed", "1.0",
            ]
        else:
            if not profile_id or not PROFILE_ID.fullmatch(profile_id):
                raise GatewayError("live SDR requires an allowlisted RF profile identifier")
            profile_path = (self.repo_root / "configs" / "rf_profiles" / f"{profile_id}.yaml").resolve()
            profiles_root = (self.repo_root / "configs" / "rf_profiles").resolve()
            if not profile_path.is_relative_to(profiles_root) or not profile_path.is_file():
                raise GatewayError("RF profile does not exist")
            rf_profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
            system = yaml.safe_load((self.repo_root / "config" / "system.yaml").read_text(encoding="utf-8"))
            expected = {
                "profile_id": profile_id,
                "status": "ENABLED_FOR_SUPERVISED_WORKFLOW",
                "device_serial": str(system["usrp"]["serial"]),
                "centre_frequency_hz": int(system["carrier"]["f0_hz"]),
                "sample_rate_hz": int(system["sample_rates"]["capture_hz"]),
                "tx_port": system["antenna"]["tx_port_antenna"],
                "rx_port": system["antenna"]["rx_port_antenna"],
            }
            mismatches = [name for name, value in expected.items() if rf_profile.get(name) != value]
            if mismatches:
                raise GatewayError(f"RF profile does not match current verified configuration: {', '.join(mismatches)}")
            if tx_gain_db is None or not 0.0 <= tx_gain_db <= 15.0:
                raise GatewayError("live SDR TX gain must be explicitly set in the approved 0-15 dB range")
            if tx_gain_db > float(rf_profile["maximum_tx_gain_db"]):
                raise GatewayError("live SDR TX gain exceeds the selected RF profile")
            if not 0.0 <= rx_gain_db <= 35.0:
                raise GatewayError("live SDR RX gain is outside the approved 0-35 dB range")
            if rx_gain_db > float(rf_profile["maximum_rx_gain_db"]):
                raise GatewayError("live SDR RX gain exceeds the selected RF profile")
            if maximum_seconds is None or not 1 <= maximum_seconds <= int(rf_profile["maximum_duration_seconds"]):
                raise GatewayError("live SDR run must have an automatic stop bound of 1-3600 seconds")
            commands["acquisition"] = [
                str(self.python), "sdr/cw_doppler_tx_rx.py",
                "--tx-gain", str(float(tx_gain_db)), "--rx-gain", str(float(rx_gain_db)),
                "--zmq-addr", raw_endpoint,
            ]

        started: list[str] = []
        try:
            for service_id in self.SERVICE_ORDER:
                self._spawn_service(
                    service_id,
                    commands[service_id],
                    maximum_seconds=maximum_seconds if service_id == "acquisition" and profile == "live_sdr" else None,
                )
                started.append(service_id)
        except Exception:
            for service_id in reversed(started):
                self._stop_service(service_id, emergency=True)
            raise
        result = {"mode": profile.upper(), "services": self.service_status(), "rf_transmission": profile == "live_sdr"}
        if profile == "live_sdr":
            result.update({"rf_profile_id": profile_id, "rf_profile_sha256": sha256_file(profile_path)})
        return result

    def stop_pipeline(self, *, emergency: bool = False) -> dict[str, Any]:
        results = []
        order = ("acquisition", "preprocessing", "inference", "event_aggregation")
        external = self.external_service_status()
        for service_id in order:
            results.append(self._stop_service(service_id, emergency=emergency))
            if service_id in external:
                primary = {key: value for key, value in external[service_id].items() if key not in {"conflicting_records", "conflicting_pids"}}
                records = [primary, *external[service_id].get("conflicting_records", [])]
                for record in records:
                    results.append(self._stop_external_service(record, emergency=emergency))
        remaining = self.external_service_status()
        managed_remaining = {name: item for name, item in self.service_status().items() if item.get("status") == "RUNNING"}
        if remaining or managed_remaining:
            survivors = sorted({*remaining, *managed_remaining})
            raise GatewayError(f"pipeline stop verification failed; services remain active: {', '.join(survivors)}")
        return {"status": "STOPPED", "emergency": emergency, "services": results, "verified_no_pipeline_processes": True}

    def read_service_log(self, service_id: str, *, max_bytes: int = 32768) -> dict[str, Any]:
        if service_id not in {*self.SERVICE_ORDER, "raw_capture", "candidate_training", "candidate_evaluation"}:
            raise GatewayError("unknown service log")
        path = self.log_dir / f"{service_id}.log"
        if not path.exists():
            return {"service_id": service_id, "content": "", "bytes": 0}
        size = path.stat().st_size
        with path.open("rb") as handle:
            handle.seek(max(0, size - min(max_bytes, OUTPUT_LIMIT_BYTES)))
            content = handle.read(min(max_bytes, OUTPUT_LIMIT_BYTES)).decode("utf-8", errors="replace")
        return {"service_id": service_id, "content": content, "bytes": size, "truncated": size > max_bytes}

    def discover_usrp(self, *, full_probe: bool = False) -> dict[str, Any]:
        self._require_operational()
        config = yaml.safe_load((self.repo_root / "config" / "system.yaml").read_text(encoding="utf-8"))
        address = str(config["usrp"]["addr"])
        if not re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", address):
            raise GatewayError("configured USRP address is invalid")
        executable = shutil.which("uhd_usrp_probe" if full_probe else "uhd_find_devices")
        if not executable:
            raise GatewayError("UHD discovery executable is unavailable")
        result = self.run_fixed(
            "usrp.probe" if full_probe else "usrp.discover",
            [executable, f"--args=addr={address}"],
            timeout_seconds=45 if full_probe else 15,
        )
        result.update({"device_address": address, "full_probe": full_probe})
        return result

    def raw_inventory(self) -> list[dict[str, Any]]:
        root = self.repo_root / "data" / "raw"
        output: list[dict[str, Any]] = []
        if not root.exists():
            return output
        for session_dir in sorted(root.iterdir()):
            if not session_dir.is_dir() or not SESSION_ID.fullmatch(session_dir.name):
                continue
            manifest_path = session_dir / "manifest.json"
            data_files = sorted(session_dir.glob("*.sigmf-data"))
            metadata_files = sorted(session_dir.glob("*.sigmf-meta"))
            manifest: dict[str, Any] = {}
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
            except (OSError, ValueError):
                manifest = {}
            data_path = data_files[0] if len(data_files) == 1 else None
            metadata_path = metadata_files[0] if len(metadata_files) == 1 else None
            sample_rate = manifest.get("sample_rate_hz")
            size = data_path.stat().st_size if data_path else None
            output.append(
                {
                    "session_id": session_dir.name,
                    "synthetic": manifest.get("synthetic"),
                    "activity_class": manifest.get("activity_class"),
                    "carrier_hz": manifest.get("carrier_hz"),
                    "sample_rate_hz": sample_rate,
                    "raw_bytes": size,
                    "duration_s": size / 8 / sample_rate if size and isinstance(sample_rate, (int, float)) and sample_rate > 0 else None,
                    "manifest_sha256": sha256_file(manifest_path) if manifest_path.exists() else None,
                    "metadata_sha256": sha256_file(metadata_path) if metadata_path else None,
                    "raw_file_available": data_path is not None,
                    "raw_iq_served_by_default": False,
                }
            )
        return output

    def raw_iq_path(self, session_id: str) -> Path:
        if not SESSION_ID.fullmatch(session_id):
            raise GatewayError("invalid raw-IQ session identifier")
        root = (self.repo_root / "data" / "raw").resolve()
        session_dir = (root / session_id).resolve()
        if not session_dir.is_relative_to(root) or not session_dir.is_dir():
            raise GatewayError("raw-IQ session does not exist")
        files = sorted(session_dir.glob("*.sigmf-data"))
        if len(files) != 1 or not files[0].is_file():
            raise GatewayError("raw-IQ session does not contain exactly one SigMF data file")
        return files[0]

    def capture_raw_iq(
        self,
        *,
        session_id: str,
        activity_class: str,
        duration_seconds: int,
        note: str,
        occupancy: str,
        room: str,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        self._require_operational()
        if not SESSION_ID.fullmatch(session_id):
            raise GatewayError("invalid capture session identifier")
        if activity_class not in {"walk", "sit_stand", "lie_down", "fall", "idle", "empty_room"}:
            raise GatewayError("activity class is not allowlisted")
        if not 1 <= duration_seconds <= 600:
            raise GatewayError("capture duration must be 1-600 seconds")
        if not (10 <= len(note) <= 512 and 3 <= len(occupancy) <= 128 and 3 <= len(room) <= 128):
            raise GatewayError("capture purpose, occupancy, or room description is invalid")
        if (self.repo_root / "data" / "raw" / session_id).exists():
            raise GatewayError("immutable capture session identifier already exists")
        argv = [
            str(self.python), "scripts/record_session.py",
            "--session-id", session_id,
            "--activity-class", activity_class,
            "--duration", str(duration_seconds),
            "--note", note,
            "--occupancy", occupancy,
            "--room", room,
            "--zmq-addr", "tcp://127.0.0.1:5580",
        ]
        result = self.run_fixed(
            "data.capture_raw_iq",
            argv,
            timeout_seconds=duration_seconds + 30,
            job_id=job_id,
        )
        path = self.raw_iq_path(session_id)
        result.update({"session_id": session_id, "raw_bytes": path.stat().st_size, "sha256": sha256_file(path)})
        return result

    def _dataset_from_manifest(self, manifest_ref: str) -> Path:
        if Path(manifest_ref).is_absolute() or ".." in Path(manifest_ref).parts or not manifest_ref.endswith(".json"):
            raise GatewayError("dataset manifest reference is unsafe")
        manifest_path = (self.repo_root / manifest_ref).resolve()
        if not manifest_path.is_relative_to(self.repo_root) or not manifest_path.is_file():
            raise GatewayError("dataset manifest does not exist")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifacts = manifest.get("processed_artifacts", [])
        preferred = next(
            (item for item in artifacts if str(item.get("path", "")).endswith("g3_features_v2_conflict_free.parquet")),
            artifacts[0] if artifacts else None,
        )
        if not isinstance(preferred, dict):
            raise GatewayError("dataset manifest has no processed artifact")
        dataset = (self.repo_root / str(preferred.get("path", ""))).resolve()
        if not dataset.is_relative_to(self.repo_root / "data" / "processed") or not dataset.is_file():
            raise GatewayError("manifest dataset path is unavailable")
        expected = preferred.get("sha256")
        if not isinstance(expected, str) or sha256_file(dataset) != expected:
            raise GatewayError("manifest dataset digest does not match the processed artifact")
        return dataset

    def train_candidate(
        self,
        candidate_id: str,
        dataset_manifest: str,
        *,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        self._require_operational()
        if not CANDIDATE_ID.fullmatch(candidate_id):
            raise GatewayError("candidate identifier must be 3-64 lowercase safe characters")
        dataset = self._dataset_from_manifest(dataset_manifest)
        result = self.run_fixed(
            "model.train_candidate",
            [str(self.python), "models/train_candidate.py", "--candidate-id", candidate_id, "--dataset", str(dataset)],
            timeout_seconds=3600,
            job_id=job_id,
        )
        metadata = self.repo_root / "models" / "candidates" / candidate_id / "metadata.json"
        result.update({"candidate_id": candidate_id, "metadata_sha256": sha256_file(metadata), "active_model_changed": False})
        return result

    def evaluate_candidate(
        self,
        candidate_id: str,
        dataset_manifest: str,
        *,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        self._require_operational()
        if not CANDIDATE_ID.fullmatch(candidate_id):
            raise GatewayError("candidate identifier is invalid")
        dataset = self._dataset_from_manifest(dataset_manifest)
        output = self.repo_root / "artifacts" / "evaluations" / f"{candidate_id}-dashboard-{uuid.uuid4().hex[:8]}.json"
        result = self.run_fixed(
            "model.evaluate_candidate",
            [
                str(self.python), "models/evaluate_development.py",
                "--candidate-id", candidate_id, "--dataset", str(dataset), "--out", str(output),
            ],
            timeout_seconds=3600,
            job_id=job_id,
        )
        report = json.loads(output.read_text(encoding="utf-8"))
        result.update({"candidate_id": candidate_id, "evaluation_path": str(output.relative_to(self.repo_root)), "evaluation_sha256": sha256_file(output), "status": report.get("status"), "promotion_eligible": bool(report.get("promotion_eligible", False))})
        return result

    def generate_threshold_study(self, candidate_id: str, *, job_id: str | None = None) -> dict[str, Any]:
        self._require_operational()
        if not CANDIDATE_ID.fullmatch(candidate_id):
            raise GatewayError("candidate identifier is invalid")
        metadata = self.repo_root / "models" / "candidates" / candidate_id / "metadata.json"
        if not metadata.is_file():
            raise GatewayError("candidate bundle does not exist")
        evaluations: list[Path] = []
        for path in (self.repo_root / "artifacts" / "evaluations").glob("*.json"):
            try:
                report = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if report.get("candidate_id", report.get("model_id")) == candidate_id:
                evaluations.append(path)
        if not evaluations:
            raise GatewayError("candidate has no evaluation artifact; evaluate it first")
        evaluation = max(evaluations, key=lambda path: path.stat().st_mtime_ns)
        output = self.repo_root / "artifacts" / "calibrations" / f"{candidate_id}-threshold-study-{uuid.uuid4().hex[:8]}.json"
        result = self.run_fixed(
            "model.generate_threshold_study",
            [
                str(self.python),
                "models/generate_threshold_study.py",
                "--candidate-id",
                candidate_id,
                "--evaluation",
                str(evaluation),
                "--candidate-metadata",
                str(metadata),
                "--out",
                str(output),
            ],
            timeout_seconds=120,
            job_id=job_id,
        )
        report = json.loads(output.read_text(encoding="utf-8"))
        result.update(
            {
                "candidate_id": candidate_id,
                "threshold_study_path": str(output.relative_to(self.repo_root)),
                "threshold_study_sha256": sha256_file(output),
                "target_feasible": report["target_feasible"],
                "active_model_changed": False,
            }
        )
        return result

    def active_pointer(self) -> dict[str, Any]:
        pointer_path = self.repo_root / "models" / "registry" / "active.json"
        if not pointer_path.exists():
            legacy = self.repo_root / "models" / "production"
            return {
                "schema_version": "1.0",
                "model_id": "legacy-production-directory",
                "bundle_path": "models/production",
                "metadata_sha256": sha256_file(legacy / "metadata.json"),
                "generation": 0,
                "source": "LEGACY_FALLBACK",
            }
        document = json.loads(pointer_path.read_text(encoding="utf-8"))
        bundle = (self.repo_root / document["bundle_path"]).resolve()
        if not bundle.is_relative_to(self.repo_root / "models") or not bundle.is_dir():
            raise GatewayError("active model pointer escapes the model registry")
        if sha256_file(bundle / "metadata.json") != document["metadata_sha256"]:
            raise GatewayError("active model metadata digest does not match the pointer")
        return {**document, "source": "REGISTRY_POINTER"}

    def resolve_active_model_dir(self) -> Path:
        pointer = self.active_pointer()
        return (self.repo_root / pointer["bundle_path"]).resolve()

    def _verified_promotable_bundle(self, model_id: str) -> tuple[Path, dict[str, Any]]:
        if not CANDIDATE_ID.fullmatch(model_id):
            raise GatewayError("model identifier is invalid")
        bundle = (self.repo_root / "models" / "candidates" / model_id).resolve()
        if not bundle.is_relative_to(self.repo_root / "models" / "candidates") or not bundle.is_dir():
            raise GatewayError("candidate bundle does not exist")
        metadata_path = bundle / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("model_id") != model_id:
            raise GatewayError("candidate metadata model_id mismatch")
        if metadata.get("deployment_status") not in {"APPROVED", "ACTIVE"}:
            raise GatewayError("candidate has not been assigned an approved deployment status")
        if metadata.get("promotion_eligible") is not True or metadata.get("performance_gate_passed") is not True:
            raise GatewayError("candidate is not promotion eligible and has not passed its performance gate")
        evaluation_ref = metadata.get("evaluation_artifact")
        evaluation_hash = metadata.get("evaluation_artifact_sha256")
        if not isinstance(evaluation_ref, str) or not isinstance(evaluation_hash, str):
            raise GatewayError("candidate lacks an immutable evaluation binding")
        evaluation = (self.repo_root / evaluation_ref).resolve()
        if not evaluation.is_relative_to(self.repo_root / "artifacts" / "evaluations") or sha256_file(evaluation) != evaluation_hash:
            raise GatewayError("candidate evaluation binding is invalid")
        report = json.loads(evaluation.read_text(encoding="utf-8"))
        report_model_id = report.get("model_id", report.get("candidate_id"))
        if report_model_id != model_id:
            raise GatewayError("bound evaluation report model identity does not match the candidate")
        if report.get("promotion_eligible") is not True or report.get("performance_gate_passed") is not True:
            raise GatewayError("bound evaluation report does not authorise promotion")
        threshold_policy = report.get("threshold_policy")
        threshold = metadata.get("fall_decision_threshold")
        if (
            not isinstance(threshold_policy, dict)
            or threshold_policy.get("performance_gate_passed") is not True
            or isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or threshold_policy.get("threshold") != threshold
        ):
            raise GatewayError("candidate threshold is not bound to a passing evaluation policy")
        for filename, expected in metadata.get("artifact_sha256", {}).items():
            path = bundle / filename
            if not path.is_file() or sha256_file(path) != expected:
                raise GatewayError(f"candidate artifact digest mismatch: {filename}")
        model_card = metadata.get("model_card")
        if not isinstance(model_card, str) or not (bundle / model_card).is_file():
            raise GatewayError("candidate lacks its required model card")
        return bundle, metadata

    def promote_model(self, model_id: str, expected_active_digest: str, *, actor_id: str, approval_binding: str) -> dict[str, Any]:
        self._require_operational()
        bundle, metadata = self._verified_promotable_bundle(model_id)
        current = self.active_pointer()
        if current["metadata_sha256"] != expected_active_digest:
            raise GatewayError("active model changed after preview; compare-and-swap refused")
        registry = self.repo_root / "models" / "registry"
        registry.mkdir(parents=True, exist_ok=True)
        pointer_path = registry / "active.json"
        history_dir = registry / "history"
        history_dir.mkdir(parents=True, exist_ok=True)
        if pointer_path.exists():
            previous = pointer_path.read_bytes()
            previous_name = f"generation-{int(current.get('generation', 0)):06d}-{current['metadata_sha256'][:12]}.json"
            (history_dir / previous_name).write_bytes(previous)
        pointer = {
            "schema_version": "1.0",
            "model_id": model_id,
            "bundle_path": str(bundle.relative_to(self.repo_root)),
            "metadata_sha256": sha256_file(bundle / "metadata.json"),
            "previous_metadata_sha256": current["metadata_sha256"],
            "generation": int(current.get("generation", 0)) + 1,
            "activated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "activated_by": actor_id,
            "approval_binding_sha256": approval_binding,
            "deployment_status": metadata.get("deployment_status"),
        }
        temporary = registry / f".active-{os.getpid()}-{uuid.uuid4().hex}.tmp"
        temporary.write_text(json.dumps(pointer, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, pointer_path)
        if self.active_pointer()["metadata_sha256"] != pointer["metadata_sha256"]:
            raise GatewayError("post-promotion pointer verification failed")
        return {"before": current, "after": pointer, "restart_required": True}

    def rollback_model(self, target_metadata_digest: str, expected_active_digest: str, *, actor_id: str, approval_binding: str) -> dict[str, Any]:
        self._require_operational()
        current = self.active_pointer()
        if current["metadata_sha256"] != expected_active_digest:
            raise GatewayError("active model changed after preview; rollback compare-and-swap refused")
        target: tuple[Path, dict[str, Any]] | None = None
        for location in [self.repo_root / "models" / "production", *sorted((self.repo_root / "models" / "candidates").glob("*"))]:
            metadata_path = location / "metadata.json"
            if metadata_path.is_file() and sha256_file(metadata_path) == target_metadata_digest:
                target = (location, json.loads(metadata_path.read_text(encoding="utf-8")))
                break
        if target is None:
            raise GatewayError("rollback target is not present in the immutable model catalog")
        bundle, metadata = target
        if metadata.get("deployment_status") not in {"APPROVED", "ACTIVE"}:
            raise GatewayError("rollback target is not a previously approved model bundle")
        registry = self.repo_root / "models" / "registry"
        registry.mkdir(parents=True, exist_ok=True)
        pointer = {
            "schema_version": "1.0",
            "model_id": metadata.get("model_id", bundle.name),
            "bundle_path": str(bundle.relative_to(self.repo_root)),
            "metadata_sha256": target_metadata_digest,
            "previous_metadata_sha256": current["metadata_sha256"],
            "generation": int(current.get("generation", 0)) + 1,
            "activated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "activated_by": actor_id,
            "approval_binding_sha256": approval_binding,
            "rollback": True,
        }
        temporary = registry / f".active-{os.getpid()}-{uuid.uuid4().hex}.tmp"
        temporary.write_text(json.dumps(pointer, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, registry / "active.json")
        return {"before": current, "after": pointer, "restart_required": True}

    def registered_tools(self) -> list[dict[str, Any]]:
        """The operations console registry; none accepts a command string."""

        return [
            {"tool_id": "host.snapshot", "display_name": "Host resource snapshot", "risk": "read_only", "parameters": {}},
            {"tool_id": "usrp.discover", "display_name": "Discover N210", "risk": "read_only", "parameters": {}},
            {"tool_id": "usrp.probe", "display_name": "Full stopped-state N210 probe", "risk": "disruptive_read", "parameters": {}},
            {"tool_id": "governance.validate", "display_name": "Validate governance stack", "risk": "read_only", "parameters": {}},
            {"tool_id": "tests.dashboard", "display_name": "Run dashboard test suite", "risk": "read_only", "parameters": {}},
        ]

    def execute_tool(self, tool_id: str) -> dict[str, Any]:
        if tool_id == "host.snapshot":
            process = psutil.Process()
            return {
                "tool_id": tool_id,
                "returncode": 0,
                "host": {
                    "cpu_percent": psutil.cpu_percent(interval=0.1, percpu=True),
                    "memory": psutil.virtual_memory()._asdict(),
                    "disk": psutil.disk_usage(str(self.repo_root))._asdict(),
                    "process_rss": process.memory_info().rss,
                },
            }
        if tool_id == "usrp.discover":
            return self.discover_usrp(full_probe=False)
        if tool_id == "usrp.probe":
            if (
                any(item["status"] == "RUNNING" for item in self.service_status().values())
                or self.external_service_status()
            ):
                raise GatewayError("full probe is only allowed while every managed or discovered pipeline process is stopped")
            return self.discover_usrp(full_probe=True)
        if tool_id == "governance.validate":
            return self.run_fixed(tool_id, [str(self.python), "tools/validate_instruction_stack.py"], timeout_seconds=60)
        if tool_id == "tests.dashboard":
            return self.run_fixed(tool_id, [str(self.python), "-m", "pytest", "-q", "tests/unit/test_control_plane.py"], timeout_seconds=180)
        raise GatewayError("unknown registered tool")
