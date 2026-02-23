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
      const eventTitle =
        typeof event.event_data?.title === 'string' ? event.event_data.title.trim() : '';
      const shouldUpdateTitle = event.event_type === 'MISSION_TITLE_UPDATED' && eventTitle.length > 0;
      const isRunBoundary = RUN_BOUNDARY_EVENT_TYPES.has(event.event_type);
      const isClarificationRequest = CLARIFICATION_REQUEST_EVENT_TYPES.has(event.event_type);
      const isClarificationResponse = CLARIFICATION_RESPONSE_EVENT_TYPES.has(event.event_type);
      const clarificationRequestText =
        typeof event.event_data?.questions === 'string' && event.event_data.questions.trim().length > 0
          ? event.event_data.questions.trim()
          : event.message?.trim() || undefined;

      const patchMission = (mission: Mission): Mission => {
        if (mission.mission_id !== event.mission_id) return mission;

        let patched: Mission = mission;
        if (shouldUpdateTitle) {
          patched = { ...patched, title: eventTitle };
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
        return patched;
      };

      return {
        missionEvents: nextEvents.slice(-500),
        missions: state.missions.map((mission) => patchMission(mission)),
        selectedMission:
          state.selectedMission?.mission_id === event.mission_id
            ? patchMission(state.selectedMission)
            : state.selectedMission,
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
