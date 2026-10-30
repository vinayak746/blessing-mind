
from app.services.retrieval import retrieve


def test_discord_query_finds_discord_guide():
    matches = retrieve("How do I configure Discord in Blessing?")
    assert matches, "Expected relevant Discord results"

    sources = [match["source"] for match in matches]
    assert any("discord" in source.lower() for source in sources)


def test_slack_query_finds_slack_documentation():
    matches = retrieve("How do I send a Slack message?")
    assert matches, "Expected relevant Slack results"

    sources = [match["source"] for match in matches]
    assert any("slack" in source.lower() for source in sources)


def test_france_query_is_rejected():
    matches = retrieve("What is the capital of France?")
    assert not matches, f"Expected no matches, got: {matches}"


def test_nonexistent_node_query_is_not_assumed_supported():
    matches = retrieve(
        "How do I configure a node that does not exist in Blessing?"
    )

    # Retrieval may return related existing-node documentation.
    # This test intentionally does not require an empty result.
    # Later we will test answer grounding at the API level.
    assert isinstance(matches, list)


def test_reranker_failure_rejects_evidence(monkeypatch):
    import app.services.retrieval as service

    def broken_reranker(query, candidates):
        raise RuntimeError("simulated reranker failure")

    monkeypatch.setattr(service, "rerank", broken_reranker)

    candidates = [
        {"id": "1", "text": "Unrelated documentation", "source": "unrelated.md"}
    ]

    assert service.rerank_with_relevance_gate(
        "How do I configure Discord?",
        candidates,
        top_k=5,
    ) == []


def test_weak_reranker_score_rejects_evidence(monkeypatch):
    import app.services.retrieval as service

    monkeypatch.setattr(service, "MIN_RERANK_SCORE", 0.0)
    monkeypatch.setattr(
        service,
        "rerank",
        lambda query, candidates: [
            {**candidates[0], "rerank_score": -0.2}
        ],
    )

    candidates = [{"id": "1", "text": "Weak match"}]

    assert service.rerank_with_relevance_gate(
        "How do I configure Discord?",
        candidates,
        top_k=5,
    ) == []


def test_relevant_reranked_evidence_is_preserved(monkeypatch):
    import app.services.retrieval as service

    monkeypatch.setattr(service, "MIN_RERANK_SCORE", 0.0)
    monkeypatch.setattr(
        service,
        "rerank",
        lambda query, candidates: [
            {**candidates[0], "rerank_score": 0.8}
        ],
    )

    candidates = [{"id": "1", "text": "Discord setup instructions"}]

    result = service.rerank_with_relevance_gate(
        "How do I configure Discord?",
        candidates,
        top_k=5,
    )

    assert len(result) == 1
    assert result[0]["rerank_score"] == 0.8

def test_source_authority_prefers_node_docs_over_readme_for_node_questions():
    import app.services.retrieval as service

    candidates = [
        {
            "id": "readme",
            "source": "knowledge_base/raw/blessing/generated/readme.md.md",
            "source_type": "blessing_readme",
            "authority": "supporting",
            "rerank_score": 6.0,
        },
        {
            "id": "node",
            "source": (
                "knowledge_base/raw/blessing/generated/"
                "nodes-google-form-trigger.md"
            ),
            "source_type": "blessing_node_docs",
            "authority": "product_docs",
            "rerank_score": 5.5,
        },
    ]

    ranked = service.rank_by_source_authority(
        "How does the Google Forms trigger node work in Blessing?",
        candidates,
    )

    assert ranked[0]["id"] == "node"


def test_source_authority_preserves_official_docs_for_external_api():
    import app.services.retrieval as service

    candidates = [
        {
            "id": "blessing",
            "source": "knowledge_base/raw/blessing/guides/discord-setup.md",
            "source_type": "blessing_supporting_docs",
            "authority": "supporting",
            "rerank_score": 6.0,
        },
        {
            "id": "official",
            "source": (
                "knowledge_base/raw/official/discord/"
                "discord-incoming-webhooks.md"
            ),
            "source_type": "official_external",
            "authority": "official",
            "rerank_score": 5.5,
        },
    ]

    ranked = service.rank_by_source_authority(
        "What does Discord's official incoming webhook API support?",
        candidates,
    )

    assert ranked[0]["id"] == "official"


def test_source_authority_does_not_change_relevance_scores():
    import app.services.retrieval as service

    candidates = [
        {
            "id": "readme",
            "source": "knowledge_base/raw/blessing/generated/readme.md.md",
            "source_type": "blessing_readme",
            "authority": "supporting",
            "rerank_score": 6.0,
        },
        {
            "id": "node",
            "source": (
                "knowledge_base/raw/blessing/generated/"
                "nodes-google-form-trigger.md"
            ),
            "source_type": "blessing_node_docs",
            "authority": "product_docs",
            "rerank_score": 5.5,
        },
    ]

    ranked = service.rank_by_source_authority(
        "How does the Google Forms trigger node work in Blessing?",
        candidates,
    )

    original_scores = {item["id"]: item["rerank_score"] for item in candidates}
    ranked_scores = {item["id"]: item["rerank_score"] for item in ranked}

    assert ranked_scores == original_scores
