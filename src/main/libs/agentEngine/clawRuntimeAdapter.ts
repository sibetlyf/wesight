import type { PermissionResult } from '@anthropic-ai/claude-agent-sdk';
import { net } from 'electron';
import { EventEmitter } from 'events';
import fs from 'fs';
import os from 'os';
import path from 'path';

import { CoworkAgentEngine } from '../../../shared/cowork/constants';
import type { CoworkMessage, CoworkMessageMetadata, CoworkStore } from '../../coworkStore';
import { resolveRawApiConfig } from '../claudeSettings';
import { type ClawNormalizedEvent, type ClawRawEvent, normalizeClawEvent } from './clawRuntimeEvent';
import type { CoworkContinueOptions, CoworkRuntime, CoworkRuntimeEvents, CoworkStartOptions } from './types';

type ActiveClawSession = {
  sessionId: string;
  controller: AbortController;
  assistantMessageId: string | null;
  assistantContent: string;
  initialMessageCount: number;
};

type ClawRuntimeAdapterDeps = {
  store: CoworkStore;
};

const STREAMING_TEXT_MAX_CHARS = 120_000;
const CONTENT_TRUNCATED_HINT = '\n...[truncated to prevent memory pressure]';

const truncateLargeContent = (content: string, maxChars: number): string => {
  if (content.length <= maxChars) return content;
  return `${content.slice(0, maxChars)}${CONTENT_TRUNCATED_HINT}`;
};

export class ClawRuntimeAdapter extends EventEmitter implements CoworkRuntime {
  private readonly store: CoworkStore;
  private readonly activeSessions = new Map<string, ActiveClawSession>();
  private readonly stoppedSessions = new Set<string>();

  constructor(deps: ClawRuntimeAdapterDeps) {
    super();
    this.store = deps.store;
  }

  override on<U extends keyof CoworkRuntimeEvents>(
    event: U,
    listener: CoworkRuntimeEvents[U],
  ): this {
    return super.on(event, listener);
  }

  override off<U extends keyof CoworkRuntimeEvents>(
    event: U,
    listener: CoworkRuntimeEvents[U],
  ): this {
    return super.off(event, listener);
  }

  async startSession(sessionId: string, prompt: string, options: CoworkStartOptions = {}): Promise<void> {
    await this.runTurn(sessionId, prompt, options, !options.skipInitialUserMessage);
  }

  async continueSession(sessionId: string, prompt: string, options: CoworkContinueOptions = {}): Promise<void> {
    await this.runTurn(sessionId, prompt, options, true);
  }

  stopSession(sessionId: string): void {
    this.stoppedSessions.add(sessionId);
    const active = this.activeSessions.get(sessionId);
    if (active) {
      active.controller.abort();
      this.activeSessions.delete(sessionId);
    }
    this.store.updateSession(sessionId, { status: 'idle' });
    this.emit('sessionStopped', sessionId);
  }

  stopAllSessions(): void {
    for (const sessionId of Array.from(this.activeSessions.keys())) {
      this.stopSession(sessionId);
    }
  }

  respondToPermission(_requestId: string, _result: PermissionResult): void {
    // Claw runtime runs non-interactively or handles permissions internally.
  }

  isSessionActive(sessionId: string): boolean {
    return this.activeSessions.has(sessionId);
  }

  getSessionConfirmationMode(_sessionId: string): 'modal' | 'text' | null {
    return null;
  }

  onSessionDeleted(sessionId: string): void {
    this.stopSession(sessionId);
    this.stoppedSessions.delete(sessionId);
  }

