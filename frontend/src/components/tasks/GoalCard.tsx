import React from 'react';
import { Target, Clock, CheckCircle, XCircle, AlertCircle, ChevronDown, ChevronUp } from 'lucide-react';
import { GlassPanel } from '@/components/GlassPanel';
import type { Goal } from '@/types/task';

interface GoalCardProps {
  goal: Goal;
  onExpand: (goalId: string) => void;
  isExpanded: boolean;
}

export const GoalCard: React.FC<GoalCardProps> = ({ goal, onExpand, isExpanded }) => {
  const getStatusColor = (status: Goal['status']) => {
    switch (status) {
      case 'completed':
        return 'text-green-500';
      case 'failed':
        return 'text-red-500';
      case 'executing':
        return 'text-blue-500';
      case 'analyzing':
      case 'decomposing':
        return 'text-yellow-500';
      default:
        return 'text-gray-500';
    }
  };

  const getStatusIcon = (status: Goal['status']) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="w-5 h-5" />;
      case 'failed':
        return <XCircle className="w-5 h-5" />;
      case 'executing':
        return <Clock className="w-5 h-5 animate-pulse" />;
      default:
        return <AlertCircle className="w-5 h-5" />;
    }
  };

  const completedTasks = goal.tasks.filter((t) => t.status === 'completed').length;
  const totalTasks = goal.tasks.length;
  const progress = totalTasks > 0 ? (completedTasks / totalTasks) * 100 : 0;

  return (
    <GlassPanel className="hover:scale-[1.01] transition-transform duration-200">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-start gap-3 flex-1">
          <Target className="w-6 h-6 text-indigo-500 mt-1" />
          <div className="flex-1">
            <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-1">
              {goal.title}
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2">
              {goal.description}
            </p>
          </div>
        </div>
        <div className={`flex items-center gap-2 ${getStatusColor(goal.status)}`}>
          {getStatusIcon(goal.status)}
          <span className="text-sm font-medium capitalize">{goal.status.replace('_', ' ')}</span>
        </div>
      </div>

      {/* Progress Bar */}
      {totalTasks > 0 && (
        <div className="mb-4">
          <div className="flex items-center justify-between text-sm mb-2">
            <span className="text-gray-600 dark:text-gray-400">Progress</span>
            <span className="text-gray-800 dark:text-white font-medium">
              {completedTasks}/{totalTasks} tasks
            </span>
          </div>
          <div className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-indigo-500 transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {/* Clarification Questions */}
      {goal.clarificationNeeded && goal.clarificationQuestions && (
        <div className="mb-4 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
          <p className="text-sm font-medium text-yellow-700 dark:text-yellow-400 mb-2">
            Clarification Needed:
          </p>
          <ul className="text-sm text-gray-700 dark:text-gray-300 space-y-1">
            {goal.clarificationQuestions.map((q, i) => (
              <li key={i}>• {q}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Metadata */}
      <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
        <span>Created: {new Date(goal.createdAt).toLocaleString()}</span>
        <button
          onClick={() => onExpand(goal.id)}
          className="flex items-center gap-1 hover:text-indigo-500 transition-colors"
        >
          {isExpanded ? (
            <>
              <ChevronUp className="w-4 h-4" />
              Hide Details
            </>
          ) : (
            <>
              <ChevronDown className="w-4 h-4" />
              Show Details
            </>
          )}
        </button>
      </div>
    </GlassPanel>
  );
};
