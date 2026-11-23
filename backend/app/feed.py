import re
import threading
from datetime import datetime, timezone
from .state import state
from .config import UPSTOX_ACCESS_TOKEN
from .market_data import provider_timestamp


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
            provider_received_at = provider_timestamp(message.get("currentTs") if isinstance(message, dict) else None)
            for instrument_key, item in feeds.items():
                full_feed = item.get("fullFeed", {}) if isinstance(item, dict) else {}
                option_level = ((item.get("firstLevelWithGreeks") or full_feed.get("firstLevelWithGreeks", {}))
                                if isinstance(item, dict) else {})
                ltpc = (item.get("ltpc") or full_feed.get("marketFF", {}).get("ltpc")
                        or full_feed.get("indexFF", {}).get("ltpc") or option_level.get("ltpc") or {})
                ltp = ltpc.get("ltp")
                if ltp is not None:
                    # A fresh market message proves the stream recovered, even if a
                    # prior error callback left the dashboard in ERROR state.
                    state.connected = True
                    state.feed_status = "CONNECTED"
                    state.feed_error = None
                    tick = {"ltp": float(ltp), "instrument_key": instrument_key,
                            "received_at": now,
                            "provider_received_at": provider_received_at,
                            "last_traded_at": provider_timestamp(ltpc.get("ltt")), "raw": item,
                            "source": "Upstox V3 WebSocket"}
                    market_ff = full_feed.get("marketFF", {}) if isinstance(full_feed, dict) else {}
                    level = market_ff.get("marketLevel", {}) if isinstance(market_ff, dict) else {}
                    book = level.get("bidAskQuote", []) if isinstance(level, dict) else []
                    if isinstance(book, list) and book:
                        try:
                            bids = [float(row["bidP"]) for row in book if float(row.get("bidP", 0)) > 0]
                            asks = [float(row["askP"]) for row in book if float(row.get("askP", 0)) > 0]
                            if bids and asks and max(bids) <= min(asks):
                                tick.update({"bid": max(bids), "ask": min(asks)})
                        except (KeyError, TypeError, ValueError):
                            pass
                    if "bid" not in tick or "ask" not in tick:
                        first_depth = option_level.get("firstDepth", {}) if isinstance(option_level, dict) else {}
                        try:
                            bid, ask = float(first_depth.get("bidP", 0)), float(first_depth.get("askP", 0))
                            if bid > 0 and ask > 0 and bid <= ask:
                                tick.update({"bid": bid, "ask": ask})
                        except (TypeError, ValueError):
                            pass
                    state.tick(instrument_key, tick)
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

    def subscribe(self, instrument_keys: list[str]):
        """Add contracts to the current stream without replacing base subscriptions."""
        if not instrument_keys:
            return
        with self._lock:
            streamer = self.streamer
            new_keys = [key for key in dict.fromkeys(instrument_keys) if key not in self._instrument_keys]
            if not streamer or not new_keys:
                return
            if len(self._instrument_keys) + len(new_keys) > 100:
                raise RuntimeError("Upstox feed subscription limit reached; remove unused symbols before adding option contracts.")
            self._instrument_keys = self._instrument_keys + tuple(new_keys)
            streamer.subscribe(new_keys, "full")

    def unsubscribe(self, instrument_keys: list[str]):
        if not instrument_keys:
            return
        with self._lock:
            streamer = self.streamer
            remove = [key for key in instrument_keys if key in self._instrument_keys]
            if not streamer or not remove:
                return
            streamer.unsubscribe(remove)
            removed = set(remove)
            self._instrument_keys = tuple(key for key in self._instrument_keys if key not in removed)

feed = UpstoxFeed()
