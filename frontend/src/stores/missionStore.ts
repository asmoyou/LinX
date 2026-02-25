import { create } from 'zustand';
import { missionsApi } from '../api/missions';
import type {
  Mission,
  MissionEvent,
  MissionTask,
  MissionAgent,
  MissionAttachment,
  MissionConfig,
  MissionStatus,
  MissionSettings,
} from '../types/mission';

const normalizeMissionStatus = (mission: Mission): Mission => {
  if (
    mission.status === 'completed' &&
    mission.total_tasks > 0 &&
    (mission.completed_tasks < mission.total_tasks || mission.failed_tasks > 0)
  ) {
    return {
      ...mission,
      status: mission.failed_tasks > 0 ? 'failed' : 'executing',
    };
  }
  return mission;
};

const getErrorMessage = (error: unknown, fallback: string): string => {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  if (typeof error === 'string' && error) {
    return error;
  }
  return fallback;
};

const RUN_BOUNDARY_EVENT_TYPES = new Set([
  'MISSION_STARTED',
  'MISSION_RETRY_REQUESTED',
  'MISSION_PARTIAL_RETRY_REQUESTED',
]);
const CLARIFICATION_REQUEST_EVENT_TYPES = new Set([
  'USER_CLARIFICATION_REQUESTED',
  'clarification_request',
]);
const CLARIFICATION_RESPONSE_EVENT_TYPES = new Set(['clarification_response']);
const TASK_EVENT_TYPES = new Set([
  'TASK_STARTED',
  'TASK_COMPLETED',
  'TASK_FAILED',
  'TASK_BLOCKED',
  'TASK_REVIEWED',
  'TASK_REVIEW',
  'TASK_AGENT_ASSIGNED',
  'TASK_AGENT_ESCALATED',
  'TASK_ATTEMPT_FAILED',
]);

const normalizeEventType = (eventType: string): string => eventType.trim().toUpperCase();

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const getEventString = (
  eventData: Record<string, unknown>,
  key: string
): string | undefined => {
  const value = eventData[key];
  if (typeof value !== 'string') return undefined;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
};

const getEventNumber = (
  eventData: Record<string, unknown>,
  key: string
): number | undefined => {
  const value = eventData[key];
  if (typeof value !== 'number' || !Number.isFinite(value)) return undefined;
  return value;
};

const getEventBoolean = (
  eventData: Record<string, unknown>,
  key: string
): boolean | undefined => {
  const value = eventData[key];
  if (typeof value !== 'boolean') return undefined;
  return value;
};

const getEventStringList = (
  eventData: Record<string, unknown>,
  key: string
): string[] => {
  const value = eventData[key];
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is string => typeof item === 'string')
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
};

