# Blessing Node: Google Form Trigger

**Node type:** `GOOGLE_FORM_TRIGGER`  
**User-facing name:** Google Form  
**User-facing description:** When Form is submitted  
**Documentation status:** Source-reviewed; live end-to-end behavior has
not been independently tested.

## On this page

- [Overview](#1-what-this-node-does)
- [Open and configure](#2-where-to-find-it-and-open-its-settings)
- [Webhook URL](#3-webhook-url)
- [Apps Script setup](#4-google-apps-script-setup)
- [Payload format](#5-payload-format-what-the-generated-script-sends)
- [Webhook processing](#6-webhook-processing-what-blessing-does-with-the-payload)
- [Workflow variables](#7-workflow-variables-and-expressions)
- [Execution and status](#8-execution-and-status-behavior)
- [Troubleshooting](#9-troubleshooting)
- [Limitations](#10-limitations-and-unverified-behavior)
- [Evidence and references](#11-references-and-evidence)
- [Verification checklist](#12-verification-checklist)
- [Maintenance metadata](#13-documentation-metadata)



## 1. What this node does

The Google Form Trigger starts a Blessing workflow when a Google Form
submission is forwarded to Blessing's Google Form webhook endpoint.

The setup dialog displays a workflow-specific webhook URL and provides a
button to copy a Google Apps Script. The generated script reads the
submitted form's metadata and answers, then sends them to the webhook as
JSON.

The trigger is registered in both the visual node registry and the
workflow executor registry.

## 2. Where to find it and open its settings

1.  Add the **Google Form** trigger to a workflow.
2.  Open its settings using the node's settings control or double-click
    the node.
3.  In **Google Form Trigger Configuration**, copy the displayed
    **Webhook URL**.
4.  Use **Copy Google Apps Script** to copy the generated script, which
    already includes that webhook URL.

The node subscribes to the realtime channel
`google-form-trigger-execution` and the `status` topic to display
execution status.

## 3. Webhook URL

The dialog builds the URL as:

`{baseUrl}/api/webhooks/google-form?workflowId={workflowId}`

The base URL is taken from `NEXT_PUBLIC_APP_URL`; if that environment
variable is not set, the code falls back to `http://localhost:3000`.

**Important deployment note:** the fallback is a local development URL.
A Google Apps Script running outside your computer cannot generally
reach a service that is only listening on your local machine. Configure
`NEXT_PUBLIC_APP_URL` to a reachable deployment URL for real
submissions. This is a deployment implication of the URL construction; a
successful live deployment has not been verified as part of this source
review.

The URL includes the workflow ID as a query parameter. Keep it
associated with the intended workflow.

## 4. Google Apps Script setup

The configuration dialog presents these steps:

1.  Open the Google Form.
2.  Open the three-dot menu and choose **Script editor**.
3.  Paste the script provided by Blessing.
4.  Replace `WEBHOOK_URL` with the webhook URL shown in Blessing. The
    copy button generates a script with the URL already inserted.
5.  Save the script.
6.  Open **Triggers** and choose **Add Trigger**.
7.  Choose **From form** as the event source and **On form submit** as
    the event type, then save.

Google may ask you to authorize the script to access the form and make
the outgoing request. The exact prompts depend on Google's current
interface and account settings; they were not verified in the supplied
source.

## 5. Payload format: what the generated script sends

The script reads `e.response`, gets its item responses, and creates a
`responses` object. Each key is the form question title and each value
is the corresponding response returned by `getResponse()`.

It then sends a JSON payload with these fields:

  -----------------------------------------------------------------------
  Field                               Meaning in the source
  ----------------------------------- -----------------------------------
  `formId`                            ID of the form (`e.source.getId()`)

  `formTitle`                         Title of the form
                                      (`e.source.getTitle()`)

  `responseId`                        ID of the submitted response

  `timestamp`                         Submission timestamp

  `respondentEmail`                   Respondent email returned by
                                      `getRespondentEmail()`

  `responses`                         Object mapping question titles to
                                      answers
  -----------------------------------------------------------------------

The script sends the payload using `UrlFetchApp.fetch()` with method
`post`, content type `application/json`, and the JSON-stringified
payload.

The script catches request errors and logs `Webhook failed:` plus the
error to the Apps Script console. It does not rethrow the error in the
shown code.

### Example payload shape

This is an illustrative shape, not a captured live request:

``` json
{
  "formId": "FORM_ID",
  "formTitle": "Contact form",
  "responseId": "RESPONSE_ID",
  "timestamp": "TIMESTAMP_VALUE",
  "respondentEmail": "respondent@example.com",
  "responses": {
    "Name": "Example Person",
    "What do you need?": "Help with an order"
  }
}
```

The exact response values depend on the form's questions and answers. Do
not assume every field will always contain a non-empty value.

## 6. Webhook processing: what Blessing does with the payload

The route is `POST /api/webhooks/google-form`.

1.  It reads `workflowId` from the query string.
2.  If `workflowId` is missing, it returns HTTP `400` with an error
    indicating that the query parameter is required.
3.  It looks up the workflow by ID. If no workflow is found, it returns
    HTTP `404` with `Workflow not found`.
4.  It parses the request body as JSON.
5.  It constructs a `formData` object containing `formId`, `formTitle`,
    `responseId`, `timestamp`, `respondentEmail`, and `responses`, plus
    `raw`, which contains the complete request body.
6.  It calls `sendWorkflowExecution()` with the workflow ID and
    `initialData: { googleForm: formData }`.
7.  If that call completes, it returns HTTP `200` with
    `{ "success": true }`.
8.  If an error is caught by the route, it logs a message and returns
    HTTP `500` with `Failed to process Google Form submission`.

The route checks that the workflow exists. In the supplied route code,
no Google signature, shared secret, or other webhook authentication
check is visible. This source review alone does not establish what other
protections may exist elsewhere in the application or deployment.

## 7. Workflow variables and expressions

The configuration dialog advertises these expressions:

  ---------------------------------------------------------------------------------
  Expression                                    Purpose
  --------------------------------------------- -----------------------------------
  `{{googleForm.respondentEmail}}`              Respondent's email

  `{{googleForm.responses['Question Name']}}`   Answer for a question, addressed by
                                                its exact title

  `{{json googleForm.responses}}`               All answers represented as JSON
  ---------------------------------------------------------------------------------

The webhook places the submitted form data under the `googleForm` key in
the workflow's initial data. The execution engine initializes its
context from the event's `initialData`, and the Google Form Trigger
executor returns the context it receives.

Use the exact question title as the key in `googleForm.responses`. The
supplied source does not document how duplicate question titles or every
possible Google Forms answer type are handled downstream.

## 8. Execution and status behavior

The Google Form executor:

1.  Publishes node status `loading`.
2.  Runs an Inngest step named `google-form-trigger` that returns the
    incoming context unchanged.
3.  Publishes node status `success`.
4.  Returns that context.

The channel declares `loading`, `success`, and `error` as possible
status values. The shown Google Form executor publishes `loading` and
`success`; it does not itself publish `error` in the supplied
implementation.

The workflow engine receives `googleForm` in the initial context, then
processes workflow nodes in execution order. The Google Form executor
does not itself transform the form payload beyond passing through the
context.

## 9. Troubleshooting

### The setup dialog shows a localhost URL

Check `NEXT_PUBLIC_APP_URL`. The dialog falls back to
`http://localhost:3000` if it is unset. For an external Google Apps
Script to reach the application, the URL needs to resolve to a reachable
deployment.

### The webhook returns HTTP 400

The route requires the `workflowId` query parameter. Use the URL copied
from the intended workflow's configuration dialog.

### The webhook returns HTTP 404

The route could not find a workflow with the supplied ID. Re-copy the
URL from the correct workflow and verify that the workflow still exists.

### The webhook returns HTTP 500

The route catches processing errors and responds with a generic error.
Check the application server logs for `Google form webhook error:` and
inspect the underlying error without exposing secrets.

### The Apps Script logs "Webhook failed"

The generated script catches errors from `UrlFetchApp.fetch()` and logs
them. Inspect the Apps Script execution logs and confirm the URL is
correct and reachable. The shown script does not rethrow the error or
implement its own retry loop.

### The workflow starts but a downstream node cannot find an answer

Check the execution input/output and use the `googleForm.responses`
object. The keys are the question titles, so the expression must match
the title exactly. For the full answer object, use the expression shown
in the configuration dialog.

## 10. Limitations and unverified behavior

-   This node uses a Google Apps Script installable form-submit trigger;
    the supplied code does not show a direct OAuth connection between
    Blessing and Google Forms.
-   The webhook route checks for a workflow ID and verifies that the
    workflow exists. No webhook signature or shared-secret validation is
    visible in the supplied route implementation.
-   The generated Apps Script logs fetch errors but does not visibly
    retry failed webhook requests.
-   The webhook route forwards the raw payload under `googleForm.raw`,
    in addition to the selected fields.
-   The source files reviewed here do not prove that a production
    deployment, Google authorization, or end-to-end form submission has
    been tested successfully.
-   Handling of duplicate question titles, file-upload answers, and
    other specialized Google Forms response types is not established by
    these files.
-   The dialog's `localhost:3000` fallback is intended for local
    development and should not be assumed to work for external Google
    Apps Script requests.

## 11. References and evidence

### Blessing source of truth

These files establish what Blessing currently implements:

- `src/config/node-components.ts` — visual node registration.
- `src/features/executions/lib/executor-registry.ts` — executor registration.
- `src/features/triggers/components/google-form-trigger/node.tsx` — node label, settings dialog, and realtime status subscription.
- `src/features/triggers/components/google-form-trigger/dialog.tsx` — URL construction, setup instructions, copy controls, and advertised expressions.
- `src/features/triggers/components/google-form-trigger/utils.ts` — generated Apps Script and outgoing payload.
- `src/features/triggers/components/google-form-trigger/executor.ts` — status publishing and context pass-through.
- `src/app/api/webhooks/google-form/route.ts` — request validation, workflow lookup, initial data, and HTTP responses.
- `src/inngest/channels/google-form-trigger.ts` — realtime status channel.
- `src/inngest/functions.ts` — workflow initialization and node execution flow.
- `src/features/editor/hooks/use-workflow-validation.ts` — identifies Google Form Trigger as a workflow trigger.

### External platform references

These references explain Google Apps Script behavior. They do **not** override Blessing's implementation:

- [Installable Triggers — Google Apps Script](https://developers.google.com/apps-script/guides/triggers/installable) — installable form-submit triggers, authorization, and trigger restrictions.
- [Event Objects — Google Apps Script](https://developers.google.com/apps-script/guides/triggers/events) — the event object supplied to the form-submit handler.
- [FormResponse class — Google Apps Script](https://developers.google.com/apps-script/reference/forms/form-response) — response IDs, timestamps, respondent email, and item responses.

**Source precedence:** for what a Blessing node actually does, prefer the current Blessing source code and tests. Use official platform documentation only to explain behavior of the external platform. If the two sources appear to conflict, document the discrepancy rather than silently reconciling it.

## 12. Verification checklist

Before marking this guide as fully end-to-end verified, test in a development deployment:

- [ ] Copy the webhook URL and generated script from a real workflow.
- [ ] Configure and authorize the Apps Script form-submit trigger.
- [ ] Submit a form and confirm the webhook receives the payload.
- [ ] Confirm the workflow execution is created for the intended workflow.
- [ ] Confirm `googleForm.formId`, `googleForm.formTitle`, `googleForm.responseId`, `googleForm.timestamp`, `googleForm.respondentEmail`, `googleForm.responses`, and `googleForm.raw` are present as expected.
- [ ] Use one answer in a downstream node and confirm the expression resolves.
- [ ] Test missing `workflowId`, an unknown workflow ID, and a simulated processing failure.
- [ ] Review webhook access controls before exposing the endpoint publicly.

## 13. Documentation metadata

- **Document type:** Node reference and practical setup guide.
- **Product:** Blessing.
- **Node type:** `GOOGLE_FORM_TRIGGER`.
- **Primary evidence:** Blessing source files listed above.
- **Supplementary evidence:** Official Google Apps Script documentation listed above.
- **Verification level:** Source-reviewed; end-to-end behavior still needs a live test.
- **Maintenance rule:** Re-check this guide whenever the listed implementation files change.
