import React from 'react';
import { Clock, CheckCircle, XCircle, Loader2, Ban } from 'lucide-react';
import { GlassPanel } from '@/components/GlassPanel';
import type { Task } from '@/types/task';

interface TaskTimelineProps {
  tasks: Task[];
}

export const TaskTimeline: React.FC<TaskTimelineProps> = ({ tasks }) => {
  const getStatusIcon = (status: Task['status']) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="w-5 h-5 text-green-500" />;
      case 'failed':
        return <XCircle className="w-5 h-5 text-red-500" />;
      case 'in_progress':
        return <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />;
      case 'blocked':
        return <Ban className="w-5 h-5 text-orange-500" />;
      default:
        return <Clock className="w-5 h-5 text-gray-400" />;
    }
  };

  const getStatusColor = (status: Task['status']) => {
    switch (status) {
      case 'completed':
        return 'border-green-500';
      case 'failed':
        return 'border-red-500';
      case 'in_progress':
        return 'border-blue-500';
      case 'blocked':
        return 'border-orange-500';
      default:
        return 'border-gray-400';
    }
  };

  if (tasks.length === 0) {
    return (
      <GlassPanel>
        <p className="text-center text-gray-500 dark:text-gray-400 py-8">
          No tasks yet. Submit a goal to get started.
        </p>
      </GlassPanel>
    );
  }

  return (
    <GlassPanel>
      <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-4">Task Timeline</h3>
      <div className="space-y-4">
        {tasks.map((task, index) => (
          <div key={task.id} className="flex gap-4">
            {/* Timeline Line */}
            <div className="flex flex-col items-center">
              <div className={`p-2 rounded-full border-2 ${getStatusColor(task.status)} bg-white dark:bg-gray-800`}>
                {getStatusIcon(task.status)}
              </div>
              {index < tasks.length - 1 && (
                <div className="w-0.5 h-full min-h-[40px] bg-gray-300 dark:bg-gray-600 my-1" />
              )}
            </div>

            {/* Task Content */}
            <div className="flex-1 pb-4">
              <div className="flex items-start justify-between mb-2">
                <div className="flex-1">
                  <h4 className="font-medium text-gray-800 dark:text-white">{task.title}</h4>
                  {task.description && (
                    <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                      {task.description}
                    </p>
                  )}
                </div>
                <span className="text-xs text-gray-500 dark:text-gray-400 capitalize ml-2">
                  {task.status.replace('_', ' ')}
                </span>
              </div>

              {/* Progress Bar */}
              {task.status === 'in_progress' && (
                <div className="mb-2">
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="text-gray-600 dark:text-gray-400">Progress</span>
                    <span className="text-gray-800 dark:text-white font-medium">
                      {task.progress}%
                    </span>
                  </div>
                  <div className="w-full h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-500 transition-all duration-500"
                      style={{ width: `${task.progress}%` }}
                    />
                  </div>
                </div>
              )}

              {/* Metadata */}
              <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
                {task.assignedAgent && (
                  <span>Agent: {task.assignedAgent}</span>
                )}
                {task.startTime && (
                  <span>Started: {new Date(task.startTime).toLocaleTimeString()}</span>
                )}
                {task.endTime && (
                  <span>Ended: {new Date(task.endTime).toLocaleTimeString()}</span>
                )}
              </div>

              {/* Error Message */}
              {task.error && (
                <div className="mt-2 p-2 bg-red-500/10 border border-red-500/30 rounded text-sm text-red-700 dark:text-red-400">
                  {task.error}
                </div>
              )}

              {/* Result */}
              {task.result && (
                <div className="mt-2 p-2 bg-green-500/10 border border-green-500/30 rounded text-sm text-gray-700 dark:text-gray-300">
                  {task.result}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </GlassPanel>
  );
};