const applyTaskEventUpdate = (task: MissionTask, event: MissionEvent): MissionTask => {
  const eventType = normalizeEventType(event.event_type);
  const eventData = isRecord(event.event_data) ? event.event_data : {};
  const eventMessage = typeof event.message === 'string' ? event.message.trim() : '';

  let nextTask = task;
  let nextTaskMetadata = isRecord(task.task_metadata) ? { ...task.task_metadata } : {};
  let nextTaskResult = isRecord(task.result) ? { ...task.result } : {};
  let taskMetadataChanged = false;
  let taskResultChanged = false;

  const setStatus = (status: string) => {
    if (nextTask.status === status) return;
    nextTask = { ...nextTask, status };
  };

  const setAssignedAgent = (agentId?: string, agentName?: string) => {
    if (
      !agentId &&
      !agentName
    ) {
      return;
    }
    const nextAssignedAgentId = agentId ?? nextTask.assigned_agent_id;
    const nextAssignedAgentName = agentName ?? nextTask.assigned_agent_name;
    if (
      nextAssignedAgentId === nextTask.assigned_agent_id &&
      nextAssignedAgentName === nextTask.assigned_agent_name
    ) {
      return;
    }
    nextTask = {
      ...nextTask,
      assigned_agent_id: nextAssignedAgentId,
      assigned_agent_name: nextAssignedAgentName,
    };
  };

  const setTaskMetadata = (key: string, value: unknown) => {
    if (nextTaskMetadata[key] === value) return;
    nextTaskMetadata[key] = value;
    taskMetadataChanged = true;
  };

  const deleteTaskMetadata = (key: string) => {
    if (!(key in nextTaskMetadata)) return;
    delete nextTaskMetadata[key];
    taskMetadataChanged = true;
  };

  const setTaskResult = (key: string, value: unknown) => {
    if (nextTaskResult[key] === value) return;
    nextTaskResult[key] = value;
    taskResultChanged = true;
  };

  const deleteTaskResult = (key: string) => {
    if (!(key in nextTaskResult)) return;
    delete nextTaskResult[key];
    taskResultChanged = true;
  };

  const mergeFailureMessage = () => {
    const failureMessage = getEventString(eventData, 'error') || eventMessage || undefined;
    if (!failureMessage) return;
    setTaskResult('error', failureMessage);
    setTaskResult('last_error', failureMessage);
  };

  switch (eventType) {
    case 'TASK_STARTED': {
      setStatus('in_progress');
      setAssignedAgent(getEventString(eventData, 'agent_id'), getEventString(eventData, 'agent_name'));
      deleteTaskMetadata('blocked_by_failed_dependencies');
      if (String(nextTaskMetadata.review_status || '').toLowerCase() === 'blocked_by_dependency') {
        deleteTaskMetadata('review_status');
      }
      deleteTaskResult('error');
      break;
    }
    case 'TASK_COMPLETED': {
      setStatus('completed');
      setTaskMetadata('review_status', 'pending');
      deleteTaskMetadata('blocked_by_failed_dependencies');
      deleteTaskMetadata('review_feedback');
      deleteTaskResult('error');
      break;
    }
    case 'TASK_FAILED': {
      setStatus('failed');
      mergeFailureMessage();
      break;
    }
    case 'TASK_BLOCKED': {
      setStatus('pending');
      setTaskMetadata('review_status', 'blocked_by_dependency');
      const blockedBy = getEventStringList(eventData, 'blocked_by');
      if (blockedBy.length > 0) {
        setTaskMetadata('blocked_by_failed_dependencies', blockedBy);
      }
      mergeFailureMessage();
      break;
    }
    case 'TASK_REVIEWED':
    case 'TASK_REVIEW': {
      const verdict = (getEventString(eventData, 'verdict') || '').toUpperCase();
      if (verdict === 'PASS') {
        setTaskMetadata('review_status', 'approved');
        deleteTaskMetadata('review_feedback');
        deleteTaskMetadata('blocked_by_failed_dependencies');
      } else if (verdict === 'FAIL') {
        setStatus('failed');
        setTaskMetadata('review_status', 'rework_required');
        const reviewFeedback =
          getEventString(eventData, 'review_feedback') ||
          getEventString(eventData, 'feedback') ||
          getEventString(eventData, 'reason') ||
          eventMessage ||
          undefined;
        if (reviewFeedback) {
          setTaskMetadata('review_feedback', reviewFeedback);
        }
      } else if (verdict === 'BLOCKED') {
        setStatus('pending');
        setTaskMetadata('review_status', 'blocked_by_dependency');
        const blockedBy = getEventStringList(eventData, 'blocked_by');
        if (blockedBy.length > 0) {
          setTaskMetadata('blocked_by_failed_dependencies', blockedBy);
        }
      }
      break;
    }
    case 'TASK_AGENT_ASSIGNED':
    case 'TASK_AGENT_ESCALATED': {
      const agentId =
        getEventString(eventData, 'agent_id') ||
        getEventString(eventData, 'new_agent_id') ||
        getEventString(eventData, 'next_agent_id');
      const agentName =
        getEventString(eventData, 'agent_name') ||
        getEventString(eventData, 'new_agent_name') ||
        getEventString(eventData, 'next_agent_name');
      setAssignedAgent(agentId, agentName);
      const source =
        getEventString(eventData, 'source') || getEventString(eventData, 'assignment_source');
      if (source) {
        setTaskMetadata('assignment_source', source);
      }
      break;
    }
    case 'TASK_ATTEMPT_FAILED': {
      const attemptRecord: Record<string, unknown> = {
        timestamp: getEventString(eventData, 'timestamp') || new Date().toISOString(),
      };
      const attempt = getEventNumber(eventData, 'attempt');
      if (attempt !== undefined) attemptRecord.attempt = attempt;
      const maxAttempts = getEventNumber(eventData, 'max_attempts');
      if (maxAttempts !== undefined) attemptRecord.max_attempts = maxAttempts;
      const error = getEventString(eventData, 'error');
      if (error) attemptRecord.error = error;
      const errorType = getEventString(eventData, 'error_type');
      if (errorType) attemptRecord.error_type = errorType;
      const willRetry = getEventBoolean(eventData, 'will_retry');
      if (willRetry !== undefined) attemptRecord.will_retry = willRetry;
      const backoff = getEventNumber(eventData, 'backoff_s');
      if (backoff !== undefined) attemptRecord.backoff_s = backoff;
      const timeout = getEventNumber(eventData, 'timeout_s');
      if (timeout !== undefined) attemptRecord.timeout_s = timeout;
      const traceback = getEventString(eventData, 'traceback');
      if (traceback) attemptRecord.traceback = traceback;

      const existingAttempts = Array.isArray(nextTaskResult.attempts) ? nextTaskResult.attempts : [];
      setTaskResult('attempts', [...existingAttempts, attemptRecord]);
      mergeFailureMessage();
      if (willRetry === false) {
        setStatus('failed');
      } else if (nextTask.status !== 'completed') {
        setStatus('in_progress');
      }
      break;
    }
    default:
      break;
  }

  if (taskMetadataChanged) {
    nextTask = { ...nextTask, task_metadata: nextTaskMetadata };
  }
  if (taskResultChanged) {
    nextTask = { ...nextTask, result: nextTaskResult };
  }
  return nextTask;
};

