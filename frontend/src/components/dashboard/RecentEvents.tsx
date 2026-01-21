import React from 'react';

interface Event {
  id: string;
  type: 'success' | 'error' | 'info';
  message: string;
  timestamp: string;
}

interface RecentEventsProps {
  events: Event[];
}

export const RecentEvents: React.FC<RecentEventsProps> = ({ events }) => {
  return (
    <div className="glass-panel p-8 rounded-[32px]">
      <h3 className="text-sm font-bold uppercase tracking-widest text-zinc-400 mb-8">
        Recent Events
      </h3>
      <div className="space-y-6">
        {events.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400 text-center py-4">
            No recent events
          </p>
        ) : (
          events.map((event) => (
            <div key={event.id} className="flex gap-4 items-start group">
              <div className="text-[10px] font-bold text-zinc-400 dark:text-zinc-500 pt-1 w-8 uppercase">
                {event.timestamp}
              </div>
              <div className="flex-1">
                <div className="text-sm font-semibold text-zinc-700 dark:text-zinc-200 group-hover:text-emerald-500 transition-colors duration-300">
                  {event.message}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
