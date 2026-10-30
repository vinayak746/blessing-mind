from app.services.retrieval import get_source_authority_bonus


def test_workflow_request_prefers_blessing_docs_over_external_docs():
    query = (
        "I want to send an email whenever a Stripe payment succeeds. "
        "How should I build this in Blessing?"
    )

    blessing_readme = {
        "source": "knowledge_base/raw/blessing/readme.md.md",
        "source_type": "blessing_readme",
    }
    stripe_eventgrid = {
        "source": "knowledge_base/raw/external/stripe-eventgrid.md",
        "source_type": "official_external",
    }

    assert get_source_authority_bonus(query, blessing_readme) == 1.5
    assert get_source_authority_bonus(query, stripe_eventgrid) == -1.5


def test_api_key_question_prefers_official_external_docs():
    query = "Where do I find my Stripe API key?"

    stripe_docs = {
        "source": "knowledge_base/raw/external/stripe-auth.md",
        "source_type": "official_external",
    }

    assert get_source_authority_bonus(query, stripe_docs) == 1.5


def test_node_configuration_prefers_node_docs():
    query = "How do I configure the Slack node?"

    node_docs = {
        "source": "knowledge_base/raw/blessing/generated/nodes-slack.md",
        "source_type": "blessing_node_docs",
    }

    assert get_source_authority_bonus(query, node_docs) == 1.0
