import type { MissionEvent } from '@/types/mission';

function toTimestamp(value?: string): number {
  if (!value) return 0;
  const ts = Date.parse(value);
  return Number.isFinite(ts) ? ts : 0;
}

const RUN_BOUNDARY_EVENT_TYPES = new Set(['MISSION_STARTED', 'MISSION_RETRY_REQUESTED']);

export function selectLatestMissionRunEvents(events: MissionEvent[]): MissionEvent[] {
  if (events.length === 0) return [];

  let latestStartAt = -1;
  for (const event of events) {
    if (!RUN_BOUNDARY_EVENT_TYPES.has(event.event_type)) continue;
    latestStartAt = Math.max(latestStartAt, toTimestamp(event.created_at));
  }

  if (latestStartAt < 0) {
    return events;
  }

  return events.filter((event) => toTimestamp(event.created_at) >= latestStartAt);
}
