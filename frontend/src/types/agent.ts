export type AgentSkillSummary = {
  skill_id: string;
  skill_slug: string;
  display_name: string;
  description: string;
  skill_type: string;
  artifact_kind?: string | null;
  runtime_mode?: string | null;
  active_revision_id?: string | null;
  version: string;
  access_level: 'private' | 'team' | 'public';
  department_id?: string | null;
  department_name?: string | null;
};

export type Agent = {
  id: string;
  name: string;
  type: string;
  avatar?: string;
  status: 'working' | 'idle' | 'offline';
  currentTask?: string;
  tasksExecuted?: number;
  tasksCompleted: number;
  tasksFailed?: number;
  completionRate?: number;
  uptime: string;
  systemPrompt?: string;
  skill_ids?: string[];
  skill_summaries?: AgentSkillSummary[];
  model?: string;
  provider?: string;
  temperature?: number;
  maxTokens?: number;
  topP?: number;
  departmentId?: string;
  departmentName?: string | null;
  accessLevel?: 'private' | 'department' | 'public' | 'team';
  allowedKnowledge?: string[];
  ownerUserId: string;
  ownerUsername?: string | null;
  isOwned?: boolean;
  canManage?: boolean;
  canExecute?: boolean;
  topK?: number;
  similarityThreshold?: number;
  createdAt?: string;
  updatedAt?: string;
};

export interface AgentConversationSummary {
  id: string;
  agentId: string;
  ownerUserId: string;
  title: string;
  status: string;
  source: 'web' | 'feishu';
  latestSnapshotId?: string | null;
  latestSnapshotStatus?: string | null;
  storageTier?: 'hot' | 'compacted' | 'archived' | string;
  archivedAt?: string | null;
  deleteAfter?: string | null;
  workspaceBytes?: number;
  workspaceFileCount?: number;
  compactedMessageCount?: number;
  lastMessageAt?: string | null;
  lastMessagePreview?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface AgentConversationDetail extends AgentConversationSummary {
  latestSnapshotGeneration?: number | null;
}

export interface AgentConversationHistorySummary {
  summaryText: string;
  summaryJson?: Record<string, string[]> | null;
  rawMessageCount: number;
  coversUntilMessageId?: string | null;
  coversUntilCreatedAt?: string | null;
}

export interface ConversationMessage {
  id: string;
  conversationId: string;
  role: 'user' | 'assistant' | 'system';
  contentText: string;
  contentJson?: Record<string, any> | null;
  attachments: Array<Record<string, any>>;
  source: 'web' | 'feishu';
  externalEventId?: string | null;
  createdAt: string;
}

export interface FeishuPublicationConfig {
  publicationId?: string | null;
  channelType: 'feishu';
  deliveryMode: 'long_connection';
  status: string;
  channelIdentity?: string | null;
  appId?: string | null;
  hasAppSecret: boolean;
  connectionState: 'inactive' | 'connecting' | 'connected' | 'error' | string;
  connectionStatusUpdatedAt?: string | null;
  lastConnectedAt?: string | null;
  lastEventAt?: string | null;
  lastErrorAt?: string | null;
  lastErrorMessage?: string | null;
}
