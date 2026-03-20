export type ScheduleType = 'once' | 'recurring';
export type ScheduleStatus = 'active' | 'paused' | 'completed' | 'failed';
export type ScheduleCreatedVia = 'manual_ui' | 'agent_auto';
export type ScheduleOriginSurface =
  | 'persistent_chat'
  | 'test_chat'
  | 'feishu'
  | 'schedule_page';
export type ScheduleRunStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'skipped';

export interface ScheduleRun {
  id: string;
  scheduleId: string;
  scheduledFor?: string | null;
  startedAt?: string | null;
  completedAt?: string | null;
  status: ScheduleRunStatus | string;
  skipReason?: string | null;
  errorMessage?: string | null;
  assistantMessageId?: string | null;
  conversationId?: string | null;
  deliveryChannel: 'web' | 'feishu' | string;
  createdAt?: string | null;
}

export interface AgentSchedule {
  id: string;
  ownerUserId: string;
  ownerUsername?: string | null;
  agentId: string;
  agentName?: string | null;
  boundConversationId: string;
  boundConversationTitle?: string | null;
  boundConversationSource?: 'web' | 'feishu' | string | null;
  name: string;
  promptTemplate: string;
  scheduleType: ScheduleType;
  cronExpression?: string | null;
  runAtUtc?: string | null;
  timezone: string;
  status: ScheduleStatus | string;
  createdVia: ScheduleCreatedVia | string;
  originSurface: ScheduleOriginSurface | string;
  originMessageId?: string | null;
  nextRunAt?: string | null;
  lastRunAt?: string | null;
  lastRunStatus?: ScheduleRunStatus | string | null;
  lastError?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
  latestRun?: ScheduleRun | null;
}

export interface ScheduleCreatedEvent {
  schedule_id: string;
  agent_id: string;
  name: string;
  status: string;
  next_run_at?: string | null;
  timezone: string;
  created_via: string;
  bound_conversation_id: string;
  bound_conversation_title?: string | null;
  origin_surface: string;
}

export interface ScheduleListResponse {
  items: AgentSchedule[];
  total: number;
}

export interface ScheduleRunListResponse {
  items: ScheduleRun[];
  total: number;
}

export interface SchedulePreviewRequest {
  scheduleType: ScheduleType;
  timezone: string;
  cronExpression?: string;
  runAt?: string;
}

export interface SchedulePreviewResponse {
  is_valid: boolean;
  human_summary: string;
  normalized_cron?: string | null;
  next_occurrences: string[];
}

export interface CreateScheduleRequest {
  agentId: string;
  name: string;
  promptTemplate: string;
  scheduleType: ScheduleType;
  cronExpression?: string;
  runAt?: string;
  timezone?: string;
}

export interface UpdateScheduleRequest {
  name?: string;
  promptTemplate?: string;
  scheduleType?: ScheduleType;
  cronExpression?: string;
  runAt?: string;
  timezone?: string;
}

export interface ScheduleCreateResponse {
  schedule: AgentSchedule;
  createdEvent: ScheduleCreatedEvent;
}

export interface ScheduleListFilters {
  scope?: 'mine' | 'all';
  status?: 'all' | ScheduleStatus;
  type?: 'all' | ScheduleType;
  createdVia?: 'all' | ScheduleCreatedVia;
  agentId?: string;
  query?: string;
  limit?: number;
  offset?: number;
}
