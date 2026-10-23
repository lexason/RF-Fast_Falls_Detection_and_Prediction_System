import React, { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Json = Record<string, any>;
type PanelId = "command" | "detection" | "rf" | "flowgraph" | "health" | "models" | "data" | "clinical" | "maintenance" | "security" | "chat";

const PANELS: Array<{ id: PanelId; label: string; eyebrow: string }> = [
  { id: "command", label: "Command centre", eyebrow: "01" },
  { id: "detection", label: "Detection", eyebrow: "02" },
  { id: "rf", label: "RF / USRP", eyebrow: "03" },
  { id: "flowgraph", label: "Flowgraph", eyebrow: "04" },
  { id: "health", label: "System health", eyebrow: "05" },
  { id: "models", label: "Model ops", eyebrow: "06" },
  { id: "data", label: "Data", eyebrow: "07" },
  { id: "clinical", label: "Clinical", eyebrow: "08" },
  { id: "maintenance", label: "Maintenance", eyebrow: "09" },
  { id: "security", label: "Security & audit", eyebrow: "10" },
  { id: "chat", label: "Agent desk", eyebrow: "11" },
];

const STATUS_CLASS: Record<string, string> = {
  RUNNING: "good", HEALTHY: "good", PASS: "good", COMPLETED: "good",
  STOPPED: "neutral", UNKNOWN: "neutral", DRY_RUN_COMPLETED: "neutral",
  DEGRADED: "warn", CONDITIONAL: "warn", PREFLIGHT: "warn", MAINTENANCE: "warn", AWAITING_APPROVAL: "warn",
  FAILED: "bad", FAIL: "bad", CANCELLED: "bad", ROLLED_BACK: "bad",
  UNMANAGED_RUNNING: "warn", UNMANAGED_CONFLICT: "bad",
};

function statusClass(value?: string) { return STATUS_CLASS[value || ""] || "neutral"; }
function fmtBytes(value?: number) {
  if (value == null) return "Unavailable";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let amount = value, i = 0;
  while (amount >= 1024 && i < units.length - 1) { amount /= 1024; i++; }
  return `${amount.toFixed(i > 1 ? 1 : 0)} ${units[i]}`;
}
function fmtTime(value?: string) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}
function shortHash(value?: string) { return value ? `${value.slice(0, 10)}…${value.slice(-6)}` : "—"; }
function makeKey(prefix: string) {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  const suffix = Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("");
  return `${prefix}-${suffix}`;
}

function Pill({ children, tone = "neutral" }: { children: React.ReactNode; tone?: string }) {
  return <span className={`pill ${tone}`}>{children}</span>;
}

