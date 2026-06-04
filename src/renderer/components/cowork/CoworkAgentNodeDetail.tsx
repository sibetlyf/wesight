import {
  ArrowPathIcon,
  CheckCircleIcon,
  ClockIcon,
  CommandLineIcon,
  CpuChipIcon,
  ExclamationCircleIcon,
} from '@heroicons/react/24/outline';
import React from 'react';

import type { AgentHierarchyNode, AgentTimelineItem, AgentToolCall } from '../../types/cowork';

interface CoworkAgentNodeDetailProps {
  node: AgentHierarchyNode;
  timelineById: Record<string, AgentTimelineItem>;
  toolCallsById: Record<string, AgentToolCall>;
}

export const CoworkAgentNodeDetail: React.FC<CoworkAgentNodeDetailProps> = ({
  node,
  timelineById,
  toolCallsById,
}) => {
  const [activeTab, setActiveTab] = React.useState<'output' | 'reasoning' | 'tools' | 'timeline'>('output');

  const duration = node.updatedAt && node.startedAt
    ? `${((node.updatedAt - node.startedAt) / 1000).toFixed(1)}s`
    : null;

  const nodeTimeline = React.useMemo(() => {
    return node.timelineItemIds
      .map(id => timelineById[id])
      .filter(Boolean)
      .sort((a, b) => a.timestamp - b.timestamp);
  }, [node.timelineItemIds, timelineById]);

  const nodeTools = React.useMemo(() => {
    return node.toolCallIds
      .map(id => toolCallsById[id])
      .filter(Boolean)
      .sort((a, b) => a.startedAt - b.startedAt);
  }, [node.toolCallIds, toolCallsById]);

  const renderStatusIcon = () => {
    switch (node.status) {
      case 'completed':
        return <CheckCircleIcon className="h-5 w-5 text-emerald-500 shrink-0" />;
      case 'error':
        return <ExclamationCircleIcon className="h-5 w-5 text-rose-500 shrink-0" />;
      case 'running':
        return <ArrowPathIcon className="h-5 w-5 text-primary animate-spin shrink-0" />;
      default:
        return <ClockIcon className="h-5 w-5 text-secondary shrink-0" />;
    }
  };

  const getStatusLabel = () => {
    switch (node.status) {
      case 'completed':
        return 'Completed';
      case 'error':
        return 'Failed';
      case 'running':
        return 'Running';
      default:
        return 'Pending';
    }
  };

  return (
    <div className="flex h-full flex-col bg-surface border border-border rounded-xl overflow-hidden shadow-sm">
      {/* Detail Header */}
      <div className="border-b border-border bg-surface-raised px-4 py-3.5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <CpuChipIcon className="h-5 w-5 text-primary shrink-0" />
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-foreground truncate">
              {node.title}
            </h3>
            {node.agentId && (
              <p className="text-[11px] text-secondary truncate">
                ID: {node.agentId}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs text-secondary">
            {renderStatusIcon()}
            <span className="font-medium text-foreground">{getStatusLabel()}</span>
          </div>
          {duration && (
            <div className="flex items-center gap-1 text-xs text-secondary border-l border-border pl-3">
              <ClockIcon className="h-4 w-4" />
              <span>{duration}</span>
            </div>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border bg-surface px-2">
        <button
          type="button"
          onClick={() => setActiveTab('output')}
          className={`px-3 py-2 text-xs font-semibold border-b-2 transition-colors ${
            activeTab === 'output'
              ? 'border-primary text-primary'
              : 'border-transparent text-secondary hover:text-foreground'
          }`}
        >
          Output Content
        </button>
        {node.reasoning && (
          <button
            type="button"
            onClick={() => setActiveTab('reasoning')}
            className={`px-3 py-2 text-xs font-semibold border-b-2 transition-colors ${
              activeTab === 'reasoning'
                ? 'border-primary text-primary'
                : 'border-transparent text-secondary hover:text-foreground'
            }`}
          >
            Reasoning Logs
          </button>
        )}
        {nodeTools.length > 0 && (
          <button
            type="button"
            onClick={() => setActiveTab('tools')}
            className={`px-3 py-2 text-xs font-semibold border-b-2 transition-colors ${
              activeTab === 'tools'
                ? 'border-primary text-primary'
                : 'border-transparent text-secondary hover:text-foreground'
            }`}
          >
            Tools ({nodeTools.length})
          </button>
        )}
        <button
          type="button"
          onClick={() => setActiveTab('timeline')}
          className={`px-3 py-2 text-xs font-semibold border-b-2 transition-colors ${
            activeTab === 'timeline'
              ? 'border-primary text-primary'
              : 'border-transparent text-secondary hover:text-foreground'
          }`}
        >
          Event Timeline
        </button>
      </div>

      {/* Tab Contents */}
      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === 'output' && (
          <div className="h-full">
            {node.content ? (
              <div className="prose prose-sm dark:prose-invert max-w-none text-foreground leading-relaxed whitespace-pre-wrap select-text font-normal text-xs">
                {node.content}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-48 text-secondary">
                <CommandLineIcon className="h-8 w-8 mb-2 opacity-50" />
                <span className="text-xs">No output content received yet.</span>
              </div>
            )}
          </div>
        )}

        {activeTab === 'reasoning' && (
          <div className="h-full">
            <div className="rounded-lg border border-primary/20 bg-primary/5 p-3.5 select-text">
              <div className="text-[11px] font-semibold text-primary mb-2 uppercase tracking-wider">
                Thinking Process
              </div>
              <div className="text-xs font-mono leading-relaxed text-foreground whitespace-pre-wrap">
                {node.reasoning}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'tools' && (
          <div className="flex flex-col gap-3">
            {nodeTools.map((tool) => (
              <div
                key={tool.toolCallId}
                className="border border-border rounded-lg bg-surface-raised overflow-hidden text-xs"
              >
                <div className="flex items-center justify-between bg-surface px-3 py-2 border-b border-border">
                  <div className="flex items-center gap-1.5 font-mono font-semibold text-foreground">
                    <CommandLineIcon className="h-4 w-4 text-primary" />
                    <span>{tool.toolName}</span>
                  </div>
                  <span
                    className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${
                      tool.status === 'completed'
                        ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                        : tool.status === 'error'
                          ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
                          : 'bg-primary/10 text-primary animate-pulse'
                    }`}
                  >
                    {tool.status}
                  </span>
                </div>
                <div className="p-3 flex flex-col gap-2">
                  <div>
                    <div className="text-[10px] font-semibold text-secondary mb-1">Arguments</div>
                    <pre className="p-2 bg-surface border border-border rounded font-mono text-[11px] text-foreground overflow-x-auto max-h-36">
                      {JSON.stringify(tool.args, null, 2)}
                    </pre>
                  </div>
                  {tool.result !== undefined && (
                    <div>
                      <div className="text-[10px] font-semibold text-secondary mb-1">Result</div>
                      <pre className="p-2 bg-surface border border-border rounded font-mono text-[11px] text-foreground overflow-x-auto max-h-36">
                        {typeof tool.result === 'string'
                          ? tool.result
                          : JSON.stringify(tool.result, null, 2)}
                      </pre>
                    </div>
                  )}
                  {tool.error && (
                    <div>
                      <div className="text-[10px] font-semibold text-rose-500 mb-1">Error</div>
                      <div className="p-2 bg-rose-500/5 border border-rose-500/20 text-rose-600 dark:text-rose-400 rounded font-mono text-[11px] overflow-x-auto">
                        {tool.error}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'timeline' && (
          <div className="flex flex-col gap-3 font-mono text-[11px] text-secondary">
            {nodeTimeline.map((item) => (
              <div key={item.id} className="flex gap-3 border-b border-border/40 pb-2.5 last:border-0 last:pb-0">
                <span className="shrink-0 text-secondary/60">
                  {new Date(item.timestamp).toLocaleTimeString()}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold text-foreground bg-surface-raised px-1.5 py-0.5 rounded text-[10px]">
                      {item.kind}
                    </span>
                    {item.toolName && (
                      <span className="text-primary font-semibold">
                        tool: {item.toolName}
                      </span>
                    )}
                  </div>
                  {item.text && (
                    <div className="text-foreground whitespace-pre-wrap line-clamp-6 leading-relaxed select-text">
                      {item.text}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
