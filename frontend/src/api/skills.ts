/**
 * Skills API client
 * Handles all skill-related API calls
 */

import apiClient from './client';

export interface Skill {
  skill_id: string;
  name: string;
  description: string;
  version: string;
  skill_type?: string;
  storage_type?: string;
  storage_path?: string;
  code?: string;
  config?: Record<string, any>;
  manifest?: Record<string, any>;
  is_active?: boolean;
  is_system?: boolean;
  execution_count?: number;
  last_executed_at?: string;
  average_execution_time?: number;
  interface_definition: {
    inputs: Record<string, string>;
    outputs: Record<string, string>;
    required_inputs?: string[];
  };
  dependencies: string[];
  created_at: string;
  created_by?: string;
}

export interface CreateSkillRequest {
  name: string;
  description: string;
  skill_type?: string;
  code?: string;
  config?: Record<string, any>;
  dependencies?: string[];
  version?: string;
}

export interface UpdateSkillRequest {
  description?: string;
  code?: string;
  dependencies?: string[];
}

export const skillsApi = {
  /**
   * Get all skills
   */
  async getAll(limit = 100, offset = 0, includeCode = true): Promise<Skill[]> {
    const response = await apiClient.get<Skill[]>('/skills', {
      params: { limit, offset, include_code: includeCode },
    });
    return response.data;
  },

  /**
   * Get skill by ID
   */
  async getById(skillId: string): Promise<Skill> {
    const response = await apiClient.get<Skill>(`/skills/${skillId}`);
    return response.data;
  },

  /**
   * Search skills
   */
  async search(query: string): Promise<Skill[]> {
    const response = await apiClient.get<Skill[]>('/skills/search', {
      params: { query },
    });
    return response.data;
  },

  /**
   * Create new skill
   */
  async create(data: CreateSkillRequest): Promise<Skill> {
    const response = await apiClient.post<Skill>('/skills', data);
    return response.data;
  },

  /**
   * Update skill
   */
  async update(skillId: string, data: UpdateSkillRequest): Promise<Skill> {
    const response = await apiClient.put<Skill>(`/skills/${skillId}`, data);
    return response.data;
  },

  /**
   * Delete skill
   */
  async delete(skillId: string): Promise<void> {
    await apiClient.delete(`/skills/${skillId}`);
  },

  /**
   * Get skill templates
   */
  async getTemplates(category?: string): Promise<any[]> {
    const response = await apiClient.get('/skills/templates', {
      params: category ? { category } : undefined,
    });
    return response.data;
  },

  /**
   * Create skill from template
   */
  async createFromTemplate(templateId: string, name: string, description?: string): Promise<Skill> {
    const response = await apiClient.post('/skills/from-template', {
      template_id: templateId,
      name,
      description,
    });
    return response.data;
  },

  /**
   * Test skill execution
   */
  async testSkill(skillId: string, inputs: Record<string, any>): Promise<any> {
    const response = await apiClient.post(`/skills/${skillId}/test`, inputs);
    return response.data;
  },

  /**
   * Activate skill
   */
  async activateSkill(skillId: string): Promise<void> {
    await apiClient.post(`/skills/${skillId}/activate`);
  },

  /**
   * Deactivate skill
   */
  async deactivateSkill(skillId: string): Promise<void> {
    await apiClient.post(`/skills/${skillId}/deactivate`);
  },

  /**
   * Get skill execution statistics
   */
  async getStats(skillId: string): Promise<any> {
    const response = await apiClient.get(`/skills/${skillId}/stats`);
    return response.data;
  },

  /**
   * Validate skill code
   */
  async validateCode(code: string): Promise<any> {
    const response = await apiClient.post('/skills/validate', { code });
    return response.data;
  },

  /**
   * Download package template
   */
  async downloadPackageTemplate(): Promise<Blob> {
    const response = await apiClient.get('/skills/templates/package-example', {
      responseType: 'blob',
    });
    return response.data;
  },
};
