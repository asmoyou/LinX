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
  interface_definition: {
    inputs: Record<string, string>;
    outputs: Record<string, string>;
    required_inputs?: string[];
  };
  dependencies: string[];
  created_at: string;
}

export interface CreateSkillRequest {
  name: string;
  description: string;
  interface_definition: {
    inputs: Record<string, string>;
    outputs: Record<string, string>;
    required_inputs?: string[];
  };
  dependencies?: string[];
  version?: string;
}

export interface UpdateSkillRequest {
  description?: string;
  interface_definition?: {
    inputs: Record<string, string>;
    outputs: Record<string, string>;
    required_inputs?: string[];
  };
  dependencies?: string[];
}

export const skillsApi = {
  /**
   * Get all skills
   */
  async getAll(limit = 100, offset = 0): Promise<Skill[]> {
    const response = await apiClient.get<Skill[]>('/skills', {
      params: { limit, offset },
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
   * Register default skills
   */
  async registerDefaults(): Promise<{ registered_count: number }> {
    const response = await apiClient.post<{ registered_count: number }>(
      '/skills/register-defaults'
    );
    return response.data;
  },
};