interface MissionState {
  missions: Mission[];
  selectedMission: Mission | null;
  missionEvents: MissionEvent[];
  missionTasks: MissionTask[];
  missionAgents: MissionAgent[];
  missionAttachments: MissionAttachment[];
  isGlobalMissionWsConnected: boolean;
  isLoading: boolean;
  error: string | null;
  missionSettings: MissionSettings | null;

  // Filters
  statusFilter: MissionStatus | 'all';
  searchQuery: string;

  // Actions
  fetchMissions: (params?: { status?: string; department_id?: string }) => Promise<void>;
  fetchMission: (missionId: string) => Promise<void>;
  createMission: (data: {
    title?: string;
    instructions: string;
    department_id?: string;
    mission_config?: MissionConfig;
  }) => Promise<Mission>;
  startMission: (missionId: string) => Promise<void>;
  retryMission: (missionId: string) => Promise<void>;
  retryFailedMissionParts: (missionId: string) => Promise<void>;
  cancelMission: (missionId: string) => Promise<void>;
  clarify: (missionId: string, message: string) => Promise<void>;
  deleteMission: (missionId: string) => Promise<void>;

  // Selection
  selectMission: (mission: Mission | null) => void;

  // Sub-resource loading
  fetchMissionTasks: (missionId: string) => Promise<void>;
  fetchMissionAgents: (missionId: string) => Promise<void>;
  fetchMissionEvents: (missionId: string) => Promise<void>;
  fetchMissionAttachments: (missionId: string) => Promise<void>;

  // Attachments
  uploadAttachment: (missionId: string, file: File) => Promise<void>;
  removeAttachment: (missionId: string, attachmentId: string) => Promise<void>;

  // Settings
  fetchMissionSettings: () => Promise<void>;
  updateMissionSettings: (data: Partial<MissionSettings>) => Promise<void>;

