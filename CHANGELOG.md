# Changelog

## Unreleased — Reports, themes and startup safety
- Start with the emergency kill switch released (OFF), while leaving the master bot stopped; daily rollover keeps the switch released.
- Add separate Global Intelligence and Reports tabs, with closed-trade daily P&L charts, win/loss breakdowns and period, date, market, asset and symbol filters.
- Add a grayscale dark theme and an optional high-contrast dark theme.
- Change the explicit LIVE mode acknowledgement phrase to `I AGREE`; make clear that it records a mode selection only. Live order routing stays OFF and locked.
- No autonomous scanner, durable report history, or validated/profitable strategy is added.

## 2.4.0 - Responsive controls and startup-managed services
- Replaced the page-wide pending flag with independent action states so research does not disable navigation, routine controls, or the emergency kill switch.
- Added a FastAPI lifespan worker for immediate and periodic global-intelligence refresh, plus automatic Upstox feed startup when credentials and subscriptions are configured.
- Exposed feed/worker health in status and clarified the missing Upstox token configuration response.
- Added concurrency, startup, and feed-prerequisite tests; revalidated the SearXNG adapter and research route against a running local instance.

## 2.3.0 — Independent SearXNG research search
- Added SearXNG as an optional search provider independent from AI_PROVIDER, including bounded queries, timeouts, JSON/error handling, result deduplication, source snippets and publication metadata.
- NVIDIA and OpenAI-compatible model research can now receive externally retrieved source evidence without claiming provider-native search support.
- Added SearXNG provenance to research responses and audit events, plus setup instructions and coverage for success, 403 configuration errors and NVIDIA-backed research.
- Research/search remains advisory and does not supply market quotes or execute trades.

## 2.2.1 — NVIDIA NIM environment profile
- Added a ready-to-copy NVIDIA NIM environment profile and setup instructions.
- The profile uses NVIDIA's OpenAI-compatible endpoint, leaves the API key/model blank for local configuration, and keeps live trading disabled.

## 2.2.0 — Market classification and execution mode clarity
- Added market region, asset class (equity/commodity/currency), and exchange fields to new signals and trade candidates, with API filters for trades, suggestions, and audit events.
- Added India/US/Global, category, exchange, status, side, symbol, and date filters to trade and suggestion views; added market/category filters to the audit view.
- Added a visible paper-versus-live execution control. Paper is selected; live mode is locked and the API rejects requests because live execution is not implemented.
- Added currency/FX as a selectable AI research scope and widened local CORS for localhost and 127.0.0.1 Vite origins.
- Migrates existing daily Excel sheets to include the new market classification columns when next updated.
- These market labels and filters do not add US/global/FX market feeds or live broker connectivity.

## 2.1.0 — Provider adapters and safer research workflow
- Added provider adapters for OpenAI, Anthropic, Gemini, NVIDIA NIM, and custom OpenAI-compatible chat-completions endpoints.
- Added provider/model/key configuration, provider-backed research, and source provenance where the adapter supports search grounding.
- Added persistent dashboard agent and kill-switch controls, reset endpoint, semi/full paper-permission mode, and filtered Trades, Suggested Trades, and Audit Ledger tabs.
- Added pending suggestion expiry for TTL, quote staleness/invalidity, stop/target invalidation, and excessive entry drift.
- Added daily-sheet Excel logging/export for suggested trades.
- Added `SETUP_GUIDE.md` with Upstox and AI provider setup instructions.
- Live order submission remains disabled; this release does not promise or establish a trading win rate.

## 2.0.0 — Development milestone
- Added SQLite append-only audit ledger with SHA-256 hash chaining and integrity verification endpoint.
- Added audit records for candidate creation/decisions, AI research, bot controls, paper orders and paper trade closure/modification.
- Added trade candidate confidence, rationale, evidence, strategy version and dual-review fields.
- Added suggested-versus-actual paper trade price fields and paper exit P&L with charges.
- Replaced daily loss hard lock/kill-switch conflation with a separate daily loss lock and explicit reset baseline.
- Added one-click daily lock reset without erasing cumulative P&L or re-enabling autonomy.
- Added dashboard light/dark theme and candidate/audit panels.
- Live order route remains deliberately disabled.

## Unreleased — Multi-asset research and source provenance
- Added research scope inputs for equities, commodities, regions/venues, instruments and time horizons.
- Added structured web-search source links, generation timestamps and audit metadata to research responses.
- Global intelligence readiness now requires at least one structured source reference.
- Research outputs remain advisory; this change does not add global market data feeds or live broker execution.

