# Control-plane threat model

Status: Draft STRIDE-oriented foundation; no security approval.

| Threat | Example | Required control | Verification |
|---|---|---|---|
| Spoofing | Unauthenticated HTTP/WebSocket client or fake sensor | Mutual/service authentication, user sessions, device inventory | Access-matrix and device-auth tests |
| Tampering | Model/config/log replacement | Digests, signatures, compare-and-swap, append-only audit | Tamper and rollback tests |
| Repudiation | Operator denies start, stop, promotion, export | Actor/correlation/approval/step audit chain | Audit completeness test |
| Information disclosure | Raw IQ, movement, identity, secret in UI/log/bundle | Minimisation, RBAC, TLS, redaction, separated linkage | Privacy and secret-scanning tests |
| Denial of service | Worker loss, queue flood, WebSocket hang, RF interference | Bounded queues/timeouts, supervision, cancellation, safe degradation | Recovery and fault-injection tests |
| Elevation of privilege | Natural language or API reaches shell/root/Docker | No shell, allowlisted action registry, dedicated identities, narrow helper | Command/prompt injection and peer-credential tests |

Additional safety-security interactions include RF start without approval, duplicate ownership,
wrong room/person association, model mismatch, stale telemetry, replayed requests, and approval
reuse after parameters change. G1A remains failed until executable controls and evidence exist.
