export type ProjectExecutionSection =
  | 'projects'
  | 'projectDetail'
  | 'projectTaskDetail'
  | 'runs'
  | 'runDetail'
  | 'skillHub'
  | 'extensions';

export type PlatformStatus =
  | 'draft'
  | 'planning'
  | 'queued'
  | 'assigned'
  | 'scheduled'
  | 'running'
  | 'blocked'
  | 'reviewing'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'working'
  | 'idle'
  | 'offline'
  | 'connected'
  | 'disconnected'
  | 'error'
  | 'syncing'
  | string;

export type ActivityLevel = 'info' | 'success' | 'warning' | 'error';

export interface ProjectActivityItem {
  id: string;
  title: string;
  description: string;
  timestamp: string;
  level: ActivityLevel;
  actor?: string | null;
  taskId?: string | null;
}

export interface ProjectTaskSummary {
  id: string;
  title: string;
  status: PlatformStatus;
  priority: number;
  updatedAt: string;
  assignedAgentId?: string | null;
  assignedAgentName?: string | null;
  dependencyIds: string[];
  reviewStatus?: string | null;
}

export interface ProjectAgentSummary {
  id: string;
  name: string;
  role: string;
  status: PlatformStatus;
  isTemporary: boolean;
  avatar?: string | null;
  assignedAt?: string | null;
}

export interface ProjectAgentBinding {
  id: string;
  projectId: string;
  agentId: string;
  agentName: string;
  agentType?: string | null;
  roleHint?: string | null;
  priority: number;
  status: PlatformStatus;
  allowedStepKinds: string[];
  preferredSkills: string[];
  preferredRuntimeTypes: string[];
  createdAt: string;
  updatedAt: string;
}

export interface AgentProvisioningProfile {
  id: string;
  projectId: string;
  stepKind: string;
  agentType: string;
  templateId?: string | null;
  defaultSkillIds: string[];
  defaultProvider?: string | null;
  defaultModel?: string | null;
  runtimeType: string;
  preferredNodeSelector?: string | null;
  sandboxMode: string;
  ephemeral: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface ProjectDeliverable {
  filename: string;
  path: string;
  size: number;
  downloadUrl?: string | null;
  isTarget: boolean;
  sourceScope?: string | null;
}

export interface ProjectSummary {
  id: string;
  title: string;
  summary: string;
  status: PlatformStatus;
  progress: number;
  createdAt: string;
  updatedAt: string;
  startedAt?: string | null;
  completedAt?: string | null;
  totalTasks: number;
  completedTasks: number;
  failedTasks: number;
  activeNodeCount?: number;
  needsClarification: boolean;
  latestSignal?: string | null;
}

export interface ProjectDetail extends ProjectSummary {
  instructions: string;
  departmentId?: string | null;
  workspaceBucket?: string | null;
  configuration?: Record<string, unknown>;
  tasks: ProjectTaskSummary[];
  agents: ProjectAgentSummary[];
  deliverables: ProjectDeliverable[];
  recentActivity: ProjectActivityItem[];
  agentBindings?: ProjectAgentBinding[];
  provisioningProfiles?: AgentProvisioningProfile[];
}

export interface ProjectTaskMetadataItem {
  label: string;
  value: string;
}

export interface ProjectTaskDetail extends ProjectTaskSummary {
  projectId: string;
  projectTitle: string;
  projectStatus: PlatformStatus;
  description: string;
  acceptanceCriteria?: string | null;
  assignedSkillNames: string[];
  latestResult?: string | null;
  metadata: ProjectTaskMetadataItem[];
  events: ProjectActivityItem[];
}

export interface RunSummary {
  id: string;
  projectId: string;
  projectTitle: string;
  status: PlatformStatus;
  startedAt?: string | null;
  completedAt?: string | null;
  updatedAt: string;
  totalTasks: number;
  completedTasks: number;
  failedTasks: number;
  externalAgentCount?: number;
  latestSignal?: string | null;
}

export interface RunDetail extends RunSummary {
  projectSummary: string;
  timeline: ProjectActivityItem[];
  deliverables: ProjectDeliverable[];
  runWorkspaceRoot?: string | null;
  executorAssignment?: {
    executorKind?: string | null;
    agentId?: string | null;
    selectionReason?: string | null;
    provisionedAgent?: boolean;
    runtimeType?: string | null;
  } | null;
  externalDispatches?: ExternalAgentDispatch[];
}

export interface ExternalAgentDispatch {
  id: string;
  agentId: string;
  bindingId: string;
  projectId: string;
  runId: string;
  runStepId: string;
  sourceType: string;
  sourceId: string;
  runtimeType: string;
  status: PlatformStatus;
  errorMessage?: string | null;
  requestPayload?: Record<string, unknown>;
  resultPayload?: Record<string, unknown>;
  ackedAt?: string | null;
  startedAt?: string | null;
  completedAt?: string | null;
  expiresAt?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface SkillHubOverview {
  totalSkills: number;
  activeSkills: number;
  candidateCount: number;
  bindingCount: number;
  storeItems: number;
}

export interface SkillHubSkillItem {
  id: string;
  name: string;
  description: string;
  type: string;
  executionCount: number;
  accessLevel: string;
  lastExecutedAt?: string | null;
}

export interface SkillHubCandidateItem {
  id: string;
  title: string;
  summary: string;
  status: string;
  sourceAgentName?: string | null;
  createdAt: string;
}

export interface SkillHubBindingItem {
  id: string;
  ownerName: string;
  ownerType: string;
  skillName: string;
  skillSlug: string;
  bindingMode?: string | null;
  enabled: boolean;
  updatedAt?: string | null;
}

export interface SkillHubSnapshot {
  overview: SkillHubOverview;
  featuredSkills: SkillHubSkillItem[];
  pendingCandidates: SkillHubCandidateItem[];
  recentBindings: SkillHubBindingItem[];
}

export interface PlatformExtension {
  id: string;
  name: string;
  description?: string | null;
  status: PlatformStatus;
  transport: string;
  toolCount: number;
  isActive: boolean;
  endpoint?: string | null;
  lastConnectedAt?: string | null;
  lastSyncAt?: string | null;
  errorMessage?: string | null;
}

export interface PlatformQueryResult<T> {
  data: T;
  fallback: boolean;
  error?: string | null;
}
