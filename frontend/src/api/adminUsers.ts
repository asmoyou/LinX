import apiClient from './client';

export interface AdminUser {
  id: string;
  username: string;
  email: string;
  role: string;
  departmentId?: string;
  departmentName?: string;
  isDisabled: boolean;
  displayName?: string;
  createdAt: string;
  updatedAt: string;
}

export interface AdminUserListResponse {
  users: AdminUser[];
  total: number;
  page: number;
  pageSize: number;
}

export interface CreateUserRequest {
  username: string;
  email: string;
  password: string;
  role: string;
  department_id?: string;
}

export interface UpdateUserRequest {
  email?: string;
  role?: string;
  department_id?: string;
  is_disabled?: boolean;
  display_name?: string;
}

function mapAdminUser(data: any): AdminUser {
  return {
    id: data.user_id || data.id,
    username: data.username,
    email: data.email,
    role: data.role,
    departmentId: data.department_id,
    departmentName: data.department_name,
    isDisabled: data.is_disabled || false,
    displayName: data.display_name,
    createdAt: data.created_at,
    updatedAt: data.updated_at,
  };
}

export const adminUsersApi = {
  list: async (params?: {
    page?: number;
    page_size?: number;
    search?: string;
    role?: string;
    department_id?: string;
    status?: string;
  }): Promise<AdminUserListResponse> => {
    const response = await apiClient.get<any>('/admin/users', { params });
    return {
      users: (response.data.users || []).map(mapAdminUser),
      total: response.data.total || 0,
      page: response.data.page || 1,
      pageSize: response.data.page_size || 20,
    };
  },

  getById: async (userId: string): Promise<AdminUser> => {
    const response = await apiClient.get<any>(`/admin/users/${userId}`);
    return mapAdminUser(response.data);
  },

  create: async (data: CreateUserRequest): Promise<AdminUser> => {
    const response = await apiClient.post<any>('/admin/users', data);
    return mapAdminUser(response.data);
  },

  update: async (userId: string, data: UpdateUserRequest): Promise<AdminUser> => {
    const response = await apiClient.put<any>(`/admin/users/${userId}`, data);
    return mapAdminUser(response.data);
  },

  resetPassword: async (userId: string, newPassword: string): Promise<void> => {
    await apiClient.put(`/admin/users/${userId}/reset-password`, {
      new_password: newPassword,
    });
  },

  delete: async (userId: string): Promise<void> => {
    await apiClient.delete(`/admin/users/${userId}`);
  },

  batchAction: async (action: string, userIds: string[]): Promise<void> => {
    await apiClient.post('/admin/users/batch', { action, user_ids: userIds });
  },
};