function Metric({ label, value, note }: { label: string; value: React.ReactNode; note?: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong>{note && <small>{note}</small>}</div>;
}

function Empty({ children }: { children: React.ReactNode }) { return <div className="empty">{children}</div>; }

function App() {
  const [authConfig, setAuthConfig] = useState<Json | null>(null);
  const [actorId, setActorId] = useState("dev_admin");
  const [secret, setSecret] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [actor, setActor] = useState<Json | null>(null);
  const [panel, setPanel] = useState<PanelId>("command");
  const [state, setState] = useState<Json | null>(null);
  const [capabilities, setCapabilities] = useState<Json | null>(null);
  const [health, setHealth] = useState<Json | null>(null);
  const [flowgraph, setFlowgraph] = useState<Json | null>(null);
  const [workflows, setWorkflows] = useState<Json[]>([]);
  const [runs, setRuns] = useState<Json[]>([]);
  const [models, setModels] = useState<Json[]>([]);
  const [datasets, setDatasets] = useState<Json[]>([]);
  const [rawSessions, setRawSessions] = useState<Json[]>([]);
  const [tools, setTools] = useState<Json[]>([]);
  const [toolOutput, setToolOutput] = useState<Json | null>(null);
  const [audit, setAudit] = useState<Json[]>([]);
  const [auditIntegrity, setAuditIntegrity] = useState<Json | null>(null);
  const [activity, setActivity] = useState<Json | null>(null);
  const [eventStreamStatus, setEventStreamStatus] = useState<"connecting" | "connected" | "disconnected">("connecting");
  const [toast, setToast] = useState<{ tone: string; text: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [reason, setReason] = useState("Dashboard operational control requested");
  const [dryRun, setDryRun] = useState(false);
  const [chatMode, setChatMode] = useState("EXPLAIN");
  const [chatSession, setChatSession] = useState<string | null>(null);
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState<Array<{ role: string; body: any }>>([]);
  const lastSequence = useRef(0);
  const eventSocket = useRef<WebSocket | null>(null);

  useEffect(() => {
    fetch("/api/v1/auth/config").then(r => r.json()).then(setAuthConfig).catch(() => setAuthConfig({ enabled: false, users: [] }));
  }, []);

  const api = useCallback(async (path: string, options: RequestInit = {}) => {
    const headers = new Headers(options.headers || {});
    if (token) headers.set("Authorization", `Bearer ${token}`);
    if (options.body) headers.set("Content-Type", "application/json");
    const response = await fetch(`/api/v1${path}`, { ...options, headers });
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
    return body;
  }, [token]);

  const refresh = useCallback(async () => {
    if (!token) return;
    const requests = await Promise.allSettled([
      api("/platform/state"), api("/platform/capabilities"), api("/health"), api("/workflows"), api("/workflow-runs?limit=50"),
      api("/models"), api("/datasets"), api("/data/raw-sessions"), api("/audit/events?limit=200"), api("/audit/integrity"), api("/tools"), api("/flowgraph"),
    ]);
    const setters = [setState, setCapabilities, setHealth, setWorkflows, setRuns, setModels, setDatasets, setRawSessions, setAudit, setAuditIntegrity, setTools, setFlowgraph];
    requests.forEach((result, index) => { if (result.status === "fulfilled") setters[index](result.value as never); });
    const auditResult = requests[8];
    if (auditResult.status === "fulfilled" && Array.isArray(auditResult.value)) {
      lastSequence.current = Math.max(lastSequence.current, ...auditResult.value.map((item: Json) => item.sequence || 0));
    }
  }, [api, token]);

  useEffect(() => {
    refresh();
    if (!token) return;
    const timer = window.setInterval(refresh, 5000);
    return () => window.clearInterval(timer);
  }, [refresh, token]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setEventStreamStatus("connecting");
    async function connect() {
      try {
        const ticket = await api("/ws-ticket", { method: "POST" });
        if (cancelled) return;
        const proto = location.protocol === "https:" ? "wss" : "ws";
        const ws = new WebSocket(
          `${proto}://${location.host}/api/v1/ws/events?after=${lastSequence.current}`,
          ["carat.v1", `ticket.${ticket.ticket}`],
        );
        eventSocket.current = ws;
        ws.onopen = () => setEventStreamStatus("connected");
        ws.onmessage = event => {
          const item = JSON.parse(event.data);
          if (item.type === "stream.heartbeat") return;
          lastSequence.current = Math.max(lastSequence.current, item.sequence || 0);
          setAudit(previous => [item, ...previous.filter(existing => existing.event_id !== item.event_id)].slice(0, 200));
          if (item.type?.startsWith("workflow.")) refresh();
        };
        ws.onerror = () => setEventStreamStatus("disconnected");
        ws.onclose = () => { if (!cancelled) { setEventStreamStatus("disconnected"); window.setTimeout(connect, 1500); } };
      } catch { if (!cancelled) { setEventStreamStatus("disconnected"); window.setTimeout(connect, 2500); } }
    }
    connect();
    return () => { cancelled = true; eventSocket.current?.close(); };
  }, [api, refresh, token]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    function connect() {
      const ws = new WebSocket(`${proto}://${location.host}/ws/activity`);
      ws.onmessage = event => { try { setActivity(JSON.parse(event.data)); } catch { /* malformed legacy frame */ } };
      ws.onclose = () => { if (!cancelled) window.setTimeout(connect, 2500); };
    }
    connect();
    return () => { cancelled = true; };
  }, [token]);

  async function login(event: FormEvent) {
    event.preventDefault();
    try {
      const response = await fetch("/api/v1/auth/session", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ actor_id: actorId, bootstrap_secret: secret }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "Login failed");
      setToken(body.access_token); setActor(body.actor); setSecret("");
    } catch (error) { setToast({ tone: "bad", text: (error as Error).message }); }
  }

  async function logout() {
    try { await api("/auth/session", { method: "DELETE" }); } catch { /* local cleanup still applies */ }
    setToken(null); setActor(null); setState(null); setCapabilities(null); setHealth(null); setFlowgraph(null);
    setWorkflows([]); setRuns([]); setModels([]); setDatasets([]); setRawSessions([]); setTools([]);
    setToolOutput(null); setAudit([]); setAuditIntegrity(null); setActivity(null); setEventStreamStatus("connecting"); setChatSession(null); setChatMessages([]);
    eventSocket.current?.close();
  }

  async function runWorkflow(workflowId: string, parameters: Json = {}, options: Json = {}) {
    setBusy(workflowId);
    try {
      const body = {
        parameters,
        dry_run: options.dryRun ?? dryRun,
        confirmed: true,
        idempotency_key: makeKey(workflowId),
        reason: options.reason ?? reason,
        reference: options.reference ?? null,
      };
      const result = await api(`/workflows/${workflowId}/runs`, { method: "POST", body: JSON.stringify(body) });
      setToast({ tone: statusClass(result.status), text: `${workflowId}: ${result.status}` });
      await refresh();
      return result;
    } catch (error) { setToast({ tone: "bad", text: (error as Error).message }); }
    finally { setBusy(null); }
  }

  async function validateDataset(datasetId: string) {
    setBusy(`dataset-${datasetId}`);
    try {
      const result = await api(`/datasets/${encodeURIComponent(datasetId)}/validate`, { method: "POST" });
      setToast({ tone: statusClass(result.status), text: `${datasetId}: ${result.status}` }); await refresh();
    } catch (error) { setToast({ tone: "bad", text: (error as Error).message }); }
    finally { setBusy(null); }
  }

  async function approveRun(runId: string, decision = "approve") {
    setBusy(`approval-${runId}`);
    try {
      const result = await api(`/workflow-runs/${runId}/approve`, {
        method: "POST",
        body: JSON.stringify({ decision, reason: `${decision === "approve" ? "Independent approval" : "Rejection"} recorded from operations dashboard` }),
      });
      setToast({ tone: statusClass(result.status), text: `${result.workflow_id}: ${result.status}` });
      await refresh();
    } catch (error) { setToast({ tone: "bad", text: (error as Error).message }); }
    finally { setBusy(null); }
  }

  async function cancelRun(runId: string) {
    setBusy(`cancel-${runId}`);
    try {
      const result = await api(`/workflow-runs/${runId}/cancel`, { method: "POST" });
      setToast({ tone: statusClass(result.status), text: `${result.workflow_id}: ${result.status}` });
      await refresh();
    } catch (error) { setToast({ tone: "bad", text: (error as Error).message }); }
    finally { setBusy(null); }
  }

  async function executeTool(toolId: string) {
    setBusy(`tool-${toolId}`);
    try {
      const result = await api(`/tools/${encodeURIComponent(toolId)}/runs`, {
        method: "POST",
        body: JSON.stringify({ reason: reason || "Registered diagnostic requested from dashboard", reference: null }),
      });
      setToolOutput(result);
      setToast({ tone: "good", text: `${toolId}: completed` });
      await refresh();
    } catch (error) { setToast({ tone: "bad", text: (error as Error).message }); }
    finally { setBusy(null); }
  }

  async function startChat() {
    try {
      const result = await api("/chat/sessions", { method: "POST", body: JSON.stringify({ mode: chatMode }) });
      setChatSession(result.session_id); setChatMessages([]);
    } catch (error) { setToast({ tone: "bad", text: (error as Error).message }); }
  }

  async function sendChat(event: FormEvent) {
    event.preventDefault();
    if (!chatSession || !chatInput.trim()) return;
    const message = chatInput.trim(); setChatInput("");
    setChatMessages(previous => [...previous, { role: "user", body: message }]);
    try {
      const response = await api(`/chat/sessions/${chatSession}/messages`, { method: "POST", body: JSON.stringify({ message }) });
      setChatMessages(previous => [...previous, { role: "assistant", body: response }]);
    } catch (error) { setChatMessages(previous => [...previous, { role: "error", body: (error as Error).message }]); }
  }

  const latestEvaluation = useMemo(() => models.find(model => model.evaluation)?.evaluation, [models]);
  const allowed = useCallback((workflowId: string) => workflows.find(item => item.id === workflowId)?.available, [workflows]);
  const blocked = useCallback((workflowId: string) => {
    const workflow = workflows.find(item => item.id === workflowId);
    return workflow?.available ? undefined : workflow?.unavailable_reason || "Workflow metadata is not yet available";
  }, [workflows]);

  if (!token) {
    return <main className="login-shell">
      <section className="login-story">
        <div className="brand-mark">RF<span>·</span>SF</div>
        <p className="kicker">Operations control plane / Development</p>
        <h1>Know the state.<br />Control the workflow.<br /><em>Keep claims honest.</em></h1>
        <p className="lede">A local-first command surface for the RF Sensing Falls research platform. Every action is typed, scoped, idempotent and audited.</p>
        <div className="guardrail-grid">
          <span>Typed workflows</span><span>No arbitrary shell</span><span>Two-person RF</span><span>Atomic promotion</span>
        </div>
      </section>
      <section className="login-card" aria-labelledby="login-title">
        <p className="kicker">Restricted access</p><h2 id="login-title">Development sign in</h2>
        <p>Choose an explicit test identity. The shared bootstrap secret must be supplied through <code>RF_FALLS_DEV_AUTH_SECRET</code>.</p>
        <form onSubmit={login}>
          <label>Identity<select value={actorId} onChange={e => setActorId(e.target.value)}>
            {(authConfig?.users || []).map((user: Json) => <option key={user.actor_id} value={user.actor_id}>{user.display_name} · {user.role}</option>)}
          </select></label>
          <label>Bootstrap secret<input type="password" value={secret} onChange={e => setSecret(e.target.value)} autoComplete="current-password" /></label>
          <button className="button primary" type="submit" disabled={!authConfig?.enabled}>Enter operations</button>
        </form>
        {!authConfig?.enabled && <div className="callout warn">Authentication is not configured. Start the API with a development bootstrap secret; there is no insecure fallback.</div>}
        <p className="fine">This login is a development boundary, not a production identity provider.</p>
      </section>
      {toast && <Toast {...toast} onClose={() => setToast(null)} />}
    </main>;
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark small">RF<span>·</span>SF</div><div><strong>Operations</strong><small>Control plane v1</small></div></div>
      <nav aria-label="Operations panels">{PANELS.map(item => <button key={item.id} className={panel === item.id ? "active" : ""} onClick={() => setPanel(item.id)}><span>{item.eyebrow}</span>{item.label}</button>)}</nav>
      <div className="sidebar-foot"><Pill tone="warn">DEVELOPMENT</Pill><p>{actor?.display_name}<br /><small>{actor?.role}</small></p><button className="link-button" onClick={logout}>Sign out</button></div>
    </aside>
    <main className="workspace">
      <header className="topbar">
        <div><p className="kicker">{state?.project?.display_name || "RF Sensing Falls Project"}</p><h1>{PANELS.find(item => item.id === panel)?.label}</h1></div>
        <div className="top-status"><Pill tone={statusClass(state?.state)}>{state?.state || "LOADING"}</Pill><span className={`live-dot ${eventStreamStatus}`} /> <small>event stream {eventStreamStatus}</small></div>
      </header>
      <div className="constraint-bar"><strong>{capabilities?.execution_adapter || "Loading control adapter"}.</strong> Fixed argv only; RF, raw capture, and model activation remain approval-, scope-, state-, and lock-bound.</div>
      {panel === "command" && <CommandPanel state={state} capabilities={capabilities} runs={runs} reason={reason} setReason={setReason} dryRun={dryRun} setDryRun={setDryRun} busy={busy} allowed={allowed} blocked={blocked} run={runWorkflow} approve={approveRun} cancel={cancelRun} actor={actor} />}
      {panel === "detection" && <DetectionPanel activity={activity} state={state} audit={audit} evaluation={latestEvaluation} />}
      {panel === "rf" && <RfPanel health={health} capabilities={capabilities} tools={tools} busy={busy} allowed={allowed} blocked={blocked} run={runWorkflow} executeTool={executeTool} toolOutput={toolOutput} />}
      {panel === "flowgraph" && <FlowgraphPanel topology={flowgraph} state={state} busy={busy} allowed={allowed} blocked={blocked} run={runWorkflow} />}
      {panel === "health" && <HealthPanel health={health} state={state} busy={busy} allowed={allowed} blocked={blocked} run={runWorkflow} />}
      {panel === "models" && <ModelsPanel models={models} state={state} busy={busy} allowed={allowed} blocked={blocked} run={runWorkflow} />}
      {panel === "data" && <DataPanel datasets={datasets} rawSessions={rawSessions} busy={busy} allowed={allowed} blocked={blocked} validate={validateDataset} run={runWorkflow} />}
      {panel === "clinical" && <ClinicalPanel evaluation={latestEvaluation} />}
      {panel === "maintenance" && <MaintenancePanel state={state} runs={runs} reason={reason} setReason={setReason} busy={busy} allowed={allowed} blocked={blocked} run={runWorkflow} />}
      {panel === "security" && <SecurityPanel authConfig={authConfig} audit={audit} integrity={auditIntegrity} capabilities={capabilities} />}
      {panel === "chat" && <ChatPanel mode={chatMode} setMode={setChatMode} session={chatSession} start={startChat} reset={() => { setChatSession(null); setChatMessages([]); setChatInput(""); }} input={chatInput} setInput={setChatInput} send={sendChat} messages={chatMessages} tools={tools} executeTool={executeTool} toolOutput={toolOutput} busy={busy} />}
    </main>
    {toast && <Toast {...toast} onClose={() => setToast(null)} />}
  </div>;
}

