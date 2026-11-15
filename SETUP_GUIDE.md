# Trabot 2.2.0 setup and configuration

This guide covers local installation, AI provider configuration, Upstox API configuration, and dashboard behavior. Keep this project in paper mode. It is a development prototype, not a production trading system.

## 1. What “compatible with any AI model” means here

There is no universal API that works with every model. Providers differ in request formats, tool calling, search grounding, citations, model IDs, and billing. Trabot normalizes results behind provider adapters and supports:

| `AI_PROVIDER` | API protocol used | Search grounding and citations |
| --- | --- | --- |
| `openai` | OpenAI Responses API | OpenAI web search; source references are collected |
| `anthropic` | Anthropic Messages API | Anthropic web search tool; citations are collected |
| `gemini` | Google GenAI `generate_content` | Google Search grounding; grounding sources are collected |
| `nvidia` | NVIDIA NIM OpenAI-compatible Chat Completions | Text generation; use independent SearXNG search for external web evidence |
| `openai_compatible` | Configurable OpenAI-compatible Chat Completions endpoint | Text generation; use independent SearXNG search unless the endpoint's own search is configured |

Search is selected independently from the model in `RESEARCH_SEARCH_PROVIDER`: `native` uses provider-supported web search, `searxng` queries your local SearXNG JSON endpoint and passes numbered snippets and URLs to any configured model, and `none` disables web search. Do not treat a source snippet as a verified price or a model confidence score as a calibrated win probability.

The provider adapter normalizes text, model/provider IDs, and source records. It does not make proprietary APIs interchangeable, make every model support every tool, or certify model output. Provider model IDs and tool availability can change; use the current model ID shown by the provider and keep this file updated when switching models.

## 2. Install and run on Windows

From PowerShell, use Python 3.13 and the virtual environment explicitly. This avoids PowerShell's script activation policy:

```powershell
cd C:\Users\Dell\Trabot\backend
py -3.13 -m venv .venv313
.\.venv313\Scripts\python.exe -m pip install --upgrade pip
.\.venv313\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

Set the AI provider fields and save `.env`. Start the backend:

```powershell
.\.venv313\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd C:\Users\Dell\Trabot\frontend
npm.cmd install
npm.cmd run dev
```

Open the local URL Vite prints, usually `http://127.0.0.1:5173`. Restart the backend after any `.env` change. Never expose the development server publicly.

## 3. Configure an AI provider

The application reads provider settings from `backend/.env`, not from frontend JavaScript. Do not commit this file, paste a key into chat, or add a key to the dashboard.

Common fields:

```dotenv
AI_PROVIDER=openai
AI_API_KEY=
AI_MODEL=
AI_BASE_URL=
AI_TIMEOUT_SECONDS=60
AI_WEB_SEARCH_ENABLED=true
RESEARCH_SEARCH_PROVIDER=native
SEARXNG_BASE_URL=http://127.0.0.1:8888
SEARXNG_TIMEOUT_SECONDS=15
```

For OpenAI, keep `AI_PROVIDER=openai`; set `AI_API_KEY` or the legacy `OPENAI_API_KEY`. Set `AI_MODEL` or the legacy `OPENAI_MODEL` to a model enabled for your API project.

For another provider, set `AI_PROVIDER` to the table value and set that provider's key and model. Examples:

```dotenv
# Anthropic Claude
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=your-local-key
ANTHROPIC_MODEL=provider-model-id

# Google Gemini
AI_PROVIDER=gemini
GEMINI_API_KEY=your-local-key
GEMINI_MODEL=provider-model-id

# NVIDIA NIM
AI_PROVIDER=nvidia
NVIDIA_API_KEY=your-local-key
NVIDIA_MODEL=provider-model-id
# Optional; defaults to https://integrate.api.nvidia.com/v1
AI_BASE_URL=https://integrate.api.nvidia.com/v1

# Another service that implements OpenAI Chat Completions
AI_PROVIDER=openai_compatible
AI_API_KEY=your-local-key
AI_MODEL=provider-model-id
AI_BASE_URL=https://your-provider.example/v1
AI_WEB_SEARCH_ENABLED=false
```

Use only one provider block at a time. `AI_API_KEY` and `AI_MODEL`, when set, take precedence over provider-specific aliases. For `openai_compatible`, `AI_BASE_URL` is required. OpenAI-compatible means the Chat Completions request schema; an endpoint that only implements another API shape will not work through this adapter.

For a copy-ready NVIDIA NIM profile, use `backend/nvidia.env.example` as a reference and copy its entries into your existing `backend/.env`. Fill `NVIDIA_API_KEY` and `NVIDIA_MODEL` with values from your NVIDIA account. Do not replace your whole `.env` if it already contains Upstox settings; preserve those entries and keep the file out of Git.

Create keys from the provider's official API console. API access and billing are separate from consumer chat subscriptions. Check model access, API limits, and search/tool billing with the provider before use. Search grounding is used for the global intelligence brief when the selected provider supports it.

### Use local SearXNG with NVIDIA, Claude, Gemini, or another model

Keep the SearXNG container running at `http://127.0.0.1:8888` and make sure its `settings.yml` enables JSON under `search.formats`. You already verified the endpoint by requesting `/search?q=...&format=json` and receiving result JSON. In `backend/.env`, add or change:

```dotenv
RESEARCH_SEARCH_PROVIDER=searxng
SEARXNG_BASE_URL=http://127.0.0.1:8888
SEARXNG_TIMEOUT_SECONDS=15
```

