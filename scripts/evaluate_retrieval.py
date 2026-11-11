
from app.services.retrieval import retrieve

GUIDE_SOURCE = "guides/node-reference/http-request.md"

CASES = [
    {
        "name": "Discord setup",
        "query": "How do I configure the Discord node in Blessing?",
        "expected": ("discord-setup.md", "nodes-discord.md"),
    },
    {
        "name": "Incoming webhooks",
        "query": "How do I send a message to a Discord channel using an incoming webhook?",
        "expected": ("discord-incoming-webhooks.md",),
    },
    {
        "name": "Webhook events",
        "query": "What are Discord webhook events?",
        "expected": ("discord-webhook-events.md",),
    },
    {
        "name": "Slack node",
        "query": "What does the Slack node do in Blessing?",
        "expected": ("nodes-slack.md",),
    },
    {
        "name": "Gmail node",
        "query": "How does the Gmail reader node work in Blessing?",
        "expected": ("nodes-gmail-reader.md",),
    },
    {
        "name": "HTTP request node",
        "query": "How do I configure an HTTP request node in Blessing?",
        "expected": ("nodes-http-request.md",),
    },
    {
        "name": "Google Forms trigger",
        "query": "How does the Google Forms trigger node work?",
        "expected": ("nodes-google-form-trigger.md", "google-form.md"),
    },
    {
        "name": "Authentication methods",
        "query": "Which authentication methods does Blessing support?",
        "expected": ("capabilities-and-limitations.md",),
    },
    {
        "name": "Dedicated email node limitation",
        "query": "Can I send emails directly using a dedicated email node?",
        "expected": ("capabilities-and-limitations.md",),
    },
    {
        "name": "PostgreSQL workflow node limitation",
        "query": "Can I save workflow output directly to PostgreSQL using a built-in Blessing node?",
        "expected": ("capabilities-and-limitations.md",),
    },

    # Human-written HTTP Request guide tests.
    {
        "name": "HTTP guide: configuration fields",
        "query": "What configuration fields does the HTTP Request node provide?",
        "expected": (GUIDE_SOURCE,),
        "require_rank_1": True,
        "human_guide": True,
    },
    {
        "name": "HTTP guide: headers and authentication",
        "query": "Why can't I configure custom headers or authentication in the HTTP Request node?",
        "expected": (GUIDE_SOURCE,),
        "require_rank_1": True,
        "human_guide": True,
    },
    {
        "name": "HTTP guide: non-JSON responses",
        "query": "How does the HTTP Request node parse non-JSON responses?",
        "expected": (GUIDE_SOURCE,),
        "require_rank_1": True,
        "human_guide": True,
    },
    {
        "name": "HTTP guide: downstream response",
        "query": "How do I reference the HTTP response in a downstream workflow node?",
        "expected": (GUIDE_SOURCE,),
        "require_rank_1": True,
        "human_guide": True,
    },
    {
        "name": "HTTP guide: missing endpoint",
        "query": "What happens if the HTTP Request endpoint is not configured?",
        "expected": (GUIDE_SOURCE,),
        "require_rank_1": True,
        "human_guide": True,
    },

    # Human-written Manual Trigger guide tests.
    {
        "name": "Manual Trigger: starting a workflow",
        "query": "How do I start a workflow manually from the editor?",
        "expected": ("guides/node-reference/manual-trigger.md",),
        "require_rank_1": True,
        "human_guide": True,
    },
    {
        "name": "Manual Trigger: runtime input",
        "query": "Does the Manual Trigger accept user input when a workflow starts?",
        "expected": ("guides/node-reference/manual-trigger.md",),
        "require_rank_1": True,
        "human_guide": True,
    },
    {
        "name": "Manual Trigger: context pass-through",
        "query": "Does the Manual Trigger pass the existing workflow context through unchanged?",
        "expected": ("guides/node-reference/manual-trigger.md",),
        "require_rank_1": True,
        "human_guide": True,
    },
    {
        "name": "Manual Trigger: configuration",
        "query": "What configuration options are available in the Manual Trigger settings?",
        "expected": ("guides/node-reference/manual-trigger.md",),
        "require_rank_1": True,
        "human_guide": True,
    },

    # Human-written Slack guide tests.
    {
        "name": "Slack guide: configuration fields",
        "query": "What fields must I configure in the Slack node?",
        "expected": ("guides/node-reference/slack.md",),
        "require_rank_1": True,
        "human_guide": True,
    },
    {
        "name": "Slack guide: webhook payload",
        "query": "In the Slack node executor, what JSON body is POSTed to the configured Slack webhook URL?",
        "expected": ("guides/node-reference/slack.md",),
        "require_rank_1": True,
        "human_guide": True,
    },
    {
        "name": "Slack guide: downstream output",
        "query": "How do I reference the Slack node output in a downstream node?",
        "expected": ("guides/node-reference/slack.md",),
        "require_rank_1": True,
        "human_guide": True,
    },
    {
        "name": "Slack guide: JSON template helper",
        "query": "How can I stringify an object as JSON in Slack message content?",
        "expected": ("guides/node-reference/slack.md",),
        "require_rank_1": True,
        "human_guide": True,
    },

    {
        "name": "Unknown node",
        "query": "How do I configure the QuantumFlux node in Blessing?",
        "expected": (),
        "must_be_empty": True,
    },
    {
        "name": "Unsupported feature",
        "query": "How do I connect Blessing to a quantum blockchain using a QuantumFlux connector?",
        "expected": (),
        "must_be_empty": True,
    },
    {
        "name": "Unrelated question",
        "query": "What is the capital of France?",
        "expected": (),
        "must_be_empty": True,
    },
]