function Toast({ tone, text, onClose }: { tone: string; text: string; onClose: () => void }) {
  useEffect(() => { const timer = window.setTimeout(onClose, 5000); return () => window.clearTimeout(timer); }, [onClose]);
  return <div className={`toast ${tone}`} role="status">{text}<button onClick={onClose} aria-label="Dismiss">×</button></div>;
}

function CommandPanel({ state, capabilities, runs, reason, setReason, dryRun, setDryRun, busy, allowed, blocked, run, approve, cancel, actor }: any) {
  const [replaySession, setReplaySession] = useState("2026-07-18_fall_gain5");
  const [txGain, setTxGain] = useState(0);
  const [rxGain, setRxGain] = useState(20);
  const [rfDuration, setRfDuration] = useState(300);
  const [reference, setReference] = useState("APPROVAL-REFERENCE-REQUIRED");
  const pending = runs.filter((item: Json) => item.status === "AWAITING_APPROVAL");
  return <div className="panel-flow">
    <section className="hero-card">
      <div><p className="kicker">Authoritative operational state</p><h2>{state?.state || "—"}</h2><p>{state?.mode || "—"} · {state?.project?.environment || "—"}</p></div>
      <div className="hero-metrics"><Metric label="RF workflow" value={capabilities?.rf_transmission ? "Available · approval gated" : "Unavailable"} /><Metric label="Control adapter" value={state?.privileged_helper_kind || "Simulation"} /><Metric label="Runtime model" value={state?.runtime_model_override || state?.active_model?.model_id || "—"} note={state?.runtime_model_override ? "Discovered legacy process override" : undefined} /></div>
    </section>
    <section className="card control-card"><div className="section-head"><div><p className="kicker">Primary controls</p><h2>Detection lifecycle</h2></div><label className="toggle"><input type="checkbox" checked={dryRun} onChange={e => setDryRun(e.target.checked)} /><span />Dry-run preview</label></div>
      <label>Operational reason<input value={reason} onChange={e => setReason(e.target.value)} /></label>
      <div className="button-grid">
        <Action label="Preflight" note="Config + health" disabledReason={blocked("preflight")} onClick={() => run("preflight", { profile: "simulation" })} disabled={!allowed("preflight") || !!busy} />
        <Action label="Start simulation" note="State-machine validation" disabledReason={blocked("start_detection")} onClick={() => run("start_detection", { profile: "simulation", replay_session: replaySession })} disabled={!allowed("start_detection") || !!busy} />
        <Action label="Start replay" note="Real DSP + inference services" disabledReason={blocked("start_detection") || (!capabilities?.operational_actions_enabled ? "Operational gateway is unavailable" : undefined)} tone="primary" onClick={() => run("start_detection", { profile: "replay", replay_session: replaySession })} disabled={!allowed("start_detection") || !capabilities?.operational_actions_enabled || !!busy} />
        <Action label="Graceful stop" note="SIGTERM, wait, then verify every service stopped" disabledReason={blocked("stop_detection_gracefully")} onClick={() => run("stop_detection_gracefully", { reason })} disabled={!allowed("stop_detection_gracefully") || !!busy} />
        <Action label="Emergency stop" note="Highest priority" disabledReason={blocked("emergency_stop")} tone="danger" onClick={() => run("emergency_stop", { reason })} disabled={!allowed("emergency_stop") || !!busy} />
      </div>
      <div className="split compact-controls"><label>Replay session<input value={replaySession} onChange={e => setReplaySession(e.target.value)} /></label><label>Approval / protocol reference<input value={reference} onChange={e => setReference(e.target.value)} /></label></div>
    </section>
    <section className="card control-card"><div className="section-head"><div><p className="kicker">Supervised RF</p><h2>Live SDR detection</h2></div><Pill tone="warn">Two approvers + timeout</Pill></div>
      <div className="form-grid"><label>TX gain dB<input type="number" min="0" max="15" value={txGain} onChange={e => setTxGain(Number(e.target.value))} /></label><label>RX gain dB<input type="number" min="0" max="35" value={rxGain} onChange={e => setRxGain(Number(e.target.value))} /></label><label>Automatic stop, seconds<input type="number" min="1" max="3600" value={rfDuration} onChange={e => setRfDuration(Number(e.target.value))} /></label></div>
      <button className="button danger" title={blocked("start_live_sdr")} disabled={!allowed("start_live_sdr") || !capabilities?.rf_transmission || !!busy} onClick={() => run("start_live_sdr", { profile_id: "lab_cw_2462", tx_gain_db: txGain, rx_gain_db: rxGain, maximum_duration_seconds: rfDuration }, { reference })}>Request live RF start</button>
      {blocked("start_live_sdr") && <p className="blocked-reason">{blocked("start_live_sdr")}</p>}
      <p className="fine">The request does not execute until two distinct non-requesters approve the exact workflow digest, parameters, RF-profile digest, reason, reference, environment, and expiry.</p>
    </section>
    {pending.length > 0 && <section className="card"><div className="section-head"><div><p className="kicker">Human control boundary</p><h2>Pending approvals</h2></div><Pill tone="warn">{pending.length}</Pill></div><div className="approval-list">{pending.map((item: Json) => <article key={item.run_id}><div><strong>{item.workflow_id}</strong><small>requested by {item.actor_id} · {item.approvals.length}/2 approvals</small><p>{item.reason} · {item.reference}</p></div><div className="button-row"><button className="button small" disabled={item.actor_id === actor?.actor_id || !!busy} onClick={() => approve(item.run_id, "approve")}>Approve exact request</button><button className="button small danger" disabled={item.actor_id === actor?.actor_id || !!busy} onClick={() => approve(item.run_id, "reject")}>Reject</button>{item.actor_id === actor?.actor_id && <button className="button small" disabled={!!busy} onClick={() => cancel(item.run_id)}>Cancel request</button>}</div></article>)}</div></section>}
    <section className="card"><div className="section-head"><div><p className="kicker">Recent execution</p><h2>Workflow ledger</h2></div><Pill>{runs.length} runs</Pill></div><RunTable runs={runs.slice(0, 8)} cancel={cancel} actor={actor} busy={busy} /></section>
  </div>;
}

