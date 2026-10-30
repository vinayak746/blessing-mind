# HTTP Request Node

## 1. Overview

The HTTP Request node sends an outbound HTTP request to an API or other HTTP endpoint during workflow execution.

It supports five HTTP methods, allows Handlebars templates to reference values from the current workflow context, and stores the response under a configurable variable name for downstream nodes.

**Node type:** `HTTP_REQUEST`

**Default method:** `GET`

**Realtime status channel:** `http-request-execution`

## 2. Configuration

### 2.1 Variable Name

**Required.** Defines the key under which the HTTP response is stored in the workflow context.

The name must match this pattern:

`^[A-Za-z_$][A-Za-z0-9_$]*$`

It must start with a letter, underscore, or dollar sign. Subsequent characters may include letters, numbers, underscores, and dollar signs.

Example:

`myApiCall`

After a successful request, downstream nodes can reference the response using:

- `{{myApiCall.httpResponse.status}}`
- `{{myApiCall.httpResponse.statusText}}`
- `{{myApiCall.httpResponse.data}}`

Replace `myApiCall` with the actual variable name configured in the node.

### 2.2 Endpoint URL

**Required.** Specifies the endpoint to which the request is sent.

The endpoint can be a static URL or a Handlebars template that uses values from the current workflow context.

Static example:

`https://api.example.com/users`

Dynamic example:

`https://api.example.com/users/{{previousStep.httpResponse.data.id}}`

The dynamic example assumes that `previousStep` exists in the workflow context and contains the referenced response structure.

The form validates that the endpoint is nonempty. The displayed Zod schema does not validate URL syntax.

### 2.3 HTTP Method

The node supports the following methods:

| Method | Purpose |
|---|---|
| `GET` | Retrieve information from an endpoint. |
| `POST` | Send data to an endpoint. |
| `PUT` | Send data, commonly to create or replace a resource. |
| `PATCH` | Send data to update a resource. |
| `DELETE` | Request deletion of a resource. |

The behavior of each method ultimately depends on the target API.

The editor defaults to `GET`.

### 2.4 Request Body

The request body field is displayed for `POST`, `PUT`, and `PATCH`.

It accepts text containing a Handlebars template. The executor resolves the template against the current workflow context before sending the request.

Example:

```json
{
  "userId": "{{previousStep.httpResponse.data.id}}",
  "name": "{{previousStep.httpResponse.data.name}}"
}
```

This example assumes the referenced values exist in the workflow context.

After resolving the template, the executor attempts to parse the result as JSON.

- If parsing succeeds, the executor sets `Content-Type: application/json`.
- If parsing fails, the executor sets `Content-Type: text/plain`.

The resolved body is then sent with the request.

The current editor does not expose a body field for `GET` or `DELETE`.

## 3. Template Variables and JSON Serialization

The executor uses Handlebars to process the endpoint and request body with the current workflow context.

### 3.1 Referencing a Value

Example:

`{{previousStep.httpResponse.data.id}}`

Use the correct variable name and property path for the data produced by an earlier workflow step.

### 3.2 Serializing an Object

The executor registers a custom Handlebars helper named `json`.

Example:

`{{json previousStep.httpResponse.data}}`

This helper uses `JSON.stringify` with two-space indentation and returns the result as a Handlebars `SafeString`.

Use it when you need an object represented as JSON text rather than a default string representation.

**Important:** Template expressions depend on the actual structure of the workflow context. The examples in this document are illustrative; confirm the source variable and property names in your workflow.

## 4. Response Structure

After a successful request, the executor preserves the existing workflow context and adds a property using the configured variable name.

For example, if the variable name is `myApiCall`, the resulting context has this structure:

```json
{
  "myApiCall": {
    "httpResponse": {
      "status": 200,
      "statusText": "OK",
      "data": {
        "id": 123,
        "name": "Example"
      }
    }
  }
}
```

The status code, status text, and response data above are illustrative, not guaranteed values.

### 4.1 Available Response Properties

| Expression | Description |
|---|---|
| `{{myApiCall.httpResponse.status}}` | HTTP response status code. |
| `{{myApiCall.httpResponse.statusText}}` | HTTP response status text. |
| `{{myApiCall.httpResponse.data}}` | Parsed response data. |

### 4.2 How Response Data Is Parsed

The executor checks the response's `Content-Type` header.

- If the content type contains `application/json`, the response is parsed as JSON.
- Otherwise, the response is read as text.

