# Architecture v1

React dashboard -> FastAPI -> market data / AI research / strategy approval / deterministic risk engine -> paper order state.

Upstox integration:
- OAuth 2.0 login URL and callback exchange
- Upstox Python SDK MarketDataStreamerV3 for V3 protobuf WebSocket stream
- Sandbox/live order endpoints documented, but this build does not submit orders

AI:
- Provider adapter layer for OpenAI Responses, Anthropic Messages, Google GenAI, NVIDIA NIM, and OpenAI-compatible Chat Completions.
- Optional user-supplied context is treated as unverified; provider-grounded sources are surfaced when supported.
- Explicit instruction to separate facts, assumptions, uncertainty and missing data.

Live execution is intentionally gated. Prior to enabling it, broker-specific compliance onboarding and a production-grade order state machine are required.

## v2.0 audit and safety additions

- `backend/app/audit.py` provides an append-only SQLite ledger, WAL, FULL synchronous commits, update/delete guards and SHA-256 event chaining.
- Candidate and trade lifecycle records include rationale/evidence, confidence, strategy version, reviewer evidence, suggested/actual price fields, and gross/charges/net paper P&L.
- Daily loss lock has its own state and reset baseline; it is distinct from the emergency kill switch.
- Dashboard supports light/dark theme and exposes candidate decisions plus recent audit events.
- Audit ledger persistence is not equivalent to durable trading-state recovery. Full event-sourced replay, external hash anchoring and production hardening remain outstanding.

## v2.1.0 provider and dashboard changes

- `backend/app/ai_provider.py` routes research to OpenAI Responses, Anthropic Messages, Google Gemini, NVIDIA NIM, or a user-supplied OpenAI-compatible chat-completions endpoint. Search grounding is provider-specific; adapters report support and return structured sources where available.
- `backend/app/excel_log.py` writes candidate lifecycle rows to daily worksheets. The SQLite audit ledger remains the canonical append-only record; Excel is a convenience export, not the audit source of truth.
- Agent start/stop and emergency kill/reset controls remain visible across dashboard tabs. Trades, suggestions, and audit events each have dedicated filtered views.
- Semi/full mode is a paper-mode operating permission. There is no autonomous scanner/strategy scheduler, and live order submission remains disabled.
- Pending candidates are checked for expiry when the candidate API is read or a decision is attempted. Quote based invalidation requires a market quote.
- Optional user context can be attached to research and is treated as unverified input.

See `SETUP_GUIDE.md` for Upstox and provider setup.
