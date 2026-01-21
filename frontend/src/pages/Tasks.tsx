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
        title: 'Analyze Q4 Sales Data',
        description: 'Generate comprehensive sales report for Q4 2025',
        status: 'executing',
        createdAt: new Date().toISOString(),
        tasks: [
          {
            id: 't1',
            title: 'Extract sales data from database',
            status: 'completed',
            progress: 100,
            assignedAgent: 'Data Analyst #1',
            startTime: new Date(Date.now() - 3600000).toISOString(),
            endTime: new Date(Date.now() - 3000000).toISOString(),
            result: 'Successfully extracted 15,234 sales records',
          },
          {
            id: 't2',
            title: 'Clean and normalize data',
            status: 'in_progress',
            progress: 65,
            assignedAgent: 'Data Analyst #1',
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
          {
            id: 't4',
            title: 'Create visualizations',
            status: 'pending',
            progress: 0,
            dependencies: ['t3'],
          },
          {
            id: 't5',
            title: 'Write executive summary',
            status: 'pending',
            progress: 0,
            assignedAgent: 'Content Writer #1',
            dependencies: ['t3', 't4'],
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

    // Simulate clarification needed
    setTimeout(() => {
      const updatedGoal = {
        ...newGoal,
        clarificationNeeded: true,
        clarificationQuestions: [
          'What specific metrics should be included in the analysis?',
          'What is the preferred format for the final report?',
        ],
      };
      setGoals((prev) => prev.map((g) => (g.id === newGoal.id ? updatedGoal : g)));
      setClarificationGoal(updatedGoal);
    }, 3000);
  };

  const handleClarificationSubmit = (answers: string[]) => {
    if (!clarificationGoal) return;

    // Update goal status
    const updatedGoal = {
      ...clarificationGoal,
      clarificationNeeded: false,
      status: 'decomposing' as const,
    };
    setGoals((prev) => prev.map((g) => (g.id === clarificationGoal.id ? updatedGoal : g)));
    setClarificationGoal(null);

    // Simulate task decomposition
    setTimeout(() => {
      const goalWithTasks = {
        ...updatedGoal,
        status: 'executing' as const,
        tasks: [
          {
            id: `t${Date.now()}-1`,
            title: 'Gather required data',
            status: 'in_progress' as const,
            progress: 30,
            assignedAgent: 'Data Analyst #2',
            startTime: new Date().toISOString(),
          },
        ],
      };
      setGoals((prev) => prev.map((g) => (g.id === updatedGoal.id ? goalWithTasks : g)));
    }, 2000);
  };

  const handleExpandGoal = (goalId: string) => {
    setExpandedGoalId(expandedGoalId === goalId ? null : goalId);
  };

  const expandedGoal = goals.find((g) => g.id === expandedGoalId);

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-800 dark:text-white mb-6">
        {t('nav.tasks')}
      </h1>

      {/* Goal Input */}
      <div className="mb-6">
        <GoalInput onSubmit={handleGoalSubmit} isLoading={isSubmitting} />
      </div>

      {/* Goals List */}
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-gray-800 dark:text-white mb-4">Active Goals</h2>
        {goals.length === 0 ? (
          <div className="text-center py-12 text-gray-500 dark:text-gray-400">
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
            <h2 className="text-xl font-semibold text-gray-800 dark:text-white">
              Task Visualization
            </h2>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setViewMode('timeline')}
                className={`p-2 rounded-lg transition-colors ${
                  viewMode === 'timeline'
                    ? 'bg-primary-500 text-white'
                    : 'bg-white/20 text-gray-700 dark:text-gray-300 hover:bg-white/30'
                }`}
              >
                <List className="w-5 h-5" />
              </button>
              <button
                onClick={() => setViewMode('flow')}
                className={`p-2 rounded-lg transition-colors ${
                  viewMode === 'flow'
                    ? 'bg-primary-500 text-white'
                    : 'bg-white/20 text-gray-700 dark:text-gray-300 hover:bg-white/30'
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
