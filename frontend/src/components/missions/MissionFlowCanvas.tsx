import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import ReactFlow, {
  useNodesState,
  useEdgesState,
  Controls,
  MiniMap,
  Background,
  BackgroundVariant,
  ConnectionLineType,
  MarkerType,
  type ReactFlowInstance,
} from 'reactflow';
import type { Node, Edge } from 'reactflow';
import dagre from 'dagre';
import 'reactflow/dist/style.css';
import { useTranslation } from 'react-i18next';

import { MissionNode } from './nodes/MissionNode';
import { RequirementsNode } from './nodes/RequirementsNode';
import { TaskNode } from './nodes/TaskNode';
import { AgentNode } from './nodes/AgentNode';
import { SupervisorNode } from './nodes/SupervisorNode';
import { QANode } from './nodes/QANode';
import { ClarificationNode } from './nodes/ClarificationNode';
import { useMissionStore } from '@/stores/missionStore';

const nodeTypes = {
  missionNode: MissionNode,
  requirementsNode: RequirementsNode,
  taskNode: TaskNode,
  agentNode: AgentNode,
  supervisorNode: SupervisorNode,
  qaNode: QANode,
  clarificationNode: ClarificationNode,
};

const DEFAULT_NODE_WIDTH = 260;
const DEFAULT_NODE_HEIGHT = 140;

const NODE_DIMENSIONS: Record<string, { width: number; height: number }> = {
  missionNode: { width: 280, height: 170 },
  requirementsNode: { width: 280, height: 180 },
  clarificationNode: { width: 280, height: 260 },
  taskNode: { width: 260, height: 160 },
  supervisorNode: { width: 260, height: 170 },
  qaNode: { width: 260, height: 170 },
  agentNode: { width: 240, height: 140 },
};

const ACTIVE_STATUSES = new Set([
  'requirements',
  'planning',
  'executing',
  'reviewing',
  'qa',
]);

function getNodeDimensions(node: Node): { width: number; height: number } {
  const fallback = NODE_DIMENSIONS[node.type || ''] || {
    width: DEFAULT_NODE_WIDTH,
    height: DEFAULT_NODE_HEIGHT,
  };

  if (node.type === 'clarificationNode') {
    const messageCount = Array.isArray((node.data as { messages?: unknown[] } | undefined)?.messages)
      ? ((node.data as { messages?: unknown[] }).messages as unknown[]).length
      : 0;
    const dynamicHeight = Math.min(380, fallback.height + Math.max(0, messageCount - 1) * 18);
    return { width: fallback.width, height: dynamicHeight };
  }

  return fallback;
}

function getLayoutedElements(nodes: Node[], edges: Edge[]) {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', nodesep: 80, ranksep: 110, marginx: 30, marginy: 30 });

  const agentNodes = nodes.filter((node) => node.type === 'agentNode');
  const flowNodes = nodes.filter((node) => node.type !== 'agentNode');
  const flowNodeIds = new Set(flowNodes.map((node) => node.id));

  flowNodes.forEach((node) => {
    const { width, height } = getNodeDimensions(node);
    g.setNode(node.id, { width, height });
  });

  edges.forEach((edge) => {
    if (flowNodeIds.has(edge.source) && flowNodeIds.has(edge.target)) {
      g.setEdge(edge.source, edge.target);
    }
  });

  dagre.layout(g);

  const layoutedFlowNodes = flowNodes.map((node) => {
    const nodeWithPosition = g.node(node.id);
    const { width, height } = getNodeDimensions(node);
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - width / 2,
        y: nodeWithPosition.y - height / 2,
      },
    };
  });

  const maxFlowX = layoutedFlowNodes.reduce((acc, node) => {
    const { width } = getNodeDimensions(node);
    return Math.max(acc, node.position.x + width);
  }, 0);
  const minFlowY = layoutedFlowNodes.reduce((acc, node) => Math.min(acc, node.position.y), 0);

  const roleOrder: Record<string, number> = {
    leader: 0,
    supervisor: 1,
    qa: 2,
    worker: 3,
  };
  const sortedAgentNodes = [...agentNodes].sort((a, b) => {
    const aRole = String((a.data as { role?: string } | undefined)?.role || 'worker');
    const bRole = String((b.data as { role?: string } | undefined)?.role || 'worker');
    const byRole = (roleOrder[aRole] ?? 99) - (roleOrder[bRole] ?? 99);
    if (byRole !== 0) return byRole;
    return a.id.localeCompare(b.id);
  });

  const layoutedAgentNodes = sortedAgentNodes.map((node, index) => ({
    ...node,
    position: {
      x: maxFlowX + 220,
      y: minFlowY + index * 170,
    },
  }));

  return { nodes: [...layoutedFlowNodes, ...layoutedAgentNodes], edges };
}

