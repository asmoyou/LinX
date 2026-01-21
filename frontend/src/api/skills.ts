import apiClient from './client';

export interface Skill {
  id: string;
  name: string;
  description: string;
  interface_definition: {
    input: Record<string, string>;
    output: Record<string, string>;
  };
  dependencies: string[];
  version: string;
  created_at: string;
}

export interface CreateSkillRequest {
  name: string;
  description: string;
  interface_definition: {
    input: Record<string, string>;
    output: Record<string, string>;
  };
  dependencies?: string[];
  implementation?: string;
}

export interface UpdateSkillRequest {
  description?: string;
  interface_definition?: {
    input: Record<string, string>;
    output: Record<string, string>;
  };
  dependencies?: string[];
}

/**
 * Skills API
 */
export const skillsApi = {
  /**
   * Get all skills
   */
  getAll: async (): Promise<Skill[]> => {
    const response = await apiClient.get<Skill[]>('/skills');
    return response.data;
  },

  /**
   * Get skill by ID
   */
  getById: async (skillId: string): Promise<Skill> => {
    const response = await apiClient.get<Skill>(`/skills/${skillId}`);
    return response.data;
  },

  /**
   * Get skill by name
   */
  getByName: async (name: string): Promise<Skill> => {
    const response = await apiClient.get<Skill>(`/skills/name/${name}`);
    return response.data;
  },

  /**
   * Create skill
   */
  create: async (data: CreateSkillRequest): Promise<Skill> => {
    const response = await apiClient.post<Skill>('/skills', data);
    return response.data;
  },

  /**
   * Update skill
   */
  update: async (skillId: string, data: UpdateSkillRequest): Promise<Skill> => {
    const response = await apiClient.put<Skill>(`/skills/${skillId}`, data);
    return response.data;
  },

  /**
   * Delete skill
   */
  delete: async (skillId: string): Promise<void> => {
    await apiClient.delete(`/skills/${skillId}`);
  },

  /**
   * Get default skills
   */
  getDefaults: async (): Promise<Skill[]> => {
    const response = await apiClient.get<Skill[]>('/skills/defaults');
    return response.data;
  },

  /**
   * Search skills
   */
  search: async (query: string): Promise<Skill[]> => {
    const response = await apiClient.get<Skill[]>('/skills/search', {
      params: { q: query },
    });
    return response.data;
  },
};