function Action({ label, note, tone = "", disabledReason, ...props }: any) { return <div className="action-wrap"><button className={`action ${tone}`} title={disabledReason} {...props}><strong>{label}</strong><span>{note}</span></button>{props.disabled && disabledReason && <small className="blocked-reason">{disabledReason}</small>}</div>; }
function RunTable({ runs, cancel, actor, busy }: { runs: Json[]; cancel?: (id: string) => void; actor?: Json; busy?: string | null }) { return runs.length ? <div className="table-wrap"><table><thead><tr><th>Workflow</th><th>Status</th><th>Actor</th><th>When</th><th>Control</th></tr></thead><tbody>{runs.map(run => <tr key={run.run_id}><td><strong>{run.workflow_id}</strong><small>{shortHash(run.workflow_digest)}</small></td><td><Pill tone={statusClass(run.status)}>{run.status}</Pill></td><td>{run.actor_id}</td><td>{fmtTime(run.created_at_utc)}</td><td>{cancel && actor && ["QUEUED", "RUNNING"].includes(run.status) && (run.actor_id === actor.actor_id || actor.scopes?.includes("workflow:cancel_any")) ? <button className="button small" disabled={!!busy} onClick={() => cancel(run.run_id)}>Cancel</button> : "—"}</td></tr>)}</tbody></table></div> : <Empty>No workflow runs yet.</Empty>; }

function DetectionPanel({ activity, state, audit, evaluation }: any) {
  const recent = audit.filter((item: Json) => item.type?.includes("fall") || item.type?.includes("workflow")).slice(0, 12);
  return <div className="panel-flow"><section className="split hero-split"><div className="activity-state"><p className="kicker">Research activity stream</p><h2>{activity?.state?.replaceAll("_", " ") || "No current frame"}</h2><p>Research score {activity?.research_score != null ? Number(activity.research_score).toFixed(3) : "unavailable"}</p><a className="text-link" href="/monitor">Open legacy research monitor ↗</a></div><div className="card"><p className="kicker">Evidence boundary</p><h3>{evaluation?.status || "G3 remains failed"}</h3><p>Scores are not calibrated probabilities. No alert means neither “safe” nor monitored successfully.</p><Pill tone="bad">Clinical alerting disabled</Pill></div></section>
    <section className="metric-grid"><Metric label="Platform" value={state?.state || "—"} /><Metric label="Fall recall" value={evaluation?.threshold_policy?.recall != null ? `${(evaluation.threshold_policy.recall * 100).toFixed(1)}%` : "Unavailable"} note="Development, pooled grouped folds" /><Metric label="Specificity" value={evaluation?.threshold_policy?.specificity != null ? `${(evaluation.threshold_policy.specificity * 100).toFixed(1)}%` : "Unavailable"} /><Metric label="Fall windows" value={evaluation?.n_fall_windows ?? "—"} /></section>
    <section className="card"><div className="section-head"><div><p className="kicker">Typed event timeline</p><h2>Recent control and detection evidence</h2></div></div><EventList events={recent} /></section></div>;
}

function EventList({ events }: { events: Json[] }) { return events.length ? <div className="event-list">{events.map(item => <article key={item.event_id}><span className={`event-dot ${item.severity || "info"}`} /><div><strong>{item.type}</strong><p>{item.payload?.workflow_id || item.payload?.status || "Recorded event"}</p></div><time>{fmtTime(item.timestamp)}</time></article>)}</div> : <Empty>No matching events recorded.</Empty>; }

