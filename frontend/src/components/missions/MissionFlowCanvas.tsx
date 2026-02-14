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
} from 'reactflow';
import type { Node, Edge } from 'reactflow';
import dagre from 'dagre';
import 'reactflow/dist/style.css';

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

const NODE_WIDTH = 260;
const NODE_HEIGHT = 140;

function getLayoutedElements(nodes: Node[], edges: Edge[]) {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', nodesep: 60, ranksep: 80 });

  nodes.forEach((node) => {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  });

  edges.forEach((edge) => {
    g.setEdge(edge.source, edge.target);
  });

  dagre.layout(g);

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = g.node(node.id);
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - NODE_WIDTH / 2,
        y: nodeWithPosition.y - NODE_HEIGHT / 2,
      },
    };
  });

  return { nodes: layoutedNodes, edges };
}

interface MissionFlowCanvasProps {
  missionId: string;
}

export const MissionFlowCanvas: React.FC<MissionFlowCanvasProps> = ({ missionId }) => {
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

  // Load data
  useEffect(() => {
    fetchMission(missionId);
    fetchMissionTasks(missionId);
    fetchMissionAgents(missionId);
    fetchMissionEvents(missionId);
  }, [missionId, fetchMission, fetchMissionTasks, fetchMissionAgents, fetchMissionEvents]);

  // WebSocket connection
  useEffect(() => {
    const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/v1/missions/${missionId}/ws`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const store = useMissionStore.getState();

        if (data.type === 'mission_event') {
          store.handleMissionEvent(data.event);
        } else if (data.type === 'mission_status') {
          store.handleMissionStatusUpdate(data);
        } else if (data.type === 'task_status') {
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

  // Build nodes and edges from mission data
  const { initialNodes, initialEdges } = useMemo(() => {
    const nodes: Node[] = [];
    const edges: Edge[] = [];

    if (!selectedMission) return { initialNodes: nodes, initialEdges: edges };

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
      edges.push({
        id: 'e-mission-requirements',
        source: 'mission',
        target: 'requirements',
        type: 'smoothstep',
        animated: selectedMission.status === 'requirements',
      });
    }

    // Clarification node for clarification events
    const clarificationEvents = missionEvents.filter(
      (e) => e.event_type === 'clarification_request' || e.event_type === 'clarification_response'
    );
    if (clarificationEvents.length > 0) {
      nodes.push({
        id: 'clarification',
        type: 'clarificationNode',
        position: { x: 0, y: 0 },
        data: {
          messages: clarificationEvents.map((e) => ({
            sender: e.event_type === 'clarification_request' ? 'leader' as const : 'user' as const,
            text: e.message || '',
          })),
          is_active: selectedMission.status === 'requirements',
        },
      });
      edges.push({
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
          assigned_agent_name: task.assigned_agent_name,
          acceptance_criteria: task.acceptance_criteria,
        },
      });

      // Edge from parent task or from requirements/mission
      if (task.parent_task_id) {
        edges.push({
          id: `e-task-${task.parent_task_id}-${task.task_id}`,
          source: `task-${task.parent_task_id}`,
          target: `task-${task.task_id}`,
          type: 'smoothstep',
          animated: task.status === 'in_progress',
        });
      } else {
        edges.push({
          id: `e-${parentEdgeSource}-task-${task.task_id}`,
          source: parentEdgeSource,
          target: `task-${task.task_id}`,
          type: 'smoothstep',
          animated: task.status === 'in_progress',
        });
      }

      // Dependency edges
      task.dependencies?.forEach((depId) => {
        edges.push({
          id: `e-dep-${depId}-${task.task_id}`,
          source: `task-${depId}`,
          target: `task-${task.task_id}`,
          type: 'smoothstep',
          style: { strokeDasharray: '3 3', stroke: '#94a3b8' },
          markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
        });
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
          edges.push({
            id: `e-agent-${agent.id}-task-${task.task_id}`,
            source: agentNodeId,
            target: `task-${task.task_id}`,
            type: 'smoothstep',
            style: { strokeDasharray: '5 5', stroke: '#06b6d4' },
          });
        });
      } else {
        // Connect to mission node
        edges.push({
          id: `e-agent-${agent.id}-mission`,
          source: 'mission',
          target: agentNodeId,
          type: 'smoothstep',
          style: { strokeDasharray: '5 5', stroke: '#06b6d4' },
        });
      }
    });

    // Review events as supervisor nodes
    const reviewEvents = missionEvents.filter((e) => e.event_type === 'task_review');
    reviewEvents.forEach((event, i) => {
      const nodeId = `supervisor-${i}`;
      const taskId = event.task_id ? `task-${event.task_id}` : null;
      nodes.push({
        id: nodeId,
        type: 'supervisorNode',
        position: { x: 0, y: 0 },
        data: {
          task_id: event.task_id || '',
          task_label: event.event_data?.task_label || 'Review',
          verdict: event.event_data?.verdict || 'pending',
          feedback: event.event_data?.feedback,
        },
      });
      if (taskId && nodes.some((n) => n.id === taskId)) {
        edges.push({
          id: `e-${taskId}-${nodeId}`,
          source: taskId,
          target: nodeId,
          type: 'smoothstep',
          style: { stroke: '#a855f7' },
        });
      }
    });

    // QA events
    const qaEvents = missionEvents.filter((e) => e.event_type === 'qa_audit');
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
      edges.push({
        id: `e-mission-${nodeId}`,
        source: 'mission',
        target: nodeId,
        type: 'smoothstep',
        style: { stroke: '#6366f1' },
      });
    });

    return { initialNodes: nodes, initialEdges: edges };
  }, [selectedMission, missionTasks, missionAgents, missionEvents]);

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

  const onInit = useCallback((instance: any) => {
    instance.fitView({ padding: 0.2 });
  }, []);

  if (!selectedMission) {
    return (
      <div className="flex items-center justify-center h-96 text-zinc-500">
        Loading mission...
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
