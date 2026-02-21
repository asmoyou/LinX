import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { createPortal } from 'react-dom';
import { ListTodo, X } from 'lucide-react';
import type { MissionAgent, MissionTask } from '@/types/mission';

interface TaskListPanelProps {
  isOpen: boolean;
  onClose: () => void;
  tasks: MissionTask[];
  agents: MissionAgent[];
}

function statusBadgeClass(status: string): string {
  switch (status) {
    case 'completed':
      return 'bg-green-100 text-green-700 dark:bg-green-500/10 dark:text-green-400';
    case 'in_progress':
      return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400';
    case 'failed':
      return 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400';
    case 'reviewing':
      return 'bg-purple-100 text-purple-700 dark:bg-purple-500/10 dark:text-purple-400';
    default:
      return 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400';
  }
}

export const TaskListPanel: React.FC<TaskListPanelProps> = ({
  isOpen,
  onClose,
  tasks,
  agents,
}) => {
  const { t } = useTranslation();
  const agentNameById = useMemo(
    () =>
      new Map(
        agents
          .filter((agent) => Boolean(agent.agent_id))
          .map((agent) => [agent.agent_id, agent.agent_name || agent.role || 'Agent'])
      ),
    [agents]
  );

  if (!isOpen) return null;

  const panel = (
    <div
      className="fixed right-0 z-[60] glass-panel border-l border-zinc-200 dark:border-zinc-700 pointer-events-auto flex flex-col animate-in slide-in-from-right duration-300 shadow-2xl"
      style={{
        top: 'var(--app-header-height, 4rem)',
        height: 'calc(100vh - var(--app-header-height, 4rem))',
        width: 'min(42vw, 560px)',
      }}
    >
      <div className="flex items-center justify-between p-4 border-b border-zinc-200 dark:border-zinc-700">
        <div className="flex items-center gap-2 min-w-0">
          <ListTodo className="w-4 h-4 text-cyan-500" />
          <h3 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200 truncate">
            {t('missions.taskListTitle', 'Task List')}
          </h3>
          <span className="text-xs text-zinc-400">({tasks.length})</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-1 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors"
        >
          <X className="w-4 h-4 text-zinc-500" />
        </button>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto p-4 custom-scrollbar space-y-4">
        {agents.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {agents.map((agent) => (
              <span
                key={agent.id}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] bg-cyan-50 text-cyan-700 dark:bg-cyan-500/10 dark:text-cyan-300 border border-cyan-200 dark:border-cyan-500/20"
              >
                <span className="font-semibold">
                  {agent.agent_name || t('missions.unknownAgent', 'Agent')}
                </span>
                <span className="opacity-80">({agent.role})</span>
              </span>
            ))}
          </div>
        )}

        {tasks.length === 0 ? (
          <div className="text-sm text-zinc-500 py-3">
            {t('missions.noPlannedTasksYet', 'Tasks have not been planned yet.')}
          </div>
        ) : (
          <div className="space-y-2">
            {tasks.map((task) => {
              const owner =
                task.assigned_agent_name ||
                (task.assigned_agent_id ? agentNameById.get(task.assigned_agent_id) : undefined) ||
                t('missions.unassigned', 'Unassigned');

              return (
                <div
                  key={task.task_id}
                  className="rounded-lg border border-zinc-200 dark:border-zinc-700 px-3 py-2.5 bg-white/70 dark:bg-zinc-900/60"
                >
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-sm text-zinc-800 dark:text-zinc-200 leading-6">
                      {task.goal_text}
                    </p>
                    <span
                      className={`text-[11px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap ${statusBadgeClass(
                        task.status
                      )}`}
                    >
                      {task.status}
                    </span>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-zinc-500">
                    <span>
                      {t('missions.owner', 'Owner')}: {owner}
                    </span>
                    <span>•</span>
                    <span>
                      {t('missions.priorityShort', 'P')}: {task.priority ?? 0}
                    </span>
                    <span>•</span>
                    <span>
                      {t('missions.dependenciesShort', 'Deps')}:{' '}
                      {Array.isArray(task.dependencies) ? task.dependencies.length : 0}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );

  if (typeof document === 'undefined') {
    return panel;
  }
  return createPortal(panel, document.body);
};
