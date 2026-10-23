# Dashboard

The FastAPI application now exposes two deliberately separate products:

- `/operations` is the authenticated DEVELOPMENT operations dashboard. Its ten responsive panels
  provide typed simulation, replay, live-SDR, raw-capture, model-lifecycle, diagnostic, emergency,
  approval, cancellation, health, evidence, Explain/Plan, and hash-chained audit controls.
- `/monitor`, `/live`, and the session pages preserve the legacy silent research viewer.

The default adapter is operational. It launches only code-owned fixed argument vectors with
`shell=False`, minimal environment, closed stdin, bounded output/time, process-group supervision,
resource locks, RBAC, and audit. There is no arbitrary shell endpoint. Live RF, raw capture, model
promotion, and rollback are separate approval-bound workflows; raw sample bytes are never returned
to the browser. Simulation remains selectable with `RF_FALLS_EXECUTION_MODE=simulation`.

The gateway supervises repository processes directly on this development workstation. It does not
claim the host-wide isolation of a root-owned systemd/PolicyKit helper, production identity provider,
PostgreSQL queue, or append-only external audit store.

## Build the frontend

```bash
cd dashboard/frontend
npm install
npm run build
```

The compiled local assets are served from `dashboard/frontend/dist`; the UI has no CDN dependency.

## Run locally

The bootstrap secret and launch config live in a local `.env` file (gitignored; never commit it).
Create one once, then every future launch just sources it -- no regenerating a secret, no hunting
for the current value:

```bash
# One-time setup: pick your own real secret, not the literal placeholder text below.
cat > .env <<'EOF'
RF_FALLS_DEV_AUTH_SECRET=choose-a-real-secret-and-keep-it-here-not-in-this-file
RF_FALLS_EXECUTION_MODE=operational
EOF

# Every launch after that:
set -a; source .env; set +a
uvicorn dashboard.app:app --host 127.0.0.1 --port 18090
```

Open `http://127.0.0.1:18090/operations`. The bootstrap secret is read from the environment, never
stored in SQLite, and there is no unauthenticated fallback. For Tailscale access, `.env` also carries
`RF_FALLS_DASHBOARD_ACCESS=tailscale`, `RF_FALLS_DASHBOARD_BIND_HOST`, and `RF_FALLS_TAILSCALE_IPV4`
(the existing exact-IP bind and Origin controls described in the validation report); bind the server
to that same Tailscale IP, not `127.0.0.1`, when using them.

The actual secret value is never written here or anywhere else in the repository -- only in the
local, gitignored `.env` file, and handed to whoever operates the dashboard directly.

## Verify

```bash
.venv/bin/python -m pytest -q tests/unit/test_control_plane.py
npm --prefix dashboard/frontend run build
```

The production gaps are tracked in `docs/architecture/control_plane.md` and ADR 0003. Current
candidate evidence fails acceptance, so promotion is correctly unavailable. This dashboard is not
a clinically deployable or emergency-response system.
