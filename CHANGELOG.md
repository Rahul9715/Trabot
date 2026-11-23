# Changelog

## Unreleased — durable reports and execution-aware paper fills
- Reconstruct trade/order history and candidate decision history from the append-only local audit ledger, and restore open paper positions after backend restarts. Historical records are available only when their lifecycle events were written to that ledger.
- Use Asia/Kolkata calendar dates consistently in trade, suggestion, audit, and report filters.
- Model paper entries and exits with the best streamed bid/ask when available, otherwise configurable spread and slippage estimates; deduct configured brokerage, exchange, STT, stamp duty, SEBI and GST estimates for India, and a configurable USD cost-rate estimate for global paper trades.
- Show net realized P&L reports with cumulative and daily charts, win/loss outcomes, average wins/losses, profit factor, and drawdown. Live broker routing remains disabled.
- Add a fixed latest-action timestamp to each trade, freeze it at closure, and close India paper positions at session cutoff using the latest in-session quote. Ignore after-hours ticks for stop/target decisions.
- Void an invalid after-hours paper stop from active history/P&L via an append-only correction event while preserving the original event and a backup of the local learning file.

## Next build backlog
- Persist complete paper trade/order history locally and reload it after backend restarts, so the Trades table can show prior-day records when the date filters include them. Preserve open/closed status, actual entry and exit prices, realized/unrealized P&L, market, currency, and symbol; keep INR and USD accounts distinct and avoid duplicate history rows.

## Unreleased — Paper model baseline and responsive layout
- Capture price-only features from each signal bar and retain them with the closed paper outcome; older records without snapshots are excluded from training.
- Add manual local logistic-regression training with a chronological holdout, visible sample/class counts, metrics, versioned artifacts, and a hard shadow-only boundary.
- Add configurable model storage and optional shared environment-file loading, retaining local `.env` as fallback. No external Drive data is copied automatically.
- Expand the dashboard to full available width and make its tables/grid layouts adapt to screen size.

## Unreleased — Arm paper autonomy before readiness
- Add a single dashboard action to start the agent and arm full paper autonomy with its daily loss limit, even while the market feed or research checks are still pending.
- Keep order submission gated on fresh in-session data, current source-backed intelligence, a healthy audit ledger, open market hours, configured instruments, and risk controls.
- Preserve an armed mode across daily counter rollover while the backend process remains running; manual stop, kill switch, or daily loss lock still revoke autonomy.

## Unreleased — paper trade controls, attribution, and decision review
- Set new-install paper defaults to 10 concurrent positions and 15 daily entries per account, with validated dashboard controls and local persistence.
- Show current capital plus daily P&L, open positions, and entries; add actual entry, exit/mark, and per-trade P&L to the Trades table.
- Map NSE instrument keys back to readable symbols, and sample a broad configured equity universe under Upstox's 100-key subscription cap while reserving capacity for options.
- Capture rule triggers, price/risk-reward context, approvals, and rejection reasons; persist closed outcomes for strategy-level win-rate/P&L/R review.
- Add repeat-signal cooldown and duplicate-underlying exposure guards. After 20 outcomes with non-positive average R, pause autonomous entries for that strategy while keeping suggestions visible.
- Keep live routes unimplemented. Paper outcomes are available for later live-mode review but do not authorize real orders.

## Unreleased — broader paper scanning and warm-up recovery
- Added EMA(5,13), Donchian(10), Bollinger re-entry and MACD(12,26,9) alongside the existing paper rules.
- Added optional local NSE equity watchlist loading and an Upstox option-chain path that maps directional setups to filtered long calls or long puts for configured index/stock underlyings.
- Persist completed India and global minute bars locally and reload same-session warm-up after backend restart; partial bars and prior-session bars are excluded.
- Live broker routing remains unimplemented; the live-order endpoint is still fail-closed.

## Unreleased — Twelve Data global paper markets
- Add optional Twelve Data WebSocket quote ingestion for explicitly configured US equities, FX pairs, and spot commodity symbols.
- Add a separate USD paper account, risk caps, daily loss lock, trade-count cap, market-session gates, 30-real-bar warm-up, suggestions, semi-mode human approval, and full-mode local paper orders.
- Keep global USD P&L and open positions separate from INR account totals and add a currency selector to performance reports.
- Live routing remains disabled. Twelve Data plan entitlements, exact venue schedules/holidays, spot-commodity maintenance windows, spread, fees, slippage, financing, historical recovery, and strategy performance are not validated by this integration.
- Validation: 16 focused backend tests passed, Python app/tests compiled, and the Vite production build succeeded. No Twelve Data account key was used for an external connection test.

## Unreleased — Experimental autonomous paper strategy engine
- Add a feed-driven paper scanner with 1-minute EMA crossover, Donchian breakout, and RSI re-entry rules, plus paper-only entry sizing and observed-tick exits.
- Add NSE-equity instrument eligibility checks, warm-up/status reporting, stale-feed handling, bounded bar deduplication, and regression coverage for kill-switch and autonomy/order races.
- This is an unvalidated rules prototype. It does not enable live order routing or claim profitability; fees, slippage, durable recovery, and out-of-sample validation remain incomplete.

## Unreleased — Reports, themes and startup safety
- Start with the emergency kill switch released (OFF), while leaving the master bot stopped; daily rollover keeps the switch released.
- Add separate Global Intelligence and Reports tabs, with closed-trade daily P&L charts, win/loss breakdowns and period, date, market, asset and symbol filters.
- Add a grayscale dark theme and an optional high-contrast dark theme.
- Change the explicit LIVE mode acknowledgement phrase to `I AGREE`; make clear that it records a mode selection only. Live order routing stays OFF and locked.
- No durable report history or validated/profitable strategy is added.

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

