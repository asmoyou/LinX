import React, { useEffect, useMemo, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { LayoutModal } from '@/components/LayoutModal';
import type { Agent } from '@/types/agent';
import type {
  AgentSchedule,
  CreateScheduleRequest,
  SchedulePreviewResponse,
  UpdateScheduleRequest,
} from '@/types/schedule';
import { CronBuilder } from './CronBuilder';
import {
  builderToCron,
  createDefaultCronBuilderState,
  cronToBuilder,
  type CronBuilderState,
} from './cronBuilderUtils';

type ScheduleFormPayload = CreateScheduleRequest | UpdateScheduleRequest;

interface ScheduleFormModalProps {
  isOpen: boolean;
  agents: Agent[];
  schedule?: AgentSchedule | null;
  isSubmitting?: boolean;
  preview?: SchedulePreviewResponse | null;
  previewLoading?: boolean;
  previewError?: string | null;
  onClose: () => void;
  onPreview: (payload: {
    scheduleType: 'once' | 'recurring';
    timezone: string;
    cronExpression?: string;
    runAt?: string;
  }) => Promise<void>;
  onSubmit: (payload: ScheduleFormPayload) => Promise<void>;
}

function getDefaultTimezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
}

function toDatetimeLocalValue(value?: string | null, timezone?: string): string {
  if (!value) {
    return '';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return '';
  }

  const formatter = new Intl.DateTimeFormat('sv-SE', {
    timeZone: timezone || undefined,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
  return formatter.format(parsed).replace(' ', 'T');
}

export const ScheduleFormModal: React.FC<ScheduleFormModalProps> = ({
  isOpen,
  agents,
  schedule,
  isSubmitting = false,
  preview,
  previewLoading = false,
  previewError,
  onClose,
  onPreview,
  onSubmit,
}) => {
  const { t } = useTranslation();
  const isEditMode = Boolean(schedule);
  const [agentId, setAgentId] = useState('');
  const [name, setName] = useState('');
  const [promptTemplate, setPromptTemplate] = useState('');
  const [scheduleType, setScheduleType] = useState<'once' | 'recurring'>('recurring');
  const [timezone, setTimezone] = useState(getDefaultTimezone());
  const [runAt, setRunAt] = useState('');
  const [rawCron, setRawCron] = useState('0 9 * * 1-5');
  const [builderState, setBuilderState] = useState<CronBuilderState>(createDefaultCronBuilderState());
  const [builderSupported, setBuilderSupported] = useState(true);
  const [validationError, setValidationError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const initialBuilderState =
      schedule?.cronExpression ? cronToBuilder(schedule.cronExpression) : createDefaultCronBuilderState();

    setAgentId(schedule?.agentId || agents[0]?.id || '');
    setName(schedule?.name || '');
    setPromptTemplate(schedule?.promptTemplate || '');
    setScheduleType(schedule?.scheduleType || 'recurring');
    setTimezone(schedule?.timezone || getDefaultTimezone());
    setRunAt(toDatetimeLocalValue(schedule?.runAtUtc, schedule?.timezone || getDefaultTimezone()));
    setRawCron(schedule?.cronExpression || builderToCron(createDefaultCronBuilderState()));
    setBuilderState(initialBuilderState || createDefaultCronBuilderState());
    setBuilderSupported(Boolean(initialBuilderState) || !schedule?.cronExpression);
    setValidationError(null);
  }, [agents, isOpen, schedule]);

  const modalTitle = isEditMode
    ? t('schedules.form.editTitle', '编辑定时任务')
    : t('schedules.form.createTitle', '新建定时任务');
  const submitLabel = isEditMode
    ? t('schedules.form.saveChanges', '保存修改')
    : t('schedules.form.createAction', '创建任务');
  const previewOccurrences = useMemo(() => preview?.next_occurrences || [], [preview]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const shouldPreview =
      timezone &&
      ((scheduleType === 'once' && Boolean(runAt)) || (scheduleType === 'recurring' && Boolean(rawCron.trim())));

    if (!shouldPreview) {
      return;
    }

    const timer = window.setTimeout(() => {
      void onPreview({
        scheduleType,
        timezone,
        cronExpression: scheduleType === 'recurring' ? rawCron.trim() : undefined,
        runAt: scheduleType === 'once' ? runAt : undefined,
      });
    }, 250);

    return () => {
      window.clearTimeout(timer);
    };
  }, [isOpen, onPreview, rawCron, runAt, scheduleType, timezone]);

  const handleBuilderChange = (nextState: CronBuilderState) => {
    setBuilderState(nextState);
    setBuilderSupported(true);
    setRawCron(builderToCron(nextState));
  };

  const handleRawCronChange = (nextCron: string) => {
    setRawCron(nextCron);
    const parsed = cronToBuilder(nextCron);
    if (parsed) {
      setBuilderState(parsed);
      setBuilderSupported(true);
      return;
    }
    setBuilderSupported(false);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();

    if (!name.trim()) {
      setValidationError(t('schedules.form.validation.nameRequired', '请输入任务名称'));
      return;
    }
    if (!agentId && !isEditMode) {
      setValidationError(t('schedules.form.validation.agentRequired', '请选择 Agent'));
      return;
    }
    if (!promptTemplate.trim()) {
      setValidationError(t('schedules.form.validation.promptRequired', '请输入执行内容'));
      return;
    }
    if (!timezone.trim()) {
      setValidationError(t('schedules.form.validation.timezoneRequired', '请输入时区'));
      return;
    }
    if (scheduleType === 'once' && !runAt) {
      setValidationError(t('schedules.form.validation.runAtRequired', '请选择执行时间'));
      return;
    }
    if (scheduleType === 'recurring' && !rawCron.trim()) {
      setValidationError(t('schedules.form.validation.cronRequired', '请输入 cron 表达式'));
      return;
    }

    setValidationError(null);

    const payload = {
      ...(isEditMode ? {} : { agentId }),
      name: name.trim(),
      promptTemplate: promptTemplate.trim(),
      scheduleType,
      cronExpression: scheduleType === 'recurring' ? rawCron.trim() : undefined,
      runAt: scheduleType === 'once' ? runAt : undefined,
      timezone: timezone.trim(),
    };

    await onSubmit(payload);
  };

  return (
    <LayoutModal
      isOpen={isOpen}
      onClose={onClose}
      closeOnBackdropClick={false}
      title={modalTitle}
      description={t(
        'schedules.form.description',
        '支持单次任务与可视化 cron 配置，复杂规则也可以直接编辑原始 cron。'
      )}
      size="4xl"
      footer={
        <div className="flex items-center justify-between gap-3">
          <div className="text-xs text-zinc-500 dark:text-zinc-400">
            {t('schedules.form.footerHint', '手动创建会自动绑定一条专属持久化会话。')}
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded-full px-4 py-2 text-sm font-semibold text-zinc-600 transition hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
            >
              {t('common.cancel', '取消')}
            </button>
            <button
              form="schedule-form"
              type="submit"
              disabled={isSubmitting}
              className="inline-flex items-center gap-2 rounded-full bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-60"
            >
              {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {submitLabel}
            </button>
          </div>
        </div>
      }
    >
      <form id="schedule-form" onSubmit={handleSubmit} className="space-y-6">
        <div className="grid gap-4 md:grid-cols-2">
          {!isEditMode ? (
            <label className="space-y-2">
              <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">
                {t('schedules.form.agent', 'Agent')}
              </span>
              <select
                aria-label={t('schedules.form.agent', 'Agent')}
                value={agentId}
                onChange={(event) => setAgentId(event.target.value)}
                className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-emerald-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
              >
                <option value="">{t('schedules.form.selectAgent', '请选择 Agent')}</option>
                {agents.map((agent) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.name}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <div className="space-y-2">
              <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">
                {t('schedules.form.agent', 'Agent')}
              </span>
              <div className="rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900/60 dark:text-zinc-200">
                {schedule?.agentName || schedule?.agentId}
              </div>
            </div>
          )}

          <label className="space-y-2">
            <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">
              {t('schedules.form.name', '名称')}
            </span>
            <input
              aria-label={t('schedules.form.name', '名称')}
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t('schedules.form.namePlaceholder', '例如：工作日报提醒')}
              className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-emerald-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
            />
          </label>
        </div>

        <label className="block space-y-2">
          <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">
            {t('schedules.form.prompt', '执行内容（Prompt）')}
          </span>
          <textarea
            aria-label={t('schedules.form.prompt', '执行内容（Prompt）')}
            value={promptTemplate}
            onChange={(event) => setPromptTemplate(event.target.value)}
            rows={5}
            placeholder={t('schedules.form.promptPlaceholder', '触发时发送给 Agent 的固定消息')}
            className="w-full rounded-3xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-emerald-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
          />
        </label>

        <div className="grid gap-4 md:grid-cols-3">
          <label className="space-y-2">
            <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">
              {t('schedules.form.scheduleType', '任务类型')}
            </span>
            <select
              aria-label={t('schedules.form.scheduleType', '任务类型')}
              value={scheduleType}
              onChange={(event) => setScheduleType(event.target.value as 'once' | 'recurring')}
              className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-emerald-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
            >
              <option value="recurring">{t('schedules.shared.types.recurring', '循环')}</option>
              <option value="once">{t('schedules.shared.types.once', '单次')}</option>
            </select>
          </label>

          <label className="space-y-2">
            <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">
              {t('schedules.form.timezone', '时区')}
            </span>
            <input
              aria-label={t('schedules.form.timezone', '时区')}
              value={timezone}
              onChange={(event) => setTimezone(event.target.value)}
              placeholder="Asia/Shanghai"
              className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-emerald-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
            />
          </label>

          {scheduleType === 'once' ? (
            <label className="space-y-2">
              <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">
                {t('schedules.form.runAt', '执行时间')}
              </span>
              <input
                aria-label={t('schedules.form.runAt', '执行时间')}
                type="datetime-local"
                value={runAt}
                onChange={(event) => setRunAt(event.target.value)}
                className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-emerald-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
              />
            </label>
          ) : (
            <div className="rounded-3xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900/60 dark:text-zinc-300">
              <p className="font-semibold text-zinc-900 dark:text-zinc-100">
                {t('schedules.shared.types.recurring', '循环')}
              </p>
              <p className="mt-1">
                {t('schedules.form.recurringHint', '可视化 builder 与高级 cron 输入会尽量保持同步。')}
              </p>
            </div>
          )}
        </div>

        {scheduleType === 'recurring' ? (
          <>
            <CronBuilder
              value={builderState}
              isSupported={builderSupported}
              onChange={handleBuilderChange}
            />

            <label className="block space-y-2">
              <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">
                {t('schedules.form.rawCron', '高级 Cron（5 段）')}
              </span>
              <input
                aria-label={t('schedules.form.rawCron', '高级 Cron（5 段）')}
                value={rawCron}
                onChange={(event) => handleRawCronChange(event.target.value)}
                placeholder="0 9 * * 1-5"
                className="w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 font-mono text-sm text-zinc-900 outline-none transition focus:border-emerald-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
              />
            </label>
          </>
        ) : null}

        <div className="rounded-3xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                {t('schedules.form.previewTitle', '预览')}
              </p>
              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                {t('schedules.form.previewSubtitle', '展示解析结果和未来 5 次执行时间。')}
              </p>
            </div>
            {previewLoading ? <Loader2 className="h-4 w-4 animate-spin text-emerald-500" /> : null}
          </div>

          {previewError ? (
            <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-300">
              {previewError}
            </p>
          ) : null}

          {preview ? (
            <div className="mt-4 space-y-3">
              <p className="text-sm text-zinc-700 dark:text-zinc-200">{preview.human_summary}</p>
              {preview.normalized_cron ? (
                <p className="text-xs font-mono text-zinc-500 dark:text-zinc-400">
                  {t('schedules.form.normalizedCron', 'normalized')}: {preview.normalized_cron}
                </p>
              ) : null}
              <div className="grid gap-2 sm:grid-cols-2">
                {previewOccurrences.map((occurrence) => (
                  <div
                    key={occurrence}
                    className="rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-xs text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-300"
                  >
                    {new Date(occurrence).toLocaleString(undefined, {
                      timeZone: timezone || undefined,
                    })}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="mt-4 text-sm text-zinc-500 dark:text-zinc-400">
              {t('schedules.form.previewEmpty', '补全时间规则后会自动预览。')}
            </p>
          )}
        </div>

        {validationError ? (
          <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-300">
            {validationError}
          </p>
        ) : null}
      </form>
    </LayoutModal>
  );
};
