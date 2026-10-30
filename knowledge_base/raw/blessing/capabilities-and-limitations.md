# Blessing Authentication, Workflow Capabilities, and Limitations

## Authentication methods

Blessing supports the following sign-in methods through Better Auth:
- Email and password.
- Google OAuth.
- GitHub OAuth.

Google and GitHub sign-in require the relevant OAuth configuration.
See the Blessing README and authentication configuration for setup details.

## Database and PostgreSQL support

Blessing uses PostgreSQL as its application database through Prisma.
The application database stores Blessing's own application data.

The registered workflow node catalogue does not include a general-purpose
database-write node. Therefore, do not assume that a workflow can directly
insert arbitrary output into PostgreSQL using a built-in database node.

The existence of PostgreSQL support in the application does not mean that
a PostgreSQL workflow integration is available.

## Email sending

The registered workflow node catalogue does not include a dedicated
email-sending node. Do not assume that a workflow can send email directly
through a built-in email node.

The application has email-related service code, but an application-level
email service is not the same as a registered workflow node.

## Webhook triggers

The registered workflow node catalogue does not include a generic webhook
trigger. Do not assume that an arbitrary incoming webhook can start a
workflow through a built-in generic webhook-trigger node.

## How to answer capability questions

Distinguish between:
- Features implemented in the Blessing application itself.
- Nodes registered for use in visual workflows.
- External services that can be accessed through supported integrations.

Do not claim a workflow node exists unless it appears in the registered
node catalogue and executor registry. If a capability is not documented
or registered, explain that limitation rather than inventing a node.
