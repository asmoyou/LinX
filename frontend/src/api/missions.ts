import apiClient from './client';
import type {
  Mission,
  MissionAgent,
  MissionAttachment,
  MissionEvent,
  MissionDeliverable,
  MissionTask,
  MissionConfig,
  MissionSettings,
} from '../types/mission';

export interface MissionListResponse {
  items: Mission[];
  total: number;
}

export interface CreateMissionRequest {
  title: string;
  instructions: string;
  department_id?: string;
  mission_config?: MissionConfig;
}

export interface UpdateMissionRequest {
  title?: string;
  instructions?: string;
  mission_config?: MissionConfig;
}

export interface ClarifyRequest {
  message: string;
}

export interface WorkspaceFile {
  name: string;
  path: string;
  size: number;
  is_dir: boolean;
  modified_at?: string;
}

export const missionsApi = {
  getAll: async (params?: {
    status?: string;
    department_id?: string;
    page?: number;
    page_size?: number;
  }): Promise<MissionListResponse> => {
    const response = await apiClient.get<MissionListResponse>('/missions', { params });
    return response.data;
  },

  getById: async (missionId: string): Promise<Mission> => {
    const response = await apiClient.get<Mission>(`/missions/${missionId}`);
    return response.data;
  },

  create: async (data: CreateMissionRequest): Promise<Mission> => {
    const response = await apiClient.post<Mission>('/missions', data);
    return response.data;
  },

  update: async (missionId: string, data: UpdateMissionRequest): Promise<Mission> => {
    const response = await apiClient.put<Mission>(`/missions/${missionId}`, data);
    return response.data;
  },

  delete: async (missionId: string): Promise<void> => {
    await apiClient.delete(`/missions/${missionId}`);
  },

  start: async (missionId: string): Promise<Mission> => {
    const response = await apiClient.post<Mission>(`/missions/${missionId}/start`);
    return response.data;
  },

  cancel: async (missionId: string): Promise<Mission> => {
    const response = await apiClient.post<Mission>(`/missions/${missionId}/cancel`);
    return response.data;
  },

  clarify: async (missionId: string, data: ClarifyRequest): Promise<MissionEvent> => {
    const response = await apiClient.post<MissionEvent>(
      `/missions/${missionId}/clarify`,
      data
    );
    return response.data;
  },

  uploadAttachment: async (missionId: string, file: File): Promise<MissionAttachment> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await apiClient.post<MissionAttachment>(
      `/missions/${missionId}/attachments`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    );
    return response.data;
  },

  getAttachments: async (missionId: string): Promise<MissionAttachment[]> => {
    const response = await apiClient.get<MissionAttachment[]>(
      `/missions/${missionId}/attachments`
    );
    return response.data;
  },

  deleteAttachment: async (missionId: string, attachmentId: string): Promise<void> => {
    await apiClient.delete(`/missions/${missionId}/attachments/${attachmentId}`);
  },

  getAgents: async (missionId: string): Promise<MissionAgent[]> => {
    const response = await apiClient.get<MissionAgent[]>(`/missions/${missionId}/agents`);
    return response.data;
  },

  getTasks: async (missionId: string): Promise<MissionTask[]> => {
    const response = await apiClient.get<MissionTask[]>(`/missions/${missionId}/tasks`);
    return response.data;
  },

  getEvents: async (missionId: string, params?: {
    limit?: number;
    offset?: number;
  }): Promise<MissionEvent[]> => {
    const response = await apiClient.get<MissionEvent[]>(
      `/missions/${missionId}/events`,
      { params }
    );
    return response.data;
  },

  getDeliverables: async (missionId: string): Promise<MissionDeliverable[]> => {
    const response = await apiClient.get<MissionDeliverable[]>(
      `/missions/${missionId}/deliverables`
    );
    return response.data;
  },

  downloadDeliverable: async (missionId: string, path: string): Promise<Blob> => {
    const response = await apiClient.get(
      `/missions/${missionId}/deliverables/download`,
      { params: { path }, responseType: 'blob' }
    );
    return response.data;
  },

  getWorkspaceFiles: async (missionId: string, path?: string): Promise<WorkspaceFile[]> => {
    const response = await apiClient.get<WorkspaceFile[]>(
      `/missions/${missionId}/workspace`,
      { params: { path } }
    );
    return response.data;
  },

  getSettings: async (): Promise<MissionSettings> => {
    const response = await apiClient.get<MissionSettings>('/missions/settings');
    return response.data;
  },

  updateSettings: async (data: Partial<MissionSettings>): Promise<MissionSettings> => {
    const response = await apiClient.put<MissionSettings>('/missions/settings', data);
    return response.data;
  },
};
