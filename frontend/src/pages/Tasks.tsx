import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { LayoutGrid, List } from 'lucide-react';
import { GoalInput } from '@/components/tasks/GoalInput';
import { GoalCard } from '@/components/tasks/GoalCard';
import { TaskTimeline } from '@/components/tasks/TaskTimeline';
import { TaskFlowVisualization } from '@/components/tasks/TaskFlowVisualization';
import { TaskDetailsPanel } from '@/components/tasks/TaskDetailsPanel';
import { ClarificationModal } from '@/components/tasks/ClarificationModal';
import type { Goal, Task } from '@/types/task';

export const Tasks: React.FC = () => {
  const { t } = useTranslation();
  const [goals, setGoals] = useState<Goal[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [expandedGoalId, setExpandedGoalId] = useState<string | null>(null);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [isTaskDetailsPanelOpen, setIsTaskDetailsPanelOpen] = useState(false);
  const [clarificationGoal, setClarificationGoal] = useState<Goal | null>(null);
  const [viewMode, setViewMode] = useState<'timeline' | 'flow'>('timeline');

  // Mock data for demonstration
  useEffect(() => {
    const mockGoals: Goal[] = [
      {
        id: '1',
        title: 'Q4 Market Strategy Report',
        description: 'Generate comprehensive sales report for Q4 2025',
        status: 'executing',
        createdAt: new Date().toISOString(),
        tasks: [
          {
            id: 't1',
            title: 'Analyze competitor performance',
            status: 'completed',
            progress: 100,
            assignedAgent: 'Analyst-Prime',
            startTime: new Date(Date.now() - 3600000).toISOString(),
            endTime: new Date(Date.now() - 3000000).toISOString(),
            result: 'Competitors show a 15% increase in cloud adoption',
          },
          {
            id: 't2',
            title: 'Draft executive summary',
            status: 'in_progress',
            progress: 45,
            assignedAgent: 'Scribe-7',
            dependencies: ['t1'],
            startTime: new Date(Date.now() - 2400000).toISOString(),
          },
          {
            id: 't3',
            title: 'Generate statistical analysis',
            status: 'pending',
            progress: 0,
            dependencies: ['t2'],
          },
        ],
      },
    ];
    setGoals(mockGoals);
  }, []);

  const handleGoalSubmit = async (title: string, description: string) => {
    setIsSubmitting(true);
    
    // Simulate API call
    await new Promise((resolve) => setTimeout(resolve, 2000));

    const newGoal: Goal = {
      id: String(goals.length + 1),
      title,
      description,
      status: 'analyzing',
      createdAt: new Date().toISOString(),
      tasks: [],
    };

    setGoals([newGoal, ...goals]);
    setIsSubmitting(false);

    // Simulate task decomposition
    setTimeout(() => {
      const goalWithTasks = {
        ...newGoal,
        status: 'executing' as const,
        tasks: [
          {
            id: `t${Date.now()}-1`,
            title: 'Gather required data',
            status: 'in_progress' as const,
            progress: 30,
            assignedAgent: 'Analyst-Beta',
            startTime: new Date().toISOString(),
          },
        ],
      };
      setGoals((prev) => prev.map((g) => (g.id === newGoal.id ? goalWithTasks : g)));
    }, 2000);
  };

  const handleClarificationSubmit = (answers: string[]) => {
    if (!clarificationGoal) return;
    setClarificationGoal(null);
  };

  const handleExpandGoal = (goalId: string) => {
    setExpandedGoalId(expandedGoalId === goalId ? null : goalId);
  };

  const expandedGoal = goals.find((g) => g.id === expandedGoalId);

  return (
    <div className="space-y-10 animate-in fade-in slide-in-from-bottom-6 duration-700">
      <header>
        <h1 className="text-4xl font-bold tracking-tight mb-2 text-zinc-800 dark:text-zinc-200">
          {t('nav.tasks')}
        </h1>
        <p className="text-zinc-600 dark:text-zinc-400 font-medium">
          Submit goals and watch AI agents decompose and execute tasks
        </p>
      </header>

      {/* Goal Input */}
      <div className="mb-6">
        <GoalInput onSubmit={handleGoalSubmit} isLoading={isSubmitting} />
      </div>

      {/* Goals List */}
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-zinc-800 dark:text-white mb-4">Active Goals</h2>
        {goals.length === 0 ? (
          <div className="text-center py-12 text-zinc-500 dark:text-zinc-400">
            No goals yet. Submit a goal above to get started.
          </div>
        ) : (
          <div className="space-y-4">
            {goals.map((goal) => (
              <GoalCard
                key={goal.id}
                goal={goal}
                onExpand={handleExpandGoal}
                isExpanded={expandedGoalId === goal.id}
              />
            ))}
          </div>
        )}
      </div>

      {/* Task Visualization */}
      {expandedGoal && expandedGoal.tasks.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-zinc-800 dark:text-white">
              Task Visualization
            </h2>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setViewMode('timeline')}
                className={`p-2 rounded-lg transition-colors ${
                  viewMode === 'timeline'
                    ? 'bg-emerald-500 text-white'
                    : 'bg-zinc-500/5 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-500/10'
                }`}
              >
                <List className="w-5 h-5" />
              </button>
              <button
                onClick={() => setViewMode('flow')}
                className={`p-2 rounded-lg transition-colors ${
                  viewMode === 'flow'
                    ? 'bg-emerald-500 text-white'
                    : 'bg-zinc-500/5 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-500/10'
                }`}
              >
                <LayoutGrid className="w-5 h-5" />
              </button>
            </div>
          </div>

          {viewMode === 'timeline' ? (
            <TaskTimeline tasks={expandedGoal.tasks} />
          ) : (
            <TaskFlowVisualization tasks={expandedGoal.tasks} />
          )}
        </div>
      )}

      {/* Modals */}
      <TaskDetailsPanel
        task={selectedTask}
        isOpen={isTaskDetailsPanelOpen}
        onClose={() => {
          setIsTaskDetailsPanelOpen(false);
          setSelectedTask(null);
        }}
      />
      <ClarificationModal
        isOpen={!!clarificationGoal}
        questions={clarificationGoal?.clarificationQuestions || []}
        onClose={() => setClarificationGoal(null)}
        onSubmit={handleClarificationSubmit}
      />
    </div>
  );
};
