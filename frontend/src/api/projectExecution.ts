import apiClient, { type RequestConfigWithMeta } from './client';
import { agentsApi, type AgentSessionWorkspaceFile } from './agents';
import { skillsApi } from './skills';
import type { ProjectExecutionMode } from '@/utils/projectExecutionPlanning';
import type {
  PlatformExtension,
  PlatformQueryResult,
  ProjectActivityItem,
  AgentProvisioningProfile,
  ProjectAgentBinding,
  ProjectDeliverable,
  ProjectDetail,
  ProjectSummary,
  ProjectTaskDetail,
  ProjectTaskMetadataItem,
  ProjectTaskSummary,
  RunDetail,
  RunSummary,
  SkillHubBindingItem,
  SkillHubCandidateItem,
  SkillHubOverview,
  SkillHubSkillItem,
  SkillHubSnapshot,
} from '@/types/projectExecution';

type SkeletonProjectRecord = {
  project_id: string;
  name: string;
  description?: string | null;
  status: string;
  configuration: Record<string, unknown>;
  created_by_user_id: string;
  created_at: string;
  updated_at: string;
};

type SkeletonPlanRecord = {
  plan_id: string;
  project_id: string;
  name: string;
  goal?: string | null;
  status: string;
  version: number;
  definition: Record<string, unknown>;
  created_by_user_id: string;
  created_at: string;
  updated_at: string;
};

type SkeletonProjectTaskRecord = {
  project_task_id: string;
  project_id: string;
  plan_id?: string | null;
  run_id?: string | null;
  assignee_agent_id?: string | null;
  title: string;
  description?: string | null;
  status: string;
  priority: string;
  sort_order: number;
  input_payload: Record<string, unknown>;
  output_payload: Record<string, unknown>;
  error_message?: string | null;
  created_by_user_id: string;
  created_at: string;
  updated_at: string;
};

type SkeletonRunRecord = {
  run_id: string;
  project_id: string;
  plan_id?: string | null;
  status: string;
  trigger_source: string;
  runtime_context: Record<string, unknown>;
  error_message?: string | null;
  requested_by_user_id: string;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
};

type SkeletonRunStepRecord = {
  run_step_id: string;
  run_id: string;
  project_task_id?: string | null;
  node_id?: string | null;
  name: string;
  step_type: string;
  status: string;
  sequence_number: number;
  input_payload: Record<string, unknown>;
  output_payload: Record<string, unknown>;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
};

type SkeletonTaskLaunchBundleRecord = {
  task: SkeletonProjectTaskRecord;
  plan?: SkeletonPlanRecord | null;
  run?: SkeletonRunRecord | null;
  step?: SkeletonRunStepRecord | null;
  needs_clarification?: boolean;
  clarification_questions?: Array<{ question: string; importance?: string }>;
};

type SkeletonProjectSpaceRecord = {
  project_space_id: string;
  project_id: string;
  storage_uri?: string | null;
  branch_name?: string | null;
  status: string;
  root_path?: string | null;
  space_metadata: Record<string, unknown>;
  last_synced_at?: string | null;
  created_at: string;
  updated_at: string;
};

type SkeletonProjectAgentBindingRecord = {
  binding_id: string;
  project_id: string;
  agent_id: string;
  role_hint?: string | null;
  priority: number;
  status: string;
  allowed_step_kinds: string[];
  preferred_skills: string[];
  preferred_runtime_types: string[];
  created_at: string;
  updated_at: string;
};

type SkeletonAgentProvisioningProfileRecord = {
  profile_id: string;
  project_id: string;
  step_kind: string;
  agent_type: string;
  template_id?: string | null;
  default_skill_ids: string[];
  default_provider?: string | null;
  default_model?: string | null;
  runtime_type: string;
  sandbox_mode: string;
  ephemeral: boolean;
  created_at: string;
  updated_at: string;
};

type SkeletonRunSchedulingRecord = {
  run: SkeletonRunRecord;
  executor_assignment?: {
    executor_kind?: string | null;
    agent_id?: string | null;
    node_id?: string | null;
    selection_reason?: string | null;
    provisioned_agent?: boolean;
  } | null;
  run_workspace?: {
    workspace_id: string;
    root_path: string;
    sandbox_mode: string;
  } | null;
};

type SkeletonExternalAgentDispatchRecord = {
  dispatch_id: string;
  agent_id: string;
  binding_id: string;
  project_id?: string | null;
  run_id?: string | null;
  run_step_id?: string | null;
  source_type: string;
  source_id: string;
  runtime_type: string;
  request_payload: Record<string, unknown>;
  result_payload: Record<string, unknown>;
  status: string;
  error_message?: string | null;
  acked_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  expires_at?: string | null;
  created_at: string;
  updated_at: string;
};

type SkeletonExtensionRecord = {
  extension_package_id: string;
  project_id: string;
  name: string;
  package_type: string;
  source_uri?: string | null;
  status: string;
  manifest: Record<string, unknown>;
  installed_by_user_id: string;
  created_at: string;
  updated_at: string;
};

type SeedTask = {
  id: string;
  title: string;
  status: string;
  priority: number;
  assignedAgentId?: string;
  assignedAgentName?: string;
  dependencies?: string[];
  acceptanceCriteria?: string;
  assignedSkillNames?: string[];
  result?: string;
  metadata?: ProjectTaskMetadataItem[];
};

type SeedAgent = {
  id: string;
  name: string;
  role: string;
  status: string;
  isTemporary?: boolean;
  assignedAt?: string;
};

type SeedProject = {
  id: string;
  title: string;
  summary: string;
  instructions: string;
  status: string;
  createdAt: string;
  updatedAt: string;
  runCreatedAt: string;
  runTriggerSource: string;
  startedAt?: string;
  completedAt?: string;
  totalTasks: number;
  completedTasks: number;
  failedTasks: number;
  tasks: SeedTask[];
  agents: SeedAgent[];
  deliverables: ProjectDeliverable[];
  projectActivity: ProjectActivityItem[];
  runTimeline: ProjectActivityItem[];
};

const now = Date.now();
const ENABLE_PROJECT_EXECUTION_SEEDS = import.meta.env.VITE_ENABLE_PROJECT_EXECUTION_SEEDS === 'true';
const isoMinutesAgo = (minutes: number): string =>
  new Date(now - minutes * 60 * 1000).toISOString();

const fallbackSeedProjects: SeedProject[] = [
  {
    id: 'project-launchpad-shell',
    title: 'Launchpad Workspace Rollout',
    summary: 'Coordinate staging hardening, release automation, and launch content for the new workspace shell.',
    instructions:
      'Deliver the first production-ready workspace shell, harden release automation, and align content for the launch window.',
    status: 'running',
    createdAt: isoMinutesAgo(7200),
    updatedAt: isoMinutesAgo(14),
    runCreatedAt: isoMinutesAgo(6402),
    runTriggerSource: 'manual',
    startedAt: isoMinutesAgo(6400),
    totalTasks: 5,
    completedTasks: 3,
    failedTasks: 0,
    tasks: [
      {
        id: 'task-release-checklist',
        title: 'Finalize rollout checklist',
        status: 'completed',
        priority: 3,
        assignedAgentId: 'node-release-lead',
        assignedAgentName: 'Release Lead',
        acceptanceCriteria: 'Checklist covers release, rollback, comms, and observability owners.',
        assignedSkillNames: ['Release Planning', 'Risk Review'],
        result: 'Checklist approved by release and platform owners.',
        metadata: [{ label: 'Review status', value: 'Approved' }],
      },
      {
        id: 'task-staging-bake',
        title: 'Run staging bake and smoke suite',
        status: 'running',
        priority: 2,
        assignedAgentId: 'node-platform-ops',
        assignedAgentName: 'Platform Ops',
        dependencies: ['task-release-checklist'],
        acceptanceCriteria: 'Smoke suite passes with deployment, auth, and notifications flows.',
        assignedSkillNames: ['CI Diagnostics', 'Canary Analysis'],
        result: 'Smoke suite is 80% complete with no blockers.',
        metadata: [{ label: 'Owner lane', value: 'Operations' }],
      },
      {
        id: 'task-launch-copy',
        title: 'Publish launch narrative and internal FAQ',
        status: 'planning',
        priority: 1,
        assignedAgentId: 'node-ops-comms',
        assignedAgentName: 'Ops Comms',
        dependencies: ['task-release-checklist'],
        acceptanceCriteria: 'FAQ reflects launch scope, ownership, and escalation routes.',
        assignedSkillNames: ['Technical Writing'],
      },
    ],
    agents: [
      {
        id: 'node-release-lead',
        name: 'Release Lead',
        role: 'leader',
        status: 'working',
        assignedAt: isoMinutesAgo(6000),
      },
      {
        id: 'node-platform-ops',
        name: 'Platform Ops',
        role: 'worker',
        status: 'working',
        assignedAt: isoMinutesAgo(1200),
      },
      {
        id: 'node-ops-comms',
        name: 'Ops Comms',
        role: 'qa',
        status: 'idle',
        assignedAt: isoMinutesAgo(400),
      },
    ],
    deliverables: [
      {
        filename: 'launchpad-rollout-checklist.md',
        path: 'shared/launchpad-rollout-checklist.md',
        size: 48_200,
        isTarget: true,
        sourceScope: 'shared',
      },
    ],
    projectActivity: [
      {
        id: 'activity-1',
        title: 'Smoke suite extended',
        description: 'Platform Ops added notification-center coverage to the staging bake.',
        timestamp: isoMinutesAgo(14),
        level: 'info' as const,
        actor: 'Platform Ops',
        taskId: 'task-staging-bake',
      },
      {
        id: 'activity-2',
        title: 'Checklist approved',
        description: 'Release checklist signed off and marked ready for the launch review.',
        timestamp: isoMinutesAgo(65),
        level: 'success',
        actor: 'Release Lead',
        taskId: 'task-release-checklist',
      },
    ],
    runTimeline: [
      {
        id: 'run-activity-1',
        title: 'Run created',
        description: 'Triggered manually from the project shell.',
        timestamp: isoMinutesAgo(6402),
        level: 'info',
      },
      {
        id: 'run-activity-2',
        title: 'Run started',
        description: 'Execution entered the staging bake flow.',
        timestamp: isoMinutesAgo(6400),
        level: 'info',
      },
      {
        id: 'run-activity-3',
        title: 'Smoke suite extended',
        description: 'Platform Ops added notification-center coverage to the staging bake.',
        timestamp: isoMinutesAgo(14),
        level: 'info',
      },
    ],
  },
  {
    id: 'project-run-center-refresh',
    title: 'Run Center Refresh',
    summary:
      'Unify historical execution visibility for latest run attempts, event streams, and node health snapshots.',
    instructions:
      'Create a clean run operations surface that summarizes current attempts, failure patterns, and handoffs to projects.',
    status: 'reviewing',
    createdAt: isoMinutesAgo(12_000),
    updatedAt: isoMinutesAgo(55),
    runCreatedAt: isoMinutesAgo(10_510),
    runTriggerSource: 'plan_generated',
    startedAt: isoMinutesAgo(10_500),
    totalTasks: 4,
    completedTasks: 4,
    failedTasks: 0,
    tasks: [
      {
        id: 'task-timeline-shell',
        title: 'Define run timeline shell',
        status: 'completed',
        priority: 3,
        assignedAgentId: 'node-ux-lead',
        assignedAgentName: 'UX Lead',
        assignedSkillNames: ['Journey Mapping'],
        result: 'Timeline layout approved with overview and detail drill-down.',
      },
      {
        id: 'task-run-filters',
        title: 'Connect status and failure filters',
        status: 'completed',
        priority: 2,
        assignedAgentId: 'node-data-ops',
        assignedAgentName: 'Data Ops',
        assignedSkillNames: ['Data Shaping'],
        result: 'Filter states now align with execution event labels.',
      },
    ],
    agents: [
      {
        id: 'node-ux-lead',
        name: 'UX Lead',
        role: 'leader',
        status: 'idle',
        assignedAt: isoMinutesAgo(11_000),
      },
      {
        id: 'node-data-ops',
        name: 'Data Ops',
        role: 'worker',
        status: 'idle',
        assignedAt: isoMinutesAgo(10_000),
      },
    ],
    deliverables: [
      {
        filename: 'run-center-wireframe.fig',
        path: 'output/run-center-wireframe.fig',
        size: 182_000,
        isTarget: false,
        sourceScope: 'output',
      },
    ],
    projectActivity: [
      {
        id: 'activity-3',
        title: 'Review queued',
        description: 'Design review requested for the final run-center shell pass.',
        timestamp: isoMinutesAgo(55),
        level: 'warning',
        actor: 'UX Lead',
      },
      {
        id: 'activity-4',
        title: 'Filters connected',
        description: 'Run filters now align with execution status and failure groupings.',
        timestamp: isoMinutesAgo(130),
        level: 'success',
        actor: 'Data Ops',
        taskId: 'task-run-filters',
      },
    ],
    runTimeline: [
      {
        id: 'run-activity-4',
        title: 'Run created',
        description: 'Triggered from the planning workflow.',
        timestamp: isoMinutesAgo(10_510),
        level: 'info',
      },
      {
        id: 'run-activity-5',
        title: 'Run started',
        description: 'Execution began for the run-center refresh scope.',
        timestamp: isoMinutesAgo(10_500),
        level: 'info',
      },
      {
        id: 'run-activity-6',
        title: 'Run reviewing',
        description: 'Design review requested for the final run-center shell pass.',
        timestamp: isoMinutesAgo(55),
        level: 'warning',
      },
    ],
  },
];

