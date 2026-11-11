from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_chat_uses_configured_rag():
    response = client.post(
        "/v1/chat",
        json={"message": "How do I configure Discord?"},
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

    response = client.post(
        "/v1/chat",
        json={"message": "How do I configure Discord?"},
    )

    assert response.status_code == 503
    assert "knowledge database" in response.json()["detail"].lower()
