import apiClient from './client';
import type { NotificationListResponse, ServerNotification } from '@/types/notification';

export const notificationsApi = {
  getAll: async (params?: {
    status?: 'all' | 'unread';
    limit?: number;
    offset?: number;
  }): Promise<NotificationListResponse> => {
    const response = await apiClient.get<NotificationListResponse>('/notifications', {
      params,
    });
    return response.data;
  },

  markAsRead: async (notificationId: string): Promise<ServerNotification> => {
    const response = await apiClient.patch<ServerNotification>(
      `/notifications/${notificationId}/read`
    );
    return response.data;
  },

  markAllAsRead: async (): Promise<{ updated: number }> => {
    const response = await apiClient.post<{ updated: number }>('/notifications/read-all');
    return response.data;
  },

  deleteOne: async (notificationId: string): Promise<void> => {
    await apiClient.delete(`/notifications/${notificationId}`);
  },

  clear: async (scope: 'read' | 'all' = 'read'): Promise<{ deleted: number }> => {
    const response = await apiClient.delete<{ deleted: number }>('/notifications', {
      params: { scope },
    });
    return response.data;
  },
};
