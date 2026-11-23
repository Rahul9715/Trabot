from types import SimpleNamespace

import app.ai_provider as ai_provider


def test_nvidia_request_disables_thinking_to_preserve_final_output(monkeypatch):
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="Source-led brief."))]
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setitem(__import__("sys").modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setattr(ai_provider, "AI_API_KEY", "test-key")
    monkeypatch.setattr(ai_provider, "AI_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")
    monkeypatch.setattr(ai_provider, "AI_PROVIDER", "nvidia")
    monkeypatch.setattr(ai_provider, "AI_BASE_URL", None)
    monkeypatch.setattr(ai_provider, "AI_TIMEOUT_SECONDS", 30)

    result = ai_provider.generate_research("system", "prompt", search_enabled=False)

    assert result.text == "Source-led brief."
    assert captured["max_tokens"] == 6000
    assert captured["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}