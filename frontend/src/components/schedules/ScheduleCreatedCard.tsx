import React from 'react';
import { CalendarClock, MessageSquareText } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import type { ScheduleCreatedEvent } from '@/types/schedule';
import {
  formatCreatedVia,
  formatOriginSurface,
  formatScheduleDateTime,
  formatScheduleStatus,
} from './scheduleUtils';

interface ScheduleCreatedCardProps {
  event: ScheduleCreatedEvent;
}

export const ScheduleCreatedCard: React.FC<ScheduleCreatedCardProps> = ({ event }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <div className="rounded-[28px] border border-emerald-200 bg-emerald-50/70 p-5 shadow-sm dark:border-emerald-900/60 dark:bg-emerald-950/20">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-300">
            <CalendarClock className="h-4 w-4" />
            <p className="text-xs font-bold uppercase tracking-[0.18em]">
              {t('schedules.card.createdTitle', '定时任务已创建')}
            </p>
          </div>
          <h4 className="mt-2 text-lg font-semibold text-zinc-900 dark:text-zinc-100">{event.name}</h4>
          <div className="mt-3 grid gap-2 text-sm text-zinc-600 dark:text-zinc-300 md:grid-cols-2">
            <p>{t('schedules.card.status', '状态')}: {formatScheduleStatus(event.status)}</p>
            <p>
              {t('schedules.card.nextRun', '下次执行')}:{' '}
              {formatScheduleDateTime(event.next_run_at, event.timezone)}
            </p>
            <p>{t('schedules.card.timezone', '时区')}: {event.timezone}</p>
            <p>{t('schedules.card.origin', '来源')}: {formatOriginSurface(event.origin_surface)}</p>
            <p>{t('schedules.card.createdVia', '创建方式')}: {formatCreatedVia(event.created_via)}</p>
            {event.bound_conversation_title ? (
              <p>
                {t('schedules.card.boundConversation', '绑定会话')}: {event.bound_conversation_title}
              </p>
            ) : null}
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => navigate(`/schedules/${event.schedule_id}`)}
            className="inline-flex items-center gap-2 rounded-full bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700"
          >
            <CalendarClock className="h-4 w-4" />
            {t('schedules.page.viewSchedule', '查看定时任务')}
          </button>
          <button
            type="button"
            onClick={() =>
              navigate(`/workforce/${event.agent_id}/conversations/${event.bound_conversation_id}`)
            }
            className="inline-flex items-center gap-2 rounded-full border border-emerald-300 bg-white px-4 py-2 text-sm font-semibold text-emerald-700 transition hover:bg-emerald-50 dark:border-emerald-800 dark:bg-transparent dark:text-emerald-300 dark:hover:bg-emerald-950/30"
          >
            <MessageSquareText className="h-4 w-4" />
            {t('schedules.page.openConversation', '打开绑定会话')}
          </button>
        </div>
      </div>
    </div>
  );
};
