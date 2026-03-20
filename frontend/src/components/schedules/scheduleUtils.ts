import i18n from '@/i18n/config';
import type { AgentSchedule, ScheduleCreatedEvent, ScheduleRun } from '@/types/schedule';

export function formatScheduleDateTime(value?: string | null, timezone?: string): string {
  if (!value) {
    return i18n.t('schedules.shared.notSet', '未设置');
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString(undefined, timezone ? { timeZone: timezone } : undefined);
}

export function formatScheduleType(value?: string | null): string {
  switch (String(value || '').trim()) {
    case 'once':
      return i18n.t('schedules.shared.types.once', '单次');
    case 'recurring':
      return i18n.t('schedules.shared.types.recurring', '循环');
    default:
      return value || '-';
  }
}

export function formatScheduleStatus(value?: string | null): string {
  switch (String(value || '').trim()) {
    case 'active':
      return i18n.t('schedules.shared.status.active', '运行中');
    case 'paused':
      return i18n.t('schedules.shared.status.paused', '已暂停');
    case 'completed':
      return i18n.t('schedules.shared.status.completed', '已完成');
    case 'failed':
      return i18n.t('schedules.shared.status.failed', '失败');
    default:
      return value || '-';
  }
}

export function formatCreatedVia(value?: string | null): string {
  switch (String(value || '').trim()) {
    case 'manual_ui':
      return i18n.t('schedules.shared.createdVia.manual', '手动创建');
    case 'agent_auto':
      return i18n.t('schedules.shared.createdVia.agent', 'Agent 自动创建');
    default:
      return value || '-';
  }
}

export function formatOriginSurface(value?: string | null): string {
  switch (String(value || '').trim()) {
    case 'persistent_chat':
      return i18n.t('schedules.shared.origin.persistent', '持久化会话');
    case 'test_chat':
      return i18n.t('schedules.shared.origin.testChat', '测试聊天');
    case 'feishu':
      return i18n.t('schedules.shared.origin.feishu', '飞书');
    case 'schedule_page':
      return i18n.t('schedules.shared.origin.schedulePage', '定时任务页');
    default:
      return value || '-';
  }
}

export function formatRunStatus(value?: string | null): string {
  switch (String(value || '').trim()) {
    case 'queued':
      return i18n.t('schedules.shared.runStatus.queued', '排队中');
    case 'running':
      return i18n.t('schedules.shared.runStatus.running', '执行中');
    case 'succeeded':
      return i18n.t('schedules.shared.runStatus.succeeded', '成功');
    case 'failed':
      return i18n.t('schedules.shared.runStatus.failed', '失败');
    case 'skipped':
      return i18n.t('schedules.shared.runStatus.skipped', '跳过');
    default:
      return value || '-';
  }
}

export function describeScheduleTiming(
  schedule: Pick<AgentSchedule, 'scheduleType' | 'cronExpression' | 'runAtUtc' | 'timezone'>
): string {
  if (schedule.scheduleType === 'once') {
    return schedule.runAtUtc
      ? `${i18n.t('schedules.shared.types.once', '单次')} · ${formatScheduleDateTime(
          schedule.runAtUtc,
          schedule.timezone
        )}`
      : i18n.t('schedules.shared.types.once', '单次');
  }
  return schedule.cronExpression || '-';
}

export function normalizeScheduleCreatedEvent(rawEvent: unknown): ScheduleCreatedEvent | null {
  if (!rawEvent || typeof rawEvent !== 'object') {
    return null;
  }

  const payload = rawEvent as Record<string, unknown>;
  const scheduleId = String(payload.schedule_id || payload.scheduleId || '').trim();
  const agentId = String(payload.agent_id || payload.agentId || '').trim();
  const name = String(payload.name || '').trim();
  const timezone = String(payload.timezone || '').trim();
  const boundConversationId = String(
    payload.bound_conversation_id || payload.boundConversationId || ''
  ).trim();

  if (!scheduleId || !agentId || !name || !timezone || !boundConversationId) {
    return null;
  }

  return {
    schedule_id: scheduleId,
    agent_id: agentId,
    name,
    status: String(payload.status || '').trim() || 'active',
    next_run_at: payload.next_run_at
      ? String(payload.next_run_at)
      : payload.nextRunAt
        ? String(payload.nextRunAt)
        : null,
    timezone,
    created_via: String(payload.created_via || payload.createdVia || '').trim() || 'agent_auto',
    bound_conversation_id: boundConversationId,
    bound_conversation_title: payload.bound_conversation_title
      ? String(payload.bound_conversation_title)
      : payload.boundConversationTitle
        ? String(payload.boundConversationTitle)
        : null,
    origin_surface:
      String(payload.origin_surface || payload.originSurface || '').trim() || 'persistent_chat',
  };
}

export function mergeScheduleEvents(
  currentEvents: ScheduleCreatedEvent[] | undefined,
  rawEvents: unknown
): ScheduleCreatedEvent[] | undefined {
  const base = Array.isArray(currentEvents) ? [...currentEvents] : [];
  const incoming = Array.isArray(rawEvents)
    ? rawEvents.map(normalizeScheduleCreatedEvent).filter(Boolean)
    : [];
  const deduped = new Map<string, ScheduleCreatedEvent>();

  [...base, ...(incoming as ScheduleCreatedEvent[])].forEach((event) => {
    deduped.set(event.schedule_id, event);
  });

  return deduped.size > 0 ? [...deduped.values()] : undefined;
}

export function latestRunSummary(run?: ScheduleRun | null): string {
  if (!run) {
    return i18n.t('schedules.page.noRunsYet', '暂无执行');
  }
  const status = formatRunStatus(run.status);
  if (run.errorMessage) {
    return `${status}: ${run.errorMessage}`;
  }
  if (run.skipReason) {
    return `${status}: ${run.skipReason}`;
  }
  return status;
}

export function summarizePrompt(value?: string | null, maxLength = 72): string {
  const normalized = String(value || '').replace(/\s+/g, ' ').trim();
  if (!normalized) {
    return i18n.t('schedules.page.noPrompt', '未设置执行内容');
  }
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, Math.max(0, maxLength - 1)).trimEnd()}…`;
}
