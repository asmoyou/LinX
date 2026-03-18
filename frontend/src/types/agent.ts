export type AgentSkillSummary = {
  skill_id: string;
  skill_slug: string;
  display_name: string;
  description: string;
  skill_type: string;
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
  accessLevel?: 'private' | 'team' | 'public';
  allowedKnowledge?: string[];
  allowedMemory?: string[];
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
  lastMessageAt?: string | null;
  lastMessagePreview?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface AgentConversationDetail extends AgentConversationSummary {
  latestSnapshotGeneration?: number | null;
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
  status: string;
  channelIdentity?: string | null;
  botName?: string | null;
  appId?: string | null;
  tenantKey?: string | null;
  webhookPath?: string | null;
  webhookUrl?: string | null;
  hasAppSecret: boolean;
  hasVerificationToken: boolean;
  hasEncryptKey: boolean;
}
