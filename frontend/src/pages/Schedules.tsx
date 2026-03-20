import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowRight,
  Bot,
  CalendarClock,
  Clock3,
  Loader2,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  Wand2,
  PencilLine,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { agentsApi } from '@/api';
import { ScheduleFormModal } from '@/components/schedules/ScheduleFormModal';
import {
  describeScheduleTiming,
  formatCreatedVia,
  formatOriginSurface,
  formatRunStatus,
  formatScheduleDateTime,
  formatScheduleStatus,
  formatScheduleType,
  latestRunSummary,
  summarizePrompt,
} from '@/components/schedules/scheduleUtils';
import { useAuthStore, useNotificationStore, useScheduleStore } from '@/stores';
import type { Agent } from '@/types/agent';
import type {
  AgentSchedule,
  CreateScheduleRequest,
  SchedulePreviewRequest,
  UpdateScheduleRequest,
} from '@/types/schedule';

const statusBadgeClasses: Record<string, string> = {
  active: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
  paused: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
  completed: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
  failed: 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300',
};

const metaBadgeClasses = 'rounded-full border border-zinc-200/80 bg-zinc-100/80 px-2.5 py-1 text-[11px] font-semibold text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300';

const isTerminalOnceSchedule = (schedule: AgentSchedule): boolean =>
  schedule.scheduleType === 'once' &&
  ['completed', 'failed'].includes(String(schedule.status || ''));

interface SummaryMetricProps {
  label: string;
  value: string;
  title?: string;
  icon: React.ComponentType<{ className?: string }>;
}

const SummaryMetric: React.FC<SummaryMetricProps> = ({ label, value, title, icon: Icon }) => (
  <div className="min-w-0 space-y-1">
    <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500 dark:text-zinc-400">
      <Icon className="h-3.5 w-3.5" />
      {label}
    </div>
    <p
      className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-100"
      title={title || value}
    >
      {value}
    </p>
  </div>
);

interface IconActionButtonProps {
  ariaLabel: string;
  title: string;
  onClick: () => void;
  icon: React.ComponentType<{ className?: string }>;
  disabled?: boolean;
  tone?: 'default' | 'danger';
  spinning?: boolean;
}

const IconActionButton: React.FC<IconActionButtonProps> = ({
  ariaLabel,
  title,
  onClick,
  icon: Icon,
  disabled = false,
  tone = 'default',
  spinning = false,
}) => (
  <button
    type="button"
    aria-label={ariaLabel}
    title={title}
    onClick={onClick}
    disabled={disabled}
    className={`inline-flex h-9 w-9 items-center justify-center rounded-full border transition disabled:opacity-60 ${
      tone === 'danger'
        ? 'border-rose-200 text-rose-600 hover:bg-rose-50 dark:border-rose-900/60 dark:text-rose-300 dark:hover:bg-rose-950/20'
        : 'border-zinc-200 text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-900'
    }`}
  >
    {spinning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Icon className="h-4 w-4" />}
  </button>
);

