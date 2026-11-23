import os
import csv
import json
from pathlib import Path
from dotenv import dotenv_values, load_dotenv

_backend_root = Path(__file__).resolve().parents[1]

# Local configuration remains the safe default. A shared env file can be
# selected per PC once a shared folder is available; it may contain secrets,
# so it must never be placed inside the Git checkout.
_local_env_file = _backend_root / ".env"
_local_env = dotenv_values(_local_env_file) if _local_env_file.is_file() else {}
_shared_env_file = (os.getenv("TRABOT_SHARED_ENV_FILE") or
                    str(_local_env.get("TRABOT_SHARED_ENV_FILE", "")).strip())
_shared_path = None
if _shared_env_file:
    _shared_path = Path(os.path.expandvars(_shared_env_file)).expanduser()
    if not _shared_path.is_absolute():
        _shared_path = (_backend_root / _shared_path).resolve()
    if _shared_path.is_file():
        load_dotenv(_shared_path, override=False)
load_dotenv(_local_env_file, override=False)
TRABOT_CONFIG_SOURCE = "shared" if _shared_path is not None and _shared_path.is_file() else "local"
TRABOT_SHARED_ENV_FILE = _shared_env_file

def _backend_local_path(value: str) -> str:
    path = Path(os.path.expandvars(value)).expanduser()
    return str(path if path.is_absolute() else (_backend_root / path).resolve())

APP_MODE = os.getenv("APP_MODE", "paper").lower()
STARTING_CAPITAL = float(os.getenv("STARTING_CAPITAL", "10000"))
MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY", "15"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "10"))
PAPER_DEFAULT_DAILY_LOSS_LIMIT = float(os.getenv("PAPER_DEFAULT_DAILY_LOSS_LIMIT", "300"))
PAPER_MAX_HOLD_MINUTES = max(1, min(int(os.getenv("PAPER_MAX_HOLD_MINUTES", "60")), 390))
PAPER_ENTRY_CUTOFF_HOUR = int(os.getenv("PAPER_ENTRY_CUTOFF_HOUR", "15"))
PAPER_ENTRY_CUTOFF_MINUTE = int(os.getenv("PAPER_ENTRY_CUTOFF_MINUTE", "0"))
PAPER_FORCE_EXIT_HOUR = int(os.getenv("PAPER_FORCE_EXIT_HOUR", "15"))
PAPER_FORCE_EXIT_MINUTE = int(os.getenv("PAPER_FORCE_EXIT_MINUTE", "28"))
PAPER_FALLBACK_SPREAD_BPS = max(0.0, float(os.getenv("PAPER_FALLBACK_SPREAD_BPS", "10")))
PAPER_SLIPPAGE_BPS = max(0.0, float(os.getenv("PAPER_SLIPPAGE_BPS", "5")))
PAPER_GLOBAL_FALLBACK_SPREAD_BPS = max(0.0, float(os.getenv("PAPER_GLOBAL_FALLBACK_SPREAD_BPS", "15")))
PAPER_GLOBAL_SLIPPAGE_BPS = max(0.0, float(os.getenv("PAPER_GLOBAL_SLIPPAGE_BPS", "5")))
PAPER_GLOBAL_COST_RATE_BPS = max(0.0, float(os.getenv("PAPER_GLOBAL_COST_RATE_BPS", "2.5")))
PAPER_BROKERAGE_PER_ORDER = max(0.0, float(os.getenv("PAPER_BROKERAGE_PER_ORDER", "20")))
PAPER_EQUITY_BROKERAGE_RATE = max(0.0, float(os.getenv("PAPER_EQUITY_BROKERAGE_RATE", "0.001")))
PAPER_EQUITY_EXCHANGE_RATE = max(0.0, float(os.getenv("PAPER_EQUITY_EXCHANGE_RATE", "0.0000307")))
PAPER_OPTIONS_EXCHANGE_RATE = max(0.0, float(os.getenv("PAPER_OPTIONS_EXCHANGE_RATE", "0.0003553")))
PAPER_STT_EQUITY_INTRADAY_RATE = max(0.0, float(os.getenv("PAPER_STT_EQUITY_INTRADAY_RATE", "0.00025")))
PAPER_STT_OPTIONS_SELL_RATE = max(0.0, float(os.getenv("PAPER_STT_OPTIONS_SELL_RATE", "0.0015")))
PAPER_STAMP_BUY_RATE = max(0.0, float(os.getenv("PAPER_STAMP_BUY_RATE", "0.00003")))
PAPER_SEBI_RATE_PER_CRORE = max(0.0, float(os.getenv("PAPER_SEBI_RATE_PER_CRORE", "10")))
PAPER_GST_RATE = max(0.0, float(os.getenv("PAPER_GST_RATE", "0.18")))
PAPER_WARMUP_STORE_PATH = _backend_local_path(os.getenv("PAPER_WARMUP_STORE_PATH", "data/paper_warmup_bars.json").strip())
GLOBAL_PAPER_WARMUP_STORE_PATH = _backend_local_path(os.getenv("GLOBAL_PAPER_WARMUP_STORE_PATH", "data/global_paper_warmup_bars.json").strip())
PAPER_TRADE_LIMITS_PATH = _backend_local_path(os.getenv("PAPER_TRADE_LIMITS_PATH", "data/paper_trade_limits.json").strip())
PAPER_EXIT_SETTINGS_PATH = _backend_local_path(os.getenv("PAPER_EXIT_SETTINGS_PATH", "data/paper_exit_settings.json").strip())
PAPER_LEARNING_STORE_PATH = _backend_local_path(os.getenv("PAPER_LEARNING_STORE_PATH", "data/paper_strategy_learning.json").strip())
TRABOT_MODEL_DIR = _backend_local_path(os.getenv("TRABOT_MODEL_DIR", "data/model").strip() or "data/model")

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
_configured_upstox_keys = [
    item.strip() for item in os.getenv(
        "UPSTOX_INSTRUMENT_KEYS", "NSE_INDEX|Nifty 50,NSE_INDEX|Nifty Bank"
    ).split(",") if item.strip()
]
UPSTOX_INSTRUMENT_KEYS_FILE = os.getenv("UPSTOX_INSTRUMENT_KEYS_FILE", "").strip()
if UPSTOX_INSTRUMENT_KEYS_FILE:
    _watchlist_path = Path(UPSTOX_INSTRUMENT_KEYS_FILE)
    if not _watchlist_path.is_absolute():
        _watchlist_path = _backend_root / _watchlist_path
    if _watchlist_path.is_file():
        _configured_upstox_keys.extend(
            value.strip()
            for line in _watchlist_path.read_text(encoding="utf-8").splitlines()
            for value in line.split(",")
            if value.strip() and not value.lstrip().startswith("#")
        )