interface MissionFlowCanvasProps {
  missionId: string;
}

export const MissionFlowCanvas: React.FC<MissionFlowCanvasProps> = ({ missionId }) => {
  const { t } = useTranslation();
  const {
    selectedMission,
    missionTasks,
    missionAgents,
    missionEvents,
    fetchMission,
    fetchMissionTasks,
    fetchMissionAgents,
    fetchMissionEvents,
  } = useMissionStore();

  const wsRef = useRef<WebSocket | null>(null);
  const pollingInFlightRef = useRef(false);

  // Load data
  useEffect(() => {
    fetchMission(missionId);
    fetchMissionTasks(missionId);
    fetchMissionAgents(missionId);
    fetchMissionEvents(missionId);
  }, [missionId, fetchMission, fetchMissionTasks, fetchMissionAgents, fetchMissionEvents]);

  // WebSocket connection
  useEffect(() => {
    const configuredApiBase = import.meta.env.VITE_API_URL || '/api/v1';
    const absoluteApiBase = configuredApiBase.startsWith('http')
      ? configuredApiBase
      : `${window.location.origin}${configuredApiBase.startsWith('/') ? '' : '/'}${configuredApiBase}`;
    const apiBase = absoluteApiBase.replace(/\/$/, '');
    const wsUrl = `${apiBase.replace(/^http/, 'ws')}/ws/missions/${missionId}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const store = useMissionStore.getState();

        if (data.type === 'mission_event' && data.data) {
          const payload = data.data;
          store.handleMissionEvent({
            event_id: payload.event_id || `ws-${Date.now()}`,
            mission_id: payload.mission_id || missionId,
            event_type: payload.event_type || 'UNKNOWN',
            agent_id: payload.agent_id || undefined,
            task_id: payload.task_id || undefined,
            event_data: payload.event_data ?? payload.data ?? undefined,
            message: payload.message || undefined,
            created_at: payload.created_at || new Date().toISOString(),
          });
        } else if (data.type === 'mission_state' && data.data) {
          store.handleMissionStatusUpdate({
            mission_id: data.data.mission_id,
            status: data.data.status,
            updates: data.data,
          });
        } else if (data.type === 'mission_status') {
          store.handleMissionStatusUpdate(data);
        } else if (data.type === 'task_status' && data.task_id && data.updates) {
          store.handleTaskStatusUpdate(data);
        }
      } catch {
        // ignore parse errors
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [missionId]);

  const pollIntervalMs = useMemo(() => {
    if (selectedMission && ACTIVE_STATUSES.has(selectedMission.status)) {
      return 4000;
    }
    return 12000;
  }, [selectedMission]);

  // Polling fallback when websocket updates are delayed or disconnected.
  useEffect(() => {
    let cancelled = false;

    const pollMissionState = async () => {
      if (cancelled || document.visibilityState !== 'visible') {
        return;
      }
      if (pollingInFlightRef.current) {
        return;
      }
      pollingInFlightRef.current = true;
      try {
        await Promise.all([
          fetchMission(missionId),
          fetchMissionTasks(missionId),
          fetchMissionAgents(missionId),
          fetchMissionEvents(missionId),
        ]);
      } finally {
        pollingInFlightRef.current = false;
      }
    };

    const startupTimer = window.setTimeout(() => {
      void pollMissionState();
    }, 1500);
    const intervalId = window.setInterval(() => {
      void pollMissionState();
    }, pollIntervalMs);

    return () => {
      cancelled = true;
      window.clearTimeout(startupTimer);
      window.clearInterval(intervalId);
    };
  }, [
    missionId,
    pollIntervalMs,
    fetchMission,
    fetchMissionTasks,
    fetchMissionAgents,
    fetchMissionEvents,
  ]);

  // Build nodes and edges from mission data
  const { initialNodes, initialEdges } = useMemo(() => {
    const nodes: Node[] = [];
    const edges: Edge[] = [];
    const edgeKeys = new Set<string>();

    const addEdge = (edge: Edge, dedupeKey?: string) => {
      const key = dedupeKey || `${edge.source}->${edge.target}:${edge.type || 'default'}`;
      if (edgeKeys.has(key)) return;
      edgeKeys.add(key);
      edges.push(edge);
    };

    if (!selectedMission) return { initialNodes: nodes, initialEdges: edges };

    const taskIdSet = new Set(missionTasks.map((task) => task.task_id));
    const titleToTaskId = new Map<string, string>();
    const agentNameById = new Map(
      missionAgents
        .filter((agent) => Boolean(agent.agent_id))
        .map((agent) => [
          agent.agent_id,
          agent.agent_name || agent.role || t('missions.unassigned', 'Unassigned'),
        ])
    );

    missionTasks.forEach((task) => {
      const title =
        typeof task.task_metadata?.title === 'string' ? task.task_metadata.title.trim() : '';
      if (title) {
        titleToTaskId.set(title, task.task_id);
      }
    });

    const resolveDependencies = (task: (typeof missionTasks)[number]): string[] => {
      const rawDeps = Array.isArray(task.dependencies)
        ? task.dependencies
        : Array.isArray(task.task_metadata?.dependencies)
          ? (task.task_metadata.dependencies as unknown[])
          : [];

      const resolved = rawDeps
        .map((dep) => {
          if (typeof dep !== 'string') return null;
          const depText = dep.trim();
          if (!depText) return null;
          if (taskIdSet.has(depText)) return depText;
          return titleToTaskId.get(depText) ?? null;
        })
        .filter((depId): depId is string => Boolean(depId));

      return Array.from(new Set(resolved));
    };

    // Mission root node
    nodes.push({
      id: 'mission',
      type: 'missionNode',
      position: { x: 0, y: 0 },
      data: {
        title: selectedMission.title,
        status: selectedMission.status,
        total_tasks: selectedMission.total_tasks,
        completed_tasks: selectedMission.completed_tasks,
        failed_tasks: selectedMission.failed_tasks,
        agents: missionAgents,
      },
    });

    // Requirements node
    if (selectedMission.requirements_doc || selectedMission.status === 'requirements') {
      nodes.push({
        id: 'requirements',
        type: 'requirementsNode',
        position: { x: 0, y: 0 },
        data: {
          requirements_doc: selectedMission.requirements_doc,
          status: selectedMission.requirements_doc ? 'ready' : 'pending',
        },
      });
      addEdge({
        id: 'e-mission-requirements',
        source: 'mission',
        target: 'requirements',
        type: 'smoothstep',
        animated: selectedMission.status === 'requirements',
      });
    }

    // Clarification node for clarification events
    const getClarificationText = (event: typeof missionEvents[number]): string => {
      const maybeQuestions = event.event_data?.questions;
      if (
        (event.event_type === 'USER_CLARIFICATION_REQUESTED' ||
          event.event_type === 'clarification_request') &&
        typeof maybeQuestions === 'string' &&
        maybeQuestions.trim()
      ) {
        return maybeQuestions;
      }
      return event.message || '';
    };

    const clarificationEvents = missionEvents.filter(
      (e) =>
        e.event_type === 'USER_CLARIFICATION_REQUESTED' ||
        e.event_type === 'clarification_request' ||
        e.event_type === 'clarification_response'
    );
    if (clarificationEvents.length > 0) {
      nodes.push({
        id: 'clarification',
        type: 'clarificationNode',
        position: { x: 0, y: 0 },
        data: {
          messages: clarificationEvents.map((e) => ({
            sender:
              e.event_type === 'USER_CLARIFICATION_REQUESTED' ||
              e.event_type === 'clarification_request'
                ? ('leader' as const)
                : ('user' as const),
            text: getClarificationText(e),
          })),
          is_active: selectedMission.status === 'requirements',
        },
      });
      addEdge({
        id: 'e-mission-clarification',
        source: 'mission',
        target: 'clarification',
        type: 'smoothstep',
        style: { strokeDasharray: '5 5' },
      });
    }

    // Task nodes
    const parentEdgeSource = nodes.find((n) => n.id === 'requirements') ? 'requirements' : 'mission';
    missionTasks.forEach((task) => {
      nodes.push({
        id: `task-${task.task_id}`,
        type: 'taskNode',
        position: { x: 0, y: 0 },
        data: {
          task_id: task.task_id,
          goal_text: task.goal_text,
          status: task.status,
          priority: task.priority,
          assigned_agent_name:
            task.assigned_agent_name ||
            (task.assigned_agent_id
              ? agentNameById.get(task.assigned_agent_id)
              : undefined),
          acceptance_criteria: task.acceptance_criteria,
        },
      });

      // Edge from parent task or from requirements/mission
      const dependencyIds = resolveDependencies(task);

      if (task.parent_task_id) {
        addEdge({
          id: `e-task-${task.parent_task_id}-${task.task_id}`,
          source: `task-${task.parent_task_id}`,
          target: `task-${task.task_id}`,
          type: 'smoothstep',
          animated: task.status === 'in_progress',
        });
      } else if (dependencyIds.length === 0) {
        addEdge({
          id: `e-${parentEdgeSource}-task-${task.task_id}`,
          source: parentEdgeSource,
          target: `task-${task.task_id}`,
          type: 'smoothstep',
          animated: task.status === 'in_progress',
        });
      }

      // Dependency edges
      dependencyIds.forEach((depId) => {
        addEdge(
          {
          id: `e-dep-${depId}-${task.task_id}`,
          source: `task-${depId}`,
          target: `task-${task.task_id}`,
          type: 'smoothstep',
          style: { strokeDasharray: '3 3', stroke: '#94a3b8' },
          markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
          },
          `dep:${depId}->${task.task_id}`
        );
      });
    });

    // Agent nodes connected to their assigned tasks
    missionAgents.forEach((agent) => {
      const agentNodeId = `agent-${agent.id}`;
      nodes.push({
        id: agentNodeId,
        type: 'agentNode',
        position: { x: 0, y: 0 },
        data: {
          agent_name: agent.agent_name || 'Agent',
          role: agent.role,
          status: agent.status,
          avatar: agent.avatar,
          is_temporary: agent.is_temporary,
        },
      });

      // Connect agent to their tasks
      const agentTasks = missionTasks.filter((t) => t.assigned_agent_id === agent.agent_id);
      if (agentTasks.length > 0) {
        agentTasks.forEach((task) => {
          addEdge({
            id: `e-agent-${agent.id}-task-${task.task_id}`,
            source: agentNodeId,
            target: `task-${task.task_id}`,
            type: 'smoothstep',
            style: { strokeDasharray: '5 5', stroke: '#06b6d4' },
          });
        });
      } else {
        // Connect to mission node
        addEdge({
          id: `e-agent-${agent.id}-mission`,
          source: 'mission',
          target: agentNodeId,
          type: 'smoothstep',
          style: { strokeDasharray: '5 5', stroke: '#06b6d4' },
        });
      }
    });

    // Review events as supervisor nodes
    const reviewEvents = missionEvents
      .filter((e) => e.event_type === 'TASK_REVIEWED' || e.event_type === 'task_review')
      .slice()
      .sort(
        (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
      );
    const latestReviewByTask = new Map<string, (typeof missionEvents)[number]>();
    const detachedReviewEvents: (typeof missionEvents)[number][] = [];
    reviewEvents.forEach((event) => {
      if (event.task_id) {
        latestReviewByTask.set(String(event.task_id), event);
      } else {
        detachedReviewEvents.push(event);
      }
    });

    const reviewNodes = [
      ...latestReviewByTask.values(),
      ...detachedReviewEvents.slice(-3),
    ];

    reviewNodes.forEach((event) => {
      const nodeId = event.task_id
        ? `supervisor-${event.task_id}`
        : `supervisor-${event.event_id}`;
      const taskId = event.task_id ? `task-${event.task_id}` : null;
      nodes.push({
        id: nodeId,
        type: 'supervisorNode',
        position: { x: 0, y: 0 },
        data: {
          task_id: event.task_id || '',
          task_label: event.event_data?.title || event.event_data?.task_label || 'Review',
          verdict: event.event_data?.verdict || 'pending',
          feedback: event.event_data?.review_feedback || event.event_data?.feedback,
        },
      });
      if (taskId && nodes.some((n) => n.id === taskId)) {
        addEdge({
          id: `e-${taskId}-${nodeId}`,
          source: taskId,
          target: nodeId,
          type: 'smoothstep',
          style: { stroke: '#a855f7' },
        });
      }
    });

    // QA events
    const qaEvents = missionEvents.filter(
      (e) => e.event_type === 'QA_VERDICT' || e.event_type === 'qa_audit'
    );
    qaEvents.forEach((event, i) => {
      const nodeId = `qa-${i}`;
      nodes.push({
        id: nodeId,
        type: 'qaNode',
        position: { x: 0, y: 0 },
        data: {
          verdict: event.event_data?.verdict || 'pending',
          issues_count: event.event_data?.issues_count,
          summary: event.event_data?.summary,
        },
      });
      // Connect to mission
      addEdge({
        id: `e-mission-${nodeId}`,
        source: 'mission',
        target: nodeId,
        type: 'smoothstep',
        style: { stroke: '#6366f1' },
      });
    });

    return { initialNodes: nodes, initialEdges: edges };
  }, [selectedMission, missionTasks, missionAgents, missionEvents, t]);

  // Apply layout
  const { nodes: layoutedNodes, edges: layoutedEdges } = useMemo(
    () => getLayoutedElements(initialNodes, initialEdges),
    [initialNodes, initialEdges]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(layoutedNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(layoutedEdges);

  // Re-layout when data changes
  useEffect(() => {
    const { nodes: ln, edges: le } = getLayoutedElements(initialNodes, initialEdges);
    setNodes(ln);
    setEdges(le);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  const onInit = useCallback((instance: ReactFlowInstance) => {
    instance.fitView({ padding: 0.2 });
  }, []);

  if (!selectedMission) {
    return (
      <div className="flex items-center justify-center h-96 text-zinc-500">
        {t('missions.loading')}
      </div>
    );
  }

  return (
    <div className="w-full h-[calc(100vh-12rem)] rounded-xl border border-zinc-200 dark:border-zinc-700 overflow-hidden bg-white dark:bg-zinc-900">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onInit={onInit}
        nodeTypes={nodeTypes}
        connectionLineType={ConnectionLineType.SmoothStep}
        fitView
        minZoom={0.3}
        maxZoom={1.5}
        attributionPosition="bottom-left"
      >
        <Controls className="!bg-white dark:!bg-zinc-800 !border-zinc-200 dark:!border-zinc-700 !rounded-lg !shadow-lg" />
        <MiniMap
          className="!bg-zinc-100 dark:!bg-zinc-800 !rounded-lg !border-zinc-200 dark:!border-zinc-700"
          nodeColor={(node) => {
            if (node.type === 'missionNode') return '#10b981';
            if (node.type === 'taskNode') return '#06b6d4';
            if (node.type === 'agentNode') return '#8b5cf6';
            return '#a1a1aa';
          }}
        />
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#e4e4e7" />
      </ReactFlow>
    </div>
  );
};
