from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_chat_uses_configured_rag(monkeypatch):
    import app.api.routes as routes

    monkeypatch.setenv("BLESSING_SERVICE_TOKEN", "test-service-token")
    monkeypatch.setattr(
        routes,
        "generate_answer",
        lambda *args, **kwargs: "Configure the Discord node with your webhook URL.",
    )

    response = client.post(
        "/v1/chat",
        headers={
            "Authorization": "bEaReR test-service-token",
            "X-Provider-API-Key": "test-provider-key",
        },
        json={
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "message": "How do I configure Discord?",
        },
    )

    assert response.status_code == 200

    data = response.json()
    assert data["retrieval_configured"] is True
    assert data["answer"]
    assert data["sources"]


def test_evidence_ids_match_returned_sources():
    from app.api.routes import build_sources, make_evidence

    matches = [
        {
            "source": "guides/discord-setup.md",
            "chunk_index": 2,
            "text": "Open the Discord node and configure the webhook.",
        },
        {
            "source": "official/discord/webhooks.md",
            "chunk_index": 1,
            "text": "Discord incoming webhooks can post messages.",
        },
    ]

    evidence = make_evidence(matches)
    sources = build_sources(matches)

    assert "[S1] Source: guides/discord-setup.md" in evidence
    assert "[S2] Source: official/discord/webhooks.md" in evidence
    assert [source.id for source in sources] == ["S1", "S2"]
    assert sources[0].title == "discord-setup.md"
    assert sources[0].chunk_index == 2
    assert sources[1].excerpt.startswith("Discord incoming webhooks")

def test_external_sources_include_title_type_and_canonical_url():
    from app.api.routes import build_sources

    matches = [
        {
            "source": "knowledge_base/raw/external/docs.stripe.com-webhooks.md",
            "source_type": "official_external",
            "document_title": "Receive Stripe events in your webhook endpoint",
            "canonical_url": "https://docs.stripe.com/webhooks",
            "chunk_index": 0,
            "text": "Stripe sends events to webhook endpoints.",
        }
    ]

    sources = build_sources(matches)

    assert len(sources) == 1
    assert sources[0].id == "S1"
    assert sources[0].title == "Receive Stripe events in your webhook endpoint"
    assert sources[0].type == "official_external"
    assert sources[0].url == "https://docs.stripe.com/webhooks"

def test_duplicate_urls_share_citation_and_return_one_source():
    from app.api.routes import build_sources, make_evidence

    matches = [
        {
            "source": "external/stripe.md",
            "source_type": "official_external",
            "document_title": "Stripe Webhooks",
            "canonical_url": "https://docs.stripe.com/webhooks",
            "chunk_index": 1,
            "text": "Stripe sends webhook events.",
        },
        {
            "source": "external/stripe.md",
            "source_type": "official_external",
            "document_title": "Stripe Webhooks",
            "canonical_url": "https://docs.stripe.com/webhooks",
            "chunk_index": 2,
            "text": "Verify the Stripe signature.",
        },
        {
            "source": "guides/stripe-node.md",
            "source_type": "blessing_node_docs",
            "chunk_index": 0,
            "text": "Configure the Stripe node in Blessing.",
        },
    ]

    evidence = make_evidence(matches)
    sources = build_sources(matches)

    assert len(sources) == 2
    assert [source.id for source in sources] == ["S1", "S2"]
    assert evidence.count("[S1] Source:") == 2
    assert "[S1] Source: external/stripe.md (chunk 1)" in evidence
    assert "[S1] Source: external/stripe.md (chunk 2)" in evidence
    assert "[S2] Source: guides/stripe-node.md (chunk 0)" in evidence
    assert sources[0].url == "https://docs.stripe.com/webhooks"


