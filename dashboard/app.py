"""Local DEVELOPMENT dashboard for the RF Sensing Falls Project.

Preserves the session/results viewer and research waterfall while mounting the
G1A DEVELOPMENT operations dashboard. The operations control plane is typed,
authenticated, scope checked, audited, and backed by a fixed-argv local
operations gateway. Named controls cover replay/live SDR, bounded raw capture,
candidate jobs, promotion/rollback, diagnostics, and emergency stop. It never
accepts arbitrary shell text and does not emit a clinical alert.

Raw-IQ capture and server-side processing can be orchestrated, but sample bytes
are never served to the browser; only bounded inventory/integrity metadata is
returned.

Run:
    uvicorn dashboard.app:app --host 127.0.0.1 --port 18090
"""
import asyncio
import html
import ipaddress
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import zmq
import zmq.asyncio
import yaml
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from dashboard.control_plane import ControlPlane, create_router, websocket_events

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = REPO_ROOT / "data" / "raw"
FIGS_DIR = REPO_ROOT / "experiments" / "g1_pipeline_check" / "figs"
OPERATIONS_DIST = REPO_ROOT / "dashboard" / "frontend" / "dist"
SPECTROGRAM_ZMQ_ADDR = os.environ.get("RF_FALLS_SPECTROGRAM_ADDR", "tcp://127.0.0.1:5591")
ACTIVITY_ZMQ_ADDR = os.environ.get("RF_FALLS_ACTIVITY_ADDR", "tcp://127.0.0.1:5594")
ACCESS_MODE = os.environ.get("RF_FALLS_DASHBOARD_ACCESS", "loopback").strip().lower()
DASHBOARD_BIND_HOST = os.environ.get("RF_FALLS_DASHBOARD_BIND_HOST", "127.0.0.1").strip()
TAILSCALE_IPV4_TEXT = os.environ.get("RF_FALLS_TAILSCALE_IPV4", "").strip()
LOOPBACK_CLIENTS = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}
TAILSCALE_IPV4_NETWORK = ipaddress.ip_network("100.64.0.0/10")


def _validated_access_policy() -> ipaddress.IPv4Address | None:
    if ACCESS_MODE == "loopback":
        if DASHBOARD_BIND_HOST not in {"127.0.0.1", "::1"}:
            raise RuntimeError("loopback dashboard access requires a loopback bind host")
        return None
    if ACCESS_MODE != "tailscale":
        raise RuntimeError("dashboard access mode must be loopback or tailscale")
    try:
        tailscale_ip = ipaddress.ip_address(TAILSCALE_IPV4_TEXT)
    except ValueError as exc:
        raise RuntimeError("tailscale dashboard access requires a valid RF_FALLS_TAILSCALE_IPV4") from exc
    if not isinstance(tailscale_ip, ipaddress.IPv4Address) or tailscale_ip not in TAILSCALE_IPV4_NETWORK:
        raise RuntimeError("dashboard Tailscale address must be an IPv4 address in 100.64.0.0/10")
    if DASHBOARD_BIND_HOST != str(tailscale_ip):
        raise RuntimeError("tailscale dashboard access requires an exact Tailscale-IP bind")
    return tailscale_ip


TAILSCALE_IPV4 = _validated_access_policy()


def _is_loopback_endpoint(endpoint: str) -> bool:
    parsed = urlparse(endpoint)
    return parsed.scheme == "tcp" and parsed.hostname in {"127.0.0.1", "localhost", "::1"} and parsed.port is not None


def _allowed_client_host(client_host: str | None) -> bool:
    if client_host in LOOPBACK_CLIENTS:
        return True
    if ACCESS_MODE != "tailscale" or client_host is None:
        return False
    try:
        return ipaddress.ip_address(client_host) in TAILSCALE_IPV4_NETWORK
    except ValueError:
        return False


def _allowed_dashboard_hostname(hostname: str | None) -> bool:
    allowed = {"127.0.0.1", "localhost", "::1"}
    if TAILSCALE_IPV4 is not None:
        allowed.add(str(TAILSCALE_IPV4))
    return hostname in allowed


