import React from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import type { Goal } from '@/types/task';

interface GoalCardProps {
  goal: Goal;
  onExpand: (goalId: string) => void;
  isExpanded: boolean;
}

export const GoalCard: React.FC<GoalCardProps> = ({ goal, onExpand, isExpanded }) => {
  const completedTasks = goal.tasks.filter((t) => t.status === 'completed').length;
  const totalTasks = goal.tasks.length;

  return (
    <div className="glass-panel rounded-[40px] overflow-hidden">
      <div className="bg-zinc-500/5 p-8 border-b border-zinc-500/5 flex justify-between items-center">
        <div>
          <h3 className="text-2xl font-bold tracking-tight">{goal.title}</h3>
          <p className="text-[10px] font-bold text-zinc-400 mt-2 uppercase tracking-widest">
            ID: {goal.id.toUpperCase()}
          </p>
        </div>
        <span className={`px-4 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-widest ${
          goal.status === 'completed' 
            ? 'bg-emerald-500/10 text-emerald-600' 
            : goal.status === 'failed'
            ? 'bg-red-500/10 text-red-600'
            : 'bg-blue-500/10 text-blue-600'
        }`}>
          {goal.status}
        </span>
      </div>
      
      <div className="p-8">
        <p className="text-zinc-600 dark:text-zinc-400 mb-6">{goal.description}</p>
        
        {totalTasks > 0 && (
          <div className="mb-6">
            <div className="flex items-center justify-between text-sm mb-2">
              <span className="text-zinc-500 dark:text-zinc-400">Progress</span>
              <span className="text-zinc-800 dark:text-white font-medium">
                {completedTasks}/{totalTasks} tasks
              </span>
            </div>
            <div className="w-full bg-zinc-500/10 h-1.5 rounded-full overflow-hidden">
              <div 
                className="bg-emerald-500 h-full transition-all duration-1000" 
                style={{ width: `${totalTasks > 0 ? (completedTasks / totalTasks) * 100 : 0}%` }}
              />
            </div>
          </div>
        )}

        {goal.clarificationNeeded && goal.clarificationQuestions && (
          <div className="mb-6 p-4 bg-yellow-500/10 border border-yellow-500/20 rounded-[16px]">
            <p className="text-sm font-bold text-yellow-700 dark:text-yellow-400 mb-2 uppercase tracking-wider">
              Clarification Needed:
            </p>
            <ul className="text-sm text-zinc-700 dark:text-zinc-300 space-y-1">
              {goal.clarificationQuestions.map((q, i) => (
                <li key={i}>• {q}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="flex items-center justify-between text-xs text-zinc-400">
          <span className="font-mono">{new Date(goal.createdAt).toLocaleString()}</span>
          <button
            onClick={() => onExpand(goal.id)}
            className="flex items-center gap-1 hover:text-emerald-500 transition-colors font-bold uppercase tracking-widest"
          >
            {isExpanded ? (
              <>
                <ChevronUp className="w-4 h-4" />
                Hide
              </>
            ) : (
              <>
                <ChevronDown className="w-4 h-4" />
                Details
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
