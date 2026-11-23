"""Source extraction helpers for Responses API research output.

Web search text is useful for reading, but structured citations make its evidence
reviewable by the UI and audit ledger. Missing source metadata stays missing.
"""
from __future__ import annotations


def extract_sources(response) -> list[dict]:
    """Return deduplicated web sources/citations exposed by the Responses API."""
    if hasattr(response, "model_dump"):
        try:
            payload = response.model_dump(mode="json")
        except TypeError:
            payload = response.model_dump()
    elif isinstance(response, dict):
        payload = response
    else:
        payload = {}

    sources: list[dict] = []
    seen: set[str] = set()

    def add(item, kind: str) -> None:
        if not isinstance(item, dict):
            return
        citation = item.get("url_citation") if isinstance(item.get("url_citation"), dict) else item
        url = citation.get("url")
        if not isinstance(url, str) or not url.startswith(("https://", "http://")) or url in seen:
            return
        seen.add(url)
        source = {"url": url, "title": citation.get("title") or item.get("title") or url, "kind": kind}
        if citation.get("start_index") is not None:
            source["start_index"] = citation["start_index"]
        if citation.get("end_index") is not None:
            source["end_index"] = citation["end_index"]
        sources.append(source)

    def walk(value) -> None:
        if isinstance(value, dict):
            item_type = value.get("type")
            if item_type == "url_citation":
                add(value, "citation")
            elif item_type == "web_search_call":
                action = value.get("action") or {}
                for source in action.get("sources", []) if isinstance(action, dict) else []:
                    add(source, "search_result")
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return sources
