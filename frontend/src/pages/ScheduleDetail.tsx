import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  Bot,
  CalendarClock,
  Clock3,
  Loader2,
  MessageSquareText,
  Pause,
  Play,
  RefreshCw,
  Trash2,
  Wand2,
  PencilLine,
  UserRound,
  Hash,
  AlertTriangle,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { schedulesApi } from '@/api';
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
} from '@/components/schedules/scheduleUtils';
import { useNotificationStore } from '@/stores';
import type {
  AgentSchedule,
  SchedulePreviewRequest,
  SchedulePreviewResponse,
  ScheduleRun,
  UpdateScheduleRequest,
} from '@/types/schedule';

const statusBadgeClasses: Record<string, string> = {
  active: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
  paused: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
  completed: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
  failed: 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300',
};

const isTerminalOnceSchedule = (schedule: AgentSchedule): boolean =>
  schedule.scheduleType === 'once' &&
  ['completed', 'failed'].includes(String(schedule.status || ''));

interface DetailMetaCardProps {
  label: string;
  value: string;
  title?: string;
  icon: React.ComponentType<{ className?: string }>;
}

const DetailMetaCard: React.FC<DetailMetaCardProps> = ({ label, value, title, icon: Icon }) => (
  <div className="rounded-[26px] border border-zinc-200 bg-zinc-50/80 p-4 dark:border-zinc-800 dark:bg-zinc-900/60">
    <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500 dark:text-zinc-400">
      <Icon className="h-3.5 w-3.5" />
      {label}
    </div>
    <p
      className="mt-2 break-words text-sm font-medium text-zinc-900 dark:text-zinc-100"
      title={title || value}
    >
      {value}
    </p>
  </div>
);

