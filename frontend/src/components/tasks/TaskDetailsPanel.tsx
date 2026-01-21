import React from 'react';
import { X, User, Clock, CheckCircle, AlertTriangle } from 'lucide-react';
import { GlassPanel } from '@/components/GlassPanel';
import type { Task } from '@/types/task';

interface TaskDetailsPanelProps {
  task: Task | null;
  isOpen: boolean;
  onClose: () => void;
}

export const TaskDetailsPanel: React.FC<TaskDetailsPanelProps> = ({ task, isOpen, onClose }) => {
  if (!isOpen || !task) return null;

  const getStatusColor = (status: Task['status']) => {
    switch (status) {
      case 'completed':
        return 'text-green-500 bg-green-500/10';
      case 'failed':
        return 'text-red-500 bg-red-500/10';
      case 'in_progress':
        return 'text-blue-500 bg-blue-500/10';
      case 'blocked':
        return 'text-orange-500 bg-orange-500/10';
      default:
        return 'text-gray-500 bg-gray-500/10';
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <GlassPanel className="w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-gray-800 dark:text-white">Task Details</h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/20 rounded-lg transition-colors"
          >
            <X className="w-6 h-6 text-gray-700 dark:text-gray-300" />
          </button>
        </div>

        {/* Status Badge */}
        <div className="mb-6">
          <span className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium ${getStatusColor(task.status)}`}>
            {task.status === 'completed' && <CheckCircle className="w-4 h-4" />}
            {task.status === 'failed' && <AlertTriangle className="w-4 h-4" />}
            <span className="capitalize">{task.status.replace('_', ' ')}</span>
          </span>
        </div>

        {/* Title and Description */}
        <div className="mb-6">
          <h3 className="text-xl font-semibold text-gray-800 dark:text-white mb-2">
            {task.title}
          </h3>
          {task.description && (
            <p className="text-gray-600 dark:text-gray-400">{task.description}</p>
          )}
        </div>

        {/* Progress */}
        {task.status === 'in_progress' && (
          <div className="mb-6">
            <div className="flex items-center justify-between text-sm mb-2">
              <span className="text-gray-600 dark:text-gray-400">Progress</span>
              <span className="text-gray-800 dark:text-white font-medium">{task.progress}%</span>
            </div>
            <div className="w-full h-3 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 transition-all duration-500"
                style={{ width: `${task.progress}%` }}
              />
            </div>
          </div>
        )}

        {/* Metadata Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          {task.assignedAgent && (
            <div className="p-4 bg-white/10 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <User className="w-5 h-5 text-indigo-500" />
                <span className="text-sm text-gray-600 dark:text-gray-400">Assigned Agent</span>
              </div>
              <p className="text-gray-800 dark:text-white font-medium">{task.assignedAgent}</p>
            </div>
          )}
          {task.startTime && (
            <div className="p-4 bg-white/10 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <Clock className="w-5 h-5 text-blue-500" />
                <span className="text-sm text-gray-600 dark:text-gray-400">Start Time</span>
              </div>
              <p className="text-gray-800 dark:text-white font-medium">
                {new Date(task.startTime).toLocaleString()}
              </p>
            </div>
          )}
          {task.endTime && (
            <div className="p-4 bg-white/10 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <Clock className="w-5 h-5 text-green-500" />
                <span className="text-sm text-gray-600 dark:text-gray-400">End Time</span>
              </div>
              <p className="text-gray-800 dark:text-white font-medium">
                {new Date(task.endTime).toLocaleString()}
              </p>
            </div>
          )}
        </div>

        {/* Dependencies */}
        {task.dependencies && task.dependencies.length > 0 && (
          <div className="mb-6">
            <h4 className="text-lg font-semibold text-gray-800 dark:text-white mb-2">
              Dependencies
            </h4>
            <div className="flex flex-wrap gap-2">
              {task.dependencies.map((depId) => (
                <span
                  key={depId}
                  className="px-3 py-1 bg-white/10 rounded-full text-sm text-gray-700 dark:text-gray-300"
                >
                  Task {depId}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Result */}
        {task.result && (
          <div className="mb-6">
            <h4 className="text-lg font-semibold text-gray-800 dark:text-white mb-2">Result</h4>
            <div className="p-4 bg-green-500/10 border border-green-500/30 rounded-lg">
              <p className="text-gray-700 dark:text-gray-300">{task.result}</p>
            </div>
          </div>
        )}

        {/* Error */}
        {task.error && (
          <div className="mb-6">
            <h4 className="text-lg font-semibold text-gray-800 dark:text-white mb-2">Error</h4>
            <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
              <p className="text-red-700 dark:text-red-400">{task.error}</p>
            </div>
          </div>
        )}
      </GlassPanel>
    </div>
  );
};
