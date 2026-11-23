"""Twelve Data quote stream used only as input to Trabot's local paper engine."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any

from .config import (
    TWELVE_DATA_API_KEY,
    TWELVE_DATA_COMMODITIES,
    TWELVE_DATA_FOREX,
    TWELVE_DATA_US_EQUITIES,
)
from .state import state


def configured_instruments() -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for symbols, asset_class, region, prefix in (
        (TWELVE_DATA_US_EQUITIES, "equity", "US", "TD_US_EQ"),
        (TWELVE_DATA_FOREX, "currency", "Global", "TD_FX"),
        (TWELVE_DATA_COMMODITIES, "commodity", "Global", "TD_COMMODITY"),
    ):
        for symbol in symbols:
            result.append({
                "symbol": symbol,
                "instrument_token": f"{prefix}|{symbol}",
                "asset_class": asset_class,
                "market_region": region,
                "exchange": "NASDAQ/NYSE" if asset_class == "equity" else "Twelve Data",
                "currency": "USD",
                "data_source": "Twelve Data",
            })
    symbols_seen: set[str] = set()
    for row in result:
        normalized = row["symbol"].casefold()
        if normalized in symbols_seen:
            raise ValueError(f"Twelve Data symbol is configured in more than one asset list: {row['symbol']}")
        symbols_seen.add(normalized)
    return result


class TwelveDataFeed:
    """Own one reconnecting WebSocket and normalize updates into runtime ticks."""

    URL = "wss://ws.twelvedata.com/v1/quotes/price"

    def __init__(self) -> None:
        self.ws: Any = None
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.lock = threading.RLock()
        self.lifecycle_lock = threading.Lock()
        self.symbols: list[str] = []
        self.by_symbol: dict[str, dict[str, str]] = {}

    def start(self) -> dict[str, Any]:
        if not TWELVE_DATA_API_KEY:
            state.global_feed_status = "CONFIGURATION_REQUIRED"
            state.global_feed_connected = False
            state.global_feed_error = "Set TWELVE_DATA_API_KEY in backend/.env to enable global paper-market quotes."
            return {"started": False, "status": state.global_feed_status, "error": state.global_feed_error}
        instruments = configured_instruments()
        if not instruments:
            state.global_feed_status = "CONFIGURATION_REQUIRED"
            state.global_feed_connected = False
            state.global_feed_error = "Configure at least one Twelve Data equity, FX, or commodity symbol in backend/.env."
            return {"started": False, "status": state.global_feed_status, "error": state.global_feed_error}
        if len(instruments) > 100:
            raise ValueError("Configure no more than 100 global paper symbols per feed.")

        with self.lifecycle_lock:
            with self.lock:
                if self.thread and self.thread.is_alive() and self.symbols == [row["symbol"] for row in instruments]:
                    return {"started": True, "status": state.global_feed_status, "symbols": self.symbols}
                old_thread = self._request_stop_locked()
            if old_thread and old_thread.is_alive() and old_thread is not threading.current_thread():
                old_thread.join(timeout=2.0)
                if old_thread.is_alive():
                    state.global_feed_status = "ERROR"
                    state.global_feed_connected = False
                    state.global_feed_error = "Previous Twelve Data connection is still shutting down; retry the feed start."
                    raise RuntimeError(state.global_feed_error)
            with self.lock:
                self.stop_event = threading.Event()
                self.symbols = [row["symbol"] for row in instruments]
                self.by_symbol = {row["symbol"].casefold(): row for row in instruments}
                state.global_feed_symbols = instruments
                state.global_feed_error = None
                state.global_feed_status = "CONNECTING"
                state.global_feed_connected = False
                self.thread = threading.Thread(target=self._run, name="twelve-data-feed", daemon=True)
                self.thread.start()
        return {"started": True, "status": state.global_feed_status, "symbols": self.symbols}

    def _run(self) -> None:
        try:
            import websocket
        except Exception as exc:
            state.global_feed_status = "ERROR"
            state.global_feed_error = f"Install websocket-client to start Twelve Data streaming: {type(exc).__name__}."
            return

        while not self.stop_event.is_set():
            socket_url = f"{self.URL}?apikey={TWELVE_DATA_API_KEY}"
            app = websocket.WebSocketApp(
                socket_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            with self.lock:
                self.ws = app
            try:
                app.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as exc:
                self._set_error(f"{type(exc).__name__}: {exc}")
            finally:
                with self.lock:
                    if self.ws is app:
                        self.ws = None
            if not self.stop_event.is_set():
                state.global_feed_status = "RECONNECTING"
                state.global_feed_connected = False
                self.stop_event.wait(5)

    def _on_open(self, ws) -> None:
        try:
            ws.send(json.dumps({"action": "subscribe", "params": {"symbols": ",".join(self.symbols)}}))
            state.global_feed_status = "CONNECTED"
            state.global_feed_connected = True
            state.global_feed_error = None
        except Exception as exc:
            self._set_error(f"Subscription request failed: {type(exc).__name__}: {exc}")

    def _on_message(self, _ws, raw: str) -> None:
        try:
            message = json.loads(raw)
        except (TypeError, ValueError):
            return
        if not isinstance(message, dict):
            return
        event = str(message.get("event") or "").casefold()
        if event in {"subscribe-status", "status"}:
            fails = message.get("fails") or []
            if fails:
                self._set_error(f"Twelve Data rejected one or more subscriptions ({len(fails)} symbol(s)); check the account plan and symbol access.")
            elif message.get("status") == "ok":
                state.global_feed_status = "CONNECTED"
                state.global_feed_connected = True
                state.global_feed_error = None
            return
        if event != "price":
            if message.get("status") == "error" or message.get("code"):
                description = str(message.get("message") or message.get("msg") or message.get("code") or "provider error")
                self._set_error(description)
            return

        symbol = str(message.get("symbol") or "").strip().casefold()
        instrument = self.by_symbol.get(symbol)
        try:
            price = float(message["price"])
        except (KeyError, TypeError, ValueError):
            return
        if not instrument or price <= 0:
            return

        received_at = datetime.now(timezone.utc).isoformat()
        provider_time = message.get("timestamp")
        try:
            provider_at = datetime.fromtimestamp(float(provider_time), timezone.utc).isoformat()
        except (TypeError, ValueError, OSError):
            provider_at = received_at
        tick = {
            "ltp": price,
            "instrument_key": instrument["instrument_token"],
            "symbol": instrument["symbol"],
            "asset_class": instrument["asset_class"],
            "market_region": instrument["market_region"],
            "exchange": str(message.get("exchange") or instrument["exchange"]),
            "currency": str(message.get("currency") or instrument["currency"]),
            "provider_timestamp": provider_at,
            "received_at": received_at,
            "data_source": "Twelve Data",
        }
        state.tick(instrument["instrument_token"], tick)
        state.global_feed_last_update = received_at
        state.global_feed_status = "CONNECTED"
        state.global_feed_connected = True
        state.global_feed_error = None

    def _on_error(self, _ws, error) -> None:
        self._set_error(f"{type(error).__name__}: {error}")

    def _on_close(self, _ws, status_code, message) -> None:
        state.global_feed_connected = False
        if self.stop_event.is_set():
            state.global_feed_status = "STOPPED"
        elif state.global_feed_status != "ERROR":
            state.global_feed_status = "DISCONNECTED"

    def _set_error(self, detail: str) -> None:
        safe = str(detail).replace(TWELVE_DATA_API_KEY, "[redacted]")[:300]
        state.global_feed_connected = False
        state.global_feed_status = "ERROR"
        state.global_feed_error = safe

    def _request_stop_locked(self) -> threading.Thread | None:
        self.stop_event.set()
        ws = self.ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        thread = self.thread
        self.thread = None
        self.ws = None
        self.symbols = []
        self.by_symbol = {}
        return thread

    def stop(self) -> None:
        with self.lifecycle_lock:
            with self.lock:
                thread = self._request_stop_locked()
            if thread and thread.is_alive() and thread is not threading.current_thread():
                thread.join(timeout=2.0)
            state.global_feed_connected = False
            state.global_feed_status = "STOPPED"


global_feed = TwelveDataFeed()
