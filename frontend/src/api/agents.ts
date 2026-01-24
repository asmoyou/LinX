import apiClient from './client';
import { useAuthStore } from '../stores/authStore';
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
   * Upload agent avatar
   */
  uploadAvatar: async (agentId: string, file: Blob): Promise<{ avatar_url: string }> => {
    const formData = new FormData();
    formData.append('file', file, 'avatar.webp');
    
    const response = await apiClient.post<{ avatar_url: string }>(
      `/agents/${agentId}/avatar`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    );
    return response.data;
  },

  /**
   * Test agent with a message (streaming SSE)
   * Note: SSE requires native fetch API, but we get auth token from apiClient interceptor
   */
  testAgent: async (
    agentId: string,
    message: string,
    onChunk: (chunk: { type: string; content: string }) => void,
    onError?: (error: string) => void,
    onComplete?: () => void
  ): Promise<void> => {
    try {
      // Get token from auth store (same way apiClient does)
      const { useAuthStore } = await import('../stores/authStore');
      const token = useAuthStore.getState().token;
      
      // Use native fetch for SSE streaming (axios doesn't support SSE well in browser)
      const response = await fetch(`${apiClient.defaults.baseURL}/agents/${agentId}/test`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ message }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        let errorMessage = 'Failed to test agent';
        
        try {
          const errorData = JSON.parse(errorText);
          errorMessage = errorData.message || errorData.detail || errorMessage;
        } catch {
          errorMessage = errorText || errorMessage;
        }
        
        if (onError) onError(errorMessage);
        throw new Error(errorMessage);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        const error = 'No response body';
        if (onError) onError(error);
        throw new Error(error);
      }

      try {
        let buffer = '';
        
        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            // Stream ended, call onComplete
            if (onComplete) onComplete();
            break;
          }

          // Decode chunk and add to buffer
          buffer += decoder.decode(value, { stream: true });
          
          // Process complete lines
          const lines = buffer.split('\n');
          buffer = lines.pop() || ''; // Keep incomplete line in buffer

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));
                onChunk(data);

                if (data.type === 'error' && onError) {
                  onError(data.content);
                }
              } catch (e) {
                console.error('Failed to parse SSE data:', line, e);
              }
            }
          }
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        if (onError) onError(errorMessage);
        throw error;
      }
    } catch (error: any) {
      const errorMessage = error.message || 'Failed to test agent';
      if (onError) onError(errorMessage);
      throw error;
    }
  },
};
