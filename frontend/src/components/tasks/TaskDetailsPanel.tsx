import React from 'react';
import { User, Clock, CheckCircle, AlertTriangle, Layers } from 'lucide-react';
import { LayoutModal } from '@/components/LayoutModal';
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
        return 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/20';
      case 'failed':
        return 'text-red-600 dark:text-red-400 bg-red-500/10 border-red-500/20';
      case 'in_progress':
        return 'text-blue-600 dark:text-blue-400 bg-blue-500/10 border-blue-500/20';
      case 'blocked':
        return 'text-amber-600 dark:text-amber-400 bg-amber-500/10 border-amber-500/20';
      default:
        return 'text-zinc-600 dark:text-zinc-400 bg-zinc-500/10 border-zinc-500/20';
    }
  };

  return (
    <LayoutModal
      isOpen={isOpen}
      onClose={onClose}
      size="2xl"
      title={
        <div className="flex items-center gap-2 text-zinc-900 dark:text-zinc-100">
          <Layers className="w-5 h-5 text-indigo-500" />
          <span>Task Details</span>
        </div>
      }
      closeOnBackdropClick={true}
    >
      <div className="space-y-6">
        {/* Status Badge */}
        <div>
          <span className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium border ${getStatusColor(task.status)}`}>
            {task.status === 'completed' && <CheckCircle className="w-4 h-4" />}
            {task.status === 'failed' && <AlertTriangle className="w-4 h-4" />}
            <span className="capitalize">{task.status.replace('_', ' ')}</span>
          </span>
        </div>

        {/* Title and Description */}
        <div>
          <h3 className="text-xl font-semibold text-zinc-900 dark:text-white mb-2 leading-tight">
            {task.title}
          </h3>
          {task.description && (
            <p className="text-zinc-600 dark:text-zinc-400 leading-relaxed">{task.description}</p>
          )}
        </div>

        {/* Progress */}
        {task.status === 'in_progress' && (
          <div className="bg-zinc-50 dark:bg-zinc-900/50 p-4 rounded-xl border border-zinc-100 dark:border-zinc-800/60">
            <div className="flex items-center justify-between text-sm mb-3">
              <span className="font-medium text-zinc-700 dark:text-zinc-300">Execution Progress</span>
              <span className="text-indigo-600 dark:text-indigo-400 font-bold">{task.progress}%</span>
            </div>
            <div className="w-full h-2.5 bg-zinc-200 dark:bg-zinc-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-500 transition-all duration-500 ease-out"
                style={{ width: `${task.progress}%` }}
              />
            </div>
          </div>
        )}

        {/* Metadata Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {task.assignedAgent && (
            <div className="p-4 bg-zinc-50 dark:bg-zinc-900/50 border border-zinc-100 dark:border-zinc-800/60 rounded-xl flex items-center gap-4">
              <div className="p-2.5 bg-indigo-500/10 rounded-lg shrink-0">
                <User className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400 mb-0.5">Assigned Agent</p>
                <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 truncate">{task.assignedAgent}</p>
              </div>
            </div>
          )}
          {task.startTime && (
            <div className="p-4 bg-zinc-50 dark:bg-zinc-900/50 border border-zinc-100 dark:border-zinc-800/60 rounded-xl flex items-center gap-4">
              <div className="p-2.5 bg-blue-500/10 rounded-lg shrink-0">
                <Clock className="w-5 h-5 text-blue-600 dark:text-blue-400" />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400 mb-0.5">Start Time</p>
                <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 truncate">
                  {new Date(task.startTime).toLocaleString()}
                </p>
              </div>
            </div>
          )}
          {task.endTime && (
            <div className="p-4 bg-zinc-50 dark:bg-zinc-900/50 border border-zinc-100 dark:border-zinc-800/60 rounded-xl flex items-center gap-4">
              <div className="p-2.5 bg-emerald-500/10 rounded-lg shrink-0">
                <Clock className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400 mb-0.5">End Time</p>
                <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 truncate">
                  {new Date(task.endTime).toLocaleString()}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Dependencies */}
        {task.dependencies && task.dependencies.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mb-3">
              Dependencies
            </h4>
            <div className="flex flex-wrap gap-2">
              {task.dependencies.map((depId) => (
                <span
                  key={depId}
                  className="px-3 py-1 bg-zinc-100 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700/50 rounded-lg text-xs font-medium text-zinc-700 dark:text-zinc-300"
                >
                  Task {depId}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Result */}
        {task.result && (
          <div>
            <h4 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mb-3">Result</h4>
            <div className="p-4 bg-emerald-50 dark:bg-emerald-500/5 border border-emerald-200 dark:border-emerald-500/20 rounded-xl">
              <p className="text-sm text-emerald-800 dark:text-emerald-200 whitespace-pre-wrap leading-relaxed">{task.result}</p>
            </div>
          </div>
        )}

        {/* Error */}
        {task.error && (
          <div>
            <h4 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mb-3">Error</h4>
            <div className="p-4 bg-red-50 dark:bg-red-500/5 border border-red-200 dark:border-red-500/20 rounded-xl">
              <p className="text-sm text-red-800 dark:text-red-200 whitespace-pre-wrap leading-relaxed">{task.error}</p>
            </div>
          </div>
        )}
      </div>
    </LayoutModal>
  );
};

