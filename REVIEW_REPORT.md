# v2.0 Review Report

## Unreleased dashboard and startup controls
- Added regression coverage that startup and day rollover leave the kill switch released while the bot remains stopped.
- Added exact `I AGREE` phrase validation; a test confirms live order submission still returns HTTP 501 even when configured activation flags and acknowledgement are supplied.
- Added report charts/filters and separate intelligence navigation. The report view uses only closed trades in the current runtime and does not claim durable or statistically validated performance.
- Validation: 16 backend tests passed; Python compile succeeded; Vite production build succeeded. Vite reports the large-bundle warning and lucide module-directive warnings.
- No independent human or external reviewer has reviewed this change. Live routing, strategy scheduling, performance, and funded-account operation remain unvalidated.

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

## Follow-up repository review — multi-asset research scope

- The current order-validation path requires a daily strategy approval, but no API route writes `state.approval`; as checked, paper and sandbox order submissions therefore fail validation.
- No background scanner or strategy scheduler generates candidates. Candidate creation is an API input, and a dashboard approval does not create an order.
- The market-data adapter subscribes to Upstox instrument keys; there is no global equity or commodity feed, market-hours/calendar layer, or cross-venue contract metadata.
- There is no backtest/forward-test dataset or calibrated performance record. A 90–100% win-rate target cannot be supported or verified from this repository.
- The research enhancement adds scope controls and source provenance, but does not change order execution or turn research output into a signal.
- This follow-up is a code inspection only; no automated tests or build were run for these changes.

## Release 2.1.0 implementation review

- Added provider adapters for OpenAI, Anthropic, Gemini, NVIDIA NIM and OpenAI-compatible chat-completions APIs. Provider-grounding support differs; ungrounded adapters do not claim search capability, and readiness still requires sources.
- Added daily Excel mirrors for candidate lifecycle records; the audit hash-chain remains canonical. Candidate expiry is evaluated on reads/decisions and therefore is not a continuously running background timer.
- Added dashboard-wide emergency controls and filtered trade/suggestion/audit tabs. Engaging the emergency switch now also stops the agent and clears full-mode permission; resetting it leaves the agent stopped.
- Full mode remains paper-mode permission only; there is no production scanner, calibrated win-rate evidence, durable trade-state recovery or global broker feed. Live order submission is still disabled.
- Setup is documented in `SETUP_GUIDE.md`. Tests, package installation, and frontend build were not run for this release.
- The existing `frontend/package-lock.json` was untracked before this work and was left untouched and unstaged.

## Release 2.2.0 scope review

- Added market-region, asset-class, exchange, and date filters across the trades and candidate APIs/dashboard, plus market/category filtering in audit views.
- Added explicit visible execution mode selection. Paper mode remains active; live mode is rejected by the backend with HTTP 501.
- Added currency/FX research scope and CORS support for both local Vite hostnames.
- Classification is metadata only. US equities, commodities, FX and other global feeds, broker integrations, live order lifecycle, durable trade recovery, and production authentication remain unimplemented.
- No automated tests or frontend build were run for these changes.

