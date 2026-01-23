import apiClient from './client';
import type { Agent } from '../types/agent';

export interface CreateAgentRequest {
  name: string;
  type: string;
  template_id?: string;
  systemPrompt?: string;
  skills?: string[];
  model?: string;
  provider?: string;
  temperature?: number;
  maxTokens?: number;
  topP?: number;
  accessLevel?: string;
  allowedKnowledge?: string[];
  allowedMemory?: string[];
  capabilities?: string[];
  config?: Record<string, any>;
}

export interface UpdateAgentRequest {
  name?: string;
  systemPrompt?: string;
  skills?: string[];
  model?: string;
  provider?: string;
  temperature?: number;
  maxTokens?: number;
  topP?: number;
  accessLevel?: string;
  allowedKnowledge?: string[];
  allowedMemory?: string[];
  capabilities?: string[];
  config?: Record<string, any>;
}

export interface AgentTemplate {
  id: string;
  name: string;
  description: string;
  default_skills: string[];
  default_config: Record<string, any>;
}

/**
 * Agents API
 */
export const agentsApi = {
  /**
   * Get all agents
   */
  getAll: async (): Promise<Agent[]> => {
    const response = await apiClient.get<Agent[]>('/agents');
    return response.data;
  },

  /**
   * Get agent by ID
   */
  getById: async (agentId: string): Promise<Agent> => {
    const response = await apiClient.get<Agent>(`/agents/${agentId}`);
    return response.data;
  },

  /**
   * Create new agent
   */
  create: async (data: CreateAgentRequest): Promise<Agent> => {
    const response = await apiClient.post<Agent>('/agents', data);
    return response.data;
  },

  /**
   * Update agent
   */
  update: async (agentId: string, data: UpdateAgentRequest): Promise<Agent> => {
    const response = await apiClient.put<Agent>(`/agents/${agentId}`, data);
    return response.data;
  },

  /**
   * Delete agent
   */
  delete: async (agentId: string): Promise<void> => {
    await apiClient.delete(`/agents/${agentId}`);
  },

  /**
   * Get agent logs
   */
  getLogs: async (agentId: string, limit = 100): Promise<any[]> => {
    const response = await apiClient.get(`/agents/${agentId}/logs`, {
      params: { limit },
    });
    return response.data;
  },

  /**
   * Get agent metrics
   */
  getMetrics: async (agentId: string): Promise<any> => {
    const response = await apiClient.get(`/agents/${agentId}/metrics`);
    return response.data;
  },

  /**
   * Pause agent
   */
  pause: async (agentId: string): Promise<void> => {
    await apiClient.post(`/agents/${agentId}/pause`);
  },

  /**
   * Resume agent
   */
  resume: async (agentId: string): Promise<void> => {
    await apiClient.post(`/agents/${agentId}/resume`);
  },

  /**
   * Get agent templates
   */
  getTemplates: async (): Promise<AgentTemplate[]> => {
    const response = await apiClient.get<AgentTemplate[]>('/agents/templates');
    return response.data;
  },

  /**
   * Get template by ID
   */
  getTemplateById: async (templateId: string): Promise<AgentTemplate> => {
    const response = await apiClient.get<AgentTemplate>(`/agents/templates/${templateId}`);
    return response.data;
  },

  /**
   * Test agent with a message (streaming)
   */
  testAgent: async (
    agentId: string,
    message: string,
    onChunk: (chunk: { type: string; content: string }) => void,
    onError?: (error: string) => void,
    onComplete?: () => void
  ): Promise<void> => {
    const token = localStorage.getItem('token');
    const response = await fetch(`${apiClient.defaults.baseURL}/agents/${agentId}/test`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ message }),
    });

    if (!response.ok) {
      const error = await response.text();
      if (onError) onError(error);
      throw new Error(`Failed to test agent: ${error}`);
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();

    if (!reader) {
      if (onError) onError('No response body');
      throw new Error('No response body');
    }

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              onChunk(data);

              if (data.type === 'done' && onComplete) {
                onComplete();
              } else if (data.type === 'error' && onError) {
                onError(data.content);
              }
            } catch (e) {
              console.error('Failed to parse SSE data:', e);
            }
          }
        }
      }
    } catch (error) {
      if (onError) onError(error instanceof Error ? error.message : 'Unknown error');
      throw error;
    }
  },
};
