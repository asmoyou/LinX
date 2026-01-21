import React, { useMemo } from 'react';
import ReactFlow, {
  type Node,
  type Edge,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  MarkerType,
  BackgroundVariant,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { GlassPanel } from '@/components/GlassPanel';
import type { Task } from '@/types/task';

interface TaskFlowVisualizationProps {
  tasks: Task[];
}

export const TaskFlowVisualization: React.FC<TaskFlowVisualizationProps> = ({ tasks }) => {
  // Convert tasks to React Flow nodes
  const initialNodes: Node[] = useMemo(() => {
    return tasks.map((task, index) => {
      const getNodeColor = (status: Task['status']) => {
        switch (status) {
          case 'completed':
            return '#10b981'; // green
          case 'failed':
            return '#ef4444'; // red
          case 'in_progress':
            return '#3b82f6'; // blue
          case 'blocked':
            return '#f97316'; // orange
          default:
            return '#9ca3af'; // gray
        }
      };

      return {
        id: task.id,
        type: 'default',
        position: { x: 250 * (index % 3), y: 150 * Math.floor(index / 3) },
        data: {
          label: (
            <div className="text-center">
              <div className="font-medium text-sm">{task.title}</div>
              {task.assignedAgent && (
                <div className="text-xs text-gray-500 mt-1">{task.assignedAgent}</div>
              )}
              {task.status === 'in_progress' && (
                <div className="text-xs text-blue-600 mt-1">{task.progress}%</div>
              )}
            </div>
          ),
        },
        style: {
          background: 'rgba(255, 255, 255, 0.9)',
          border: `2px solid ${getNodeColor(task.status)}`,
          borderRadius: '8px',
          padding: '10px',
          width: 200,
        },
      };
    });
  }, [tasks]);

  // Convert task dependencies to React Flow edges
  const initialEdges: Edge[] = useMemo(() => {
    const edges: Edge[] = [];
    tasks.forEach((task) => {
      if (task.dependencies) {
        task.dependencies.forEach((depId) => {
          edges.push({
            id: `${depId}-${task.id}`,
            source: depId,
            target: task.id,
            type: 'smoothstep',
            animated: task.status === 'in_progress',
            markerEnd: {
              type: MarkerType.ArrowClosed,
              color: '#6366f1',
            },
            style: {
              stroke: '#6366f1',
              strokeWidth: 2,
            },
          });
        });
      }
    });
    return edges;
  }, [tasks]);

  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);

  // Update nodes when tasks change
  React.useEffect(() => {
    onNodesChange([{ type: 'reset', item: initialNodes }] as any);
  }, [initialNodes, onNodesChange]);

  // Update edges when tasks change
  React.useEffect(() => {
    onEdgesChange([{ type: 'reset', item: initialEdges }] as any);
  }, [initialEdges, onEdgesChange]);

  if (tasks.length === 0) {
    return (
      <GlassPanel>
        <p className="text-center text-gray-500 dark:text-gray-400 py-8">
          No tasks to visualize. Submit a goal to see the task flow.
        </p>
      </GlassPanel>
    );
  }

  return (
    <GlassPanel className="p-0 overflow-hidden">
      <div className="h-[600px] w-full">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          fitView
          attributionPosition="bottom-left"
        >
          <Controls />
          <Background variant={BackgroundVariant.Dots} gap={12} size={1} />
        </ReactFlow>
      </div>
      
      {/* Legend */}
      <div className="p-4 border-t border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-6 text-sm">
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded border-2 border-gray-400" />
            <span className="text-gray-600 dark:text-gray-400">Pending</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded border-2 border-blue-500" />
            <span className="text-gray-600 dark:text-gray-400">In Progress</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded border-2 border-green-500" />
            <span className="text-gray-600 dark:text-gray-400">Completed</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded border-2 border-orange-500" />
            <span className="text-gray-600 dark:text-gray-400">Blocked</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded border-2 border-red-500" />
            <span className="text-gray-600 dark:text-gray-400">Failed</span>
          </div>
        </div>
      </div>
    </GlassPanel>
  );
};