  private async runTurn(
    sessionId: string,
    prompt: string,
    options: CoworkStartOptions | CoworkContinueOptions,
    shouldAddUserMessage: boolean,
  ): Promise<void> {
    if (this.activeSessions.has(sessionId)) {
      throw new Error('This session is already running.');
    }
    this.stoppedSessions.delete(sessionId);
    const session = this.store.getSession(sessionId);
    if (!session) {
      throw new Error(`Session ${sessionId} not found`);
    }

    this.store.updateSession(sessionId, { status: 'running' });

    if (shouldAddUserMessage) {
      const metadata: Record<string, unknown> = {};
      if (options.skillIds?.length) {
        metadata.skillIds = options.skillIds;
      }
      if (options.imageAttachments?.length) {
        metadata.imageAttachments = options.imageAttachments;
      }
      const message = this.store.addMessage(sessionId, {
        type: 'user',
        content: prompt,
        metadata: Object.keys(metadata).length > 0 ? metadata : undefined,
      });
      this.emit('message', sessionId, message);
    }

    const currentSession = this.store.getSession(sessionId);
    const cwd = path.resolve(currentSession?.cwd || this.store.getConfig().workingDirectory || os.homedir());

    // Set up Claw Environment Headers
    // 后端 EnVar 校验要求：sessionspace ⊇ userspace, workspace ⊇ sessionspace, runspace ⊇ workspace
    // 因此将 userspace 设为 cwd 的父目录，其余三个都设为 cwd 本身
    const userspace = path.dirname(cwd);
    const sessionspace = cwd;
    const workspace = cwd;
    const runspace = cwd;

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'X-Userspace': userspace,
      'X-Sessionspace': sessionspace,
      'X-Workspace': workspace,
      'X-Runspace': runspace,
      'X-User-Id': 'wesight_claw_user',
      'X-Record-Id': sessionId,
    };

    // Extract API key if available
    const apiConfigOverride = options.runtimeSnapshot
      ? {
        modelId: options.runtimeSnapshot.modelId,
        providerName: options.runtimeSnapshot.providerKey || options.runtimeSnapshot.providerName,
      }
      : undefined;
    const resolved = resolveRawApiConfig(apiConfigOverride);
    if (resolved.config?.apiKey) {
      headers['X-Api-Key'] = resolved.config.apiKey;
      headers['X-Authorization'] = `Bearer ${resolved.config.apiKey}`;
    }
    if (resolved.config?.model) {
      headers['X-Model-Id'] = resolved.config.model;
    }
    if (resolved.config?.baseURL) {
      headers['X-Model-Base-Url'] = resolved.config.baseURL;
    }
    if (resolved.providerMetadata?.providerName) {
      headers['X-Model-Provider'] = resolved.providerMetadata.providerName;
    }

    const controller = new AbortController();
    const active: ActiveClawSession = {
      sessionId,
      controller,
      assistantMessageId: null,
      assistantContent: '',
      initialMessageCount: currentSession?.messages.length ?? 0,
    };
    this.activeSessions.set(sessionId, active);

    const extra: Record<string, any> = {};
    if (options.imageAttachments?.length) {
      extra.media = options.imageAttachments.map((img) => ({
        url: `data:${img.mimeType};base64,${img.base64Data}`,
        mime_type: img.mimeType,
      }));
    }

    const requestBody = {
      message: prompt,
      extra: Object.keys(extra).length > 0 ? extra : null,
    };

    const config = this.store.getConfig();
    const serverUrl = config.clawServerUrl?.trim() || 'http://127.0.0.1:8000';
    const url = `${serverUrl.replace(/\/+$/, '')}/api/orchestrator/run`;