Consequently, `httpResponse.data` can contain an object, array, string, or another JSON value, depending on the endpoint response.

The node does not expose response headers in the returned `httpResponse` object shown in the inspected executor.

## 5. Execution Lifecycle and Status

The executor performs the following operations:

1. Publishes a `loading` status for the node.
2. Runs the request inside an Inngest step named `http-request`.
3. Checks that the endpoint, variable name, and method are configured.
4. Resolves the endpoint and, when applicable, the request body using Handlebars.
5. Sends the HTTP request using `ky`.
6. Parses the response according to its content type.
7. Preserves the existing context and adds the configured response variable.
8. Publishes `success` and returns the updated context.

If execution throws an error, the executor publishes `error` and rethrows the error.

The realtime channel is named `http-request-execution`.

The editor's node component subscribes to this channel to display the node's status.

## 6. Error Handling

The executor throws an Inngest `NonRetriableError` when required configuration is missing:

- `HTTP Request node: No endpoint configured`
- `HTTP Request node: Variable name not configured`
- `HTTP Request node: Method not configured`

The executor publishes an error status for these failures and rethrows errors caught during execution.

The request uses `ky`. The inspected executor does not configure `throwHttpErrors`, so unsuccessful HTTP status codes are subject to `ky`'s default HTTP-error behavior. Do not assume that every non-2xx response will be returned as a normal `httpResponse` object.

The executor does not show custom request retry logic or an explicitly configured timeout in the supplied source.

## 7. Limitations of the Current Node UI

Based on the inspected configuration form and executor, the node does not expose configurable fields for:

- Custom request headers.
- Authentication credentials or authentication schemes.
- A configurable timeout.
- A configurable retry policy.
- A request body for `GET` or `DELETE`.

For `POST`, `PUT`, and `PATCH`, the executor sets the `Content-Type` header based on whether the resolved body parses as JSON.

These observations describe the implementation inspected for this document. They should be rechecked if the node's source code changes.

## 8. Troubleshooting

### The node says the endpoint is not configured

Provide a nonempty endpoint URL and verify that any template expressions reference values available in the workflow context.

### The node says the variable name is not configured

Set a variable name that satisfies the documented naming pattern.

### The node says the method is not configured

Select one of the supported methods: `GET`, `POST`, `PUT`, `PATCH`, or `DELETE`.

### A downstream node cannot access the response

Verify the configured variable name and use the correct path.

For example, if the variable name is `myApiCall`, use:

`{{myApiCall.httpResponse.data}}`

Do not assume that `httpResponse` is itself the top-level workflow variable.

### The response data is a string instead of an object

Check the response's `Content-Type` header. The executor parses JSON only when the content type contains `application/json`; otherwise, it reads the response as text.

### The HTTP request fails for an unsuccessful status code

Check the endpoint and API response. The executor uses `ky` without an explicit override of its default HTTP-error behavior. An unsuccessful status may therefore throw an error instead of returning the normal response structure.

### The API requires authentication or custom headers

The inspected node form does not provide configuration fields for these settings. Confirm whether the current implementation supports the required API configuration elsewhere before assuming the node can send the request successfully.

## 9. Source Code References

The following files implement or register the HTTP Request node:

- `src/features/executions/components/http-request/dialog.tsx` — configuration fields, defaults, and form validation.
- `src/features/executions/components/http-request/executor.ts` — request execution, templating, response parsing, and error handling.
- `src/features/executions/components/http-request/node.tsx` — editor node, saved configuration, and realtime status display.
- `src/features/executions/components/http-request/actions.ts` — realtime token action.
- `src/inngest/channels/http-request.ts` — realtime status channel.
- `src/features/executions/lib/executor-registry.ts` — executor registration.
- `src/config/node-components.ts` — editor component registration.

## 10. Verification Checklist

Before treating this document as fully verified, test the node in a real workflow:

- [ ] Successful `GET` request.
- [ ] Successful `POST` request with a JSON body.
- [ ] Successful `PUT` and `PATCH` requests.
- [ ] Successful `DELETE` request.
- [ ] Dynamic endpoint using a value from an earlier node.
- [ ] Dynamic request body using context variables.
- [ ] Object serialization using the `json` helper.
- [ ] JSON response parsing.
- [ ] Plain-text response parsing.
- [ ] Missing required configuration.
- [ ] Unsuccessful HTTP status and request failure behavior.
- [ ] Response variable available to a downstream node.

Record any differences between observed behavior and this document, and update the documentation from the actual implementation rather than assumptions.
