import React from "react";
import { CalendarClock } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import {
  formatScheduleDateTime,
  formatScheduleStatus,
} from "@/components/schedules/scheduleUtils";
import type { ScheduleCreatedEvent } from "@/types/schedule";

interface PersistentConversationScheduleCardProps {
  event: ScheduleCreatedEvent;
}

export const PersistentConversationScheduleCard: React.FC<
  PersistentConversationScheduleCardProps
> = ({ event }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <div className="rounded-[22px] border border-emerald-200 bg-emerald-50/70 p-4 shadow-sm dark:border-emerald-900/50 dark:bg-emerald-950/20">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-300">
            <CalendarClock className="h-4 w-4" />
            <span className="text-[11px] font-semibold uppercase tracking-[0.16em]">
              {t("agent.persistentResult.schedules", "定时任务")}
            </span>
          </div>
          <p className="mt-2 truncate text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            {event.name}
          </p>
          <div className="mt-2 space-y-1 text-xs text-zinc-600 dark:text-zinc-300">
            <p>
              {t("schedules.card.status", "状态")}: {formatScheduleStatus(event.status)}
            </p>
            <p>
              {t("schedules.card.nextRun", "下次执行")}:{" "}
              {formatScheduleDateTime(event.next_run_at, event.timezone)}
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => navigate(`/schedules/${event.schedule_id}`)}
          className="inline-flex shrink-0 items-center gap-2 rounded-full bg-emerald-600 px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-emerald-700"
        >
          <CalendarClock className="h-3.5 w-3.5" />
          {t("schedules.page.viewSchedule", "查看定时任务")}
        </button>
      </div>
    </div>
  );
};
