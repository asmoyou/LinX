import apiClient from './client';
import type {
  Department,
  DepartmentStats,
  DepartmentMember,
  DepartmentAgent,
  CreateDepartmentRequest,
  UpdateDepartmentRequest,
} from '../types/department';

/**
 * Map API response (snake_case) to frontend Department (camelCase)
 */
function mapDepartment(data: any): Department {
  return {
    id: data.department_id,
    name: data.name,
    code: data.code,
    description: data.description,
    parentId: data.parent_id,
    managerId: data.manager_id,
    managerName: data.manager_name,
    status: data.status,
    sortOrder: data.sort_order,
    memberCount: data.member_count || 0,
    agentCount: data.agent_count || 0,
    knowledgeCount: data.knowledge_count || 0,
    children: (data.children || []).map(mapDepartment),
    createdAt: data.created_at,
    updatedAt: data.updated_at,
  };
}

/**
 * Departments API
 */
export const departmentsApi = {
  /**
   * List all departments
   */
  list: async (params?: {
    view?: 'flat' | 'tree';
    status?: 'active' | 'archived';
    search?: string;
  }): Promise<Department[]> => {
    const response = await apiClient.get<any[]>('/departments', { params });
    return response.data.map(mapDepartment);
  },

  /**
   * Get department by ID
   */
  getById: async (id: string): Promise<Department> => {
    const response = await apiClient.get<any>(`/departments/${id}`);
    return mapDepartment(response.data);
  },

  /**
   * Create a new department
   */
  create: async (data: CreateDepartmentRequest): Promise<Department> => {
    const response = await apiClient.post<any>('/departments', data);
    return mapDepartment(response.data);
  },

  /**
   * Update a department
   */
  update: async (id: string, data: UpdateDepartmentRequest): Promise<Department> => {
    const response = await apiClient.put<any>(`/departments/${id}`, data);
    return mapDepartment(response.data);
  },

  /**
   * Delete a department
   */
  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/departments/${id}`);
  },

  /**
   * Get department members
   */
  getMembers: async (id: string): Promise<DepartmentMember[]> => {
    const response = await apiClient.get<any[]>(`/departments/${id}/members`);
    return response.data.map((m: any) => ({
      userId: m.user_id,
      username: m.username,
      email: m.email,
      role: m.role,
      displayName: m.display_name,
    }));
  },

  /**
   * Get department agents
   */
  getAgents: async (id: string): Promise<DepartmentAgent[]> => {
    const response = await apiClient.get<any[]>(`/departments/${id}/agents`);
    return response.data.map((a: any) => ({
      agentId: a.agent_id,
      name: a.name,
      agentType: a.agent_type,
      status: a.status,
      accessLevel: a.access_level,
      ownerUsername: a.owner_username,
    }));
  },

  /**
   * Get department statistics
   */
  getStats: async (id: string): Promise<DepartmentStats> => {
    const response = await apiClient.get<any>(`/departments/${id}/stats`);
    return {
      memberCount: response.data.member_count,
      agentCount: response.data.agent_count,
      knowledgeCount: response.data.knowledge_count,
      activeTaskCount: response.data.active_task_count,
    };
  },
};