const fallbackSkillHub: SkillHubSnapshot = {
  overview: {
    totalSkills: 42,
    activeSkills: 36,
    candidateCount: 5,
    bindingCount: 18,
    storeItems: 9,
  },
  featuredSkills: [
    {
      id: 'skill-release-planning',
      name: 'Release Planning',
      description: 'Coordinates launch checklists, approvals, and risk notes.',
      type: 'agent_skill',
      executionCount: 128,
      accessLevel: 'team',
      lastExecutedAt: isoMinutesAgo(80),
    },
    {
      id: 'skill-ci-diagnostics',
      name: 'CI Diagnostics',
      description: 'Summarizes pipeline regressions and flaky test clusters.',
      type: 'langchain_tool',
      executionCount: 94,
      accessLevel: 'team',
      lastExecutedAt: isoMinutesAgo(30),
    },
  ],
  pendingCandidates: [
    {
      id: 'candidate-launch-note-diff',
      title: 'Launch note diff summarizer',
      summary: 'Suggest a reusable skill from the launch narrative reconciliation flow.',
      status: 'pending',
      sourceAgentName: 'Ops Comms',
      createdAt: isoMinutesAgo(250),
    },
  ],
  recentBindings: [
    {
      id: 'binding-release-lead',
      ownerName: 'Release Lead',
      ownerType: 'agent',
      skillName: 'Release Planning',
      skillSlug: 'release-planning',
      bindingMode: 'tool',
      enabled: true,
      updatedAt: isoMinutesAgo(95),
    },
  ],
};

const fallbackExtensions: PlatformExtension[] = [
  {
    id: 'extension-github-actions',
    name: 'GitHub Actions MCP',
    description: 'Pulls workflow status, logs, and deployment artifacts.',
    status: 'connected',
    transport: 'streamable_http',
    toolCount: 12,
    isActive: true,
    endpoint: 'https://mcp.example.dev/github-actions',
    lastConnectedAt: isoMinutesAgo(18),
    lastSyncAt: isoMinutesAgo(8),
  },
  {
    id: 'extension-release-registry',
    name: 'Release Registry',
    description: 'Resolves build provenance and release channel metadata.',
    status: 'syncing',
    transport: 'stdio',
    toolCount: 6,
    isActive: true,
    endpoint: 'npx @linx/release-registry-mcp',
    lastSyncAt: isoMinutesAgo(2),
  },
];

const asUnknownRecord = (value: unknown): Record<string, unknown> => {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }

  return {};
};

const asOptionalString = (value: unknown): string | null =>
  typeof value === 'string' && value.trim().length > 0 ? value : null;

const asOptionalNumber = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  return null;
};

const asOptionalBoolean = (value: unknown): boolean | null =>
  typeof value === 'boolean' ? value : null;

const asStringArray = (value: unknown): string[] => {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.flatMap((item): string[] => {
    if (typeof item === 'string' && item.trim().length > 0) {
      return [item];
    }
    if (typeof item === 'number' && Number.isFinite(item)) {
      return [String(item)];
    }
    if (item && typeof item === 'object' && !Array.isArray(item)) {
      const record = item as Record<string, unknown>;
      const label =
        asOptionalString(record.display_name) ||
        asOptionalString(record.name) ||
        asOptionalString(record.skill) ||
        asOptionalString(record.slug);
      return label ? [label] : [];
    }
    return [];
  });
};

const pickFirstString = (
  record: Record<string, unknown>,
  keys: string[],
): string | null => {
  for (const key of keys) {
    const value = asOptionalString(record[key]);
    if (value) {
      return value;
    }
  }

  return null;
};

const pickFirstStringArray = (
  record: Record<string, unknown>,
  keys: string[],
): string[] => {
  for (const key of keys) {
    const values = asStringArray(record[key]);
    if (values.length > 0) {
      return values;
    }
  }

  return [];
};

const groupByKey = <T>(
  items: T[],
  getKey: (item: T) => string | null | undefined,
): Map<string, T[]> => {
  const groups = new Map<string, T[]>();

  items.forEach((item) => {
    const key = getKey(item);
    if (!key) {
      return;
    }

    const existing = groups.get(key);
    if (existing) {
      existing.push(item);
      return;
    }

    groups.set(key, [item]);
  });

  return groups;
};

const latestIsoString = (values: Array<string | null | undefined>): string | null => {
  const filtered = values.filter(
    (value): value is string => typeof value === 'string' && value.length > 0,
  );

  if (filtered.length === 0) {
    return null;
  }

  return filtered.sort((left, right) => new Date(right).getTime() - new Date(left).getTime())[0];
};

const getRunHandledAtFromRuntimeContext = (runtimeContext: Record<string, unknown>): string | null => {
  const alertState = asUnknownRecord(runtimeContext.alert_state);
  return (
    pickFirstString(alertState, ['handled_at', 'handledAt']) ||
    pickFirstString(runtimeContext, ['handled_at', 'handledAt'])
  );
};

const getRunHandledSignatureFromRuntimeContext = (
  runtimeContext: Record<string, unknown>,
): string | null => {
  const alertState = asUnknownRecord(runtimeContext.alert_state);
  return pickFirstString(alertState, ['handled_signature', 'handledSignature']);
};

const buildRunAlertSignature = (input: {
  status: string;
  taskId?: string | null;
  taskTitle?: string | null;
  failureReason?: string | null;
  latestSignal?: string | null;
}): string => {
  return JSON.stringify({
    status: input.status,
    taskId: input.taskId || null,
    taskTitle: input.taskTitle || null,
    failureReason: input.failureReason || null,
    latestSignal: input.latestSignal || null,
  });
};

const skeletonRequestConfig: RequestConfigWithMeta = {
  suppressErrorToast: true,
};

const asErrorMessage = (error: unknown, fallback: string): string =>
  error instanceof Error ? error.message : fallback;

const getErrorStatus = (error: unknown): number | null => {
  if (!error || typeof error !== 'object' || !('response' in error)) {
    return null;
  }

  const response = (error as { response?: { status?: unknown } }).response;
  return typeof response?.status === 'number' ? response.status : null;
};

const toProjectStatus = (status: string): string => {
  switch ((status || '').toLowerCase()) {
    case 'requirements':
    case 'planning':
      return 'planning';
    case 'queued':
    case 'pending':
      return 'queued';
    case 'assigned':
      return 'assigned';
    case 'scheduled':
      return 'scheduled';
    case 'executing':
    case 'running':
    case 'in_progress':
      return 'running';
    case 'reviewing':
    case 'qa':
    case 'review':
      return 'reviewing';
    case 'blocked':
      return 'blocked';
    case 'busy':
      return 'working';
    case 'available':
      return 'idle';
    case 'disabled':
      return 'offline';
    default:
      return status || 'draft';
  }
};

const toExtensionStatus = (status: string): string => {
  switch ((status || '').toLowerCase()) {
    case 'enabled':
      return 'connected';
    case 'installed':
      return 'idle';
    case 'disabled':
      return 'disconnected';
    default:
      return status || 'disconnected';
  }
};

const activityLevelFromStatus = (status: string): ProjectActivityItem['level'] => {
  const normalized = (status || '').toLowerCase();
  if (normalized.includes('fail') || normalized.includes('error') || normalized === 'cancelled') {
    return 'error';
  }
  if (
    normalized.includes('review') ||
    normalized.includes('blocked') ||
    normalized.includes('clarification')
  ) {
    return 'warning';
  }
  if (
    normalized.includes('complete') ||
    normalized.includes('success') ||
    normalized.includes('approved')
  ) {
    return 'success';
  }
  return 'info';
};

const isCompletedStatus = (status: string): boolean => {
  const normalized = (status || '').toLowerCase();
  return ['completed', 'done', 'success', 'succeeded', 'approved'].includes(normalized);
};

const isFailedStatus = (status: string): boolean => {
  const normalized = (status || '').toLowerCase();
  return (
    normalized === 'cancelled' ||
    normalized === 'canceled' ||
    normalized === 'error' ||
    normalized === 'failed' ||
    normalized.includes('fail')
  );
};

const isClosedRunStatus = (status: string): boolean => {
  const normalized = (status || '').toLowerCase();
  return ['completed', 'done', 'success', 'succeeded', 'failed', 'cancelled', 'canceled'].includes(
    normalized,
  );
};

const isTerminalTaskStatus = (status: string): boolean =>
  isCompletedStatus(status) || isFailedStatus(status);

const isBlockedStatus = (status: string): boolean => (status || '').toLowerCase() === 'blocked';

const isActiveRunStatus = (status: string): boolean =>
  ['running', 'executing', 'in_progress'].includes((status || '').toLowerCase());

const isQueuedRunStatus = (status: string): boolean =>
  ['queued', 'assigned', 'scheduled', 'pending'].includes((status || '').toLowerCase());

type ResolvedProjectLifecycle = {
  status: string;
  completedAt: string | null;
};

const resolveProjectLifecycle = (
  project: SkeletonProjectRecord,
  tasks: SkeletonProjectTaskRecord[],
  runs: SkeletonRunRecord[],
): ResolvedProjectLifecycle => {
  const taskStatuses = tasks.map((task) => (task.status || '').toLowerCase());
  const resolvedRuns = runs.map((run) => ({
    run,
    lifecycle: resolveRunLifecycle(
      run,
      tasks.filter((task) => task.run_id === run.run_id),
      [],
    ),
  }));
  const runStatuses = resolvedRuns.map((item) => (item.lifecycle.status || '').toLowerCase());

  if (taskStatuses.length === 0 && runStatuses.length === 0) {
    return {
      status: toProjectStatus(project.status),
      completedAt: null,
    };
  }

  if (taskStatuses.some((status) => status === 'running') || runStatuses.some(isActiveRunStatus)) {
    return {
      status: 'running',
      completedAt: null,
    };
  }

  if (taskStatuses.some(isQueuedRunStatus) || runStatuses.some(isQueuedRunStatus)) {
    return {
      status: 'queued',
      completedAt: null,
    };
  }

  if (resolvedRuns.length > 0) {
    const latestRun = resolvedRuns
      .slice()
      .sort(
        (left, right) =>
          new Date(
            right.run.updated_at ||
              right.lifecycle.completedAt ||
              right.run.started_at ||
              right.run.created_at,
          ).getTime() -
          new Date(
            left.run.updated_at ||
              left.lifecycle.completedAt ||
              left.run.started_at ||
              left.run.created_at,
          ).getTime(),
      )[0];
    const latestRunStatus = latestRun.lifecycle.status.toLowerCase();
    if (isBlockedStatus(latestRunStatus)) {
      return {
        status: 'blocked',
        completedAt: null,
      };
    }
    if (isFailedStatus(latestRunStatus)) {
      return {
        status: 'failed',
        completedAt: latestRun.lifecycle.completedAt,
      };
    }
    if (isClosedRunStatus(latestRunStatus)) {
      return {
        status: 'completed',
        completedAt: latestRun.lifecycle.completedAt,
      };
    }
  }

  if (tasks.length > 0) {
    const latestTask = tasks
      .slice()
      .sort(
        (left, right) =>
          new Date(right.updated_at || right.created_at).getTime() -
          new Date(left.updated_at || left.created_at).getTime(),
      )[0];
    const latestTaskStatus = (latestTask.status || '').toLowerCase();
    if (isBlockedStatus(latestTaskStatus)) {
      return {
        status: 'blocked',
        completedAt: null,
      };
    }
    if (isFailedStatus(latestTaskStatus)) {
      return {
        status: 'failed',
        completedAt: latestTask.updated_at || null,
      };
    }
    if (isCompletedStatus(latestTaskStatus)) {
      return {
        status: 'completed',
        completedAt: latestTask.updated_at || null,
      };
    }
  }

  return {
    status: toProjectStatus(project.status),
    completedAt: null,
  };
};

