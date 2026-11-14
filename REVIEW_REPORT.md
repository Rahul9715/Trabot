# v2.0 Review Report

## Pass 1 — Functional/API
- FastAPI app import succeeded; application reports version 2.0.0.
- Python modules compile with `compileall`.
- Candidate create/decision endpoints were exercised through FastAPI TestClient.
- Paper close calculation checked with a deterministic example (2 shares, ₹10/share gross gain, ₹2.50 charges => ₹17.50 net).
- Daily loss reset verified to preserve cumulative P&L and leave autonomy disabled.
- Automated result: 5 backend tests passed.

## Pass 2 — Safety/risk
- No separate hard daily loss ceiling remains in the autonomy config schema.
- Daily loss lock is distinct from emergency kill switch.
- Reset changes the comparison baseline, preserves cumulative P&L, and does not re-enable autonomy.
- Live endpoint remains HTTP 501; no live orders can be sent by this release.
- Bot readiness includes audit-ledger availability.

## Pass 3 — Audit/security
- SHA-256 chain verified across multiple appended events.
- SQLite triggers reject ordinary UPDATE and DELETE statements on audit rows.
- Candidate decisions and trade lifecycle actions are represented as new events, not in-place audit edits.
- Sensitive OAuth tokens/secrets are not included in generic API request audit metadata.
- Known limitations: privileged local administrator can tamper with the database/file; hash anchoring is local only; audit writes are synchronous; runtime trading state is not fully durable; no independent external security review has occurred.

## Reviewer independence
These three passes were performed by the same assistant in separate functional, safety and audit/security review lenses. They are not three independent AI agents or human peers. External independent review remains a release gate.

## Not tested
- Frontend package install/build (dependency installation timed out in this environment). JSX syntax was separately transpiled with the locally installed TypeScript compiler and passed.
- Real Upstox market feed, OAuth, sandbox, broker fills, partial fills, order reconciliation, real-time exits, production latency, restart recovery, Windows installation, and funded/live trading.