def test_chat_returns_503_when_knowledge_store_fails(monkeypatch):
    import app.api.routes as routes

    def fail_retrieval(*args, **kwargs):
        raise RuntimeError("Knowledge database unavailable")

    monkeypatch.setattr(routes, "retrieve", fail_retrieval)

    monkeypatch.setenv("BLESSING_SERVICE_TOKEN", "test-service-token")

    response = client.post(
        "/v1/chat",
        headers={
            "Authorization": "Bearer test-service-token",
            "X-Provider-API-Key": "test-provider-key",
        },
        json={
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "message": "How do I configure Discord?",
        },
    )

    assert response.status_code == 503
    assert "knowledge database" in response.json()["detail"].lower()


def test_chat_rejects_missing_service_token(monkeypatch):
    monkeypatch.setenv("BLESSING_SERVICE_TOKEN", "test-service-token")

    response = client.post(
        "/v1/chat",
        json={
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "message": "Hello",
        },
    )

    assert response.status_code == 401


def test_chat_rejects_invalid_service_token(monkeypatch):
    monkeypatch.setenv("BLESSING_SERVICE_TOKEN", "test-service-token")

    response = client.post(
        "/v1/chat",
        headers={
            "Authorization": "Bearer incorrect-token",
            "X-Provider-API-Key": "test-provider-key",
        },
        json={
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "message": "Hello",
        },
    )

    assert response.status_code == 401


def test_chat_rejects_missing_provider_api_key(monkeypatch):
    monkeypatch.setenv("BLESSING_SERVICE_TOKEN", "test-service-token")

    response = client.post(
        "/v1/chat",
        headers={"Authorization": "Bearer test-service-token"},
        json={
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "message": "Hello",
        },
    )

    assert response.status_code == 400




def test_image_chat_rejects_missing_authorization(monkeypatch):
    monkeypatch.setenv("BLESSING_SERVICE_TOKEN", "test-service-token")

    response = client.post(
        "/v1/chat/image",
        data={
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "message": "What is in this image?",
        },
        files={"image": ("test.png", b"fake-image", "image/png")},
    )

    assert response.status_code == 401


def test_provider_api_key_is_not_exposed_in_logs_or_response(
    monkeypatch, caplog
):
    import app.api.routes as routes
    from app.services.providers import ProviderRequestError

    secret = "sensitive-test-provider-key"

    monkeypatch.setenv("BLESSING_SERVICE_TOKEN", "test-service-token")
    monkeypatch.setattr(
        routes,
        "retrieve",
        lambda *args, **kwargs: [
            {
                "source": "test.md",
                "text": "Test documentation evidence.",
                "chunk_index": 0,
            }
        ],
    )

    def fail_generation(*args, **kwargs):
        raise ProviderRequestError(f"Provider rejected key: {secret}")

    monkeypatch.setattr(routes, "generate_answer", fail_generation)

    response = client.post(
        "/v1/chat",
        headers={
            "Authorization": "Bearer test-service-token",
            "X-Provider-API-Key": secret,
        },
        json={
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "message": "Test question",
        },
    )

    assert response.status_code == 502
    assert secret not in caplog.text
    assert secret not in response.text

def test_chat_returns_503_when_service_token_is_not_configured(monkeypatch):
    monkeypatch.delenv("BLESSING_SERVICE_TOKEN", raising=False)

    response = client.post(
        "/v1/chat",
        headers={
            "Authorization": "Bearer test-service-token",
            "X-Provider-API-Key": "test-provider-key",
        },
        json={
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "message": "Hello",
        },
    )

    assert response.status_code == 503


def test_chat_rejects_non_ascii_service_token(monkeypatch):
    from fastapi import HTTPException
    from app.api.routes import get_provider_credentials

    monkeypatch.setenv("BLESSING_SERVICE_TOKEN", "test-service-token")

    try:
        get_provider_credentials(
            authorization="Bearer inválid-token",
            provider_api_key="test-provider-key",
        )
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("Non-ASCII invalid token should be rejected.")
def test_invalid_service_token_rejects_chat_before_retrieval(
    monkeypatch,
):
    import app.api.routes as routes

    monkeypatch.setenv("BLESSING_SERVICE_TOKEN", "test-service-token")

    def unexpected_retrieval(*args, **kwargs):
        raise AssertionError("Retrieval must not run before authentication.")

    monkeypatch.setattr(routes, "retrieve", unexpected_retrieval)

    response = client.post(
        "/v1/chat",
        headers={
            "Authorization": "Bearer wrong-token",
            "X-Provider-API-Key": "test-provider-key",
        },
        json={
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "message": "Hello",
        },
    )

    assert response.status_code == 401