def _allowed_websocket_origin(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    if not origin:
        return False
    parsed = urlparse(origin)
    request_port = websocket.url.port or (443 if websocket.url.scheme == "wss" else 80)
    origin_port = parsed.port or (443 if parsed.scheme == "https" else 80)
    expected_origin_scheme = "https" if websocket.url.scheme == "wss" else "http"
    return (
        parsed.scheme == expected_origin_scheme
        and _allowed_dashboard_hostname(parsed.hostname)
        and _allowed_dashboard_hostname(websocket.url.hostname)
        and parsed.hostname == websocket.url.hostname
        and origin_port == request_port
    )


if not _is_loopback_endpoint(SPECTROGRAM_ZMQ_ADDR) or not _is_loopback_endpoint(ACTIVITY_ZMQ_ADDR):
    raise RuntimeError("research dashboard upstreams must use TCP loopback")

_project_config = yaml.safe_load((REPO_ROOT / "configs" / "project.yaml").read_text(encoding="utf-8"))
PROJECT_NAME = _project_config["project"]["display_name"]
PROJECT_ENVIRONMENT = _project_config["project"]["active_environment"]

app = FastAPI(title=f"{PROJECT_NAME} Research Dashboard")
app.mount("/figs", StaticFiles(directory=str(FIGS_DIR)), name="figs")
if OPERATIONS_DIST.exists():
    app.mount("/operations-assets", StaticFiles(directory=str(OPERATIONS_DIST)), name="operations-assets")
control_plane = ControlPlane.from_environment(REPO_ROOT)
app.include_router(create_router(control_plane))
_zmq_ctx = zmq.asyncio.Context()


@app.middleware("http")
async def dashboard_access_policy(request: Request, call_next):
    client_host = request.client.host if request.client else None
    if not _allowed_client_host(client_host) or not _allowed_dashboard_hostname(request.url.hostname):
        return JSONResponse({"detail": f"{ACCESS_MODE} DEVELOPMENT access only"}, status_code=403)
    return await call_next(request)

PAGE_STYLE = """
<style>
  body { font-family: -apple-system, sans-serif; max-width: 1000px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }
  h1 { border-bottom: 2px solid #333; padding-bottom: 0.5rem; }
  .session-card { border: 1px solid #ddd; border-radius: 8px; padding: 1rem 1.5rem; margin: 1rem 0; }
  .session-card a { text-decoration: none; color: #0b5fff; font-weight: 600; font-size: 1.1rem; }
  .badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.8rem; font-weight: 600; margin-left: 0.5rem; }
  .badge-synthetic { background: #ffe9b3; color: #7a5200; }
  .badge-real { background: #c8f7c5; color: #1a5c14; }
  table { border-collapse: collapse; width: 100%; margin: 0.75rem 0; }
  td, th { text-align: left; padding: 0.25rem 0.75rem 0.25rem 0; vertical-align: top; }
  th { color: #666; font-weight: 500; width: 180px; }
  img { max-width: 100%; border: 1px solid #ddd; border-radius: 4px; margin: 0.5rem 0; }
  .warn { background: #fff3cd; border: 1px solid #ffe69c; padding: 0.75rem 1rem; border-radius: 6px; margin: 1rem 0; }
  .back { display: inline-block; margin-bottom: 1rem; }
</style>
"""

LANDING_STYLE = """
<style>
  :root { color-scheme: dark; --bg:#06100f; --panel:#0d1d1a; --panel2:#102823; --line:rgba(220,242,235,.13); --ink:#edf5f2; --muted:#91a6a1; --green:#65d8a2; --amber:#efbd72; }
  * { box-sizing: border-box; }
  body { margin:0; min-height:100vh; color:var(--ink); background:radial-gradient(circle at 75% -20%,rgba(45,128,98,.28),transparent 38%),var(--bg); font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif; }
  .shell { width:min(1400px,calc(100% - 40px)); margin:0 auto; padding:28px 0 70px; }
  .top { display:flex; justify-content:space-between; align-items:center; padding:0 0 28px; }
  .brand { display:flex; align-items:center; gap:14px; }.mark { border:1px solid var(--line); border-radius:999px; padding:10px 13px; font:700 12px ui-monospace; letter-spacing:.15em; }.mark b { color:var(--green); }.brand strong,.brand small { display:block; }.brand small { color:var(--muted); margin-top:3px; }
  .status { display:flex; gap:9px; align-items:center; color:var(--muted); font-size:13px; }.dot { width:8px; height:8px; border-radius:50%; background:var(--amber); box-shadow:0 0 0 6px rgba(241,185,104,.09); }
  .hero { min-height:430px; display:grid; grid-template-columns:minmax(0,1.25fr) minmax(360px,.75fr); border:1px solid var(--line); border-radius:22px; overflow:hidden; background:linear-gradient(120deg,#123e32,#0b1a18 62%); }
  .hero-copy { padding:clamp(36px,6vw,86px); display:flex; flex-direction:column; justify-content:center; }.eyebrow { color:var(--green); font:700 11px ui-monospace; letter-spacing:.2em; text-transform:uppercase; }.hero h1 { font-size:clamp(48px,7vw,96px); line-height:.94; letter-spacing:-.065em; margin:22px 0; max-width:10ch; }.hero p { color:#bfd0cb; line-height:1.65; max-width:62ch; font-size:17px; }
  .actions { display:flex; flex-wrap:wrap; gap:11px; margin-top:24px; }.button { display:inline-flex; align-items:center; justify-content:center; gap:8px; min-height:48px; padding:0 18px; border:1px solid var(--line); border-radius:10px; color:var(--ink); text-decoration:none; background:#142723; font-weight:700; }.button.primary { color:#06100f; background:var(--green); border-color:var(--green); }.button:hover { transform:translateY(-1px); border-color:rgba(101,216,162,.65); }
  .hero-side { padding:26px; border-left:1px solid var(--line); display:grid; grid-template-columns:1fr 1fr; gap:12px; align-content:center; background:rgba(3,12,10,.25); }.metric { min-height:130px; padding:20px; border:1px solid var(--line); border-radius:14px; background:rgba(8,22,19,.72); }.metric span,.metric small { display:block; color:var(--muted); font-size:12px; }.metric strong { display:block; margin:13px 0 7px; font-size:clamp(22px,3vw,34px); overflow-wrap:anywhere; }
  .section { margin-top:30px; }.section-head { display:flex; justify-content:space-between; align-items:end; margin-bottom:14px; }.section h2 { margin:5px 0 0; font-size:28px; letter-spacing:-.035em; }.section-head p { color:var(--muted); margin:0; }
  .portal-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }.portal { min-height:210px; padding:24px; border:1px solid var(--line); border-radius:15px; background:var(--panel); text-decoration:none; color:var(--ink); transition:.18s ease; }.portal:hover { transform:translateY(-2px); background:var(--panel2); border-color:rgba(101,216,162,.42); }.portal .num { color:var(--green); font:700 11px ui-monospace; }.portal h3 { font-size:24px; margin:40px 0 9px; }.portal p { color:var(--muted); line-height:1.55; margin:0; }
  .sessions { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }.session { padding:18px; border:1px solid var(--line); border-radius:12px; background:rgba(13,29,26,.82); }.session a { color:var(--ink); text-decoration:none; font-weight:750; overflow-wrap:anywhere; }.session small { display:block; color:var(--muted); margin-top:12px; }.badge { display:inline-flex; margin-top:15px; padding:5px 8px; border-radius:999px; color:var(--green); border:1px solid rgba(101,216,162,.28); background:rgba(101,216,162,.08); font:700 10px ui-monospace; text-transform:uppercase; }
  .notice { margin-top:28px; padding:16px 18px; border:1px solid rgba(239,189,114,.24); border-radius:11px; color:#c9b893; background:rgba(239,189,114,.055); line-height:1.55; font-size:13px; }
  @media(max-width:900px){.hero{grid-template-columns:1fr}.hero-side{border-left:0;border-top:1px solid var(--line)}.portal-grid,.sessions{grid-template-columns:1fr 1fr}}
  @media(max-width:620px){.shell{width:min(100% - 24px,1400px)}.top{align-items:flex-start}.status{display:none}.hero-side,.portal-grid,.sessions{grid-template-columns:1fr}.hero-copy{padding:32px 24px}.hero h1{font-size:50px}}
</style>
"""


def load_sessions():
    sessions = []
    if not DATA_RAW.exists():
        return sessions
    for session_dir in sorted(DATA_RAW.iterdir(), reverse=True):
        manifest_path = session_dir / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(manifest, dict):
                continue
            manifest["_dir"] = session_dir.name
            sessions.append(manifest)
    return sessions


@app.get("/", response_class=HTMLResponse)
def index():
    sessions = load_sessions()
    real_count = sum(1 for item in sessions if not item.get("synthetic"))
    recent = []
    for item in sessions[:6]:
        session_dir = html.escape(str(item["_dir"]), quote=True)
        session_id = html.escape(str(item.get("session_id", item["_dir"])))
        kind = "synthetic" if item.get("synthetic") else "real capture"
        recent.append(
            f'<article class="session"><a href="/session/{session_dir}">{session_id}</a>'
            f'<small>Immutable local session manifest</small><span class="badge">{kind}</span></article>'
        )
    recent_html = "".join(recent) if recent else '<div class="session"><strong>No sessions yet</strong><small>Use the Data panel to request a bounded capture.</small></div>'
    safe_name = html.escape(PROJECT_NAME)
    safe_environment = html.escape(PROJECT_ENVIRONMENT)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark"><title>{safe_name} · Portal</title>{LANDING_STYLE}</head>
    <body><main class="shell">
      <header class="top"><div class="brand"><div class="mark">RF<b>·</b>SF</div><div><strong>{safe_name}</strong><small>Research operations portal</small></div></div><div class="status"><i class="dot"></i> Local-first research portal</div></header>
      <section class="hero"><div class="hero-copy"><span class="eyebrow">{safe_environment} · supervised operations</span><h1>One surface. Full control.</h1><p>Operate acquisition, replay, RF, data capture, model workflows, health, approvals and audit from a single authenticated command surface.</p><div class="actions"><a class="button primary" href="/operations">Open operations console →</a><a class="button" href="/monitor">View activity monitor</a></div></div>
      <div class="hero-side"><div class="metric"><span>Control adapter</span><strong>Fixed argv</strong><small>No arbitrary shell</small></div><div class="metric"><span>Environment</span><strong>{safe_environment}</strong><small>Authenticated access</small></div><div class="metric"><span>Local sessions</span><strong>{len(sessions)}</strong><small>{real_count} real captures</small></div><div class="metric"><span>Clinical mode</span><strong>Research</strong><small>No emergency alert claim</small></div></div></section>
      <section class="section"><div class="section-head"><div><span class="eyebrow">Workspaces</span><h2>Choose a control surface</h2></div><p>Purpose-built views, one local platform.</p></div><div class="portal-grid">
        <a class="portal" href="/operations"><span class="num">01 / OPERATE</span><h3>Operations console</h3><p>Command centre, live SDR, health, model and data controls, approvals, maintenance, security and registered tools.</p></a>
        <a class="portal" href="/monitor"><span class="num">02 / OBSERVE</span><h3>Activity monitor</h3><p>Live research state, event candidates and a bounded activity timeline from the local inference chain.</p></a>
        <a class="portal" href="/live"><span class="num">03 / INSPECT</span><h3>Micro-Doppler view</h3><p>Local spectral waterfall for signal and motion inspection without exposing raw-IQ sample files.</p></a>
      </div></section>
      <section class="section"><div class="section-head"><div><span class="eyebrow">Local evidence</span><h2>Recent sessions</h2></div><p><a class="button" href="/operations">Manage data</a></p></div><div class="sessions">{recent_html}</div></section>
      <div class="notice"><strong>Development research system.</strong> Controls are audited and bounded. Activity scores are not calibrated clinical probabilities, and this portal is not an emergency-response service.</div>
    </main></body></html>"""


@app.get("/session/{session_id}", response_class=HTMLResponse)
def session_detail(session_id: str):
    if Path(session_id).name != session_id:
        return HTMLResponse("<h1>Invalid session identifier</h1>", status_code=400)
    session_root = (DATA_RAW / session_id).resolve()
    if session_root.parent != DATA_RAW.resolve():
        return HTMLResponse("<h1>Invalid session identifier</h1>", status_code=400)
    manifest_path = session_root / "manifest.json"
    if not manifest_path.exists():
        return HTMLResponse(f"<h1>Session not found: {html.escape(session_id)}</h1>", status_code=404)
    try:
        s = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return HTMLResponse("<h1>Session manifest is invalid</h1>", status_code=422)

    safe_session_id = html.escape(session_id)

    def safe(value):
        return html.escape(str(value if value is not None else "N/A"))

    synthetic_warning = ""
    if s.get("synthetic"):
        synthetic_warning = f"""<div class="warn"><b>SYNTHETIC DATA.</b> {safe(s.get('synthetic_warning', 'Not a real capture.'))}</div>"""

    timeline_rows = "".join(
        f"<tr><td>{safe(seg.get('t_start'))}s - {safe(seg.get('t_end'))}s</td><td>{safe(seg.get('label'))}</td></tr>"
        for seg in s.get("scripted_activity_timeline", []) if isinstance(seg, dict)
    )

    psd_path = FIGS_DIR / f"{session_id}_psd.png"
    spec_path = FIGS_DIR / f"{session_id}_spectrogram.png"
    psd_html = f'<img src="/figs/{safe_session_id}_psd.png">' if psd_path.exists() else "<p><i>PSD plot not yet generated.</i></p>"
    spec_html = f'<img src="/figs/{safe_session_id}_spectrogram.png">' if spec_path.exists() else "<p><i>Spectrogram not yet generated.</i></p>"

    return f"""<!doctype html><html><head><title>{safe_session_id} -- {PROJECT_NAME}</title>{PAGE_STYLE}</head>
    <body>
    <a class="back" href="/">&larr; all sessions</a>
    <h1>{safe_session_id}</h1>
    {synthetic_warning}
    <table>
      <tr><th>Carrier</th><td>{safe(s.get('carrier_hz'))} Hz</td></tr>
      <tr><th>Sample rate</th><td>{safe(s.get('sample_rate_hz'))} sps</td></tr>
      <tr><th>TX / RX gain</th><td>{safe(s.get('tx_gain_db'))} dB / {safe(s.get('rx_gain_db'))} dB</td></tr>
      <tr><th>Antenna geometry</th><td>{safe(s.get('antenna_geometry'))}</td></tr>
      <tr><th>Occupancy</th><td>{safe(s.get('occupancy'))}</td></tr>
      <tr><th>Room</th><td>{safe(s.get('room'))}</td></tr>
    </table>
    <h2>Activity timeline</h2>
    <table>{timeline_rows}</table>
    <h2>Spectrogram</h2>
    {spec_html}
    <h2>PSD</h2>
    {psd_html}
    </body></html>"""


LIVE_PAGE = """<!doctype html><html><head><title>Local Waterfall -- __PROJECT_NAME__</title>""" + PAGE_STYLE + """
<style>
  #status { font-weight: 600; }
  #status.connected { color: #1a5c14; }
  #status.disconnected { color: #a30000; }
  canvas { border: 1px solid #ddd; border-radius: 4px; display: block; margin-top: 0.5rem; image-rendering: pixelated; }
</style>
</head>
<body>
<a class="back" href="/">&larr; all sessions</a>
<h1>Local Micro-Doppler Waterfall</h1>
<p>DEVELOPMENT view: local replay -&gt; DSP -&gt; WebSocket. This offline POC does not start or control RF
hardware. Research use only -- not a diagnostic or emergency-response tool.</p>
<p>Status: <span id="status" class="disconnected">connecting...</span> | Frames: <span id="framecount">0</span>
| FPS: <span id="fps">0</span></p>
<canvas id="waterfall" width="900" height="400"></canvas>
<script>
const canvas = document.getElementById('waterfall');
const ctx = canvas.getContext('2d');
ctx.fillStyle = '#00003f';
ctx.fillRect(0, 0, canvas.width, canvas.height);

let frameCount = 0;
let fpsWindow = [];

function dbToColor(v) {
  // v is normalized dB relative to the frame's own full-spectrum median.
  // Empirically (2026-07-18 live test) the +/-300Hz crop sits ~13-15dB above
  // that reference even at rest (clutter filter hasn't fully settled that
  // close to DC), with quiet periods ~20-25dB and active motion ~35-44dB --
  // so floor=15/ceil=42 is calibrated to that range, not 0-40.
  const FLOOR = 15.0, CEIL = 42.0;
  const t = Math.max(0, Math.min(1, (v - FLOOR) / (CEIL - FLOOR)));
  const r = Math.round(255 * t);
  const g = Math.round(255 * Math.pow(t, 0.7));
  const b = Math.round(80 * (1 - t) + 40);
  return `rgb(${r},${g},${b})`;
}

function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws/waterfall`);
  ws.binaryType = 'arraybuffer';

  ws.onopen = () => {
    document.getElementById('status').textContent = 'connected';
    document.getElementById('status').className = 'connected';
  };
  ws.onclose = () => {
    document.getElementById('status').textContent = 'disconnected -- retrying...';
    document.getElementById('status').className = 'disconnected';
    setTimeout(connect, 2000);
  };
  ws.onerror = () => ws.close();

  ws.onmessage = (event) => {
    const buf = event.data;
    const ts = new Float64Array(buf, 0, 1)[0];
    const mag = new Float32Array(buf, 8);
    const h = canvas.height;
    const nBins = mag.length;

    // Scroll existing image left by 1px, draw new column at the right edge.
    ctx.drawImage(canvas, 1, 0, canvas.width - 1, h, 0, 0, canvas.width - 1, h);
    for (let i = 0; i < h; i++) {
      const binIdx = Math.floor((i / h) * nBins);
      ctx.fillStyle = dbToColor(mag[nBins - 1 - binIdx]);  // flip so +freq is up
      ctx.fillRect(canvas.width - 1, i, 1, 1);
    }

    frameCount++;
    document.getElementById('framecount').textContent = frameCount;
    const now = performance.now();
    fpsWindow.push(now);
    fpsWindow = fpsWindow.filter(t => now - t < 1000);
    document.getElementById('fps').textContent = fpsWindow.length;
  };
}
connect();
</script>
</body></html>""".replace("__PROJECT_NAME__", html.escape(PROJECT_NAME))


@app.get("/live", response_class=HTMLResponse)
def live_view():
    return LIVE_PAGE


@app.get("/operations", response_class=FileResponse)
@app.get("/operations/", response_class=FileResponse)
def operations_view():
    """Serve the compiled local-first React operations dashboard."""
    index_path = OPERATIONS_DIST / "index.html"
    if not index_path.exists():
        return HTMLResponse(
            "<h1>Operations frontend is not built</h1><p>Run npm install and npm run build in dashboard/frontend.</p>",
            status_code=503,
        )
    return FileResponse(index_path)


@app.get("/healthz")
def healthz():
    """Process health only; upstream availability is intentionally not claimed."""
    return {
        "status": "ok",
        "project": PROJECT_NAME,
        "environment": PROJECT_ENVIRONMENT,
        "mode": "silent_research_poc",
        "access_policy": f"{ACCESS_MODE}_only",
        "bind_host": DASHBOARD_BIND_HOST,
        "upstreams": "not_asserted",
    }


async def _bridge_websocket(websocket: WebSocket, endpoint: str, binary: bool) -> None:
    """Bridge ZMQ with cancellation on either client disconnect or app shutdown."""
    client_host = websocket.client.host if websocket.client else None
    if not _allowed_client_host(client_host) or not _allowed_websocket_origin(websocket):
        await websocket.close(code=1008, reason=f"{ACCESS_MODE} DEVELOPMENT access only")
        return
    await websocket.accept()
    subscriber = _zmq_ctx.socket(zmq.SUB)
    subscriber.setsockopt(zmq.SUBSCRIBE, b"")
    subscriber.setsockopt(zmq.LINGER, 0)
    subscriber.connect(endpoint)
    zmq_task = asyncio.ensure_future(subscriber.recv() if binary else subscriber.recv_string())
    client_task = asyncio.create_task(websocket.receive())
    try:
        while True:
            done, _ = await asyncio.wait(
                {zmq_task, client_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if client_task in done:
                event = client_task.result()
                if event.get("type") == "websocket.disconnect":
                    break
                client_task = asyncio.create_task(websocket.receive())
            if zmq_task in done:
                payload = zmq_task.result()
                if binary:
                    await websocket.send_bytes(payload)
                    zmq_task = asyncio.ensure_future(subscriber.recv())
                else:
                    await websocket.send_text(payload)
                    zmq_task = asyncio.ensure_future(subscriber.recv_string())
    except (WebSocketDisconnect, asyncio.CancelledError, zmq.ZMQError):
        pass
    finally:
        for task in (zmq_task, client_task):
            task.cancel()
        await asyncio.gather(zmq_task, client_task, return_exceptions=True)
        subscriber.close(0)


@app.websocket("/ws/waterfall")
async def ws_waterfall(websocket: WebSocket):
    await _bridge_websocket(websocket, SPECTROGRAM_ZMQ_ADDR, binary=True)


MONITOR_PAGE = """<!doctype html><html><head><title>Research Monitor -- __PROJECT_NAME__</title>""" + PAGE_STYLE + """
<style>
  #status { font-weight: 600; }
  #status.connected { color: #1a5c14; }
  #status.disconnected { color: #a30000; }
  canvas { border: 1px solid #ddd; border-radius: 4px; display: block; margin-top: 0.5rem; image-rendering: pixelated; }
  .grid { display: grid; grid-template-columns: 1fr 340px; gap: 1.5rem; align-items: start; margin-top: 1rem; }
  .panel { border: 1px solid #ddd; border-radius: 8px; padding: 1rem 1.25rem; }
  #state-display { font-size: 2rem; font-weight: 700; text-align: center; padding: 1rem; border-radius: 8px;
    background: #eef2ff; color: #1e3a8a; transition: background 0.3s, color 0.3s; }
  #state-display.fall_candidate { background: #fee2e2; color: #991b1b; }
  #state-conf { text-align: center; color: #666; font-size: 0.85rem; margin-top: 0.25rem; }
  #fall-banner { display: none; background: #dc2626; color: white; padding: 1rem; border-radius: 8px;
    margin-top: 1rem; font-weight: 700; text-align: center; animation: pulse 1s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.7; } }
  #summary-table td { padding: 0.2rem 0.5rem 0.2rem 0; }
  #timeline { max-height: 260px; overflow-y: auto; font-size: 0.85rem; font-family: monospace; }
  #timeline div { padding: 0.15rem 0; border-bottom: 1px solid #f0f0f0; }
  .caveat { background: #fff3cd; border: 1px solid #ffe69c; padding: 0.6rem 0.9rem; border-radius: 6px;
    font-size: 0.85rem; margin-top: 1rem; }
</style>
</head>
<body>
<a class="back" href="/">&larr; all sessions</a> | <a class="back" href="/live">waterfall only</a>
<h1>__PROJECT_NAME__ Research Monitor</h1>
<p>Status: <span id="status" class="disconnected">connecting...</span></p>

<div class="grid">
  <div>
    <canvas id="waterfall" width="900" height="360"></canvas>
    <div id="fall-banner">PROBABLE FALL CANDIDATE -- <span id="fall-time"></span></div>
  </div>
  <div>
    <div class="panel">
      <div id="state-display">--</div>
      <div id="state-conf">research score: --</div>
    </div>
    <div class="panel" style="margin-top:1rem;">
      <h3 style="margin-top:0;">Today's summary</h3>
      <table id="summary-table">
        <tr><td>Fall candidates</td><td id="s-falls">0</td></tr>
        <tr><td>Transitions</td><td id="s-transitions">0</td></tr>
        <tr><td>Walking bouts</td><td id="s-walks">0</td></tr>
      </table>
    </div>
    <div class="panel" style="margin-top:1rem;">
      <h3 style="margin-top:0;">Activity timeline</h3>
      <div id="timeline"></div>
    </div>
  </div>
</div>
<div class="caveat">Silent DEVELOPMENT research POC only. Scores are uncalibrated and the fall-performance
gate failed (recall about 0.17 on a narrow, non-independent development set). This is not an alerting,
diagnostic, or emergency-response system. Timeline resets on page reload.</div>

<script>
const canvas = document.getElementById('waterfall');
const ctx = canvas.getContext('2d');
ctx.fillStyle = '#00003f';
ctx.fillRect(0, 0, canvas.width, canvas.height);

function dbToColor(v) {
  const FLOOR = 15.0, CEIL = 42.0;
  const t = Math.max(0, Math.min(1, (v - FLOOR) / (CEIL - FLOOR)));
  const r = Math.round(255 * t);
  const g = Math.round(255 * Math.pow(t, 0.7));
  const b = Math.round(80 * (1 - t) + 40);
  return `rgb(${r},${g},${b})`;
}

function connectWaterfall() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws/waterfall`);
  ws.binaryType = 'arraybuffer';
  ws.onopen = () => { document.getElementById('status').textContent = 'connected'; document.getElementById('status').className = 'connected'; };
  ws.onclose = () => { document.getElementById('status').textContent = 'disconnected -- retrying...'; document.getElementById('status').className = 'disconnected'; setTimeout(connectWaterfall, 2000); };
  ws.onerror = () => ws.close();
  ws.onmessage = (event) => {
    const buf = event.data;
    const mag = new Float32Array(buf, 8);
    const h = canvas.height, nBins = mag.length;
    ctx.drawImage(canvas, 1, 0, canvas.width - 1, h, 0, 0, canvas.width - 1, h);
    for (let i = 0; i < h; i++) {
      const binIdx = Math.floor((i / h) * nBins);
      ctx.fillStyle = dbToColor(mag[nBins - 1 - binIdx]);
      ctx.fillRect(canvas.width - 1, i, 1, 1);
    }
  };
}

