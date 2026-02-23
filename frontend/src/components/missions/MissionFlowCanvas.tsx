import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import { X } from 'lucide-react';
import axios from 'axios';
import toast from 'react-hot-toast';

import { MissionNode } from './nodes/MissionNode';
import { RequirementsNode } from './nodes/RequirementsNode';
import { TaskNode } from './nodes/TaskNode';
import { AgentNode } from './nodes/AgentNode';
import { SupervisorNode } from './nodes/SupervisorNode';
import { QANode } from './nodes/QANode';
import { ClarificationNode } from './nodes/ClarificationNode';
import { LayoutModal } from '@/components/LayoutModal';
import { ModalPanel } from '@/components/ModalPanel';
import { useMissionStore } from '@/stores/missionStore';
import { selectLatestMissionRunEvents } from '@/utils/missionEvents';
import type { MissionEvent, MissionTask } from '@/types/mission';

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

const FLOW_POLL_INTERVAL_MS = 10_000;

function formatDetailTimestamp(value?: string): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function stringifyForDetail(value: unknown): string {
  if (value === undefined) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function getEventDisplayMessage(event: MissionEvent): string {
  const error = event.event_data?.error;
  if (typeof error === 'string' && error.trim()) return error.trim();
  const summary = event.event_data?.summary;
  if (typeof summary === 'string' && summary.trim()) return summary.trim();
  if (typeof event.message === 'string' && event.message.trim()) return event.message.trim();
  return '';
}

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
  g.setGraph({ rankdir: 'TB', nodesep: 120, ranksep: 150, marginx: 40, marginy: 40 });

  const agentNodes = nodes.filter((node) => node.type === 'agentNode');
  const supervisorNodes = nodes.filter((node) => node.type === 'supervisorNode');
  const qaNodes = nodes.filter((node) => node.type === 'qaNode');
  const dagreNodes = nodes.filter(
    (node) =>
      node.type !== 'agentNode' && node.type !== 'supervisorNode' && node.type !== 'qaNode'
  );
  const dagreNodeIds = new Set(dagreNodes.map((node) => node.id));

  dagreNodes.forEach((node) => {
    const { width, height } = getNodeDimensions(node);
    g.setNode(node.id, { width, height });
  });

  edges.forEach((edge) => {
    if (dagreNodeIds.has(edge.source) && dagreNodeIds.has(edge.target)) {
      g.setEdge(edge.source, edge.target);
    }
  });

  dagre.layout(g);

  const layoutedDagreNodes = dagreNodes.map((node) => {
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

  const taskNodeByTaskId = new Map<string, Node>();
  layoutedDagreNodes.forEach((node) => {
    if (node.type !== 'taskNode') return;
    const taskId = (node.data as { task_id?: string } | undefined)?.task_id;
    if (taskId) {
      taskNodeByTaskId.set(taskId, node);
    }
  });

  const maxDagreX = layoutedDagreNodes.reduce((acc, node) => {
    const { width } = getNodeDimensions(node);
    return Math.max(acc, node.position.x + width);
  }, 0);
  const minDagreX = layoutedDagreNodes.reduce((acc, node) => Math.min(acc, node.position.x), 0);
  const minDagreY = layoutedDagreNodes.reduce((acc, node) => Math.min(acc, node.position.y), 0);
  const maxDagreY = layoutedDagreNodes.reduce((acc, node) => {
    const { height } = getNodeDimensions(node);
    return Math.max(acc, node.position.y + height);
  }, 0);

  const supervisorLaneX = maxDagreX + 180;
  let detachedSupervisorIndex = 0;
  const layoutedSupervisorNodes = supervisorNodes.map((node) => {
    const taskId = (node.data as { task_id?: string } | undefined)?.task_id;
    const taskNode = taskId ? taskNodeByTaskId.get(taskId) : undefined;
    if (taskNode) {
      const { width } = getNodeDimensions(taskNode);
      return {
        ...node,
        position: {
          x: taskNode.position.x + width + 120,
          y: taskNode.position.y,
        },
      };
    }

    const positioned = {
      ...node,
      position: {
        x: supervisorLaneX,
        y: minDagreY + detachedSupervisorIndex * 200,
      },
    };
    detachedSupervisorIndex += 1;
    return positioned;
  });

  const qaBaseY = maxDagreY + 170;
  const qaGapX = 300;
  const qaCenterX = (minDagreX + maxDagreX) / 2;
  const qaStartX = qaCenterX - ((Math.max(qaNodes.length, 1) - 1) * qaGapX) / 2;
  const layoutedQANodes = qaNodes.map((node, index) => ({
    ...node,
    position: {
      x: qaStartX + index * qaGapX,
      y: qaBaseY,
    },
  }));

  const nonAgentNodes = [...layoutedDagreNodes, ...layoutedSupervisorNodes, ...layoutedQANodes];
  const maxFlowX = nonAgentNodes.reduce((acc, node) => {
    const { width } = getNodeDimensions(node);
    return Math.max(acc, node.position.x + width);
  }, maxDagreX);
  const minFlowY = nonAgentNodes.reduce((acc, node) => Math.min(acc, node.position.y), minDagreY);

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
      x: maxFlowX + 260,
      y: minFlowY + index * 180,
    },
  }));

  return {
    nodes: [...layoutedDagreNodes, ...layoutedSupervisorNodes, ...layoutedQANodes, ...layoutedAgentNodes],
    edges,
  };
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
    retryFailedMissionParts,
    clarify,
  } = useMissionStore();

  const wsRef = useRef<WebSocket | null>(null);
  const pollingInFlightRef = useRef(false);
  const previousStructureSignatureRef = useRef<string>('');
  const previousMissionIdRef = useRef<string | null>(null);
  const [detailNodeId, setDetailNodeId] = useState<string | null>(null);
  const [clarificationReply, setClarificationReply] = useState('');
  const [isSendingClarification, setIsSendingClarification] = useState(false);
  const [isRetryingFailedParts, setIsRetryingFailedParts] = useState(false);
  const scopedMissionEvents = useMemo(
    () =>
      selectLatestMissionRunEvents(
        missionEvents.filter((event) => event.mission_id === missionId)
      ),
    [missionEvents, missionId]
  );

  // Load data
  useEffect(() => {
    fetchMission(missionId);
    fetchMissionTasks(missionId);
    fetchMissionAgents(missionId);
    fetchMissionEvents(missionId);
  }, [missionId, fetchMission, fetchMissionTasks, fetchMissionAgents, fetchMissionEvents]);

  useEffect(() => {
    setDetailNodeId(null);
    setClarificationReply('');
  }, [missionId]);

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
    }, FLOW_POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearTimeout(startupTimer);
      window.clearInterval(intervalId);
    };
  }, [
    missionId,
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
        mission_id: selectedMission.mission_id,
        title: selectedMission.title,
        status: selectedMission.status,
        error_message: selectedMission.error_message,
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
          mission_instructions: selectedMission.instructions,
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
    const getClarificationText = (event: (typeof scopedMissionEvents)[number]): string => {
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

    const clarificationEvents = scopedMissionEvents.filter(
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
          event_ids: clarificationEvents.map((e) => e.event_id),
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
      const dependencyIds = resolveDependencies(task);
      const reviewStatus =
        typeof task.task_metadata?.review_status === 'string'
          ? task.task_metadata.review_status
          : '';
      const assignmentSource =
        typeof task.task_metadata?.assignment_source === 'string'
          ? task.task_metadata.assignment_source
          : '';
      const dependencyLevel =
        typeof task.task_metadata?.dependency_level === 'number'
          ? task.task_metadata.dependency_level
          : undefined;
      const visualTaskStatus =
        task.status === 'completed' &&
        reviewStatus !== 'approved' &&
        selectedMission.status !== 'completed' &&
        selectedMission.status !== 'qa'
          ? 'reviewing'
          : task.status;

      nodes.push({
        id: `task-${task.task_id}`,
        type: 'taskNode',
        position: { x: 0, y: 0 },
        data: {
          task_id: task.task_id,
          goal_text: task.goal_text,
          status: visualTaskStatus,
          priority: task.priority,
          assigned_agent_name:
            task.assigned_agent_name ||
            (task.assigned_agent_id
              ? agentNameById.get(task.assigned_agent_id)
              : assignmentSource === 'temporary_fallback_pending'
                ? t('missions.assignmentTempPending', 'Temporary fallback')
                : undefined),
          assignment_source: assignmentSource,
          dependency_level: dependencyLevel,
          dependencies: dependencyIds,
          acceptance_criteria: task.acceptance_criteria,
        },
      });

      // Edge from parent task or from requirements/mission
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
          mission_agent_id: agent.id,
          agent_id: agent.agent_id,
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
    const reviewEvents = scopedMissionEvents
      .filter((e) => e.event_type === 'TASK_REVIEWED' || e.event_type === 'task_review')
      .slice()
      .sort(
        (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
      );
    const latestReviewByTask = new Map<string, (typeof scopedMissionEvents)[number]>();
    const detachedReviewEvents: (typeof scopedMissionEvents)[number][] = [];
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
          event_id: event.event_id,
          created_at: event.created_at,
          task_id: event.task_id || '',
          task_label: event.event_data?.title || event.event_data?.task_label || 'Review',
          verdict: event.event_data?.verdict || 'pending',
          feedback: event.event_data?.review_feedback || event.event_data?.feedback,
          event_data: event.event_data,
          message: event.message,
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
    const qaEvents = scopedMissionEvents.filter(
      (e) => e.event_type === 'QA_VERDICT' || e.event_type === 'qa_audit'
    );
    qaEvents.forEach((event, i) => {
      const nodeId = `qa-${i}`;
      nodes.push({
        id: nodeId,
        type: 'qaNode',
        position: { x: 0, y: 0 },
        data: {
          event_id: event.event_id,
          created_at: event.created_at,
          verdict: event.event_data?.verdict || 'pending',
          issues_count: event.event_data?.issues_count,
          summary: event.event_data?.summary,
          event_data: event.event_data,
          message: event.message,
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
  }, [selectedMission, missionTasks, missionAgents, scopedMissionEvents, t]);

  // Apply layout
  const { nodes: layoutedNodes, edges: layoutedEdges } = useMemo(
    () => getLayoutedElements(initialNodes, initialEdges),
    [initialNodes, initialEdges]
  );
  const structureSignature = useMemo(() => {
    const nodePart = initialNodes
      .map((node) => {
        const { width, height } = getNodeDimensions(node);
        return `${node.id}:${node.type || 'default'}:${width}x${height}`;
      })
      .sort()
      .join('|');
    const edgePart = initialEdges
      .map((edge) => `${edge.id}:${edge.source}->${edge.target}:${edge.type || 'default'}`)
      .sort()
      .join('|');
    return `${nodePart}__${edgePart}`;
  }, [initialNodes, initialEdges]);

  const [nodes, setNodes, onNodesChange] = useNodesState(layoutedNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(layoutedEdges);
  const activeDetailNode = useMemo(
    () => nodes.find((node) => node.id === detailNodeId) || null,
    [detailNodeId, nodes]
  );
  const activeDetailData = (activeDetailNode?.data || {}) as Record<string, unknown>;

  const activeDetailTask = useMemo<MissionTask | null>(() => {
    const taskId = typeof activeDetailData.task_id === 'string' ? activeDetailData.task_id : '';
    if (!taskId) return null;
    return missionTasks.find((task) => task.task_id === taskId) || null;
  }, [activeDetailData.task_id, missionTasks]);

  const detailEvents = useMemo(() => {
    if (!activeDetailNode) return [] as MissionEvent[];

    const sortDesc = (items: MissionEvent[]) =>
      items
        .slice()
        .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

    if (activeDetailNode.type === 'missionNode') {
      return sortDesc(scopedMissionEvents).slice(0, 80);
    }

    if (activeDetailNode.type === 'requirementsNode') {
      return sortDesc(
        scopedMissionEvents.filter((event) => {
          if (
            event.event_type === 'USER_CLARIFICATION_REQUESTED' ||
            event.event_type === 'clarification_request' ||
            event.event_type === 'clarification_response'
          ) {
            return true;
          }
          const phase = event.event_data?.phase;
          return typeof phase === 'string' && phase === 'requirements';
        })
      ).slice(0, 80);
    }

    if (activeDetailNode.type === 'clarificationNode') {
      return sortDesc(
        scopedMissionEvents.filter(
          (event) =>
            event.event_type === 'USER_CLARIFICATION_REQUESTED' ||
            event.event_type === 'clarification_request' ||
            event.event_type === 'clarification_response'
        )
      );
    }

    if (activeDetailNode.type === 'taskNode' || activeDetailNode.type === 'supervisorNode') {
      const taskId = typeof activeDetailData.task_id === 'string' ? activeDetailData.task_id : '';
      if (!taskId) return [] as MissionEvent[];
      return sortDesc(scopedMissionEvents.filter((event) => event.task_id === taskId)).slice(0, 80);
    }

    if (activeDetailNode.type === 'qaNode') {
      const eventId =
        typeof activeDetailData.event_id === 'string' ? activeDetailData.event_id : '';
      if (eventId) {
        const matched = scopedMissionEvents.find((event) => event.event_id === eventId);
        return matched ? [matched] : [];
      }
      return sortDesc(
        scopedMissionEvents.filter((event) => event.event_type === 'QA_VERDICT')
      ).slice(0, 20);
    }

    if (activeDetailNode.type === 'agentNode') {
      const agentId = typeof activeDetailData.agent_id === 'string' ? activeDetailData.agent_id : '';
      if (!agentId) return [] as MissionEvent[];
      return sortDesc(scopedMissionEvents.filter((event) => event.agent_id === agentId)).slice(0, 80);
    }

    return [] as MissionEvent[];
  }, [activeDetailData, activeDetailNode, scopedMissionEvents]);

  const activeTaskAttempts = useMemo(() => {
    const attempts = activeDetailTask?.result?.attempts;
    if (!Array.isArray(attempts)) return [] as Array<Record<string, unknown>>;
    return attempts.filter(
      (item): item is Record<string, unknown> => typeof item === 'object' && item !== null
    );
  }, [activeDetailTask]);
  const canRetryThisTask =
    selectedMission.status === 'failed' || selectedMission.status === 'cancelled';

  const handleRetryThisTaskFromNode = useCallback(async () => {
    if (isRetryingFailedParts || !canRetryThisTask) return;
    setIsRetryingFailedParts(true);
    try {
      await retryFailedMissionParts(missionId);
      await Promise.all([
        fetchMission(missionId),
        fetchMissionTasks(missionId),
        fetchMissionEvents(missionId),
      ]);
    } catch {
      // Error toast is handled by API interceptor/store.
    } finally {
      setIsRetryingFailedParts(false);
    }
  }, [
    canRetryThisTask,
    fetchMission,
    fetchMissionEvents,
    fetchMissionTasks,
    isRetryingFailedParts,
    missionId,
    retryFailedMissionParts,
  ]);

  const handleSendClarificationFromNode = useCallback(async () => {
    if (isSendingClarification) return;
    const trimmedMessage = clarificationReply.trim();
    if (!trimmedMessage) {
      toast.error(t('missions.clarificationEmpty'));
      return;
    }

    setIsSendingClarification(true);
    try {
      await clarify(missionId, trimmedMessage);
      setClarificationReply('');
      await Promise.all([fetchMission(missionId), fetchMissionEvents(missionId)]);
    } catch (error) {
      let message = t('missions.clarificationSendFailed');
      if (axios.isAxiosError(error)) {
        const responseData = error.response?.data as { detail?: string; message?: string } | undefined;
        message = responseData?.detail || responseData?.message || error.message || message;
      } else if (error instanceof Error) {
        message = error.message;
      }
      toast.error(message);
    } finally {
      setIsSendingClarification(false);
    }
  }, [clarificationReply, clarify, fetchMission, fetchMissionEvents, isSendingClarification, missionId, t]);

  // Re-layout when data changes
  useEffect(() => {
    const missionSwitched = previousMissionIdRef.current !== missionId;
    const structureChanged = previousStructureSignatureRef.current !== structureSignature;
    previousMissionIdRef.current = missionId;
    previousStructureSignatureRef.current = structureSignature;

    if (missionSwitched || structureChanged) {
      const { nodes: ln, edges: le } = getLayoutedElements(initialNodes, initialEdges);
      setNodes(ln);
      setEdges(le);
      return;
    }

    // Incremental patch: update node/edge data in place so we don't reset positions or cause flicker.
    const latestNodeById = new Map(initialNodes.map((node) => [node.id, node] as const));
    const latestEdgeById = new Map(initialEdges.map((edge) => [edge.id, edge] as const));

    setNodes((prevNodes) =>
      prevNodes.map((node) => {
        const latest = latestNodeById.get(node.id);
        if (!latest) return node;
        return {
          ...node,
          data: latest.data,
          type: latest.type,
          draggable: latest.draggable,
          selectable: latest.selectable,
        };
      })
    );
    setEdges((prevEdges) =>
      prevEdges.map((edge) => {
        const latest = latestEdgeById.get(edge.id);
        if (!latest) return edge;
        return {
          ...edge,
          animated: latest.animated,
          style: latest.style,
          markerEnd: latest.markerEnd,
          type: latest.type,
          data: latest.data,
        };
      })
    );
  }, [initialNodes, initialEdges, missionId, setEdges, setNodes, structureSignature]);

  const onInit = useCallback((instance: ReactFlowInstance) => {
    instance.fitView({ padding: 0.2 });
  }, []);
  const handleNodeDoubleClick = useCallback((_event: React.MouseEvent, node: Node) => {
    setDetailNodeId(node.id);
  }, []);

  if (!selectedMission) {
    return (
      <div className="flex items-center justify-center h-96 text-zinc-500">
        {t('missions.loading')}
      </div>
    );
  }

  return (
    <div className="relative w-full h-[calc(100vh-12rem)] rounded-xl border border-zinc-200 dark:border-zinc-700 overflow-hidden bg-white dark:bg-zinc-900">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onInit={onInit}
        onNodeDoubleClick={handleNodeDoubleClick}
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
          pannable
          zoomable
          nodeColor={(node) => {
            if (node.type === 'missionNode') return '#10b981';
            if (node.type === 'taskNode') return '#06b6d4';
            if (node.type === 'agentNode') return '#8b5cf6';
            return '#a1a1aa';
          }}
        />
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#e4e4e7" />
      </ReactFlow>
      <div className="absolute right-6 top-4 z-[5] px-3 py-1.5 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white/90 dark:bg-zinc-900/90 text-[11px] text-zinc-500">
        {t('missions.flowHint', 'Double-click a node to inspect full details')}
      </div>

      <LayoutModal
        isOpen={Boolean(activeDetailNode)}
        onClose={() => setDetailNodeId(null)}
        closeOnBackdropClick={true}
        closeOnEscape={true}
      >
        <ModalPanel className="w-full max-w-5xl p-0 max-h-[calc(100vh-var(--app-header-height,4rem)-3rem)] overflow-hidden flex flex-col">
          <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-200 dark:border-zinc-700">
            <div className="min-w-0">
              <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
                {t('missions.nodeDetailsTitle', 'Node Details')}
              </h2>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1 truncate">
                {activeDetailNode?.type || '-'} • {activeDetailNode?.id || '-'}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setDetailNodeId(null)}
              className="p-2 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-500 transition-colors"
              aria-label={t('common.close', 'Close')}
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <div className="overflow-y-auto px-6 py-4 space-y-4">
            {activeDetailNode?.type === 'missionNode' && (
              <section className="rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50/70 dark:bg-zinc-900/60 p-4">
                <div className="text-sm font-semibold text-zinc-800 dark:text-zinc-200 mb-2">
                  {t('missions.overview', 'Overview')}
                </div>
                <div className="text-sm text-zinc-700 dark:text-zinc-200 whitespace-pre-wrap break-words">
                  {selectedMission.title}
                </div>
                <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                  <div className="px-2 py-1 rounded-md bg-zinc-100 dark:bg-zinc-800">
                    {t('missions.statusLabel', 'Status')}: {selectedMission.status}
                  </div>
                  <div className="px-2 py-1 rounded-md bg-zinc-100 dark:bg-zinc-800">
                    {t('missions.totalTasksLabel', 'Total')}: {selectedMission.total_tasks}
                  </div>
                  <div className="px-2 py-1 rounded-md bg-zinc-100 dark:bg-zinc-800">
                    {t('missions.completedTasksLabel', 'Completed')}: {selectedMission.completed_tasks}
                  </div>
                  <div className="px-2 py-1 rounded-md bg-zinc-100 dark:bg-zinc-800">
                    {t('missions.failedTasks', 'Failed Tasks')}: {selectedMission.failed_tasks}
                  </div>
                </div>
                {selectedMission.error_message && (
                  <div className="mt-3 rounded-lg border border-red-200 dark:border-red-500/40 bg-red-50/70 dark:bg-red-500/10 p-3 text-xs text-red-700 dark:text-red-200 whitespace-pre-wrap break-words">
                    {selectedMission.error_message}
                  </div>
                )}
              </section>
            )}

            {activeDetailNode?.type === 'requirementsNode' && (
              <section className="rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50/70 dark:bg-zinc-900/60 p-4 space-y-3">
                <div className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
                  {t('missions.requirementsContent', 'Requirements Content')}
                </div>
                <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words text-xs leading-5 text-zinc-700 dark:text-zinc-200 bg-white dark:bg-zinc-900 rounded p-3 border border-zinc-200 dark:border-zinc-700">
                  {typeof activeDetailData.requirements_doc === 'string' &&
                  activeDetailData.requirements_doc.trim()
                    ? activeDetailData.requirements_doc
                    : t('missions.noRequirementsYet', 'No requirements document yet.')}
                </pre>
                <div className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
                  {t('missions.originalInstructions', 'Original Instructions')}
                </div>
                <pre className="max-h-52 overflow-auto whitespace-pre-wrap break-words text-xs leading-5 text-zinc-700 dark:text-zinc-200 bg-white dark:bg-zinc-900 rounded p-3 border border-zinc-200 dark:border-zinc-700">
                  {typeof activeDetailData.mission_instructions === 'string' &&
                  activeDetailData.mission_instructions.trim()
                    ? activeDetailData.mission_instructions
                    : '-'}
                </pre>
              </section>
            )}

            {activeDetailNode?.type === 'clarificationNode' && (
              <section className="rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50/70 dark:bg-zinc-900/60 p-4">
                <div className="text-sm font-semibold text-zinc-800 dark:text-zinc-200 mb-3">
                  {t('missions.clarificationTimeline', 'Clarification Timeline')}
                </div>
                <div className="space-y-2">
                  {detailEvents.length === 0 && (
                    <div className="text-xs text-zinc-500">
                      {t('missions.noMessagesYet', 'No messages yet')}
                    </div>
                  )}
                  {detailEvents.map((event) => (
                    <div
                      key={event.event_id}
                      className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 p-2.5"
                    >
                      <div className="text-[11px] text-zinc-500">
                        {event.event_type} • {formatDetailTimestamp(event.created_at)}
                      </div>
                      <div className="mt-1 text-xs text-zinc-700 dark:text-zinc-200 whitespace-pre-wrap break-words">
                        {getEventDisplayMessage(event) || '-'}
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-4 pt-3 border-t border-zinc-200 dark:border-zinc-700">
                  <div className="text-xs font-semibold text-zinc-700 dark:text-zinc-200 mb-2">
                    {t('missions.replyFromCanvas', 'Reply From Canvas')}
                  </div>
                  <textarea
                    value={clarificationReply}
                    onChange={(event) => setClarificationReply(event.target.value)}
                    onKeyDown={(event) => {
                      if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
                        event.preventDefault();
                        void handleSendClarificationFromNode();
                      }
                    }}
                    placeholder={t('missions.clarificationPlaceholder')}
                    rows={3}
                    className="w-full resize-none rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm text-zinc-800 dark:text-zinc-200 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
                  />
                  <div className="mt-2 flex items-center justify-between gap-2">
                    <span className="text-[11px] text-zinc-500">
                      {t('missions.sendHint', 'Press Cmd/Ctrl + Enter to send')}
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        void handleSendClarificationFromNode();
                      }}
                      disabled={isSendingClarification}
                      className="inline-flex items-center rounded-md border border-emerald-300 dark:border-emerald-500/40 px-3 py-1.5 text-xs font-medium text-emerald-700 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-500/10 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                    >
                      {isSendingClarification
                        ? t('missions.sendingClarification', 'Sending...')
                        : t('missions.sendClarification', 'Send Reply')}
                    </button>
                  </div>
                </div>
              </section>
            )}

            {activeDetailNode?.type === 'taskNode' && activeDetailTask && (
              <section className="rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50/70 dark:bg-zinc-900/60 p-4 space-y-3">
                <div className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
                  {t('missions.taskDetails', 'Task Details')}
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs text-zinc-700 dark:text-zinc-200">
                  <div className="px-2 py-1 rounded bg-zinc-100 dark:bg-zinc-800">
                    ID: {activeDetailTask.task_id}
                  </div>
                  <div className="px-2 py-1 rounded bg-zinc-100 dark:bg-zinc-800">
                    {t('missions.statusLabel', 'Status')}: {activeDetailTask.status}
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      void handleRetryThisTaskFromNode();
                    }}
                    disabled={!canRetryThisTask || isRetryingFailedParts}
                    className="inline-flex items-center rounded-md border border-emerald-300 dark:border-emerald-500/40 px-3 py-1.5 text-xs font-medium text-emerald-700 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-500/10 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    {isRetryingFailedParts
                      ? t('missions.retryingThisTask', 'Retrying this task...')
                      : t('missions.retryThisTask', 'Retry This Task')}
                  </button>
                  {!canRetryThisTask && (
                    <span className="text-[11px] text-zinc-500">
                      {t(
                        'missions.retryThisTaskHint',
                        'Available when mission status is failed or cancelled'
                      )}
                    </span>
                  )}
                </div>
                <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words text-xs leading-5 text-zinc-700 dark:text-zinc-200 bg-white dark:bg-zinc-900 rounded p-3 border border-zinc-200 dark:border-zinc-700">
                  {activeDetailTask.goal_text}
                </pre>
                <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words text-xs leading-5 text-zinc-700 dark:text-zinc-200 bg-white dark:bg-zinc-900 rounded p-3 border border-zinc-200 dark:border-zinc-700">
                  {activeDetailTask.acceptance_criteria ||
                    t('missions.noAcceptanceCriteria', 'No acceptance criteria')}
                </pre>
                <details>
                  <summary className="cursor-pointer text-xs text-zinc-600 dark:text-zinc-300">
                    {t('missions.taskMetadata', 'Task Metadata')}
                  </summary>
                  <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words text-xs leading-5 text-zinc-700 dark:text-zinc-200 bg-white dark:bg-zinc-900 rounded p-3 border border-zinc-200 dark:border-zinc-700">
                    {stringifyForDetail(activeDetailTask.task_metadata)}
                  </pre>
                </details>
                <details>
                  <summary className="cursor-pointer text-xs text-zinc-600 dark:text-zinc-300">
                    {t('missions.taskResult', 'Task Result')}
                  </summary>
                  <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words text-xs leading-5 text-zinc-700 dark:text-zinc-200 bg-white dark:bg-zinc-900 rounded p-3 border border-zinc-200 dark:border-zinc-700">
                    {stringifyForDetail(activeDetailTask.result)}
                  </pre>
                </details>
                {activeTaskAttempts.length > 0 && (
                  <div className="space-y-2">
                    <div className="text-xs font-semibold text-zinc-700 dark:text-zinc-200">
                      {t('missions.attemptFailureDetails', 'Attempt Failure Details')}
                    </div>
                    {activeTaskAttempts.map((attempt, index) => (
                      <div
                        key={`${activeDetailTask.task_id}-attempt-${index}`}
                        className="rounded-lg border border-red-200 dark:border-red-500/30 bg-red-50/60 dark:bg-red-500/10 p-2 text-xs"
                      >
                        <div className="text-red-700 dark:text-red-300">
                          {t('missions.attemptLabel', 'Attempt')} {String(attempt.attempt || index + 1)}
                          {attempt.max_attempts ? `/${String(attempt.max_attempts)}` : ''}
                          {attempt.error_type ? ` • ${String(attempt.error_type)}` : ''}
                        </div>
                        {attempt.error && (
                          <pre className="mt-1 whitespace-pre-wrap break-words text-red-700 dark:text-red-200">
                            {String(attempt.error)}
                          </pre>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </section>
            )}

            {(activeDetailNode?.type === 'supervisorNode' || activeDetailNode?.type === 'qaNode') && (
              <section className="rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50/70 dark:bg-zinc-900/60 p-4 space-y-3">
                <div className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
                  {t('missions.reviewQaDetails', 'Review / QA Details')}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      void handleRetryThisTaskFromNode();
                    }}
                    disabled={!canRetryThisTask || isRetryingFailedParts}
                    className="inline-flex items-center rounded-md border border-emerald-300 dark:border-emerald-500/40 px-3 py-1.5 text-xs font-medium text-emerald-700 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-500/10 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    {isRetryingFailedParts
                      ? t('missions.retryingThisTask', 'Retrying this task...')
                      : t('missions.retryThisTask', 'Retry This Task')}
                  </button>
                  {!canRetryThisTask && (
                    <span className="text-[11px] text-zinc-500">
                      {t(
                        'missions.retryThisTaskHint',
                        'Available when mission status is failed or cancelled'
                      )}
                    </span>
                  )}
                </div>
                <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words text-xs leading-5 text-zinc-700 dark:text-zinc-200 bg-white dark:bg-zinc-900 rounded p-3 border border-zinc-200 dark:border-zinc-700">
                  {stringifyForDetail(activeDetailData)}
                </pre>
              </section>
            )}

            {activeDetailNode?.type === 'agentNode' && (
              <section className="rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50/70 dark:bg-zinc-900/60 p-4 space-y-3">
                <div className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
                  {t('missions.agentDetails', 'Agent Details')}
                </div>
                <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words text-xs leading-5 text-zinc-700 dark:text-zinc-200 bg-white dark:bg-zinc-900 rounded p-3 border border-zinc-200 dark:border-zinc-700">
                  {stringifyForDetail(activeDetailData)}
                </pre>
              </section>
            )}

            {detailEvents.length > 0 && (
              <section className="rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60 p-4">
                <div className="text-sm font-semibold text-zinc-800 dark:text-zinc-200 mb-3">
                  {t('missions.relatedEvents', 'Related Events')}
                </div>
                <div className="space-y-2">
                  {detailEvents.map((event) => (
                    <div
                      key={`detail-event-${event.event_id}`}
                      className="rounded-md border border-zinc-200 dark:border-zinc-700 bg-zinc-50/70 dark:bg-zinc-900/50 p-2.5"
                    >
                      <div className="flex flex-wrap items-center gap-2 text-[11px] text-zinc-600 dark:text-zinc-300">
                        <span className="font-medium text-zinc-700 dark:text-zinc-200">
                          {event.event_type}
                        </span>
                        <span>{formatDetailTimestamp(event.created_at)}</span>
                      </div>
                      <div className="mt-1 text-xs text-zinc-700 dark:text-zinc-200 whitespace-pre-wrap break-words">
                        {getEventDisplayMessage(event) || '-'}
                      </div>
                      {event.event_data && (
                        <details className="mt-1">
                          <summary className="cursor-pointer text-[11px] text-zinc-500">
                            {t('missions.eventData', 'Event Data')}
                          </summary>
                          <pre className="mt-1 max-h-56 overflow-auto whitespace-pre-wrap break-words text-[11px] leading-5 text-zinc-700 dark:text-zinc-200 bg-white dark:bg-zinc-900 rounded p-2 border border-zinc-200 dark:border-zinc-700">
                            {stringifyForDetail(event.event_data)}
                          </pre>
                        </details>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        </ModalPanel>
      </LayoutModal>
    </div>
  );
};
