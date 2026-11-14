# Architecture v1

React dashboard -> FastAPI -> market data / AI research / strategy approval / deterministic risk engine -> paper order state.

Upstox integration:
- OAuth 2.0 login URL and callback exchange
- Upstox Python SDK MarketDataStreamerV3 for V3 protobuf WebSocket stream
- Sandbox/live order endpoints documented, but this build does not submit orders

AI:
- OpenAI Responses API
- User-supplied timestamped market context
- Explicit instruction to separate facts, assumptions, uncertainty and missing data

Live execution is intentionally gated. Prior to enabling it, broker-specific compliance onboarding and a production-grade order state machine are required.

## v2.0 audit and safety additions

- `backend/app/audit.py` provides an append-only SQLite ledger, WAL, FULL synchronous commits, update/delete guards and SHA-256 event chaining.
- Candidate and trade lifecycle records include rationale/evidence, confidence, strategy version, reviewer evidence, suggested/actual price fields, and gross/charges/net paper P&L.
- Daily loss lock has its own state and reset baseline; it is distinct from the emergency kill switch.
- Dashboard supports light/dark theme and exposes candidate decisions plus recent audit events.
- Audit ledger persistence is not equivalent to durable trading-state recovery. Full event-sourced replay, external hash anchoring and production hardening remain outstanding.