type ResolvedRunLifecycle = {
  status: string;
  completedAt: string | null;
};

const resolveRunLifecycle = (
  run: SkeletonRunRecord,
  tasks: SkeletonProjectTaskRecord[],
  runSteps: SkeletonRunStepRecord[],
): ResolvedRunLifecycle => {
  const rawStatus = (run.status || '').toLowerCase();
  const fallbackCompletedAt =
    latestIsoString([
      run.completed_at,
      ...tasks.map((task) => task.updated_at),
      ...runSteps.map((step) => step.completed_at || null),
      ...runSteps.map((step) => step.updated_at),
      run.updated_at,
      run.started_at,
    ]) || null;

  if (isClosedRunStatus(rawStatus)) {
    return {
      status: toProjectStatus(run.status),
      completedAt: run.completed_at || fallbackCompletedAt,
    };
  }

  if (tasks.length === 0) {
    if (run.started_at) {
      return {
        status: runSteps.some((step) => isFailedStatus(step.status)) ? 'failed' : 'completed',
        completedAt: run.completed_at || fallbackCompletedAt,
      };
    }

    return {
      status: toProjectStatus(run.status),
      completedAt: run.completed_at || null,
    };
  }

  if (tasks.every((task) => isTerminalTaskStatus(task.status))) {
    return {
      status:
        tasks.some((task) => isFailedStatus(task.status)) ||
        runSteps.some((step) => isFailedStatus(step.status))
          ? 'failed'
          : 'completed',
      completedAt: run.completed_at || fallbackCompletedAt,
    };
  }

  return {
    status: toProjectStatus(run.status),
    completedAt: run.completed_at || null,
  };
};

const priorityToNumber = (value: string | number | null | undefined): number => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }

  const normalized = String(value || '').toLowerCase();
  const numericValue = Number(normalized);
  if (Number.isFinite(numericValue) && normalized.trim().length > 0) {
    return numericValue;
  }

  switch (normalized) {
    case 'urgent':
    case 'critical':
      return 4;
    case 'high':
      return 3;
    case 'medium':
    case 'normal':
      return 2;
    case 'low':
      return 1;
    default:
      return 2;
  }
};

const truncateText = (value: string | undefined | null, limit = 160): string => {
  if (!value) {
    return 'No summary available yet.';
  }

  const normalized = value.trim();
  if (normalized.length <= limit) {
    return normalized;
  }

  return `${normalized.slice(0, Math.max(limit - 1, 1))}…`;
};

const humanizeToken = (value: string): string =>
  value
    .replace(/[_-]+/g, ' ')
    .split(' ')
    .filter(Boolean)
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1).toLowerCase())
    .join(' ');

const isTerminalRunStatus = (status: string): boolean => {
  const normalized = (status || '').toLowerCase();
  return ['completed', 'done', 'success', 'succeeded', 'failed', 'cancelled', 'canceled', 'blocked'].includes(
    normalized,
  );
};

const summarizeRecord = (value?: Record<string, unknown> | null): string | null => {
  if (!value) {
    return null;
  }

  const prioritizedKeys = [
    'summary',
    'output',
    'result',
    'error',
    'reason',
    'review_feedback',
    'message',
  ];

  for (const key of prioritizedKeys) {
    const candidate = value[key];
    if (typeof candidate === 'string' && candidate.trim().length > 0) {
      return truncateText(candidate, 180);
    }
  }

  const flattened = Object.entries(value)
    .filter(([, candidate]) => ['string', 'number', 'boolean'].includes(typeof candidate))
    .slice(0, 3)
    .map(([key, candidate]) => `${humanizeToken(key)}: ${String(candidate)}`)
    .join(' · ');

  return flattened.length > 0 ? flattened : null;
};

const sortByUpdatedDescending = <T extends { updatedAt: string }>(left: T, right: T): number =>
  new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime();

const buildProgress = (completedTasks: number, totalTasks: number, status: string): number => {
  if (totalTasks <= 0) {
    return status === 'completed' ? 100 : 0;
  }

  return Math.max(0, Math.min(100, Math.round((completedTasks / totalTasks) * 100)));
};

const seedToProjectSummary = (seed: SeedProject): ProjectSummary => ({
  id: seed.id,
  title: seed.title,
  summary: seed.summary,
  status: seed.status,
  progress: buildProgress(seed.completedTasks, seed.totalTasks, seed.status),
  createdAt: seed.createdAt,
  updatedAt: seed.updatedAt,
  startedAt: seed.startedAt || null,
  completedAt: seed.completedAt || null,
  totalTasks: seed.totalTasks,
  completedTasks: seed.completedTasks,
  failedTasks: seed.failedTasks,
  activeNodeCount: seed.agents.length,
  needsClarification: false,
  latestSignal: seed.projectActivity[0]?.description || null,
});

const seedToProjectDetail = (seed: SeedProject): ProjectDetail => ({
  ...seedToProjectSummary(seed),
  instructions: seed.instructions,
  tasks: seed.tasks.map((task) => ({
    id: task.id,
    title: task.title,
    status: task.status,
    priority: task.priority,
    updatedAt: seed.updatedAt,
    assignedAgentId: task.assignedAgentId || null,
    assignedAgentName: task.assignedAgentName || null,
    dependencyIds: task.dependencies || [],
    reviewStatus:
      task.metadata?.find((entry) => entry.label.toLowerCase() === 'review status')?.value || null,
  })),
  runs: [seedToRunSummary(seed)].sort(sortByUpdatedDescending),
  agents: seed.agents.map((agent) => ({
    id: agent.id,
    name: agent.name,
    role: agent.role,
    status: agent.status,
    isTemporary: Boolean(agent.isTemporary),
    assignedAt: agent.assignedAt || null,
  })),
  deliverables: seed.deliverables,
  recentActivity: seed.projectActivity,
});

const seedToTaskDetail = (seed: SeedProject, taskId: string): ProjectTaskDetail => {
  const task = seed.tasks.find((candidate) => candidate.id === taskId);
  if (!task) {
    throw new Error('Task not found');
  }

  return {
    id: task.id,
    projectId: seed.id,
    projectTitle: seed.title,
    projectStatus: seed.status,
    title: task.title,
    description: task.title,
    status: task.status,
    priority: task.priority,
    updatedAt: seed.updatedAt,
    assignedAgentId: task.assignedAgentId || null,
    assignedAgentName: task.assignedAgentName || null,
    dependencyIds: task.dependencies || [],
    reviewStatus:
      task.metadata?.find((entry) => entry.label.toLowerCase() === 'review status')?.value || null,
    acceptanceCriteria: task.acceptanceCriteria || null,
    assignedSkillNames: task.assignedSkillNames || [],
    latestResult: task.result || null,
    metadata: task.metadata || [],
    events: seed.projectActivity.filter((item) => item.taskId === taskId),
  };
};

const seedToRunSummary = (seed: SeedProject): RunSummary => ({
  id: seed.id,
  projectId: seed.id,
  projectTitle: seed.title,
  status: seed.status,
  createdAt: seed.runCreatedAt,
  triggerSource: seed.runTriggerSource,
  taskId: seed.tasks[0]?.id || null,
  taskTitle: seed.tasks[0]?.title || null,
  failureReason: seed.failedTasks > 0 ? seed.runTimeline[seed.runTimeline.length - 1]?.description || null : null,
  startedAt: seed.startedAt || null,
  completedAt: seed.completedAt || null,
  updatedAt: seed.updatedAt,
  totalTasks: seed.totalTasks,
  completedTasks: seed.completedTasks,
  failedTasks: seed.failedTasks,
  externalAgentCount: seed.agents.length,
  latestSignal: seed.runTimeline[seed.runTimeline.length - 1]?.description || null,
});

const seedToRunDetail = (seed: SeedProject): RunDetail => ({
  ...seedToRunSummary(seed),
  projectSummary: seed.summary,
  timeline: [...seed.runTimeline].sort(
    (left, right) => new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime(),
  ),
  deliverables: seed.deliverables,
  externalDispatches: [],
});

const fallbackProjectMap = new Map(
  fallbackSeedProjects.map((project) => [project.id, project]),
);

const fallbackProjectSummaries = fallbackSeedProjects.map(seedToProjectSummary).sort(sortByUpdatedDescending);
const fallbackRunSummaries = fallbackSeedProjects.map(seedToRunSummary).sort(sortByUpdatedDescending);

const toSkillItem = (record: {
  skill_id: string;
  display_name: string;
  description: string;
  skill_type?: string;
  execution_count?: number;
  access_level: string;
  last_executed_at?: string | null;
}): SkillHubSkillItem => ({
  id: record.skill_id,
  name: record.display_name,
  description: record.description,
  type: record.skill_type || 'unknown',
  executionCount: record.execution_count || 0,
  accessLevel: record.access_level,
  lastExecutedAt: record.last_executed_at || null,
});

const toCandidateItem = (record: {
  candidate_id: string;
  title: string;
  summary: string;
  status: string;
  source_agent_name?: string | null;
  created_at: string;
}): SkillHubCandidateItem => ({
  id: record.candidate_id,
  title: record.title,
  summary: record.summary,
  status: record.status,
  sourceAgentName: record.source_agent_name || null,
  createdAt: record.created_at,
});

const toBindingItem = (record: {
  binding_id: string;
  owner_name: string;
  owner_type: string;
  display_name: string;
  skill_slug: string;
  binding_mode?: string | null;
  enabled?: boolean;
  updated_at?: string | null;
}): SkillHubBindingItem => ({
  id: record.binding_id,
  ownerName: record.owner_name,
  ownerType: record.owner_type,
  skillName: record.display_name,
  skillSlug: record.skill_slug,
  bindingMode: record.binding_mode || null,
  enabled: record.enabled !== false,
  updatedAt: record.updated_at || null,
});

const toWorkspaceFile = (item: {
  name: string;
  path: string;
  size: number;
  is_directory?: boolean;
  is_dir?: boolean;
  modified_at?: string;
  previewable_inline?: boolean;
  retention_class?: string;
}): AgentSessionWorkspaceFile => ({
  name: item.name,
  path: item.path,
  size: item.size,
  is_dir: item.is_dir ?? Boolean(item.is_directory),
  modified_at: item.modified_at,
  previewable_inline: item.previewable_inline,
  retentionClass: item.retention_class,
});

