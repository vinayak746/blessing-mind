
import json
import re
import sys
import urllib.error
import urllib.request

BASE_URL = "http://localhost:8000/v1/chat"

UNCERTAINTY_PHRASES = [
    "cannot verify",
    "can't verify",
    "not documented",
    "don't have enough information",
    "do not have enough information",
    "no evidence",
    "couldn't find",
    "could not find",
    "unable to confirm",
    "not available in",
    "doesn't appear to exist",
    "does not appear to exist",
    "cannot confirm",
    "can't confirm",
    "not sure",
    "not supported by the available documentation",
    "insufficient information",
    "unable to determine",
]

TESTS = [
    {
        "name": "Google Forms: exact downstream expression",
        "question": (
            "What is the exact documented expression for accessing "
            "a submitted Google Form answer?"
        ),
        "required": [
            "{{googleForm.responses['Question Name']}}",
        ],
        "source": "google-form.md",
    },
    {
        "name": "Google Forms: illustrative payload",
        "question": (
            "Show the documented illustrative JSON payload for the "
            "Google Form Trigger. Preserve the example's exact "
            "field names and placeholder values."
        ),
        "required": [
            "FORM_ID",
            "RESPONSE_ID",
            "TIMESTAMP_VALUE",
            "Example Person",
            "responses",
        ],
        "source": "google-form.md",
    },
    {
        "name": "Slack: webhook and workflow output",
        "question": (
            "What JSON body does the Slack node POST to its webhook, "
            "and what field does it return in the workflow context?"
        ),
        "required": [
            "content",
            "messageContent",
        ],
        "source": "slack.md",
    },
    {
        "name": "Manual Trigger: how to start a workflow",
        "question": (
            "How do I start a workflow manually in Blessing, "
            "and does the Manual Trigger require configuration?"
        ),
        "required": [
            "Execute",
            "configuration",
        ],
        "source": "manual-trigger.md",
    },
    {
        "name": "Unsupported node: no invented capability",
        "question": "How do I configure the QuantumFlux node in Blessing?",
        "no_evidence": True,
    },

    # Multi-node workflow tests.
    {
        "name": "Multi-node: Gemini output into Slack",
        "question": (
            "I have a Gemini node followed by a Slack node. "
            "Assume Gemini's Variable Name is myGemini and Slack's "
            "Variable Name is mySlack. What exact Handlebars expression "
            "should I put in Slack Message Content to send the Gemini "
            "generated text, and what property does the Slack executor "
            "store in its own output?"
        ),
        "required": [
            "{{myGemini.text}}",
            "{{mySlack.messageContent}}",
            "messageContent",
        ],
        "expected_sources": [
            "gemini.md",
            "slack.md",
        ],
    },
    {
        "name": "Multi-node: Gmail Reader into Gemini",
        "question": (
            "I want a Gmail Reader node followed by Gemini. "
            "Assume Gmail Reader's Variable Name is gmailData. "
            "What documented expression passes the emails as JSON "
            "into the Gemini prompt, and under what property does "
            "Gemini store its generated text if its Variable Name "
            "is myGemini?"
        ),
        "required": [
            "{{json gmailData.emails}}",
            "{{myGemini.text}}",
            "emails",
        ],
        "expected_sources": [
            "nodes-gmail-reader.md",
            "gemini.md",
        ],
    },
    {
        "name": "Implementation accuracy: Slack output discrepancy",
        "question": (
            "The Slack configuration dialog suggests referencing "
            "{{mySlack.text}}, but the executor implementation returns "
            "a different property. Which expression should downstream "
            "nodes actually use, and what is the discrepancy?"
        ),
        "required": [
            "{{mySlack.messageContent}}",
            "messageContent",
            "text",
        ],
        "expected_sources": [
            "slack.md",
        ],
    },
]


def call_api(question, index):
    payload = {
        "conversation_id": f"api-evaluation-{index}",
        "message": question,
        "context": None,
    }

    request = urllib.request.Request(
        BASE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def check_test(test, result):
    answer = result.get("answer", "")
    sources = result.get("sources", [])
    problems = []

    if not isinstance(answer, str) or not answer.strip():
        return ["Answer is empty"]

    if test.get("no_evidence"):
        answer_lower = answer.casefold()

        acknowledges_uncertainty = any(
            phrase in answer_lower
            for phrase in UNCERTAINTY_PHRASES
        )

        if not acknowledges_uncertainty:
            problems.append(
                "Unsupported question: answer does not clearly "
                "acknowledge uncertainty"
            )

        return problems

    for phrase in test.get("required", []):
        if phrase.casefold() not in answer.casefold():
            problems.append(
                f"Missing expected answer text: {phrase}"
            )

    expected_sources = list(test.get("expected_sources", []))

    if test.get("source"):
        expected_sources.append(test["source"])

    source_text = " ".join(
        str(source.get("title", ""))
        + " "
        + str(source.get("excerpt", ""))
        for source in sources
    )

    for expected_source in expected_sources:
        if expected_source.casefold() not in source_text.casefold():
            problems.append(
                f"Expected source not found: {expected_source}"
            )

    if not sources:
        problems.append("No sources returned")

    for source in sources:
        if not source.get("excerpt"):
            problems.append(
                "Empty excerpt in source: "
                f"{source.get('title', 'unknown')}"
            )

    return problems


def check_grounding(test, result):
    """Check citation integrity and known expression invariants."""
    answer = result.get("answer", "")
    sources = result.get("sources", [])
    problems = []

    valid_ids = {
        source.get("id")
        for source in sources
        if source.get("id")
    }

    cited_ids = set(re.findall(r"\[(S\d+)\]", answer))

    for citation in sorted(cited_ids - valid_ids):
        problems.append(
            f"Citation {citation} has no matching source"
        )

    if test.get("name") == (
        "Google Forms: exact downstream expression"
    ):
        if "steps.googleForm" in answer:
            problems.append(
                "Contains unsupported steps.googleForm syntax"
            )

    if test.get("name") == "Google Forms: illustrative payload":
        if '"raw"' in answer or "'raw'" in answer:
            problems.append(
                "Payload example contains raw, which is absent "
                "from the documented illustrative outgoing payload"
            )

    return problems


def main():
    print("BLESSING API EVALUATION")
    print("=" * 65)

    passed = 0
    failed = 0

    for index, test in enumerate(TESTS, start=1):
        print(f"\n[{index}/{len(TESTS)}] {test['name']}")

        try:
            result = call_api(test["question"], index)

            problems = (
                check_test(test, result)
                + check_grounding(test, result)
            )

            if problems:
                failed += 1
                print("FAIL")

                for problem in problems:
                    print(f"  - {problem}")

                print(
                    "  Answer:",
                    repr(result.get("answer", "")[:900]),
                )
                print(
                    "  Sources:",
                    [
                        source.get("title")
                        for source in result.get("sources", [])
                    ],
                )
            else:
                passed += 1
                print("PASS")
                print(
                    "  Sources:",
                    [
                        source.get("title")
                        for source in result.get("sources", [])
                    ],
                )

        except urllib.error.HTTPError as error:
            failed += 1
            details = error.read().decode(
                "utf-8",
                errors="replace",
            )
            print(f"FAIL: HTTP {error.code}: {details[:500]}")

        except Exception as error:
            failed += 1
            print(f"FAIL: {type(error).__name__}: {error}")

    print("\n" + "=" * 65)
    print(f"Results: {passed}/{len(TESTS)} passed; {failed} failed")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
