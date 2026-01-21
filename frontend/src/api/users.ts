import apiClient from './client';
import type { UserProfile, ResourceQuota } from '../stores/userStore';

export interface UpdateProfileRequest {
  username?: string;
  email?: string;
  attributes?: Record<string, any>;
}

/**
 * Users API
 */
export const usersApi = {
  /**
   * Get current user profile
   */
  getProfile: async (): Promise<UserProfile> => {
    const response = await apiClient.get<UserProfile>('/users/me');
    return response.data;
  },

  /**
   * Update current user profile
   */
  updateProfile: async (data: UpdateProfileRequest): Promise<UserProfile> => {
    const response = await apiClient.put<UserProfile>('/users/me', data);
    return response.data;
  },

  /**
   * Get user resource quotas
   */
  getQuotas: async (): Promise<ResourceQuota> => {
    const response = await apiClient.get<ResourceQuota>('/users/me/quotas');
    return response.data;
  },

  /**
   * Get user by ID (admin only)
   */
  getUserById: async (userId: string): Promise<UserProfile> => {
    const response = await apiClient.get<UserProfile>(`/users/${userId}`);
    return response.data;
  },

  /**
   * Get user quotas by ID (admin only)
   */
  getUserQuotas: async (userId: string): Promise<ResourceQuota> => {
    const response = await apiClient.get<ResourceQuota>(`/users/${userId}/quotas`);
    return response.data;
  },
};