const skeletonApi = {
  async listProjects(): Promise<SkeletonProjectRecord[]> {
    const response = await apiClient.get<SkeletonProjectRecord[]>('/projects', skeletonRequestConfig);
    return response.data;
  },

  async getProject(projectId: string): Promise<SkeletonProjectRecord> {
    const response = await apiClient.get<SkeletonProjectRecord>(
      `/projects/${projectId}`,
      skeletonRequestConfig,
    );
    return response.data;
  },

  async listPlans(projectId?: string): Promise<SkeletonPlanRecord[]> {
    const response = await apiClient.get<SkeletonPlanRecord[]>('/plans', {
      ...skeletonRequestConfig,
      params: projectId ? { project_id: projectId } : undefined,
    });
    return response.data;
  },

  async listProjectTasks(projectId?: string): Promise<SkeletonProjectTaskRecord[]> {
    const response = await apiClient.get<SkeletonProjectTaskRecord[]>('/project-tasks', {
      ...skeletonRequestConfig,
      params: projectId ? { project_id: projectId } : undefined,
    });
    return response.data;
  },

  async getProjectTask(taskId: string): Promise<SkeletonProjectTaskRecord> {
    const response = await apiClient.get<SkeletonProjectTaskRecord>(
      `/project-tasks/${taskId}`,
      skeletonRequestConfig,
    );
    return response.data;
  },

  async listRuns(projectId?: string): Promise<SkeletonRunRecord[]> {
    const response = await apiClient.get<SkeletonRunRecord[]>('/runs', {
      ...skeletonRequestConfig,
      params: projectId ? { project_id: projectId } : undefined,
    });
    return response.data;
  },

  async getRun(runId: string): Promise<SkeletonRunRecord> {
    const response = await apiClient.get<SkeletonRunRecord>(`/runs/${runId}`, skeletonRequestConfig);
    return response.data;
  },

  async listRunWorkspaceFiles(
    runId: string,
    path?: string,
    recursive = false,
    options?: { suppressErrorToast?: boolean },
  ): Promise<AgentSessionWorkspaceFile[]> {
    const requestConfig: RequestConfigWithMeta = {
      ...skeletonRequestConfig,
      params: {
        ...(path ? { path } : {}),
        ...(recursive ? { recursive: true } : {}),
      },
      suppressErrorToast: options?.suppressErrorToast,
    };
    const response = await apiClient.get<
      Array<{
        name: string;
        path: string;
        size: number;
        is_directory?: boolean;
        is_dir?: boolean;
        modified_at?: string;
        previewable_inline?: boolean;
        retention_class?: string;
      }>
    >(`/runs/${runId}/workspace/files`, requestConfig);
    return response.data.map(toWorkspaceFile);
  },

  async downloadRunWorkspaceFile(
    runId: string,
    path: string,
    options?: { suppressErrorToast?: boolean },
  ): Promise<Blob> {
    const requestConfig: RequestConfigWithMeta = {
      ...skeletonRequestConfig,
      params: { path },
      responseType: 'blob',
      suppressErrorToast: options?.suppressErrorToast,
    };
    const response = await apiClient.get(`/runs/${runId}/workspace/download`, requestConfig);
    return response.data;
  },

  async listRunExternalDispatches(runId: string): Promise<SkeletonExternalAgentDispatchRecord[]> {
    const response = await apiClient.get<SkeletonExternalAgentDispatchRecord[]>(`/runs/${runId}/external-dispatches`, skeletonRequestConfig);
    return response.data;
  },

  async listRunSteps(runId?: string): Promise<SkeletonRunStepRecord[]> {
    const response = await apiClient.get<SkeletonRunStepRecord[]>('/run-steps', {
      ...skeletonRequestConfig,
      params: runId ? { run_id: runId } : undefined,
    });
    return response.data;
  },

  async getProjectSpace(projectId: string): Promise<SkeletonProjectSpaceRecord | null> {
    try {
      const response = await apiClient.get<SkeletonProjectSpaceRecord>(
        `/project-space/${projectId}`,
        skeletonRequestConfig,
      );
      return response.data;
    } catch (error) {
      if (getErrorStatus(error) === 404) {
        return null;
      }

      throw error;
    }
  },

  async listProjectWorkspaceFiles(
    projectId: string,
    path?: string,
    recursive = false,
    options?: { suppressErrorToast?: boolean },
  ): Promise<AgentSessionWorkspaceFile[]> {
    const requestConfig: RequestConfigWithMeta = {
      ...skeletonRequestConfig,
      params: {
        ...(path ? { path } : {}),
        ...(recursive ? { recursive: true } : {}),
      },
      suppressErrorToast: options?.suppressErrorToast,
    };
    const response = await apiClient.get<
      Array<{
        name: string;
        path: string;
        size: number;
        is_directory?: boolean;
        is_dir?: boolean;
        modified_at?: string;
        previewable_inline?: boolean;
        retention_class?: string;
      }>
    >(`/project-space/${projectId}/files`, requestConfig);
    return response.data.map(toWorkspaceFile);
  },

  async downloadProjectWorkspaceFile(
    projectId: string,
    path: string,
    options?: { suppressErrorToast?: boolean },
  ): Promise<Blob> {
    const requestConfig: RequestConfigWithMeta = {
      ...skeletonRequestConfig,
      params: { path },
      responseType: 'blob',
      suppressErrorToast: options?.suppressErrorToast,
    };
    const response = await apiClient.get(`/project-space/${projectId}/download`, requestConfig);
    return response.data;
  },

  async listProjectAgentBindings(projectId: string): Promise<SkeletonProjectAgentBindingRecord[]> {
    const response = await apiClient.get<SkeletonProjectAgentBindingRecord[]>(`/projects/${projectId}/agent-bindings`, skeletonRequestConfig);
    return response.data;
  },

  async createProjectAgentBinding(projectId: string, payload: { agentId: string; roleHint?: string | null; priority?: number; allowedStepKinds?: string[]; preferredSkills?: string[]; preferredRuntimeTypes?: string[]; }): Promise<SkeletonProjectAgentBindingRecord> {
    const response = await apiClient.post<SkeletonProjectAgentBindingRecord>(`/projects/${projectId}/agent-bindings`, {
      agent_id: payload.agentId,
      role_hint: payload.roleHint || undefined,
      priority: payload.priority ?? 0,
      status: 'active',
      allowed_step_kinds: payload.allowedStepKinds || [],
      preferred_skills: payload.preferredSkills || [],
      preferred_runtime_types: payload.preferredRuntimeTypes || [],
    }, skeletonRequestConfig);
    return response.data;
  },

  async deleteProjectAgentBinding(projectId: string, bindingId: string): Promise<void> {
    await apiClient.delete(`/projects/${projectId}/agent-bindings/${bindingId}`, skeletonRequestConfig);
  },

  async listAgentProvisioningProfiles(projectId: string): Promise<SkeletonAgentProvisioningProfileRecord[]> {
    const response = await apiClient.get<SkeletonAgentProvisioningProfileRecord[]>(`/projects/${projectId}/agent-provisioning-profiles`, skeletonRequestConfig);
    return response.data;
  },

  async listExtensions(projectId?: string): Promise<SkeletonExtensionRecord[]> {
    const response = await apiClient.get<SkeletonExtensionRecord[]>('/extensions', {
      ...skeletonRequestConfig,
      params: projectId ? { project_id: projectId } : undefined,
    });
    return response.data;
  },

  async deleteProject(projectId: string): Promise<void> {
    await apiClient.delete(`/projects/${projectId}`, skeletonRequestConfig);
  },

  async deleteProjectTask(taskId: string): Promise<void> {
    await apiClient.delete(`/project-tasks/${taskId}`, skeletonRequestConfig);
  },

  async updateProject(projectId: string, payload: Partial<{ name: string; description?: string | null; status: string; configuration: Record<string, unknown>; }>): Promise<SkeletonProjectRecord> {
    const response = await apiClient.patch<SkeletonProjectRecord>(`/projects/${projectId}`, {
      ...payload,
      description: payload.description === null ? undefined : payload.description,
    }, skeletonRequestConfig);
    return response.data;
  },

  async createProject(input: {
    name: string;
    description?: string | null;
  }): Promise<SkeletonProjectRecord> {
    const response = await apiClient.post<SkeletonProjectRecord>(
      '/projects',
      {
        name: input.name,
        description: input.description || undefined,
        status: 'draft',
        configuration: {},
      },
      skeletonRequestConfig,
    );
    return response.data;
  },

  async createProjectTask(input: {
    projectId: string;
    title: string;
    description?: string | null;
    sortOrder?: number;
    executionMode?: ProjectExecutionMode;
  }): Promise<SkeletonProjectTaskRecord> {
    const response = await apiClient.post<SkeletonProjectTaskRecord>(
      '/project-tasks',
      {
        project_id: input.projectId,
        title: input.title,
        description: input.description || undefined,
        status: 'planning',
        priority: 'normal',
        sort_order: input.sortOrder ?? 0,
        input_payload: {
          execution_mode: input.executionMode || 'auto',
        },
        execution_mode: input.executionMode || 'auto',
      },
      skeletonRequestConfig,
    );
    return response.data;
  },

  async createProjectTaskAndLaunchRun(input: {
    projectId: string;
    title: string;
    description?: string | null;
    executionMode?: ProjectExecutionMode;
  }): Promise<SkeletonTaskLaunchBundleRecord> {
    const response = await apiClient.post<SkeletonTaskLaunchBundleRecord>(
      '/project-tasks/create-and-launch',
      {
        project_id: input.projectId,
        title: input.title,
        description: input.description || undefined,
        priority: 'normal',
        input_payload: {
          execution_mode: input.executionMode || 'auto',
        },
        execution_mode: input.executionMode || 'auto',
      },
      skeletonRequestConfig,
    );
    return response.data;
  },

  async updateProjectTask(
    taskId: string,
    payload: Partial<{
      plan_id: string;
      run_id: string;
      status: string;
      input_payload: Record<string, unknown>;
    }>,
  ): Promise<SkeletonProjectTaskRecord> {
    const response = await apiClient.patch<SkeletonProjectTaskRecord>(
      `/project-tasks/${taskId}`,
      payload,
      skeletonRequestConfig,
    );
    return response.data;
  },

  async createPlan(input: {
    projectId: string;
    name: string;
    goal?: string | null;
    definition?: Record<string, unknown>;
  }): Promise<SkeletonPlanRecord> {
    const response = await apiClient.post<SkeletonPlanRecord>(
      '/plans',
      {
        project_id: input.projectId,
        name: input.name,
        goal: input.goal || undefined,
        status: 'generated',
        version: 1,
        definition: input.definition || {},
      },
      skeletonRequestConfig,
    );
    return response.data;
  },

  async activatePlan(planId: string): Promise<SkeletonPlanRecord> {
    const response = await apiClient.post<SkeletonPlanRecord>(
      `/plans/${planId}/activate`,
      { status: 'active' },
      skeletonRequestConfig,
    );
    return response.data;
  },

  async createRun(input: {
    projectId: string;
    planId?: string | null;
    runtimeContext?: Record<string, unknown>;
  }): Promise<SkeletonRunRecord> {
    const response = await apiClient.post<SkeletonRunRecord>(
      '/runs',
      {
        project_id: input.projectId,
        plan_id: input.planId || undefined,
        status: 'queued',
        trigger_source: 'manual',
        runtime_context: input.runtimeContext || {},
      },
      skeletonRequestConfig,
    );
    return response.data;
  },

  async startRun(runId: string): Promise<SkeletonRunRecord> {
    const response = await apiClient.post<SkeletonRunRecord>(
      `/runs/${runId}/start`,
      undefined,
      skeletonRequestConfig,
    );
    return response.data;
  },

  async scheduleRun(runId: string): Promise<SkeletonRunSchedulingRecord> {
    const response = await apiClient.post<SkeletonRunSchedulingRecord>(`/runs/${runId}/schedule`, undefined, skeletonRequestConfig);
    return response.data;
  },

  async updateRun(
    runId: string,
    payload: Partial<{
      status: string;
      triggerSource: string;
      runtimeContext: Record<string, unknown>;
      errorMessage: string | null;
    }>,
  ): Promise<SkeletonRunRecord> {
    const response = await apiClient.patch<SkeletonRunRecord>(
      `/runs/${runId}`,
      {
        status: payload.status,
        trigger_source: payload.triggerSource,
        runtime_context: payload.runtimeContext,
        error_message: payload.errorMessage === null ? undefined : payload.errorMessage,
      },
      skeletonRequestConfig,
    );
    return response.data;
  },

  async createRunStep(input: {
    runId: string;
    projectTaskId: string;
    name: string;
    sequenceNumber?: number;
    inputPayload?: Record<string, unknown>;
  }): Promise<SkeletonRunStepRecord> {
    const response = await apiClient.post<SkeletonRunStepRecord>(
      '/run-steps',
      {
        run_id: input.runId,
        project_task_id: input.projectTaskId,
        name: input.name,
        step_type: 'task',
        status: 'pending',
        sequence_number: input.sequenceNumber ?? 0,
        input_payload: input.inputPayload || { project_task_id: input.projectTaskId },
      },
      skeletonRequestConfig,
    );
    return response.data;
  },
};

