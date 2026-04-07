import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';

import { agentsApi } from '@/api/agents';
import { projectExecutionApi } from '@/api/projectExecution';
import { ProjectTaskCreateModal } from '@/components/platform/ProjectExecutionFormModal';
import {
  EmptyState,
  LoadingState,
  MetricCard,
  NoticeBanner,
  SectionCard,
  StatusBadge,
} from '@/components/platform/PlatformUi';
import { useProjectExecutionStore } from '@/stores/projectExecutionStore';
import { getAgentTypeToken } from '@/utils/agentPresentation';
import {
  formatDateTime,
  formatDuration,
  formatRunLabel,
  formatTokenLabel,
} from '@/utils/platformFormatting';

export const ProjectDetail = () => {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [isTaskModalOpen, setIsTaskModalOpen] = useState(false);
  const [isCreatingTask, setIsCreatingTask] = useState(false);
  const [isDeletingProject, setIsDeletingProject] = useState(false);
  const [availableAgents, setAvailableAgents] = useState<Array<{ id: string; name: string; type: string }>>([]);
  const [selectedAgentId, setSelectedAgentId] = useState('');
  const [selectedRuntimeType, setSelectedRuntimeType] = useState('');
  const [isBindingAgent, setIsBindingAgent] = useState(false);
  const [bindingError, setBindingError] = useState<string | null>(null);
  const [projectCommandTemplate, setProjectCommandTemplate] = useState('');
  const [isSavingProjectCommand, setIsSavingProjectCommand] = useState(false);
  const [showAllRuns, setShowAllRuns] = useState(false);
  const { projectId } = useParams<{ projectId: string }>();
  const project = useProjectExecutionStore((state) =>
    projectId ? state.projectDetails[projectId] : undefined,
  );
  const isLoading = useProjectExecutionStore((state) => state.loading.projectDetail);
  const error = useProjectExecutionStore((state) => state.errors.projectDetail);
  const fallbackSections = useProjectExecutionStore((state) => state.fallbackSections);
  const loadProjectDetail = useProjectExecutionStore((state) => state.loadProjectDetail);
  const createProjectTask = useProjectExecutionStore((state) => state.createProjectTask);
  const createProjectTaskAndLaunchRun = useProjectExecutionStore((state) => state.createProjectTaskAndLaunchRun);
  const deleteProject = useProjectExecutionStore((state) => state.deleteProject);

  useEffect(() => {
    if (projectId) {
      void loadProjectDetail(projectId);
      void agentsApi.getAll()
        .then((items) => {
          setAvailableAgents(
            items.map((agent) => ({ id: agent.id, name: agent.name, type: agent.type }))
          );
        })
        .catch((error) => {
          console.warn('Failed to load agents for binding', error);
        });
    }
  }, [loadProjectDetail, projectId]);

  const isFallback = fallbackSections.includes('projectDetail');
  const assignedCapabilityCount =
    project?.tasks.filter((task) => task.assignedAgentId || task.assignedAgentName).length || 0;

  useEffect(() => {
    if (project) {
      const configuration = project.configuration || {};
      setProjectCommandTemplate(String(configuration.external_agent_command_template || ''));
    }
  }, [project]);

  const unboundAgents = useMemo(() => {
    const bound = new Set((project?.agentBindings || []).map((item) => item.agentId));
    return availableAgents.filter((agent) => !bound.has(agent.id));
  }, [availableAgents, project?.agentBindings]);
  const visibleRuns = useMemo(
    () => (showAllRuns ? project?.runs || [] : (project?.runs || []).slice(0, 5)),
    [project?.runs, showAllRuns],
  );

  const handleBindAgent = async () => {
    if (!projectId || !selectedAgentId || isFallback) return;
    try {
      setIsBindingAgent(true);
      setBindingError(null);
      await projectExecutionApi.createProjectAgentBinding(projectId, {
        agentId: selectedAgentId,
        preferredRuntimeTypes: selectedRuntimeType ? [selectedRuntimeType] : [],
      });
      await loadProjectDetail(projectId);
      setSelectedAgentId('');
      setSelectedRuntimeType('');
      toast.success(t('projectExecution.projectDetail.bindAgentSuccess', 'Agent added to project pool'));
    } catch (bindError) {
      const message = bindError instanceof Error ? bindError.message : t('projectExecution.projectDetail.bindAgentFailed', 'Failed to add agent to project pool');
      setBindingError(message);
      toast.error(message);
    } finally {
      setIsBindingAgent(false);
    }
  };

  const handleRemoveBinding = async (bindingId: string) => {
    if (!projectId || isFallback) return;
    if (!window.confirm(t('projectExecution.projectDetail.removeBindingConfirm', 'Remove this agent from the project pool?'))) {
      return;
    }
    try {
      setBindingError(null);
      await projectExecutionApi.deleteProjectAgentBinding(projectId, bindingId);
      await loadProjectDetail(projectId);
      toast.success(t('projectExecution.projectDetail.removeBindingSuccess', 'Agent removed from project pool'));
    } catch (removeError) {
      const message = removeError instanceof Error ? removeError.message : t('projectExecution.projectDetail.removeBindingFailed', 'Failed to remove agent from project pool');
      setBindingError(message);
      toast.error(message);
    }
  };

  const handleSaveProjectCommand = async () => {
    if (!projectId || isFallback) return;
    try {
      setIsSavingProjectCommand(true);
      await projectExecutionApi.updateProject(projectId, {
        configuration: {
          ...(project?.configuration || {}),
          external_agent_command_template: projectCommandTemplate,
        },
      });
      await loadProjectDetail(projectId);
      toast.success(t('projectExecution.projectDetail.projectCommandSaved', 'Project external runner override saved'));
    } catch (saveError) {
      const message = saveError instanceof Error
        ? saveError.message
        : t('projectExecution.projectDetail.projectCommandSaveFailed', 'Failed to save project external runner override');
      toast.error(message);
    } finally {
      setIsSavingProjectCommand(false);
    }
  };

  const handleDeleteProject = async () => {
    if (!projectId || isFallback) return;

    if (!window.confirm(t('projectExecution.projectDetail.deleteConfirm', 'Delete this project and all related tasks/runs?'))) {
      return;
    }

    try {
      setIsDeletingProject(true);
      await deleteProject(projectId);
      toast.success(t('projectExecution.projectDetail.deleteSuccess', 'Project deleted'));
      navigate('/projects');
    } catch (deleteError) {
      const message = deleteError instanceof Error
        ? deleteError.message
        : t('projectExecution.projectDetail.deleteFailed', 'Failed to delete project');
      toast.error(message);
    } finally {
      setIsDeletingProject(false);
    }
  };

  const handleCreateTask = async (payload: { title: string; description?: string; autoStart?: boolean }) => {
    if (!projectId) return;

    const shouldAutoStart = payload.autoStart ?? true;

    try {
      setIsCreatingTask(true);

      if (!shouldAutoStart) {
        const taskId = await createProjectTask({
          projectId,
          title: payload.title,
          description: payload.description,
        });
        toast.success(t('projectExecution.modals.taskCreated', 'Task created'));
        setIsTaskModalOpen(false);
        navigate(`/projects/${projectId}/tasks/${taskId}`);
        return;
      }

      try {
        const { runId } = await createProjectTaskAndLaunchRun({
          projectId,
          title: payload.title,
          description: payload.description,
        });
        toast.success(t('projectExecution.modals.autoStartedTask', 'Task created and run started'));
        setIsTaskModalOpen(false);
        navigate(`/runs/${runId}`);
      } catch (launchError) {
        const message = launchError instanceof Error
          ? launchError.message
          : t('projectExecution.modals.autoStartFailed', 'Task created, but automatic run start failed');
        toast.error(message);
      }
    } catch (creationError) {
      const message = creationError instanceof Error
        ? creationError.message
        : t('projectExecution.modals.taskCreateFailed', 'Failed to create task');
      toast.error(message);
    } finally {
      setIsCreatingTask(false);
    }
  };

  if (!projectId) {
    return <EmptyState title={t('projectExecution.projectDetail.notFoundTitle', 'Project not found')} description={t('projectExecution.projectDetail.notFoundDescription', 'Missing project identifier.')} />;
  }

  if (isLoading && !project) {
    return <LoadingState label={t('projectExecution.projectDetail.loading', 'Loading project detail…')} />;
  }

  if (!project) {
    return (
      <EmptyState
        title={t('projectExecution.projects.title', 'Projects')}
        description={error || t('projectExecution.taskDetail.taskUnavailableDescription', 'Task detail could not be loaded.')}
      />
    );
  }

  return (
    <>
      <div className="space-y-6">
        {isFallback ? (
          <NoticeBanner
            title={t('projectExecution.projectDetail.fallbackTitle', 'Fallback project detail')}
            description={t('projectExecution.projectDetail.fallbackDescription', 'This detail view is in fallback mode. Creation actions are disabled until live project APIs are available for this project.')}
          />
        ) : null}

        {error ? <NoticeBanner title={t('projectExecution.projectDetail.errorTitle', 'Project detail warning')} description={error} /> : null}

        <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl space-y-3">
            <p className="text-sm font-semibold uppercase tracking-[0.22em] text-indigo-500">{t('projectExecution.shared.project', 'Project')}</p>
            <div>
              <h1 className="text-3xl font-semibold text-zinc-950 dark:text-zinc-50">
                {project.title}
              </h1>
              <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{project.instructions}</p>
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => setIsTaskModalOpen(true)}
              disabled={isFallback || isDeletingProject}
              className="rounded-full bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >{t('projectExecution.shared.addTask', 'Add Task')}
            </button>
            <button
              type="button"
              onClick={handleDeleteProject}
              disabled={isFallback || isDeletingProject}
              className="rounded-full border border-rose-300 px-4 py-2 text-sm font-medium text-rose-700 transition hover:bg-rose-50 dark:border-rose-800 dark:text-rose-300 dark:hover:bg-rose-950/40 disabled:cursor-not-allowed disabled:opacity-50"
            >{isDeletingProject ? t('projectExecution.shared.deleting', 'Deleting…') : t('projectExecution.shared.deleteProject', 'Delete Project')}
            </button>
            <a
              href="#project-runs"
              className="rounded-full border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition hover:border-zinc-400 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:border-zinc-600 dark:hover:bg-zinc-900"
            >{t('projectExecution.projectDetail.viewProjectRunsAction', 'View Project Runs')}
            </a>
            <StatusBadge status={project.status} />
          </div>
        </section>

        <div className="grid gap-4 md:grid-cols-4">
          <MetricCard label={t('projectExecution.projectDetail.metricTasks', 'Tasks')} value={String(project.totalTasks)} helper={t('projectExecution.projectDetail.metricTasksHelper', 'Items in project')} />
          <MetricCard label={t('projectExecution.projectDetail.metricCompleted', 'Completed')} value={String(project.completedTasks)} helper={t('projectExecution.projectDetail.metricCompletedHelper', 'Closed items')} />
          <MetricCard label={t('projectExecution.projectDetail.metricFailed', 'Failed')} value={String(project.failedTasks)} helper={t('projectExecution.projectDetail.metricFailedHelper', 'Needs recovery')} />
          <MetricCard label={t('projectExecution.projectDetail.metricNodes', 'Nodes')} value={String(project.activeNodeCount ?? 0)} helper={t('projectExecution.projectDetail.metricNodesHelper', 'Assigned executors')} />
        </div>

        <SectionCard title={t('projectExecution.projectDetail.taskBacklogTitle', 'Task backlog')} description={t('projectExecution.projectDetail.taskBacklogDescription', 'Project-scoped work items and their latest execution state.')}>
          {project.tasks.length === 0 ? (
            <EmptyState
              title={t('projectExecution.projectDetail.emptyTasksTitle', 'No tasks yet')}
              description={isFallback ? t('projectExecution.projectDetail.emptyTasksFallbackDescription', 'This fallback project is read-only.') : t('projectExecution.projectDetail.emptyTasksDescription', 'Create the first task for this project.')}
              action={
                !isFallback ? (
                  <button
                    type="button"
                    onClick={() => setIsTaskModalOpen(true)}
                    className="rounded-full bg-zinc-950 px-4 py-2 text-sm font-medium text-white dark:bg-zinc-50 dark:text-zinc-950"
                  >
                    {t('projectExecution.shared.createTask', 'Create Task')}
                  </button>
                ) : undefined
              }
            />
          ) : (
            <div className="space-y-3">
              {project.tasks.map((task) => (
                <Link
                  key={task.id}
                  to={`/projects/${projectId}/tasks/${task.id}`}
                  className="flex flex-col gap-3 rounded-2xl border border-zinc-200/70 bg-white/70 p-4 transition hover:border-sky-400/40 hover:bg-white/90 dark:border-zinc-800 dark:bg-zinc-950/50"
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h2 className="font-semibold text-zinc-950 dark:text-zinc-50">{task.title}</h2>
                      <p className="text-sm text-zinc-600 dark:text-zinc-400">
                        {t('projectExecution.projectDetail.priorityUpdated', { priority: task.priority, value: formatDateTime(task.updatedAt), defaultValue: `Priority ${task.priority} · Updated ${formatDateTime(task.updatedAt)}` })}
                      </p>
                    </div>
                    <StatusBadge status={task.status} />
                  </div>
                  <div className="flex flex-wrap gap-4 text-sm text-zinc-600 dark:text-zinc-400">
                    <span>{t('projectExecution.projectDetail.dependencies', { count: task.dependencyIds.length, defaultValue: `Dependencies: ${task.dependencyIds.length}` })}</span>
                    <span>{t('projectExecution.projectDetail.owner', { value: task.assignedAgentName || 'Unassigned', defaultValue: `Owner: ${task.assignedAgentName || 'Unassigned'}` })}</span>
                    {task.reviewStatus ? <span>{t('projectExecution.projectDetail.review', { value: task.reviewStatus, defaultValue: `Review: ${task.reviewStatus}` })}</span> : null}
                  </div>
                </Link>
              ))}
            </div>
          )}
        </SectionCard>

        <div id="project-runs">
          <SectionCard
            title={t('projectExecution.projectDetail.projectRunsTitle', 'Project runs')}
            description={t('projectExecution.projectDetail.projectRunsDescription', 'Recent runs for this project. Open a run for execution detail and troubleshooting.')}
            action={
              project.runs.length > 5 ? (
                <button
                  type="button"
                  onClick={() => setShowAllRuns((current) => !current)}
                  className="rounded-full border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition hover:border-zinc-400 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:border-zinc-600 dark:hover:bg-zinc-900"
                >
                  {showAllRuns
                    ? t('projectExecution.projectDetail.showRecentRunsAction', 'Show Recent')
                    : t('projectExecution.projectDetail.showAllRunsAction', 'Show All')}
                </button>
              ) : null
            }
          >
            {project.runs.length === 0 ? (
              <EmptyState
                title={t('projectExecution.projectDetail.emptyRunsTitle', 'No runs yet')}
                description={t('projectExecution.projectDetail.emptyRunsDescription', 'Runs created from this project will appear here.')}
              />
            ) : (
              <div className="space-y-3">
                {visibleRuns.map((run) => (
                  <div
                    key={run.id}
                    className="rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50"
                  >
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                      <div>
                        <div className="flex flex-wrap items-center gap-3">
                          <h3 className="font-semibold text-zinc-950 dark:text-zinc-50">
                            {formatRunLabel(run.id)}
                          </h3>
                          <StatusBadge status={run.status} />
                        </div>
                        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                          {t('projectExecution.projectDetail.runCreatedPrefix', {
                            value: formatDateTime(run.createdAt),
                            defaultValue: `Created ${formatDateTime(run.createdAt)}`,
                          })}
                        </p>
                      </div>

                      <Link
                        to={`/runs/${run.id}`}
                        className="rounded-full bg-zinc-950 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-800 dark:bg-zinc-50 dark:text-zinc-950 dark:hover:bg-zinc-200"
                      >
                        {t('projectExecution.shared.openRun', 'Open Run')}
                      </Link>
                    </div>

                    <div className="mt-4 grid gap-3 rounded-[20px] border border-zinc-200/70 bg-zinc-50/70 p-4 sm:grid-cols-4 dark:border-zinc-800 dark:bg-zinc-900/60">
                      <div>
                        <p className="text-xs uppercase tracking-[0.14em] text-zinc-500 dark:text-zinc-400">
                          {t('projectExecution.runCenter.startedAt', 'Started')}
                        </p>
                        <p className="mt-2 text-sm font-semibold text-zinc-950 dark:text-zinc-50">
                          {formatDateTime(run.startedAt)}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs uppercase tracking-[0.14em] text-zinc-500 dark:text-zinc-400">
                          {t('projectExecution.runCenter.duration', 'Duration')}
                        </p>
                        <p className="mt-2 text-sm font-semibold text-zinc-950 dark:text-zinc-50">
                          {formatDuration(run.startedAt, run.completedAt)}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs uppercase tracking-[0.14em] text-zinc-500 dark:text-zinc-400">
                          {t('projectExecution.runCenter.failed', 'Failed')}
                        </p>
                        <p className="mt-2 text-sm font-semibold text-zinc-950 dark:text-zinc-50">
                          {run.failedTasks}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs uppercase tracking-[0.14em] text-zinc-500 dark:text-zinc-400">
                          {t('projectExecution.runCenter.triggerSource', 'Trigger')}
                        </p>
                        <p className="mt-2 text-sm font-semibold text-zinc-950 dark:text-zinc-50">
                          {formatTokenLabel(run.triggerSource)}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </SectionCard>
        </div>

        <SectionCard
          title={t('projectExecution.projectDetail.externalRunnerOverrideTitle', 'Project external runner override')}
          description={t('projectExecution.projectDetail.externalRunnerOverrideDescription', 'Override the platform default external agent command template for this project.')}
        >
          <div className="space-y-4 rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50">
            <textarea
              value={projectCommandTemplate}
              onChange={(event) => setProjectCommandTemplate(event.target.value)}
              rows={4}
              disabled={isFallback}
              className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
              placeholder={t('projectExecution.projectDetail.externalRunnerOverridePlaceholder', 'Leave empty to inherit the platform default external runner command')}
            />
            <button
              type="button"
              onClick={() => void handleSaveProjectCommand()}
              disabled={isFallback || isSavingProjectCommand}
              className="rounded-full bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isSavingProjectCommand ? t('projectExecution.shared.saving', 'Saving…') : t('projectExecution.projectDetail.saveProjectCommandAction', 'Save project override')}
            </button>
          </div>
        </SectionCard>

        <SectionCard
          title={t('projectExecution.projectDetail.projectAgentPoolTitle', 'Project Agent Pool')}
          description={t('projectExecution.projectDetail.projectAgentPoolDescription', 'Agents in this pool are preferred for automatic assignment. If none match, LinX provisions a temporary run-scoped agent.')}
        >
          <div className="space-y-4">
            <div className="flex flex-col gap-3 rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50 lg:flex-row lg:items-center">
              <select
                value={selectedAgentId}
                onChange={(event) => setSelectedAgentId(event.target.value)}
                disabled={isFallback || isBindingAgent || unboundAgents.length === 0}
                className="min-w-0 flex-1 rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
              >
                <option value="">{t('projectExecution.projectDetail.selectAgentPlaceholder', 'Select an agent to bind')}</option>
                {unboundAgents.map((agent) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.name} · {agent.type}
                  </option>
                ))}
              </select>
              <select
                value={selectedRuntimeType}
                onChange={(event) => setSelectedRuntimeType(event.target.value)}
                disabled={isFallback || isBindingAgent || !selectedAgentId}
                className="min-w-0 rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100 lg:w-56"
              >
                <option value="">{t('projectExecution.projectDetail.selectRuntimePlaceholder', 'Any runtime')}</option>
                <option value="project_sandbox">project_sandbox</option>
                <option value="external_worktree">external_worktree</option>
                <option value="external_same_dir">external_same_dir</option>
                <option value="remote_session">remote_session</option>
              </select>
              <button
                type="button"
                onClick={handleBindAgent}
                disabled={isFallback || isBindingAgent || !selectedAgentId}
                className="rounded-full bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isBindingAgent ? t('projectExecution.shared.saving', 'Saving…') : t('projectExecution.projectDetail.bindAgentAction', 'Add to project pool')}
              </button>
            </div>
            {bindingError ? <NoticeBanner title={t('projectExecution.projectDetail.projectAgentPoolError', 'Project agent pool issue')} description={bindingError} /> : null}
            {project.agentBindings && project.agentBindings.length > 0 ? (
              <div className="space-y-3">
                {project.agentBindings.map((binding) => (
                  <div key={binding.id} className="flex flex-col gap-3 rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <p className="font-medium text-zinc-950 dark:text-zinc-50">{binding.agentName}</p>
                      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                        {binding.agentType ? t(`agent.typeLabel.${getAgentTypeToken({ type: binding.agentType, runtimeType: binding.preferredRuntimeTypes[0] || 'project_sandbox' } as any)}`, { defaultValue: binding.agentType }) : t('projectExecution.projectDetail.agentTypeUnknown', 'Unknown type')} · {binding.roleHint || t('projectExecution.projectDetail.agentPoolPriority', { value: binding.priority, defaultValue: `Priority ${binding.priority}` })}
                      </p>
                      <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                        {binding.allowedStepKinds.length > 0
                          ? t('projectExecution.projectDetail.allowedStepKinds', { value: binding.allowedStepKinds.join(', '), defaultValue: `Allowed step kinds: ${binding.allowedStepKinds.join(', ')}` })
                          : t('projectExecution.projectDetail.allStepKinds', 'All step kinds')}
                      </p>
                      <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                        {binding.preferredRuntimeTypes.length > 0
                          ? t('projectExecution.projectDetail.preferredRuntimeTypes', { value: binding.preferredRuntimeTypes.join(', '), defaultValue: `Preferred runtimes: ${binding.preferredRuntimeTypes.join(', ')}` })
                          : t('projectExecution.projectDetail.anyRuntimeTypes', 'Any runtime')}
                      </p>
                    </div>
                    <div className="flex items-center gap-3">
                      <StatusBadge status={binding.status} />
                      <button
                        type="button"
                        onClick={() => void handleRemoveBinding(binding.id)}
                        disabled={isFallback}
                        className="rounded-full border border-rose-300 px-4 py-2 text-sm font-medium text-rose-700 transition hover:bg-rose-50 dark:border-rose-800 dark:text-rose-300 dark:hover:bg-rose-950/40 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {t('projectExecution.projectDetail.removeBindingAction', 'Remove')}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                title={t('projectExecution.projectDetail.emptyAgentPoolTitle', 'No project-bound agents')}
                description={t('projectExecution.projectDetail.emptyAgentPoolDescription', 'Bind agents here to make them the first choice for automatic task assignment.')}
              />
            )}
          </div>
        </SectionCard>

        <SectionCard
          title={t('projectExecution.projectDetail.provisioningProfilesTitle', 'Provisioning Profiles')}
          description={t('projectExecution.projectDetail.provisioningProfilesDescription', 'When no project-bound agent matches, LinX provisions a temporary agent using these defaults.')}
        >
          {project.provisioningProfiles && project.provisioningProfiles.length > 0 ? (
            <div className="grid gap-3 lg:grid-cols-2">
              {project.provisioningProfiles.map((profile) => (
                <div key={profile.id} className="rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50">
                  <div className="flex items-center justify-between gap-3">
                    <p className="font-medium text-zinc-950 dark:text-zinc-50">{profile.stepKind}</p>
                    <StatusBadge status={profile.ephemeral ? 'idle' : 'draft'} />
                  </div>
                  <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                    {t('projectExecution.projectDetail.provisioningProfileSummary', { agentType: profile.agentType, sandboxMode: profile.sandboxMode, defaultValue: `${profile.agentType} · ${profile.sandboxMode}` })}
                  </p>
                  <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                    {profile.defaultProvider || 'auto'} / {profile.defaultModel || 'default'}
                  </p>
                  <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                    {t('projectExecution.projectDetail.provisioningProfileRuntime', { runtime: profile.runtimeType, selector: profile.preferredNodeSelector || 'auto', defaultValue: `${profile.runtimeType} · node ${profile.preferredNodeSelector || 'auto'}` })}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              title={t('projectExecution.projectDetail.emptyProvisioningProfilesTitle', 'No explicit provisioning profiles')}
              description={t('projectExecution.projectDetail.emptyProvisioningProfilesDescription', 'Default temporary-agent heuristics are currently in use for this project.')}
            />
          )}
        </SectionCard>

        <SectionCard
          title={t('projectExecution.projectDetail.capabilitiesTitle', 'Capabilities & Integrations')}
          description={t('projectExecution.projectDetail.capabilitiesDescription', 'Project pages show only capability summaries. Manage skills and extensions centrally in the Skills Library.')}
        >
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-zinc-200/70 bg-white/70 p-5 dark:border-zinc-800 dark:bg-zinc-950/50">
              <p className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">{t('projectExecution.projectDetail.capabilitySummaryTitle', 'Capability Summary')}</p>
              <p className="mt-3 text-3xl font-semibold text-zinc-950 dark:text-zinc-50">
                {assignedCapabilityCount}
              </p>
              <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                {t('projectExecution.projectDetail.capabilitySummaryDescription', 'Tasks currently routed through explicit executors or capability-bearing agents.')}
              </p>
              <div className="mt-4">
                <Link
                  to="/skills/library?section=library"
                  className="inline-flex rounded-full border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition hover:border-zinc-400 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:border-zinc-600 dark:hover:bg-zinc-900"
                >
                  {t('projectExecution.projectDetail.openSkillsLibrary', 'Open Skills Library')}
                </Link>
              </div>
            </div>

            <div className="rounded-2xl border border-zinc-200/70 bg-white/70 p-5 dark:border-zinc-800 dark:bg-zinc-950/50">
              <p className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">{t('projectExecution.projectDetail.extensionsSummaryTitle', 'Extensions Summary')}</p>
              <p className="mt-3 text-3xl font-semibold text-zinc-950 dark:text-zinc-50">
                {project.activeNodeCount ?? 0}
              </p>
              <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                {t('projectExecution.projectDetail.extensionsSummaryDescription', 'Active executors that may rely on MCP servers or extension-backed tools.')}
              </p>
              <div className="mt-4">
                <Link
                  to="/skills/library?section=mcp_servers"
                  className="inline-flex rounded-full border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition hover:border-zinc-400 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:border-zinc-600 dark:hover:bg-zinc-900"
                >
                  {t('projectExecution.projectDetail.openMcpExtensions', 'Open MCP & Extensions')}
                </Link>
              </div>
            </div>
          </div>
        </SectionCard>

        <SectionCard title={t('projectExecution.projectDetail.recentActivityTitle', 'Recent activity')} description={t('projectExecution.projectDetail.recentActivityDescription', 'Latest project-level execution signals.')}>
          <div className="space-y-3">
            {project.recentActivity.map((activity) => (
              <div
                key={activity.id}
                className="rounded-2xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/50"
              >
                <div className="flex items-center justify-between gap-4">
                  <p className="font-medium text-zinc-950 dark:text-zinc-50">{activity.title}</p>
                  <span className="text-xs text-zinc-500 dark:text-zinc-400">
                    {formatDateTime(activity.timestamp)}
                  </span>
                </div>
                <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{activity.description}</p>
              </div>
            ))}
          </div>
        </SectionCard>
      </div>

      <ProjectTaskCreateModal
        isOpen={isTaskModalOpen}
        projectTitle={project.title}
        isSubmitting={isCreatingTask}
        onClose={() => setIsTaskModalOpen(false)}
        onSubmit={handleCreateTask}
      />
    </>
  );
};
