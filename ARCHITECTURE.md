# Architecture v1

React dashboard -> FastAPI -> market data / AI research / strategy approval / deterministic risk engine -> paper order state.

FastAPI lifespan starts the asynchronous periodic intelligence worker and conditionally connects the configured Upstox V3 feed. The worker offloads provider/search I/O from the event loop; request handlers remain available during refresh. Browser buttons use per-action pending state so kill-switch requests remain independent. The SearXNG container and Vite frontend are separate services and must be running separately.

FastAPI lifespan also starts a paper-only strategy worker. It aggregates actual configured NSE cash-equity LTP updates into completed one-minute bars, evaluates EMA crossover, Donchian breakout, and RSI re-entry rules, creates suggestions in semi mode, and submits risk-bounded local paper orders in full mode. It simulates stop/target/time/session exits on feed updates. It skips index-only instruments and reports that condition in status. Paper strategy state and market history are currently in memory and reset on restart; no fees, taxes, slippage, holiday calendar, or broker fill behavior are simulated.

Upstox integration:
- OAuth 2.0 login URL and callback exchange
- Upstox Python SDK MarketDataStreamerV3 for V3 protobuf WebSocket stream
- Sandbox/live order endpoints documented, but this build does not submit orders

AI:
- Provider adapter layer for OpenAI Responses, Anthropic Messages, Google GenAI, NVIDIA NIM, and OpenAI-compatible Chat Completions.
- Optional user-supplied context is treated as unverified; provider-grounded sources are surfaced when supported.
- Explicit instruction to separate facts, assumptions, uncertainty and missing data.
- Research search can be selected independently from the model provider: native provider search, local SearXNG JSON search, or disabled. SearXNG titles, snippets, URLs, publication dates and engine names are passed to the selected model and retained in the returned source list and audit event.

Live execution remains intentionally unimplemented and gated. Prior to enabling it, broker-specific compliance onboarding, a production-grade order state machine with restart recovery and fill reconciliation, live end-to-end validation, and a separate safety review are required.

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

## v2.3.0 independent web research search

- Added a bounded SearXNG JSON search adapter configurable independently of the AI model provider. This enables source collection when using NVIDIA NIM or another model without native web search.
- Research prompts receive numbered, explicitly untrusted search snippets; responses include source URLs, publication dates when available, and search-engine metadata.
- Search is a research-evidence service. It is not a market quote, order-book, broker, or execution feed. SearXNG must be reachable from the backend and have JSON enabled.

## v2.2.0 market views and execution mode

- Orders and candidates carry `asset_class` (`equity`, `commodity`, `currency`), `market_region` (`India`, `US`, `Global`), and `exchange` metadata. Older records without these fields are displayed as India/equity for backward compatibility.
- Trade, candidate, and audit APIs accept region and asset-class filters. Dashboard views also filter by exchange, symbol, status, side, confidence (suggestions), and date range.
- The execution mode endpoint permits PAPER only. LIVE selection returns HTTP 501 and leaves state in PAPER because the live order lifecycle is not implemented.
- Classification makes records filterable; it does not provide US, commodity, FX or global market data feeds. Upstox market feed remains an NSE-focused scaffold.


## v2.4.0 service startup and responsiveness

- Global intelligence refresh starts once on FastAPI startup, then repeats every `INTELLIGENCE_REFRESH_INTERVAL_MINUTES` (default 30) when `INTELLIGENCE_AUTO_REFRESH=true`. It waits for provider configuration rather than preventing the API from starting.
- Upstox feed auto-connects at startup when `UPSTOX_ACCESS_TOKEN` and `UPSTOX_INSTRUMENT_KEYS` are set. Without them, FastAPI stays available and status reports configuration required. The token must be renewed according to Upstox expiry.
- The browser keeps research, intelligence, feed, bot, and kill-switch actions independent. The API handles synchronous research in FastAPI worker threads and the periodic worker uses a background thread for provider I/O.
- SearXNG is a separate Docker service; this change does not start Docker or Vite from inside the FastAPI process.

## Unreleased dashboard and startup controls

- The emergency kill switch initializes released (OFF); the master agent remains stopped until explicitly started. Daily rollover also leaves the switch released.
- The dashboard separates Global Intelligence from Overview and adds report charts based on closed paper trades from the current in-memory runtime. Reports are filtered by period, symbol, region, asset class and date range; this is not durable trade history.
- Dark mode uses grayscale surfaces; Contrast adds stronger accent and border colors. Light mode remains available.
- The UI requires the exact phrase `I AGREE` to record a LIVE mode selection. The separate Live trading switch remains visibly OFF and locked because live order routing and lifecycle reconciliation are not implemented or reviewed.
- Full autonomy remains a permission flag only. There is no scanner, candidate scheduler or validated strategy in this release.

