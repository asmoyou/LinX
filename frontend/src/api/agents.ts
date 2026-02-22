import apiClient from './client';
import type { Agent } from '../types/agent';

export interface CreateAgentRequest {
  name: string;
  type: string;
  template_id?: string;
  avatar?: string;
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
  topK?: number;
  similarityThreshold?: number;
  capabilities?: string[];
  config?: Record<string, any>;
  department_id?: string;
}

export interface UpdateAgentRequest {
  name?: string;
  avatar?: string;
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
  topK?: number;
  similarityThreshold?: number;
  capabilities?: string[];
  config?: Record<string, any>;
  department_id?: string | null;
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
  uploadAvatar: async (agentId: string, file: Blob): Promise<{ avatar_url: string; avatar_ref: string }> => {
    const formData = new FormData();
    formData.append('file', file, 'avatar.webp');

    const response = await apiClient.post<{ avatar_url: string; avatar_ref: string }>(
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
   * Test agent with a message and optional files (streaming SSE)
   * Note: SSE requires native fetch API, but we get auth token from apiClient interceptor
   */
  testAgent: async (
    agentId: string,
    message: string,
    onChunk: (chunk: { type: string; content: string; [key: string]: any }) => void,
    onError?: (error: string) => void,
    onComplete?: () => void,
    history?: Array<{ role: string; content: string }>,
    files?: File[],
    signal?: AbortSignal,  // AbortSignal support
    sessionId?: string     // Session ID for persistent execution environment
  ): Promise<void> => {
    try {
      // Get token from auth store (same way apiClient does)
      const { useAuthStore } = await import('../stores/authStore');
      const token = useAuthStore.getState().token;

      // Prepare form data for multipart/form-data request
      const formData = new FormData();
      formData.append('message', message);

      // Add history as JSON string
      if (history && history.length > 0) {
        formData.append('history', JSON.stringify(history));
      }

      // Add files
      if (files && files.length > 0) {
        files.forEach((file) => {
          formData.append('files', file);
        });
      }

      // Build URL with session_id query parameter
      let url = `${apiClient.defaults.baseURL}/agents/${agentId}/test`;
      if (sessionId) {
        url += `?session_id=${encodeURIComponent(sessionId)}`;
      }

      // Use native fetch for SSE streaming (axios doesn't support SSE well in browser)
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Accept': 'text/event-stream',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          // Don't set Content-Type - browser will set it with boundary for multipart/form-data
        },
        body: formData,
        signal,  // 传递 AbortSignal
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
        // Check if error is due to abort
        if (error instanceof Error && error.name === 'AbortError') {
          console.log('Stream aborted by user');
          return; // Don't call onError for user-initiated abort
        }
        
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        if (onError) onError(errorMessage);
        throw error;
      } finally {
        // Always release the reader
        reader.releaseLock();
      }
    } catch (error: any) {
      // Check if error is due to abort
      if (error.name === 'AbortError') {
        console.log('Request aborted by user');
        return; // Don't call onError for user-initiated abort
      }
      
      const errorMessage = error.message || 'Failed to test agent';
      if (onError) onError(errorMessage);
      throw error;
    }
  },
  
  /**
   * Get agent's configured skills and available skills
   */
  getAgentSkills: async (agentId: string): Promise<{
    agent_id: string;
    configured_skills: string[];
    available_skills: Array<{
      skill_id: string;
      name: string;
      description: string;
      skill_type: string;
      version: string;
    }>;
  }> => {
    const response = await apiClient.get(`/agents/${agentId}/skills`);
    return response.data;
  },
  
  /**
   * Update agent's configured skills
   */
  updateAgentSkills: async (agentId: string, skillNames: string[]): Promise<Agent> => {
    const response = await apiClient.put<Agent>(`/agents/${agentId}/skills`, {
      skill_names: skillNames
    });
    return response.data;
  },

  /**
   * End an agent session and clean up resources
   *
   * This should be called when the test dialog is closed to clean up:
   * - Working directory and files created during the session
   * - Sandbox container (if sandbox mode was enabled)
   *
   * The session is also automatically cleaned up after TTL expiration,
   * so this is optional but recommended for explicit cleanup.
   *
   * Note: The backend DELETE endpoint is idempotent — it returns 200
   * even if the session is already gone, so no 404 toast will appear.
   */
  endSession: async (
    agentId: string,
    sessionId: string
  ): Promise<{ success: boolean; error?: string }> => {
    try {
      await apiClient.delete(`/agents/${agentId}/sessions/${sessionId}`);
      return { success: true };
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error ? error.message : 'Unknown error while ending session';
      console.warn(`[agentsApi.endSession] Failed for ${agentId}/${sessionId}: ${errorMessage}`);
      return { success: false, error: errorMessage };
    }
  },

  /**
   * Get all active sessions for an agent
   */
  getAgentSessions: async (agentId: string): Promise<{
    agent_id: string;
    sessions: Array<{
      session_id: string;
      agent_id: string;
      created_at: string;
      last_activity: string;
      remaining_ttl_seconds: number;
      use_sandbox: boolean;
      workdir: string;
    }>;
    total_count: number;
  }> => {
    const response = await apiClient.get(`/agents/${agentId}/sessions`);
    return response.data;
  },
};
