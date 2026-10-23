"""Regression tests for the offline DEVELOPMENT proof-of-concept path."""

from __future__ import annotations

import asyncio
import importlib.util
import ipaddress
import json
import shutil
import struct
import subprocess
import sys
import uuid
from collections import deque
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from starlette.datastructures import URL

from dashboard import app as dashboard_app
from dsp.spectrogram_service import (
    IQ_MESSAGE_MAGIC,
    ClutterRemover,
    SourceSequenceTracker,
    decode_iq_chunk,
    decode_iq_message,
    doppler_frequencies,
)
from features.micro_doppler import window_features
from inference.model_runtime import ModelContractError, ProductionModel
from inference.posture_state_machine import PostureStateMachine
from inference.realtime_classifier import EventWindowQueue, _features_for_window, decode_spectrogram_frame
from models.build_dataset import remove_cross_label_overlap

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ".venv" / "bin" / "python"


def load_script(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_frozen_model_bundle_loads_and_scores_are_declared_uncalibrated():
    model = ProductionModel(ROOT / "models" / "production")
    assert model.model_id == "rf-sensing-falls-v3-legacy-baseline"
    assert model.quality_gate_passed is False
    assert model.score_kind == "uncalibrated_model_score_not_probability"
    features = {name: 0.0 for name in model.feature_names}
    label, score = model.classify_continuous(features)
    assert label in {"idle", "walk", "transient"}
    assert 0.0 <= score <= 1.0
    for session in (model.sess1, model.sess2):
        options = session.get_session_options()
        assert options.intra_op_num_threads == 1
        assert options.inter_op_num_threads == 1
        assert options.execution_mode.name == "ORT_SEQUENTIAL"


@pytest.mark.parametrize("directory", ["production_v4", "production_v5"])
def test_uncalibrated_staged_bundle_fails_at_startup(directory):
    with pytest.raises(ModelContractError, match="missing required fields|threshold"):
        ProductionModel(ROOT / "models" / directory)


def test_modified_model_artifact_fails_hash_check(tmp_path):
    source = ROOT / "models" / "production"
    metadata = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
    (tmp_path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (tmp_path / "stage1_idle_walk_transient.onnx").write_bytes(b"modified")
    (tmp_path / "stage2_transient_subclass.onnx").write_bytes(
        (source / "stage2_transient_subclass.onnx").read_bytes()
    )
    with pytest.raises(ModelContractError, match="hash mismatch"):
        ProductionModel(tmp_path)


def test_threshold_is_bound_to_hashed_evaluation_policy(tmp_path):
    repository = tmp_path / "repository"
    bundle = repository / "models" / "baseline"
    evaluation_dir = repository / "artifacts" / "evaluations"
    bundle.mkdir(parents=True)
    evaluation_dir.mkdir(parents=True)
    source = ROOT / "models" / "production"
    metadata = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
    metadata["fall_decision_threshold"] = 0.0004
    (bundle / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    for filename in ("stage1_idle_walk_transient.onnx", "stage2_transient_subclass.onnx"):
        shutil.copyfile(source / filename, bundle / filename)
    shutil.copyfile(
        ROOT / metadata["evaluation_artifact"],
        repository / metadata["evaluation_artifact"],
    )
    with pytest.raises(ModelContractError, match="does not match the bound evaluation policy"):
        ProductionModel(bundle)


def test_runtime_rejects_performance_claim_inflation(tmp_path):
    source = ROOT / "models" / "production"
    metadata = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
    metadata["performance_gate_passed"] = True
    (tmp_path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ModelContractError, match="promotion and performance gates must agree"):
        ProductionModel(tmp_path)


def test_event_waits_for_complete_training_window():
    queue = EventWindowQueue()
    pending = queue.add(10.0, 10.4)
    assert pending.window_t1 == pytest.approx(11.7)
    assert queue.ready(11.699) == []
    assert queue.ready(11.7) == [pending]


def test_sparse_or_edge_incomplete_frame_window_abstains():
    frequencies = np.linspace(-300, 300, 10, endpoint=False)
    magnitude = np.ones(10, dtype=np.float32)
    sparse = deque((timestamp, magnitude) for timestamp in (0.0, 0.05, 0.10, 0.15, 2.95))
    assert _features_for_window(sparse, frequencies, 5.8e9, 0.0, 3.0, None, None) is None
    late = deque((timestamp, magnitude) for timestamp in np.arange(0.5, 3.0, 0.05))
    assert _features_for_window(late, frequencies, 5.8e9, 0.0, 3.0, None, None) is None


def test_frame_contract_rejects_malformed_nonfinite_and_reordered_inputs():
    valid = np.asarray([12.5], dtype=np.float64).tobytes() + np.asarray([1.0, 2.0], dtype=np.float32).tobytes()
    timestamp, magnitude = decode_spectrogram_frame(valid, expected_bins=2)
    assert timestamp == 12.5
    assert magnitude.tolist() == [1.0, 2.0]
    with pytest.raises(ValueError):
        decode_spectrogram_frame(b"bad")
    invalid = np.asarray([np.nan], dtype=np.float64).tobytes() + np.asarray([1.0], dtype=np.float32).tobytes()
    with pytest.raises(ValueError):
        decode_spectrogram_frame(invalid)


def test_dsp_rejects_bad_iq_and_clutter_state_is_streaming():
    raw = np.asarray([1 + 2j, 3 + 4j], dtype=np.complex64).tobytes()
    decoded = decode_iq_chunk(raw)
    remover = ClutterRemover()
    assert remover.process(decoded).shape == (2,)
    with pytest.raises(ValueError):
        decode_iq_chunk(b"123")
    with pytest.raises(ValueError):
        decode_iq_chunk(np.asarray([complex(np.nan, 0)], dtype=np.complex64).tobytes())
    source_index, typed = decode_iq_message(IQ_MESSAGE_MAGIC + struct.pack("<Q", 123) + raw)
    assert source_index == 123
    assert np.array_equal(typed, decoded)


def test_dsp_sequence_gap_is_counted_and_zero_loss_policy_fails():
    tracker = SourceSequenceTracker()
    assert tracker.observe(0, 10) is False
    assert tracker.observe(10, 5) is False
    assert tracker.observe(20, 5) is True
    assert tracker.sequence_gaps == 1

    supervisor = load_script("offline_supervisor_health_module", "scripts/run_offline_poc.py")
    health = {
        "input_chunks": 3,
        "input_samples": 20,
        "frames_published": 4,
        "invalid_chunks": 0,
        "invalid_frames": 0,
        "sequence_gaps": tracker.sequence_gaps,
    }
    verdict = supervisor.evaluate_dsp_health(health, {"samples_sent": 20})
    assert verdict["policy_passed"] is False
    assert verdict["violations"] == ["sequence_gaps=1 exceeds zero-loss policy"]


def test_training_and_serving_share_exact_doppler_axis_and_features():
    sample_rate_hz = 250000.0
    nperseg = round(0.256 * sample_rate_hz)
    exact_axis = doppler_frequencies(sample_rate_hz)
    expected = (np.arange(len(exact_axis)) - len(exact_axis) / 2) * (sample_rate_hz / nperseg)
    assert np.array_equal(exact_axis, expected)

    times = np.arange(0.0, 3.0, 0.05)
    magnitudes = np.tile(np.linspace(0.0, 40.0, len(exact_axis), dtype=np.float32), (len(times), 1))
    frames = deque(zip(times, magnitudes))
    test_f0_hz = 5.8e9
    serving = _features_for_window(frames, exact_axis, test_f0_hz, 0.0, 3.0, 0.5, 1.0)
    training = window_features(magnitudes, expected, test_f0_hz, frame_times=times, event_t0=0.5, event_t1=1.0)
    assert serving is not None
    assert serving == pytest.approx(training, rel=0.0, abs=0.0)


def test_posture_starts_unknown_never_infers_absence_and_uses_candidate_semantics():
    machine = PostureStateMachine(now=100.0)
    assert machine.state == "unknown"
    heartbeat = machine.handle_message({"type": "heartbeat", "timestamp": 100.5}, wall_time=100.5)
    assert heartbeat == {
        "type": "heartbeat",
        "timestamp": 100.5,
        "event": "source_heartbeat",
        "state": "unknown",
        "research_score": None,
        "quality_status": "usable",
        "model_id": None,
        "model_performance_gate_passed": None,
        "score_kind": None,
        "operating_mode": None,
        "changed": False,
    }
    assert machine.handle_continuous("idle", 0.8, 101.0) is None
    assert machine.state == "unknown"
    walking = machine.handle_continuous("walk", 0.7, 102.0)
    assert walking["state"] == "walking_observed"
    stopped = machine.handle_continuous("idle", 0.6, 103.0)
    assert stopped["state"] == "static_posture_unknown"
    candidate = machine.handle_transient("fall", 0.55, 104.0)
    assert candidate["type"] == "fall_candidate"
    assert candidate["state"] == "fall_candidate"
    stale = machine.check_stale(104.9)
    assert stale is None
    stale = machine.check_stale(106.0)
    assert stale["state"] == "sensor_unavailable"
    assert "absent" not in json.dumps(stale)
    previous_liveness = machine.last_message_wall_time
    with pytest.raises(ValueError):
        machine.handle_message({"type": "unsupported", "timestamp": 110.0}, wall_time=110.0)
    assert machine.state == "sensor_unavailable"
    assert machine.last_message_wall_time == previous_liveness
    with pytest.raises(ValueError):
        machine.handle_message({"type": "heartbeat", "timestamp": float("nan")}, wall_time=110.0)
    assert machine.state == "sensor_unavailable"


def test_cross_label_raw_time_overlap_is_removed():
    specs = [
        (0.0, 3.0, "idle", None),
        (2.5, 5.5, "fall", (3.8, 4.2)),
        (6.0, 9.0, "walk", None),
        (6.5, 8.5, "walk", None),
    ]
    cleaned, excluded = remove_cross_label_overlap(specs)
    assert excluded == 2
    assert cleaned == specs[2:]


def test_pure_python_replay_stops_once_at_eof(tmp_path):
    replay = load_script("offline_replay_module", "scripts/replay.py")
    iq_path = tmp_path / "tiny.sigmf-data"
    iq_path.write_bytes(np.arange(10, dtype=np.complex64).tobytes())
    result = replay.replay_file(
        iq_path,
        10.0,
        f"inproc://replay-{uuid.uuid4()}",
        chunk_samples=3,
        speed=0,
        repeat=False,
        startup_delay_s=0,
    )
    assert result["samples_sent"] == 10
    assert result["cycles_completed"] == 1
    assert result["repeat"] is False


def test_dashboard_uses_configured_name_escapes_manifest_and_rejects_traversal(tmp_path, monkeypatch):
    session = tmp_path / "bad-session"
    session.mkdir()
    (session / "manifest.json").write_text(
        json.dumps(
            {
                "session_id": "<script>alert(1)</script>",
                "occupancy": "<img src=x onerror=alert(1)>",
                "room": "lab&room",
                "scripted_activity_timeline": [{"label": "<b>fall</b>"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard_app, "DATA_RAW", tmp_path)
    page = dashboard_app.index()
    assert dashboard_app.PROJECT_NAME in page
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "RF-FAST" not in page
    response = dashboard_app.session_detail("../escape")
    assert response.status_code == 400
    allowed = SimpleNamespace(
        headers={"origin": "http://127.0.0.1:18090"},
        url=URL("ws://127.0.0.1:18090/ws/activity"),
    )
    hostile = SimpleNamespace(
        headers={"origin": "https://attacker.example"},
        url=URL("ws://127.0.0.1:18090/ws/activity"),
    )
    assert dashboard_app._allowed_websocket_origin(allowed) is True
    assert dashboard_app._allowed_websocket_origin(hostile) is False


def test_dashboard_tailscale_mode_allows_only_tailnet_clients_and_exact_server_origin(monkeypatch):
    server_ip = ipaddress.ip_address("100.93.70.68")
    monkeypatch.setattr(dashboard_app, "ACCESS_MODE", "tailscale")
    monkeypatch.setattr(dashboard_app, "TAILSCALE_IPV4", server_ip)
    assert dashboard_app._allowed_client_host("100.113.107.21") is True
    assert dashboard_app._allowed_client_host("203.0.113.10") is False
    allowed = SimpleNamespace(
        headers={"origin": "http://100.93.70.68:18090"},
        url=URL("ws://100.93.70.68:18090/ws/activity"),
    )
    wrong_server = SimpleNamespace(
        headers={"origin": "http://100.113.107.21:18090"},
        url=URL("ws://100.93.70.68:18090/ws/activity"),
    )
    loopback_cross_host = SimpleNamespace(
        headers={"origin": "http://127.0.0.1:18090"},
        url=URL("ws://100.93.70.68:18090/ws/activity"),
    )
    assert dashboard_app._allowed_websocket_origin(allowed) is True
    assert dashboard_app._allowed_websocket_origin(wrong_server) is False
    assert dashboard_app._allowed_websocket_origin(loopback_cross_host) is False


def test_dashboard_tailscale_policy_rejects_non_tailnet_or_mismatched_bind(monkeypatch):
    monkeypatch.setattr(dashboard_app, "ACCESS_MODE", "tailscale")
    monkeypatch.setattr(dashboard_app, "TAILSCALE_IPV4_TEXT", "203.0.113.10")
    monkeypatch.setattr(dashboard_app, "DASHBOARD_BIND_HOST", "203.0.113.10")
    with pytest.raises(RuntimeError, match="100.64.0.0/10"):
        dashboard_app._validated_access_policy()
    monkeypatch.setattr(dashboard_app, "TAILSCALE_IPV4_TEXT", "100.93.70.68")
    with pytest.raises(RuntimeError, match="exact Tailscale-IP bind"):
        dashboard_app._validated_access_policy()


def test_websocket_bridge_cancels_when_client_disconnects():
    class FakeWebSocket:
        client = SimpleNamespace(host="127.0.0.1")
        headers = {"origin": "http://127.0.0.1:18090"}
        url = URL("ws://127.0.0.1:18090/ws/activity")

        async def accept(self):
            return None

        async def receive(self):
            return {"type": "websocket.disconnect"}

        async def send_text(self, _payload):
            raise AssertionError("no upstream message expected")

        async def close(self, **_kwargs):
            return None

    asyncio.run(
        asyncio.wait_for(
            dashboard_app._bridge_websocket(FakeWebSocket(), f"inproc://disconnect-{uuid.uuid4()}", binary=False),
            timeout=1.0,
        )
    )


def test_legacy_production_training_refuses_without_modifying_bundle():
    metadata = ROOT / "models" / "production" / "metadata.json"
    before = metadata.read_bytes()
    result = subprocess.run(
        [str(PYTHON), str(ROOT / "models" / "train_production.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "REFUSED" in result.stderr
    assert metadata.read_bytes() == before
    source = (ROOT / "models" / "train_production.py").read_text(encoding="utf-8")
    assert "FALL_THRESHOLD" not in source
    assert "mkdir" not in source


def test_supervisor_dry_run_is_bounded_loopback_and_hardware_free():
    result = subprocess.run(
        [str(PYTHON), str(ROOT / "scripts" / "run_offline_poc.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    plan = json.loads(result.stdout)
    assert plan["mode"] == "silent_research_poc"
    assert plan["network_policy"] == "loopback_only"
    assert plan["network_policy_scope"] == "internal_pipeline_only"
    assert plan["internal_pipeline_network_policy"] == "loopback_only"
    assert plan["performance_gate_passed"] is False
    assert plan["sample_rate_hz"] == 250000.0
    commands = json.dumps(plan["commands"]).lower()
    assert commands.count("--samp-rate") == 2
    for forbidden in ("uhd", "cw_doppler_tx_rx", "192.168.10.50", "0.0.0.0", "n210-sensing-bridge"):
        assert forbidden not in commands


def test_supervisor_tailscale_mode_exposes_only_dashboard_on_exact_tailnet_ip():
    result = subprocess.run(
        [
            str(PYTHON),
            str(ROOT / "scripts" / "run_offline_poc.py"),
            "--tailscale-dashboard-ip",
            "100.93.70.68",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    plan = json.loads(result.stdout)
    assert plan["network_policy"] == "loopback_only"
    assert plan["dashboard_access"] == "tailscale_only"
    assert plan["dashboard_bind_host"] == "100.93.70.68"
    dashboard = next(command for command in plan["commands"] if command["name"] == "dashboard")
    assert dashboard["argv"][dashboard["argv"].index("--host") + 1] == "100.93.70.68"
    assert dashboard["env"]["RF_FALLS_DASHBOARD_ACCESS"] == "tailscale"
    assert dashboard["env"]["RF_FALLS_TAILSCALE_IPV4"] == "100.93.70.68"
    non_dashboard = json.dumps([command for command in plan["commands"] if command["name"] != "dashboard"])
    assert "100.93.70.68" not in non_dashboard
    assert "0.0.0.0" not in json.dumps(plan)

    rejected = subprocess.run(
        [
            str(PYTHON),
            str(ROOT / "scripts" / "run_offline_poc.py"),
            "--tailscale-dashboard-ip",
            "203.0.113.10",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode != 0
    assert "100.64.0.0/10" in rejected.stderr


def test_authoritative_candidate_is_byte_reproducible_and_evaluation_is_bound():
    candidate = ROOT / "models" / "candidates" / "rf-sensing-falls-v6-dev-003"
    reproduction = ROOT / "models" / "candidates" / "rf-sensing-falls-v6-repro-check-2"
    metadata = json.loads((candidate / "metadata.json").read_text(encoding="utf-8"))
    evaluation = json.loads(
        (ROOT / "artifacts" / "evaluations" / "rf-sensing-falls-v6-dev-003-grouped-development-v3.json").read_text(
            encoding="utf-8"
        )
    )
    for filename, expected_hash in metadata["artifact_sha256"].items():
        assert (candidate / filename).read_bytes() == (reproduction / filename).read_bytes()
        assert evaluation["candidate_bundle"]["artifact_sha256"][filename] == expected_hash
    assert evaluation["promotion_eligible"] is False
    assert evaluation["performance_gate_passed"] is False
    assert evaluation["threshold_policy"] is None


def test_supervisor_refuses_dead_component_before_replay():
    supervisor = load_script("offline_supervisor_module", "scripts/run_offline_poc.py")
    dead = SimpleNamespace(poll=lambda: 7, returncode=7)
    with pytest.raises(RuntimeError, match="pipeline process exited early"):
        supervisor.assert_pipeline_alive([("classifier", dead, None)])


def test_supervisor_fails_if_component_dies_during_replay(monkeypatch):
    supervisor = load_script("offline_supervisor_monitor_module", "scripts/run_offline_poc.py")

    class SequencedProcess:
        def __init__(self, statuses):
            self.statuses = iter(statuses)
            self.last = None

        def poll(self):
            self.last = next(self.statuses, self.last)
            return self.last

    classifier = SequencedProcess([None, 9])
    replay = SequencedProcess([None, None, None])
    monkeypatch.setattr(supervisor.time, "sleep", lambda _seconds: None)
    with pytest.raises(RuntimeError, match="classifier.*9"):
        supervisor.wait_for_replay_or_child_exit(
            [("classifier", classifier, None), ("replay", replay, None)],
            poll_interval_s=0,
        )
