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

    def start(self, instrument_keys: list[str]):
        if not UPSTOX_ACCESS_TOKEN:
            raise RuntimeError("Set UPSTOX_ACCESS_TOKEN before starting live feed.")
        import upstox_client
        cfg = upstox_client.Configuration()
        cfg.access_token = UPSTOX_ACCESS_TOKEN
        api_client = upstox_client.ApiClient(cfg)
        self.streamer = upstox_client.MarketDataStreamerV3(api_client, instrument_keys, "full")

        def on_open(*args):
            state.connected = True
        def on_close(*args):
            state.connected = False
        def on_error(*args):
            state.connected = False
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
        self.thread = threading.Thread(target=self.streamer.connect, daemon=True)
        self.thread.start()

    def stop(self):
        if self.streamer:
            self.streamer.disconnect()
        state.connected = False

feed = UpstoxFeed()
