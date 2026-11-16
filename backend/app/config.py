import os
from dotenv import load_dotenv
load_dotenv()

APP_MODE = os.getenv("APP_MODE", "paper").lower()
STARTING_CAPITAL = float(os.getenv("STARTING_CAPITAL", "10000"))
MAX_RISK_PER_TRADE = float(os.getenv("MAX_RISK_PER_TRADE", "50"))
MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY", "2"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "1"))
PAPER_DEFAULT_DAILY_LOSS_LIMIT = float(os.getenv("PAPER_DEFAULT_DAILY_LOSS_LIMIT", "300"))
PAPER_MAX_HOLD_MINUTES = max(1, min(int(os.getenv("PAPER_MAX_HOLD_MINUTES", "60")), 390))
PAPER_ENTRY_CUTOFF_HOUR = int(os.getenv("PAPER_ENTRY_CUTOFF_HOUR", "15"))
PAPER_ENTRY_CUTOFF_MINUTE = int(os.getenv("PAPER_ENTRY_CUTOFF_MINUTE", "0"))
PAPER_FORCE_EXIT_HOUR = int(os.getenv("PAPER_FORCE_EXIT_HOUR", "15"))
PAPER_FORCE_EXIT_MINUTE = int(os.getenv("PAPER_FORCE_EXIT_MINUTE", "25"))