def test_image_chat_rejects_invalid_token_before_image_analysis(
    monkeypatch,
):
    import app.api.routes as routes

    monkeypatch.setenv("BLESSING_SERVICE_TOKEN", "test-service-token")

    def unexpected_analysis(*args, **kwargs):
        raise AssertionError("Image analysis must not run before authentication.")

    monkeypatch.setattr(routes, "analyze_image", unexpected_analysis)

    response = client.post(
        "/v1/chat/image",
        headers={
            "Authorization": "Bearer wrong-token",
            "X-Provider-API-Key": "test-provider-key",
        },
        data={
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "message": "What is in this image?",
        },
        files={"image": ("test.png", b"fake-image", "image/png")},
    )

    assert response.status_code == 401

def test_chat_rejects_unsupported_provider_before_retrieval(monkeypatch):
    import app.api.routes as routes

    monkeypatch.setenv("BLESSING_SERVICE_TOKEN", "test-service-token")

    def unexpected_retrieval(*args, **kwargs):
        raise AssertionError("Retrieval must not run for an invalid provider.")

    monkeypatch.setattr(routes, "retrieve", unexpected_retrieval)

    response = client.post(
        "/v1/chat",
        headers={
            "Authorization": "Bearer test-service-token",
            "X-Provider-API-Key": "test-provider-key",
        },
        json={
            "provider": "unsupported",
            "model": "some-model",
            "message": "Hello",
        },
    )

    assert response.status_code == 400


def test_image_chat_rejects_unsupported_mime_type(monkeypatch):
    monkeypatch.setenv("BLESSING_SERVICE_TOKEN", "test-service-token")

    response = client.post(
        "/v1/chat/image",
        headers={
            "Authorization": "Bearer test-service-token",
            "X-Provider-API-Key": "test-provider-key",
        },
        data={
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "message": "Describe this file",
        },
        files={"image": ("test.gif", b"GIF89a", "image/gif")},
    )

    assert response.status_code == 415


def test_image_chat_rejects_empty_image(monkeypatch):
    monkeypatch.setenv("BLESSING_SERVICE_TOKEN", "test-service-token")

    response = client.post(
        "/v1/chat/image",
        headers={
            "Authorization": "Bearer test-service-token",
            "X-Provider-API-Key": "test-provider-key",
        },
        data={
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "message": "Describe this image",
        },
        files={"image": ("empty.png", b"", "image/png")},
    )

    assert response.status_code == 400


def test_image_chat_rejects_oversized_image(monkeypatch):
    import app.api.routes as routes

    monkeypatch.setenv("BLESSING_SERVICE_TOKEN", "test-service-token")

    response = client.post(
        "/v1/chat/image",
        headers={
            "Authorization": "Bearer test-service-token",
            "X-Provider-API-Key": "test-provider-key",
        },
        data={
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "message": "Describe this image",
        },
        files={
            "image": (
                "large.png",
                b"\x89PNG\r\n\x1a\n" + b"x" * routes.MAX_IMAGE_BYTES,
                "image/png",
            )
        },
    )

    assert response.status_code == 413


def test_image_chat_rejects_mismatched_image_signature(monkeypatch):
    monkeypatch.setenv("BLESSING_SERVICE_TOKEN", "test-service-token")

    response = client.post(
        "/v1/chat/image",
        headers={
            "Authorization": "Bearer test-service-token",
            "X-Provider-API-Key": "test-provider-key",
        },
        data={
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "message": "Describe this image",
        },
        files={"image": ("fake.png", b"not-a-real-png", "image/png")},
    )

    assert response.status_code == 415
