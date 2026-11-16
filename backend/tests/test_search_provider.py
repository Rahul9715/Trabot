import httpx
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.ai_provider import AIResult
from app.search_provider import SearchProviderError, search_searxng


def test_searxng_search_normalizes_deduplicates_and_bounds_results():
    calls = []

    def handler(request):
        calls.append(dict(request.url.params))
        query = request.url.params["q"]
        items = [{
            "title": f"Result for {query}",
            "url": "https://example.com/market",
            "content": "A source snippet.",
            "publishedDate": "2026-11-15T09:00:00Z",
            "engine": "example-search",
        }]
        if query == "second query":
            items.append({"title": "Second source", "url": "https://example.com/second", "content": "More context."})
        return httpx.Response(200, json={"query": query, "results": items})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        sources = search_searxng(
            ["first query", "second query"],
            base_url="http://127.0.0.1:8888/",
            client=client,
            limit_per_query=2,
        )
    finally:
        client.close()

    assert len(calls) == 2
    assert calls[0]["format"] == "json"
    assert [source["url"] for source in sources] == [
        "https://example.com/market", "https://example.com/second"
    ]
    assert sources[0]["published_at"] == "2026-11-15T09:00:00Z"
    assert sources[0]["engine"] == "example-search"


def test_searxng_403_explains_json_format_setting():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(403)))
    try:
        with pytest.raises(SearchProviderError, match="Enable json"):
            search_searxng(["market news"], base_url="http://localhost:8888", client=client)
    finally:
        client.close()


def test_searxng_no_results_reports_per_search_usable_url_counts():
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"results": []})
    ))
    try:
        with pytest.raises(SearchProviderError, match=r"2 searches \(usable results per search: 0, 0\)"):
            search_searxng(["macro update", "India market update"], base_url="http://localhost:8888", client=client)
    finally:
        client.close()


def test_research_passes_searxng_evidence_to_nvidia_and_returns_sources(tmp_path, monkeypatch):
    import app.audit as audit

    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "searxng-research-audit.db")
    audit.init_audit()
    monkeypatch.setattr(main, "RESEARCH_SEARCH_PROVIDER", "searxng")
    monkeypatch.setattr(main, "SEARXNG_BASE_URL", "http://127.0.0.1:8888")
    monkeypatch.setattr(main, "SEARXNG_TIMEOUT_SECONDS", 10)
    monkeypatch.setattr(main, "AI_PROVIDER", "nvidia")
    monkeypatch.setattr(main, "AI_API_KEY", "test-key")
    monkeypatch.setattr(main, "AI_MODEL", "test-model")
    monkeypatch.setattr(main, "AI_WEB_SEARCH_ENABLED", True)

    source = {
        "url": "https://example.com/market",
        "title": "Market report",
        "snippet": "A verified-source lead.",
        "published_at": "2026-11-15T09:00:00Z",
        "engine": "example-search",
        "query": "market news",
        "kind": "searxng_search_result",
    }
    monkeypatch.setattr(main, "search_searxng", lambda queries, **kwargs: [source])
    captured = {}

    def fake_generate(system, prompt, search_enabled):
        captured.update({"system": system, "prompt": prompt, "search_enabled": search_enabled})
        return AIResult(
            text="Evidence-led report [S1].",
            sources=[],
            provider="nvidia",
            model="test-model",
            search_requested=search_enabled,
            search_supported=False,
        )

    monkeypatch.setattr(main, "generate_research", fake_generate)
    response = TestClient(main.app).post("/api/research", json={"question": "Assess Indian markets"})
    assert response.status_code == 200
    body = response.json()
    assert body["web_search_enabled"] is True
    assert body["web_search_supported"] is False
    assert body["search_provider"] == "searxng"
    assert body["sources"][0]["url"] == source["url"]
    assert "A verified-source lead." in captured["prompt"]
    assert "[S1]" in captured["prompt"]
    assert captured["search_enabled"] is False  # NVIDIA receives external evidence; native search is not claimed.
