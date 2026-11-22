from types import SimpleNamespace

import pytest

from app.services import providers


class MockProviderError(Exception):
    def __init__(self, message, status_code):
        super().__init__(message)
        self.status_code = status_code


def test_resolve_model_supports_configured_providers():
    assert providers.resolve_model("gemini", "gemini-2.5-flash") == (
        "gemini/gemini-2.5-flash"
    )
    assert providers.resolve_model("openai", "gpt-4o") == "openai/gpt-4o"
    assert providers.resolve_model("anthropic", "claude-sonnet-4-5") == (
        "anthropic/claude-sonnet-4-5"
    )


def test_resolve_model_rejects_unsupported_provider():
    with pytest.raises(providers.ProviderConfigurationError):
        providers.resolve_model("unknown", "some-model")


@pytest.mark.parametrize(
    "model",
    [
        "",
        "   ",
        "../model",
        ".hidden",
        "model name",
        "model\nname",
        "model\tname",
        "m" * 129,
    ],
)
def test_resolve_model_rejects_invalid_model(model):
    with pytest.raises(providers.ProviderConfigurationError):
        providers.resolve_model("gemini", model)


def test_gemini_api_key_is_passed_only_to_current_sdk_client(monkeypatch):
    captured = {}

    class FakeModels:
        def generate_content(self, **kwargs):
            captured["model"] = kwargs["model"]
            captured["contents"] = kwargs["contents"]
            return SimpleNamespace(text="Generated answer")

    class FakeClient:
        def __init__(self, *, api_key, http_options):
            captured["api_key"] = api_key
            captured["http_options"] = http_options
            self.models = FakeModels()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(providers.genai, "Client", FakeClient)

    secret = "test-provider-secret"
    result = providers.generate_text(
        provider="gemini",
        model="gemini-3.5-flash-lite",
        api_key=secret,
        prompt="Hello",
    )

    assert result == "Generated answer"
    assert captured["api_key"] == secret
    assert captured["model"] == "gemini-3.5-flash-lite"
    assert captured["contents"] == "Hello"
    assert captured["http_options"].timeout == 30000
    assert not hasattr(providers, "api_key")
    assert not hasattr(providers, "API_KEY")

def test_provider_error_does_not_expose_api_key(monkeypatch):
    secret = "test-provider-secret"

    def failing_completion(**kwargs):
        raise RuntimeError(f"Authentication failed for {secret}")

    monkeypatch.setattr(providers.litellm, "completion", failing_completion)

    with pytest.raises(providers.ProviderRequestError) as exc_info:
        providers.generate_text(
            provider="openai",
            model="gemini-2.5-flash",
            api_key=secret,
            prompt="Hello",
        )

    assert secret not in str(exc_info.value)


def test_empty_api_key_is_rejected():
    with pytest.raises(providers.ProviderConfigurationError):
        providers.generate_text(
            provider="gemini",
            model="gemini-2.5-flash",
            api_key=" ",
            prompt="Hello",
        )


def test_retryable_provider_error_retries_then_succeeds(monkeypatch):
    calls = {"count": 0}
    sleeps = []

    def fake_completion(**kwargs):
        calls["count"] += 1
        if calls["count"] < 2:
            raise MockProviderError("Temporary failure", 503)

        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="Recovered answer")
                )
            ]
        )

    monkeypatch.setattr(providers.litellm, "completion", fake_completion)
    monkeypatch.setattr(providers.time, "sleep", sleeps.append)

    result = providers.generate_text(
        provider="openai",
        model="gemini-2.5-flash",
        api_key="test-provider-key",
        prompt="Hello",
    )

    assert result == "Recovered answer"
    assert calls["count"] == 2
    assert sleeps == [1]


def test_retryable_provider_error_returns_safe_unavailable_error(monkeypatch):
    calls = {"count": 0}

    def failing_completion(**kwargs):
        calls["count"] += 1
        raise MockProviderError("Temporary failure", 503)

    monkeypatch.setattr(providers.litellm, "completion", failing_completion)
    monkeypatch.setattr(providers.time, "sleep", lambda _: None)

    with pytest.raises(providers.ProviderUnavailableError) as exc_info:
        providers.generate_text(
            provider="openai",
            model="gemini-2.5-flash",
            api_key="test-provider-key",
            prompt="Hello",
        )

    assert calls["count"] == 2
    assert "test-provider-key" not in str(exc_info.value)


def test_image_analysis_sends_image_to_provider(monkeypatch):
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="A workflow editor is visible.")
                )
            ]
        )

    monkeypatch.setattr(providers.litellm, "completion", fake_completion)

    result = providers.analyze_image(
        provider="openai",
        model="gpt-4o",
        api_key="test-provider-key",
        question="What is visible?",
        image_bytes=b"test-image",
        mime_type="image/png",
    )

    assert result == "A workflow editor is visible."
    content = captured["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_extract_text_content_accepts_string():
    assert providers._extract_text_content("  Hello  ") == "Hello"


def test_extract_text_content_accepts_content_blocks():
    content = [
        {"type": "text", "text": "First part"},
        {"type": "image", "image_url": "ignored"},
        {"type": "text", "text": "Second part"},
    ]

    assert providers._extract_text_content(content) == (
        "First part\nSecond part"
    )


def test_extract_text_content_handles_empty_content():
    assert providers._extract_text_content(None) == ""
    assert providers._extract_text_content([]) == ""
@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(choices=[]),
        SimpleNamespace(choices=[SimpleNamespace(message=None)]),
        SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=None))
            ]
        ),
    ],
)
def test_malformed_provider_response_returns_safe_error(monkeypatch, response):
    monkeypatch.setattr(
        providers.litellm,
        "completion",
        lambda **kwargs: response,
    )

    with pytest.raises(providers.ProviderRequestError):
        providers.generate_text(
            provider="openai",
            model="gemini-2.5-flash",
            api_key="test-provider-key",
            prompt="Hello",
        )

def test_non_retryable_provider_error_is_not_retried(monkeypatch):
    calls = {"count": 0}

    def failing_completion(**kwargs):
        calls["count"] += 1
        raise MockProviderError("Invalid API key", 401)

    monkeypatch.setattr(providers.litellm, "completion", failing_completion)

    with pytest.raises(providers.ProviderRequestError):
        providers.generate_text(
            provider="openai",
            model="gemini-2.5-flash",
            api_key="test-provider-key",
            prompt="Hello",
        )

    assert calls["count"] == 1

