import os
from dotenv import load_dotenv
load_dotenv()

APP_MODE = os.getenv("APP_MODE", "paper").lower()
STARTING_CAPITAL = float(os.getenv("STARTING_CAPITAL", "10000"))
MAX_RISK_PER_TRADE = float(os.getenv("MAX_RISK_PER_TRADE", "50"))
MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY", "2"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "1"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")

UPSTOX_CLIENT_ID = os.getenv("UPSTOX_CLIENT_ID", "")
UPSTOX_CLIENT_SECRET = os.getenv("UPSTOX_CLIENT_SECRET", "")
UPSTOX_REDIRECT_URI = os.getenv("UPSTOX_REDIRECT_URI", "http://127.0.0.1:8000/api/broker/upstox/callback")
UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN", "")
UPSTOX_MODE = os.getenv("UPSTOX_MODE", "sandbox").lower()
UPSTOX_SANDBOX_TOKEN = os.getenv("UPSTOX_SANDBOX_TOKEN", "")

LIVE_TRADING_ENABLED = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"
LIVE_TRADING_ACK = os.getenv("LIVE_TRADING_ACK", "")

if APP_MODE not in {"paper", "sandbox"}:
    raise RuntimeError("APP_MODE must be paper or sandbox in this build.")
if UPSTOX_MODE not in {"sandbox", "live"}:
    raise RuntimeError("UPSTOX_MODE must be sandbox or live.")

AI_WEB_SEARCH_ENABLED = os.getenv("AI_WEB_SEARCH_ENABLED", "true").lower() == "true"

INTELLIGENCE_MAX_AGE_MINUTES = int(os.getenv("INTELLIGENCE_MAX_AGE_MINUTES", "60"))
