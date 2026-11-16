from types import SimpleNamespace

import app.feed as feed_module
from app.feed import _safe_stream_error


def test_stream_error_detail_is_readable_and_redacts_access_token():
    token = "secret-access-token"

    detail = _safe_stream_error(
        (RuntimeError(f"401 Unauthorized Bearer {token}"),),
        token,
    )

    assert "RuntimeError" in detail
    assert "401 Unauthorized" in detail
    assert token not in detail
    assert "[redacted]" in detail


def test_stream_error_extracts_safe_sdk_fields_from_mapping():
    detail = _safe_stream_error(({"code": 1001, "message": "subscription rejected"},))

    assert detail == "1001: subscription rejected"


def test_repeated_connect_reuses_stream_and_retry_replaces_failed_stream(monkeypatch):
    class FakeStreamer:
        instances = []

        def __init__(self, api_client, instrument_keys, mode):
            self.handlers = {}
            self.disconnect_calls = 0
            self.connect_calls = 0
            self.__class__.instances.append(self)

        def on(self, event, handler):
            self.handlers[event] = handler

        def auto_reconnect(self, enabled, interval, retries):
            pass

        def connect(self):
            self.connect_calls += 1

        def disconnect(self):
            self.disconnect_calls += 1

    class FakeConfiguration:
        access_token = ""

    fake_sdk = SimpleNamespace(
        Configuration=FakeConfiguration,
        ApiClient=lambda config: config,
        MarketDataStreamerV3=FakeStreamer,
    )
    fake_state = SimpleNamespace(
        connected=False,
        feed_status="NOT_CONFIGURED",
        feed_error=None,
        ticks=[],
    )
    fake_state.tick = lambda key, data: fake_state.ticks.append((key, data))
    monkeypatch.setattr(feed_module, "state", fake_state)
    monkeypatch.setattr(feed_module, "UPSTOX_ACCESS_TOKEN", "test-token")
    monkeypatch.setitem(__import__("sys").modules, "upstox_client", fake_sdk)
    FakeStreamer.instances.clear()

    feed = feed_module.UpstoxFeed()
    keys = ["NSE_EQ|INE002A01018"]
    feed.start(keys)
    feed.start(keys)

    assert len(FakeStreamer.instances) == 1
    assert FakeStreamer.instances[0].connect_calls == 1

    FakeStreamer.instances[0].handlers["error"](RuntimeError("403 Forbidden"))
    assert fake_state.feed_status == "ERROR"
    feed.start(keys)

    assert len(FakeStreamer.instances) == 2
    assert FakeStreamer.instances[0].disconnect_calls == 1
    assert FakeStreamer.instances[1].connect_calls == 1
    assert fake_state.feed_status == "CONNECTING"

    FakeStreamer.instances[1].handlers["open"]()
    FakeStreamer.instances[1].handlers["message"]({
        "feeds": {keys[0]: {"ltpc": {"ltp": 123.45}}}
    })
    assert fake_state.connected is True
    assert fake_state.feed_status == "CONNECTED"
    assert fake_state.feed_error is None
    assert fake_state.ticks[0][1]["ltp"] == 123.45
