import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';

import { LaunchRunModal } from '@/components/platform/ProjectExecutionFormModal';
import {
  EmptyState,
  LoadingState,
  NoticeBanner,
  SectionCard,
  StatusBadge,
} from '@/components/platform/PlatformUi';
import { useProjectExecutionStore } from '@/stores/projectExecutionStore';
import { formatDateTime } from '@/utils/platformFormatting';

export const ProjectTaskDetail = () => {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [isLaunchModalOpen, setIsLaunchModalOpen] = useState(false);
  const [isLaunching, setIsLaunching] = useState(false);
  const [isDeletingTask, setIsDeletingTask] = useState(false);
  const { projectId, taskId } = useParams<{ projectId: string; taskId: string }>();
  const task = useProjectExecutionStore((state) =>
    projectId && taskId ? state.projectTaskDetails[`${projectId}:${taskId}`] : undefined,
  );
  const isLoading = useProjectExecutionStore((state) => state.loading.projectTaskDetail);
  const error = useProjectExecutionStore((state) => state.errors.projectTaskDetail);
  const fallbackSections = useProjectExecutionStore((state) => state.fallbackSections);
  const loadProjectTaskDetail = useProjectExecutionStore((state) => state.loadProjectTaskDetail);
  const launchTaskRun = useProjectExecutionStore((state) => state.launchTaskRun);
  const deleteProjectTask = useProjectExecutionStore((state) => state.deleteProjectTask);

  useEffect(() => {
    if (projectId && taskId) {
      void loadProjectTaskDetail(projectId, taskId);
    }
  }, [loadProjectTaskDetail, projectId, taskId]);

  const isFallback = fallbackSections.includes('projectTaskDetail');

  const handleDeleteTask = async () => {
    if (!projectId || !taskId || isFallback) return;

    if (!window.confirm(t('projectExecution.taskDetail.deleteConfirm', 'Delete this task?'))) {
      return;
    }

    try {
      setIsDeletingTask(true);
      await deleteProjectTask(projectId, taskId);
      toast.success(t('projectExecution.taskDetail.deleteSuccess', 'Task deleted'));
      navigate(`/projects/${projectId}`);
    } catch (deleteError) {
      const message = deleteError instanceof Error
        ? deleteError.message
        : t('projectExecution.taskDetail.deleteFailed', 'Failed to delete task');
      toast.error(message);
    } finally {
      setIsDeletingTask(false);
    }
  };

  const handleLaunchRun = async () => {
    if (!projectId || !taskId || !task) return;

    try {
      setIsLaunching(true);
      const runId = await launchTaskRun({
        projectId,
        taskId,
        title: task.title,
        description: task.description,
      });
      toast.success(t('projectExecution.taskDetail.launchSuccess', 'Plan generated and run started'));
      setIsLaunchModalOpen(false);
      navigate(`/runs/${runId}`);
    } catch (launchError) {
      const message = launchError instanceof Error ? launchError.message : t('projectExecution.taskDetail.launchError', 'Failed to start run');
      toast.error(message);
    } finally {
      setIsLaunching(false);
    }
  };

  if (!projectId || !taskId) {
    return <EmptyState title={t('projectExecution.taskDetail.taskNotFound', 'Task not found')} description={t('projectExecution.taskDetail.taskNotFoundDescription', 'Missing task identifier.')} />;
  }

  if (isLoading && !task) {
    return <LoadingState label={t('projectExecution.taskDetail.loading', 'Loading task detail…')} />;
  }

  if (!task) {
    return (
      <EmptyState
        title={t('projectExecution.taskDetail.taskUnavailable', 'Task unavailable')}
        description={error || t('projectExecution.taskDetail.taskUnavailableDescription', 'Task detail could not be loaded.')}
      />
    );
  }

  return (
    <>
      <div className="space-y-6">
        {isFallback ? (
          <NoticeBanner
            title={t('projectExecution.taskDetail.fallbackTitle', 'Fallback task detail')}
            description={t('projectExecution.taskDetail.fallbackDescription', 'This task is currently sourced from fallback data, so run creation is disabled.')}
          />
        ) : null}

        {error ? <NoticeBanner title={t('projectExecution.taskDetail.errorTitle', 'Task detail warning')} description={error} /> : null}

        {['queued', 'assigned', 'scheduled'].includes(String(task.status).toLowerCase()) ? (
          <NoticeBanner
            title={t('projectExecution.taskDetail.dispatchTitle', 'Waiting for execution progress')}
            description={
              task.assignedAgentName
                ? t('projectExecution.taskDetail.dispatchDescriptionAssigned', { agent: task.assignedAgentName, defaultValue: `Assigned to ${task.assignedAgentName}; execution is being prepared in the run sandbox.` })
                : t('projectExecution.taskDetail.dispatchDescriptionUnassigned', 'The task has been queued, but no executor has been assigned yet.')
            }
          />
        ) : null}

        <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl space-y-3">
            <p className="text-sm font-semibold uppercase tracking-[0.22em] text-indigo-500">{t('projectExecution.shared.task', 'Task')}</p>
            <div>
              <h1 className="text-3xl font-semibold text-zinc-950 dark:text-zinc-50">{task.title}</h1>
              <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{task.description}</p>
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => setIsLaunchModalOpen(true)}
              disabled={isFallback || isDeletingTask}
              className="rounded-full bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >{t('projectExecution.taskDetail.launchAction', 'Generate Plan + Start Run')}
            </button>
            <button
              type="button"
              onClick={handleDeleteTask}
              disabled={isFallback || isDeletingTask}
              className="rounded-full border border-rose-300 px-4 py-2 text-sm font-medium text-rose-700 transition hover:bg-rose-50 dark:border-rose-800 dark:text-rose-300 dark:hover:bg-rose-950/40 disabled:cursor-not-allowed disabled:opacity-50"
            >{isDeletingTask ? t('projectExecution.shared.deleting', 'Deleting…') : t('projectExecution.shared.deleteTask', 'Delete Task')}
            </button>
            <StatusBadge status={task.status} />
          </div>
        </section>

        <SectionCard title={t('projectExecution.taskDetail.executionContextTitle', 'Execution context')} description={t('projectExecution.taskDetail.executionContextDescription', 'Task-level runtime and assignment metadata.')}>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <div className="rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50">
              <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">{t('projectExecution.taskDetail.assignedAgent', 'Assigned Agent')}</p>
              <p className="mt-2 text-sm text-zinc-800 dark:text-zinc-200">
                {task.assignedAgentName || t('projectExecution.taskDetail.noAssignedAgent', 'No executor assigned yet')}
              </p>
              <p className="mt-3 text-sm font-medium text-zinc-500 dark:text-zinc-400">{t('projectExecution.taskDetail.assignedSkills', 'Assigned skills')}</p>
              <p className="mt-2 text-sm text-zinc-800 dark:text-zinc-200">
                {task.assignedSkillNames.length > 0 ? task.assignedSkillNames.join(', ') : t('projectExecution.taskDetail.noSkills', 'No skills linked')}
              </p>
            </div>
            <div className="rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50">
              <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">{t('projectExecution.taskDetail.acceptance', 'Acceptance')}</p>
              <p className="mt-2 text-sm text-zinc-800 dark:text-zinc-200">
                {task.acceptanceCriteria || t('projectExecution.taskDetail.noAcceptance', 'No explicit acceptance criteria recorded yet.')}
              </p>
            </div>
            <div className="rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50">
              <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">{t('projectExecution.taskDetail.latestResult', 'Latest result')}</p>
              <p className="mt-2 text-sm text-zinc-800 dark:text-zinc-200">
                {task.latestResult || t('projectExecution.taskDetail.noResult', 'No result has been recorded yet.')}
              </p>
            </div>
          </div>
        </SectionCard>

        <SectionCard title={t('projectExecution.taskDetail.metadataTitle', 'Metadata')} description={t('projectExecution.taskDetail.metadataDescription', 'Derived metadata and review signal.')}>
          <div className="grid gap-3 md:grid-cols-2">
            {task.metadata.map((item) => (
              <div
                key={`${item.label}:${item.value}`}
                className="rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50"
              >
                <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">{item.label}</p>
                <p className="mt-2 text-sm text-zinc-800 dark:text-zinc-200">{item.value}</p>
              </div>
            ))}
          </div>
        </SectionCard>

        <SectionCard title={t('projectExecution.taskDetail.timelineTitle', 'Task timeline')} description={t('projectExecution.taskDetail.timelineDescription', 'Execution and review signals for this task.')}>
          <div className="space-y-3">
            {task.events.map((event) => (
              <div
                key={event.id}
                className="rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50"
              >
                <div className="flex items-center justify-between gap-4">
                  <p className="font-medium text-zinc-950 dark:text-zinc-50">{event.title}</p>
                  <span className="text-xs text-zinc-500 dark:text-zinc-400">
                    {formatDateTime(event.timestamp)}
                  </span>
                </div>
                <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{event.description}</p>
              </div>
            ))}
          </div>
        </SectionCard>
      </div>

      <LaunchRunModal
        isOpen={isLaunchModalOpen}
        isSubmitting={isLaunching}
        taskTitle={task.title}
        taskDescription={task.description}
        onClose={() => setIsLaunchModalOpen(false)}
        onSubmit={handleLaunchRun}
      />
    </>
  );
};