function RfPanel({ health, capabilities, tools, busy, allowed, blocked, run, executeTool, toolOutput }: any) {
  const usrp = health?.usrp;
  const id = usrp?.configured_identity || {}, runtime = usrp?.configured_runtime || {};
  const pipelineActive = (health?.services?.services || []).some((service: Json) => ["RUNNING", "UNMANAGED_RUNNING", "UNMANAGED_CONFLICT"].includes(service.status));
  return <div className="panel-flow"><section className="card warning-card"><div><p className="kicker">Truthful telemetry boundary</p><h2>Configured identity, not a live probe</h2><p>{usrp?.warning || "No live USRP adapter is connected."}</p></div><Pill tone="warn">{usrp?.status || "UNKNOWN"}</Pill></section>
    <section className="metric-grid"><Metric label="Motherboard" value={id.mboard || "—"} /><Metric label="Serial" value={id.serial || "—"} /><Metric label="FPGA / firmware" value={`${id.fpga_version || "—"} / ${id.firmware_version || "—"}`} /><Metric label="Daughterboard" value={id.daughterboard || "—"} /></section>
    <section className="split"><div className="card"><p className="kicker">Configured profile</p><dl className="definition-list"><dt>Carrier</dt><dd>{runtime.frequency_hz ? `${(runtime.frequency_hz / 1e9).toFixed(3)} GHz` : "—"}</dd><dt>Sample rate</dt><dd>{runtime.sample_rate_hz?.toLocaleString() || "—"} S/s</dd><dt>TX / RX port</dt><dd>{runtime.tx_port || "—"} / {runtime.rx_port || "—"}</dd><dt>Gains</dt><dd>{runtime.tx_gain_db ?? "unset"} / {runtime.rx_gain_db ?? "unset"} dB</dd></dl></div><div className="card"><p className="kicker">Unavailable on N210</p><ul className="plain-list"><li>CPU utilisation</li><li>RAM utilisation</li><li>Process list</li><li>Device filesystem</li></ul><p className="fine">The N210 is an FPGA radio peripheral, not a Linux host.</p></div></section>
    <section className="card"><div className="section-head"><div><p className="kicker">Registered RF tools</p><h2>Discovery, probe and stop</h2></div><Pill tone={capabilities?.usrp ? "good" : "warn"}>{capabilities?.usrp ? "Gateway ready" : "Unavailable"}</Pill></div><div className="button-row"><button className="button" title={!tools.some((item: Json) => item.tool_id === "usrp.discover") ? "Discovery tool is unavailable for this role or installation" : undefined} disabled={!tools.some((item: Json) => item.tool_id === "usrp.discover") || !!busy} onClick={() => executeTool("usrp.discover")}>Discover device</button><button className="button" title={pipelineActive ? "Stop the active pipeline before running a full hardware probe" : (!tools.some((item: Json) => item.tool_id === "usrp.probe") ? "Full probe requires the registered tool" : undefined)} disabled={pipelineActive || !tools.some((item: Json) => item.tool_id === "usrp.probe") || !!busy} onClick={() => executeTool("usrp.probe")}>Stopped-state full probe</button><button className="button danger" title={blocked("emergency_stop")} disabled={!allowed("emergency_stop") || !!busy} onClick={() => run("emergency_stop", { reason: "Emergency RF and detection stop requested from dashboard" })}>Emergency stop RF + pipeline</button></div>{pipelineActive && <p className="blocked-reason">Full probe is intentionally held until the active pipeline is stopped; device discovery and emergency stop remain available.</p>}{toolOutput?.tool_id?.startsWith("usrp.") && <pre className="tool-output">{toolOutput.stdout || toolOutput.stderr || JSON.stringify(toolOutput, null, 2)}</pre>}</section></div>;
}

function FlowgraphNode({ node, selected, onSelect }: { node: Json; selected: boolean; onSelect: () => void }) {
  return <button className={`flow-node ${selected ? "selected" : ""}`} onClick={onSelect} aria-pressed={selected}>
    <span className="flow-node-head"><span>{node.group === "GNU Radio top block" ? "GR" : "CARAT"}</span><Pill tone={statusClass(node.status)}>{node.status}</Pill></span>
    <strong>{node.label}</strong><small>{node.kind}</small>
  </button>;
}

function FlowConnector({ label }: { label: string }) { return <div className="flow-connector" aria-label={label}><span>{label}</span><b>→</b></div>; }

