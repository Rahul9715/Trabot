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

## Autonomous paper strategy preview

The dashboard now includes an experimental rules-based paper engine. It builds completed 1-minute OHLC bars from actual Upstox LTP updates and evaluates three deterministic rules: 8/21 EMA crossover, 20-bar Donchian breakout, and RSI(14) re-entry from an extreme. It requires at least 30 completed bars for each subscribed instrument, the NSE intraday session, fresh feed and intelligence checks, and an available audit ledger. Full mode can only submit simulated paper orders, with per-trade sizing capped by the configured risk budget, one open position, and the daily loss lock. Stops, targets, maximum hold time, and session cutoff are simulated against observed feed ticks.

The default feed keys are Nifty indices and are not individual stock order instruments. To scan stocks, replace or extend `UPSTOX_INSTRUMENT_KEYS` in the local `backend/.env` with valid `NSE_EQ|...` stock keys from Upstox, then restart FastAPI. Strategy scores are not probabilities. This prototype has no market holiday calendar, does not model charges/taxes/slippage or broker fills, and has no validated out-of-sample performance. It does not promise profits. Live routing remains disabled pending broker/compliance validation, complete order/fill recovery, and the required safety review.

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





