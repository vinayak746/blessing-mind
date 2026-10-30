# Slack Node

## Overview

The Slack node sends a message to Slack through a configured webhook URL. It can use values from the existing workflow context to build dynamic message content.

The node is registered as `NodeType.SLACK` and uses the `slackExecutor` to perform its work.

## When to Use It

Use the Slack node when you want a workflow to:

- Send a notification to Slack.
- Share the result of an upstream node.
- Include dynamic values in a message.
- Notify a team about an event, such as a form submission or payment.

## Configuration

The Slack configuration dialog has three fields.

### Variable Name

The variable name determines where the node's result is stored in the workflow context.

The field is required. Its value must start with a letter, underscore, or dollar sign, followed by letters, numbers, underscores, or dollar signs.

Example: `mySlack`

The executor stores the result under this variable name.

### Webhook URL

The webhook URL is required. The configuration dialog directs users to Slack's Workspace Settings, under Workflows and Webhooks, to obtain it.

The configured webhook must accept a JSON payload containing a `content` field.

Keep the webhook URL private. Do not expose it in public documentation, logs, or messages.

### Message Content

Message Content is the text sent to Slack. It supports Handlebars expressions that reference values in the workflow context.

Example:

`Summary: {{myGemini.text}}`

If an upstream node stores its result under `myGemini` with a `text` property, the template can reference that value.

For an object that should be serialized as JSON, use the `json` helper:

`{{json myVariable}}`

The executor registers this helper to serialize the supplied value using `JSON.stringify`.

## How to Configure and Use the Node

1. Add the Slack node to the workflow.
2. Open its settings.
3. Enter a valid Variable Name.
4. Enter the Slack webhook URL.
5. Write the message content, using template expressions where needed.
6. Save the configuration.
7. Connect the Slack node after the trigger or action that provides the required data.
8. Execute the workflow and check the node's execution status.

The node's editor description displays a preview of the configured message content, or `Not configured` when no content is present.

## Message Processing

During execution, the Slack executor:

1. Publishes a `loading` status.
2. Checks that message content exists.
3. Compiles the content as a Handlebars template using the current workflow context.
4. Decodes HTML entities in the rendered message.
5. Checks that a webhook URL exists.
6. Sends a POST request to the webhook URL using `ky`.
7. Checks that a variable name exists.
8. Stores the result in the workflow context.
9. Publishes `success` if execution completes.

The request body is JSON with this structure:

```json
{
  "content": "Rendered message text"
}
```

## Output and Downstream References

The Slack executor adds a property to the workflow context using the configured Variable Name.

For example, if the variable name is `mySlack`, the output has this structure:

```json
{
  "mySlack": {
    "messageContent": "The rendered message"
  }
}
```

The stored `messageContent` is truncated to a maximum of 2,000 characters. The message sent to Slack is rendered before this truncation and is not truncated by this output-storage step.

A downstream node can reference the stored value with:

`{{mySlack.messageContent}}`

Replace `mySlack` with the Variable Name configured in the Slack node.

**Implementation note:** The current configuration dialog suggests `{{mySlack.text}}`, but the executor actually stores `messageContent`. Use `{{mySlack.messageContent}}` to reference the output produced by the current executor. The dialog hint should be corrected in the UI.

## Execution Status

The Slack node publishes status updates through the `slack-execution` realtime channel.

The status payload contains:

- `nodeId`: the node's ID.
- `status`: `loading`, `success`, or `error`.

The node UI subscribes to these updates using the node-status hook. Its server action obtains a realtime subscription token after checking authentication.

## Errors and Troubleshooting

### Message content is missing

The executor publishes an error status and throws a non-retriable error when message content is missing.

Add message content in the node configuration.

### Webhook URL is required

The executor publishes an error status and throws a non-retriable error if the webhook URL is missing.

Configure a valid webhook URL.

### Variable name is missing

The executor publishes an error status and throws a non-retriable error if the variable name is missing.

Set a valid variable name and save the node configuration.

The executor currently checks for the variable name after attempting the webhook request. If invalid or incomplete stored configuration bypasses the form validation, a Slack message could be sent before this error occurs.

### Slack does not receive the expected message

Check:

- The configured webhook URL.
- Whether the webhook accepts the `content` field in the JSON request.
- Whether template variables exist in the incoming workflow context.
- Whether the rendered message contains the expected values.

The executor rethrows errors encountered during execution after publishing an error status. This guide does not assume that every possible webhook or network error has the same retry behavior.

### A downstream node cannot read the Slack result

Use the configured Variable Name and the `messageContent` property. For example:

`{{mySlack.messageContent}}`

Do not rely on the dialog's current `.text` hint; it does not match the executor's output structure.

## Limitations

- The node sends a webhook request rather than using a Slack SDK in the inspected executor.
- The request body contains the rendered message under the `content` key.
- The stored output contains `messageContent`, truncated to 2,000 characters.
- The executor does not store a Slack message ID or the full webhook response in its returned context.
- The webhook URL must be configured for the node to send a message.
- The executor explicitly treats missing content, webhook URL, and variable name as non-retriable configuration errors.

## Source Code References

- `src/features/executions/components/slack/dialog.tsx` — configuration fields, validation, and template hint.
- `src/features/executions/components/slack/node.tsx` — node UI and saved configuration.
- `src/features/executions/components/slack/executor.ts` — message rendering, webhook request, output structure, and status updates.
- `src/features/executions/components/slack/actions.ts` — authenticated realtime token action.
- `src/inngest/channels/slack.ts` — realtime status channel.
- `src/features/executions/lib/executor-registry.ts` — executor registration.
- `src/config/node-components.ts` — node component registration.

## Verification Checklist

- [ ] The Slack node can be added to the editor.
- [ ] The Variable Name field validates the allowed format.
- [ ] The Webhook URL and Message Content fields are required.
- [ ] Template variables render using the workflow context.
- [ ] The `json` helper serializes objects.
- [ ] The webhook request sends JSON with a `content` property.
- [ ] The configured variable receives a `messageContent` property.
- [ ] Stored message content is limited to 2,000 characters.
- [ ] Loading, success, and error statuses are published.
- [ ] Missing required execution data produces the expected errors.