function FlowgraphPanel({ topology, state, busy, allowed, blocked, run }: any) {
  const nodes: Json[] = topology?.nodes || [];
  const byId = Object.fromEntries(nodes.map((node: Json) => [node.id, node]));
  const [selectedId, setSelectedId] = useState("usrp_sink");
  const [txGain, setTxGain] = useState(0);
  const [rxGain, setRxGain] = useState(20);
  const [duration, setDuration] = useState(300);
  const [reference, setReference] = useState("RF-FLOWGRAPH-CHANGE");
  const [changeReason, setChangeReason] = useState("Apply reviewed flowgraph parameters and restart the live SDR pipeline");
  const seeded = useRef(false);
  useEffect(() => {
    if (!topology || seeded.current) return;
    setTxGain(Number(topology.controls?.tx_gain_db ?? 0));
    setRxGain(Number(topology.controls?.rx_gain_db ?? 20));
    setDuration(Number(topology.controls?.maximum_duration_seconds ?? 300));
    seeded.current = true;
  }, [topology]);

  const selected = byId[selectedId] || nodes[0];
  const edgeLabel = (from: string, to: string) => topology?.edges?.find((edge: Json) => edge.from === from && edge.to === to)?.label || "data";
  const rerunParameters = { profile_id: topology?.profile_id || "lab_cw_2462", tx_gain_db: txGain, rx_gain_db: rxGain, maximum_duration_seconds: duration, reason: changeReason };
  const unavailable = blocked("rerun_live_sdr");
  if (!topology) return <Empty>Loading the deployed flowgraph and runtime observations…</Empty>;

  return <div className="panel-flow">
    <section className="flowgraph-intro">
      <div><p className="kicker">Executable topology · {topology.runtime_supervision?.replaceAll("_", " ")}</p><h2>{topology.title}</h2><p>{topology.implementation}. Select any block to inspect its exact runtime contract.</p></div>
      <div className="flow-provenance"><Pill tone={state?.state === "RUNNING" ? "good" : "warn"}>{state?.state || "UNKNOWN"}</Pill><span>Profile <strong>{topology.profile_id}</strong></span><span>Source <code>{topology.source}</code></span><span>Code <code>{shortHash(topology.source_sha256)}</code></span></div>
    </section>

    <section className="card flowgraph-canvas" aria-label="CARAT GNU Radio and inference flowgraph">
      <div className="section-head"><div><p className="kicker">Transmit branch</p><h3>Constant-wave sensing excitation</h3></div><Pill tone="warn">RF output · controlled</Pill></div>
      <div className="flow-lane tx-lane">
        <FlowgraphNode node={byId.constant_source} selected={selectedId === "constant_source"} onSelect={() => setSelectedId("constant_source")} />
        <FlowConnector label={edgeLabel("constant_source", "usrp_sink")} />
        <FlowgraphNode node={byId.usrp_sink} selected={selectedId === "usrp_sink"} onSelect={() => setSelectedId("usrp_sink")} />
        <div className="rf-field"><span>RF</span><strong>2.462 GHz field</strong><small>TX/RX → room → RX2</small></div>
      </div>
      <div className="flow-divider" />
      <div className="section-head"><div><p className="kicker">Receive and decision branch</p><h3>IQ to typed research evidence</h3></div><Pill>{nodes.length} blocks</Pill></div>
      <div className="flow-lane rx-lane">
        {(["usrp_source", "zmq_iq_pub", "spectrogram", "classifier", "state_machine", "dashboard_streams"] as string[]).map((id, index, sequence) => <React.Fragment key={id}>
          <FlowgraphNode node={byId[id]} selected={selectedId === id} onSelect={() => setSelectedId(id)} />
          {index < sequence.length - 1 && <FlowConnector label={edgeLabel(id, sequence[index + 1])} />}
        </React.Fragment>)}
      </div>
      <div className="branch-note"><span />The waterfall also branches directly from clutter/STFT processing to the dashboard; activity frames arrive through the state machine.</div>
    </section>

    <section className="flow-control-layout">
      <article className="card block-inspector">
        <p className="kicker">Selected element</p><h2>{selected?.label || "Select a block"}</h2><p>{selected?.description}</p><div className="block-kind"><code>{selected?.kind}</code><Pill tone={statusClass(selected?.status)}>{selected?.status}</Pill></div>
        <div className="parameter-list">{selected?.parameters?.length ? selected.parameters.map((parameter: Json) => {
          const current = parameter.id === "tx_gain_db" ? txGain : parameter.id === "rx_gain_db" ? rxGain : parameter.value;
          const update = parameter.id === "tx_gain_db" ? setTxGain : parameter.id === "rx_gain_db" ? setRxGain : undefined;
          return <div className="parameter-row" key={parameter.id}><div><strong>{parameter.label}</strong><small>{parameter.editable ? "Editable · applied through full graph restart" : parameter.reason}</small></div>{parameter.editable && update ? <label className="inline-number"><input aria-label={parameter.label} type="number" min={parameter.minimum} max={parameter.maximum} step={parameter.step || 1} value={current} onChange={event => update(Number(event.target.value))} /><span>{parameter.unit}</span></label> : <code>{String(current)}{parameter.unit ? ` ${parameter.unit}` : ""}</code>}</div>;
        }) : <Empty>This element exposes status and provenance only; it has no independent runtime knobs.</Empty>}</div>
      </article>

      <article className="card rerun-console">
        <div className="section-head"><div><p className="kicker">GRC-style parameter application</p><h2>Validate, approve, rerun</h2></div><Pill tone="warn">Two-person RF</Pill></div>
        <p>Changes are applied coherently to the complete graph. The workflow stops the existing graph, revalidates the exact profile and hardware, starts all blocks, and arms an automatic timeout.</p>
        <div className="form-grid flow-settings"><label>TX gain, dB<input type="number" min="0" max="15" value={txGain} onChange={event => setTxGain(Number(event.target.value))} /></label><label>RX gain, dB<input type="number" min="0" max="35" value={rxGain} onChange={event => setRxGain(Number(event.target.value))} /></label><label>Automatic stop, seconds<input type="number" min="1" max="3600" value={duration} onChange={event => setDuration(Number(event.target.value))} /></label></div>
        <label>Operational reason<input value={changeReason} onChange={event => setChangeReason(event.target.value)} /></label><label>Approval / protocol reference<input value={reference} onChange={event => setReference(event.target.value)} /></label>
        <div className="button-row"><button className="button" disabled={!allowed("rerun_live_sdr") || !!busy} title={unavailable} onClick={() => run("rerun_live_sdr", rerunParameters, { dryRun: true, reason: changeReason, reference })}>Preview exact rerun</button><button className="button primary" disabled={!allowed("rerun_live_sdr") || !!busy || changeReason.trim().length < 10 || !reference.trim()} title={unavailable} onClick={() => run("rerun_live_sdr", rerunParameters, { dryRun: false, reason: changeReason, reference })}>Request apply &amp; rerun</button><button className="button danger" disabled={!allowed("emergency_stop") || !!busy} title={blocked("emergency_stop")} onClick={() => run("emergency_stop", { reason: "Emergency stop requested from flowgraph console" })}>Emergency stop</button></div>
        {unavailable && <p className="blocked-reason">{unavailable}</p>}<p className="fine">The requester cannot approve their own change. Centre frequency, sample rate, endpoints and feature geometry stay locked because changing them would invalidate hardware, DSP and model contracts; their lock reason is shown on the selected block.</p>
      </article>
    </section>
  </div>;
}

function HealthPanel({ health, state, busy, allowed, blocked, run }: any) {
  const host = health?.host, services = health?.services?.services || [];
  return <div className="panel-flow"><section className="section-head standalone"><div><p className="kicker">Observed {fmtTime(health?.collected_at_utc)}</p><h2>Host and service health</h2></div><button className="button" title={blocked("comprehensive_health_check")} disabled={!allowed("comprehensive_health_check") || !!busy} onClick={() => run("comprehensive_health_check", { profile: "simulation" }, { reason: null })}>Run health check</button></section>
    <section className="metric-grid"><Metric label="Overall" value={<Pill tone={statusClass(health?.overall_status)}>{health?.overall_status || "—"}</Pill>} /><Metric label="Memory" value={host ? `${host.memory.percent}%` : "—"} note={host ? `${fmtBytes(host.memory.available_bytes)} available` : undefined} /><Metric label="Disk" value={host ? `${host.disk.percent}%` : "—"} note={host ? `${fmtBytes(host.disk.free_bytes)} free` : undefined} /><Metric label="CPU availability" value={host ? `${host.cpu.available_cpus} / ${host.cpu.logical_cpus}` : "—"} /></section>
    <section className="split"><div className="card"><p className="kicker">Managed and discovered services</p><div className="service-list">{services.map((service: Json) => <div key={service.service_id}><span>{service.service_id.replaceAll("_", " ")}<small>{service.mode?.replaceAll("_", " ").toLowerCase()}</small></span><Pill tone={statusClass(service.status)}>{service.status}</Pill></div>)}</div></div><div className="card"><p className="kicker">Resource detail</p><dl className="definition-list"><dt>Host</dt><dd>{host?.subject_id || "—"}</dd><dt>Load average</dt><dd>{host?.cpu?.load_average?.map((v: number) => v.toFixed(2)).join(" · ") || "—"}</dd><dt>API process RSS</dt><dd>{fmtBytes(host?.process?.rss_bytes)}</dd><dt>Network received</dt><dd>{fmtBytes(host?.network?.bytes_recv)}</dd><dt>Temperature</dt><dd>{host?.temperature_c != null ? `${host.temperature_c.toFixed(1)} °C` : "Unavailable"}</dd></dl></div></section>
    <p className="fine">Platform state {state?.state || "—"}. Host metrics come from the workstation; service status combines the supervisor registry with exact repository-process discovery. N210-only fields remain explicitly separate.</p></div>;
}