    try {
      const response = await net.fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify(requestBody),
        signal: controller.signal,
      });

      if (!response.ok) {
        const errorText = await response.text().catch(() => '');
        throw new Error(`Claw server returned status ${response.status}: ${errorText}`);
      }

      if (!response.body) {
        throw new Error('Claw server returned empty response body');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split(/\r?\n/);
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data:')) continue;
          const dataStr = trimmed.slice(5).trim();
          if (!dataStr) continue;

          try {
            const rawEvent = JSON.parse(dataStr) as ClawRawEvent;
            const normalized = normalizeClawEvent(sessionId, rawEvent);

            // Emit Claw Normalized Event
            this.emit('runtimeEvent', sessionId, normalized);

            // Handle Main Transcript Updates according to Main Transcript Rules
            if (normalized.source === 'orchestrator' && normalized.kind === 'message') {
              if (normalized.content) {
                this.appendAssistant(active, normalized.content);
              }
            } else if (normalized.kind === 'tool_start' && normalized.toolName) {
              const toolUseId = normalized.toolCallId || `tool-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
              const toolInput = (normalized.toolArgs as Record<string, unknown>) || {};
              const inputContent = typeof toolInput === 'string' ? toolInput : JSON.stringify(toolInput);
              this.addToolMessage(sessionId, {
                type: 'tool_use',
                content: inputContent,
                metadata: {
                  toolName: normalized.toolName,
                  toolInput,
                  toolUseId,
                },
              });
            } else if (normalized.kind === 'tool_end' && normalized.toolName) {
              const toolResult = normalized.toolResult || '';
              const resultContent = typeof toolResult === 'string' ? toolResult : JSON.stringify(toolResult);
              this.addToolMessage(sessionId, {
                type: 'tool_result',
                content: resultContent,
                metadata: {
                  toolName: normalized.toolName,
                  toolResult: resultContent,
                  toolUseId: normalized.toolCallId,
                  isError: false,
                },
              });
            } else if (normalized.kind === 'tool_error' && normalized.error) {
              const toolResult = normalized.error || '';
              const resultContent = typeof toolResult === 'string' ? toolResult : JSON.stringify(toolResult);
              this.addToolMessage(sessionId, {
                type: 'tool_result',
                content: resultContent,
                metadata: {
                  toolName: normalized.toolName || 'Tool',
                  toolResult: resultContent,
                  toolUseId: normalized.toolCallId,
                  isError: true,
                },
              });
            } else if (normalized.kind === 'error' && normalized.error) {
              this.handleError(sessionId, normalized.error);
            }
          } catch (e) {
            console.warn('[ClawRuntimeAdapter] Failed to parse SSE event chunk:', e);
          }
        }
      }

      this.finalizeAssistant(active);
      this.activeSessions.delete(sessionId);
      this.store.updateSession(sessionId, { status: 'completed' });
      this.emit('complete', sessionId, null);

    } catch (error: any) {
      this.activeSessions.delete(sessionId);
      if (this.stoppedSessions.has(sessionId)) {
        this.store.updateSession(sessionId, { status: 'idle' });
        this.emit('sessionStopped', sessionId);
        return;
      }

      let errorMsg = error.message || String(error);
      if (errorMsg.includes('connect ECONNREFUSED')) {
        errorMsg = 'Claw Server is not running. Please start the server by running bin/test_start.bat in llm-host-claw.';
      }
      this.handleError(sessionId, errorMsg);
    }
  }

  private appendAssistant(active: ActiveClawSession, delta: string): void {
    const next = truncateLargeContent(`${active.assistantContent}${delta}`, STREAMING_TEXT_MAX_CHARS);
    this.replaceAssistant(active, next, false);
  }

  private replaceAssistant(active: ActiveClawSession, content: string, isFinal: boolean): void {
    const safeContent = truncateLargeContent(content, STREAMING_TEXT_MAX_CHARS);
    active.assistantContent = safeContent;
    if (!active.assistantMessageId) {
      const message = this.store.addMessage(active.sessionId, {
        type: 'assistant',
        content: safeContent,
        metadata: { isStreaming: !isFinal, isFinal },
      });
      active.assistantMessageId = message.id;
      this.emit('message', active.sessionId, message);
      return;
    }
    this.store.updateMessage(active.sessionId, active.assistantMessageId, {
      content: safeContent,
      metadata: { isStreaming: !isFinal, isFinal },
    });
    this.emit('messageUpdate', active.sessionId, active.assistantMessageId, safeContent);
  }

  private finalizeAssistant(active: ActiveClawSession): void {
    if (!active.assistantMessageId) return;
    this.store.updateMessage(active.sessionId, active.assistantMessageId, {
      content: active.assistantContent,
      metadata: { isStreaming: false, isFinal: true },
    });
    this.emit('messageUpdate', active.sessionId, active.assistantMessageId, active.assistantContent);
  }

  private addSystemMessage(sessionId: string, content: string): void {
    const message = this.store.addMessage(sessionId, {
      type: 'system',
      content,
    });
    this.emit('message', sessionId, message);
  }

  private addToolMessage(
    sessionId: string,
    input: { type: CoworkMessage['type']; content: string; metadata?: CoworkMessageMetadata },
  ): void {
    if (input.type === 'tool_use') {
      this.splitAssistantSegmentBeforeTool(sessionId);
    }
    const message = this.store.addMessage(sessionId, input);
    this.emit('message', sessionId, message);
  }

  private splitAssistantSegmentBeforeTool(sessionId: string): void {
    const active = this.activeSessions.get(sessionId);
    if (!active?.assistantMessageId) return;
    this.finalizeAssistant(active);
    active.assistantMessageId = null;
    active.assistantContent = '';
  }

  private handleError(sessionId: string, error: string): void {
    if (this.stoppedSessions.has(sessionId)) return;
    if (this.store.getSession(sessionId)?.status === 'error') return;
    this.store.updateSession(sessionId, { status: 'error' });
    this.emit('error', sessionId, error);
  }
}
