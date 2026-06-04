# WeSight Custom Agent Runtime Integration Implementation Guide

## Goal

This document describes how to integrate a custom Agent runtime into `wesight` so that it behaves like the existing cowork agent engines.

The target outcome is:

- the runtime is selectable through the same `CoworkAgentEngine` routing model used by other engines;
- the runtime starts through the same `startSession` / `continueSession` flow as other CLI-style agents;
- the runtime can issue requests without requiring any immediate user config migration;
- the renderer can correctly display orchestrator output, tool calls, subagent output, and agent hierarchy;
- `ExternalAgentRunResponseContentEvent` is normalized correctly, especially when the real content lives in `metadata`.

This guide does not require changing default user configuration files up front. The adapter only needs to issue the runtime request and consume the returned event stream.

## Non-Goals

- Do not introduce a parallel chat pipeline outside `cowork`.
- Do not make the renderer consume raw runtime payloads directly.
- Do not require immediate updates to user-facing config import or settings pages.
- Do not depend on `child_run_id` for hierarchy assembly.

## Reference Inputs

Implementation should be based on these sources:

- `wesight` cowork architecture: [architecture-openclaw-gui-cowork.md](file:///G:/MOMA/UI/wesight/docs/architecture-openclaw-gui-cowork.md)
- runtime API entrypoint: [orchestrator.py](file:///G:/MOMA/UI/llm-host-claw/src/api/routes/orchestrator.py)
- runtime request model: [orchestrator.py](file:///G:/MOMA/UI/llm-host-claw/src/api/models/orchestrator.py)
- runtime app entrypoint: [main.py](file:///G:/MOMA/UI/llm-host-claw/src/api/main.py)
- known-good event parsing reference: [page.tsx](file:///G:/MOMA/UI/llm-host-claw/swarm-ui/app/im/page.tsx)
- observed real stream payloads: `G:\MOMA\UI\log\run_20260430_165302.log`

## Existing WeSight Architecture Boundaries

The integration must fit into the existing cowork layers.

Main process routing and runtime contracts:

- [constants.ts](file:///G:/MOMA/UI/wesight/src/shared/cowork/constants.ts)
- [types.ts](file:///G:/MOMA/UI/wesight/src/main/libs/agentEngine/types.ts)
- [coworkEngineRouter.ts](file:///G:/MOMA/UI/wesight/src/main/libs/agentEngine/coworkEngineRouter.ts)
- [main.ts](file:///G:/MOMA/UI/wesight/src/main/main.ts)

Existing external-agent runtime pattern:

- [externalCliRuntimeAdapter.ts](file:///G:/MOMA/UI/wesight/src/main/libs/agentEngine/externalCliRuntimeAdapter.ts)
- [claudeRuntimeAdapter.ts](file:///G:/MOMA/UI/wesight/src/main/libs/agentEngine/claudeRuntimeAdapter.ts)
- [openclawRuntimeAdapter.ts](file:///G:/MOMA/UI/wesight/src/main/libs/agentEngine/openclawRuntimeAdapter.ts)

Renderer ingestion and display:

- [cowork.ts](file:///G:/MOMA/UI/wesight/src/renderer/services/cowork.ts)
- [coworkSlice.ts](file:///G:/MOMA/UI/wesight/src/renderer/store/slices/coworkSlice.ts)
- [cowork.ts](file:///G:/MOMA/UI/wesight/src/renderer/types/cowork.ts)
- [CoworkView.tsx](file:///G:/MOMA/UI/wesight/src/renderer/components/cowork/CoworkView.tsx)
- [CoworkSessionDetail.tsx](file:///G:/MOMA/UI/wesight/src/renderer/components/cowork/CoworkSessionDetail.tsx)
- [CoworkActivitySidebar.tsx](file:///G:/MOMA/UI/wesight/src/renderer/components/cowork/CoworkActivitySidebar.tsx)

## Required Integration Principle

The new runtime must be integrated as a new cowork engine, not as a special-case request path.

That means:

1. Add a new `CoworkAgentEngine` member for the runtime.
2. Register a dedicated runtime adapter in `CoworkEngineRouter`.
3. Keep using the standard cowork session lifecycle:
   - `SessionStart`
   - `SessionContinue`
   - `SessionStop`
   - stream events back through `cowork:stream:*`
4. Reuse the existing `runtimeSnapshot` and `ExternalAgentConfigSource` model so the runtime can be invoked with the same logical configuration flow as other external agents.

The runtime does not need to read or modify global user config files immediately. It only needs enough request-time data to issue the runtime call and stream responses back.

## Runtime Request Model

The runtime API behaves as follows:

- endpoint: `POST /api/orchestrator/run`
- content type: JSON request body
- response type: `text/event-stream`
- each SSE record emits `data: {json}`

Observed request fields:

```json
{
  "message": "user prompt",
  "extra": {
    "location": "上海"
  }
}
```

Observed optional request headers:

- `X-Userspace`
- `X-Sessionspace`
- `X-Workspace`
- `X-Runspace`
- `X-User-Id`
- `X-Record-Id`
- `X-Authorization`
- `X-Api-Key`

The adapter should support issuing requests with these headers when available from runtime context, but it should not block the first integration if only `message` is available.

## Event Stream Facts That Must Shape the Design

The real runtime stream is not a simple assistant-text delta stream.

Observed event families include:

- `RunStarted`
- `ModelRequestStarted`
- `RunContent`
- `ModelRequestCompleted`
- `ToolCallStarted`
- `ToolCallCompleted`
- `ToolCallError`
- `RunError`
- `ExternalAgentRunResponseContentEvent`

Critical facts:

1. Main orchestrator text usually appears in top-level `content` on `RunContent`.
2. Subagent output often appears inside `metadata.reasoning_content`, not top-level `content`.
3. `ExternalAgentRunResponseContentEvent` is often only a wrapper. The true event meaning may live in:
   - `metadata.event`
   - `metadata.raw_event.event`
   - `metadata.rawdata.raw_event.event`
4. Subagent identity may not exist on the top-level event. The true identity may live in:
   - `metadata.agent_id`
   - `metadata.agent_name`
   - `metadata.raw_event.agent_id`
   - `metadata.raw_event.agent_name`
5. `tool_call_id` is the most reliable join key between parent tool invocation and subagent stream.
6. `run_id` and `parent_run_id` are better hierarchy keys than `child_run_id`.
7. Chunks may be emitted at token or character granularity and must be aggregated.

## Recommended File Additions

Add these files:

- `src/main/libs/agentEngine/clawRuntimeAdapter.ts`
- `src/main/libs/agentEngine/clawRuntimeEvent.ts`
- `src/renderer/components/cowork/CoworkAgentHierarchyPanel.tsx`
- `src/renderer/components/cowork/CoworkAgentNodeDetail.tsx`

Optional if the hierarchy reducer grows large:

- `src/renderer/store/slices/coworkRuntimeState.ts`

## Required File Modifications

Modify these files:

- [constants.ts](file:///G:/MOMA/UI/wesight/src/shared/cowork/constants.ts)
- [types.ts](file:///G:/MOMA/UI/wesight/src/main/libs/agentEngine/types.ts)
- [coworkEngineRouter.ts](file:///G:/MOMA/UI/wesight/src/main/libs/agentEngine/coworkEngineRouter.ts)
- [main.ts](file:///G:/MOMA/UI/wesight/src/main/main.ts)
- [cowork.ts](file:///G:/MOMA/UI/wesight/src/renderer/types/cowork.ts)
- [coworkSlice.ts](file:///G:/MOMA/UI/wesight/src/renderer/store/slices/coworkSlice.ts)
- [cowork.ts](file:///G:/MOMA/UI/wesight/src/renderer/services/cowork.ts)
- [CoworkSessionDetail.tsx](file:///G:/MOMA/UI/wesight/src/renderer/components/cowork/CoworkSessionDetail.tsx)
- optionally [CoworkActivitySidebar.tsx](file:///G:/MOMA/UI/wesight/src/renderer/components/cowork/CoworkActivitySidebar.tsx)

## Step 1: Add a New Cowork Engine

In [constants.ts](file:///G:/MOMA/UI/wesight/src/shared/cowork/constants.ts):

1. Add a new engine constant to `CoworkAgentEngine`.
2. Add it to `CoworkAgentEngineValues`.
3. Decide whether it belongs in `CliCoworkAgentEngines`.

Recommended decision:

- Add it to `CoworkAgentEngineValues`.
- Add it to `CliCoworkAgentEngines` only if the product should present it under the same external-agent grouping as Codex, OpenCode, Qwen Code, and DeepSeek TUI.

Suggested constant shape:

```ts
export const CoworkAgentEngine = {
  ...,
  ClawRuntime: 'claw_runtime',
} as const;
```

This keeps the engine selectable through the same config field as other cowork engines.

## Step 2: Add Main-Process Runtime Adapter

Create `src/main/libs/agentEngine/clawRuntimeAdapter.ts`.

This adapter should implement `CoworkRuntime` and follow the same interface contract as existing runtime adapters.

Required behavior:

1. `startSession(sessionId, prompt, options)`
   - add the user message through the existing store flow unless `skipInitialUserMessage` is set;
   - create or reuse the assistant aggregation message for root orchestrator output;
   - issue the SSE request to the runtime.
2. `continueSession(sessionId, prompt, options)`
   - same behavior as `startSession`, but using the existing session.
3. `stopSession(sessionId)`
   - cancel the in-flight HTTP request or SSE reader;
   - emit `sessionStopped`.
4. `stopAllSessions()`
   - cancel all in-flight requests.
5. `respondToPermission()`
   - likely no-op unless the runtime exposes approval interrupts later.

The adapter should mirror the runtime lifecycle behavior already expected by `CoworkEngineRouter`.

## Step 3: Reuse Existing Request-Time Configuration Model

The runtime should behave like other external agents from the perspective of the request pipeline.

That means the adapter should accept and interpret:

- `options.agentEngine`
- `options.runtimeSnapshot`
- `options.runtimeSource`
- `options.agentId`
- `options.systemPrompt`
- `options.skillIds`

Recommended rule:

- Use `ExternalAgentConfigSource.WesightModel` when the request should use the active WeSight provider/model context.
- Use `ExternalAgentConfigSource.LocalCli` when the runtime should use its own local environment or server-side configuration.

For the first iteration, this only needs to affect the request payload and headers. No global config file sync is required.

Do not invent a new parallel config-source enum.

## Step 4: Add Raw Event and Normalized Event Types

In `src/main/libs/agentEngine/clawRuntimeEvent.ts`, define:

```ts
export interface ClawRawEvent {
  event?: string;
  created_at?: number;
  content?: string;
  reasoning_content?: string;
  type?: string;
  content_type?: string;
  agent_id?: string;
  agent_name?: string;
  run_id?: string;
  parent_run_id?: string;
  parent_agent_id?: string;
  session_id?: string;
  tool_call_id?: string;
  workflow_agent?: boolean;
  metadata?: Record<string, unknown> | null;
  tool?: Record<string, unknown> | null;
  error?: unknown;
}

export type ClawNormalizedKind =
  | 'agent_start'
  | 'agent_end'
  | 'message'
  | 'reasoning'
  | 'tool_start'
  | 'tool_end'
  | 'tool_error'
  | 'status'
  | 'error';

export interface ClawNormalizedEvent {
  id: string;
  sessionId: string;
  timestamp: number;
  eventName: string;
  kind: ClawNormalizedKind;
  source: 'orchestrator' | 'subagent' | 'tool' | 'system';
  agentId?: string;
  agentName?: string;
  runId?: string;
  parentRunId?: string;
  parentAgentId?: string;
  toolCallId?: string;
  toolName?: string;
  content?: string;
  reasoningContent?: string;
  contentType?: string;
  toolArgs?: unknown;
  toolResult?: unknown;
  error?: string;
  metadata: Record<string, unknown>;
  raw: ClawRawEvent;
}
```

Retaining `raw` is mandatory for debugging and forward-compatibility.

## Step 5: Normalize the Runtime Events

In the adapter, implement a normalization function that expands the wrapper structure used by subagent events.

Required metadata layers:

- `raw.metadata`
- `metadata.raw_event`
- `metadata.rawdata`
- `metadata.rawdata.raw_event`

Recommended helper shape:

```ts
interface MetadataLayers {
  metadata: Record<string, unknown>;
  rawEvent: Record<string, unknown>;
  rawData: Record<string, unknown>;
  rawDataEvent: Record<string, unknown>;
}
```

Required normalization rules:

1. If the top-level event is `ExternalAgentRunResponseContentEvent`, resolve the actual event name from nested metadata.
2. Prefer nested `agent_id` and `agent_name` for subagent events.
3. Prefer `metadata.reasoning_content` for subagent stream text.
4. Preserve `tool_call_id` exactly; do not synthesize a replacement.
5. Preserve `run_id`, `parent_run_id`, and `parent_agent_id` whenever available.
6. If a nested `RunError` or equivalent error event appears, normalize it as `kind = 'error'`.

Suggested event classification:

- `RunStarted` -> `agent_start`
- `RunCompleted` -> `agent_end`
- `RunContent` with top-level orchestrator content -> `message`
- `ReasoningStarted` / `ReasoningStep` / `ReasoningCompleted` -> `reasoning`
- `ToolCallStarted` -> `tool_start`
- `ToolCallCompleted` -> `tool_end`
- `ToolCallError` -> `tool_error`
- nested subagent `RunContent` with reasoning-like payload -> `reasoning`
- nested subagent `RunContent` with content payload -> `message`
- `RunError` -> `error`

## Step 6: Do Not Force Everything Into `messageUpdate`

The existing renderer pipeline assumes `messageUpdate` is a content update for one message.

That is not enough for subagent hierarchy.

Add new runtime stream channels to [constants.ts](file:///G:/MOMA/UI/wesight/src/shared/cowork/constants.ts):

- `CoworkIpcChannel.StreamRuntimeEvent`
- optional `CoworkIpcChannel.StreamRuntimeSnapshot`

Recommended first iteration:

- use `StreamRuntimeEvent` only;
- let the renderer build the hierarchy state incrementally.

Keep the old `StreamMessage` and `StreamMessageUpdate` behavior for the main conversation transcript.

## Step 7: Extend Main Runtime Event Contract

In [types.ts](file:///G:/MOMA/UI/wesight/src/main/libs/agentEngine/types.ts), extend `CoworkRuntimeEvents` with a new event:

```ts
runtimeEvent: (sessionId: string, event: ClawNormalizedEvent) => void;
```

If the repository prefers a more generic name, use one that can also support future engines, but keep the payload normalized.

Then update [coworkEngineRouter.ts](file:///G:/MOMA/UI/wesight/src/main/libs/agentEngine/coworkEngineRouter.ts) so this event is forwarded exactly like the existing `message` and `messageUpdate` events.

## Step 8: Register the New Engine in the Router

In [coworkEngineRouter.ts](file:///G:/MOMA/UI/wesight/src/main/libs/agentEngine/coworkEngineRouter.ts):

1. Add the new runtime to `RouterDeps`.
2. Add it to `runtimeByEngine`.
3. Bind runtime events for the new engine.

This is what makes the runtime behave like the other cowork engines.

Do not create a side-channel launcher outside `CoworkEngineRouter`.

## Step 9: Wire IPC in `main.ts`

In [main.ts](file:///G:/MOMA/UI/wesight/src/main/main.ts):

1. instantiate the new adapter;
2. pass it into `CoworkEngineRouter`;
3. forward `runtimeEvent` to renderer subscribers through the new IPC channel;
4. keep session subscription semantics identical to other cowork stream events.

The renderer must receive these events through the same subscription lifecycle already used for cowork sessions.

## Step 10: Extend Renderer Types

In [cowork.ts](file:///G:/MOMA/UI/wesight/src/renderer/types/cowork.ts), add a renderer-side runtime-state model.

Recommended types:

```ts
export interface AgentTimelineItem {
  id: string;
  nodeId: string;
  kind: 'message' | 'reasoning' | 'tool_start' | 'tool_end' | 'tool_error' | 'status' | 'error';
  timestamp: number;
  text?: string;
  toolCallId?: string;
  toolName?: string;
  metadata?: Record<string, unknown>;
}

export interface AgentToolCall {
  toolCallId: string;
  toolName: string;
  status: 'running' | 'completed' | 'error';
  startedAt: number;
  finishedAt?: number;
  args?: unknown;
  result?: unknown;
  error?: string;
  spawnedNodeId?: string;
}

export interface AgentHierarchyNode {
  nodeId: string;
  sessionId: string;
  source: 'orchestrator' | 'subagent';
  agentId?: string;
  agentName?: string;
  runId?: string;
  parentRunId?: string;
  parentAgentId?: string;
  parentNodeId?: string;
  toolCallId?: string;
  status: 'pending' | 'running' | 'completed' | 'error';
  startedAt: number;
  updatedAt: number;
  title: string;
  content: string;
  reasoning: string;
  timelineItemIds: string[];
  toolCallIds: string[];
  childNodeIds: string[];
  unresolvedParent?: boolean;
}

export interface CoworkRuntimeState {
  rootNodeIds: string[];
  nodesById: Record<string, AgentHierarchyNode>;
  timelineById: Record<string, AgentTimelineItem>;
  toolCallsById: Record<string, AgentToolCall>;
  runIdToNodeId: Record<string, string>;
  toolCallIdToNodeId: Record<string, string>;
}
```

Keep this state separate from the transcript-oriented `CoworkMessage[]` model.

## Step 11: Add Renderer Subscription and Reducers

In [cowork.ts](file:///G:/MOMA/UI/wesight/src/renderer/services/cowork.ts):

1. subscribe to the new runtime event IPC channel;
2. dispatch a new Redux action such as `appendRuntimeEvent(sessionId, event)`.

In [coworkSlice.ts](file:///G:/MOMA/UI/wesight/src/renderer/store/slices/coworkSlice.ts), add reducers to:

- create runtime nodes;
- append node reasoning;
- append node content;
- create and finalize tool calls;
- attach children to parents;
- update main transcript summary messages.

The store should own the hierarchy assembly, not the React components.

## Step 12: Hierarchy Assembly Rules

Use these parent-resolution rules in order:

1. `parent_run_id`
2. `tool_call_id`
3. `parent_agent_id`
4. fallback to root node list

Use these node identity rules in order:

1. `run_id`
2. `tool_call_id`
3. `agent_id + firstTimestamp`

Recommended node key shape:

```ts
const nodeKey =
  runId
    ? `run:${runId}`
    : toolCallId
      ? `tool:${toolCallId}`
      : agentId
        ? `agent:${agentId}:${bucket}`
        : `anon:${timestamp}`;
```

If a node cannot be attached immediately, set `unresolvedParent = true` and retry linking when later events arrive.

## Step 13: Main Transcript Rules

Do not dump all subagent text into the main assistant transcript.

Recommended transcript policy:

1. User prompt becomes a normal `user` message.
2. Root orchestrator `RunContent` becomes the main assistant transcript stream.
3. Subagent streams update hierarchy nodes, not the main assistant bubble.
4. Tool start/end/error may emit concise system summaries, but detailed tool state belongs in runtime state.

This preserves readability and avoids mixing orchestrator text with subagent reasoning.

## Step 14: UI Rendering Plan

In [CoworkSessionDetail.tsx](file:///G:/MOMA/UI/wesight/src/renderer/components/cowork/CoworkSessionDetail.tsx):

1. keep the existing conversation transcript rendering;
2. add an `Execution` or `Agent Hierarchy` section;
3. render the runtime tree separately from the flat message timeline.

Recommended first UI iteration:

- left column: agent hierarchy list
- right column: selected node detail

Each hierarchy node should show:

- `agentName` or fallback title
- status
- latest reasoning preview
- latest content preview
- tool count
- child count

Each node detail view should show:

- reasoning text
- content text
- tool calls
- tool results
- timeline items

Do not start with a complex DAG canvas. A structured list is enough for the first correct implementation.

## Step 15: Sidebar Enhancements

If needed, update [CoworkActivitySidebar.tsx](file:///G:/MOMA/UI/wesight/src/renderer/components/cowork/CoworkActivitySidebar.tsx) to surface:

- active subagent name
- recent tool calls
- failed nodes
- unresolved parent links

This component should complement the hierarchy panel, not replace it.

## Step 16: Compatibility With Existing CLI-Agent UX

To keep the user experience aligned with existing CLI agents:

1. The runtime must be started through the same cowork engine selection field.
2. The runtime must honor the same session lifecycle and subscription flow.
3. The runtime should accept `runtimeSnapshot` when the request originates from WeSight model settings.
4. The runtime should also allow execution without immediate settings migration when its server-side environment already knows how to resolve auth or workspace context.
5. The renderer should remain engine-agnostic at the transcript layer.

In practical terms, the new engine should feel like Codex, OpenCode, or Qwen Code from the GUI perspective:

- selectable as an engine;
- invoked by starting a normal cowork session;
- streamed into the same conversation view;
- augmented with engine-specific runtime hierarchy rendering.

## Step 17: Minimum Viable Integration Checklist

The first acceptable implementation should satisfy all of the following:

- `CoworkAgentEngine` includes the new engine.
- `CoworkEngineRouter` can route start and continue requests to the new adapter.
- the adapter can issue `POST /api/orchestrator/run`.
- SSE `data:` frames are parsed safely.
- top-level `RunContent` appears in the main assistant transcript.
- `ExternalAgentRunResponseContentEvent` is parsed through nested metadata.
- subagent output is rendered under a separate hierarchy node.
- tool start/end/error are visible in the UI.
- the first-level hierarchy is stable across one full session.

## Step 18: Important Edge Cases

Handle these cases explicitly:

1. `ExternalAgentRunResponseContentEvent` with empty top-level `agent_id` and `agent_name`.
2. subagent output where only `reasoning_content` exists.
3. top-level `content` present while `metadata` is null.
4. `ToolCallCompleted` arriving before all subagent chunks are received.
5. multiple subagent streams belonging to different `tool_call_id` values in one session.
6. highly fragmented content chunks.

## Step 19: Debugging Recommendation

Add a development-only raw event inspector.

Recommended data to display per event:

- `eventName`
- `kind`
- `toolCallId`
- `runId`
- `parentRunId`
- `agentName`
- `source`
- selected metadata payload

This greatly reduces debugging time when the runtime payload evolves.

## Step 20: Verification Plan

After implementation, verify with at least these scenarios:

1. simple prompt that returns only root orchestrator content;
2. prompt that triggers one tool call with one subagent;
3. prompt that triggers multiple tool calls;
4. prompt that causes a tool error;
5. prompt that emits reasoning-only subagent chunks;
6. stop-session while SSE is still active.

Recommended commands:

```bash
npm run lint
npx tsc --noEmit
npm run electron:dev
```

If stream/render logic is covered by replay tests in your branch, also run the relevant replay or event integration tests.

## Implementation Summary

The key design decision is this:

The custom runtime must be integrated as a normal cowork engine, but its event stream must be normalized into a richer runtime-state model before rendering.

That gives WeSight these properties at the same time:

- consistent engine selection and request flow with other CLI agents;
- no forced config migration on day one;
- correct handling of subagent wrapper events;
- correct agent hierarchy rendering;
- no contamination of the main transcript with low-level runtime event noise.

If implementation choices conflict, prefer consistency with the existing cowork engine lifecycle over short-term shortcuts.
