import { randomUUID } from 'crypto';

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

export function normalizeClawEvent(sessionId: string, raw: ClawRawEvent): ClawNormalizedEvent {
  const metadata = raw.metadata || {};
  const rawEvent = (metadata.raw_event as Record<string, unknown>) || {};
  const rawData = (metadata.rawdata as Record<string, unknown>) || {};
  const rawDataEvent = (rawData.raw_event as Record<string, unknown>) || {};

  // Resolve tool information early to help resolve toolCallId
  const tool =
    (raw.tool as Record<string, any>) ||
    (metadata.tool as Record<string, any>) ||
    (rawEvent.tool as Record<string, any>) ||
    (rawDataEvent.tool as Record<string, any>);

  // 1. Resolve actual event name
  let eventName = raw.event || '';
  if (eventName === 'ExternalAgentRunResponseContentEvent' || !eventName) {
    eventName =
      (metadata.event as string) ||
      (rawEvent.event as string) ||
      (rawDataEvent.event as string) ||
      eventName;
  }

  // 2. Resolve agent identity
  const agentId =
    raw.agent_id ||
    (metadata.agent_id as string) ||
    (rawEvent.agent_id as string) ||
    (rawDataEvent.agent_id as string);
  const agentName =
    raw.agent_name ||
    (metadata.agent_name as string) ||
    (rawEvent.agent_name as string) ||
    (rawDataEvent.agent_name as string);

  // 3. Resolve run identity
  const runId =
    raw.run_id ||
    (metadata.run_id as string) ||
    (rawEvent.run_id as string) ||
    (rawDataEvent.run_id as string);
  const parentRunId =
    raw.parent_run_id ||
    (metadata.parent_run_id as string) ||
    (rawEvent.parent_run_id as string) ||
    (rawDataEvent.parent_run_id as string);
  const parentAgentId =
    raw.parent_agent_id ||
    (metadata.parent_agent_id as string) ||
    (rawEvent.parent_agent_id as string) ||
    (rawDataEvent.parent_agent_id as string);
  const toolCallId =
    raw.tool_call_id ||
    (tool?.tool_call_id as string) ||
    (metadata.tool_call_id as string) ||
    (rawEvent.tool_call_id as string) ||
    (rawDataEvent.tool_call_id as string);

  // 4. Resolve content & reasoning
  const content =
    raw.content ||
    (metadata.content as string) ||
    (rawEvent.content as string) ||
    (rawDataEvent.content as string);
  const reasoningContent =
    raw.reasoning_content ||
    (metadata.reasoning_content as string) ||
    (rawEvent.reasoning_content as string) ||
    (rawDataEvent.reasoning_content as string);

  // 5. Resolve source
  let source: 'orchestrator' | 'subagent' | 'tool' | 'system' = 'orchestrator';
  if (runId && parentRunId) {
    source = 'subagent';
  } else if (eventName.startsWith('ToolCall')) {
    source = 'tool';
  } else if (agentId && agentId !== 'orchestrator' && !agentId.startsWith('orchestrator-')) {
    source = 'subagent';
  }

  // 6. Classify kind
  let kind: ClawNormalizedKind = 'message';

  if (eventName === 'RunStarted') {
    kind = 'agent_start';
  } else if (eventName === 'RunCompleted') {
    kind = 'agent_end';
  } else if (eventName === 'RunContent') {
    if (reasoningContent && !content) {
      kind = 'reasoning';
    } else {
      kind = 'message';
    }
  } else if (
    eventName === 'ReasoningStarted' ||
    eventName === 'ReasoningStep' ||
    eventName === 'ReasoningCompleted'
  ) {
    kind = 'reasoning';
  } else if (eventName === 'ToolCallStarted') {
    kind = 'tool_start';
  } else if (eventName === 'ToolCallCompleted') {
    kind = 'tool_end';
  } else if (eventName === 'ToolCallError') {
    kind = 'tool_error';
  } else if (eventName === 'RunError' || raw.error) {
    kind = 'error';
  }

  // Resolve tool information details
  const toolName = (tool?.name || tool?.tool_name) as string | undefined;
  const toolArgs = tool?.arguments || tool?.args || tool?.tool_args;
  const toolResult = tool?.result || tool?.output || tool?.tool_result;

  // Resolve error
  let errorMsg =
    typeof raw.error === 'string'
      ? raw.error
      : raw.error
        ? JSON.stringify(raw.error)
        : undefined;
  if (!errorMsg && metadata.error) {
    errorMsg =
      typeof metadata.error === 'string' ? metadata.error : JSON.stringify(metadata.error);
  }

  return {
    id: randomUUID(),
    sessionId,
    timestamp: raw.created_at || Date.now(),
    eventName,
    kind,
    source,
    agentId,
    agentName,
    runId,
    parentRunId,
    parentAgentId,
    toolCallId,
    toolName,
    content,
    reasoningContent,
    contentType: raw.content_type || (metadata.content_type as string),
    toolArgs,
    toolResult,
    error: errorMsg,
    metadata: metadata as Record<string, unknown>,
    raw,
  };
}
