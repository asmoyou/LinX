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
  skill_md_content?: string;
  homepage?: string;
  metadata?: {
    emoji?: string;
    requires?: {
      bins?: string[];
      env?: string[];
      config?: string[];
    };
    os?: string[];
  };
  gating_status?: {
    eligible: boolean;
    missing_bins?: string[];
    missing_env?: string[];
    missing_config?: string[];
    os_compatible?: boolean;
    reason?: string;
  };
}

export interface CreateSkillRequest {
  name: string;
  description: string;
  skill_type?: string;
  code?: string;
  config?: Record<string, any>;
  dependencies?: string[];
  version?: string;
  package_file?: File;
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
    // Always use multipart/form-data for consistency
    const formData = new FormData();
    formData.append('name', data.name);
    formData.append('description', data.description);
    if (data.skill_type) formData.append('skill_type', data.skill_type);
    if (data.version) formData.append('version', data.version);
    if (data.package_file) formData.append('package_file', data.package_file);
    if (data.code) formData.append('code', data.code);
    if (data.config) formData.append('config', JSON.stringify(data.config));
    if (data.dependencies && data.dependencies.length > 0) {
      formData.append('dependencies', JSON.stringify(data.dependencies));
    }

    const response = await apiClient.post<Skill>('/skills', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
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
   * For langchain_tool: Pass structured inputs
   * For agent_skill: Pass natural_language_input and required agent_id
   */
  async testSkill(
    skillId: string,
    params: { 
      inputs?: Record<string, any>; 
      natural_language_input?: string; 
      agent_id?: string;
    }
  ): Promise<any> {
    const response = await apiClient.post(`/skills/${skillId}/test`, params);
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

  /**
   * List environment variable keys for current user
   */
  async listEnvVars(): Promise<string[]> {
    const response = await apiClient.get<string[]>('/skills/env-vars');
    return response.data;
  },

  /**
   * Set environment variable for current user
   */
  async setEnvVar(key: string, value: string): Promise<{ message: string }> {
    const response = await apiClient.post<{ message: string }>('/skills/env-vars', {
      key,
      value,
    });
    return response.data;
  },

  /**
   * Delete environment variable for current user
   */
  async deleteEnvVar(key: string): Promise<void> {
    await apiClient.delete(`/skills/env-vars/${key}`);
  },

  /**
   * Get file list for agent_skill package
   */
  async getFiles(skillId: string): Promise<{
    skill_id: string;
    skill_name: string;
    skill_type: string;
    files: FileTreeItem[];
  }> {
    const response = await apiClient.get(`/skills/${skillId}/files`);
    return response.data;
  },

  /**
   * Get content of a specific file in agent_skill package
   */
  async getFileContent(skillId: string, filePath: string): Promise<{
    skill_id: string;
    file_path: string;
    file_name: string;
    content: string;
    size: number;
    extension: string;
  }> {
    const response = await apiClient.get(`/skills/${skillId}/files/${filePath}`);
    return response.data;
  },

  /**
   * Update file content in agent_skill package (TODO: Backend implementation needed)
   */
  async updateFileContent(skillId: string, filePath: string, content: string): Promise<void> {
    await apiClient.put(`/skills/${skillId}/files/${filePath}`, { content });
  },

  /**
   * Re-upload package for agent_skill (TODO: Backend implementation needed)
   */
  async updatePackage(skillId: string, formData: FormData): Promise<void> {
    await apiClient.put(`/skills/${skillId}/package`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  },
};

export interface FileTreeItem {
  name: string;
  path: string;
  type: 'file' | 'directory';
  file_type?: 'python' | 'text' | 'config' | 'script' | 'other';
  size?: number;
  children?: FileTreeItem[];
}
