# Gemini Node

**Node type:** `NodeType.GEMINI`
**Verification status:** Source-reviewed

## 1. Overview

The Gemini node uses Google's Gemini model to generate text from a configured prompt.

It can use values from the workflow context and stores its generated text under the configured Variable Name.

The node is registered as `NodeType.GEMINI` and uses the Gemini executor.

## 2. When to use it

Use the Gemini node to:
- Generate text using a Gemini model.
- Summarize information from an upstream node.
- Transform or interpret data before passing it to another node.
- Generate content for a downstream action, such as Slack.

The Gemini node generates text; it should not be treated as a replacement for nodes that perform external actions.

## 3. Setup

1. Add the Gemini node to the workflow.
2. Open its configuration dialog.
3. Enter a Variable Name.
4. Configure the available model settings.
5. Enter the prompt.
6. Save the configuration.
7. Connect the node after the trigger or action that provides its input.
8. Execute the workflow and inspect the output.

Check the current dialog for the exact model and credential requirements.

## 4. Configuration

| Field | Required? | Meaning | Example |
|---|---|---|---|
| Variable Name | Verify in dialog | Determines the key used to store the generated output in workflow context. | `myGemini` |
| Model | Verify in dialog | Selects the Gemini model. | A model currently available in the dialog |
| Prompt | Verify in dialog | Instructions and input supplied to Gemini. | `Summarize the following information...` |

Do not assume model names shown in older screenshots are still available.

## 5. Inputs and outputs

### Input

The executor receives the node configuration and current workflow context.

The prompt can use values from the workflow context through the application's supported expression syntax. The exact prompt templating behavior should be checked against the current implementation.

### Output

The executor reads the first generation step's content. If its first content item has type `text`, that text is extracted. Otherwise, the extracted value is an empty string.

The result is stored under the configured Variable Name, in a property named `text`.

For example, with Variable Name `myGemini`, the output is:

```json
{
  "myGemini": {
    "text": "Generated response from Gemini"
  }
}
```


This is an illustrative example, not captured production output.
### Referencing the output downstream

For Variable Name `myGemini`, use:

{{myGemini.text}}

Replace `myGemini` with the exact Variable Name configured in the Gemini node.

The Gemini configuration dialog also displays the `.text` output convention.

## 6. Example workflow
### Generate a summary and send it to Slack

1. Add a trigger or another node that provides information to summarize.
2. Add a Gemini node after it.
3. Set its Variable Name to `myGemini`.
4. Configure the model and prompt.
5. Include the relevant upstream information in the prompt using supported workflow expressions.
6. Add a Slack node after Gemini.
7. Set the Slack message content to:

   Summary: {{myGemini.text}}
8. Configure the Slack webhook and Slack Variable Name.
9. Execute the workflow.
10. Check that Gemini generated the expected text and Slack received the rendered message.
The downstream expression matches the Gemini executor's output structure.

## 7. Execution behavior

The inspected Gemini executor:
1. Receives the node configuration and workflow context.
2. Runs the configured generation operation.
3. Reads the first generation step's content.
4. Extracts text if the first content item has type text; otherwise, it uses an empty string.
5. Returns the existing context with an additional property named after the configured Variable Name.
6. Stores the extracted value in that property as an object containing `text`.

For example, a Variable Name of `myGemini` produces a context entry equivalent to:

```json
{
  "myGemini": {
    "text": "Generated response"
  }
}
```


This output mapping is source-reviewed. It does not mean every provider response or failure case has been live-tested.
## 8. Troubleshooting

| Symptom | Possible cause | Suggested check |
|---|---|---|
| A downstream node cannot read Gemini's result | The expression uses the wrong property or Variable Name. | Check the configured name and use `{{myGemini.text}}` when the name is `myGemini`. |
| Gemini produces empty text | The first content item may not have type `text`. | Inspect the generation response. |
| Expected upstream data is missing | The referenced context key may not exist or the expression may be incorrect. | Inspect the upstream node's output and verify the expression. |
| Generation fails | The cause cannot be established from output mapping alone. | Inspect the execution error, model configuration, and credentials. |

## 9. Security and limitations

### Confirmed behavior

- Generated text is stored under the configured Variable Name.
- The output property is named text.
- The inspected implementation reads the first content item of the first generation step.
- If that item is not of type text, the extracted value is an empty string.
### Items requiring further verification

- The complete list of available Gemini models.
- All credential, quota, and provider error behaviors.
- Whether any additional provider response data is retained elsewhere.
- How non-text or multi-part generation responses are handled beyond the inspected first content item.
Do not place secrets or sensitive information in prompts unless the workflow's data handling and provider configuration have been reviewed.
## 10. Evidence and references

### Blessing source files

- src/features/executions/components/gemini/executor.ts — generation execution, text extraction, and workflow context output.
- src/features/executions/components/gemini/dialog.tsx — configuration dialog and downstream .text expression hint.
- src/features/executions/lib/executor-registry.ts — executor registration.
- src/config/node-components.ts — node component registration.
Blessing's current source and tests determine actual executor behavior. Configuration details should be checked against the current dialog.
## 11. Verification checklist


- [ ] The Gemini node can be added to the workflow editor.
- [ ] Current configuration fields and validation have been checked.
- [ ] A configured prompt successfully generates text.
- [ ] The configured Variable Name is used in the returned context.
- [ ] The output contains the text property.
- [ ] A downstream node can read the output using {{myGemini.text}}.
- [ ] Upstream workflow values are correctly available to the prompt.
- [ ] Empty or non-text generation content is handled as expected.
- [ ] Generation errors and credential failures have been tested.
## Maintenance metadata


- Last reviewed: 2026-11-04
- Reviewer: Not specified
- Verification status: Source-reviewed
- Source revision or commit: Not recorded