UPSTOX_INSTRUMENT_KEYS = list(dict.fromkeys(_configured_upstox_keys))
UPSTOX_OPTION_UNDERLYING_KEYS = [
    value.strip() for value in os.getenv("UPSTOX_OPTION_UNDERLYING_KEYS", "").split(",") if value.strip()
]
if not UPSTOX_OPTION_UNDERLYING_KEYS:
    UPSTOX_OPTION_UNDERLYING_KEYS = [key for key in UPSTOX_INSTRUMENT_KEYS if key.startswith("NSE_INDEX|")]
if len(UPSTOX_OPTION_UNDERLYING_KEYS) > 10:
    raise RuntimeError("Configure at most 10 UPSTOX_OPTION_UNDERLYING_KEYS to keep option-chain scans within API limits.")
UPSTOX_OPTION_UNDERLYING_KEYS = list(dict.fromkeys(UPSTOX_OPTION_UNDERLYING_KEYS))
UPSTOX_INSTRUMENT_KEYS = list(dict.fromkeys(UPSTOX_INSTRUMENT_KEYS + UPSTOX_OPTION_UNDERLYING_KEYS))
if UPSTOX_INSTRUMENT_KEYS_FILE:
    UPSTOX_INSTRUMENT_KEYS_FILE = _backend_local_path(UPSTOX_INSTRUMENT_KEYS_FILE)
UPSTOX_SYMBOL_MAP_FILE = _backend_local_path(os.getenv("UPSTOX_SYMBOL_MAP_FILE", "data/upstox_instrument_symbols.json").strip())
UPSTOX_SYMBOL_BY_KEY: dict[str, str] = {}
try:
    _symbol_file = Path(UPSTOX_SYMBOL_MAP_FILE)
    if _symbol_file.is_file():
        _loaded_symbols = json.loads(_symbol_file.read_text(encoding="utf-8"))
        if isinstance(_loaded_symbols, dict):
            UPSTOX_SYMBOL_BY_KEY.update({str(key): str(value) for key, value in _loaded_symbols.items() if key and value})
except (OSError, json.JSONDecodeError):
    pass
# Migrate from the existing repair-script CSV if no JSON map exists yet.
if not UPSTOX_SYMBOL_BY_KEY:
    _reports = sorted((_backend_root / "data").glob("nifty500_upstox_equity_keys-*.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
    if _reports:
        try:
            with _reports[0].open(encoding="utf-8-sig", newline="") as _stream:
                for _row in csv.DictReader(_stream):
                    if _row.get("InstrumentKey") and _row.get("Symbol"):
                        UPSTOX_SYMBOL_BY_KEY[_row["InstrumentKey"].strip()] = _row["Symbol"].strip()
        except (OSError, csv.Error):
            pass
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
MARKET_DATA_MAX_AGE_SECONDS = max(3, min(int(os.getenv("MARKET_DATA_MAX_AGE_SECONDS", "5")), 60))
CANDIDATE_ENTRY_TOLERANCE_PERCENT = max(0.01, min(float(os.getenv("CANDIDATE_ENTRY_TOLERANCE_PERCENT", "0.25")), 10.0))

INTELLIGENCE_MAX_AGE_MINUTES = int(os.getenv("INTELLIGENCE_MAX_AGE_MINUTES", "60"))
INTELLIGENCE_AUTO_REFRESH = os.getenv("INTELLIGENCE_AUTO_REFRESH", "true").lower() == "true"
INTELLIGENCE_REFRESH_INTERVAL_MINUTES = max(5, min(int(os.getenv("INTELLIGENCE_REFRESH_INTERVAL_MINUTES", "30")), 1440))