export const Schedules: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const redirectedScheduleId = searchParams.get('scheduleId');
  const { user } = useAuthStore();
  const addNotification = useNotificationStore((state) => state.addNotification);
  const {
    schedules,
    total,
    isLoading,
    error,
    filters,
    preview,
    previewLoading,
    previewError,
    setFilters,
    clearPreview,
    loadSchedules,
    createSchedule,
    updateSchedule,
    deleteSchedule,
    pauseSchedule,
    resumeSchedule,
    runScheduleNow,
    previewSchedule,
  } = useScheduleStore();

  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState<AgentSchedule | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [activeRunScheduleId, setActiveRunScheduleId] = useState<string | null>(null);

  const canViewAll = ['admin', 'manager'].includes(String(user?.role || '').toLowerCase());

  useEffect(() => {
    if (!redirectedScheduleId) {
      return;
    }
    navigate(`/schedules/${redirectedScheduleId}`, { replace: true });
  }, [navigate, redirectedScheduleId]);

  useEffect(() => {
    void loadSchedules().catch(() => undefined);
  }, [filters, loadSchedules]);

  useEffect(() => {
    let cancelled = false;

    const loadAgents = async () => {
      try {
        setAgentsLoading(true);
        const response = await agentsApi.getAll();
        if (!cancelled) {
          setAgents(response.filter((agent) => agent.canExecute !== false));
        }
      } catch (loadError) {
        console.error('Failed to load agents for schedules:', loadError);
      } finally {
        if (!cancelled) {
          setAgentsLoading(false);
        }
      }
    };

    void loadAgents();
    return () => {
      cancelled = true;
    };
  }, []);

  const scheduleCountLabel = useMemo(
    () =>
      t('schedules.page.count', {
        count: total,
        defaultValue: `${total} 个任务`,
      }),
    [t, total]
  );

  const handleOpenCreate = () => {
    clearPreview();
    setEditingSchedule(null);
    setFormOpen(true);
  };

  const handleOpenEdit = (schedule: AgentSchedule) => {
    clearPreview();
    setEditingSchedule(schedule);
    setFormOpen(true);
  };

  const handlePreview = async (payload: SchedulePreviewRequest) => {
    try {
      await previewSchedule(payload);
    } catch {
      // inline error handled by modal/store
    }
  };

  const handleSubmit = async (payload: CreateScheduleRequest | UpdateScheduleRequest) => {
    try {
      setSubmitting(true);
      if (editingSchedule) {
        const updated = await updateSchedule(editingSchedule.id, payload as UpdateScheduleRequest);
        addNotification({
          type: 'success',
          title: t('schedules.page.updatedTitle', '定时任务已更新'),
          message: `${updated.name} ${t('schedules.page.savedSuffix', '已保存')}`,
          actionUrl: `/schedules/${updated.id}`,
          actionLabel: t('schedules.page.viewDetails', '查看详情'),
        });
      } else {
        const created = await createSchedule(payload as CreateScheduleRequest);
        addNotification({
          type: 'success',
          title: t('schedules.page.createdTitle', '定时任务已创建'),
          message: `${created.name} ${t('schedules.page.createdSuffix', '已创建')}`,
          actionUrl: `/schedules/${created.id}`,
          actionLabel: t('schedules.page.viewDetails', '查看详情'),
        });
      }
      setFormOpen(false);
      setEditingSchedule(null);
      clearPreview();
      await loadSchedules();
    } catch (submitError) {
      console.error('Failed to save schedule:', submitError);
      toast.error(
        submitError instanceof Error
          ? submitError.message
          : t('schedules.page.saveError', '保存定时任务失败')
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handlePauseToggle = async (schedule: AgentSchedule) => {
    if (isTerminalOnceSchedule(schedule)) {
      toast.error(
        t('schedules.page.terminalPauseError', '已结束的一次性任务不能再暂停或恢复')
      );
      return;
    }

    try {
      const updated =
        schedule.status === 'paused'
          ? await resumeSchedule(schedule.id)
          : await pauseSchedule(schedule.id);
      addNotification({
        type: updated.status === 'paused' ? 'warning' : 'success',
        title:
          updated.status === 'paused'
            ? t('schedules.page.pausedTitle', '定时任务已暂停')
            : t('schedules.page.resumedTitle', '定时任务已恢复'),
        message: updated.name,
        actionUrl: `/schedules/${updated.id}`,
        actionLabel: t('schedules.page.viewDetails', '查看详情'),
      });
      await loadSchedules();
    } catch (toggleError) {
      console.error('Failed to toggle schedule status:', toggleError);
      toast.error(
        toggleError instanceof Error
          ? toggleError.message
          : t('schedules.page.toggleError', '更新任务状态失败')
      );
    }
  };

  const handleDelete = async (schedule: AgentSchedule) => {
    if (
      !window.confirm(
        t('schedules.page.deleteConfirm', {
          name: schedule.name,
          defaultValue: `确认删除定时任务「${schedule.name}」吗？`,
        })
      )
    ) {
      return;
    }

    try {
      await deleteSchedule(schedule.id);
      toast.success(t('schedules.page.deleteSuccess', '定时任务已删除'));
    } catch (deleteError) {
      console.error('Failed to delete schedule:', deleteError);
      toast.error(
        deleteError instanceof Error
          ? deleteError.message
          : t('schedules.page.deleteError', '删除定时任务失败')
      );
    }
  };

  const handleRunNow = async (schedule: AgentSchedule) => {
    if (isTerminalOnceSchedule(schedule)) {
      toast.error(t('schedules.page.terminalRunError', '已结束的一次性任务不能再次手动执行'));
      return;
    }

    try {
      setActiveRunScheduleId(schedule.id);
      await runScheduleNow(schedule.id);
      addNotification({
        type: 'info',
        title: t('schedules.page.queuedTitle', '已加入执行队列'),
        message: `${schedule.name} ${t('schedules.page.queuedSuffix', '已触发立即执行')}`,
        actionUrl: `/schedules/${schedule.id}`,
        actionLabel: t('schedules.page.viewDetails', '查看详情'),
      });
      await loadSchedules();
    } catch (runError) {
      console.error('Failed to enqueue schedule run:', runError);
      toast.error(
        runError instanceof Error
          ? runError.message
          : t('schedules.page.runNowError', '触发执行失败')
      );
    } finally {
      setActiveRunScheduleId(null);
    }
  };

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/20 dark:text-emerald-300">
            <CalendarClock className="h-3.5 w-3.5" />
            {t('schedules.page.badge', 'Agent Schedule')}
          </div>
          <h1 className="mt-4 text-4xl font-black tracking-tight text-zinc-900 dark:text-zinc-100">
            {t('nav.schedules', '定时任务')}
          </h1>
          <p className="mt-2 max-w-3xl text-sm text-zinc-600 dark:text-zinc-400">
            {t(
              'schedules.page.subtitle',
              '管理手动创建和 Agent 自动创建的任务。循环任务基于 cron，触发后会继续在绑定会话内执行。'
            )}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="rounded-full border border-zinc-200 bg-white px-4 py-2 text-sm font-semibold text-zinc-700 shadow-sm dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200">
            {scheduleCountLabel}
          </div>
          <button
            type="button"
            onClick={() => void loadSchedules()}
            className="inline-flex items-center gap-2 rounded-full border border-zinc-200 bg-white px-4 py-2 text-sm font-semibold text-zinc-700 transition hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            <RefreshCw className="h-4 w-4" />
            {t('schedules.page.refresh', '刷新')}
          </button>
          <button
            type="button"
            onClick={handleOpenCreate}
            className="inline-flex items-center gap-2 rounded-full bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-700"
          >
            <Plus className="h-4 w-4" />
            {t('schedules.page.create', '新建任务')}
          </button>
        </div>
      </div>

      <section className="grid gap-4 rounded-[32px] border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950 lg:grid-cols-[1.6fr_repeat(4,minmax(0,1fr))]">
        <label className="relative block">
          <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
          <input
            aria-label={t('schedules.page.searchLabel', '搜索定时任务')}
            value={filters.query || ''}
            onChange={(event) => setFilters({ query: event.target.value, offset: 0 })}
            placeholder={t('schedules.page.searchPlaceholder', '搜索任务名或执行内容')}
            className="w-full rounded-2xl border border-zinc-200 bg-zinc-50 py-3 pl-11 pr-4 text-sm text-zinc-900 outline-none transition focus:border-emerald-400 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          />
        </label>

        <select
          aria-label={t('schedules.page.statusFilter', '筛选状态')}
          value={filters.status}
          onChange={(event) =>
            setFilters({ status: event.target.value as typeof filters.status, offset: 0 })
          }
          className="rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-emerald-400 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
        >
          <option value="all">{t('schedules.page.statusAll', '全部状态')}</option>
          <option value="active">{t('schedules.shared.status.active', '运行中')}</option>
          <option value="paused">{t('schedules.shared.status.paused', '已暂停')}</option>
          <option value="completed">{t('schedules.shared.status.completed', '已完成')}</option>
          <option value="failed">{t('schedules.shared.status.failed', '失败')}</option>
        </select>

        <select
          aria-label={t('schedules.page.typeFilter', '筛选类型')}
          value={filters.type}
          onChange={(event) =>
            setFilters({ type: event.target.value as typeof filters.type, offset: 0 })
          }
          className="rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-emerald-400 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
        >
          <option value="all">{t('schedules.page.typeAll', '全部类型')}</option>
          <option value="once">{t('schedules.shared.types.once', '单次')}</option>
          <option value="recurring">{t('schedules.shared.types.recurring', '循环')}</option>
        </select>

        <select
          aria-label={t('schedules.page.createdViaFilter', '筛选创建方式')}
          value={filters.createdVia}
          onChange={(event) =>
            setFilters({ createdVia: event.target.value as typeof filters.createdVia, offset: 0 })
          }
          className="rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-emerald-400 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
        >
          <option value="all">{t('schedules.page.createdViaAll', '全部来源')}</option>
          <option value="manual_ui">{t('schedules.shared.createdVia.manual', '手动创建')}</option>
          <option value="agent_auto">
            {t('schedules.shared.createdVia.agent', 'Agent 自动创建')}
          </option>
        </select>

        <select
          aria-label={t('schedules.page.agentFilter', '筛选 Agent')}
          value={filters.agentId || ''}
          onChange={(event) => setFilters({ agentId: event.target.value, offset: 0 })}
          disabled={agentsLoading}
          className="rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-emerald-400 disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
        >
          <option value="">{t('schedules.page.agentAll', '全部 Agent')}</option>
          {agents.map((agent) => (
            <option key={agent.id} value={agent.id}>
              {agent.name}
            </option>
          ))}
        </select>

        {canViewAll ? (
          <select
            aria-label={t('schedules.page.scopeFilter', '筛选范围')}
            value={filters.scope}
            onChange={(event) =>
              setFilters({ scope: event.target.value as 'mine' | 'all', offset: 0 })
            }
            className="rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-emerald-400 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          >
            <option value="mine">{t('schedules.page.scopeMine', '我的任务')}</option>
            <option value="all">{t('schedules.page.scopeAll', '全部任务')}</option>
          </select>
        ) : null}
      </section>

      {error ? (
        <div className="rounded-[28px] border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/20 dark:text-rose-300">
          {error}
        </div>
      ) : null}

      {isLoading ? (
        <section className="grid gap-4 xl:grid-cols-2 2xl:grid-cols-3">
          {Array.from({ length: 4 }).map((_, index) => (
            <div
              key={`schedule-skeleton-${index}`}
              className="rounded-[28px] border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
            >
              <div className="animate-pulse space-y-3">
                <div className="flex gap-2">
                  <div className="h-6 w-20 rounded-full bg-zinc-200 dark:bg-zinc-800" />
                  <div className="h-6 w-16 rounded-full bg-zinc-200 dark:bg-zinc-800" />
                </div>
                <div className="h-6 w-2/3 rounded-xl bg-zinc-200 dark:bg-zinc-800" />
                <div className="h-4 w-full rounded-lg bg-zinc-200 dark:bg-zinc-800" />
                <div className="grid gap-x-4 gap-y-2 sm:grid-cols-2">
                  {Array.from({ length: 4 }).map((__, metricIndex) => (
                    <div
                      key={`schedule-skeleton-metric-${metricIndex}`}
                      className="h-8 rounded-xl bg-zinc-100 dark:bg-zinc-900"
                    />
                  ))}
                </div>
              </div>
            </div>
          ))}
        </section>
      ) : schedules.length === 0 ? (
        <section className="rounded-[32px] border border-dashed border-zinc-300 bg-white px-6 py-14 text-center shadow-sm dark:border-zinc-700 dark:bg-zinc-950">
          <p className="text-sm font-medium text-zinc-600 dark:text-zinc-300">
            {t('schedules.page.empty', '当前没有匹配的定时任务。')}
          </p>
        </section>
      ) : (
        <section className="grid gap-4 xl:grid-cols-2 2xl:grid-cols-3">
          {schedules.map((schedule) => {
            const terminalOnceSchedule = isTerminalOnceSchedule(schedule);
            const timingText = describeScheduleTiming(schedule);
            const nextRunText = formatScheduleDateTime(
              schedule.nextRunAt || schedule.runAtUtc,
              schedule.timezone
            );
            const latestResult = schedule.latestRun
              ? latestRunSummary(schedule.latestRun)
              : schedule.lastRunStatus
                ? formatRunStatus(schedule.lastRunStatus)
                : t('schedules.page.noRunsYet', '暂无执行');

            return (
              <article
                key={schedule.id}
                className="group flex h-full flex-col rounded-[28px] border border-zinc-200 bg-white p-4 shadow-sm transition hover:border-emerald-200 hover:shadow-md dark:border-zinc-800 dark:bg-zinc-950 dark:hover:border-emerald-900/60"
              >
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <span
                    className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                      statusBadgeClasses[schedule.status] ||
                      'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'
                    }`}
                  >
                    {formatScheduleStatus(schedule.status)}
                  </span>
                  <span className={metaBadgeClasses}>{formatScheduleType(schedule.scheduleType)}</span>
                  <span className={metaBadgeClasses}>
                    {formatCreatedVia(schedule.createdVia)}
                  </span>
                </div>

                <button
                  type="button"
                  onClick={() => navigate(`/schedules/${schedule.id}`)}
                  className="mt-3 block max-w-full text-left"
                >
                  <h2
                    className="truncate text-lg font-black tracking-tight text-zinc-900 transition group-hover:text-emerald-700 dark:text-zinc-100 dark:group-hover:text-emerald-300"
                    title={schedule.name}
                  >
                    {schedule.name}
                  </h2>
                </button>

                <p
                  className="mt-1.5 truncate text-[13px] text-zinc-500 dark:text-zinc-400"
                  title={schedule.promptTemplate}
                >
                  {summarizePrompt(schedule.promptTemplate, 88)}
                </p>

                <div className="mt-3 grid gap-x-4 gap-y-2 sm:grid-cols-2">
                  <SummaryMetric
                    label={t('schedules.page.summary.agent', 'Agent')}
                    value={schedule.agentName || schedule.agentId}
                    title={schedule.agentName || schedule.agentId}
                    icon={Bot}
                  />
                  <SummaryMetric
                    label={t('schedules.page.summary.timing', '排班')}
                    value={timingText}
                    title={timingText}
                    icon={CalendarClock}
                  />
                  <SummaryMetric
                    label={t('schedules.page.summary.nextRun', '下次执行')}
                    value={nextRunText}
                    title={nextRunText}
                    icon={Clock3}
                  />
                  <SummaryMetric
                    label={t('schedules.page.summary.latestResult', '最近结果')}
                    value={latestResult}
                    title={latestResult}
                    icon={RefreshCw}
                  />
                </div>

                <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-zinc-500 dark:text-zinc-400">
                  <span className="truncate">
                    {t('schedules.page.summary.source', '来源')} ·{' '}
                    {formatOriginSurface(schedule.originSurface)}
                  </span>
                  <span>•</span>
                  <span className="truncate">{schedule.timezone}</span>
                </div>

                <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-zinc-200/80 pt-3 dark:border-zinc-800">
                  <button
                    type="button"
                    onClick={() => navigate(`/schedules/${schedule.id}`)}
                    className="inline-flex items-center gap-1.5 rounded-full bg-zinc-900 px-3.5 py-2 text-sm font-semibold text-white transition hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-950 dark:hover:bg-white"
                  >
                    {t('schedules.page.viewDetails', '查看详情')}
                    <ArrowRight className="h-4 w-4" />
                  </button>

                  {!terminalOnceSchedule ? (
                    <IconActionButton
                      ariaLabel={t('schedules.page.runNow', '立即执行')}
                      title={t('schedules.page.runNow', '立即执行')}
                      onClick={() => void handleRunNow(schedule)}
                      icon={Wand2}
                      disabled={activeRunScheduleId === schedule.id}
                      spinning={activeRunScheduleId === schedule.id}
                    />
                  ) : null}

                  {!terminalOnceSchedule ? (
                    <IconActionButton
                      ariaLabel={
                        schedule.status === 'paused'
                          ? t('schedules.page.resume', '恢复')
                          : t('schedules.page.pause', '暂停')
                      }
                      title={
                        schedule.status === 'paused'
                          ? t('schedules.page.resume', '恢复')
                          : t('schedules.page.pause', '暂停')
                      }
                      onClick={() => void handlePauseToggle(schedule)}
                      icon={schedule.status === 'paused' ? Play : Pause}
                    />
                  ) : null}

                  <IconActionButton
                    ariaLabel={t('common.edit', '编辑')}
                    title={t('common.edit', '编辑')}
                    onClick={() => handleOpenEdit(schedule)}
                    icon={PencilLine}
                  />

                  <IconActionButton
                    ariaLabel={t('common.delete', '删除')}
                    title={t('common.delete', '删除')}
                    onClick={() => void handleDelete(schedule)}
                    icon={Trash2}
                    tone="danger"
                  />
                </div>
              </article>
            );
          })}
        </section>
      )}

      <ScheduleFormModal
        isOpen={formOpen}
        agents={agents}
        schedule={editingSchedule}
        isSubmitting={submitting}
        preview={preview}
        previewLoading={previewLoading}
        previewError={previewError}
        onClose={() => {
          setFormOpen(false);
          setEditingSchedule(null);
          clearPreview();
        }}
        onPreview={handlePreview}
        onSubmit={handleSubmit}
      />
    </div>
  );
};
