import threading, time
from datetime import datetime, timezone
from .state import state
from .config import UPSTOX_ACCESS_TOKEN

class UpstoxFeed:
    """Uses official Upstox Python SDK MarketDataStreamerV3.
    Requires UPSTOX_ACCESS_TOKEN and the SDK. Stream decoding is handled by SDK.
    """
    def __init__(self):
        self.streamer = None
        self.thread = None

    def start(self, instrument_keys: list[str], access_token: str | None = None):
        token = (access_token or UPSTOX_ACCESS_TOKEN).strip()
        if not token:
            state.connected = False
            state.feed_status = "CONFIGURATION_REQUIRED"
            state.feed_error = "UPSTOX_ACCESS_TOKEN is missing. Complete Upstox OAuth, set the local token in backend/.env, then restart the backend."
            raise RuntimeError(state.feed_error)
        if not instrument_keys or len(instrument_keys) > 100:
            state.feed_status = "CONFIGURATION_REQUIRED"
            state.feed_error = "Configure 1–100 Upstox instrument keys in UPSTOX_INSTRUMENT_KEYS."
            raise RuntimeError(state.feed_error)
        if self.thread and self.thread.is_alive():
            state.feed_status = "CONNECTING" if not state.connected else "CONNECTED"
            return
        state.feed_status = "CONNECTING"
        state.feed_error = None
        import upstox_client
        cfg = upstox_client.Configuration()
        cfg.access_token = token
        api_client = upstox_client.ApiClient(cfg)
        self.streamer = upstox_client.MarketDataStreamerV3(api_client, instrument_keys, "full")

        def on_open(*args):
            state.connected = True
            state.feed_status = "CONNECTED"
            state.feed_error = None
        def on_close(*args):
            state.connected = False
            state.feed_status = "DISCONNECTED"
        def on_error(*args):
            state.connected = False
            state.feed_status = "ERROR"
            state.feed_error = "Upstox stream reported an error. Check the access token, subscription keys, and Upstox connection status."
        def on_message(message):
            now = datetime.now(timezone.utc).isoformat()
            feeds = message.get("feeds", {}) if isinstance(message, dict) else {}
            for instrument_key, item in feeds.items():
                ltpc = item.get("ltpc") or item.get("fullFeed", {}).get("marketFF", {}).get("ltpc") or item.get("fullFeed", {}).get("indexFF", {}).get("ltpc") or {}
                ltp = ltpc.get("ltp")
                if ltp is not None:
                    state.tick(instrument_key, {"ltp": float(ltp), "instrument_key": instrument_key,
                                                "received_at": now, "raw": item})
        self.streamer.on("open", on_open)
        self.streamer.on("close", on_close)
        self.streamer.on("error", on_error)
        self.streamer.on("message", on_message)
        self.streamer.auto_reconnect(True, 5, 10)
        def connect_stream():
            try:
                self.streamer.connect()
            except Exception:
                state.connected = False
                state.feed_status = "ERROR"
                state.feed_error = "Upstox stream failed to start or disconnected. Check token expiry, subscription keys, and network access."

        self.thread = threading.Thread(target=connect_stream, daemon=True)
        self.thread.start()

    def stop(self):
        if self.streamer:
            try:
                self.streamer.disconnect()
            except Exception:
                pass
        state.connected = False
        state.feed_status = "STOPPED"

feed = UpstoxFeed()
