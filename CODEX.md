# Codex project instructions — NSE AI Trading Desk

## Project status
This repository is a development prototype (v2.0 baseline), not a production trading system. Paper mode is the default. Live broker order execution is intentionally unimplemented and the `/api/orders/live` endpoint returns HTTP 501. Do not claim otherwise.

## Safety invariants
- Never commit credentials, tokens, `.env` files, private keys, broker secrets, account identifiers, or local audit databases.
- Keep `LIVE_TRADING_ENABLED=false`. Do not enable live execution or add real order placement without explicit user authorisation, broker/compliance validation, end-to-end testing, and a separate documented safety review.
- Preserve independent master bot, autonomy and emergency kill-switch controls.
- Daily loss reset must never erase cumulative realised P&L or release the emergency kill switch.
- Audit failure must fail closed for autonomous entries.
- Never fabricate quotes, fills, market timestamps, backtest results, review independence, or confidence probabilities.
- Confidence score is a research score, not a win probability unless empirically calibrated out of sample.

## Engineering workflow
- Read `README.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, and `REVIEW_REPORT.md` before making material changes.
- Run backend tests with `cd backend && python -m pytest -q tests` and compile with `python -m compileall -q app`.
- For frontend changes run `npm install` (or `npm ci` only after a lockfile exists) and `npm run build`.
- Add tests for risk, order lifecycle, audit integrity, state recovery, and failure handling.
- Keep `.env.example` non-secret and synchronised with config parsing. Local runtime config belongs in ignored `.env`.
- Document assumptions, data source timestamps, incomplete features, and operational limitations.
- Do not describe same-model reviews as independent peer reviews. Record actual reviewers and evidence separately.
