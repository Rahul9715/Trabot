# NSE AI Trading Desk — Development Release 2.0

> **Status: development prototype only.** This repository is the v2.0 baseline, not a production release. Live order placement is disabled/unimplemented; `/api/orders/live` deliberately returns HTTP 501.

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

## Source baseline

The v2.0 development baseline includes a FastAPI backend, React/Vite frontend, SQLite append-only audit ledger with SHA-256 hash chain, candidate review fields, paper-trade suggested-versus-actual values, daily-loss reset controls, and light/dark dashboard theme.

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

See `ARCHITECTURE.md`, `CHANGELOG.md`, `REVIEW_REPORT.md`, `CODEX.md` and `SECURITY.md` before changing execution, risk or audit code.

## Outstanding work

Durable event-sourced recovery, autonomous NSE scan and strategy scheduling, statistically calibrated confidence, portfolio allocation, genuinely independent review, complete broker order/fill lifecycle, asynchronous evidence archival, UI end-to-end testing, authentication/security hardening, and compliance review remain outstanding.

A passing health/readiness check is not proof of production readiness and is not a trade signal.
