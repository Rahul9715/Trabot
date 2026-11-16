import re
import threading
from datetime import datetime, timezone
from .state import state
from .config import UPSTOX_ACCESS_TOKEN


def _safe_stream_error(args, token: str | None = None) -> str:
    """Extract a short SDK error description without exposing credentials."""
    detail = ""
    for value in args:
        if isinstance(value, BaseException):
            detail = f"{type(value).__name__}: {value}"
        elif isinstance(value, dict):
            fields = [value.get(key) for key in ("code", "message", "error", "reason")]
            detail = ": ".join(str(field) for field in fields if field)
        elif isinstance(value, (str, int, float)):
            detail = str(value)
        if detail:
            break
    if token:
        detail = detail.replace(token, "[redacted]")
    detail = re.sub(r"(?i)(bearer\s+)[^\s,'\"]+", r"\1[redacted]", detail)
    return detail[:300]

class UpstoxFeed:
    """Uses official Upstox Python SDK MarketDataStreamerV3.
    Requires UPSTOX_ACCESS_TOKEN and the SDK. Stream decoding is handled by SDK.
    """
    def __init__(self):
        self.streamer = None
        self._lock = threading.Lock()
        self._stopping = False
        self._instrument_keys: tuple[str, ...] = ()

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
        with self._lock:
            requested_keys = tuple(instrument_keys)
            if self.streamer is not None:
                if (requested_keys == self._instrument_keys and
                        state.feed_status in {"CONNECTING", "CONNECTED"}):
                    return
                old_streamer = self.streamer
                self.streamer = None
                try:
                    old_streamer.disconnect()
                except Exception:
                    pass

            state.connected = False
            state.feed_status = "CONNECTING"
            state.feed_error = None
            self._stopping = False
            import upstox_client
            cfg = upstox_client.Configuration()
            cfg.access_token = token
            api_client = upstox_client.ApiClient(cfg)
            streamer = upstox_client.MarketDataStreamerV3(api_client, instrument_keys, "full")
            self.streamer = streamer
            self._instrument_keys = requested_keys

        def is_current_stream():
            return self.streamer is streamer and not self._stopping

        def on_open(*args):
            if not is_current_stream():
                return
            state.connected = True
            state.feed_status = "CONNECTED"
            state.feed_error = None
        def on_close(*args):
            if not is_current_stream():
                return
            state.connected = False
            state.feed_status = "DISCONNECTED"
        def on_error(*args):
            if not is_current_stream():
                return
            state.connected = False
            state.feed_status = "ERROR"
            detail = _safe_stream_error(args, token)
            state.feed_error = "Upstox stream reported an error. Check token validity, subscription keys, and network access."
            if detail:
                state.feed_error += f" SDK detail: {detail}"
        def on_message(message):
            if not is_current_stream():
                return
            now = datetime.now(timezone.utc).isoformat()
            feeds = message.get("feeds", {}) if isinstance(message, dict) else {}
            for instrument_key, item in feeds.items():
                ltpc = item.get("ltpc") or item.get("fullFeed", {}).get("marketFF", {}).get("ltpc") or item.get("fullFeed", {}).get("indexFF", {}).get("ltpc") or {}
                ltp = ltpc.get("ltp")
                if ltp is not None:
                    # A fresh market message proves the stream recovered, even if a
                    # prior error callback left the dashboard in ERROR state.
                    state.connected = True
                    state.feed_status = "CONNECTED"
                    state.feed_error = None
                    state.tick(instrument_key, {"ltp": float(ltp), "instrument_key": instrument_key,
                                                "received_at": now, "raw": item})
        streamer.on("open", on_open)
        streamer.on("close", on_close)
        streamer.on("error", on_error)
        streamer.on("message", on_message)
        streamer.auto_reconnect(True, 5, 10)
        try:
            # MarketDataStreamerV3.connect() starts its own socket thread and
            # returns immediately. The old wrapper thread therefore could not
            # indicate whether the websocket remained alive.
            if self.streamer is streamer:
                streamer.connect()
        except Exception as exc:
            state.connected = False
            state.feed_status = "ERROR"
            detail = _safe_stream_error((exc,), token)
            state.feed_error = "Upstox stream failed to start or disconnected. Check token validity, subscription keys, and network access."
            if detail:
                state.feed_error += f" SDK detail: {detail}"

    def stop(self):
        with self._lock:
            self._stopping = True
            streamer = self.streamer
            self.streamer = None
            self._instrument_keys = ()
            state.connected = False
            state.feed_status = "STOPPED"
        if streamer:
            try:
                streamer.disconnect()
            except Exception:
                pass

feed = UpstoxFeed()