const deliverableFromUnknown = (value: unknown): ProjectDeliverable | null => {
  const record = asUnknownRecord(value);
  const path = pickFirstString(record, ['path', 'file_reference', 'uri']);
  const filename =
    pickFirstString(record, ['filename', 'name']) || path?.split('/').filter(Boolean).pop();

  if (!filename || !path) {
    return null;
  }

  return {
    filename,
    path,
    size: asOptionalNumber(record.size) || asOptionalNumber(record.file_size) || 0,
    downloadUrl: pickFirstString(record, ['download_url', 'downloadUrl', 'url']),
    isTarget: asOptionalBoolean(record.is_target) ?? asOptionalBoolean(record.isTarget) ?? false,
    sourceScope: pickFirstString(record, ['source_scope', 'sourceScope', 'scope']),
  };
};

const NON_DELIVERABLE_WORKSPACE_EXTENSIONS = new Set([
  '.ttf',
  '.otf',
  '.ttc',
  '.woff',
  '.woff2',
  '.eot',
]);

const normalizeWorkspaceArtifactPath = (value: string): string => {
  const normalized = String(value || '').trim().replace(/\\/g, '/');
  if (!normalized) {
    return '';
  }
  if (normalized.startsWith('/')) {
    return normalized;
  }
  return normalized.startsWith('workspace/') ? `/${normalized}` : `/workspace/${normalized}`;
};

const isDeliverableWorkspaceArtifactPath = (path: string): boolean => {
  const normalized = normalizeWorkspaceArtifactPath(path);
  if (
    !normalized ||
    normalized === '/workspace/output' ||
    !normalized.startsWith('/workspace/output/')
  ) {
    return false;
  }

  const suffixIndex = normalized.lastIndexOf('.');
  const suffix = suffixIndex >= 0 ? normalized.slice(suffixIndex).toLowerCase() : '';
  return !NON_DELIVERABLE_WORKSPACE_EXTENSIONS.has(suffix);
};

const artifactDeliverableFromUnknown = (value: unknown): ProjectDeliverable | null => {
  const record = asUnknownRecord(value);
  const path = pickFirstString(record, ['path', 'file_path', 'uri']);
  if (!path || asOptionalBoolean(record.is_directory) || asOptionalBoolean(record.is_dir)) {
    return null;
  }
  if (!isDeliverableWorkspaceArtifactPath(path)) {
    return null;
  }

  const normalizedPath = normalizeWorkspaceArtifactPath(path);
  const filename =
    pickFirstString(record, ['filename', 'name']) ||
    normalizedPath.split('/').filter(Boolean).pop() ||
    normalizedPath;

  return {
    filename,
    path: normalizedPath,
    size: asOptionalNumber(record.size) || asOptionalNumber(record.file_size) || 0,
    downloadUrl: pickFirstString(record, ['download_url', 'downloadUrl', 'url']),
    isTarget: true,
    sourceScope: 'run_workspace',
  };
};

const collectDeliverablesFromPayloads = (
  payloads: Array<Record<string, unknown>>,
): ProjectDeliverable[] => {
  const mapped = new Map<string, ProjectDeliverable>();

  payloads.forEach((payload) => {
    const rawDeliverables = payload.deliverables;
    if (Array.isArray(rawDeliverables)) {
      rawDeliverables.forEach((item) => {
        const deliverable = deliverableFromUnknown(item);
        if (!deliverable) {
          return;
        }

        mapped.set(deliverable.path, deliverable);
      });
    }

    const rawArtifacts = payload.artifacts;
    if (Array.isArray(rawArtifacts)) {
      rawArtifacts.forEach((item) => {
        const deliverable = artifactDeliverableFromUnknown(item);
        if (!deliverable) {
          return;
        }

        mapped.set(deliverable.path, deliverable);
      });
    }
  });

  return Array.from(mapped.values());
};

const getTaskDependenciesFromPayload = (payloads: Array<Record<string, unknown>>): string[] => {
  for (const payload of payloads) {
    const dependencies = pickFirstStringArray(payload, ['dependencies', 'dependency_ids', 'blocked_by']);
    if (dependencies.length > 0) {
      return dependencies;
    }
  }

  return [];
};

const getTaskAcceptanceFromPayload = (payloads: Array<Record<string, unknown>>): string | null => {
  for (const payload of payloads) {
    const acceptance = pickFirstString(payload, ['acceptance_criteria', 'acceptanceCriteria']);
    if (acceptance) {
      return acceptance;
    }
  }

  return null;
};

const getTaskReviewStatusFromPayload = (payloads: Array<Record<string, unknown>>): string | null => {
  for (const payload of payloads) {
    const reviewStatus = pickFirstString(payload, ['review_status', 'reviewStatus']);
    if (reviewStatus) {
      return reviewStatus;
    }
  }

  return null;
};

const getTaskSkillNamesFromPayload = (payloads: Array<Record<string, unknown>>): string[] => {
  for (const payload of payloads) {
    const skills = pickFirstStringArray(payload, ['skill_names', 'skillNames', 'skills']);
    if (skills.length > 0) {
      return skills;
    }
  }

  return [];
};

const getTaskAssigneeNameFromPayload = (payloads: Array<Record<string, unknown>>): string | null => {
  for (const payload of payloads) {
    const assignee = pickFirstString(payload, ['assigned_agent_name', 'assignee_name', 'owner_name']);
    if (assignee) {
      return assignee;
    }
  }

  return null;
};

const getTaskExecutionModeFromPayload = (
  payloads: Array<Record<string, unknown>>,
): string | null => {
  for (const payload of payloads) {
    const executionMode = pickFirstString(payload, ['execution_mode', 'executionMode']);
    if (executionMode) {
      return executionMode;
    }
  }

  return null;
};

const getPlannerQuestionsFromPayload = (
  payloads: Array<Record<string, unknown>>,
): Array<{ question: string; importance?: string }> => {
  for (const payload of payloads) {
    const rawQuestions = payload.planner_clarification_questions;
    if (!Array.isArray(rawQuestions)) continue;
    return rawQuestions
      .map((question) => asUnknownRecord(question))
      .map((question) => ({
        question: pickFirstString(question, ['question']) || '',
        importance: pickFirstString(question, ['importance']) || undefined,
      }))
      .filter((question) => question.question.length > 0);
  }
  return [];
};

const extractRunPlannerMetrics = (
  runtimeContext: Record<string, unknown>,
  runSteps: SkeletonRunStepRecord[],
) => {
  const plannerSummary = pickFirstString(runtimeContext, ['planner_summary']);
  const plannerSource = pickFirstString(runtimeContext, ['planner_source']);
  const stepTotal =
    asOptionalNumber(runtimeContext.step_count) || runSteps.length || null;
  const completedStepCount = runSteps.filter((step) => isCompletedStatus(step.status)).length;
  const activeStepCount = runSteps.filter((step) =>
    ['assigned', 'queued', 'leased', 'acked', 'running'].includes(String(step.status).toLowerCase()),
  ).length;
  const currentStep = runSteps
    .slice()
    .sort((left, right) => left.sequence_number - right.sequence_number)
    .find((step) => !['completed', 'failed', 'cancelled', 'blocked'].includes(String(step.status).toLowerCase()));
  const parallelGroups = new Set(
    runSteps
      .map((step) => pickFirstString(asUnknownRecord(step.input_payload), ['parallel_group']))
      .filter((value): value is string => Boolean(value)),
  );
  const activeSuggestedAgentIds = currentStep
    ? asStringArray(asUnknownRecord(currentStep.input_payload).suggested_agent_ids)
    : [];
  const clarificationQuestions = getPlannerQuestionsFromPayload([runtimeContext]);
  return {
    plannerSummary,
    plannerSource,
    stepTotal: stepTotal || 0,
    completedStepCount,
    activeStepCount,
    parallelGroupCount: parallelGroups.size,
    currentStepTitle: currentStep?.name || null,
    suggestedAgentIds: activeSuggestedAgentIds,
    needsClarification: clarificationQuestions.length > 0,
    clarificationQuestions,
  };
};

const toProjectTaskSummaryFromSkeleton = (
  task: SkeletonProjectTaskRecord,
): ProjectTaskSummary => {
  const payloads = [asUnknownRecord(task.input_payload), asUnknownRecord(task.output_payload)];

  return {
    id: task.project_task_id,
    title: task.title,
    status: toProjectStatus(task.status),
    priority: priorityToNumber(task.priority),
    updatedAt: task.updated_at,
    assignedAgentId: task.assignee_agent_id || null,
    assignedAgentName: getTaskAssigneeNameFromPayload(payloads),
    dependencyIds: getTaskDependenciesFromPayload(payloads),
    reviewStatus: getTaskReviewStatusFromPayload(payloads),
  };
};

