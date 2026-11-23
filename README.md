# NSE AI Trading Desk — Development Release 2.4.0

> **Status: development prototype only.** This repository is the v2.4.0 development release, not a production release. Live order placement is disabled/unimplemented; `/api/orders/live` deliberately returns HTTP 501.

## Repository conventions

- Keep credentials and local runtime state out of Git. Use `backend/.env.example` as a template and create an ignored `backend/.env` on your own PC.
- SQLite databases, logs, virtual environments, `node_modules/` and build output must not be committed.
- Read `CODEX.md` for project-specific development and safety invariants.

## Safety status

- The application starts in paper mode.
- Upstox integration is a scaffold; do not assume production broker execution is implemented.
- The experimental paper scanner is rules-based and has no out-of-sample validation. Portfolio optimisation, durable trade recovery, broker fill reconciliation and production-grade recovery are incomplete.
- Do not connect a funded account or enable live trading with this release.
- Never put credentials, OAuth tokens, passwords or client secrets in source control, screenshots or chat.
- The emergency kill switch starts released (OFF), while the master agent still starts stopped. Starting the application never starts trading.
- The dashboard includes performance charts based on closed trades currently held in memory. They are not a durable brokerage statement or a validated strategy-performance record.

## Background services and responsiveness

FastAPI starts a periodic global-intelligence worker at launch (30-minute default; configurable) and auto-connects the Upstox feed when a current local access token and instrument keys are configured. The API reports worker/feed state. SearXNG remains a separately managed Docker service; start it before relying on SearXNG-backed refreshes. Slow research requests do not hold the browser controls or the FastAPI event loop.

## Multi-asset research

The research endpoint supports equities and commodities across a user-selected region/venue, watchlist and time horizon. When web search is enabled, responses include structured source links and generation timestamps, and the source references are recorded in the audit ledger. Research is advisory only: it does not generate verified trading signals or place orders. Market data and broker execution remain limited to the prototype integrations described below; global live trading is not implemented.

## AI provider compatibility and setup

The backend supports adapters for OpenAI, Anthropic Claude, Google Gemini, NVIDIA NIM, and custom OpenAI-compatible chat-completions APIs. Grounding and source citations differ by provider; only supported adapters claim those capabilities. See [SETUP_GUIDE.md](SETUP_GUIDE.md) for Upstox and AI configuration. AI research is advisory; confidence is not a calibrated win probability.

## Paper outcome learning and shared configuration

Closed strategy trades retain a compact price-feature snapshot from the signal bar alongside the realized outcome. The Overview tab's **Paper model training** panel reports eligible examples and lets you manually fit an offline logistic-regression baseline after at least 40 feature-complete closed outcomes, including at least 10 winners and 10 losers. It uses a chronological 80/20 train/holdout split. Scores and metrics are for shadow review only; this model does not influence suggestions, approvals, sizing, or orders. Older trades without saved feature snapshots are excluded because their signal-time indicators cannot be safely reconstructed.

The default model directory is `backend/data/model`; override it with `TRABOT_MODEL_DIR`. Each new closed trade writes an immutable, uniquely named feature/outcome sample under `samples/`, as well as updating the existing local outcome ledger. Point `TRABOT_MODEL_DIR` to a shared folder to sync training samples and model artifacts between PCs; sample files are merged by unique trade ID. Shared-drive synchronization may take time to appear on another PC, and only one PC should train at a time because the shared latest-model pointer is updated after each training run. `TRABOT_SHARED_ENV_FILE` optionally points at one shared env file outside the repository; the app reads it before the local `backend/.env`, while process-level environment variables retain precedence. The configured local `.env` remains the fallback if the shared file is absent. Never commit either env file.

The dashboard expands to the available browser width and reflows the grids and tables at narrower window sizes.

## Arm paper autonomy ahead of market readiness

On Overview, enter the India paper daily loss limit and select **Start agent + arm autonomy**. This starts the agent in paper mode and arms full paper autonomy immediately, even if the feed or source-backed intelligence is not ready yet. The scanner waits for fresh in-session quotes, current sourced intelligence, a healthy audit ledger, an open market session, 30 completed one-minute warm-up bars per NSE instrument, and the existing risk checks before considering any entry. Global-market auto entries also wait for fresh quotes and current sourced intelligence. No rule trigger means no suggestion or order.

If the backend stays running overnight, the armed setting carries through the daily counter rollover and scanning can resume after the feed is fresh in the next session. Warm-up bars from the previous NSE session are discarded, so the next session needs to build its 30 bars again. Restarting the backend or PC leaves the bot stopped and autonomy disarmed; use the dashboard button again after restart. The kill switch, manual stop, or a breached daily loss limit disables autonomy.

## Autonomous paper strategy preview

The experimental paper engine builds completed 1-minute OHLC bars from actual Upstox LTP updates and evaluates seven rules: 8/21 and 5/13 EMA crossovers, 20- and 10-bar Donchian breakouts, RSI(14) re-entry, Bollinger-band re-entry, and MACD(12,26,9) crossover. It requires at least 30 completed bars, the NSE intraday session, fresh feed and intelligence checks, and an available audit ledger. Completed bars are atomically stored under `backend/data/` and restored after a same-session backend restart; prior-session bars are discarded. Full mode remains paper-only and is constrained by configured risk limits.