def main():
    passed = 0
    required = 0
    reciprocal_ranks = []
    known_hits = 0
    known_total = 0
    guide_passed = 0
    guide_total = 0

    print("\nBLESSING RETRIEVAL EVALUATION")
    print("=" * 65)

    for case in CASES:
        print(f"\n[{case['name']}]")
        print(f"Query: {case['query']}")

        try:
            results = retrieve(case["query"], top_k=5)
        except Exception as exc:
            print(f"ERROR: {type(exc).__name__}: {exc}")
            required += 1
            if case.get("human_guide"):
                guide_total += 1
            continue

        sources = [str(r.get("source", "")) for r in results]

        for rank, result in enumerate(results, start=1):
            score = result.get("rerank_score")
            score_text = f"{score:.4f}" if score is not None else "n/a"
            print(
                f"  {rank}. {result.get('source')} "
                f"| chunk={result.get('chunk_index')} "
                f"| rerank_score={score_text}"
            )

        if not results:
            print("  No evidence returned.")

        required += 1

        if case.get("must_be_empty"):
            ok = not results
            print(
                "  " + (
                    "PASS: no evidence returned."
                    if ok else "FAIL: unsupported query returned evidence."
                )
            )
        else:
            expected = case["expected"]
            first_rank = next(
                (
                    rank for rank, source in enumerate(sources, start=1)
                    if any(part in source for part in expected)
                ),
                None,
            )

            known_total += 1
            if first_rank is not None:
                known_hits += 1
                reciprocal_ranks.append(1 / first_rank)
            else:
                reciprocal_ranks.append(0.0)

            if case.get("human_guide"):
                guide_total += 1
                guide_ok = first_rank == 1
                guide_passed += int(guide_ok)
                if guide_ok:
                    print("  PASS: human-written guide ranked first.")
                else:
                    print(
                        "  FAIL: human-written guide was not ranked first "
                        f"(rank={first_rank})."
                    )
                ok = guide_ok
            else:
                ok = first_rank is not None
                if ok:
                    print(
                        "  PASS: expected source first appears "
                        f"at rank {first_rank}."
                    )
                else:
                    print(f"  FAIL: expected one of {expected}.")

        passed += int(ok)

    print("\n" + "=" * 65)
    print(f"Required checks: {passed}/{required} passed")

    if known_total:
        print(
            f"Known-query Hit@5: {known_hits}/{known_total} "
            f"({known_hits / known_total:.0%})"
        )
        mrr = sum(reciprocal_ranks) / len(reciprocal_ranks)
        print(f"Known-query MRR@5: {mrr:.3f}")

    if guide_total:
        print(
            f"Human-written guide rank-1: "
            f"{guide_passed}/{guide_total} "
            f"({guide_passed / guide_total:.0%})"
        )

    if passed != required:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
