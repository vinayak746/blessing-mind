
# Blessing: Discord Node Setup

## Purpose
The Discord node sends a message to a Discord channel using a webhook.

## Required configuration

### Webhook URL
The Discord webhook URL is required for execution.

The Blessing configuration form directs users to:
Channel Settings > Integrations > Webhooks.

Create or select a webhook in Discord and enter its URL in the Webhook URL field.

Treat webhook URLs as secrets. Do not share them publicly.

### Message Content
Message content is required.

The node supports Handlebars templates, allowing values from the workflow context to be inserted into a message.

Example shown in the Blessing UI:
Summary: {{myGemini.text}}

The executor renders the template against the workflow context before sending it.

Messages sent to Discord are limited to 2,000 characters.

### Variable Name
A variable name is required by the executor.

The configuration form suggests the example name:
myDiscord

The executor stores a result under this variable name, with a
messageContent property containing the message content.

Important: the form currently displays a `.text` reference example,
while the executor returns `messageContent`. Verify this discrepancy
before relying on either property in downstream nodes.

### Bot Username
This field is optional. If provided, it overrides the webhook's
default username. The executor limits it to 80 characters.

## Execution behavior
1. Blessing renders the message template using workflow context.
2. It sends a POST request to the configured webhook URL.
3. The node publishes a success status if execution succeeds.
4. If execution fails, the node publishes an error status.

## Troubleshooting
- If content is missing, provide message content.
- If the webhook URL is missing, configure the URL.
- If the webhook request fails, verify the URL and inspect the reported error.
- If downstream nodes need the Discord result, verify the correct output property.