function ModelsPanel({ models, state, busy, allowed, blocked, run }: any) {
  const manifest = "artifacts/datasets/legacy-development-snapshot-v3.json";
  const [candidateId, setCandidateId] = useState(() => `dashboard-candidate-${new Date().toISOString().slice(0, 10).replaceAll("-", "")}-${makeKey("id").slice(-6)}`);
  const candidates = models.filter((model: Json) => model.location?.startsWith("models/candidates/"));
  const selected = candidates.find((model: Json) => model.model_id === candidateId);
  const activeDigest = state?.active_model?.metadata_sha256;
  const evaluateReason = blocked("evaluate_candidate") || (!selected ? "Select an existing trained candidate before evaluation" : undefined);
  const studyReason = blocked("recalibrate_candidate") || (!selected?.evaluation ? "Evaluate the selected candidate before generating a threshold study" : undefined);
  return <div className="panel-flow">
    <section className="card">
      <div className="section-head"><div><p className="kicker">Candidate lifecycle</p><h2>Train, evaluate, study, approve, activate</h2></div><Pill>{models.length} records</Pill></div>
      <div className="form-grid">
        <label>New / selected candidate ID<input value={candidateId} onChange={e => setCandidateId(e.target.value)} /></label>
        <label>Existing candidate<select value={selected ? candidateId : ""} onChange={e => setCandidateId(e.target.value)}><option value="">Choose a trained candidate</option>{candidates.map((model: Json) => <option key={model.model_id} value={model.model_id}>{model.model_id}</option>)}</select></label>
      </div>
      <div className="button-row">
        <button className="button" title={blocked("train_candidate_model")} disabled={!allowed("train_candidate_model") || !!busy} onClick={() => run("train_candidate_model", { candidate_id: candidateId, dataset_manifest: manifest })}>Train immutable candidate</button>
        <button className="button" title={evaluateReason} disabled={!allowed("evaluate_candidate") || !selected || !!busy} onClick={() => run("evaluate_candidate", { candidate_id: candidateId, dataset_manifest: manifest })}>Evaluate selected candidate</button>
        <button className="button" title={studyReason} disabled={!allowed("recalibrate_candidate") || !selected?.evaluation || !!busy} onClick={() => run("recalibrate_candidate", { candidate_id: candidateId })}>Generate threshold study</button>
      </div>
      {(blocked("train_candidate_model") || evaluateReason || studyReason) && <p className="blocked-reason">{blocked("train_candidate_model") || evaluateReason || studyReason}</p>}
      <p className="fine">Training, evaluation and threshold study generation never change the active pointer. Promotion remains a separate compare-and-swap workflow with two independent approvers.</p>
    </section>
    <section className="model-grid">{models.map((model: Json) => {
      const modelId = model.model_id || model.candidate_id;
      const promotable = model.promotion_eligible && model.performance_gate_passed && !model.active;
      const rollbackTarget = !model.active && ["APPROVED", "ACTIVE"].includes(model.deployment_status);
      return <article className={`card model-card ${model.active ? "active-model" : ""}`} key={modelId}>
        <div className="section-head"><Pill tone={model.active ? "good" : model.performance_gate_passed ? "good" : "bad"}>{model.active ? "ACTIVE" : model.deployment_status || model.status}</Pill><small>{model.location || "simulation record"}</small></div>
        <h3>{modelId}</h3><p>{model.score_semantics || "Candidate lifecycle record"}</p>
        <dl className="definition-list compact"><dt>Promotion eligible</dt><dd>{String(model.promotion_eligible ?? false)}</dd><dt>Performance gate</dt><dd>{String(model.performance_gate_passed ?? false)}</dd><dt>Metadata</dt><dd>{shortHash(model.metadata_sha256)}</dd></dl>
        {model.evaluation && <div className="evaluation-strip"><span>{model.evaluation.status}</span><strong>AUROC {model.evaluation.discrimination?.auroc?.toFixed(3) ?? model.evaluation.fall_transient_subset?.auroc?.toFixed(3) ?? "—"}</strong></div>}
        <details className="model-details"><summary>Review evidence and controls</summary>{model.limitations?.length ? <ul className="plain-list">{model.limitations.map((item: string) => <li key={item}>{item}</li>)}</ul> : <p>No additional limitations were recorded.</p>}
          <div className="button-row">
            {promotable && <button className="button small" title={blocked("promote_model")} disabled={!allowed("promote_model") || !activeDigest || !!busy} onClick={() => run("promote_model", { model_id: modelId, expected_active_digest: activeDigest }, { reference: "MODEL-CHANGE-APPROVAL" })}>Request promotion</button>}
            {rollbackTarget && <button className="button small" title={blocked("rollback_model")} disabled={!allowed("rollback_model") || !activeDigest || !!busy} onClick={() => run("rollback_model", { approved_model_digest: model.metadata_sha256, expected_active_digest: activeDigest, reason: "Restore previously approved model from dashboard" }, { reference: "MODEL-ROLLBACK-APPROVAL" })}>Request rollback</button>}
            {!promotable && !rollbackTarget && <p className="blocked-reason">No activation action is valid: this record has not passed and been approved for deployment.</p>}
          </div>
        </details>
      </article>;
    })}</section>
  </div>;
}

function DataPanel({ datasets, rawSessions, busy, allowed, blocked, validate, run }: any) {
  const [sessionId, setSessionId] = useState(`dashboard_capture_${new Date().toISOString().replaceAll(/[-:.TZ]/g, "").slice(0, 14)}`);
  const [activityClass, setActivityClass] = useState("idle");
  const [duration, setDuration] = useState(30);
  return <div className="panel-flow"><section className="card"><div className="section-head"><div><p className="kicker">Raw-IQ orchestration</p><h2>Capture on the approved workstation</h2></div><Pill tone="warn">Two-person approval</Pill></div><div className="form-grid"><label>Immutable session ID<input value={sessionId} onChange={e => setSessionId(e.target.value)} /></label><label>Activity class<select value={activityClass} onChange={e => setActivityClass(e.target.value)}><option>idle</option><option>walk</option><option>sit_stand</option><option>lie_down</option><option>fall</option><option>empty_room</option></select></label><label>Duration, seconds<input type="number" min="1" max="600" value={duration} onChange={e => setDuration(Number(e.target.value))} /></label></div><button className="button primary" title={blocked("capture_raw_iq")} disabled={!allowed("capture_raw_iq") || !!busy} onClick={() => run("capture_raw_iq", { session_id: sessionId, activity_class: activityClass, duration_seconds: duration, note: "Dashboard-controlled approved raw-IQ capture", occupancy: "approved research protocol", room: "configured laboratory" }, { reference: "DATA-COLLECTION-PROTOCOL" })}>Request bounded capture</button>{blocked("capture_raw_iq") && <p className="blocked-reason">{blocked("capture_raw_iq")}</p>}<p className="fine">Raw samples remain local. The browser receives inventory, size, timing and integrity metadata—not IQ payload bytes.</p></section>
    <section className="section-head standalone"><div><p className="kicker">Derived data</p><h2>Processed datasets</h2></div><Pill>{datasets.reduce((sum: number, item: Json) => sum + (item.rows || 0), 0).toLocaleString()} windows</Pill></section><section className="dataset-grid">{datasets.map((dataset: Json) => <article className="card" key={dataset.dataset_id}><div className="section-head"><Pill tone={dataset.status === "INVALID" ? "bad" : "neutral"}>{dataset.status}</Pill><small>{fmtBytes(dataset.size_bytes)}</small></div><h3>{dataset.dataset_id}</h3><p>{dataset.rows?.toLocaleString() || "—"} rows · {dataset.columns?.length || 0} columns · {dataset.row_groups || 0} row groups</p><p className="mono">{shortHash(dataset.sha256)}</p><button className="button small" disabled={busy === `dataset-${dataset.dataset_id}`} onClick={() => validate(dataset.dataset_id)}>Run structure audit</button></article>)}</section>
    <section className="card"><div className="section-head"><div><p className="kicker">Authorised local inventory</p><h2>{rawSessions.length} raw sessions</h2></div></div>{rawSessions.length ? <div className="table-wrap"><table><thead><tr><th>Session</th><th>Class</th><th>Size</th><th>Duration</th></tr></thead><tbody>{rawSessions.slice(-40).reverse().map((item: Json) => <tr key={item.session_id}><td><strong>{item.session_id}</strong><small>{shortHash(item.manifest_sha256)}</small></td><td>{item.activity_class || "legacy / unspecified"}</td><td>{fmtBytes(item.raw_bytes)}</td><td>{item.duration_s != null ? `${item.duration_s.toFixed(1)}s` : "—"}</td></tr>)}</tbody></table></div> : <Empty>Raw inventory requires the data:raw_read scope.</Empty>}</section></div>;
}

