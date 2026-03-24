import apiClient from "./client";
import type { RequestConfigWithMeta } from "./client";
import type { Agent } from "../types/agent";
import type {
  AgentConversationDetail,
  AgentConversationHistorySummary,
  AgentConversationSummary,
  ConversationMessage,
  FeishuPublicationConfig,
} from "../types/agent";

export interface CreateAgentRequest {
  name: string;
  type: string;
  template_id?: string;
  avatar?: string;
  systemPrompt?: string;
  model?: string;
  provider?: string;
  temperature?: number;
  maxTokens?: number;
  topP?: number;
  accessLevel?: 'private' | 'department' | 'public' | 'team';
  allowedKnowledge?: string[];
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
  model?: string;
  provider?: string;
  temperature?: number;
  maxTokens?: number;
  topP?: number;
  accessLevel?: 'private' | 'department' | 'public' | 'team';
  allowedKnowledge?: string[];
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

export interface AgentSessionWorkspaceFile {
  name: string;
  path: string;
  size: number;
  is_dir: boolean;
  modified_at?: string;
  previewable_inline?: boolean;
  retentionClass?:
    | "durable"
    | "rebuildable"
    | "ephemeral"
    | "stateful_runtime"
    | string;
}

export interface AgentLogEntry {
  timestamp: string;
  level: "INFO" | "SUCCESS" | "ERROR";
  message: string;
  source: "task" | "audit";
}

export interface AgentMetrics {
  tasksExecuted: number;
  tasksCompleted: number;
  tasksFailed: number;
  completionRate: number;
  successRate: number;
  failureRate: number;
  pendingTasks: number;
  inProgressTasks: number;
  lastActivityAt?: string | null;
}

export interface VoiceTranscriptionResponse {
  text: string;
  language?: string | null;
  duration?: number | null;
  processing_time?: number | null;
}

export interface AgentConversationListResponse {
  items: AgentConversationSummary[];
  total: number;
  hasMore: boolean;
  nextCursor?: string | null;
}

export interface AgentConversationMessagesResponse {
  items: ConversationMessage[];
  total: number;
  historySummary?: AgentConversationHistorySummary | null;
  compactedMessageCount?: number;
  archivedSegmentCount?: number;
  recentWindowSize?: number;
  hasOlderLiveMessages?: boolean;
  olderCursor?: string | null;
}

export interface SaveFeishuPublicationRequest {
  appId: string;
  appSecret?: string;
}

/**
 * Agents API
 */
export const agentsApi = {
  /**
   * Get all agents
   */
  getAll: async (): Promise<Agent[]> => {
    const response = await apiClient.get<Agent[]>("/agents");
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
    const response = await apiClient.post<Agent>("/agents", data);
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
  getLogs: async (agentId: string, limit = 100): Promise<AgentLogEntry[]> => {
    const response = await apiClient.get<AgentLogEntry[]>(
      `/agents/${agentId}/logs`,
      {
        params: { limit },
      },
    );
    return response.data;
  },

  /**
   * Get agent metrics
   */
  getMetrics: async (agentId: string): Promise<AgentMetrics> => {
    const response = await apiClient.get<AgentMetrics>(
      `/agents/${agentId}/metrics`,
    );
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
    const response = await apiClient.get<AgentTemplate[]>("/agents/templates");
    return response.data;
  },

  /**
   * Get template by ID
   */
  getTemplateById: async (templateId: string): Promise<AgentTemplate> => {
    const response = await apiClient.get<AgentTemplate>(
      `/agents/templates/${templateId}`,
    );
    return response.data;
  },

  /**
   * Upload agent avatar
   */
  uploadAvatar: async (
    agentId: string,
    file: Blob,
  ): Promise<{ avatar_url: string; avatar_ref: string }> => {
    const formData = new FormData();
    formData.append("file", file, "avatar.webp");

    const response = await apiClient.post<{
      avatar_url: string;
      avatar_ref: string;
    }>(`/agents/${agentId}/avatar`, formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    });
    return response.data;
  },

  /**
   * Test agent with a message and optional files (streaming SSE)
   * Note: SSE requires native fetch API, but we get auth token from apiClient interceptor
   */
  testAgent: async (
    agentId: string,
    message: string,
    onChunk: (chunk: {
      type: string;
      content: string;
      [key: string]: any;
    }) => void,
    onError?: (error: string) => void,
    onComplete?: () => void,
    history?: Array<{ role: string; content: any }>,
    files?: File[],
    signal?: AbortSignal, // AbortSignal support
    sessionId?: string, // Session ID for persistent execution environment
  ): Promise<void> => {
    try {
      // Get token from auth store (same way apiClient does)
      const { useAuthStore } = await import("../stores/authStore");
      const token = useAuthStore.getState().token;

      // Prepare form data for multipart/form-data request
      const formData = new FormData();
      formData.append("message", message);

      // Add history as JSON string
      if (history && history.length > 0) {
        formData.append("history", JSON.stringify(history));
      }

      // Add files
      if (files && files.length > 0) {
        files.forEach((file) => {
          formData.append("files", file);
        });
      }

      // Build URL with query parameters
      let url = `${apiClient.defaults.baseURL}/agents/${agentId}/test`;
      const params = new URLSearchParams();
      if (sessionId) {
        params.set("session_id", sessionId);
      }
      const query = params.toString();
      if (query) {
        url += `?${query}`;
      }

      // Use native fetch for SSE streaming (axios doesn't support SSE well in browser)
      const response = await fetch(url, {
        method: "POST",
        headers: {
          Accept: "text/event-stream",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          // Don't set Content-Type - browser will set it with boundary for multipart/form-data
        },
        body: formData,
        signal, // 传递 AbortSignal
      });

      if (!response.ok) {
        const errorText = await response.text();
        let errorMessage = "Failed to test agent";

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
        const error = "No response body";
        if (onError) onError(error);
        throw new Error(error);
      }

      try {
        let buffer = "";

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
          const lines = buffer.split("\n");
          buffer = lines.pop() || ""; // Keep incomplete line in buffer

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                const data = JSON.parse(line.slice(6));
                onChunk(data);
              } catch (e) {
                console.error("Failed to parse SSE data:", line, e);
              }
            }
          }
        }
      } catch (error) {
        // Check if error is due to abort
        if (error instanceof Error && error.name === "AbortError") {
          console.log("Stream aborted by user");
          return; // Don't call onError for user-initiated abort
        }

        const errorMessage =
          error instanceof Error ? error.message : "Unknown error";
        if (onError) onError(errorMessage);
        throw error;
      } finally {
        // Always release the reader
        reader.releaseLock();
      }
    } catch (error: any) {
      // Check if error is due to abort
      if (error.name === "AbortError") {
        console.log("Request aborted by user");
        return; // Don't call onError for user-initiated abort
      }

      const errorMessage = error.message || "Failed to test agent";
      if (onError) onError(errorMessage);
      throw error;
    }
  },

  /**
   * Transcribe one recorded audio clip for voice input in test chat.
   */
  transcribeVoiceInput: async (
    file: File,
  ): Promise<VoiceTranscriptionResponse> => {
    const formData = new FormData();
    formData.append("file", file);

    const response = await apiClient.post<VoiceTranscriptionResponse>(
      "/agents/transcribe",
      formData,
      {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      },
    );

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
    sessionId: string,
  ): Promise<{ success: boolean; error?: string }> => {
    try {
      await apiClient.delete(`/agents/${agentId}/sessions/${sessionId}`);
      return { success: true };
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error
          ? error.message
          : "Unknown error while ending session";
      console.warn(
        `[agentsApi.endSession] Failed for ${agentId}/${sessionId}: ${errorMessage}`,
      );
      return { success: false, error: errorMessage };
    }
  },

  /**
   * Get all active sessions for an agent
   */
  getAgentSessions: async (
    agentId: string,
  ): Promise<{
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

  /**
   * Browse files in an active agent session workspace.
   */
  getSessionWorkspaceFiles: async (
    agentId: string,
    sessionId: string,
    path?: string,
    recursive = false,
    options?: { suppressErrorToast?: boolean },
  ): Promise<AgentSessionWorkspaceFile[]> => {
    const requestConfig: RequestConfigWithMeta = {
      params: {
        ...(path ? { path } : {}),
        ...(recursive ? { recursive: true } : {}),
      },
      suppressErrorToast: options?.suppressErrorToast,
    };
    const response = await apiClient.get<
      Array<{
        name: string;
        path: string;
        size: number;
        is_directory?: boolean;
        is_dir?: boolean;
        modified_at?: string;
        previewable_inline?: boolean;
      }>
    >(
      `/agents/${agentId}/sessions/${sessionId}/workspace/files`,
      requestConfig,
    );
    return response.data.map((item) => ({
      name: item.name,
      path: item.path,
      size: item.size,
      is_dir: item.is_dir ?? Boolean(item.is_directory),
      modified_at: item.modified_at,
      previewable_inline: item.previewable_inline,
    }));
  },

  /**
   * Download one file from an active agent session workspace.
   */
  downloadSessionWorkspaceFile: async (
    agentId: string,
    sessionId: string,
    path: string,
    options?: { suppressErrorToast?: boolean },
  ): Promise<Blob> => {
    const requestConfig: RequestConfigWithMeta = {
      params: { path },
      responseType: "blob",
      suppressErrorToast: options?.suppressErrorToast,
    };
    const response = await apiClient.get(
      `/agents/${agentId}/sessions/${sessionId}/workspace/download`,
      requestConfig,
    );
    return response.data;
  },

  createConversation: async (
    agentId: string,
  ): Promise<AgentConversationSummary> => {
    const response = await apiClient.post<{
      conversation: AgentConversationSummary;
    }>(`/agents/${agentId}/conversations`);
    return response.data.conversation;
  },

  getConversations: async (
    agentId: string,
    options?: { limit?: number; cursor?: string | null },
  ): Promise<AgentConversationListResponse> => {
    const response = await apiClient.get<AgentConversationListResponse>(
      `/agents/${agentId}/conversations`,
      {
        params: {
          limit: options?.limit,
          cursor: options?.cursor || undefined,
        },
      },
    );
    return response.data;
  },

  getConversation: async (
    agentId: string,
    conversationId: string,
  ): Promise<AgentConversationDetail> => {
    const response = await apiClient.get<AgentConversationDetail>(
      `/agents/${agentId}/conversations/${conversationId}`,
    );
    return response.data;
  },

  updateConversation: async (
    agentId: string,
    conversationId: string,
    title: string,
  ): Promise<AgentConversationDetail> => {
    const response = await apiClient.patch<AgentConversationDetail>(
      `/agents/${agentId}/conversations/${conversationId}`,
      { title },
    );
    return response.data;
  },

  deleteConversation: async (
    agentId: string,
    conversationId: string,
  ): Promise<void> => {
    try {
      const requestConfig: RequestConfigWithMeta = { suppressErrorToast: true };
      await apiClient.delete(
        `/agents/${agentId}/conversations/${conversationId}`,
        requestConfig,
      );
    } catch (error: any) {
      if (error?.response?.status === 404) {
        return;
      }
      throw error;
    }
  },

  getConversationMessages: async (
    agentId: string,
    conversationId: string,
    options?: { limit?: number; before?: string | null },
  ): Promise<AgentConversationMessagesResponse> => {
    const response = await apiClient.get<AgentConversationMessagesResponse>(
      `/agents/${agentId}/conversations/${conversationId}/messages`,
      {
        params: {
          limit: options?.limit,
          before: options?.before || undefined,
        },
      },
    );
    return response.data;
  },

  sendConversationMessage: async (
    agentId: string,
    conversationId: string,
    message: string,
    onChunk: (chunk: {
      type: string;
      content?: string;
      [key: string]: any;
    }) => void,
    onError?: (error: string) => void,
    onComplete?: () => void,
    files?: File[],
    signal?: AbortSignal,
  ): Promise<void> => {
    try {
      const { useAuthStore } = await import("../stores/authStore");
      const token = useAuthStore.getState().token;

      const formData = new FormData();
      formData.append("message", message);
      if (files && files.length > 0) {
        files.forEach((file) => {
          formData.append("files", file);
        });
      }

      const response = await fetch(
        `${apiClient.defaults.baseURL}/agents/${agentId}/conversations/${conversationId}/messages`,
        {
          method: "POST",
          headers: {
            Accept: "text/event-stream",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: formData,
          signal,
        },
      );

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || "Failed to send conversation message");
      }
      if (!response.body) {
        throw new Error("No response body received");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let completed = false;

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            break;
          }

          buffer += decoder.decode(value, { stream: true });
          const events = buffer.split("\n\n");
          buffer = events.pop() || "";

          for (const event of events) {
            const lines = event.split("\n");
            for (const line of lines) {
              if (!line.startsWith("data: ")) {
                continue;
              }
              const data = line.slice(6);
              try {
                const parsed = JSON.parse(data);
                onChunk(parsed);
                if (parsed.type === "done") {
                  completed = true;
                  onComplete?.();
                }
              } catch (parseError) {
                console.error(
                  "Failed to parse conversation SSE chunk:",
                  parseError,
                  data,
                );
              }
            }
          }
        }
        if (!completed) {
          onComplete?.();
        }
      } finally {
        reader.releaseLock();
      }
    } catch (error: any) {
      if (error.name === "AbortError") {
        return;
      }
      const errorMessage =
        error.message || "Failed to send conversation message";
      onError?.(errorMessage);
      throw error;
    }
  },

  releaseConversationRuntime: async (
    agentId: string,
    conversationId: string,
  ): Promise<{ success: boolean }> => {
    try {
      const requestConfig: RequestConfigWithMeta = { suppressErrorToast: true };
      const response = await apiClient.post<{ success: boolean }>(
        `/agents/${agentId}/conversations/${conversationId}/runtime/release`,
        undefined,
        requestConfig,
      );
      return response.data;
    } catch (error: any) {
      if (error?.response?.status === 404) {
        return { success: true };
      }
      throw error;
    }
  },

  getConversationWorkspaceFiles: async (
    agentId: string,
    conversationId: string,
    path?: string,
    recursive = false,
    options?: { suppressErrorToast?: boolean },
  ): Promise<AgentSessionWorkspaceFile[]> => {
    const requestConfig: RequestConfigWithMeta = {
      params: {
        ...(path ? { path } : {}),
        ...(recursive ? { recursive: true } : {}),
      },
      suppressErrorToast: options?.suppressErrorToast,
    };
    const response = await apiClient.get<
      Array<{
        name: string;
        path: string;
        size: number;
        is_directory?: boolean;
        is_dir?: boolean;
        modified_at?: string;
        previewable_inline?: boolean;
        retention_class?: string;
      }>
    >(
      `/agents/${agentId}/conversations/${conversationId}/workspace/files`,
      requestConfig,
    );
    return response.data.map((item) => ({
      name: item.name,
      path: item.path,
      size: item.size,
      is_dir: item.is_dir ?? Boolean(item.is_directory),
      modified_at: item.modified_at,
      previewable_inline: item.previewable_inline,
      retentionClass: item.retention_class,
    }));
  },

  downloadConversationWorkspaceFile: async (
    agentId: string,
    conversationId: string,
    path: string,
    options?: { suppressErrorToast?: boolean },
  ): Promise<Blob> => {
    const requestConfig: RequestConfigWithMeta = {
      params: { path },
      responseType: "blob",
      suppressErrorToast: options?.suppressErrorToast,
    };
    const response = await apiClient.get(
      `/agents/${agentId}/conversations/${conversationId}/workspace/download`,
      requestConfig,
    );
    return response.data;
  },

  getFeishuPublication: async (
    agentId: string,
  ): Promise<FeishuPublicationConfig> => {
    const response = await apiClient.get<FeishuPublicationConfig>(
      `/agents/${agentId}/channels/feishu`,
    );
    return response.data;
  },

  saveFeishuPublication: async (
    agentId: string,
    payload: SaveFeishuPublicationRequest,
  ): Promise<FeishuPublicationConfig> => {
    const response = await apiClient.put<FeishuPublicationConfig>(
      `/agents/${agentId}/channels/feishu`,
      payload,
    );
    return response.data;
  },

  publishFeishuPublication: async (
    agentId: string,
  ): Promise<FeishuPublicationConfig> => {
    const response = await apiClient.post<FeishuPublicationConfig>(
      `/agents/${agentId}/channels/feishu/publish`,
    );
    return response.data;
  },

  unpublishFeishuPublication: async (
    agentId: string,
  ): Promise<FeishuPublicationConfig> => {
    const response = await apiClient.post<FeishuPublicationConfig>(
      `/agents/${agentId}/channels/feishu/unpublish`,
    );
    return response.data;
  },
};
