import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';

import { GlassPanel } from '@/components/GlassPanel';
import { ProjectCreateModal } from '@/components/platform/ProjectExecutionFormModal';
import {
  EmptyState,
  LoadingState,
  MetricCard,
  NoticeBanner,
  StatusBadge,
} from '@/components/platform/PlatformUi';
import { useProjectExecutionStore } from '@/stores/projectExecutionStore';
import { formatDateTime, formatNumber } from '@/utils/platformFormatting';

export const Projects = () => {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const projects = useProjectExecutionStore((state) => state.projects);
  const isLoading = useProjectExecutionStore((state) => state.loading.projects);
  const error = useProjectExecutionStore((state) => state.errors.projects);
  const fallbackSections = useProjectExecutionStore((state) => state.fallbackSections);
  const loadProjects = useProjectExecutionStore((state) => state.loadProjects);
  const createProject = useProjectExecutionStore((state) => state.createProject);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  const stats = useMemo(() => {
    const activeProjects = projects.filter((project) =>
      ['running', 'planning', 'reviewing'].includes(project.status.toLowerCase()),
    ).length;
    const attentionProjects = projects.filter(
      (project) => project.failedTasks > 0 || project.needsClarification,
    ).length;
    const avgProgress =
      projects.length > 0
        ? Math.round(projects.reduce((total, project) => total + project.progress, 0) / projects.length)
        : 0;

    return {
      total: projects.length,
      active: activeProjects,
      attention: attentionProjects,
      avgProgress,
    };
  }, [projects]);

  const handleCreateProject = async (payload: { name: string; description?: string }) => {
    try {
      setIsCreating(true);
      const projectId = await createProject(payload);
      toast.success(t('projectExecution.modals.projectCreated', 'Project created'));
      setIsCreateModalOpen(false);
      navigate(`/projects/${projectId}`);
    } catch (creationError) {
      const message = creationError instanceof Error ? creationError.message : t('projectExecution.modals.projectCreateFailed', 'Failed to create project');
      toast.error(message);
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <>
      <div className="space-y-6">
        <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl space-y-3">
            <p className="text-sm font-semibold uppercase tracking-[0.22em] text-indigo-500">{t('projectExecution.projects.badge', 'Project Execution')}
            </p>
            <div>
              <h1 className="text-3xl font-semibold text-zinc-950 dark:text-zinc-50">{t('projectExecution.projects.title', 'Projects')}</h1>
              <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                {t('projectExecution.projects.subtitle', 'Track delivery health, active workstreams, and the latest execution signals in one focused shell.')}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => setIsCreateModalOpen(true)}
              className="rounded-full bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500"
            >{t('projectExecution.shared.createProject', 'Create Project')}
            </button>
          </div>
        </section>

        {fallbackSections.includes('projects') ? (
          <NoticeBanner
            title={t('projectExecution.projects.fallbackTitle', 'Using fallback project data')}
            description={t('projectExecution.projects.fallbackDescription', 'The project shell prefers the new project backend and falls back to local seeded demo data only when the platform APIs are unavailable.')}
          />
        ) : null}

        {error ? <NoticeBanner title={t('projectExecution.projects.errorTitle', 'Project refresh issue')} description={error} /> : null}

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard label={t('projectExecution.projects.metricProjects', 'Projects')} value={formatNumber(stats.total)} helper={t('projectExecution.projects.metricProjectsHelper', 'Tracked workstreams')} />
          <MetricCard label={t('projectExecution.projects.metricActive', 'Active')} value={formatNumber(stats.active)} helper={t('projectExecution.projects.metricActiveHelper', 'Planning or executing now')} />
          <MetricCard label={t('projectExecution.projects.metricAttention', 'Attention')} value={formatNumber(stats.attention)} helper={t('projectExecution.projects.metricAttentionHelper', 'Needs review or clarification')} />
          <MetricCard label={t('projectExecution.projects.metricAvgProgress', 'Avg Progress')} value={`${stats.avgProgress}%`} helper={t('projectExecution.projects.metricAvgProgressHelper', 'Across listed projects')} />
        </div>

        {isLoading && projects.length === 0 ? <LoadingState label={t('projectExecution.projects.loading', 'Loading projects…')} /> : null}

        {!isLoading && projects.length === 0 ? (
          <EmptyState
            title={t('projectExecution.projects.emptyTitle', 'No projects yet')}
            description={t('projectExecution.projects.emptyDescription', 'Create your first project to start using the new execution platform.')}
            action={
              <button
                type="button"
                onClick={() => setIsCreateModalOpen(true)}
                className="rounded-full bg-zinc-950 px-4 py-2 text-sm font-medium text-white dark:bg-zinc-50 dark:text-zinc-950"
              >
                {t('projectExecution.shared.createProject', 'Create Project')}
              </button>
            }
          />
        ) : null}

        {projects.length > 0 ? (
          <div className="grid gap-4 xl:grid-cols-2">
            {projects.map((project) => (
              <GlassPanel
                key={project.id}
                hover
                className="border border-zinc-200/70 bg-white/80 p-6 dark:border-zinc-800 dark:bg-zinc-950/60"
              >
                <div className="flex flex-col gap-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
                        {t('projectExecution.projects.updatedPrefix', { value: formatDateTime(project.updatedAt), defaultValue: `Updated ${formatDateTime(project.updatedAt)}` })}
                      </p>
                      <h2 className="mt-2 text-xl font-semibold text-zinc-950 dark:text-zinc-50">
                        {project.title}
                      </h2>
                    </div>
                    <StatusBadge status={project.status} />
                  </div>

                  <p className="text-sm leading-6 text-zinc-600 dark:text-zinc-400">
                    {project.summary}
                  </p>

                  <div className="grid gap-3 rounded-[20px] border border-zinc-200/70 bg-zinc-50/70 p-4 sm:grid-cols-4 dark:border-zinc-800 dark:bg-zinc-900/60">
                    <div>
                      <p className="text-xs uppercase tracking-[0.14em] text-zinc-500 dark:text-zinc-400">{t('projectExecution.projects.progress', 'Progress')}
                      </p>
                      <p className="mt-2 text-lg font-semibold text-zinc-950 dark:text-zinc-50">
                        {project.progress}%
                      </p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-[0.14em] text-zinc-500 dark:text-zinc-400">{t('projectExecution.projects.tasks', 'Tasks')}
                      </p>
                      <p className="mt-2 text-lg font-semibold text-zinc-950 dark:text-zinc-50">
                        {project.completedTasks}/{project.totalTasks}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-[0.14em] text-zinc-500 dark:text-zinc-400">{t('projectExecution.projects.failed', 'Failed')}
                      </p>
                      <p className="mt-2 text-lg font-semibold text-zinc-950 dark:text-zinc-50">
                        {project.failedTasks}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-[0.14em] text-zinc-500 dark:text-zinc-400">{t('projectExecution.projects.risk', 'Risk')}
                      </p>
                      <p className="mt-2 text-lg font-semibold text-zinc-950 dark:text-zinc-50">
                        {project.needsClarification || project.failedTasks > 0 ? 1 : 0}
                      </p>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-3">
                    <Link
                      to={`/projects/${project.id}`}
                      className="rounded-full bg-zinc-950 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-800 dark:bg-zinc-50 dark:text-zinc-950 dark:hover:bg-zinc-200"
                    >{t('projectExecution.shared.openProject', 'Open Project')}
                    </Link>
                  </div>
                </div>
              </GlassPanel>
            ))}
          </div>
        ) : null}
      </div>

      <ProjectCreateModal
        isOpen={isCreateModalOpen}
        isSubmitting={isCreating}
        onClose={() => setIsCreateModalOpen(false)}
        onSubmit={handleCreateProject}
      />
    </>
  );
};
