from app.services.generation import ensure_documented_expressions


def test_ignores_outdated_expression_in_implementation_note():
    question = (
        "Gemini Variable Name is myGemini and Slack Variable Name is mySlack. "
        "What exact Handlebars expression should I use, and what output "
        "property does Slack store?"
    )

    evidence = """[S1] Source: slack.md
Slack Node > Output and Downstream References

If the variable name is `mySlack`, the output is:

`{{mySlack.messageContent}}`

**Implementation note:** The configuration dialog suggests
`{{mySlack.text}}`, but the executor actually stores `messageContent`.
"""

    answer = "Use `{{myGemini.text}}` in Slack Message Content [S2]."

    result = ensure_documented_expressions(question, evidence, answer)

    assert "{{mySlack.messageContent}}" in result
    assert "messageContent" in result
    assert "{{mySlack.text}}" not in result


def test_does_not_change_answer_when_no_expression_is_missing():
    question = (
        "What exact Handlebars expression should I use for "
        "the downstream output?"
    )
    evidence = """[S1] Source: slack.md
`{{mySlack.messageContent}}`
"""
    answer = (
        "Use `{{mySlack.messageContent}}`. "
        "The property is `messageContent`. [S1]"
    )

    assert ensure_documented_expressions(question, evidence, answer) == answer


def test_resolves_documented_json_helper_variable_placeholder():
    question = (
        "Gmail Reader Variable Name gmailData followed by Gemini. "
        "What exact expression should I use to pass the emails array "
        "as JSON?"
    )

    evidence = """[S1] Source: nodes-gmail-reader.md
Reference results in other nodes:
`{{json ${watchVariableName}.emails}}`
"""

    answer = "Use the Gmail Reader output in the Gemini prompt."

    result = ensure_documented_expressions(question, evidence, answer)

    assert "{{json gmailData.emails}}" in result
    assert "[S1]" in result
    assert "{{json ${watchVariableName}.emails}}" not in result


def test_resolves_gmail_json_expression_for_documented_wording():
    question = (
        "I want a Gmail Reader node followed by Gemini. "
        "Assume Gmail Reader's Variable Name is gmailData. "
        "What documented expression passes the emails as JSON "
        "into the Gemini prompt, and under what property does "
        "Gemini store its generated text if its Variable Name "
        "is myGemini?"
    )

    evidence = """[S1] Source: nodes-gmail-reader.md
Reference results in other nodes:
`{{json ${watchVariableName}.emails}}`
"""
    answer = (
        "Use `{{gmailData}}` in the Gemini prompt. "
        "Gemini stores its generated text under `text`."
    )

    result = ensure_documented_expressions(question, evidence, answer)

    assert "{{json gmailData.emails}}" in result
    assert "emails" in result
    assert "[S1]" in result
    assert "{{json ${watchVariableName}.emails}}" not in result
