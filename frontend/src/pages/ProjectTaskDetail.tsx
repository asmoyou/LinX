import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
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
import { formatDateTime, formatTokenLabel } from '@/utils/platformFormatting';

export const ProjectTaskDetail = () => {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [isLaunchModalOpen, setIsLaunchModalOpen] = useState(false);
  const [isLaunching, setIsLaunching] = useState(false);
  const [isDeletingTask, setIsDeletingTask] = useState(false);
  const [activeTab, setActiveTab] = useState<
    'overview' | 'contract' | 'dependencies' | 'delivery' | 'execution'
  >('overview');
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

  const handleLaunchRun = async (
    executionMode: 'auto' | 'project_sandbox' | 'external_runtime' = 'auto',
  ) => {
    if (!projectId || !taskId || !task) return;

    try {
      setIsLaunching(true);
      const { runId, needsClarification } = await launchTaskRun({
        projectId,
        taskId,
        title: task.title,
        description: task.description,
        executionMode,
      });
      setIsLaunchModalOpen(false);
      if (needsClarification || !runId) {
        toast.success(
          t(
            'projectExecution.modals.taskNeedsClarification',
            'Task requires clarification before execution can start',
          ),
        );
        void loadProjectTaskDetail(projectId, taskId);
        return;
      }
      toast.success(t('projectExecution.taskDetail.launchSuccess', 'Plan generated and run started'));
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

        {['failed', 'blocked', 'cancelled'].includes(String(task.status).toLowerCase()) && task.latestResult ? (
          <NoticeBanner
            title={t('projectExecution.taskDetail.failureTitle', 'Task failure reason')}
            description={task.latestResult}
          />
        ) : null}

        {task.clarificationQuestions && task.clarificationQuestions.length > 0 ? (
          <SectionCard
            title={t('projectExecution.taskDetail.clarificationTitle', 'Clarification required')}
            description={t('projectExecution.taskDetail.clarificationDescription', 'Planner needs more detail before this task can be executed.')}
          >
            <div className="space-y-3">
              {task.clarificationQuestions.map((question, index) => (
                <div
                  key={`${question.question}:${index}`}
                  className="rounded-2xl border border-amber-300/60 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300"
                >
                  <p className="font-medium">{question.question}</p>
                  {question.importance ? (
                    <p className="mt-1 text-xs uppercase tracking-[0.14em]">{question.importance}</p>
                  ) : null}
                </div>
              ))}
            </div>
          </SectionCard>
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

        <div className="flex flex-wrap gap-3">
          {([
            ['overview', t('projectExecution.taskDetail.tabOverview', 'Overview')],
            ['contract', t('projectExecution.taskDetail.tabContract', 'Contract')],
            ['dependencies', t('projectExecution.taskDetail.tabDependencies', 'Dependencies')],
            ['delivery', t('projectExecution.taskDetail.tabDelivery', 'Delivery')],
            ['execution', t('projectExecution.taskDetail.tabExecution', 'Execution')],
          ] as const).map(([value, label]) => {
            const isSelected = activeTab === value;
            return (
              <button
                key={value}
                type="button"
                onClick={() => setActiveTab(value)}
                className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                  isSelected
                    ? 'bg-zinc-950 text-white dark:bg-zinc-50 dark:text-zinc-950'
                    : 'border border-zinc-300 text-zinc-700 hover:border-zinc-400 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:border-zinc-600 dark:hover:bg-zinc-900'
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>

        {activeTab === 'overview' ? (
        <SectionCard title={t('projectExecution.taskDetail.executionContextTitle', 'Execution context')} description={t('projectExecution.taskDetail.executionContextDescription', 'Task-level runtime and assignment metadata.')}>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
            <div className="rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50">
              <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                {t('projectExecution.taskDetail.nextAction', 'Next Action')}
              </p>
              <p className="mt-2 text-sm text-zinc-800 dark:text-zinc-200">
                {task.nextAction || t('projectExecution.taskDetail.nextActionFallback', 'Review task state')}
              </p>
              {task.blockerReason ? (
                <p className="mt-3 text-xs text-amber-700 dark:text-amber-300">{task.blockerReason}</p>
              ) : null}
            </div>
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
              <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                {t('projectExecution.taskDetail.executionModeLabel', 'Execution Mode')}
              </p>
              <p className="mt-2 text-sm text-zinc-800 dark:text-zinc-200">
                {task.executionMode
                  ? t(`projectExecution.modals.executionMode.${task.executionMode}`, {
                      defaultValue: formatTokenLabel(task.executionMode),
                    })
                  : t('projectExecution.taskDetail.executionModeUnknown', 'Auto')}
              </p>
              {task.plannerSource ? (
                <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
                  {t('projectExecution.taskDetail.plannerSourcePrefix', {
                    value: formatTokenLabel(task.plannerSource),
                    defaultValue: `Planner ${formatTokenLabel(task.plannerSource)}`,
                  })}
                </p>
              ) : null}
            </div>
            <div className="rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50">
              <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                {t('projectExecution.taskDetail.stepCountLabel', 'Steps')}
              </p>
              <p className="mt-2 text-sm text-zinc-800 dark:text-zinc-200">
                {`${task.completedStepCount || 0}/${task.stepTotal || 0}`}
              </p>
            </div>
            <div className="rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50">
              <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                {t('projectExecution.taskDetail.currentStepLabel', 'Current Step')}
              </p>
              <p className="mt-2 text-sm text-zinc-800 dark:text-zinc-200">
                {task.currentStepTitle || t('projectExecution.taskDetail.currentStepUnknown', 'No active step')}
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
        ) : null}

        {activeTab === 'overview' ? (
        <SectionCard title={t('projectExecution.taskDetail.metadataTitle', 'Metadata')} description={t('projectExecution.taskDetail.metadataDescription', 'Derived metadata and review signal.')}>
          <div className="grid gap-3 md:grid-cols-2">
            {task.plannerSummary ? (
              <div className="rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50 md:col-span-2">
                <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                  {t('projectExecution.taskDetail.plannerSummaryLabel', 'Planner Summary')}
                </p>
                <p className="mt-2 text-sm text-zinc-800 dark:text-zinc-200">{task.plannerSummary}</p>
              </div>
            ) : null}
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
        ) : null}

        {activeTab === 'contract' && task.contract ? (
          <SectionCard
            title={t('projectExecution.taskDetail.contractTitle', 'Task Contract')}
            description={t('projectExecution.taskDetail.contractDescription', 'Structured delivery and acceptance contract for this task.')}
          >
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50">
                <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                  {t('projectExecution.taskDetail.contractGoal', 'Goal')}
                </p>
                <p className="mt-2 text-sm text-zinc-800 dark:text-zinc-200">
                  {task.contract.goal || task.title}
                </p>
                {task.contract.scope.length > 0 ? (
                  <>
                    <p className="mt-4 text-sm font-medium text-zinc-500 dark:text-zinc-400">
                      {t('projectExecution.taskDetail.contractScope', 'Scope')}
                    </p>
                    <div className="mt-2 space-y-2">
                      {task.contract.scope.map((item) => (
                        <p key={item} className="text-sm text-zinc-700 dark:text-zinc-300">{`• ${item}`}</p>
                      ))}
                    </div>
                  </>
                ) : null}
                {task.contract.constraints.length > 0 ? (
                  <>
                    <p className="mt-4 text-sm font-medium text-zinc-500 dark:text-zinc-400">
                      {t('projectExecution.taskDetail.contractConstraints', 'Constraints')}
                    </p>
                    <div className="mt-2 space-y-2">
                      {task.contract.constraints.map((item) => (
                        <p key={item} className="text-sm text-zinc-700 dark:text-zinc-300">{`• ${item}`}</p>
                      ))}
                    </div>
                  </>
                ) : null}
              </div>

              <div className="space-y-4">
                <div className="rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50">
                  <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                    {t('projectExecution.taskDetail.contractDeliverables', 'Deliverables')}
                  </p>
                  <div className="mt-2 space-y-2">
                    {task.contract.deliverables.length > 0 ? task.contract.deliverables.map((item) => (
                      <p key={item} className="text-sm text-zinc-700 dark:text-zinc-300">{`• ${item}`}</p>
                    )) : (
                      <p className="text-sm text-zinc-600 dark:text-zinc-400">
                        {t('projectExecution.taskDetail.contractDeliverablesEmpty', 'No deliverables defined yet.')}
                      </p>
                    )}
                  </div>
                </div>

                <div className="rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50">
                  <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                    {t('projectExecution.taskDetail.contractAcceptance', 'Acceptance Criteria')}
                  </p>
                  <div className="mt-2 space-y-2">
                    {task.contract.acceptanceCriteria.length > 0 ? task.contract.acceptanceCriteria.map((item) => (
                      <p key={item} className="text-sm text-zinc-700 dark:text-zinc-300">{`• ${item}`}</p>
                    )) : (
                      <p className="text-sm text-zinc-600 dark:text-zinc-400">
                        {t('projectExecution.taskDetail.contractAcceptanceEmpty', 'No structured acceptance criteria defined yet.')}
                      </p>
                    )}
                  </div>
                </div>

                {(task.contract.evidenceRequired.length > 0 || task.contract.assumptions.length > 0) ? (
                  <div className="rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50">
                    {task.contract.evidenceRequired.length > 0 ? (
                      <>
                        <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                          {t('projectExecution.taskDetail.contractEvidence', 'Evidence Required')}
                        </p>
                        <div className="mt-2 space-y-2">
                          {task.contract.evidenceRequired.map((item) => (
                            <p key={item} className="text-sm text-zinc-700 dark:text-zinc-300">{`• ${item}`}</p>
                          ))}
                        </div>
                      </>
                    ) : null}
                    {task.contract.assumptions.length > 0 ? (
                      <>
                        <p className="mt-4 text-sm font-medium text-zinc-500 dark:text-zinc-400">
                          {t('projectExecution.taskDetail.contractAssumptions', 'Assumptions')}
                        </p>
                        <div className="mt-2 space-y-2">
                          {task.contract.assumptions.map((item) => (
                            <p key={item} className="text-sm text-zinc-700 dark:text-zinc-300">{`• ${item}`}</p>
                          ))}
                        </div>
                      </>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </div>
          </SectionCard>
        ) : null}

        {activeTab === 'dependencies' && ((task.dependencies && task.dependencies.length > 0) || task.blockingDependencyCount) ? (
          <SectionCard
            title={t('projectExecution.taskDetail.dependenciesTitle', 'Dependencies')}
            description={t('projectExecution.taskDetail.dependenciesDescription', 'Readiness and upstream dependency state for this task.')}
          >
            <div className="mb-4 grid gap-4 md:grid-cols-2">
              <div className="rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50">
                <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                  {t('projectExecution.taskDetail.readyState', 'Ready State')}
                </p>
                <p className="mt-2 text-sm text-zinc-800 dark:text-zinc-200">
                  {task.ready === false
                    ? t('projectExecution.taskDetail.notReady', 'Blocked by upstream dependencies')
                    : t('projectExecution.taskDetail.ready', 'Ready')}
                </p>
              </div>
              <div className="rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50">
                <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                  {t('projectExecution.taskDetail.blockingDependencies', 'Blocking Dependencies')}
                </p>
                <p className="mt-2 text-sm text-zinc-800 dark:text-zinc-200">
                  {task.blockingDependencyCount || 0}
                </p>
              </div>
            </div>

            <div className="space-y-3">
              {task.dependencies?.map((dependency) => (
                <div
                  key={dependency.id}
                  className="rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50"
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="font-medium text-zinc-950 dark:text-zinc-50">
                        {dependency.dependsOnTaskTitle || dependency.dependsOnTaskId}
                      </p>
                      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                        {`Required ${formatTokenLabel(dependency.requiredState)} · ${formatTokenLabel(dependency.dependencyType)}`}
                      </p>
                    </div>
                    <span
                      className={`rounded-full px-3 py-1 text-xs font-medium ${
                        dependency.satisfied
                          ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300'
                          : 'bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300'
                      }`}
                    >
                      {dependency.satisfied
                        ? t('projectExecution.taskDetail.dependencySatisfied', 'Satisfied')
                        : t('projectExecution.taskDetail.dependencyBlocked', 'Blocking')}
                    </span>
                  </div>
                  {dependency.dependsOnTaskStatus ? (
                    <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                      {t('projectExecution.taskDetail.dependencyStatus', {
                        value: formatTokenLabel(dependency.dependsOnTaskStatus),
                        defaultValue: `Current status: ${formatTokenLabel(dependency.dependsOnTaskStatus)}`,
                      })}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          </SectionCard>
        ) : null}

        {activeTab === 'delivery' && (task.latestChangeBundle || task.latestEvidenceBundle || (task.reviewIssues && task.reviewIssues.length > 0) || (task.handoffs && task.handoffs.length > 0)) ? (
          <SectionCard
            title={t('projectExecution.taskDetail.deliveryReviewTitle', 'Delivery & Review')}
            description={t('projectExecution.taskDetail.deliveryReviewDescription', 'Structured delivery snapshots, evidence, review issues, and handoffs for this task.')}
          >
            <div className="grid gap-4 xl:grid-cols-2">
              {task.latestChangeBundle ? (
                <div className="rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50">
                  <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                    {t('projectExecution.taskDetail.latestChangeBundle', 'Latest Change Bundle')}
                  </p>
                  <p className="mt-2 text-sm text-zinc-800 dark:text-zinc-200">
                    {task.latestChangeBundle.summary || formatTokenLabel(task.latestChangeBundle.bundleKind)}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-3 text-xs text-zinc-500 dark:text-zinc-400">
                    <span>{formatTokenLabel(task.latestChangeBundle.status)}</span>
                    <span>{`Commits ${task.latestChangeBundle.commitCount}`}</span>
                    {task.latestChangeBundle.baseRef ? <span>{`Base ${task.latestChangeBundle.baseRef}`}</span> : null}
                    {task.latestChangeBundle.headRef ? <span>{`Head ${task.latestChangeBundle.headRef}`}</span> : null}
                  </div>
                  {task.latestChangeBundle.changedFiles.length > 0 ? (
                    <div className="mt-3 space-y-2">
                      {task.latestChangeBundle.changedFiles.slice(0, 5).map((item, index) => (
                        <p key={`${JSON.stringify(item)}:${index}`} className="text-sm text-zinc-700 dark:text-zinc-300">
                          {`• ${String(item.path || item.file || item.name || 'changed file')}`}
                        </p>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}

              {task.latestEvidenceBundle ? (
                <div className="rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50">
                  <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                    {t('projectExecution.taskDetail.latestEvidenceBundle', 'Latest Evidence Bundle')}
                  </p>
                  <p className="mt-2 text-sm text-zinc-800 dark:text-zinc-200">
                    {task.latestEvidenceBundle.summary}
                  </p>
                  <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
                    {formatTokenLabel(task.latestEvidenceBundle.status)}
                  </p>
                  {task.latestEvidenceBundle.bundle ? (
                    <pre className="mt-3 overflow-x-auto rounded-xl bg-zinc-950 px-3 py-3 text-xs text-zinc-100">
                      {JSON.stringify(task.latestEvidenceBundle.bundle, null, 2)}
                    </pre>
                  ) : null}
                </div>
              ) : null}
            </div>

            {(task.reviewIssues && task.reviewIssues.length > 0) ? (
              <div className="mt-6">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                    {t('projectExecution.taskDetail.reviewIssues', 'Review Issues')}
                  </p>
                  <span className="text-xs text-zinc-500 dark:text-zinc-400">
                    {t('projectExecution.taskDetail.openIssueCount', {
                      count: task.openIssueCount || 0,
                      defaultValue: `Open ${task.openIssueCount || 0}`,
                    })}
                  </span>
                </div>
                <div className="space-y-3">
                  {task.reviewIssues.map((issue) => (
                    <div
                      key={issue.id}
                      className="rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <p className="font-medium text-zinc-950 dark:text-zinc-50">{issue.summary}</p>
                        <div className="flex flex-wrap gap-2 text-xs text-zinc-500 dark:text-zinc-400">
                          <span>{formatTokenLabel(issue.severity)}</span>
                          <span>{formatTokenLabel(issue.category)}</span>
                          <span>{formatTokenLabel(issue.status)}</span>
                        </div>
                      </div>
                      {issue.suggestion ? (
                        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{issue.suggestion}</p>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {(task.handoffs && task.handoffs.length > 0) ? (
              <div className="mt-6">
                <p className="mb-3 text-sm font-medium text-zinc-500 dark:text-zinc-400">
                  {t('projectExecution.taskDetail.handoffs', 'Handoffs')}
                </p>
                <div className="space-y-3">
                  {task.handoffs.map((handoff) => (
                    <div
                      key={handoff.id}
                      className="rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <p className="font-medium text-zinc-950 dark:text-zinc-50">
                          {handoff.title || formatTokenLabel(handoff.stage)}
                        </p>
                        <span className="text-xs text-zinc-500 dark:text-zinc-400">
                          {formatDateTime(handoff.createdAt)}
                        </span>
                      </div>
                      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{handoff.summary}</p>
                      <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
                        {`${handoff.fromActor}${handoff.toActor ? ` → ${handoff.toActor}` : ''}`}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </SectionCard>
        ) : null}

        {activeTab === 'execution' && (task.attempts && task.attempts.length > 0) ? (
          <SectionCard
            title={t('projectExecution.taskDetail.executionAttemptsTitle', 'Execution Attempts')}
            description={t('projectExecution.taskDetail.executionAttemptsDescription', 'Historical and active execution attempts for this task.')}
          >
            <div className="space-y-3">
              {task.attempts.map((attempt) => (
                <Link
                  key={attempt.id}
                  to={`/runs/${attempt.id}`}
                  className="block rounded-2xl border border-zinc-200/70 bg-white/70 p-4 transition hover:border-sky-400/40 hover:bg-white/90 dark:border-zinc-800 dark:bg-zinc-950/50"
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="font-medium text-zinc-950 dark:text-zinc-50">{attempt.id}</p>
                      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                        {`${formatTokenLabel(attempt.triggerSource)} · ${attempt.completedNodes}/${attempt.totalNodes} nodes`}
                      </p>
                    </div>
                    <StatusBadge status={attempt.status} />
                  </div>
                  <div className="mt-3 flex flex-wrap gap-4 text-sm text-zinc-600 dark:text-zinc-400">
                    {attempt.executionMode ? <span>{formatTokenLabel(attempt.executionMode)}</span> : null}
                    {attempt.currentStepTitle ? <span>{attempt.currentStepTitle}</span> : null}
                    <span>{`Runtime sessions: ${attempt.activeRuntimeSessions}`}</span>
                    <span>{formatDateTime(attempt.createdAt)}</span>
                  </div>
                  {attempt.failureReason ? (
                    <p className="mt-3 text-sm text-rose-600 dark:text-rose-400">{attempt.failureReason}</p>
                  ) : null}
                </Link>
              ))}
            </div>
          </SectionCard>
        ) : null}

        {activeTab === 'execution' ? (
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
        ) : null}
      </div>

      <LaunchRunModal
        isOpen={isLaunchModalOpen}
        isSubmitting={isLaunching}
        taskTitle={task.title}
        taskDescription={task.description}
        initialExecutionMode={(task.executionMode as any) || 'auto'}
        onClose={() => setIsLaunchModalOpen(false)}
        onSubmit={handleLaunchRun}
      />
    </>
  );
};