The dashboard shows current capital, daily P&L, open positions, and entry count. New installations default to 10 simultaneous positions and 15 entries per paper account per market day; both limits can be changed on the dashboard (maximums: 50 positions and 100 entries). Settings persist locally in `backend/data/paper_trade_limits.json`. When a Nifty 500 watchlist exceeds Upstox's 100-key subscription limit, the engine subscribes to a broad evenly spaced sample of up to 80 equities, prioritizes option underlyings, and reserves space for streamed option contracts. The status panel shows the configured universe and active sample size. This is a bounded sample, not simultaneous coverage of all 500 names.

Suggestions record their triggering rule, observed bar/quote times, price levels, risk/reward, and approval or auto-rejection reason. The Trades table shows actual entry, exit or current mark, and per-trade paper P&L. Closed outcomes are saved to `backend/data/paper_strategy_learning.json` and summarized by strategy. After at least 20 closed trades for a strategy/asset class with non-positive average R, autonomous paper entries for that strategy pause while suggestions remain visible. This is a conservative sample-based guard, not a validated predictive model. Historical paper results are retained for future live-mode review; live routing remains unimplemented.

The default feed keys include Nifty indices and are not individual stock order instruments. Add valid `NSE_EQ|...` keys to `UPSTOX_INSTRUMENT_KEYS`, or list them one per line in `UPSTOX_INSTRUMENT_KEYS_FILE`. `UPSTOX_SYMBOL_MAP_FILE` maps ISIN-based keys back to readable symbols; the local Nifty 500 repair script creates it. The combined subscription has a 100-key limit. Configure up to 10 index or F&O-eligible stock underlyings in `UPSTOX_OPTION_UNDERLYING_KEYS`; on a directional setup, the paper engine reads Upstox contracts and option-chain data, then may select a liquid long call or long put based on expiry, delta, volume, open interest, and spread. Before an autonomous option entry, the app requires a fresh streamed option quote and sizes whole lots against the full premium at risk, not only the modeled stop distance. Short options and live option orders are not implemented. A signal can be rejected if one lot exceeds the risk budget, regardless of its rule-strength score. The suggestion table shows the reason. Option quotes are streamed only while a candidate or paper position is active. Scores are not probabilities. The prototype has no market holiday calendar, does not model charges/taxes/slippage or broker fills, and has no validated out-of-sample performance. It does not promise profits. The current live-order endpoint remains unimplemented.

### Global markets paper feed

The optional Twelve Data adapter adds US equities, FX, and configured spot-commodity symbols to a separate USD-denominated local paper account. Set `TWELVE_DATA_API_KEY` and opt-in comma-separated symbols in `TWELVE_DATA_US_EQUITIES`, `TWELVE_DATA_FOREX`, and/or `TWELVE_DATA_COMMODITIES` in `backend/.env`, then restart FastAPI. Example symbols are `AAPL`, `EUR/USD`, and `XAU/USD`; symbol availability and real-time access depend on the user's Twelve Data plan. The scanner builds bars from received quotes and needs 30 completed one-minute bars before evaluating the same rules used by the India paper scanner. No historical prices are fabricated for warm-up.

USD capital, per-trade risk, and daily loss limits use `PAPER_GLOBAL_STARTING_CAPITAL_USD`, `PAPER_GLOBAL_MAX_RISK_USD`, and `PAPER_GLOBAL_DAILY_LOSS_LIMIT_USD`; these settings and P&L are not converted to or combined with INR. US equities are limited to regular New York session hours. FX is generally 24/5, not 24/7. This initial global engine approximates configured FX and spot-commodity symbols as 24/5 and does not yet have a venue-specific holiday/maintenance calendar, exchange execution, financing, spreads, commissions, or slippage model. All fills are local paper simulations; live order routing remains disabled.

## Source baseline

The unreleased dashboard changes add a separate Intelligence tab, daily/weekly/monthly performance charts and outcome breakdowns, symbol/market/asset/date filters, grayscale and high-contrast dark themes, and an experimental paper-only strategy worker. Live order routing remains locked.

## Local setup

Backend (Python 3.10+):

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
# Copy .env.example to .env and edit locally. Never commit .env.
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend (Node.js 20+ recommended):

```bash
cd frontend
npm install
npm run dev
```

Dashboard: http://127.0.0.1:5173

Backend tests:

```bash
cd backend
python -m pytest -q tests
python -m compileall -q app
```

See `SETUP_GUIDE.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, `REVIEW_REPORT.md`, `CODEX.md` and `SECURITY.md` before changing execution, risk or audit code.

## Outstanding work

Durable event-sourced recovery, broader strategy research and out-of-sample testing, statistically calibrated confidence, portfolio allocation, complete broker order/fill lifecycle, asynchronous evidence archival, UI end-to-end testing, authentication/security hardening, and compliance review remain outstanding.

A passing health/readiness check is not proof of production readiness and is not a trade signal.