AI_PROVIDER = os.getenv("AI_PROVIDER", "openai").strip().lower()
_provider_key_names = {
    "openai": ("AI_API_KEY", "OPENAI_API_KEY"),
    "anthropic": ("AI_API_KEY", "ANTHROPIC_API_KEY"),
    "gemini": ("AI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "nvidia": ("AI_API_KEY", "NVIDIA_API_KEY"),
    "openai_compatible": ("AI_API_KEY",),
}
AI_API_KEY = next((os.getenv(name, "").strip() for name in _provider_key_names.get(AI_PROVIDER, ("AI_API_KEY",)) if os.getenv(name, "").strip()), "")
_provider_model_names = {
    "openai": ("AI_MODEL", "OPENAI_MODEL"),
    "anthropic": ("AI_MODEL", "ANTHROPIC_MODEL"),
    "gemini": ("AI_MODEL", "GEMINI_MODEL"),
    "nvidia": ("AI_MODEL", "NVIDIA_MODEL"),
    "openai_compatible": ("AI_MODEL",),
}
AI_MODEL = next((os.getenv(name, "").strip() for name in _provider_model_names.get(AI_PROVIDER, ("AI_MODEL",)) if os.getenv(name, "").strip()), "")
if AI_PROVIDER == "openai" and not AI_MODEL:
    AI_MODEL = "gpt-5"
AI_BASE_URL = os.getenv("AI_BASE_URL", "").strip().rstrip("/")
AI_TIMEOUT_SECONDS = max(5, min(int(os.getenv("AI_TIMEOUT_SECONDS", "60")), 180))

# Backward-compatible names for older local .env files and existing UI clients.
OPENAI_API_KEY = AI_API_KEY if AI_PROVIDER == "openai" else ""
OPENAI_MODEL = AI_MODEL

UPSTOX_CLIENT_ID = os.getenv("UPSTOX_CLIENT_ID", "")
UPSTOX_CLIENT_SECRET = os.getenv("UPSTOX_CLIENT_SECRET", "")
UPSTOX_REDIRECT_URI = os.getenv("UPSTOX_REDIRECT_URI", "http://127.0.0.1:8000/api/broker/upstox/callback")
UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN", "")
UPSTOX_INSTRUMENT_KEYS = [
    item.strip() for item in os.getenv(
        "UPSTOX_INSTRUMENT_KEYS", "NSE_INDEX|Nifty 50,NSE_INDEX|Nifty Bank"
    ).split(",") if item.strip()
]
UPSTOX_MODE = os.getenv("UPSTOX_MODE", "sandbox").lower()
UPSTOX_SANDBOX_TOKEN = os.getenv("UPSTOX_SANDBOX_TOKEN", "")

# Twelve Data supplies global paper-market quotes only; all orders remain in
# Trabot's local paper simulator. Lists are deliberately opt-in and have no
# default symbols so a newly configured key cannot start trading an unknown set.
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()
TWELVE_DATA_US_EQUITIES = [s.strip().upper() for s in os.getenv("TWELVE_DATA_US_EQUITIES", "").split(",") if s.strip()]
TWELVE_DATA_FOREX = [s.strip().upper() for s in os.getenv("TWELVE_DATA_FOREX", "").split(",") if s.strip()]
TWELVE_DATA_COMMODITIES = [s.strip().upper() for s in os.getenv("TWELVE_DATA_COMMODITIES", "").split(",") if s.strip()]
PAPER_GLOBAL_STARTING_CAPITAL_USD = float(os.getenv("PAPER_GLOBAL_STARTING_CAPITAL_USD", "10000"))
PAPER_GLOBAL_MAX_RISK_USD = float(os.getenv("PAPER_GLOBAL_MAX_RISK_USD", "10"))
PAPER_GLOBAL_DAILY_LOSS_LIMIT_USD = float(os.getenv("PAPER_GLOBAL_DAILY_LOSS_LIMIT_USD", "100"))
PAPER_GLOBAL_MAX_TRADES_PER_DAY = max(1, min(int(os.getenv("PAPER_GLOBAL_MAX_TRADES_PER_DAY", "3")), 20))
PAPER_GLOBAL_MAX_HOLD_MINUTES = max(1, min(int(os.getenv("PAPER_GLOBAL_MAX_HOLD_MINUTES", "240")), 10080))
if PAPER_GLOBAL_STARTING_CAPITAL_USD <= 0 or PAPER_GLOBAL_MAX_RISK_USD <= 0 or PAPER_GLOBAL_DAILY_LOSS_LIMIT_USD <= 0:
    raise RuntimeError("Global paper capital, per-trade risk, and daily loss limit must all be positive USD values.")

LIVE_TRADING_ENABLED = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"
LIVE_TRADING_ACK = os.getenv("LIVE_TRADING_ACK", "")

if APP_MODE not in {"paper", "sandbox"}:
    raise RuntimeError("APP_MODE must be paper or sandbox in this build.")
if UPSTOX_MODE not in {"sandbox", "live"}:
    raise RuntimeError("UPSTOX_MODE must be sandbox or live.")

AI_WEB_SEARCH_ENABLED = os.getenv("AI_WEB_SEARCH_ENABLED", "true").lower() == "true"
RESEARCH_SEARCH_PROVIDER = os.getenv("RESEARCH_SEARCH_PROVIDER", "native").strip().lower()
SEARXNG_BASE_URL = os.getenv("SEARXNG_BASE_URL", "http://127.0.0.1:8888").strip().rstrip("/")
SEARXNG_TIMEOUT_SECONDS = max(3, min(int(os.getenv("SEARXNG_TIMEOUT_SECONDS", "15")), 60))

if AI_PROVIDER not in {"openai", "anthropic", "gemini", "nvidia", "openai_compatible"}:
    raise RuntimeError("AI_PROVIDER must be openai, anthropic, gemini, nvidia, or openai_compatible.")
if AI_PROVIDER == "openai_compatible" and not AI_BASE_URL:
    raise RuntimeError("AI_BASE_URL is required when AI_PROVIDER=openai_compatible.")
if RESEARCH_SEARCH_PROVIDER not in {"native", "searxng", "none"}:
    raise RuntimeError("RESEARCH_SEARCH_PROVIDER must be native, searxng, or none.")
if RESEARCH_SEARCH_PROVIDER == "searxng" and not SEARXNG_BASE_URL:
    raise RuntimeError("SEARXNG_BASE_URL is required when RESEARCH_SEARCH_PROVIDER=searxng.")

KILL_SWITCH_RESET_ALLOWED = os.getenv("KILL_SWITCH_RESET_ALLOWED", "true").lower() == "true"
CANDIDATE_PENDING_TTL_MINUTES = max(1, min(int(os.getenv("CANDIDATE_PENDING_TTL_MINUTES", "30")), 1440))
CANDIDATE_QUOTE_MAX_AGE_SECONDS = max(3, min(int(os.getenv("CANDIDATE_QUOTE_MAX_AGE_SECONDS", "30")), 3600))
CANDIDATE_ENTRY_TOLERANCE_PERCENT = max(0.01, min(float(os.getenv("CANDIDATE_ENTRY_TOLERANCE_PERCENT", "0.25")), 10.0))

INTELLIGENCE_MAX_AGE_MINUTES = int(os.getenv("INTELLIGENCE_MAX_AGE_MINUTES", "60"))
INTELLIGENCE_AUTO_REFRESH = os.getenv("INTELLIGENCE_AUTO_REFRESH", "true").lower() == "true"
INTELLIGENCE_REFRESH_INTERVAL_MINUTES = max(5, min(int(os.getenv("INTELLIGENCE_REFRESH_INTERVAL_MINUTES", "30")), 1440))
