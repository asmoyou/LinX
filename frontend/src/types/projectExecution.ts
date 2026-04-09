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
  ready?: boolean;
  blockingDependencyCount?: number;
  openIssueCount?: number;
  latestChangeBundleStatus?: string | null;
  nextAction?: string | null;
  blockerReason?: string | null;
}

export interface TaskContract {
  id: string;
  taskId: string;
  version: number;
  goal?: string | null;
  scope: string[];
  constraints: string[];
  deliverables: string[];
  acceptanceCriteria: string[];
  assumptions: string[];
  evidenceRequired: string[];
  allowedSurface?: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface TaskDependency {
  id: string;
  projectTaskId: string;
  dependsOnTaskId: string;
  dependsOnTaskTitle?: string | null;
  dependsOnTaskStatus?: string | null;
  requiredState: string;
  dependencyType: string;
  artifactSelector?: Record<string, unknown>;
  satisfied: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface TaskHandoff {
  id: string;
  taskId: string;
  runId?: string | null;
  nodeId?: string | null;
  stage: string;
  fromActor: string;
  toActor?: string | null;
  statusFrom?: string | null;
  statusTo?: string | null;
  title?: string | null;
  summary: string;
  payload?: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface TaskChangeBundle {
  id: string;
  taskId: string;
  runId?: string | null;
  nodeId?: string | null;
  bundleKind: string;
  status: string;
  baseRef?: string | null;
  headRef?: string | null;
  summary?: string | null;
  commitCount: number;
  changedFiles: Array<Record<string, unknown>>;
  artifactManifest?: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface TaskEvidenceBundle {
  id: string;
  taskId: string;
  runId?: string | null;
  nodeId?: string | null;
  summary: string;
  status: string;
  bundle?: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface TaskReviewIssue {
  id: string;
  taskId: string;
  changeBundleId?: string | null;
  evidenceBundleId?: string | null;
  handoffId?: string | null;
  issueKey?: string | null;
  severity: string;
  category: string;
  acceptanceRef?: string | null;
  summary: string;
  suggestion?: string | null;
  status: string;
  resolvedAt?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ExecutionAttempt {
  id: string;
  taskId: string;
  status: PlatformStatus;
  createdAt: string;
  startedAt?: string | null;
  completedAt?: string | null;
  triggerSource: string;
  executionMode?: string | null;
  currentStepTitle?: string | null;
  failureReason?: string | null;
  totalNodes: number;
  completedNodes: number;
  activeRuntimeSessions: number;
}

export interface ExecutionAttemptNode {
  id: string;
  runId: string;
  taskId?: string | null;
  name: string;
  nodeType: string;
  status: PlatformStatus;
  sequenceNumber: number;
  executionMode?: string | null;
  executorKind?: string | null;
  runtimeType?: string | null;
  suggestedAgentIds?: string[];
  dependencyStepIds?: string[];
  nodePayload?: Record<string, unknown>;
  resultPayload?: Record<string, unknown>;
  errorMessage?: string | null;
  startedAt?: string | null;
  completedAt?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface RuntimeSession {
  id: string;
  runId: string;
  nodeId?: string | null;
  sessionType: string;
  status: PlatformStatus;
  runtimeType?: string | null;
  agentId?: string | null;
  bindingId?: string | null;
  workspaceRoot?: string | null;
  metadata?: Record<string, unknown>;
  createdAt: string;
  startedAt?: string | null;
  completedAt?: string | null;
  updatedAt?: string | null;
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
  projectWorkspaceRoot?: string | null;
  configuration?: Record<string, unknown>;
  tasks: ProjectTaskSummary[];
  runs: RunSummary[];
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
  executionMode?: string | null;
  plannerSource?: string | null;
  plannerSummary?: string | null;
  stepTotal?: number;
  completedStepCount?: number;
  activeStepCount?: number;
  parallelGroupCount?: number;
  currentStepTitle?: string | null;
  suggestedAgentIds?: string[];
  clarificationQuestions?: Array<{ question: string; importance?: string }>;
  acceptanceCriteria?: string | null;
  assignedSkillNames: string[];
  latestResult?: string | null;
  contract?: TaskContract | null;
  dependencies?: TaskDependency[];
  handoffs?: TaskHandoff[];
  latestChangeBundle?: TaskChangeBundle | null;
  latestEvidenceBundle?: TaskEvidenceBundle | null;
  reviewIssues?: TaskReviewIssue[];
  openIssueCount?: number;
  attempts?: ExecutionAttempt[];
  metadata: ProjectTaskMetadataItem[];
  events: ProjectActivityItem[];
}

export interface RunSummary {
  id: string;
  projectId: string;
  projectTitle: string;
  status: PlatformStatus;
  createdAt: string;
  triggerSource: string;
  executionMode?: string | null;
  plannerSource?: string | null;
  plannerSummary?: string | null;
  stepTotal?: number;
  completedStepCount?: number;
  activeStepCount?: number;
  parallelGroupCount?: number;
  currentStepTitle?: string | null;
  suggestedAgentIds?: string[];
  needsClarification?: boolean;
  clarificationQuestions?: Array<{ question: string; importance?: string }>;
  taskId?: string | null;
  taskTitle?: string | null;
  failureReason?: string | null;
  handledAt?: string | null;
  handledSignature?: string | null;
  alertSignature?: string | null;
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
    nodeId?: string | null;
    selectionReason?: string | null;
    provisionedAgent?: boolean;
    runtimeType?: string | null;
  } | null;
  externalDispatches?: ExternalAgentDispatch[];
  nodes?: ExecutionAttemptNode[];
  runtimeSessions?: RuntimeSession[];
}

export interface ExternalAgentDispatch {
  id: string;
  agentId: string;
  bindingId: string;
  projectId: string;
  runId: string;
  nodeId: string;
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