let counts = { falls: 0, transitions: 0, walks: 0 };
let lastState = null;

function addTimelineRow(text) {
  const el = document.getElementById('timeline');
  const row = document.createElement('div');
  const now = new Date().toLocaleTimeString();
  row.textContent = `${now}  ${text}`;
  el.prepend(row);
  while (el.children.length > 200) el.removeChild(el.lastChild);
}

function connectActivity() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws/activity`);
  ws.onclose = () => setTimeout(connectActivity, 2000);
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    const stateEl = document.getElementById('state-display');
    stateEl.textContent = msg.state.toUpperCase();
    stateEl.className = msg.state === 'fall_candidate' ? 'fall_candidate' : '';
    document.getElementById('state-conf').textContent = msg.research_score != null
      ? `research score: ${msg.research_score.toFixed(3)} (not calibrated)` : 'research score: --';

    if (msg.type === 'fall_candidate') {
      counts.falls++;
      document.getElementById('s-falls').textContent = counts.falls;
      const banner = document.getElementById('fall-banner');
      banner.style.display = 'block';
      document.getElementById('fall-time').textContent = new Date().toLocaleTimeString();
      setTimeout(() => { banner.style.display = 'none'; }, 15000);
      addTimelineRow(`probable fall candidate (score ${msg.research_score.toFixed(3)})`);
    } else if (msg.changed) {
      counts.transitions++;
      document.getElementById('s-transitions').textContent = counts.transitions;
      if (msg.state === 'walking_observed' && lastState !== 'walking_observed') {
        counts.walks++;
        document.getElementById('s-walks').textContent = counts.walks;
      }
      addTimelineRow(`${msg.event} -> ${msg.state}`);
    }
    lastState = msg.state;
  };
}

connectWaterfall();
connectActivity();
</script>
</body></html>""".replace("__PROJECT_NAME__", html.escape(PROJECT_NAME))


@app.get("/monitor", response_class=HTMLResponse)
def monitor_view():
    return MONITOR_PAGE


@app.websocket("/ws/activity")
async def ws_activity(websocket: WebSocket):
    await _bridge_websocket(websocket, ACTIVITY_ZMQ_ADDR, binary=False)


@app.websocket("/api/v1/ws/events")
async def ws_control_events(websocket: WebSocket):
    client_host = websocket.client.host if websocket.client else None
    if not _allowed_client_host(client_host) or not _allowed_websocket_origin(websocket):
        await websocket.close(code=1008, reason=f"{ACCESS_MODE} DEVELOPMENT access only")
        return
    await websocket_events(control_plane, websocket)
