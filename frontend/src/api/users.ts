import apiClient from './client';
import type { UserProfile, ResourceQuota } from '../stores/userStore';

export interface UpdateProfileRequest {
  username?: string;
  email?: string;
  display_name?: string;
  attributes?: Record<string, any>;
}

export interface UserPreferences {
  language: string;
  theme: string;
  sidebar_collapsed: boolean;
  dashboard_layout: string;
  notifications_enabled: boolean;
  sound_enabled: boolean;
  auto_refresh: boolean;
  refresh_interval: number;
}

export interface UserApiKey {
  key_id: string;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at?: string | null;
}

export interface CreateApiKeyResponse {
  key_id: string;
  name: string;
  key: string;
  prefix: string;
  created_at: string;
}

export interface UserSession {
  session_id: string;
  user_agent: string;
  ip_address?: string | null;
  created_at: string;
  last_seen_at: string;
  is_current: boolean;
}

export interface SessionListResponse {
  sessions: UserSession[];
  total: number;
}

export interface TwoFactorStatus {
  enabled: boolean;
  configured_at?: string | null;
  backup_codes_remaining: number;
  setup_pending: boolean;
}

export interface TwoFactorSetupResponse {
  secret: string;
  otpauth_uri: string;
  backup_codes: string[];
}

export interface PrivacySettings {
  profile_visibility: 'private' | 'team' | 'organization';
  searchable_profile: boolean;
  allow_telemetry: boolean;
  allow_training: boolean;
  data_retention_days: number;
}

export interface UserDataExportResponse {
  filename: string;
  data: Record<string, unknown>;
}

export interface BindingCodeResponse {
  code: string;
  maskedCode: string;
  status: string;
  rotatedAt?: string | null;
  lastUsedAt?: string | null;
  createdAt: string;
  updatedAt: string;
}

/**
 * Users API
 */