Leave `AI_PROVIDER=nvidia` (or select another supported model provider) and retain that provider's API key/model settings. Restart FastAPI after editing `.env`; configuration is loaded at process start. The backend will query SearXNG for a small bounded set of searches, pass result snippets to the model as untrusted evidence, and return source URLs, dates when present, and search-engine names. `AI_WEB_SEARCH_ENABLED` applies to provider-native search; it does not disable the separate SearXNG path.

If FastAPI itself runs inside a Docker container, `127.0.0.1` points to that backend container. On Docker Desktop for Windows, set `SEARXNG_BASE_URL=http://host.docker.internal:8888` so the backend container can reach the SearXNG port published on Windows. If FastAPI runs directly in PowerShell/VS Code, use `127.0.0.1` as shown above.

SearXNG supplies search result metadata/snippets, not complete page verification, licensed market quotes, broker data, or order-book data. Search failure returns an error instead of silently claiming source-backed research. This integration does not create trades or enable live execution.

## 4. Configure Upstox

Upstox settings are also in `backend/.env`. AI research does not require Upstox; Upstox credentials are only for the broker adapter and NSE market-feed scaffold.

1. Sign in to [Upstox Developer Apps](https://account.upstox.com/developer/apps) and create a personal API app.
2. Register this redirect URI exactly, including scheme, host, port, and path:

   ```text
   http://127.0.0.1:8000/api/broker/upstox/callback
   ```

3. Put the app API key and secret in `UPSTOX_CLIENT_ID` and `UPSTOX_CLIENT_SECRET`.
4. Keep `UPSTOX_MODE=sandbox` for development. `UPSTOX_SANDBOX_TOKEN` is a separate sandbox credential used only by sandbox order calls.
5. `UPSTOX_ACCESS_TOKEN` is required by the current market-feed connector. Generate it through the Upstox OAuth flow or the Developer Apps dashboard and place it only in the local `.env`. Upstox access tokens expire on Upstox's schedule and must be refreshed when expired.
6. Restart the backend and use the dashboard's market-feed control. The current dashboard subscribes to the configured NSE index keys; this is not a global equities or commodities feed.

Relevant local variables:

```dotenv
UPSTOX_CLIENT_ID=your-app-key
UPSTOX_CLIENT_SECRET=your-app-secret
UPSTOX_REDIRECT_URI=http://127.0.0.1:8000/api/broker/upstox/callback
UPSTOX_ACCESS_TOKEN=your-market-data-token
UPSTOX_MODE=sandbox
UPSTOX_SANDBOX_TOKEN=your-sandbox-token
LIVE_TRADING_ENABLED=false
LIVE_TRADING_ACK=
```

The app's `/api/broker/upstox/login` route returns an Upstox authorization URL and a state value. After login, the local callback returns an access token response; manually copy the token into `.env` and restart the backend. Never share the callback response or token. The route does not store secrets in `.env` automatically.

## 5. Dashboard controls and data behavior

- The sticky top bar shows agent start/stop and emergency kill/reset controls on every dashboard tab.
- Resetting the kill switch does not start the agent or re-enable autonomy. Starting the agent is a separate action.
- Semi-autonomous mode leaves candidate decisions for a human. Full-autonomy permission requires readiness checks and a daily loss limit; the current code has no autonomous scanner that generates verified trade signals.
- Pending suggestions expire when the market quote goes stale, price crosses the candidate stop or target, price moves beyond the configured entry tolerance, or the review TTL expires. Expiration updates the audit ledger and the daily Excel sheet.
- Suggested-trade rows are mirrored to `backend/data/suggested_trades.xlsx`, one worksheet per local calendar day. The SQLite hash-chain remains the audit source of truth. The workbook is local, git-ignored, and rebuildable/exportable.
- Trades, suggestions, and audit events have separate dashboard tabs with filters.
- Market and category metadata can be assigned to new records and filtered as India/US/Global plus equity/commodity/currency and exchange. These filters organize records; they do not connect new market-data feeds.
- The top bar shows the execution selector. Paper money is active. Real money is visibly locked, and requests to the API are rejected until a production broker workflow and safeguards exist.
- Geopolitical and market intelligence is generated by the selected AI provider with native search grounding where supported. The optional text field is treated as an unverified lead, not as confirmed market data.

## 6. Safety and limitations

- `LIVE_TRADING_ENABLED=false` must remain set. The live order API remains unimplemented and returns HTTP 501.
- The configured Upstox integration is an NSE-focused development scaffold. There is no cross-venue global market feed, automated strategy scheduler, or live broker reconciliation.
- Full-autonomy mode is a permission/risk-control state, not proof that a production trading strategy exists.
- No model or configuration guarantees profitable trades, 90%+ win rates, or loss-free results.
- Authentication, deployment hardening, independent security review, provider-specific end-to-end validation, and exchange/broker compliance review remain release gates.

## Provider and broker references

- [OpenAI API keys and project management](https://help.openai.com/en/articles/9186755-managing-projects-in-the-api-platform)
- [Anthropic web search tool](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/web-search-tool)
- [Gemini API setup](https://ai.google.dev/gemini-api/docs/get-started) and [Google Search grounding](https://ai.google.dev/gemini-api/docs/generate-content/google-search)
- [NVIDIA NIM LLM API reference](https://docs.api.nvidia.com/nim/reference/llm-apis)
- [Upstox authentication](https://upstox.com/developer/api-documentation/authentication/) and [token exchange](https://upstox.com/developer/api-documentation/get-token/)