  // WebSocket handlers
  handleMissionEvent: (event: MissionEvent) => void;
  handleMissionStatusUpdate: (data: { mission_id: string; status: MissionStatus; updates?: Partial<Mission> }) => void;
  handleTaskStatusUpdate: (data: { task_id: string; updates: Partial<MissionTask> }) => void;

  // Filters
  setStatusFilter: (status: MissionStatus | 'all') => void;
  setSearchQuery: (query: string) => void;
  getFilteredMissions: () => Mission[];

  // Common
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setGlobalMissionWsConnected: (connected: boolean) => void;
  reset: () => void;
}

export const useMissionStore = create<MissionState>((set, get) => ({
  missions: [],
  selectedMission: null,
  missionEvents: [],
  missionTasks: [],
  missionAgents: [],
  missionAttachments: [],
  isGlobalMissionWsConnected: false,
  isLoading: false,
  error: null,
  missionSettings: null,
  statusFilter: 'all',
  searchQuery: '',

  fetchMissions: async (params) => {
    set({ isLoading: true, error: null });
    try {
      const response = await missionsApi.getAll(params);
      set({
        missions: response.items.map(normalizeMissionStatus),
        isLoading: false,
      });
    } catch (err: unknown) {
      set({ error: getErrorMessage(err, 'Failed to fetch missions'), isLoading: false });
    }
  },

  fetchMission: async (missionId) => {
    set({ isLoading: true, error: null });
    try {
      const mission = normalizeMissionStatus(await missionsApi.getById(missionId));
      set({ selectedMission: mission, isLoading: false });
    } catch (err: unknown) {
      set({ error: getErrorMessage(err, 'Failed to fetch mission'), isLoading: false });
    }
  },

  createMission: async (data) => {
    set({ isLoading: true, error: null });
    try {
      const mission = normalizeMissionStatus(await missionsApi.create(data));
      set((state) => ({
        missions: [mission, ...state.missions],
        isLoading: false,
      }));
      return mission;
    } catch (err: unknown) {
      set({ error: getErrorMessage(err, 'Failed to create mission'), isLoading: false });
      throw err;
    }
  },

  startMission: async (missionId) => {
    // Optimistic transition prevents long backend startup from looking "stuck in draft".
    set((state) => ({
      missions: state.missions.map((m) =>
        m.mission_id === missionId && m.status === 'draft'
          ? { ...m, status: 'requirements' }
          : m
      ),
      selectedMission:
        state.selectedMission?.mission_id === missionId &&
        state.selectedMission.status === 'draft'
          ? { ...state.selectedMission, status: 'requirements' }
          : state.selectedMission,
    }));

    try {
      const updated = normalizeMissionStatus(await missionsApi.start(missionId));
      if (updated?.mission_id) {
        set((state) => ({
          missions: state.missions.map((m) =>
            m.mission_id === missionId ? updated : m
          ),
          selectedMission:
            state.selectedMission?.mission_id === missionId ? updated : state.selectedMission,
        }));
      } else {
        // Fallback: re-fetch the mission if the response wasn't a full object
        const mission = normalizeMissionStatus(await missionsApi.getById(missionId));
        set((state) => ({
          missions: state.missions.map((m) =>
            m.mission_id === missionId ? mission : m
          ),
          selectedMission:
            state.selectedMission?.mission_id === missionId ? mission : state.selectedMission,
        }));
      }
    } catch (err: unknown) {
      // Rollback optimistic status with authoritative backend state when possible.
      try {
        const mission = normalizeMissionStatus(await missionsApi.getById(missionId));
        set((state) => ({
          missions: state.missions.map((m) =>
            m.mission_id === missionId ? mission : m
          ),
          selectedMission:
            state.selectedMission?.mission_id === missionId ? mission : state.selectedMission,
        }));
      } catch {
        // keep optimistic state if rollback fetch fails; error is surfaced below
      }
      set({ error: getErrorMessage(err, 'Failed to start mission') });
      throw err;
    }
  },

  retryMission: async (missionId) => {
    // Optimistic transition mirrors manual retry action from failed -> requirements.
    set((state) => ({
      missions: state.missions.map((m) =>
        m.mission_id === missionId && (m.status === 'failed' || m.status === 'cancelled')
          ? { ...m, status: 'requirements', error_message: undefined }
          : m
      ),
      selectedMission:
        state.selectedMission?.mission_id === missionId &&
        (state.selectedMission.status === 'failed' ||
          state.selectedMission.status === 'cancelled')
          ? { ...state.selectedMission, status: 'requirements', error_message: undefined }
          : state.selectedMission,
    }));

    try {
      const updated = normalizeMissionStatus(await missionsApi.retry(missionId));
      if (updated?.mission_id) {
        set((state) => ({
          missions: state.missions.map((m) =>
            m.mission_id === missionId ? updated : m
          ),
          selectedMission:
            state.selectedMission?.mission_id === missionId ? updated : state.selectedMission,
        }));
      } else {
        const mission = normalizeMissionStatus(await missionsApi.getById(missionId));
        set((state) => ({
          missions: state.missions.map((m) =>
            m.mission_id === missionId ? mission : m
          ),
          selectedMission:
            state.selectedMission?.mission_id === missionId ? mission : state.selectedMission,
        }));
      }
    } catch (err: unknown) {
      // Roll back to authoritative backend state when retry fails.
      try {
        const mission = normalizeMissionStatus(await missionsApi.getById(missionId));
        set((state) => ({
          missions: state.missions.map((m) =>
            m.mission_id === missionId ? mission : m
          ),
          selectedMission:
            state.selectedMission?.mission_id === missionId ? mission : state.selectedMission,
        }));
      } catch {
        // keep optimistic state if rollback fetch fails; error is surfaced below
      }
      set({ error: getErrorMessage(err, 'Failed to retry mission') });
      throw err;
    }
  },

  retryFailedMissionParts: async (missionId) => {
    set((state) => ({
      missions: state.missions.map((m) =>
        m.mission_id === missionId && (m.status === 'failed' || m.status === 'cancelled')
          ? {
              ...m,
              status: 'executing',
              error_message: undefined,
              failed_tasks: 0,
            }
          : m
      ),
      selectedMission:
        state.selectedMission?.mission_id === missionId &&
        (state.selectedMission.status === 'failed' ||
          state.selectedMission.status === 'cancelled')
          ? {
              ...state.selectedMission,
              status: 'executing',
              error_message: undefined,
              failed_tasks: 0,
            }
          : state.selectedMission,
    }));

    try {
      const updated = normalizeMissionStatus(await missionsApi.retryFailed(missionId));
      if (updated?.mission_id) {
        set((state) => ({
          missions: state.missions.map((m) => (m.mission_id === missionId ? updated : m)),
          selectedMission:
            state.selectedMission?.mission_id === missionId ? updated : state.selectedMission,
        }));
      } else {
        const mission = normalizeMissionStatus(await missionsApi.getById(missionId));
        set((state) => ({
          missions: state.missions.map((m) => (m.mission_id === missionId ? mission : m)),
          selectedMission:
            state.selectedMission?.mission_id === missionId ? mission : state.selectedMission,
        }));
      }
    } catch (err: unknown) {
      try {
        const mission = normalizeMissionStatus(await missionsApi.getById(missionId));
        set((state) => ({
          missions: state.missions.map((m) => (m.mission_id === missionId ? mission : m)),
          selectedMission:
            state.selectedMission?.mission_id === missionId ? mission : state.selectedMission,
        }));
      } catch {
        // keep optimistic state if rollback fetch fails; error is surfaced below
      }
      set({ error: getErrorMessage(err, 'Failed to retry failed mission parts') });
      throw err;
    }
  },

  cancelMission: async (missionId) => {
    try {
      const updated = normalizeMissionStatus(await missionsApi.cancel(missionId));
      if (updated?.mission_id) {
        set((state) => ({
          missions: state.missions.map((m) =>
            m.mission_id === missionId ? updated : m
          ),
          selectedMission:
            state.selectedMission?.mission_id === missionId ? updated : state.selectedMission,
        }));
      } else {
        const mission = normalizeMissionStatus(await missionsApi.getById(missionId));
        set((state) => ({
          missions: state.missions.map((m) =>
            m.mission_id === missionId ? mission : m
          ),
          selectedMission:
            state.selectedMission?.mission_id === missionId ? mission : state.selectedMission,
        }));
      }
    } catch (err: unknown) {
      set({ error: getErrorMessage(err, 'Failed to cancel mission') });
      throw err;
    }
  },

  clarify: async (missionId, message) => {
    try {
      const response = await missionsApi.clarify(missionId, { message });
      // Only push to events if we got a valid event back
      if (response?.event_id) {
        set((state) => ({
          missionEvents: [...state.missionEvents, response],
        }));
      }
    } catch (err: unknown) {
      set({ error: getErrorMessage(err, 'Failed to send clarification') });
      throw err;
    }
  },

  deleteMission: async (missionId) => {
    try {
      await missionsApi.delete(missionId);
      set((state) => ({
        missions: state.missions.filter((m) => m.mission_id !== missionId),
        selectedMission:
          state.selectedMission?.mission_id === missionId ? null : state.selectedMission,
      }));
    } catch (err: unknown) {
      set({ error: getErrorMessage(err, 'Failed to delete mission') });
      throw err;
    }
  },

  selectMission: (mission) => set({ selectedMission: mission }),

  fetchMissionTasks: async (missionId) => {
    try {
      const tasks = await missionsApi.getTasks(missionId);
      set({ missionTasks: tasks });
    } catch (err: unknown) {
      set({ error: getErrorMessage(err, 'Failed to fetch tasks') });
    }
  },

  fetchMissionAgents: async (missionId) => {
    try {
      const agents = await missionsApi.getAgents(missionId);
      set({ missionAgents: agents });
    } catch (err: unknown) {
      set({ error: getErrorMessage(err, 'Failed to fetch agents') });
    }
  },

  fetchMissionEvents: async (missionId) => {
    try {
      const events = await missionsApi.getEvents(missionId, {
        limit: 500,
        latest_run_only: true,
      });
      set({ missionEvents: events });
    } catch (err: unknown) {
      set({ error: getErrorMessage(err, 'Failed to fetch events') });
    }
  },

  fetchMissionAttachments: async (missionId) => {
    try {
      const attachments = await missionsApi.getAttachments(missionId);
      set({ missionAttachments: attachments });
    } catch (err: unknown) {
      set({ error: getErrorMessage(err, 'Failed to fetch attachments') });
    }
  },

  uploadAttachment: async (missionId, file) => {
    try {
      const attachment = await missionsApi.uploadAttachment(missionId, file);
      set((state) => ({
        missionAttachments: [...state.missionAttachments, attachment],
      }));
    } catch (err: unknown) {
      set({ error: getErrorMessage(err, 'Failed to upload attachment') });
      throw err;
    }
  },

  removeAttachment: async (missionId, attachmentId) => {
    try {
      await missionsApi.deleteAttachment(missionId, attachmentId);
      set((state) => ({
        missionAttachments: state.missionAttachments.filter(
          (a) => a.attachment_id !== attachmentId
        ),
      }));
    } catch (err: unknown) {
      set({ error: getErrorMessage(err, 'Failed to delete attachment') });
      throw err;
    }
  },

  fetchMissionSettings: async () => {
    try {
      const settings = await missionsApi.getSettings();
      set({ missionSettings: settings });
    } catch (err: unknown) {
      set({ error: getErrorMessage(err, 'Failed to fetch mission settings') });
    }
  },

  updateMissionSettings: async (data) => {
    try {
      const settings = await missionsApi.updateSettings(data);
      set({ missionSettings: settings });
    } catch (err: unknown) {
      set({ error: getErrorMessage(err, 'Failed to update mission settings') });
      throw err;
    }
  },

  // WebSocket handlers
  handleMissionEvent: (event) => {
    set((state) => {
      if (state.missionEvents.some((existing) => existing.event_id === event.event_id)) {
        return state;
      }
      const nextEvents = [...state.missionEvents, event];
      const eventData =
        event.event_data && typeof event.event_data === 'object'
          ? (event.event_data as Record<string, unknown>)
          : {};
      const normalizedEventType = normalizeEventType(event.event_type);
      const eventTitle =
        typeof eventData.title === 'string' ? eventData.title.trim() : '';
      const shouldUpdateTitle = normalizedEventType === 'MISSION_TITLE_UPDATED' && eventTitle.length > 0;
      const isRunBoundary = RUN_BOUNDARY_EVENT_TYPES.has(event.event_type);
      const isClarificationRequest = CLARIFICATION_REQUEST_EVENT_TYPES.has(event.event_type);
      const isClarificationResponse = CLARIFICATION_RESPONSE_EVENT_TYPES.has(event.event_type);
      const clarificationRequestText =
        typeof eventData.questions === 'string' && eventData.questions.trim().length > 0
          ? eventData.questions.trim()
          : event.message?.trim() || undefined;
      const readCounter = (key: 'total_tasks' | 'completed_tasks' | 'failed_tasks'): number | undefined => {
        const value = eventData[key];
        if (typeof value !== 'number' || !Number.isFinite(value)) {
          return undefined;
        }
        return Math.max(0, Math.floor(value));
      };
      const totalTasksFromEvent = readCounter('total_tasks');
      const completedTasksFromEvent = readCounter('completed_tasks');
      const failedTasksFromEvent = readCounter('failed_tasks');
      const hasCounterSnapshot =
        totalTasksFromEvent !== undefined ||
        completedTasksFromEvent !== undefined ||
        failedTasksFromEvent !== undefined;
      const phaseFromEvent =
        typeof eventData.phase === 'string' ? eventData.phase.trim().toLowerCase() : '';
      const phaseStatusMap: Record<string, MissionStatus> = {
        requirements: 'requirements',
        planning: 'planning',
        executing: 'executing',
        reviewing: 'reviewing',
        qa: 'qa',
      };
      const inferredStatus: MissionStatus | null = (() => {
        if (normalizedEventType === 'MISSION_COMPLETED') return 'completed';
        if (normalizedEventType === 'MISSION_FAILED') return 'failed';
        if (normalizedEventType === 'MISSION_CANCELLED') return 'cancelled';
        if (normalizedEventType === 'MISSION_STARTED') return 'requirements';
        if (normalizedEventType === 'TASK_STARTED') return 'executing';
        if (normalizedEventType === 'PHASE_STARTED') {
          return phaseStatusMap[phaseFromEvent] ?? null;
        }
        return null;
      })();
      const missionFailureMessage =
        normalizedEventType === 'MISSION_FAILED'
          ? (typeof eventData.error === 'string' && eventData.error.trim().length > 0
              ? eventData.error.trim()
              : event.message?.trim() || undefined)
          : undefined;
      const shouldPatchMissionTasks =
        state.selectedMission?.mission_id === event.mission_id &&
        typeof event.task_id === 'string' &&
        event.task_id.length > 0 &&
        TASK_EVENT_TYPES.has(normalizedEventType);
      const nextMissionTasks = shouldPatchMissionTasks
        ? state.missionTasks.map((task) =>
            task.task_id === event.task_id ? applyTaskEventUpdate(task, event) : task
          )
        : state.missionTasks;
      const derivedMissionCounters =
        shouldPatchMissionTasks && nextMissionTasks.length > 0
          ? {
              total_tasks: nextMissionTasks.length,
              completed_tasks: nextMissionTasks.filter((task) => task.status === 'completed').length,
              failed_tasks: nextMissionTasks.filter((task) => task.status === 'failed').length,
            }
          : null;
      const hasDerivedMissionCounters = derivedMissionCounters !== null;

      const patchMission = (mission: Mission): Mission => {
        if (mission.mission_id !== event.mission_id) return mission;

        let patched: Mission = mission;

        if (inferredStatus) {
          patched = { ...patched, status: inferredStatus };
        }
        if (missionFailureMessage) {
          patched = { ...patched, error_message: missionFailureMessage };
        }
        if (shouldUpdateTitle) {
          patched = { ...patched, title: eventTitle };
        }

        if (hasCounterSnapshot || hasDerivedMissionCounters) {
          const nextTotalRaw =
            derivedMissionCounters?.total_tasks ?? totalTasksFromEvent ?? patched.total_tasks;
          const nextCompletedRaw =
            derivedMissionCounters?.completed_tasks ??
            completedTasksFromEvent ??
            patched.completed_tasks;
          const nextFailedRaw =
            derivedMissionCounters?.failed_tasks ?? failedTasksFromEvent ?? patched.failed_tasks;
          const normalizedTotal = Math.max(0, nextTotalRaw, nextCompletedRaw + nextFailedRaw);
          patched = {
            ...patched,
            total_tasks: normalizedTotal,
            completed_tasks: Math.min(nextCompletedRaw, normalizedTotal),
            failed_tasks: Math.min(nextFailedRaw, normalizedTotal),
          };
        }

        if (isRunBoundary) {
          patched = {
            ...patched,
            needs_clarification: false,
            pending_clarification_count: 0,
            latest_clarification_request: undefined,
            latest_clarification_requested_at: undefined,
          };
        }

        if (isClarificationRequest) {
          const currentCount = Math.max(0, patched.pending_clarification_count ?? 0);
          patched = {
            ...patched,
            needs_clarification: true,
            pending_clarification_count: currentCount + 1,
            latest_clarification_request: clarificationRequestText,
            latest_clarification_requested_at: event.created_at,
          };
        } else if (isClarificationResponse) {
          const currentCount = Math.max(0, patched.pending_clarification_count ?? 0);
          const nextCount = Math.max(0, currentCount - 1);
          patched = {
            ...patched,
            needs_clarification: nextCount > 0,
            pending_clarification_count: nextCount,
          };
        }
        return normalizeMissionStatus(patched);
      };

      return {
        missionEvents: nextEvents.slice(-500),
        missions: state.missions.map((mission) => patchMission(mission)),
        selectedMission:
          state.selectedMission?.mission_id === event.mission_id
            ? patchMission(state.selectedMission)
            : state.selectedMission,
        missionTasks: nextMissionTasks,
      };
    });
  },

  handleMissionStatusUpdate: ({ mission_id, status, updates }) => {
    set((state) => ({
      missions: state.missions.map((m) => {
        if (m.mission_id !== mission_id) return m;
        return normalizeMissionStatus({ ...m, status, ...updates });
      }),
      selectedMission:
        state.selectedMission?.mission_id === mission_id
          ? normalizeMissionStatus({ ...state.selectedMission, status, ...updates })
          : state.selectedMission,
    }));
  },

  handleTaskStatusUpdate: ({ task_id, updates }) => {
    set((state) => ({
      missionTasks: state.missionTasks.map((t) =>
        t.task_id === task_id ? { ...t, ...updates } : t
      ),
    }));
  },

  setStatusFilter: (status) => set({ statusFilter: status }),
  setSearchQuery: (query) => set({ searchQuery: query }),

  getFilteredMissions: () => {
    const { missions, statusFilter, searchQuery } = get();
    let filtered = missions || [];

    if (statusFilter !== 'all') {
      filtered = filtered.filter((m) => m.status === statusFilter);
    }

    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (m) =>
          m.title.toLowerCase().includes(q) ||
          m.instructions.toLowerCase().includes(q)
      );
    }

    return filtered;
  },

  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error }),
  setGlobalMissionWsConnected: (connected) => set({ isGlobalMissionWsConnected: connected }),

  reset: () =>
    set({
      missions: [],
      selectedMission: null,
      missionEvents: [],
      missionTasks: [],
      missionAgents: [],
      missionAttachments: [],
      isGlobalMissionWsConnected: false,
      isLoading: false,
      error: null,
      missionSettings: null,
      statusFilter: 'all',
      searchQuery: '',
    }),
}));
