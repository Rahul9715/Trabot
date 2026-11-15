# Changelog

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
