import { create } from 'zustand';
import { schedulesApi } from '@/api/schedules';
import type {
  AgentSchedule,
  CreateScheduleRequest,
  ScheduleListFilters,
  SchedulePreviewRequest,
  SchedulePreviewResponse,
  ScheduleRun,
  UpdateScheduleRequest,
} from '@/types/schedule';

interface ScheduleState {
  schedules: AgentSchedule[];
  total: number;
  isLoading: boolean;
  previewLoading: boolean;
  error: string | null;
  filters: Required<Pick<ScheduleListFilters, 'scope' | 'status' | 'type' | 'createdVia'>> &
    Pick<ScheduleListFilters, 'agentId' | 'query' | 'limit' | 'offset'>;
  runsByScheduleId: Record<string, ScheduleRun[]>;
  preview: SchedulePreviewResponse | null;
  previewError: string | null;
  setFilters: (filters: Partial<ScheduleState['filters']>) => void;
  clearPreview: () => void;
  loadSchedules: () => Promise<void>;
  createSchedule: (payload: CreateScheduleRequest) => Promise<AgentSchedule>;
  updateSchedule: (scheduleId: string, payload: UpdateScheduleRequest) => Promise<AgentSchedule>;
  deleteSchedule: (scheduleId: string) => Promise<void>;
  pauseSchedule: (scheduleId: string) => Promise<AgentSchedule>;
  resumeSchedule: (scheduleId: string) => Promise<AgentSchedule>;
  runScheduleNow: (scheduleId: string) => Promise<ScheduleRun>;
  loadRuns: (scheduleId: string, limit?: number) => Promise<ScheduleRun[]>;
  previewSchedule: (payload: SchedulePreviewRequest) => Promise<SchedulePreviewResponse>;
  reset: () => void;
}

const defaultFilters: ScheduleState['filters'] = {
  scope: 'mine',
  status: 'all',
  type: 'all',
  createdVia: 'all',
  agentId: '',
  query: '',
  limit: 50,
  offset: 0,
};

function upsertScheduleItem(items: AgentSchedule[], nextItem: AgentSchedule): AgentSchedule[] {
  const deduped = items.filter((item) => item.id !== nextItem.id);
  return [nextItem, ...deduped];
}

export const useScheduleStore = create<ScheduleState>((set, get) => ({
  schedules: [],
  total: 0,
  isLoading: false,
  previewLoading: false,
  error: null,
  filters: defaultFilters,
  runsByScheduleId: {},
  preview: null,
  previewError: null,

  setFilters: (filters) =>
    set((state) => ({
      filters: {
        ...state.filters,
        ...filters,
      },
    })),

  clearPreview: () =>
    set({
      preview: null,
      previewError: null,
      previewLoading: false,
    }),

  loadSchedules: async () => {
    set({ isLoading: true, error: null });
    try {
      const { filters } = get();
      const response = await schedulesApi.list(filters);
      set({
        schedules: response.items,
        total: response.total,
        isLoading: false,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to load schedules';
      set({ error: message, isLoading: false });
      throw error;
    }
  },

  createSchedule: async (payload) => {
    const response = await schedulesApi.create(payload);
    set((state) => ({
      schedules: upsertScheduleItem(state.schedules, response.schedule),
      total: state.total + 1,
    }));
    return response.schedule;
  },

  updateSchedule: async (scheduleId, payload) => {
    const response = await schedulesApi.update(scheduleId, payload);
    set((state) => ({
      schedules: state.schedules.map((item) => (item.id === scheduleId ? response : item)),
      runsByScheduleId: {
        ...state.runsByScheduleId,
        [scheduleId]: state.runsByScheduleId[scheduleId] || [],
      },
    }));
    return response;
  },

  deleteSchedule: async (scheduleId) => {
    await schedulesApi.remove(scheduleId);
    set((state) => {
      const nextRuns = { ...state.runsByScheduleId };
      delete nextRuns[scheduleId];
      return {
        schedules: state.schedules.filter((item) => item.id !== scheduleId),
        total: Math.max(state.total - 1, 0),
        runsByScheduleId: nextRuns,
      };
    });
  },

  pauseSchedule: async (scheduleId) => {
    const response = await schedulesApi.pause(scheduleId);
    set((state) => ({
      schedules: state.schedules.map((item) => (item.id === scheduleId ? response : item)),
    }));
    return response;
  },

  resumeSchedule: async (scheduleId) => {
    const response = await schedulesApi.resume(scheduleId);
    set((state) => ({
      schedules: state.schedules.map((item) => (item.id === scheduleId ? response : item)),
    }));
    return response;
  },

  runScheduleNow: async (scheduleId) => {
    const run = await schedulesApi.runNow(scheduleId);
    set((state) => ({
      runsByScheduleId: {
        ...state.runsByScheduleId,
        [scheduleId]: [run, ...(state.runsByScheduleId[scheduleId] || [])],
      },
    }));
    return run;
  },

  loadRuns: async (scheduleId, limit = 10) => {
    const response = await schedulesApi.listRuns(scheduleId, { limit });
    set((state) => ({
      runsByScheduleId: {
        ...state.runsByScheduleId,
        [scheduleId]: response.items,
      },
    }));
    return response.items;
  },

  previewSchedule: async (payload) => {
    set({ previewLoading: true, previewError: null });
    try {
      const response = await schedulesApi.preview(payload);
      set({
        preview: response,
        previewLoading: false,
      });
      return response;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to preview schedule';
      set({
        preview: null,
        previewError: message,
        previewLoading: false,
      });
      throw error;
    }
  },

  reset: () =>
    set({
      schedules: [],
      total: 0,
      isLoading: false,
      previewLoading: false,
      error: null,
      filters: defaultFilters,
      runsByScheduleId: {},
      preview: null,
      previewError: null,
    }),
}));