export const ScheduleDetail: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { scheduleId = '' } = useParams();
  const addNotification = useNotificationStore((state) => state.addNotification);

  const [schedule, setSchedule] = useState<AgentSchedule | null>(null);
  const [runs, setRuns] = useState<ScheduleRun[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [activeRunScheduleId, setActiveRunScheduleId] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [preview, setPreview] = useState<SchedulePreviewResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const loadScheduleDetail = async (mode: 'initial' | 'refresh' = 'initial') => {
    if (!scheduleId) {
      setError(t('schedules.detail.loadError', '加载定时任务失败'));
      setIsLoading(false);
      return;
    }

    if (mode === 'initial') {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }

    try {
      const [scheduleResponse, runsResponse] = await Promise.all([
        schedulesApi.getById(scheduleId),
        schedulesApi.listRuns(scheduleId, { limit: 10 }),
      ]);
      setSchedule(scheduleResponse);
      setRuns(runsResponse.items);
      setError(null);
    } catch (loadError) {
      console.error('Failed to load schedule detail:', loadError);
      setError(
        loadError instanceof Error
          ? loadError.message
          : t('schedules.detail.loadError', '加载定时任务失败')
      );
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    void loadScheduleDetail();
  }, [scheduleId]);

  const latestRun = useMemo(() => runs[0] || schedule?.latestRun || null, [runs, schedule]);
  const terminalOnceSchedule = schedule ? isTerminalOnceSchedule(schedule) : false;

  const handlePreview = async (payload: SchedulePreviewRequest) => {
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const response = await schedulesApi.preview(payload);
      setPreview(response);
    } catch (previewLoadError) {
      setPreview(null);
      setPreviewError(
        previewLoadError instanceof Error ? previewLoadError.message : 'Failed to preview schedule'
      );
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleSubmit = async (payload: UpdateScheduleRequest) => {
    if (!schedule) {
      return;
    }

    try {
      setSubmitting(true);
      const updated = await schedulesApi.update(schedule.id, payload);
      setSchedule(updated);
      addNotification({
        type: 'success',
        title: t('schedules.page.updatedTitle', '定时任务已更新'),
        message: `${updated.name} ${t('schedules.page.savedSuffix', '已保存')}`,
        actionUrl: `/schedules/${updated.id}`,
        actionLabel: t('schedules.page.viewDetails', '查看详情'),
      });
      setFormOpen(false);
      setPreview(null);
      await loadScheduleDetail('refresh');
    } catch (submitError) {
      console.error('Failed to update schedule:', submitError);
      toast.error(
        submitError instanceof Error
          ? submitError.message
          : t('schedules.page.saveError', '保存定时任务失败')
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handlePauseToggle = async () => {
    if (!schedule) {
      return;
    }
    if (terminalOnceSchedule) {
      toast.error(
        t('schedules.page.terminalPauseError', '已结束的一次性任务不能再暂停或恢复')
      );
      return;
    }

    try {
      const updated =
        schedule.status === 'paused'
          ? await schedulesApi.resume(schedule.id)
          : await schedulesApi.pause(schedule.id);
      setSchedule(updated);
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
      await loadScheduleDetail('refresh');
    } catch (toggleError) {
      console.error('Failed to toggle schedule status:', toggleError);
      toast.error(
        toggleError instanceof Error
          ? toggleError.message
          : t('schedules.page.toggleError', '更新任务状态失败')
      );
    }
  };

  const handleRunNow = async () => {
    if (!schedule) {
      return;
    }
    if (terminalOnceSchedule) {
      toast.error(t('schedules.page.terminalRunError', '已结束的一次性任务不能再次手动执行'));
      return;
    }

    try {
      setActiveRunScheduleId(schedule.id);
      await schedulesApi.runNow(schedule.id);
      addNotification({
        type: 'info',
        title: t('schedules.page.queuedTitle', '已加入执行队列'),
        message: `${schedule.name} ${t('schedules.page.queuedSuffix', '已触发立即执行')}`,
        actionUrl: `/workforce/${schedule.agentId}/conversations/${schedule.boundConversationId}`,
        actionLabel: t('schedules.page.openConversation', '打开绑定会话'),
      });
      await loadScheduleDetail('refresh');
    } catch (runError) {
      console.error('Failed to run schedule now:', runError);
      toast.error(
        runError instanceof Error
          ? runError.message
          : t('schedules.page.runNowError', '触发执行失败')
      );
    } finally {
      setActiveRunScheduleId(null);
    }
  };

  const handleDelete = async () => {
    if (!schedule) {
      return;
    }

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
      await schedulesApi.remove(schedule.id);
      toast.success(t('schedules.page.deleteSuccess', '定时任务已删除'));
      navigate('/schedules', { replace: true });
    } catch (deleteError) {
      console.error('Failed to delete schedule:', deleteError);
      toast.error(
        deleteError instanceof Error
          ? deleteError.message
          : t('schedules.page.deleteError', '删除定时任务失败')
      );
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3 text-sm text-zinc-500 dark:text-zinc-400">
          <Loader2 className="h-4 w-4 animate-spin" />
          {t('schedules.detail.loading', '正在加载定时任务详情')}
        </div>
      </div>
    );
  }

  if (!schedule) {
    return (
      <div className="space-y-6">
        <button
          type="button"
          onClick={() => navigate('/schedules')}
          className="inline-flex items-center gap-2 rounded-full border border-zinc-200 bg-white px-4 py-2 text-sm font-semibold text-zinc-700 transition hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-200 dark:hover:bg-zinc-900"
        >
          <ArrowLeft className="h-4 w-4" />
          {t('schedules.detail.back', '返回任务列表')}
        </button>
        <div className="rounded-[28px] border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/20 dark:text-rose-300">
          {error || t('schedules.detail.loadError', '加载定时任务失败')}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button
          type="button"
          onClick={() => navigate('/schedules')}
          className="inline-flex items-center gap-2 rounded-full border border-zinc-200 bg-white px-4 py-2 text-sm font-semibold text-zinc-700 transition hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-200 dark:hover:bg-zinc-900"
        >
          <ArrowLeft className="h-4 w-4" />
          {t('schedules.detail.back', '返回任务列表')}
        </button>

        <button
          type="button"
          onClick={() => void loadScheduleDetail('refresh')}
          disabled={isRefreshing}
          className="inline-flex items-center gap-2 rounded-full border border-zinc-200 bg-white px-4 py-2 text-sm font-semibold text-zinc-700 transition hover:bg-zinc-50 disabled:opacity-60 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-200 dark:hover:bg-zinc-900"
        >
          {isRefreshing ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          {t('schedules.page.refresh', '刷新')}
        </button>
      </div>

      <section className="rounded-[32px] border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0">
            <div className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/20 dark:text-emerald-300">
              <CalendarClock className="h-3.5 w-3.5" />
              {t('schedules.detail.badge', '任务详情')}
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <span
                className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                  statusBadgeClasses[schedule.status] ||
                  'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'
                }`}
              >
                {formatScheduleStatus(schedule.status)}
              </span>
              <span className="rounded-full border border-zinc-200 bg-zinc-100 px-2.5 py-1 text-[11px] font-semibold text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300">
                {formatScheduleType(schedule.scheduleType)}
              </span>
              <span className="rounded-full border border-zinc-200 bg-zinc-100 px-2.5 py-1 text-[11px] font-semibold text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300">
                {formatCreatedVia(schedule.createdVia)}
              </span>
            </div>
            <h1 className="mt-4 text-4xl font-black tracking-tight text-zinc-900 dark:text-zinc-100">
              {schedule.name}
            </h1>
            <p className="mt-2 max-w-3xl text-sm text-zinc-600 dark:text-zinc-400">
              {t(
                'schedules.detail.subtitle',
                '查看完整排班信息、绑定会话和最近执行记录。'
              )}
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setFormOpen(true)}
              className="inline-flex items-center gap-2 rounded-full border border-zinc-200 px-4 py-2 text-sm font-semibold text-zinc-700 transition hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-900"
            >
              <PencilLine className="h-4 w-4" />
              {t('common.edit', '编辑')}
            </button>

            {!terminalOnceSchedule ? (
              <button
                type="button"
                onClick={() => void handleRunNow()}
                disabled={activeRunScheduleId === schedule.id}
                className="inline-flex items-center gap-2 rounded-full border border-zinc-200 px-4 py-2 text-sm font-semibold text-zinc-700 transition hover:bg-zinc-50 disabled:opacity-60 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-900"
              >
                {activeRunScheduleId === schedule.id ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Wand2 className="h-4 w-4" />
                )}
                {t('schedules.page.runNow', '立即执行')}
              </button>
            ) : null}

            {!terminalOnceSchedule ? (
              <button
                type="button"
                onClick={() => void handlePauseToggle()}
                className="inline-flex items-center gap-2 rounded-full border border-zinc-200 px-4 py-2 text-sm font-semibold text-zinc-700 transition hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-900"
              >
                {schedule.status === 'paused' ? (
                  <Play className="h-4 w-4" />
                ) : (
                  <Pause className="h-4 w-4" />
                )}
                {schedule.status === 'paused'
                  ? t('schedules.page.resume', '恢复')
                  : t('schedules.page.pause', '暂停')}
              </button>
            ) : null}

            <button
              type="button"
              onClick={() =>
                navigate(`/workforce/${schedule.agentId}/conversations/${schedule.boundConversationId}`)
              }
              className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-semibold text-emerald-700 transition hover:bg-emerald-100 dark:border-emerald-900/60 dark:bg-emerald-950/20 dark:text-emerald-300 dark:hover:bg-emerald-950/40"
            >
              <MessageSquareText className="h-4 w-4" />
              {t('schedules.page.openConversation', '打开绑定会话')}
            </button>

            <button
              type="button"
              onClick={() => void handleDelete()}
              className="inline-flex items-center gap-2 rounded-full border border-rose-200 px-4 py-2 text-sm font-semibold text-rose-600 transition hover:bg-rose-50 dark:border-rose-900/60 dark:text-rose-300 dark:hover:bg-rose-950/20"
            >
              <Trash2 className="h-4 w-4" />
              {t('common.delete', '删除')}
            </button>
          </div>
        </div>
      </section>

      {error ? (
        <div className="rounded-[28px] border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/20 dark:text-rose-300">
          {error}
        </div>
      ) : null}

      <section className="grid gap-4 xl:grid-cols-4">
        <DetailMetaCard
          label={t('schedules.detail.fields.agent', 'Agent')}
          value={schedule.agentName || schedule.agentId}
          title={schedule.agentName || schedule.agentId}
          icon={Bot}
        />
        <DetailMetaCard
          label={t('schedules.detail.fields.timing', '排班')}
          value={describeScheduleTiming(schedule)}
          title={describeScheduleTiming(schedule)}
          icon={CalendarClock}
        />
        <DetailMetaCard
          label={t('schedules.detail.fields.nextRun', '下次执行')}
          value={formatScheduleDateTime(schedule.nextRunAt || schedule.runAtUtc, schedule.timezone)}
          icon={Clock3}
        />
        <DetailMetaCard
          label={t('schedules.detail.fields.latestResult', '最近结果')}
          value={
            latestRun
              ? latestRunSummary(latestRun)
              : schedule.lastRunStatus
                ? formatRunStatus(schedule.lastRunStatus)
                : t('schedules.page.noRunsYet', '暂无执行')
          }
          icon={RefreshCw}
        />
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.5fr,1fr]">
        <div className="space-y-5">
          <div className="rounded-[30px] border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
              {t('schedules.detail.sections.prompt', '执行内容')}
            </h2>
            <p className="mt-4 whitespace-pre-wrap break-words rounded-3xl bg-zinc-50 px-4 py-4 text-sm leading-7 text-zinc-700 dark:bg-zinc-900/60 dark:text-zinc-200">
              {schedule.promptTemplate}
            </p>
          </div>

          <div className="rounded-[30px] border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
              {t('schedules.detail.sections.runs', '最近运行')}
            </h2>
            <div className="mt-4 space-y-3">
              {runs.length > 0 ? (
                runs.map((run) => (
                  <div
                    key={run.id}
                    className="rounded-3xl border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-800 dark:bg-zinc-900/60"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                          {formatRunStatus(run.status)}
                        </p>
                        <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                          {formatScheduleDateTime(
                            run.completedAt || run.startedAt || run.scheduledFor,
                            schedule.timezone
                          )}
                        </p>
                      </div>
                      <span className="rounded-full border border-zinc-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-zinc-600 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-300">
                        {run.deliveryChannel}
                      </span>
                    </div>
                    {run.errorMessage ? (
                      <p className="mt-3 text-sm text-rose-600 dark:text-rose-300">
                        {run.errorMessage}
                      </p>
                    ) : null}
                    {run.skipReason ? (
                      <p className="mt-3 text-sm text-amber-600 dark:text-amber-300">
                        {run.skipReason}
                      </p>
                    ) : null}
                  </div>
                ))
              ) : (
                <div className="rounded-3xl border border-dashed border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900/50 dark:text-zinc-400">
                  {t('schedules.page.noRuns', '暂无执行记录')}
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="space-y-5">
          <div className="rounded-[30px] border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
              {t('schedules.detail.sections.schedule', '排班信息')}
            </h2>
            <dl className="mt-4 space-y-4 text-sm">
              <div className="flex items-start justify-between gap-4">
                <dt className="text-zinc-500 dark:text-zinc-400">
                  {t('schedules.detail.fields.type', '类型')}
                </dt>
                <dd className="text-right text-zinc-900 dark:text-zinc-100">
                  {formatScheduleType(schedule.scheduleType)}
                </dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="text-zinc-500 dark:text-zinc-400">
                  {t('schedules.detail.fields.timezone', '时区')}
                </dt>
                <dd className="text-right text-zinc-900 dark:text-zinc-100">{schedule.timezone}</dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="text-zinc-500 dark:text-zinc-400">
                  {t('schedules.detail.fields.cron', 'Cron')}
                </dt>
                <dd className="max-w-[16rem] break-all text-right font-mono text-zinc-900 dark:text-zinc-100">
                  {schedule.cronExpression || t('schedules.shared.notSet', '未设置')}
                </dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="text-zinc-500 dark:text-zinc-400">
                  {t('schedules.detail.fields.runAt', '单次时间')}
                </dt>
                <dd className="text-right text-zinc-900 dark:text-zinc-100">
                  {formatScheduleDateTime(schedule.runAtUtc, schedule.timezone)}
                </dd>
              </div>
              {schedule.lastError ? (
                <div className="rounded-2xl border border-rose-200 bg-rose-50 px-3 py-3 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/20 dark:text-rose-300">
                  <div className="flex items-center gap-2 font-semibold">
                    <AlertTriangle className="h-4 w-4" />
                    {t('schedules.detail.fields.lastError', '最近错误')}
                  </div>
                  <p className="mt-2 break-words">{schedule.lastError}</p>
                </div>
              ) : null}
            </dl>
          </div>

          <div className="rounded-[30px] border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
              {t('schedules.detail.sections.binding', '绑定信息')}
            </h2>
            <dl className="mt-4 space-y-4 text-sm">
              <div className="flex items-start justify-between gap-4">
                <dt className="text-zinc-500 dark:text-zinc-400">
                  {t('schedules.detail.fields.origin', '来源')}
                </dt>
                <dd className="text-right text-zinc-900 dark:text-zinc-100">
                  {formatOriginSurface(schedule.originSurface)}
                </dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="text-zinc-500 dark:text-zinc-400">
                  {t('schedules.detail.fields.createdVia', '创建方式')}
                </dt>
                <dd className="text-right text-zinc-900 dark:text-zinc-100">
                  {formatCreatedVia(schedule.createdVia)}
                </dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="text-zinc-500 dark:text-zinc-400">
                  {t('schedules.detail.fields.conversation', '绑定会话')}
                </dt>
                <dd className="max-w-[16rem] break-words text-right text-zinc-900 dark:text-zinc-100">
                  {schedule.boundConversationTitle || schedule.boundConversationId}
                </dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="text-zinc-500 dark:text-zinc-400">
                  {t('schedules.detail.fields.owner', '创建者')}
                </dt>
                <dd className="text-right text-zinc-900 dark:text-zinc-100">
                  {schedule.ownerUsername || schedule.ownerUserId}
                </dd>
              </div>
            </dl>
          </div>

          <div className="rounded-[30px] border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
              {t('schedules.detail.sections.metadata', '元数据')}
            </h2>
            <dl className="mt-4 space-y-4 text-sm">
              <div className="flex items-start justify-between gap-4">
                <dt className="flex items-center gap-2 text-zinc-500 dark:text-zinc-400">
                  <Hash className="h-3.5 w-3.5" />
                  {t('schedules.detail.fields.scheduleId', '任务 ID')}
                </dt>
                <dd className="max-w-[16rem] break-all text-right text-zinc-900 dark:text-zinc-100">
                  {schedule.id}
                </dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="flex items-center gap-2 text-zinc-500 dark:text-zinc-400">
                  <UserRound className="h-3.5 w-3.5" />
                  {t('schedules.detail.fields.messageId', '来源消息 ID')}
                </dt>
                <dd className="max-w-[16rem] break-all text-right text-zinc-900 dark:text-zinc-100">
                  {schedule.originMessageId || t('schedules.shared.notSet', '未设置')}
                </dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="text-zinc-500 dark:text-zinc-400">
                  {t('schedules.detail.fields.createdAt', '创建时间')}
                </dt>
                <dd className="text-right text-zinc-900 dark:text-zinc-100">
                  {formatScheduleDateTime(schedule.createdAt, schedule.timezone)}
                </dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="text-zinc-500 dark:text-zinc-400">
                  {t('schedules.detail.fields.updatedAt', '更新时间')}
                </dt>
                <dd className="text-right text-zinc-900 dark:text-zinc-100">
                  {formatScheduleDateTime(schedule.updatedAt, schedule.timezone)}
                </dd>
              </div>
            </dl>
          </div>
        </div>
      </section>

      <ScheduleFormModal
        isOpen={formOpen}
        agents={[]}
        schedule={schedule}
        isSubmitting={submitting}
        preview={preview}
        previewLoading={previewLoading}
        previewError={previewError}
        onClose={() => {
          setFormOpen(false);
          setPreview(null);
          setPreviewError(null);
        }}
        onPreview={handlePreview}
        onSubmit={handleSubmit}
      />
    </div>
  );
};
