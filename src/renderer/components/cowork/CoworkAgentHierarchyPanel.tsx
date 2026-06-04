import {
  ArrowPathIcon,
  BugAntIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  CommandLineIcon,
  CpuChipIcon,
  ExclamationCircleIcon,
} from '@heroicons/react/24/outline';
import React from 'react';
import { useSelector } from 'react-redux';

import type { RootState } from '../../store';
import type { AgentHierarchyNode } from '../../types/cowork';
import { CoworkAgentNodeDetail } from './CoworkAgentNodeDetail';

interface CoworkAgentHierarchyPanelProps {
  sessionId: string;
}

export const CoworkAgentHierarchyPanel: React.FC<CoworkAgentHierarchyPanelProps> = ({
  sessionId,
}) => {
  const runtimeState = useSelector((state: RootState) => state.cowork.runtimeStates[sessionId]);
  const [selectedNodeId, setSelectedNodeId] = React.useState<string | null>(null);
  const [expandedNodes, setExpandedNodes] = React.useState<Record<string, boolean>>({});

  // Reset selected node and expanded nodes when session changes
  React.useEffect(() => {
    setSelectedNodeId(null);
    setExpandedNodes({});
  }, [sessionId]);

  if (!runtimeState || !runtimeState.rootNodeIds.length) {
    return (
      <div className="flex flex-col items-center justify-center h-64 border border-dashed border-border rounded-xl bg-surface-raised/40 text-secondary">
        <BugAntIcon className="h-8 w-8 mb-2 opacity-50 animate-pulse text-primary" />
        <p className="text-xs">Waiting for agent execution events...</p>
      </div>
    );
  }

  const { rootNodeIds, nodesById, timelineById, toolCallsById } = runtimeState;

  // Automatically select the first root node if nothing is selected
  const activeNodeId = selectedNodeId || rootNodeIds[0];
  const activeNode = nodesById[activeNodeId];

  const toggleExpand = (nodeId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedNodes(prev => ({
      ...prev,
      [nodeId]: !prev[nodeId],
    }));
  };

  const renderStatusIcon = (status: AgentHierarchyNode['status']) => {
    switch (status) {
      case 'completed':
        return <CheckCircleIcon className="h-4 w-4 text-emerald-500 shrink-0" />;
      case 'error':
        return <ExclamationCircleIcon className="h-4 w-4 text-rose-500 shrink-0" />;
      case 'running':
        return <ArrowPathIcon className="h-4 w-4 text-primary animate-spin shrink-0" />;
      default:
        return <span className="h-2 w-2 rounded-full bg-secondary/50 shrink-0" />;
    }
  };

  const renderNodeRow = (nodeId: string, depth: number = 0) => {
    const node = nodesById[nodeId];
    if (!node) return null;

    const isExpanded = expandedNodes[nodeId] !== false; // Default to true (expanded)
    const hasChildren = node.childNodeIds.length > 0;
    const isSelected = activeNodeId === nodeId;

    return (
      <React.Fragment key={nodeId}>
        <div
          onClick={() => setSelectedNodeId(nodeId)}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-all duration-200 select-none ${
            isSelected
              ? 'bg-primary/10 border border-primary/20 text-primary'
              : 'hover:bg-surface-raised/80 border border-transparent text-foreground'
          }`}
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
        >
          {/* Expander */}
          <div className="w-4 h-4 flex items-center justify-center">
            {hasChildren && (
              <button
                type="button"
                onClick={(e) => toggleExpand(nodeId, e)}
                className="text-secondary hover:text-foreground shrink-0 focus:outline-none"
              >
                {isExpanded ? (
                  <ChevronDownIcon className="h-3 w-3" />
                ) : (
                  <ChevronRightIcon className="h-3 w-3" />
                )}
              </button>
            )}
          </div>

          {/* Node Icon */}
          <div className="shrink-0">
            {node.source === 'orchestrator' ? (
              <CpuChipIcon className={`h-4 w-4 ${isSelected ? 'text-primary' : 'text-secondary'}`} />
            ) : (
              <CommandLineIcon className={`h-4 w-4 ${isSelected ? 'text-primary' : 'text-secondary'}`} />
            )}
          </div>

          {/* Title / Description */}
          <div className="min-w-0 flex-1">
            <div className="text-xs font-semibold truncate leading-tight">
              {node.title}
            </div>
            {node.source !== 'orchestrator' && (
              <div className="text-[10px] text-secondary leading-none mt-0.5">
                Subagent
              </div>
            )}
          </div>

          {/* Badges / Status */}
          <div className="flex items-center gap-1.5 shrink-0 ml-2">
            {node.toolCallIds.length > 0 && (
              <span className="text-[9px] font-semibold bg-surface-raised border border-border text-secondary px-1 py-0.2 rounded-md">
                {node.toolCallIds.length} tool{node.toolCallIds.length > 1 ? 's' : ''}
              </span>
            )}
            {renderStatusIcon(node.status)}
          </div>
        </div>

        {hasChildren && isExpanded && (
          <div className="flex flex-col gap-1 mt-1">
            {node.childNodeIds.map(childId => renderNodeRow(childId, depth + 1))}
          </div>
        )}
      </React.Fragment>
    );
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 h-[550px] w-full mt-4">
      {/* Left Column: Tree List */}
      <div className="lg:col-span-5 flex flex-col bg-surface border border-border rounded-xl p-3 overflow-hidden shadow-sm">
        <div className="text-xs font-semibold text-secondary uppercase tracking-wider mb-2.5 px-1.5">
          Agent Call Stack
        </div>
        <div className="flex-1 overflow-y-auto flex flex-col gap-1 pr-1">
          {rootNodeIds.map(rootId => renderNodeRow(rootId, 0))}
        </div>
      </div>

      {/* Right Column: Node Detail */}
      <div className="lg:col-span-7 h-full overflow-hidden">
        {activeNode ? (
          <CoworkAgentNodeDetail
            node={activeNode}
            timelineById={timelineById}
            toolCallsById={toolCallsById}
          />
        ) : (
          <div className="flex items-center justify-center h-full bg-surface border border-border rounded-xl text-secondary">
            <p className="text-xs">Select a node from the stack to inspect detail.</p>
          </div>
        )}
      </div>
    </div>
  );
};
