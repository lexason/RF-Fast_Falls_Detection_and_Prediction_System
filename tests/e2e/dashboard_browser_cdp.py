#!/usr/bin/env python3
"""Headless-browser acceptance for the CARAT operations dashboard.

The test starts an isolated simulation-only API, drives Chrome over its native
DevTools protocol, traverses every dashboard page, operates the safe lifecycle
controls, and exercises the interactive flowgraph inspector and dry-run rerun.
It never starts RF, reads raw IQ, promotes a model, or invokes arbitrary shell.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket


ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ".venv" / "bin" / "python"
CHROME = shutil.which("google-chrome") or shutil.which("chromium")
SECRET = "browser-acceptance-secret"
PANELS = [
    "Command centre", "Detection", "RF / USRP", "Flowgraph", "System health",
    "Model ops", "Data", "Clinical", "Maintenance", "Security & audit", "Agent desk",
]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_http(url: str, timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.1)
    raise AssertionError(f"server did not become ready: {url}")


class CDP:
    def __init__(self, url: str) -> None:
        self.socket = websocket.create_connection(url, timeout=10, origin="http://127.0.0.1")
        self.sequence = 0

    def command(self, method: str, params: dict | None = None) -> dict:
        self.sequence += 1
        request_id = self.sequence
        self.socket.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self.socket.recv())
            if message.get("id") == request_id:
                if "error" in message:
                    raise AssertionError(f"CDP {method} failed: {message['error']}")
                return message.get("result", {})

    def evaluate(self, expression: str):
        result = self.command(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        payload = result["result"]
        if payload.get("subtype") == "error":
            raise AssertionError(payload.get("description", "browser expression failed"))
        return payload.get("value")

    def wait(self, expression: str, timeout: float = 12) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.evaluate(expression):
                return
            time.sleep(0.1)
        raise AssertionError(f"browser condition timed out: {expression}")

    def click_text(self, selector: str, text: str) -> None:
        encoded_selector, encoded_text = json.dumps(selector), json.dumps(text)
        clicked = self.evaluate(
            f"""(() => {{ const target = [...document.querySelectorAll({encoded_selector})]
              .find(node => node.textContent.trim().includes({encoded_text}) && !node.disabled);
              if (!target) return false; target.click(); return true; }})()"""
        )
        if not clicked:
            raise AssertionError(f"enabled control not found: {selector} containing {text!r}")

    def close(self) -> None:
        self.socket.close()


def main() -> int:
    if not CHROME:
        raise AssertionError("Chrome/Chromium is required for browser acceptance")
    api_port, debug_port = free_port(), free_port()
    with tempfile.TemporaryDirectory(prefix="carat-dashboard-e2e-") as temporary:
        temp = Path(temporary)
        env = {
            **os.environ,
            "PYTHONPATH": str(ROOT),
            "RF_FALLS_DEV_AUTH_SECRET": SECRET,
            "RF_FALLS_EXECUTION_MODE": "simulation",
            "RF_FALLS_CONTROL_DB": str(temp / "control-plane.sqlite3"),
            "RF_FALLS_DASHBOARD_ACCESS": "loopback",
            "RF_FALLS_DASHBOARD_BIND_HOST": "127.0.0.1",
        }
        api_log = (temp / "api.log").open("w", encoding="utf-8")
        chrome_log = (temp / "chrome.log").open("w", encoding="utf-8")
        api = subprocess.Popen(
            [str(PYTHON), "-m", "uvicorn", "dashboard.app:app", "--host", "127.0.0.1", "--port", str(api_port)],
            cwd=ROOT, env=env, stdout=api_log, stderr=subprocess.STDOUT, text=True,
        )
        chrome: subprocess.Popen[str] | None = None
        client: CDP | None = None
        try:
            wait_http(f"http://127.0.0.1:{api_port}/")
            chrome = subprocess.Popen(
                [
                    CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
                    "--disable-dev-shm-usage", "--remote-allow-origins=*", "--no-proxy-server",
                    f"--remote-debugging-port={debug_port}", f"--user-data-dir={temp / 'chrome'}",
                    "about:blank",
                ],
                stdout=chrome_log, stderr=subprocess.STDOUT, text=True,
            )
            wait_http(f"http://127.0.0.1:{debug_port}/json/version")
            pages = json.load(urllib.request.urlopen(f"http://127.0.0.1:{debug_port}/json/list"))
            page = next(item for item in pages if item.get("type") == "page" and item.get("url") == "about:blank")
            client = CDP(page["webSocketDebuggerUrl"])
            client.command("Runtime.enable")
            client.evaluate(f"setTimeout(() => location.href={json.dumps(f'http://127.0.0.1:{api_port}/operations/')}, 0); true")
            client.wait(f"location.href.startsWith('http://127.0.0.1:{api_port}/operations')")
            client.evaluate(
                """window.__caratErrors=[];
                window.addEventListener('error', event => window.__caratErrors.push(String(event.error || event.message)));
                window.addEventListener('unhandledrejection', event => window.__caratErrors.push(String(event.reason)));"""
            )
            client.wait("!!document.querySelector('input[type=password]')")
            client.evaluate(
                f"""(() => {{ const input=document.querySelector('input[type=password]');
                Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,{json.dumps(SECRET)});
                input.dispatchEvent(new Event('input',{{bubbles:true}}));
                document.querySelector('form').requestSubmit(); }})()"""
            )
            client.wait("document.querySelectorAll('.sidebar nav button').length === 11")
            assert client.evaluate("document.body.textContent.includes('crypto.randomUUID is not a function')") is False

            for panel in PANELS:
                client.click_text(".sidebar nav button", panel)
                client.wait(f"document.querySelector('.topbar h1')?.textContent === {json.dumps(panel)}")
                assert client.evaluate("!document.querySelector('.toast.bad')")

            client.click_text(".sidebar nav button", "Flowgraph")
            client.wait("document.querySelectorAll('.flow-node').length === 8")
            node_count = client.evaluate("document.querySelectorAll('.flow-node').length")
            for index in range(node_count):
                client.evaluate(f"document.querySelectorAll('.flow-node')[{index}].click()")
                client.wait(f"document.querySelectorAll('.flow-node')[{index}].classList.contains('selected')")
            client.click_text("button", "Preview exact rerun")
            client.wait("document.querySelector('.toast')?.textContent.includes('DRY_RUN_COMPLETED')")

            client.click_text(".sidebar nav button", "Command centre")
            client.click_text("button", "Preflight")
            client.wait("document.querySelector('.toast')?.textContent.includes('preflight: COMPLETED')")
            client.click_text("button", "Start simulation")
            client.wait("document.querySelector('.toast')?.textContent.includes('start_detection: COMPLETED')")
            client.click_text("button", "Graceful stop")
            client.wait("document.querySelector('.toast')?.textContent.includes('stop_detection_gracefully: COMPLETED')")

            client.click_text(".sidebar nav button", "System health")
            client.click_text("button", "Run health check")
            client.wait("document.querySelector('.toast')?.textContent.includes('comprehensive_health_check: COMPLETED')")

            client.click_text(".sidebar nav button", "Maintenance")
            client.click_text("button", "Enter maintenance")
            client.wait("document.querySelector('.toast')?.textContent.includes('enter_maintenance: COMPLETED')")
            client.click_text("button", "Leave maintenance")
            client.wait("document.querySelector('.toast')?.textContent.includes('leave_maintenance: COMPLETED')")

            errors = client.evaluate("window.__caratErrors") or []
            assert not errors, f"browser errors: {errors}"
            assert client.evaluate("!document.querySelector('.toast.bad')")
            print(json.dumps({"status": "PASS", "panels": len(PANELS), "flowgraph_nodes": node_count, "browser_errors": 0}, sort_keys=True))
            return 0
        except Exception:
            api_log.flush(); chrome_log.flush()
            print((temp / "api.log").read_text(encoding="utf-8")[-4000:], file=sys.stderr)
            print((temp / "chrome.log").read_text(encoding="utf-8")[-4000:], file=sys.stderr)
            raise
        finally:
            if client:
                client.close()
            if chrome:
                chrome.terminate()
                try: chrome.wait(timeout=5)
                except subprocess.TimeoutExpired: chrome.kill()
            api.terminate()
            try: api.wait(timeout=5)
            except subprocess.TimeoutExpired: api.kill()
            api_log.close()
            chrome_log.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"dashboard browser acceptance FAILED: {exc}", file=sys.stderr)
        raise
