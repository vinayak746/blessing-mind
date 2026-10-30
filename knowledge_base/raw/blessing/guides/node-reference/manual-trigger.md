# Manual Trigger Node

## Overview

The Manual Trigger node is used to start a workflow manually from the workflow editor. It is intended for workflows that should run when a user explicitly clicks **Execute Workflow**, rather than waiting for an external event.

The node is registered as `NodeType.MANUAL_TRIGGER` and is implemented by `ManualTriggerNode`. Its executor returns the current workflow context unchanged.

## When to Use It

Use the Manual Trigger when:
- You want to start a workflow yourself from the editor.
- You want to test a workflow without waiting for an external trigger event.
- You want to execute connected action nodes as part of a manually started workflow.

Do not use it when the workflow must start automatically from an external event, such as a Google Forms submission or a Stripe event. Use the appropriate event-trigger node for those cases.

## Configuration

The Manual Trigger has no configurable parameters.

Opening its settings displays a dialog titled **Manual Trigger** with an informational description. There are no input fields or configuration options to complete.

## How to Execute a Workflow

1. Open the workflow in the editor.
2. Add a Manual Trigger node if the workflow should start manually.
3. Connect the trigger's output handle to the next node in the workflow.
4. Configure the downstream action nodes as required.
5. Click **Execute Workflow** in the editor.
6. Wait for the workflow execution to finish and inspect the execution status of the nodes.

The Execute Workflow button checks whether the workflow can run. If validation errors are present, it opens a dialog explaining the issues that need to be fixed.

Before starting execution, the button waits for the latest editor changes to be saved when a save-before-execute callback is provided. If saving fails, execution is cancelled so an older version of the workflow is not run accidentally.

## Input and Output Behavior

The Manual Trigger executor receives the current workflow context and returns it unchanged.

Conceptually:

- Input: the existing workflow context.
- Processing: no additional data is collected or transformed by the trigger.
- Output: the same context, passed to downstream nodes.

The trigger does not provide a form for entering runtime input. Any data required by later nodes must be available through the workflow's execution context or supplied through the relevant node configuration and execution mechanisms.

## Execution Status

The executor publishes realtime status updates using the `manual-trigger-execution` channel.

The status topic includes:
- `nodeId`: the ID of the node being updated.
- `status`: the execution status, represented by `loading`, `success`, or `error`.

During execution, the executor publishes `loading`, runs the `manual-trigger` step with the current context, and then publishes `success`.

The Manual Trigger node subscribes to its status updates through the node-status hook. It obtains a realtime subscription token through `fetchManualTriggerRealtimeToken`, which requires authentication.

The current executor implementation explicitly publishes `loading` and `success`. Although `error` is included in the channel's status type, this executor does not explicitly publish an error status in the code inspected for this guide.

## Workflow Validation and Connections

The workflow validation logic recognizes `MANUAL_TRIGGER` as a trigger type.

Relevant validation behavior includes:
- Only one Manual Trigger is allowed in a workflow.
- Workflow cycles are checked by the validation logic.
- A trigger without an outgoing connection produces a warning.
- A workflow containing action nodes but no trigger is subject to validation.

Connect the Manual Trigger output to the node that should execute next. Ensure the workflow passes validation before running it.

## Troubleshooting

### The workflow cannot run

Check the validation dialog in the editor. Fix the reported errors before trying again.

### The workflow runs an older version

The Execute Workflow button attempts to save the latest editor changes before execution. If saving fails, the run is cancelled. Check the connection and try again.

### The trigger has no downstream activity

Check that the Manual Trigger is connected to the intended next node and that downstream nodes are configured correctly.

### The settings dialog has no fields

This is expected. The Manual Trigger currently has no configurable settings.

### The node status does not update

Check that the application is authenticated and that the realtime subscription can be established. The Manual Trigger obtains a subscription token through its server action and listens to the `manual-trigger-execution` status channel.

## Limitations

- The node has no configurable parameters.
- It does not collect user input when the workflow starts.
- Its executor passes the existing workflow context through unchanged.
- The current executor explicitly publishes loading and success status updates.

## Source Code References

- `src/features/triggers/components/manual-trigger/node.tsx` — node UI and realtime status subscription.
- `src/features/triggers/components/manual-trigger/dialog.tsx` — settings dialog.
- `src/features/triggers/components/manual-trigger/executor.ts` — execution behavior and context pass-through.
- `src/features/triggers/components/manual-trigger/actions.ts` — authenticated realtime token action.
- `src/inngest/channels/manual-trigger.ts` — realtime channel and status payload.
- `src/inngest/functions.ts` — workflow execution orchestration and node execution.
- `src/features/editor/components/execute-workflow-button.tsx` — execute action, validation handling, and save-before-execute behavior.
- `src/features/editor/hooks/use-workflow-validation.ts` — trigger and workflow validation.
- `src/features/workflows/server/routers.ts` — workflow execution request handling.
- `src/inngest/utils.ts` — workflow execution event dispatch.
- `src/features/executions/lib/executor-registry.ts` — executor registration.
- `src/config/node-components.ts` — node component registration.

## Verification Checklist

- [ ] The Manual Trigger can be added to the editor.
- [ ] Opening its settings shows the informational dialog without configuration fields.
- [ ] The node can be connected to a downstream action.
- [ ] A valid workflow can be started with Execute Workflow.
- [ ] The latest editor changes are saved before execution when the save callback is provided.
- [ ] A failed save prevents execution.
- [ ] The executor returns the incoming context unchanged.
- [ ] Realtime loading and success status updates are published.
- [ ] Validation prevents multiple Manual Trigger nodes in one workflow.