export const usersApi = {
  /**
   * Get current user profile
   */
  getProfile: async (): Promise<UserProfile> => {
    const response = await apiClient.get<any>('/users/me');
    const data = response.data;
    
    // Map user_id to id for frontend compatibility
    return {
      id: data.user_id,
      username: data.username,
      email: data.email,
      role: data.role,
      displayName: data.display_name,
      attributes: data.attributes,
      createdAt: data.created_at,
      updatedAt: data.updated_at,
    };
  },

  /**
   * Update current user profile
   */
  updateProfile: async (data: UpdateProfileRequest): Promise<UserProfile> => {
    const response = await apiClient.put<any>('/users/me', data);
    const resData = response.data;
    
    // Map user_id to id for frontend compatibility
    return {
      id: resData.user_id,
      username: resData.username,
      email: resData.email,
      role: resData.role,
      displayName: resData.display_name,
      attributes: resData.attributes,
      createdAt: resData.created_at,
      updatedAt: resData.updated_at,
    };
  },

  /**
   * Get user resource quotas
   */
  getQuotas: async (): Promise<ResourceQuota> => {
    const response = await apiClient.get<any>('/users/me/quotas');
    const data = response.data;
    
    // Map snake_case to camelCase for frontend compatibility
    return {
      maxAgents: data.max_agents,
      maxStorageGb: data.max_storage_gb,
      maxCpuCores: data.max_cpu_cores || 0,
      maxMemoryGb: data.max_memory_gb || 0,
      currentAgents: data.current_agents,
      currentStorageGb: data.current_storage_gb,
    };
  },

  /**
   * Get current user preferences
   */
  getPreferences: async (): Promise<UserPreferences> => {
    const response = await apiClient.get<UserPreferences>('/users/me/preferences');
    return response.data;
  },

  /**
   * Update current user preferences
   */
  updatePreferences: async (preferences: Partial<UserPreferences>): Promise<UserPreferences> => {
    const currentPreferences = await usersApi.getPreferences();
    const payload: UserPreferences = {
      ...currentPreferences,
      ...preferences,
    };
    const response = await apiClient.put<UserPreferences>('/users/me/preferences', payload);
    return response.data;
  },

  /**
   * Get user by ID (admin only)
   */
  getUserById: async (userId: string): Promise<UserProfile> => {
    const response = await apiClient.get<any>(`/users/${userId}`);
    const data = response.data;
    
    return {
      id: data.user_id,
      username: data.username,
      email: data.email,
      role: data.role,
      attributes: data.attributes,
      createdAt: data.created_at,
      updatedAt: data.updated_at,
    };
  },

  /**
   * Get user quotas by ID (admin only)
   */
  getUserQuotas: async (userId: string): Promise<ResourceQuota> => {
    const response = await apiClient.get<ResourceQuota>(`/users/${userId}/quotas`);
    return response.data;
  },

  /**
   * Change current user password
   */
  changePassword: async (currentPassword: string, newPassword: string): Promise<void> => {
    await apiClient.put('/users/me/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
  },

  /**
   * Upload user avatar
   * Converts image to WebP format for optimization
   */
  uploadAvatar: async (file: File): Promise<{ avatar_url: string }> => {
    // Convert image to WebP
    const webpBlob = await convertImageToWebP(file);
    
    // Create form data
    const formData = new FormData();
    formData.append('file', webpBlob, 'avatar.webp');
    
    const response = await apiClient.post<{ avatar_url: string }>(
      '/users/me/avatar',
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    );
    
    return response.data;
  },

  getBindingCode: async (): Promise<BindingCodeResponse> => {
    const response = await apiClient.get<any>('/users/me/binding-code');
    return {
      code: response.data.code,
      maskedCode: response.data.masked_code,
      status: response.data.status,
      rotatedAt: response.data.rotated_at,
      lastUsedAt: response.data.last_used_at,
      createdAt: response.data.created_at,
      updatedAt: response.data.updated_at,
    };
  },

  refreshBindingCode: async (): Promise<BindingCodeResponse> => {
    const response = await apiClient.post<any>('/users/me/binding-code/refresh');
    return {
      code: response.data.code,
      maskedCode: response.data.masked_code,
      status: response.data.status,
      rotatedAt: response.data.rotated_at,
      lastUsedAt: response.data.last_used_at,
      createdAt: response.data.created_at,
      updatedAt: response.data.updated_at,
    };
  },

  /**
   * List user API keys
   */
  getApiKeys: async (): Promise<UserApiKey[]> => {
    const response = await apiClient.get<UserApiKey[]>('/users/me/api-keys');
    return response.data;
  },

  /**
   * Create user API key
   */
  createApiKey: async (name: string): Promise<CreateApiKeyResponse> => {
    const response = await apiClient.post<CreateApiKeyResponse>('/users/me/api-keys', { name });
    return response.data;
  },

  /**
   * Delete user API key
   */
  deleteApiKey: async (keyId: string): Promise<void> => {
    await apiClient.delete(`/users/me/api-keys/${keyId}`);
  },

  /**
   * List active sessions
   */
  getSessions: async (): Promise<SessionListResponse> => {
    const response = await apiClient.get<SessionListResponse>('/users/me/sessions');
    return response.data;
  },

  /**
   * Revoke one session
   */
  revokeSession: async (sessionId: string): Promise<void> => {
    await apiClient.delete(`/users/me/sessions/${sessionId}`);
  },

  /**
   * Revoke all sessions except current
   */
  revokeOtherSessions: async (): Promise<{ message: string; revoked_count: number }> => {
    const response = await apiClient.post<{ message: string; revoked_count: number }>(
      '/users/me/sessions/revoke-others'
    );
    return response.data;
  },

  /**
   * Two-factor authentication status
   */
  getTwoFactorStatus: async (): Promise<TwoFactorStatus> => {
    const response = await apiClient.get<TwoFactorStatus>('/users/me/two-factor');
    return response.data;
  },

  /**
   * Setup two-factor authentication
   */
  setupTwoFactor: async (): Promise<TwoFactorSetupResponse> => {
    const response = await apiClient.post<TwoFactorSetupResponse>('/users/me/two-factor/setup');
    return response.data;
  },

  /**
   * Enable two-factor authentication
   */
  enableTwoFactor: async (verificationCode: string): Promise<TwoFactorStatus> => {
    const response = await apiClient.post<TwoFactorStatus>('/users/me/two-factor/enable', {
      verification_code: verificationCode,
    });
    return response.data;
  },

  /**
   * Disable two-factor authentication
   */
  disableTwoFactor: async (currentPassword: string): Promise<TwoFactorStatus> => {
    const response = await apiClient.post<TwoFactorStatus>('/users/me/two-factor/disable', {
      current_password: currentPassword,
    });
    return response.data;
  },

  /**
   * Privacy settings
   */
  getPrivacySettings: async (): Promise<PrivacySettings> => {
    const response = await apiClient.get<PrivacySettings>('/users/me/privacy');
    return response.data;
  },

  /**
   * Update privacy settings
   */
  updatePrivacySettings: async (settings: PrivacySettings): Promise<PrivacySettings> => {
    const response = await apiClient.put<PrivacySettings>('/users/me/privacy', settings);
    return response.data;
  },

  /**
   * Export current user data
   */
  exportUserData: async (): Promise<UserDataExportResponse> => {
    const response = await apiClient.post<UserDataExportResponse>('/users/me/privacy/export');
    return response.data;
  },

  /**
   * Delete account
   */
  deleteAccount: async (currentPassword: string, confirmation: string = 'DELETE'): Promise<void> => {
    await apiClient.delete('/users/me', {
      data: {
        current_password: currentPassword,
        confirmation,
      },
    });
  },
};

/**
 * Convert image file to WebP format
 */
async function convertImageToWebP(file: File): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    
    reader.onload = (e) => {
      const img = new Image();
      
      img.onload = () => {
        // Create canvas
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        
        if (!ctx) {
          reject(new Error('Failed to get canvas context'));
          return;
        }
        
        // Calculate dimensions (max 512x512, maintain aspect ratio)
        const maxSize = 512;
        let width = img.width;
        let height = img.height;
        
        if (width > height) {
          if (width > maxSize) {
            height = (height * maxSize) / width;
            width = maxSize;
          }
        } else {
          if (height > maxSize) {
            width = (width * maxSize) / height;
            height = maxSize;
          }
        }
        
        canvas.width = width;
        canvas.height = height;
        
        // Draw image
        ctx.drawImage(img, 0, 0, width, height);
        
        // Convert to WebP
        canvas.toBlob(
          (blob) => {
            if (blob) {
              resolve(blob);
            } else {
              reject(new Error('Failed to convert image to WebP'));
            }
          },
          'image/webp',
          0.9 // Quality
        );
      };
      
      img.onerror = () => {
        reject(new Error('Failed to load image'));
      };
      
      img.src = e.target?.result as string;
    };
    
    reader.onerror = () => {
      reject(new Error('Failed to read file'));
    };
    
    reader.readAsDataURL(file);
  });
}
