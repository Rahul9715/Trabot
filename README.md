# NSE AI Trading Desk — Development Release 2.2.1

> **Status: development prototype only.** This repository is the v2.2.1 development release, not a production release. Live order placement is disabled/unimplemented; `/api/orders/live` deliberately returns HTTP 501.

## Repository conventions

- Keep credentials and local runtime state out of Git. Use `backend/.env.example` as a template and create an ignored `backend/.env` on your own PC.
- SQLite databases, logs, virtual environments, `node_modules/` and build output must not be committed.
- Read `CODEX.md` for project-specific development and safety invariants.

## Safety status

- The application starts in paper mode.
- Upstox integration is a scaffold; do not assume production broker execution is implemented.
- Autonomous scanner/scheduler, portfolio optimiser, continuous position monitor, broker fill reconciliation and production-grade recovery are incomplete.
- Do not connect a funded account or enable live trading with this release.
- Never put credentials, OAuth tokens, passwords or client secrets in source control, screenshots or chat.

## Multi-asset research

The research endpoint supports equities and commodities across a user-selected region/venue, watchlist and time horizon. When web search is enabled, responses include structured source links and generation timestamps, and the source references are recorded in the audit ledger. Research is advisory only: it does not generate verified trading signals or place orders. Market data and broker execution remain limited to the prototype integrations described below; global live trading is not implemented.

## AI provider compatibility and setup

The backend supports adapters for OpenAI, Anthropic Claude, Google Gemini, NVIDIA NIM, and custom OpenAI-compatible chat-completions APIs. Grounding and source citations differ by provider; only supported adapters claim those capabilities. See [SETUP_GUIDE.md](SETUP_GUIDE.md) for Upstox and AI configuration. AI research is advisory; confidence is not a calibrated win probability.

## Source baseline

The v2.2.1 development release includes provider adapters, market/asset classification, region/category filters, a visible paper/live selector with live locked, candidate expiry, daily-sheet Excel export, dedicated dashboard tabs, and persistent agent/kill controls.

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

Durable event-sourced recovery, autonomous NSE scan and strategy scheduling, statistically calibrated confidence, portfolio allocation, genuinely independent review, complete broker order/fill lifecycle, asynchronous evidence archival, UI end-to-end testing, authentication/security hardening, and compliance review remain outstanding.

A passing health/readiness check is not proof of production readiness and is not a trade signal.




