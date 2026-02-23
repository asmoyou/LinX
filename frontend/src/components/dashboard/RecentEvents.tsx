import React from "react";
import { useTranslation } from "react-i18next";
import { MetricHint } from "@/components/dashboard/MetricHint";

interface Event {
  id: string;
  type: "success" | "error" | "info";
  eventType: string;
  message: string;
  timestamp: string;
}

interface RecentEventsProps {
  events: Event[];
  definition?: string;
}

const formatEventType = (eventType: string): string => {
  const normalized = String(eventType || "")
    .trim()
    .replaceAll("_", " ");
  if (!normalized) {
    return "INFO";
  }
  return normalized.toUpperCase();
};

export const RecentEvents: React.FC<RecentEventsProps> = ({
  events,
  definition,
}) => {
  const { t } = useTranslation();

  const getTypeDotClass = (type: Event["type"]): string => {
    if (type === "success") {
      return "bg-emerald-500";
    }
    if (type === "error") {
      return "bg-rose-500";
    }
    return "bg-blue-500";
  };

  return (
    <div className="glass-panel p-8 rounded-[32px]">
      <div className="mb-8 flex items-center gap-1.5">
        <h3 className="text-sm font-bold uppercase tracking-widest text-zinc-400">
          {t("dashboard.recentEvents", "Recent Events")}
        </h3>
        {definition && <MetricHint text={definition} />}
      </div>
      <div className="space-y-6">
        {events.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400 text-center py-4">
            {t("dashboard.noRecentEvents", "No recent events")}
          </p>
        ) : (
          events.map((event) => (
            <div key={event.id} className="flex gap-4 items-start group">
              <div className="text-[10px] font-bold text-zinc-400 dark:text-zinc-500 pt-1 w-12 uppercase">
                {event.timestamp}
              </div>
              <div
                className={`mt-1.5 h-2 w-2 rounded-full ${getTypeDotClass(event.type)}`}
              />
              <div className="flex-1">
                <div className="text-sm font-semibold text-zinc-700 dark:text-zinc-200 group-hover:text-emerald-500 transition-colors duration-300">
                  {event.message}
                </div>
                <div className="mt-1 text-[10px] font-mono tracking-wide text-zinc-400 dark:text-zinc-500">
                  {formatEventType(event.eventType)}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
