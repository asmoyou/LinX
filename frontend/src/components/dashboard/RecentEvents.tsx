import React from 'react';
import { Clock, CheckCircle, AlertCircle, Info } from 'lucide-react';
import { GlassPanel } from '@/components/GlassPanel';

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
  const getIcon = (type: Event['type']) => {
    switch (type) {
      case 'success':
        return <CheckCircle className="w-5 h-5 text-green-500" />;
      case 'error':
        return <AlertCircle className="w-5 h-5 text-red-500" />;
      case 'info':
        return <Info className="w-5 h-5 text-blue-500" />;
    }
  };

  return (
    <GlassPanel>
      <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-4">
        Recent Events
      </h3>
      <div className="space-y-3 max-h-96 overflow-y-auto">
        {events.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
            No recent events
          </p>
        ) : (
          events.map((event) => (
            <div
              key={event.id}
              className="flex items-start gap-3 p-3 rounded-lg hover:bg-white/10 transition-colors"
            >
              {getIcon(event.type)}
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-700 dark:text-gray-300">{event.message}</p>
                <div className="flex items-center gap-1 mt-1 text-xs text-gray-500 dark:text-gray-400">
                  <Clock className="w-3 h-3" />
                  <span>{event.timestamp}</span>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </GlassPanel>
  );
};
