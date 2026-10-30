# Discord Incoming Webhooks

Document type: Official Discord developer documentation

Purpose: Creating and executing incoming webhooks to post messages into Discord channels.

Source URL: https://docs.discord.com/developers/platform/webhooks

Fetched at: 2026-10-19T10:56:16.389975+00:00

---

Discord supports two distinct types of webhooks that work in opposite directions: **incoming webhooks** for posting messages into Discord, and **webhook events** for receiving notifications from Discord when something happens in your app.

## Incoming Webhooks

Incoming webhooks are HTTP endpoints tied to a specific Discord channel. You POST a payload to the URL and the message appears in that channel. No bot or persistent connection required. See the [Webhook Resource](/developers/resources/webhook) for the full API reference.

This makes them ideal for one-way integrations where an external system needs to push data into Discord:

- CI/CD pipelines posting build results or deployment notifications
- Monitoring systems alerting on errors or anomalies
- External apps posting updates (GitHub commits, Jira tickets, form submissions)
- Scheduled digests or reports from cron jobs

If you need your app to also listen to events or respond to users, [building a Discord bot](/developers/platform/bots) is the better fit.

## Webhook Events

Webhook events work in the opposite direction. Discord POSTs to a public URL on your server when specific events occur in your app. Instead of your app polling the API, Discord pushes the notification to you.

You subscribe to the specific event types you care about through the Developer Portal, and Discord delivers them as signed HTTP POST requests to your endpoint. Your endpoint must validate Discord's request signatures and acknowledge events promptly.

Events you can subscribe to include:

- Application authorized or de-authorized by a user
- Entitlement created (a user purchased something from your app)
- Quest enrollment and completion events

For the full list of subscribable events and setup instructions, see the [Webhook Events](/developers/events/webhook-events) documentation.

## Further Reading

  <Card title="Webhook Resource Reference" href="/developers/resources/webhook" icon={} horizontal>
    Full API reference for incoming webhook endpoints and objects.
  
  <Card title="Webhook Events" href="/developers/events/webhook-events" icon={} horizontal>
    Subscribable event types and how to set up your endpoint to receive them.
