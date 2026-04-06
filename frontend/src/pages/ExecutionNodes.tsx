import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';

import { projectExecutionApi } from '@/api/projectExecution';
import { GlassPanel } from '@/components/GlassPanel';
import { LayoutModal } from '@/components/LayoutModal';
import {
  EmptyState,
  LoadingState,
  MetricCard,
  NoticeBanner,
  StatusBadge,
} from '@/components/platform/PlatformUi';
import { useProjectExecutionStore } from '@/stores/projectExecutionStore';
import { formatNumber } from '@/utils/platformFormatting';

export const ExecutionNodes = () => {
  const { t } = useTranslation();
  const [isRegisterModalOpen, setIsRegisterModalOpen] = useState(false);
  const [availableProjects, setAvailableProjects] = useState<Array<{ id: string; title: string }>>([]);
  const [registerProjectId, setRegisterProjectId] = useState('');
  const [registerName, setRegisterName] = useState('');
  const [registerRuntimes, setRegisterRuntimes] = useState('external_worktree, remote_session');
  const [registerPaths, setRegisterPaths] = useState('');
  const [registerCommandTemplate, setRegisterCommandTemplate] = useState('');
  const [isRegistering, setIsRegistering] = useState(false);
  const [editingNodeId, setEditingNodeId] = useState<string | null>(null);
  const [commandTemplate, setCommandTemplate] = useState('');
  const [pathAllowlist, setPathAllowlist] = useState('');
  const [runtimeTypes, setRuntimeTypes] = useState('');
  const [isSavingNode, setIsSavingNode] = useState(false);
  const nodes = useProjectExecutionStore((state) => state.executionNodes);
  const isLoading = useProjectExecutionStore((state) => state.loading.nodes);
  const error = useProjectExecutionStore((state) => state.errors.nodes);
  const fallbackSections = useProjectExecutionStore((state) => state.fallbackSections);
  const loadExecutionNodes = useProjectExecutionStore((state) => state.loadExecutionNodes);
  const updateExecutionNode = useProjectExecutionStore((state) => state.updateExecutionNode);
  const registerExecutionNode = useProjectExecutionStore((state) => state.registerExecutionNode);

  useEffect(() => {
    void loadExecutionNodes();
    void projectExecutionApi.listProjects().then((result) => {
      setAvailableProjects(result.data.map((project) => ({ id: project.id, title: project.title })));
      setRegisterProjectId((current) => current || result.data[0]?.id || '');
    }).catch(() => undefined);
  }, [loadExecutionNodes]);

  const editingNode = nodes.find((node) => node.id === editingNodeId) || null;

  const openEditModal = (nodeId: string) => {
    const node = nodes.find((item) => item.id === nodeId);
    if (!node) return;
    setEditingNodeId(nodeId);
    setCommandTemplate(node.externalAgentCommandTemplate || '');
    setPathAllowlist((node.pathAllowlist || []).join('\n'));
    setRuntimeTypes((node.supportedRuntimeTypes || []).join(', '));
  };

  const handleSaveNode = async () => {
    if (!editingNode) return;
    try {
      setIsSavingNode(true);
      await updateExecutionNode(editingNode.id, {
        config: {
          external_agent_command_template: commandTemplate,
          path_allowlist: pathAllowlist.split(/\n+/).map((item) => item.trim()).filter(Boolean),
          supported_runtime_types: runtimeTypes.split(',').map((item) => item.trim()).filter(Boolean),
        },
      });
      toast.success(t('projectExecution.nodes.saveNodeSuccess', 'Runtime host updated'));
      setEditingNodeId(null);
    } catch (saveError) {
      const message = saveError instanceof Error ? saveError.message : t('projectExecution.nodes.saveNodeFailed', 'Failed to update runtime host');
      toast.error(message);
    } finally {
      setIsSavingNode(false);
    }
  };

  const handleRegisterNode = async () => {
    if (!registerProjectId || !registerName.trim()) return;
    try {
      setIsRegistering(true);
      await registerExecutionNode({
        projectId: registerProjectId,
        name: registerName.trim(),
        nodeType: 'external_cli',
        capabilities: ['host_execution', 'shell', 'ops'],
        config: {
          external_agent_command_template: registerCommandTemplate,
          path_allowlist: registerPaths.split(/\n+/).map((item) => item.trim()).filter(Boolean),
          supported_runtime_types: registerRuntimes.split(',').map((item) => item.trim()).filter(Boolean),
        },
      });
      toast.success(t('projectExecution.nodes.registerNodeSuccess', 'Runtime host registered'));
      setIsRegisterModalOpen(false);
      setRegisterName('');
      setRegisterPaths('');
      setRegisterCommandTemplate('');
    } catch (error) {
      const message = error instanceof Error ? error.message : t('projectExecution.nodes.registerNodeFailed', 'Failed to register runtime host');
      toast.error(message);
    } finally {
      setIsRegistering(false);
    }
  };

  const stats = useMemo(() => {
    const working = nodes.filter((node) => node.status.toLowerCase() === 'working').length;
    const healthy = nodes.filter((node) => ['working', 'idle'].includes(node.status.toLowerCase())).length;
    const avgCompletion =
      nodes.length > 0
        ? Math.round(nodes.reduce((total, node) => total + node.completionRate, 0) / nodes.length)
        : 0;

    return {
      total: nodes.length,
      working,
      healthy,
      avgCompletion,
    };
  }, [nodes]);

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-3xl space-y-3">
          <p className="text-sm font-semibold uppercase tracking-[0.22em] text-indigo-500">{t('projectExecution.nodes.badge', 'Capacity')}
          </p>
          <div>
            <h1 className="text-3xl font-semibold text-zinc-950 dark:text-zinc-50">
              {t('projectExecution.nodes.title', 'Runtime Hosts')}
            </h1>
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
              {t('projectExecution.nodes.subtitle', 'Monitor external runtime hosts that can spawn or carry external agents for host-affecting work.')}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => setIsRegisterModalOpen(true)}
            className="rounded-full bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500"
          >{t('projectExecution.nodes.registerNodeAction', 'Register Host')}
          </button>
          <Link
            to="/projects"
            className="rounded-full border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition hover:border-zinc-400 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:border-zinc-600 dark:hover:bg-zinc-900"
          >{t('projectExecution.shared.backToProjects', 'Back to Projects')}
          </Link>
        </div>
      </section>

      {fallbackSections.includes('nodes') ? (
        <NoticeBanner
          title={t('projectExecution.nodes.fallbackTitle', 'Execution nodes are using fallback data')}
          description={t('projectExecution.nodes.fallbackDescription', 'Node health is currently derived from the existing agent registry, with seeded data available if that registry cannot be reached.')}
        />
      ) : null}

      {error ? <NoticeBanner title={t('projectExecution.nodes.errorTitle', 'Node refresh issue')} description={error} /> : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label={t('projectExecution.nodes.metricNodes', 'Nodes')} value={formatNumber(stats.total)} helper={t('projectExecution.nodes.metricNodesHelper', 'Available execution workers')} />
        <MetricCard label={t('projectExecution.nodes.metricWorking', 'Working')} value={formatNumber(stats.working)} helper={t('projectExecution.nodes.metricWorkingHelper', 'Handling active work now')} />
        <MetricCard label={t('projectExecution.nodes.metricHealthy', 'Healthy')} value={formatNumber(stats.healthy)} helper={t('projectExecution.nodes.metricHealthyHelper', 'Working or idle nodes')} />
        <MetricCard label={t('projectExecution.nodes.metricAvgSuccess', 'Avg Success')} value={`${stats.avgCompletion}%`} helper={t('projectExecution.nodes.metricAvgSuccessHelper', 'Average completion rate')} />
      </div>

      {isLoading && nodes.length === 0 ? <LoadingState label={t('projectExecution.nodes.loading', 'Loading nodes…')} /> : null}

      {!isLoading && nodes.length === 0 ? (
        <EmptyState
          title={t('projectExecution.nodes.emptyTitle', 'No runtime hosts available')}
          description={t('projectExecution.nodes.emptyDescription', 'External runtime hosts appear here after a node agent registers with the control plane.')}
        />
      ) : null}

      {nodes.length > 0 ? (
        <div className="grid gap-4 xl:grid-cols-2">
          {nodes.map((node) => (
            <GlassPanel
              key={node.id}
              hover
              className="border border-zinc-200/70 bg-white/80 p-6 dark:border-zinc-800 dark:bg-zinc-950/60"
            >
              <div className="flex h-full flex-col gap-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <h2 className="text-xl font-semibold text-zinc-950 dark:text-zinc-50">
                      {node.name}
                    </h2>
                    <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                      {node.type}
                      {node.departmentName ? ` · ${node.departmentName}` : ''}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={() => openEditModal(node.id)}
                      className="rounded-full border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 transition hover:border-zinc-400 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:border-zinc-600 dark:hover:bg-zinc-900"
                    >
                      {t('projectExecution.nodes.editNodeAction', 'Edit Host')}
                    </button>
                    <StatusBadge status={node.status} />
                  </div>
                </div>

                <div className="grid gap-3 rounded-[20px] border border-zinc-200/70 bg-zinc-50/70 p-4 sm:grid-cols-4 dark:border-zinc-800 dark:bg-zinc-900/60">
                  <div>
                    <p className="text-xs uppercase tracking-[0.16em] text-zinc-500 dark:text-zinc-400">{t('projectExecution.nodes.activeProjects', 'Active Projects')}
                    </p>
                    <p className="mt-2 text-lg font-semibold text-zinc-950 dark:text-zinc-50">
                      {node.activeProjects}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-[0.16em] text-zinc-500 dark:text-zinc-400">{t('projectExecution.nodes.completed', 'Completed')}
                    </p>
                    <p className="mt-2 text-lg font-semibold text-zinc-950 dark:text-zinc-50">
                      {node.tasksCompleted}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-[0.16em] text-zinc-500 dark:text-zinc-400">{t('projectExecution.nodes.failed', 'Failed')}
                    </p>
                    <p className="mt-2 text-lg font-semibold text-zinc-950 dark:text-zinc-50">
                      {node.tasksFailed}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-[0.16em] text-zinc-500 dark:text-zinc-400">
                      Skills
                    </p>
                    <p className="mt-2 text-lg font-semibold text-zinc-950 dark:text-zinc-50">
                      {node.skillCount}
                    </p>
                  </div>
                </div>

                <div className="grid gap-3 text-sm text-zinc-600 dark:text-zinc-400 sm:grid-cols-2">
                  <p>{t('projectExecution.nodes.completionRate', 'Completion rate')}: {node.completionRate}%</p>
                  <p>{t('projectExecution.nodes.currentTaskLabel', 'Current task')}: {node.currentTask || t('projectExecution.nodes.idleValue', 'Idle')}</p>
                  <p>{t('projectExecution.nodes.model', 'Model')}: {node.model || '—'}</p>
                  <p>{t('projectExecution.nodes.provider', 'Provider')}: {node.provider || '—'}</p>
                  <p>{t('projectExecution.nodes.supportedRuntimes', 'Supported runtimes')}: {(node.supportedRuntimeTypes || []).join(', ') || t('projectExecution.nodes.none', '—')}</p>
                  <p>{t('projectExecution.nodes.pathAllowlist', 'Path allowlist')}: {(node.pathAllowlist || []).join(', ') || t('projectExecution.nodes.none', '—')}</p>
                </div>

                {node.topSkills.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {node.topSkills.map((skill) => (
                      <span
                        key={skill}
                        className="rounded-full bg-indigo-500/10 px-3 py-1 text-xs font-medium text-indigo-700 dark:text-indigo-300"
                      >
                        {skill}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            </GlassPanel>
          ))}
        </div>
      ) : null}
      <LayoutModal
        isOpen={!!editingNode}
        onClose={() => setEditingNodeId(null)}
        closeOnBackdropClick={!isSavingNode}
        closeOnEscape={!isSavingNode}
        title={t('projectExecution.nodes.editNodeTitle', 'Edit Runtime Host')}
        description={editingNode ? editingNode.name : undefined}
        footer={
          <div className="flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={() => setEditingNodeId(null)}
              disabled={isSavingNode}
              className="rounded-full px-4 py-2 text-sm font-semibold text-zinc-600 transition hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800 disabled:opacity-50"
            >
              {t('projectExecution.shared.cancel', 'Cancel')}
            </button>
            <button
              type="button"
              onClick={() => void handleSaveNode()}
              disabled={isSavingNode}
              className="rounded-full bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isSavingNode ? t('projectExecution.shared.saving', 'Saving…') : t('projectExecution.nodes.saveNodeAction', 'Save Host')}
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          <label className="block space-y-2">
            <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">{t('projectExecution.nodes.externalRunnerCommand', 'External runner command')}</span>
            <textarea
              value={commandTemplate}
              onChange={(event) => setCommandTemplate(event.target.value)}
              rows={4}
              className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
            />
          </label>
          <label className="block space-y-2">
            <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">{t('projectExecution.nodes.pathAllowlist', 'Path allowlist')}</span>
            <textarea
              value={pathAllowlist}
              onChange={(event) => setPathAllowlist(event.target.value)}
              rows={3}
              className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
              placeholder={t('projectExecution.nodes.pathAllowlistPlaceholder', 'One path per line')}
            />
          </label>
          <label className="block space-y-2">
            <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">{t('projectExecution.nodes.supportedRuntimes', 'Supported runtimes')}</span>
            <input
              value={runtimeTypes}
              onChange={(event) => setRuntimeTypes(event.target.value)}
              className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
              placeholder={t('projectExecution.nodes.supportedRuntimesPlaceholder', 'Comma-separated, e.g. external_worktree, remote_session')}
            />
          </label>
        </div>
      </LayoutModal>
      <LayoutModal
        isOpen={isRegisterModalOpen}
        onClose={() => setIsRegisterModalOpen(false)}
        closeOnBackdropClick={!isRegistering}
        closeOnEscape={!isRegistering}
        title={t('projectExecution.nodes.registerNodeTitle', 'Register Runtime Host')}
        footer={
          <div className="flex items-center justify-end gap-3">
            <button type="button" onClick={() => setIsRegisterModalOpen(false)} disabled={isRegistering} className="rounded-full px-4 py-2 text-sm font-semibold text-zinc-600 transition hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800 disabled:opacity-50">{t('projectExecution.shared.cancel', 'Cancel')}</button>
            <button type="button" onClick={() => void handleRegisterNode()} disabled={isRegistering || !registerProjectId || !registerName.trim()} className="rounded-full bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50">{isRegistering ? t('projectExecution.shared.saving', 'Saving…') : t('projectExecution.nodes.registerNodeAction', 'Register Host')}</button>
          </div>
        }
      >
        <div className="space-y-4">
          <select value={registerProjectId} onChange={(event) => setRegisterProjectId(event.target.value)} className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100">
            {availableProjects.map((project) => <option key={project.id} value={project.id}>{project.title}</option>)}
          </select>
          <input value={registerName} onChange={(event) => setRegisterName(event.target.value)} className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100" placeholder={t('projectExecution.nodes.registerNodeNamePlaceholder', 'Example: MacBook Host')} />
          <input value={registerRuntimes} onChange={(event) => setRegisterRuntimes(event.target.value)} className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100" placeholder={t('projectExecution.nodes.supportedRuntimesPlaceholder', 'Comma-separated, e.g. external_worktree, remote_session')} />
          <textarea value={registerPaths} onChange={(event) => setRegisterPaths(event.target.value)} rows={3} className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100" placeholder={t('projectExecution.nodes.pathAllowlistPlaceholder', 'One path per line')} />
          <textarea value={registerCommandTemplate} onChange={(event) => setRegisterCommandTemplate(event.target.value)} rows={4} className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100" placeholder={t('projectExecution.nodes.externalRunnerCommandPlaceholder', 'Example: external-agent --prompt-file LINX_AGENT_PROMPT_FILE')} />
        </div>
      </LayoutModal>
    </div>
  );
};

export default ExecutionNodes;