function ClinicalPanel({ evaluation }: any) { return <div className="panel-flow"><section className="clinical-hero"><p className="kicker">Clinical risk & decision support</p><h2>Unavailable by design</h2><p>This repository has no validated Product C risk model, no approved patient context and no operational clinical alert pathway. The panel abstains instead of fabricating a risk score.</p><Pill tone="bad">Not clinically deployable</Pill></section><section className="split"><div className="card"><p className="kicker">What the evidence supports</p><ul className="check-list"><li>Silent, local engineering replay</li><li>Derived activity research visualisation</li><li>Candidate-model comparison with explicit limitations</li><li>Configuration and provenance inspection</li></ul></div><div className="card"><p className="kicker">What remains prohibited</p><ul className="cross-list"><li>Diagnostic or emergency-response use</li><li>“Safe” status from no recent event</li><li>Calibrated individual fall risk</li><li>Treatment or care recommendations</li></ul></div></section><section className="card"><p className="kicker">Latest Product A evidence</p><h3>{evaluation?.status || "Unavailable"}</h3><p>{evaluation?.intended_use || "No evaluation artifact loaded."}</p><div className="metric-grid inset"><Metric label="AUROC" value={evaluation?.discrimination?.auroc?.toFixed(3) || "—"} /><Metric label="AUPRC" value={evaluation?.discrimination?.auprc?.toFixed(3) || "—"} /><Metric label="Fall windows" value={evaluation?.n_fall_windows ?? "—"} /></div></section></div>; }

function MaintenancePanel({ state, runs, reason, setReason, busy, allowed, blocked, run }: any) {
  return <div className="panel-flow"><section className="split"><div className="card"><p className="kicker">State discipline</p><h2>{state?.state || "—"}</h2><p>Maintenance blocks detection start and records every transition.</p><label>Change reason<input value={reason} onChange={e => setReason(e.target.value)} /></label><div className="button-row"><button className="button" title={blocked("enter_maintenance")} disabled={!allowed("enter_maintenance") || !!busy} onClick={() => run("enter_maintenance")}>Enter maintenance</button><button className="button" title={blocked("leave_maintenance")} disabled={!allowed("leave_maintenance") || !!busy} onClick={() => run("leave_maintenance")}>Leave maintenance</button></div><p className="blocked-reason">{blocked("enter_maintenance") || blocked("leave_maintenance")}</p></div><div className="card"><p className="kicker">Deployment boundary</p><ul className="plain-list"><li>local fixed-argv gateway: enabled by configuration</li><li>supervision includes exact discovery of legacy pipeline processes</li><li>long local jobs: asynchronous and cancellable</li><li>workflow locks and approvals: durable in local SQLite</li><li>arbitrary shell and unregistered commands: intentionally absent</li></ul></div></section><section className="card"><p className="kicker">Workflow provenance</p><RunTable runs={runs.slice(0, 12)} /></section></div>;
}

function SecurityPanel({ authConfig, audit, integrity, capabilities }: any) { return <div className="panel-flow"><section className="metric-grid"><Metric label="Audit chain" value={<Pill tone={statusClass(integrity?.status)}>{integrity?.status || "—"}</Pill>} note={`${integrity?.events_checked ?? 0} events checked`} /><Metric label="Authentication" value="Dev bootstrap" note="Production IdP not configured" /><Metric label="Operations console" value={capabilities?.registered_operations_console ? "Registered tools" : "Unavailable"} /><Metric label="Arbitrary shell" value="Blocked" /></section><section className="split"><div className="card"><p className="kicker">Development RBAC</p><div className="user-list">{authConfig?.users?.map((user: Json) => <article key={user.actor_id}><div><strong>{user.display_name}</strong><small>{user.actor_id}</small></div><Pill>{user.role}</Pill><p>{user.scopes.join(" · ")}</p></article>)}</div></div><div className="card"><p className="kicker">Hash-chained audit</p><p className="mono wrap">Head {integrity?.head_hash || "—"}</p><EventList events={audit.slice(0, 12)} /></div></section></div>; }

function ChatPanel({ mode, setMode, session, start, reset, input, setInput, send, messages, tools, executeTool, toolOutput, busy }: any) { return <div className="chat-layout"><section className="chat-main card"><div className="section-head"><div><p className="kicker">Controlled agent desk</p><h2>{mode === "EXPLAIN" ? "Explain observed state" : "Plan a named workflow"}</h2></div><div className="button-row">{session && <button className="button small" onClick={reset}>New session</button>}<select value={mode} onChange={e => setMode(e.target.value)} disabled={!!session}><option>EXPLAIN</option><option>PLAN</option></select></div></div><div className="chat-transcript">{messages.length ? messages.map((message: Json, index: number) => <article key={index} className={message.role}><strong>{message.role}</strong>{typeof message.body === "string" ? <p>{message.body}</p> : <><p>{message.body.answer}</p>{message.body.resolved_workflow && <Pill>{message.body.resolved_workflow}</Pill>}{message.body.steps && <ol>{message.body.steps.map((step: Json) => <li key={step.id}>{step.id} · {step.action}</li>)}</ol>}</>}</article>) : <Empty>Start a session. Chat explains and plans named workflows; execution stays in explicit workflow controls.</Empty>}</div>{session ? <form className="chat-form" onSubmit={send}><input value={input} onChange={e => setInput(e.target.value)} placeholder="Ask about state, health, start, stop or model workflows…" /><button className="button primary" disabled={!input.trim()}>Send</button></form> : <button className="button primary" onClick={start}>Start {mode.toLowerCase()} session</button>}</section><aside className="card terminal-card"><p className="kicker">Registered operations console</p><div className="terminal"><span>$</span> select a registered tool<span className="cursor" /></div><p>Each tool has fixed argv, no stdin, a finite timeout, bounded output, role checks, and an audit record.</p><div className="tool-buttons">{tools.map((tool: Json) => <button className="button small" key={tool.tool_id} disabled={!!busy} onClick={() => executeTool(tool.tool_id)}>{tool.display_name}</button>)}</div>{toolOutput && <pre className="tool-output">{toolOutput.stdout || toolOutput.stderr || JSON.stringify(toolOutput, null, 2)}</pre>}<Pill tone="good">Registered operations ready</Pill></aside></div>; }

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
