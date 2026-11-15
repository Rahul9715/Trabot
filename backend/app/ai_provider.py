"""Provider adapters for research generation and source extraction.

The application uses one normalized result shape. Provider-specific tools are
kept in adapters because OpenAI Responses, Anthropic Messages, Gemini and
OpenAI-compatible chat endpoints do not share a universal API contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import AI_API_KEY, AI_BASE_URL, AI_MODEL, AI_PROVIDER, AI_TIMEOUT_SECONDS


class AIProviderError(RuntimeError):
    """A provider could not produce a usable response."""


@dataclass
class AIResult:
    text: str
    sources: list[dict[str, str]]
    provider: str
    model: str
    search_requested: bool
    search_supported: bool


def _dict(value: Any) -> Any:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return [_dict(item) for item in value]
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(mode="json", by_alias=True)
        except TypeError:
            try:
                return value.model_dump(by_alias=True)
            except TypeError:
                return value.model_dump()
    if hasattr(value, "__dict__"):
        return {key: _dict(item) for key, item in vars(value).items() if not key.startswith("_")}
    return value


def _unique_sources(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        url = item.get("url") or item.get("uri")
        if not isinstance(url, str) or not url.startswith(("https://", "http://")) or url in seen:
            continue
        seen.add(url)
        output.append({"url": url, "title": str(item.get("title") or url), "kind": str(item.get("kind") or "citation")})
    return output


def _walk_for_sources(payload: Any) -> list[dict[str, str]]:
    found: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            kind = node.get("type")
            if kind == "url_citation":
                citation = node.get("url_citation") if isinstance(node.get("url_citation"), dict) else node
                found.append({**citation, "kind": "citation"})
            citations = node.get("citations") or []
            if isinstance(citations, list):
                found.extend({**item, "kind": "citation"} for item in citations if isinstance(item, dict))
            if kind == "web_search_call":
                action = node.get("action") or {}
                if isinstance(action, dict):
                    found.extend({**item, "kind": "search_result"} for item in action.get("sources", []) if isinstance(item, dict))
            if kind == "web_search_result":
                found.append({**node, "kind": "search_result"})
            if kind == "web_search_tool_result":
                content = node.get("content") or []
                if isinstance(content, list):
                    found.extend({**item, "kind": "search_result"} for item in content if isinstance(item, dict))
            for key in ("grounding_chunks", "groundingChunks"):
                chunks = node.get(key) or []
                if isinstance(chunks, list):
                    for chunk in chunks:
                        web = chunk.get("web") if isinstance(chunk, dict) else None
                        if isinstance(web, dict):
                            found.append({"url": web.get("uri") or web.get("url"), "title": web.get("title"), "kind": "citation"})
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(_dict(payload))
    return _unique_sources(found)


def generate_research(system: str, prompt: str, search_enabled: bool = True) -> AIResult:
    """Run the configured provider and normalize output and citations.

    Supported provider IDs: openai, anthropic, gemini, nvidia, and
    openai_compatible. The last two use the OpenAI Chat Completions protocol.
    """
    if not AI_API_KEY:
        raise AIProviderError("No AI API key is configured. Set the provider-specific key in backend/.env.")
    if not AI_MODEL:
        raise AIProviderError("No AI model is configured. Set AI_MODEL (or the provider-specific model variable).")

    provider = AI_PROVIDER
    try:
        if provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=AI_API_KEY, timeout=AI_TIMEOUT_SECONDS, max_retries=2)
            tools = [{"type": "web_search"}] if search_enabled else []
            response = client.responses.create(
                model=AI_MODEL,
                tools=tools,
                include=["web_search_call.action.sources"] if search_enabled else [],
                input=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            )
            text = response.output_text or ""
            sources = _walk_for_sources(response)
            search_supported = True
        elif provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=AI_API_KEY, timeout=AI_TIMEOUT_SECONDS, max_retries=2)
            tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}] if search_enabled else []
            response = client.messages.create(
                model=AI_MODEL,
                max_tokens=6000,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                tools=tools,
            )
            payload = _dict(response)
            text = "\n".join(block.get("text", "") for block in payload.get("content", []) if isinstance(block, dict) and block.get("type") == "text")
            sources = _walk_for_sources(response)
            search_supported = True
        elif provider == "gemini":
            from google import genai
            client = genai.Client(api_key=AI_API_KEY, http_options={"timeout": int(AI_TIMEOUT_SECONDS * 1000)})
            config: dict[str, Any] = {"system_instruction": system}
            if search_enabled:
                config["tools"] = [{"google_search": {}}]
            response = client.models.generate_content(model=AI_MODEL, contents=prompt, config=config)
            text = getattr(response, "text", None) or ""
            sources = _walk_for_sources(response)
            search_supported = True
        elif provider in {"nvidia", "openai_compatible"}:
            from openai import OpenAI
            base_url = AI_BASE_URL or ("https://integrate.api.nvidia.com/v1" if provider == "nvidia" else None)
            if not base_url:
                raise AIProviderError("AI_BASE_URL is required for openai_compatible providers.")
            client = OpenAI(api_key=AI_API_KEY, base_url=base_url, timeout=AI_TIMEOUT_SECONDS, max_retries=2)
            response = client.chat.completions.create(
                model=AI_MODEL,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                max_tokens=6000,
            )
            message = response.choices[0].message if response.choices else None
            content = getattr(message, "content", None)
            if isinstance(content, list):
                text = "\n".join(str(_dict(block).get("text", "")) for block in content if isinstance(_dict(block), dict))
            else:
                text = content or ""
            sources = _walk_for_sources(response)
            search_supported = False
        else:
            raise AIProviderError(f"Unsupported AI_PROVIDER '{provider}'.")
    except AIProviderError:
        raise
    except ImportError as exc:
        raise AIProviderError(f"The SDK for AI_PROVIDER='{provider}' is not installed. Install backend/requirements.txt.") from exc
    except Exception as exc:
        raise AIProviderError(f"{provider} request failed: {exc}") from exc

    if not text.strip():
        raise AIProviderError(f"{provider} returned an empty text response.")
    return AIResult(
        text=text,
        sources=sources,
        provider=provider,
        model=AI_MODEL,
        search_requested=bool(search_enabled),
        search_supported=search_supported,
    )
