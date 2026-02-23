import apiClient from './client';
import type { RequestConfigWithMeta } from './client';
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
  title?: string;
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
    const queryParams = params
      ? (() => {
          const { status, ...rest } = params;
          return {
            ...rest,
            ...(status ? { status_filter: status } : {}),
          };
        })()
      : undefined;
    const response = await apiClient.get<MissionListResponse>('/missions', {
      params: queryParams,
    });
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

  retry: async (missionId: string): Promise<Mission> => {
    const response = await apiClient.post<Mission>(`/missions/${missionId}/retry`);
    return response.data;
  },

  retryFailed: async (missionId: string): Promise<Mission> => {
    const response = await apiClient.post<Mission>(`/missions/${missionId}/retry-failed`);
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
    latest_run_only?: boolean;
  }): Promise<MissionEvent[]> => {
    const response = await apiClient.get<MissionEvent[]>(
      `/missions/${missionId}/events`,
      { params }
    );
    return response.data;
  },

  getDeliverables: async (
    missionId: string,
    params?: { scope?: 'all' | 'final' | 'intermediate' }
  ): Promise<MissionDeliverable[]> => {
    const response = await apiClient.get<MissionDeliverable[]>(
      `/missions/${missionId}/deliverables`,
      { params }
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

  downloadDeliverablesArchive: async (
    missionId: string,
    options?: { targetOnly?: boolean }
  ): Promise<{ blob: Blob; filename?: string }> => {
    const response = await apiClient.get(
      `/missions/${missionId}/deliverables/archive`,
      {
        params: { target_only: options?.targetOnly ?? false },
        responseType: 'blob',
      }
    );

    const disposition = response.headers['content-disposition'] as string | undefined;
    let filename: string | undefined;
    if (disposition) {
      const utf8Match = disposition.match(/filename\*=UTF-8''(.+)/i);
      if (utf8Match) {
        filename = decodeURIComponent(utf8Match[1]);
      } else {
        const basicMatch = disposition.match(/filename="?([^";\n]+)"?/i);
        if (basicMatch) {
          filename = basicMatch[1].trim();
        }
      }
    }

    return {
      blob: response.data,
      filename,
    };
  },

  getWorkspaceFiles: async (
    missionId: string,
    path?: string,
    recursive = false
  ): Promise<WorkspaceFile[]> => {
    const requestConfig: RequestConfigWithMeta = {
      params: {
        ...(path ? { path } : {}),
        ...(recursive ? { recursive: true } : {}),
      },
      suppressErrorToast: true,
    };
    const response = await apiClient.get<Array<{
      name: string;
      path: string;
      size: number;
      is_directory?: boolean;
      is_dir?: boolean;
      modified_at?: string;
    }>>(
      `/missions/${missionId}/workspace/files`,
      requestConfig
    );
    return response.data.map((item) => ({
      name: item.name,
      path: item.path,
      size: item.size,
      is_dir: item.is_dir ?? Boolean(item.is_directory),
      modified_at: item.modified_at,
    }));
  },

  downloadWorkspaceFile: async (missionId: string, path: string): Promise<Blob> => {
    const response = await apiClient.get(
      `/missions/${missionId}/workspace/download`,
      { params: { path }, responseType: 'blob' }
    );
    return response.data;
  },

  getSettings: async (): Promise<MissionSettings> => {
    const response = await apiClient.get<MissionSettings>('/missions/settings');
    return response.data;
  },

  updateSettings: async (data: Partial<MissionSettings>): Promise<MissionSettings> => {
    const requestConfig: RequestConfigWithMeta = { suppressErrorToast: true };
    const response = await apiClient.put<MissionSettings>(
      '/missions/settings',
      data,
      requestConfig
    );
    return response.data;
  },
};
