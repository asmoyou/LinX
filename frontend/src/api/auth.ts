import apiClient from './client';
import type { User } from '../stores/authStore';

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  user: User;
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
  role?: string;
}

export interface RefreshTokenRequest {
  refresh_token: string;
}

export interface RefreshTokenResponse {
  token: string;
  refresh_token: string;
}

/**
 * Authentication API
 */
export const authApi = {
  /**
   * Login user
   */
  login: async (credentials: LoginRequest): Promise<LoginResponse> => {
    const response = await apiClient.post<LoginResponse>('/auth/login', credentials);
    
    // Map user_id to id for frontend compatibility
    const data = response.data;
    if (data.user && 'user_id' in data.user) {
      data.user = {
        ...data.user,
        id: (data.user as any).user_id,
      };
    }
    
    return data;
  },

  /**
   * Register new user
   */
  register: async (data: RegisterRequest): Promise<LoginResponse> => {
    const response = await apiClient.post<any>('/auth/register', data);
    
    // Map registration response to login response format
    const regData = response.data;
    return {
      user: {
        id: regData.user_id,
        username: regData.username,
        email: regData.email,
        role: regData.role,
        attributes: regData.attributes,
      },
      access_token: '', // Registration doesn't return tokens, need to login
      refresh_token: '',
      token_type: 'bearer',
      expires_in: 0,
    };
  },

  /**
   * Logout user
   */
  logout: async (): Promise<void> => {
    await apiClient.post('/auth/logout');
  },

  /**
   * Refresh access token
   */
  refreshToken: async (refreshToken: string): Promise<RefreshTokenResponse> => {
    const response = await apiClient.post<RefreshTokenResponse>('/auth/refresh', {
      refresh_token: refreshToken,
    });
    return response.data;
  },

  /**
   * Verify token validity
   */
  verifyToken: async (): Promise<{ valid: boolean }> => {
    const response = await apiClient.get<{ valid: boolean }>('/auth/verify');
    return response.data;
  },
};
