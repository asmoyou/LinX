import apiClient from './client';
import type {
  AgentSchedule,
  CreateScheduleRequest,
  ScheduleCreateResponse,
  ScheduleListFilters,
  ScheduleListResponse,
  SchedulePreviewRequest,
  SchedulePreviewResponse,
  ScheduleRun,
  ScheduleRunListResponse,
  UpdateScheduleRequest,
} from '@/types/schedule';

export const schedulesApi = {
  list: async (filters: ScheduleListFilters = {}): Promise<ScheduleListResponse> => {
    const response = await apiClient.get<ScheduleListResponse>('/schedules', {
      params: {
        scope: filters.scope ?? 'mine',
        ...(filters.status && filters.status !== 'all' ? { status: filters.status } : {}),
        ...(filters.type && filters.type !== 'all' ? { type: filters.type } : {}),
        ...(filters.createdVia && filters.createdVia !== 'all'
          ? { createdVia: filters.createdVia }
          : {}),
        ...(filters.agentId ? { agentId: filters.agentId } : {}),
        ...(filters.query ? { query: filters.query } : {}),
        ...(typeof filters.limit === 'number' ? { limit: filters.limit } : {}),
        ...(typeof filters.offset === 'number' ? { offset: filters.offset } : {}),
      },
    });
    return response.data;
  },

  getById: async (scheduleId: string): Promise<AgentSchedule> => {
    const response = await apiClient.get<AgentSchedule>(`/schedules/${scheduleId}`);
    return response.data;
  },

  create: async (payload: CreateScheduleRequest): Promise<ScheduleCreateResponse> => {
    const response = await apiClient.post<ScheduleCreateResponse>('/schedules', payload);
    return response.data;
  },

  update: async (scheduleId: string, payload: UpdateScheduleRequest): Promise<AgentSchedule> => {
    const response = await apiClient.patch<AgentSchedule>(`/schedules/${scheduleId}`, payload);
    return response.data;
  },

  remove: async (scheduleId: string): Promise<void> => {
    await apiClient.delete(`/schedules/${scheduleId}`);
  },

  pause: async (scheduleId: string): Promise<AgentSchedule> => {
    const response = await apiClient.post<AgentSchedule>(`/schedules/${scheduleId}/pause`);
    return response.data;
  },

  resume: async (scheduleId: string): Promise<AgentSchedule> => {
    const response = await apiClient.post<AgentSchedule>(`/schedules/${scheduleId}/resume`);
    return response.data;
  },

  runNow: async (scheduleId: string): Promise<ScheduleRun> => {
    const response = await apiClient.post<ScheduleRun>(`/schedules/${scheduleId}/run-now`);
    return response.data;
  },

  listRuns: async (
    scheduleId: string,
    options: { limit?: number; offset?: number } = {}
  ): Promise<ScheduleRunListResponse> => {
    const response = await apiClient.get<ScheduleRunListResponse>(`/schedules/${scheduleId}/runs`, {
      params: {
        ...(typeof options.limit === 'number' ? { limit: options.limit } : {}),
        ...(typeof options.offset === 'number' ? { offset: options.offset } : {}),
      },
    });
    return response.data;
  },

  preview: async (payload: SchedulePreviewRequest): Promise<SchedulePreviewResponse> => {
    const response = await apiClient.post<SchedulePreviewResponse>('/schedules/preview', payload);
    return response.data;
  },
};