const buildSkeletonProjectSummary = (
  project: SkeletonProjectRecord,
  tasks: SkeletonProjectTaskRecord[],
  runs: SkeletonRunRecord[],
  plans: SkeletonPlanRecord[] = [],
): ProjectSummary => {
  const configuration = asUnknownRecord(project.configuration);
  const lifecycle = resolveProjectLifecycle(project, tasks, runs);
  const latestPlan = [...plans].sort(
    (left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime(),
  )[0];
  const latestPlanDefinition = latestPlan ? asUnknownRecord(latestPlan.definition) : {};
  const latestRun = [...runs].sort(
    (left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime(),
  )[0];
  const latestTask = [...tasks].sort(
    (left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime(),
  )[0];
  const completedTasks = tasks.filter((task) => isCompletedStatus(task.status)).length;
  const failedTasks = tasks.filter((task) => isFailedStatus(task.status)).length;
  const updatedAt =
    latestIsoString([
      project.updated_at,
      ...tasks.map((task) => task.updated_at),
      ...runs.map((run) => run.updated_at),
    ]) || project.updated_at;

  return {
    id: project.project_id,
    title: project.name,
    summary:
      project.description ||
      latestPlan?.goal ||
      pickFirstString(latestPlanDefinition, ['summary', 'goal', 'instructions']) ||
      pickFirstString(configuration, ['summary', 'goal', 'instructions']) ||
      'No summary available yet.',
    status: lifecycle.status,
    progress: buildProgress(completedTasks, tasks.length, lifecycle.status),
    createdAt: project.created_at,
    updatedAt,
    startedAt:
      latestIsoString(
        runs.map((run) => run.started_at || null),
      ) || null,
    completedAt: lifecycle.completedAt,
    totalTasks: tasks.length,
    completedTasks,
    failedTasks,
    activeNodeCount: 0,
    needsClarification: tasks.some((task) => task.status.toLowerCase().includes('clarification')),
    latestSignal:
      latestRun?.error_message ||
      summarizeRecord(latestRun ? asUnknownRecord(latestRun.runtime_context) : null) ||
      latestTask?.error_message ||
      summarizeRecord(latestTask ? asUnknownRecord(latestTask.output_payload) : null) ||
      latestPlan?.goal ||
      project.description ||
      pickFirstString(configuration, ['summary', 'goal']) ||
      null,
  };
};

const toProjectAgentBindingFromSkeleton = (
  binding: SkeletonProjectAgentBindingRecord,
  agentNames: Map<string, { name: string; type?: string | null }>,
): ProjectAgentBinding => {
  const agent = agentNames.get(binding.agent_id);
  return {
    id: binding.binding_id,
    projectId: binding.project_id,
    agentId: binding.agent_id,
    agentName: agent?.name || binding.agent_id,
    agentType: agent?.type || null,
    roleHint: binding.role_hint || null,
    priority: binding.priority,
    status: toProjectStatus(binding.status),
    allowedStepKinds: binding.allowed_step_kinds || [],
    preferredSkills: binding.preferred_skills || [],
    preferredRuntimeTypes: binding.preferred_runtime_types || [],
    createdAt: binding.created_at,
    updatedAt: binding.updated_at,
  };
};

const toProvisioningProfileFromSkeleton = (
  profile: SkeletonAgentProvisioningProfileRecord,
): AgentProvisioningProfile => ({
  id: profile.profile_id,
  projectId: profile.project_id,
  stepKind: profile.step_kind,
  agentType: profile.agent_type,
  templateId: profile.template_id || null,
  defaultSkillIds: profile.default_skill_ids || [],
  defaultProvider: profile.default_provider || null,
  defaultModel: profile.default_model || null,
  runtimeType: profile.runtime_type,
  sandboxMode: profile.sandbox_mode,
  ephemeral: profile.ephemeral,
  createdAt: profile.created_at,
  updatedAt: profile.updated_at,
});

const buildProjectActivityFromSkeleton = (
  project: SkeletonProjectRecord,
  tasks: SkeletonProjectTaskRecord[],
  extensions: SkeletonExtensionRecord[],
  plans: SkeletonPlanRecord[] = [],
  projectSpace: SkeletonProjectSpaceRecord | null = null,
): ProjectActivityItem[] => {
  const projectItem: ProjectActivityItem = {
    id: `project-${project.project_id}`,
    title: 'Project updated',
    description: project.description || 'Project metadata synchronized.',
    timestamp: project.updated_at,
    level: activityLevelFromStatus(project.status),
  };

  const taskItems = tasks.map((task) => ({
    id: `task-${task.project_task_id}`,
    title: task.title,
    description:
      task.error_message ||
      summarizeRecord(asUnknownRecord(task.output_payload)) ||
      `${humanizeToken(task.status)} task update.`,
    timestamp: task.updated_at,
    level: activityLevelFromStatus(task.status),
    actor: getTaskAssigneeNameFromPayload([
      asUnknownRecord(task.input_payload),
      asUnknownRecord(task.output_payload),
    ]),
    taskId: task.project_task_id,
  }));

  const planItems: ProjectActivityItem[] = plans.map((plan) => ({
    id: `plan-${plan.plan_id}`,
    title: `Plan ${plan.name}`,
    description:
      plan.goal ||
      summarizeRecord(asUnknownRecord(plan.definition)) ||
      `${humanizeToken(plan.status)} v${plan.version} plan.`,
    timestamp: plan.updated_at,
    level: activityLevelFromStatus(plan.status),
  }));

  const extensionItems: ProjectActivityItem[] = extensions.map((extension) => ({
    id: `extension-${extension.extension_package_id}`,
    title: `Extension ${extension.name}`,
    description:
      extension.source_uri ||
      `${humanizeToken(extension.status)} ${humanizeToken(extension.package_type)} package.`,
    timestamp: extension.updated_at,
    level: activityLevelFromStatus(extension.status),
  }));

  const projectSpaceItems = projectSpace
    ? [{
        id: `project-space-${projectSpace.project_space_id}`,
        title: 'Project space updated',
        description:
          projectSpace.root_path ||
          projectSpace.storage_uri ||
          `${humanizeToken(projectSpace.status)} workspace synced.`,
        timestamp: projectSpace.last_synced_at || projectSpace.updated_at,
        level: activityLevelFromStatus(projectSpace.status) as ProjectActivityItem['level'],
      }]
    : [];

  return [
    projectItem,
    ...planItems,
    ...taskItems,
    ...extensionItems,
    ...projectSpaceItems,
  ]
    .sort((left, right) => new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime())
    .slice(0, 20);
};

const buildProjectDetailFromSkeleton = (
  project: SkeletonProjectRecord,
  tasks: SkeletonProjectTaskRecord[],
  runs: SkeletonRunRecord[],
  runSteps: SkeletonRunStepRecord[],
  extensions: SkeletonExtensionRecord[],
  plans: SkeletonPlanRecord[],
  projectSpace: SkeletonProjectSpaceRecord | null,
  agentBindings: SkeletonProjectAgentBindingRecord[],
  provisioningProfiles: SkeletonAgentProvisioningProfileRecord[],
): ProjectDetail => {
  const configuration = asUnknownRecord(project.configuration);
  const latestPlan = [...plans].sort(
    (left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime(),
  )[0];
  const latestPlanDefinition = latestPlan ? asUnknownRecord(latestPlan.definition) : {};
  const summary = buildSkeletonProjectSummary(project, tasks, runs, plans);
  const tasksByRun = groupByKey(tasks, (task) => task.run_id || null);
  const stepsByRun = groupByKey(runSteps, (step) => step.run_id);
  const deliverables = collectDeliverablesFromPayloads([
    configuration,
    ...plans.map((plan) => asUnknownRecord(plan.definition)),
    projectSpace ? asUnknownRecord(projectSpace.space_metadata) : {},
    ...tasks.map((task) => asUnknownRecord(task.output_payload)),
    ...runs.map((run) => asUnknownRecord(run.runtime_context)),
    ...runSteps.map((step) => asUnknownRecord(step.output_payload)),
    ...extensions.map((extension) => asUnknownRecord(extension.manifest)),
  ]);

  return {
    ...summary,
    instructions:
      pickFirstString(configuration, ['instructions', 'brief', 'goal', 'summary']) ||
      latestPlan?.goal ||
      pickFirstString(latestPlanDefinition, ['instructions', 'summary', 'goal']) ||
      project.description ||
      'No instructions available yet.',
    departmentId: pickFirstString(configuration, ['department_id', 'departmentId']),
    workspaceBucket:
      projectSpace?.storage_uri ||
      projectSpace?.root_path ||
      pickFirstString(configuration, ['workspace_bucket', 'workspaceBucket']),
    projectWorkspaceRoot: projectSpace?.root_path || null,
    configuration,
    tasks: tasks
      .map(toProjectTaskSummaryFromSkeleton)
      .sort((left, right) => right.priority - left.priority),
    runs: runs
      .map((run) =>
        buildRunSummaryFromSkeleton(
          run,
          project,
          tasksByRun.get(run.run_id) || [],
          stepsByRun.get(run.run_id) || [],
        ),
      )
      .sort(sortByUpdatedDescending),
    agents: [],
    agentBindings: agentBindings.map((binding) =>
      toProjectAgentBindingFromSkeleton(
        binding,
        new Map(),
      ),
    ),
    provisioningProfiles: provisioningProfiles.map(toProvisioningProfileFromSkeleton),
    deliverables,
    recentActivity: buildProjectActivityFromSkeleton(
      project,
      tasks,
      extensions,
      plans,
      projectSpace,
    ),
  };
};

const buildRunSummaryFromSkeleton = (
  run: SkeletonRunRecord,
  project: SkeletonProjectRecord | undefined,
  tasks: SkeletonProjectTaskRecord[],
  runSteps: SkeletonRunStepRecord[],
): RunSummary => {
  const lifecycle = resolveRunLifecycle(run, tasks, runSteps);
  const runtimeContext = asUnknownRecord(run.runtime_context);
  const failedStep = runSteps
    .slice()
    .sort((left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime())
    .find((step) => isFailedStatus(step.status) || step.error_message);
  const failedTask = tasks
    .slice()
    .sort((left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime())
    .find((task) => isFailedStatus(task.status) || task.error_message);
  const primaryTask = tasks
    .slice()
    .sort((left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime())[0];
  const taskId =
    pickFirstString(runtimeContext, ['project_task_id']) ||
    primaryTask?.project_task_id ||
    null;
  const taskTitle =
    pickFirstString(runtimeContext, ['task_title']) ||
    primaryTask?.title ||
    null;
  const executionMode =
    pickFirstString(runtimeContext, ['execution_mode']) ||
    pickFirstString(asUnknownRecord(primaryTask?.input_payload), ['execution_mode']) ||
    (pickFirstString(runtimeContext, ['runtime_type'])?.startsWith('external') ? 'external_runtime' : null) ||
    null;
  const failureReason =
    run.error_message ||
    failedTask?.error_message ||
    failedStep?.error_message ||
    null;
  const handledAt = getRunHandledAtFromRuntimeContext(runtimeContext);
  const latestSignal =
    failureReason ||
    summarizeRecord(runtimeContext) ||
    runSteps
      .slice()
      .sort(
        (left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime(),
      )[0]?.error_message ||
    null;
  const handledSignature = getRunHandledSignatureFromRuntimeContext(runtimeContext);
  const alertSignature = buildRunAlertSignature({
    status: lifecycle.status,
    taskId,
    taskTitle,
    failureReason,
    latestSignal,
  });
  const plannerMetrics = extractRunPlannerMetrics(runtimeContext, runSteps);

  return {
    id: run.run_id,
    projectId: run.project_id,
    projectTitle: project?.name || 'Untitled Project',
    status: lifecycle.status,
    createdAt: run.created_at,
    triggerSource: run.trigger_source,
    executionMode,
    plannerSource: plannerMetrics.plannerSource,
    plannerSummary: plannerMetrics.plannerSummary,
    stepTotal: plannerMetrics.stepTotal,
    completedStepCount: plannerMetrics.completedStepCount,
    activeStepCount: plannerMetrics.activeStepCount,
    parallelGroupCount: plannerMetrics.parallelGroupCount,
    currentStepTitle: plannerMetrics.currentStepTitle,
    suggestedAgentIds: plannerMetrics.suggestedAgentIds,
    needsClarification: plannerMetrics.needsClarification,
    clarificationQuestions: plannerMetrics.clarificationQuestions,
    taskId,
    taskTitle,
    failureReason,
    handledAt,
    handledSignature: handledSignature || null,
    alertSignature,
    startedAt: run.started_at || null,
    completedAt: lifecycle.completedAt,
    updatedAt: run.updated_at,
    totalTasks: tasks.length,
    completedTasks: tasks.filter((task) => isCompletedStatus(task.status)).length,
    failedTasks: tasks.filter((task) => isFailedStatus(task.status)).length,
    externalAgentCount: new Set(
      runSteps
        .map((step) => asUnknownRecord(step.input_payload))
        .map((payload) => ({
          agentId: pickFirstString(payload, ['assigned_agent_id']),
          runtimeType: pickFirstString(payload, ['runtime_type']),
        }))
        .filter(
          (item) =>
            item.agentId &&
            (item.runtimeType?.startsWith('external') || item.runtimeType === 'remote_session'),
        )
        .map((item) => item.agentId),
    ).size,
    latestSignal,
  };
};

const activityFromRunStep = (
  step: SkeletonRunStepRecord,
): ProjectActivityItem => ({
  id: step.run_step_id,
  title: step.name,
  description:
    step.error_message ||
    summarizeRecord(asUnknownRecord(step.output_payload)) ||
    `${humanizeToken(step.status)} ${humanizeToken(step.step_type)} step.`,
  timestamp: step.completed_at || step.started_at || step.updated_at || step.created_at,
  level: activityLevelFromStatus(step.status),
  taskId: step.project_task_id || null,
});

const buildRunDetailFromSkeleton = (
  run: SkeletonRunRecord,
  project: SkeletonProjectRecord,
  tasks: SkeletonProjectTaskRecord[],
  steps: SkeletonRunStepRecord[],
  plans: SkeletonPlanRecord[] = [],
  projectSpace: SkeletonProjectSpaceRecord | null = null,
  externalDispatches: SkeletonExternalAgentDispatchRecord[] = [],
): RunDetail => {
  const summary = buildRunSummaryFromSkeleton(run, project, tasks, steps);
  const timeline: ProjectActivityItem[] = [
    {
      id: `run-${run.run_id}-created`,
      title: 'Run created',
      description: `Triggered via ${run.trigger_source}.`,
      timestamp: run.created_at,
      level: 'info' as const,
    },
    ...(run.started_at
      ? [{
          id: `run-${run.run_id}-started`,
          title: 'Run started',
          description: 'Execution is in progress.',
          timestamp: run.started_at,
          level: 'info' as const,
        }]
      : []),
    ...steps.map((step) => activityFromRunStep(step)),
    ...((run.completed_at || isTerminalRunStatus(run.status) || Boolean(summary.failureReason))
      ? [{
          id: `run-${run.run_id}-status`,
          title: `Run ${humanizeToken(run.status)}`,
          description:
            summary.failureReason ||
            summarizeRecord(asUnknownRecord(run.runtime_context)) ||
            'Run completed.',
          timestamp: run.completed_at || run.updated_at,
          level: activityLevelFromStatus(run.status) as ProjectActivityItem['level'],
        }]
      : []),
  ].sort((left, right) => new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime());

  const projectSummary = buildSkeletonProjectSummary(project, tasks, [run], plans);
  const deliverables = collectDeliverablesFromPayloads([
    asUnknownRecord(project.configuration),
    ...plans.map((plan) => asUnknownRecord(plan.definition)),
    projectSpace ? asUnknownRecord(projectSpace.space_metadata) : {},
    asUnknownRecord(run.runtime_context),
    ...tasks.map((task) => asUnknownRecord(task.output_payload)),
    ...steps.map((step) => asUnknownRecord(step.output_payload)),
  ]);

  const runtimeContext = asUnknownRecord(run.runtime_context);
  const assignmentCandidate = runtimeContext.agent_assignment ?? runtimeContext.executor_assignment;
  const assignment = assignmentCandidate && typeof assignmentCandidate === "object" ? asUnknownRecord(assignmentCandidate) : null;
  const runWorkspace = runtimeContext.run_workspace && typeof runtimeContext.run_workspace === "object" ? asUnknownRecord(runtimeContext.run_workspace) : null;
  return {
    ...summary,
    projectSummary: projectSummary.summary,
    timeline,
    deliverables,
    runWorkspaceRoot: pickFirstString(runWorkspace || {}, ['root_path']),
    executorAssignment: assignment ? {
      executorKind: pickFirstString(assignment, ['executor_kind']),
      agentId: pickFirstString(assignment, ['agent_id']),
      selectionReason: pickFirstString(assignment, ['selection_reason']),
      provisionedAgent: asOptionalBoolean(assignment.provisioned_agent) || false,
      runtimeType: pickFirstString(assignment, ['runtime_type']),
    } : null,
    externalDispatches: externalDispatches.map(toExternalAgentDispatchFromSkeleton),
  };
};

const buildTaskDetailFromSkeleton = (
  project: SkeletonProjectRecord,
  task: SkeletonProjectTaskRecord,
  runSteps: SkeletonRunStepRecord[],
): ProjectTaskDetail => {
  const payloads = [asUnknownRecord(task.input_payload), asUnknownRecord(task.output_payload)];
  const metadata: ProjectTaskMetadataItem[] = [];

  if (task.plan_id) {
    metadata.push({ label: 'Plan', value: task.plan_id });
  }
  if (task.run_id) {
    metadata.push({ label: 'Run', value: task.run_id });
  }
  const reviewStatus = getTaskReviewStatusFromPayload(payloads);
  if (reviewStatus) {
    metadata.push({ label: 'Review', value: humanizeToken(reviewStatus) });
  }
  const assignmentSource = pickFirstString(asUnknownRecord(task.input_payload), ['assignment_source']);
  if (assignmentSource) {
    metadata.push({ label: 'Assignment source', value: assignmentSource });
  }
  const assignedAgentName = getTaskAssigneeNameFromPayload(payloads);
  if (assignedAgentName) {
    metadata.push({ label: 'Assigned Agent', value: assignedAgentName });
  }
  const executorKind = pickFirstString(asUnknownRecord(task.input_payload), ['executor_kind', 'step_kind']);
  if (executorKind) {
    metadata.push({ label: 'Executor Kind', value: humanizeToken(executorKind) });
  }
  const selectionReason = pickFirstString(asUnknownRecord(task.input_payload), ['selection_reason']);
  if (selectionReason) {
    metadata.push({ label: 'Scheduler Decision', value: selectionReason });
  }
  const runtimeType = pickFirstString(asUnknownRecord(task.input_payload), ['runtime_type']);
  if (runtimeType) {
    metadata.push({ label: 'Runtime Type', value: humanizeToken(runtimeType) });
  }
  const executionNodeName = pickFirstString(asUnknownRecord(task.input_payload), ['execution_node_name']);
  if (executionNodeName) {
    metadata.push({ label: 'Execution Node', value: executionNodeName });
  }
  const executionMode = getTaskExecutionModeFromPayload(payloads);
  if (executionMode) {
    metadata.push({ label: 'Execution Mode', value: humanizeToken(executionMode) });
  }
  const runWorkspaceRoot = pickFirstString(asUnknownRecord(task.output_payload), ['run_workspace_root']);
  if (runWorkspaceRoot) {
    metadata.push({ label: 'Run Workspace', value: runWorkspaceRoot });
  }
  const plannerSummary = pickFirstString(asUnknownRecord(task.input_payload), ['planner_summary']);
  const plannerSource = pickFirstString(asUnknownRecord(task.input_payload), ['planner_source']);
  const stepTotal = asOptionalNumber(asUnknownRecord(task.input_payload).step_count) || runSteps.length || 0;
  const completedStepCount = runSteps.filter((step) => isCompletedStatus(step.status)).length;
  const activeStepCount = runSteps.filter((step) =>
    ['assigned', 'queued', 'leased', 'acked', 'running'].includes(String(step.status).toLowerCase()),
  ).length;
  const currentStep = runSteps
    .slice()
    .sort((left, right) => left.sequence_number - right.sequence_number)
    .find((step) => !['completed', 'failed', 'cancelled', 'blocked'].includes(String(step.status).toLowerCase()));
  const parallelGroupCount = new Set(
    runSteps
      .map((step) => pickFirstString(asUnknownRecord(step.input_payload), ['parallel_group']))
      .filter((value): value is string => Boolean(value)),
  ).size;
  const clarificationQuestions = getPlannerQuestionsFromPayload([asUnknownRecord(task.input_payload)]);

  const events = runSteps
    .filter((step) => step.project_task_id === task.project_task_id)
    .map((step) => activityFromRunStep(step, new Map<string, string>()))
    .sort((left, right) => new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime());

  return {
    ...toProjectTaskSummaryFromSkeleton(task),
    projectId: project.project_id,
    projectTitle: project.name,
    projectStatus: toProjectStatus(project.status),
    description: task.description || task.title,
    executionMode,
    plannerSource,
    plannerSummary,
    stepTotal,
    completedStepCount,
    activeStepCount,
    parallelGroupCount,
    currentStepTitle: currentStep?.name || null,
    suggestedAgentIds: currentStep ? asStringArray(asUnknownRecord(currentStep.input_payload).suggested_agent_ids) : [],
    clarificationQuestions,
    acceptanceCriteria: getTaskAcceptanceFromPayload(payloads),
    assignedSkillNames: getTaskSkillNamesFromPayload(payloads),
    latestResult:
      task.error_message || summarizeRecord(asUnknownRecord(task.output_payload)) || null,
    metadata,
    events:
      events.length > 0
        ? events
        : [
            {
              id: `task-${task.project_task_id}`,
              title: task.title,
              description:
                task.error_message ||
                summarizeRecord(asUnknownRecord(task.output_payload)) ||
                `${humanizeToken(task.status)} task update.`,
              timestamp: task.updated_at,
              level: activityLevelFromStatus(task.status),
              taskId: task.project_task_id,
            },
          ],
  };
};

const toExternalAgentDispatchFromSkeleton = (
  dispatch: SkeletonExternalAgentDispatchRecord,
) => ({
  id: dispatch.dispatch_id,
  agentId: dispatch.agent_id,
  bindingId: dispatch.binding_id,
  projectId: dispatch.project_id || '',
  runId: dispatch.run_id || '',
  runStepId: dispatch.run_step_id || '',
  sourceType: dispatch.source_type,
  sourceId: dispatch.source_id,
  runtimeType: dispatch.runtime_type,
  status: toProjectStatus(dispatch.status),
  errorMessage: dispatch.error_message || null,
  requestPayload: dispatch.request_payload || {},
  resultPayload: dispatch.result_payload || {},
  ackedAt: dispatch.acked_at || null,
  startedAt: dispatch.started_at || null,
  completedAt: dispatch.completed_at || null,
  expiresAt: dispatch.expires_at || null,
  createdAt: dispatch.created_at,
  updatedAt: dispatch.updated_at,
});

const toPlatformExtensionFromSkeleton = (
  extension: SkeletonExtensionRecord,
): PlatformExtension => {
  const manifest = asUnknownRecord(extension.manifest);
  const tools = asStringArray(manifest.tools);

  return {
    id: extension.extension_package_id,
    name: extension.name,
    description: pickFirstString(manifest, ['description', 'summary']),
    status: toExtensionStatus(extension.status),
    transport:
      pickFirstString(manifest, ['transport', 'transport_type']) || extension.package_type,
    toolCount:
      asOptionalNumber(manifest.tool_count) ||
      asStringArray(manifest.capabilities).length ||
      tools.length,
    isActive:
      (asOptionalBoolean(manifest.enabled) ?? null) ?? !['disabled', 'error'].includes(extension.status.toLowerCase()),
    endpoint:
      extension.source_uri || pickFirstString(manifest, ['endpoint', 'url', 'command', 'source_uri']),
    lastConnectedAt: pickFirstString(manifest, ['last_connected_at', 'lastConnectedAt']),
    lastSyncAt:
      pickFirstString(manifest, ['last_sync_at', 'lastSyncAt']) || extension.updated_at,
    errorMessage: pickFirstString(manifest, ['error_message', 'errorMessage']),
  };
};

const listProjectsFromSkeleton = async (): Promise<ProjectSummary[]> => {
  const [projects, tasks, runs] = await Promise.all([
    skeletonApi.listProjects(),
    skeletonApi.listProjectTasks(),
    skeletonApi.listRuns(),
  ]);

  const tasksByProject = groupByKey(tasks, (task) => task.project_id);
  const runsByProject = groupByKey(runs, (run) => run.project_id);

  return projects
    .map((project) =>
      buildSkeletonProjectSummary(
        project,
        tasksByProject.get(project.project_id) || [],
        runsByProject.get(project.project_id) || [],
      ),
    )
    .sort(sortByUpdatedDescending);
};

const getProjectDetailFromSkeleton = async (projectId: string): Promise<ProjectDetail> => {
  const [project, tasks, runs, runSteps, extensions, plans, projectSpace, agentBindings, provisioningProfiles] = await Promise.all([
    skeletonApi.getProject(projectId),
    skeletonApi.listProjectTasks(projectId),
    skeletonApi.listRuns(projectId),
    skeletonApi.listRunSteps(),
    skeletonApi.listExtensions(projectId),
    skeletonApi.listPlans(projectId),
    skeletonApi.getProjectSpace(projectId),
    skeletonApi.listProjectAgentBindings(projectId),
    skeletonApi.listAgentProvisioningProfiles(projectId),
  ]);
  const runIds = new Set(runs.map((run) => run.run_id));

  return buildProjectDetailFromSkeleton(
    project,
    tasks,
    runs,
    runSteps.filter((step) => runIds.has(step.run_id)),
    extensions,
    plans,
    projectSpace,
    agentBindings,
    provisioningProfiles,
  );
};

const getProjectTaskDetailFromSkeleton = async (
  projectId: string,
  taskId: string,
): Promise<ProjectTaskDetail> => {
  const [project, task] = await Promise.all([
    skeletonApi.getProject(projectId),
    skeletonApi.getProjectTask(taskId),
  ]);
  const runSteps = task.run_id ? await skeletonApi.listRunSteps(task.run_id) : [];

  return buildTaskDetailFromSkeleton(project, task, runSteps);
};

const listRunsFromSkeleton = async (): Promise<RunSummary[]> => {
  const [runs, projects, tasks, runSteps] = await Promise.all([
    skeletonApi.listRuns(),
    skeletonApi.listProjects(),
    skeletonApi.listProjectTasks(),
    skeletonApi.listRunSteps(),
  ]);

  const projectById = new Map(projects.map((project) => [project.project_id, project]));
  const tasksByRun = groupByKey(tasks, (task) => task.run_id || null);
  const stepsByRun = groupByKey(runSteps, (step) => step.run_id);

  return runs
    .map((run) =>
      buildRunSummaryFromSkeleton(
        run,
        projectById.get(run.project_id),
        tasksByRun.get(run.run_id) || [],
        stepsByRun.get(run.run_id) || [],
      ),
    )
    .sort(sortByUpdatedDescending);
};

const getRunDetailFromSkeleton = async (runId: string): Promise<RunDetail> => {
  const run = await skeletonApi.getRun(runId);
  const [project, tasks, steps, externalDispatches] = await Promise.all([
    skeletonApi.getProject(run.project_id),
    skeletonApi.listProjectTasks(run.project_id),
    skeletonApi.listRunSteps(runId),
    skeletonApi.listRunExternalDispatches(run.run_id),
  ]);

  return buildRunDetailFromSkeleton(
    run,
    project,
    tasks.filter((task) => task.run_id === runId),
    steps,
    [],
    null,
    externalDispatches,
  );
};

const listExtensionsFromSkeleton = async (): Promise<PlatformExtension[]> => {
  const extensions = await skeletonApi.listExtensions();
  return extensions.map(toPlatformExtensionFromSkeleton);
};

export const projectExecutionApi = {
  async listProjects(): Promise<PlatformQueryResult<ProjectSummary[]>> {
    try {
      const data = await listProjectsFromSkeleton();
      return { data, fallback: false };
    } catch (error) {
      return {
        data: ENABLE_PROJECT_EXECUTION_SEEDS ? fallbackProjectSummaries : [],
        fallback: ENABLE_PROJECT_EXECUTION_SEEDS,
        error: asErrorMessage(error, 'Failed to load projects'),
      };
    }
  },

  async getProjectDetail(projectId: string): Promise<PlatformQueryResult<ProjectDetail>> {
    try {
      const data = await getProjectDetailFromSkeleton(projectId);
      return {
        data,
        fallback: false,
      };
    } catch (error) {
      if (!ENABLE_PROJECT_EXECUTION_SEEDS) {
        throw error;
      }
      const fallbackSeed = fallbackProjectMap.get(projectId);
      if (!fallbackSeed) {
        throw error;
      }

      return {
        data: seedToProjectDetail(fallbackSeed),
        fallback: true,
        error: asErrorMessage(error, 'Failed to load project detail'),
      };
    }
  },

  async getProjectTaskDetail(
    projectId: string,
    taskId: string,
  ): Promise<PlatformQueryResult<ProjectTaskDetail>> {
    try {
      const data = await getProjectTaskDetailFromSkeleton(projectId, taskId);
      return {
        data,
        fallback: false,
      };
    } catch (error) {
      if (!ENABLE_PROJECT_EXECUTION_SEEDS) {
        throw error;
      }
      const fallbackSeed = fallbackProjectMap.get(projectId);
      if (!fallbackSeed) {
        throw error;
      }

      return {
        data: seedToTaskDetail(fallbackSeed, taskId),
        fallback: true,
        error: asErrorMessage(error, 'Failed to load task detail'),
      };
    }
  },

  async listRuns(): Promise<PlatformQueryResult<RunSummary[]>> {
    try {
      const data = await listRunsFromSkeleton();
      return { data, fallback: false };
    } catch (error) {
      return {
        data: ENABLE_PROJECT_EXECUTION_SEEDS ? fallbackRunSummaries : [],
        fallback: ENABLE_PROJECT_EXECUTION_SEEDS,
        error: asErrorMessage(error, 'Failed to load runs'),
      };
    }
  },

  async getRunDetail(runId: string): Promise<PlatformQueryResult<RunDetail>> {
    try {
      const data = await getRunDetailFromSkeleton(runId);
      return {
        data,
        fallback: false,
      };
    } catch (error) {
      if (!ENABLE_PROJECT_EXECUTION_SEEDS) {
        throw error;
      }
      const fallbackSeed = fallbackProjectMap.get(runId);
      if (!fallbackSeed) {
        throw error;
      }

      return {
        data: seedToRunDetail(fallbackSeed),
        fallback: true,
        error: asErrorMessage(error, 'Failed to load run detail'),
      };
    }
  },

  async getSkillHubSnapshot(): Promise<PlatformQueryResult<SkillHubSnapshot>> {
    const [overviewResult, skillsResult, candidatesResult, bindingsResult, storeResult] =
      await Promise.allSettled([
        skillsApi.getOverviewStats(),
        skillsApi.listPage({ limit: 6 }),
        skillsApi.getCandidates({ limit: 6 }),
        skillsApi.getBindings({ limit: 6 }),
        skillsApi.getStore(),
      ]);

    const failedCore =
      overviewResult.status === 'rejected' &&
      skillsResult.status === 'rejected' &&
      candidatesResult.status === 'rejected' &&
      bindingsResult.status === 'rejected';

    if (failedCore) {
      return {
        data: fallbackSkillHub,
        fallback: true,
        error: 'Failed to load skill hub snapshot',
      };
    }

    const featuredSkills =
      skillsResult.status === 'fulfilled'
        ? skillsResult.value.items
            .map(toSkillItem)
            .sort((left, right) => right.executionCount - left.executionCount)
        : fallbackSkillHub.featuredSkills;

    const pendingCandidates =
      candidatesResult.status === 'fulfilled'
        ? candidatesResult.value
            .filter((candidate) => candidate.status !== 'published')
            .map(toCandidateItem)
        : fallbackSkillHub.pendingCandidates;

    const recentBindings =
      bindingsResult.status === 'fulfilled'
        ? bindingsResult.value
            .map(toBindingItem)
            .sort(
              (left, right) =>
                new Date(right.updatedAt || 0).getTime() - new Date(left.updatedAt || 0).getTime(),
            )
        : fallbackSkillHub.recentBindings;

    let overview: SkillHubOverview;
    if (overviewResult.status === 'fulfilled') {
      overview = {
        totalSkills: overviewResult.value.total_skills,
        activeSkills: overviewResult.value.active_skills,
        candidateCount: pendingCandidates.length,
        bindingCount: recentBindings.length,
        storeItems: storeResult.status === 'fulfilled' ? storeResult.value.length : 0,
      };
    } else {
      overview = {
        totalSkills: featuredSkills.length,
        activeSkills: featuredSkills.length,
        candidateCount: pendingCandidates.length,
        bindingCount: recentBindings.length,
        storeItems: storeResult.status === 'fulfilled' ? storeResult.value.length : 0,
      };
    }

    return {
      data: {
        overview,
        featuredSkills,
        pendingCandidates,
        recentBindings,
      },
      fallback: false,
    };
  },

  async listExtensions(): Promise<PlatformQueryResult<PlatformExtension[]>> {
    try {
      const data = await listExtensionsFromSkeleton();
      return { data, fallback: false };
    } catch (error) {
      return {
        data: fallbackExtensions,
        fallback: true,
        error: asErrorMessage(error, 'Failed to load extensions'),
      };
    }
  },

  async createProject(input: { name: string; description?: string | null }): Promise<string> {
    const project = await skeletonApi.createProject(input);
    return project.project_id;
  },

  async deleteProject(projectId: string): Promise<void> {
    await skeletonApi.deleteProject(projectId);
  },

  async updateProject(projectId: string, payload: Partial<{ name: string; description?: string | null; status: string; configuration: Record<string, unknown>; }>): Promise<string> {
    const project = await skeletonApi.updateProject(projectId, payload);
    return project.project_id;
  },

  async listProjectAgentBindings(projectId: string): Promise<ProjectAgentBinding[]> {
    const [agents, bindings] = await Promise.all([agentsApi.getAll(), skeletonApi.listProjectAgentBindings(projectId)]);
    const agentNames = new Map(agents.map((agent) => [agent.id, { name: agent.name, type: agent.type }]));
    return bindings.map((binding) => toProjectAgentBindingFromSkeleton(binding, agentNames));
  },

  async createProjectAgentBinding(projectId: string, payload: { agentId: string; roleHint?: string | null; priority?: number; preferredRuntimeTypes?: string[]; }): Promise<ProjectAgentBinding> {
    const [agents, binding] = await Promise.all([agentsApi.getAll(), skeletonApi.createProjectAgentBinding(projectId, payload)]);
    const agentNames = new Map(agents.map((agent) => [agent.id, { name: agent.name, type: agent.type }]));
    return toProjectAgentBindingFromSkeleton(binding, agentNames);
  },

  async deleteProjectAgentBinding(projectId: string, bindingId: string): Promise<void> {
    await skeletonApi.deleteProjectAgentBinding(projectId, bindingId);
  },

  async listAgentProvisioningProfiles(projectId: string): Promise<AgentProvisioningProfile[]> {
    const profiles = await skeletonApi.listAgentProvisioningProfiles(projectId);
    return profiles.map(toProvisioningProfileFromSkeleton);
  },

  async listProjectWorkspaceFiles(
    projectId: string,
    path?: string,
    recursive = false,
    options?: { suppressErrorToast?: boolean },
  ): Promise<AgentSessionWorkspaceFile[]> {
    return skeletonApi.listProjectWorkspaceFiles(projectId, path, recursive, options);
  },

  async downloadProjectWorkspaceFile(
    projectId: string,
    path: string,
    options?: { suppressErrorToast?: boolean },
  ): Promise<Blob> {
    return skeletonApi.downloadProjectWorkspaceFile(projectId, path, options);
  },

  async listRunWorkspaceFiles(
    runId: string,
    path?: string,
    recursive = false,
    options?: { suppressErrorToast?: boolean },
  ): Promise<AgentSessionWorkspaceFile[]> {
    return skeletonApi.listRunWorkspaceFiles(runId, path, recursive, options);
  },

  async downloadRunWorkspaceFile(
    runId: string,
    path: string,
    options?: { suppressErrorToast?: boolean },
  ): Promise<Blob> {
    return skeletonApi.downloadRunWorkspaceFile(runId, path, options);
  },

  async rescheduleRun(runId: string): Promise<RunDetail> {
    await skeletonApi.scheduleRun(runId);
    return getRunDetailFromSkeleton(runId);
  },

  async markRunHandled(
    runId: string,
    input: { handledAt: string; handledByUserId?: string | null; handledSignature: string },
  ): Promise<void> {
    const run = await skeletonApi.getRun(runId);
    const runtimeContext = asUnknownRecord(run.runtime_context);
    const alertState = asUnknownRecord(runtimeContext.alert_state);
    await skeletonApi.updateRun(runId, {
      runtimeContext: {
        ...runtimeContext,
        alert_state: {
          ...alertState,
          handled_at: input.handledAt,
          handled_by_user_id: input.handledByUserId || null,
          handled_signature: input.handledSignature,
        },
      },
    });
  },

  async deleteProjectTask(taskId: string): Promise<void> {
    await skeletonApi.deleteProjectTask(taskId);
  },

  async createProjectTask(input: {
    projectId: string;
    title: string;
    description?: string | null;
    executionMode?: ProjectExecutionMode;
  }): Promise<string> {
    const existingTasks = await skeletonApi.listProjectTasks(input.projectId);
    const task = await skeletonApi.createProjectTask({
      projectId: input.projectId,
      title: input.title,
      description: input.description || undefined,
      sortOrder: existingTasks.length,
      executionMode: input.executionMode,
    });
    return task.project_task_id;
  },

  async createProjectTaskAndLaunchRun(input: {
    projectId: string;
    title: string;
    description?: string | null;
    executionMode?: ProjectExecutionMode;
  }): Promise<{ taskId: string; runId: string | null; needsClarification?: boolean }> {
    const bundle = await skeletonApi.createProjectTaskAndLaunchRun(input);
    return {
      taskId: bundle.task.project_task_id,
      runId: bundle.run?.run_id || null,
      needsClarification: Boolean(bundle.needs_clarification),
    };
  },

  async launchTaskRun(input: {
    projectId: string;
    taskId: string;
    title: string;
    description?: string | null;
    executionMode?: ProjectExecutionMode;
  }): Promise<{ runId: string | null; needsClarification?: boolean }> {
    const response = await apiClient.post<SkeletonTaskLaunchBundleRecord>(
      `/project-tasks/${input.taskId}/launch`,
      {
        project_id: input.projectId,
        title: input.title,
        description: input.description || undefined,
        priority: 'normal',
        execution_mode: input.executionMode || 'auto',
        input_payload: {
          execution_mode: input.executionMode || 'auto',
        },
      },
      skeletonRequestConfig,
    );
    return {
      runId: response.data.run?.run_id || null,
      needsClarification: Boolean(response.data.needs_clarification),
    };
  },
};
