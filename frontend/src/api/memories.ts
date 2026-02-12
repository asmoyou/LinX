import apiClient from "./client";
import type {
  Memory,
  MemoryType,
  MemoryFilter,
  MemoryIndexInfo,
} from "../types/memory";

export interface CreateMemoryRequest {
  type: MemoryType;
  content: string;
  summary?: string;
  agent_id?: string;
  tags?: string[];
  metadata?: Record<string, any>;
}

export interface SearchMemoriesRequest {
  query: string;
  type?: MemoryType;
  limit?: number;
  filters?: MemoryFilter;
}

export interface ShareMemoryRequest {
  user_ids?: string[];
  agent_ids?: string[];
}

/**
 * Memory System API
 */
export const memoriesApi = {
  /**
   * Get all memories
   */
  getAll: async (filters?: MemoryFilter): Promise<Memory[]> => {
    const response = await apiClient.get<Memory[]>("/memories", {
      params: filters,
    });
    return response.data;
  },

  /**
   * Get memory by ID
   */
  getById: async (memoryId: string): Promise<Memory> => {
    const response = await apiClient.get<Memory>(`/memories/${memoryId}`);
    return response.data;
  },

  /**
   * Create memory
   */
  create: async (data: CreateMemoryRequest): Promise<Memory> => {
    const response = await apiClient.post<Memory>("/memories", data);
    return response.data;
  },

  /**
   * Update memory
   */
  update: async (
    memoryId: string,
    data: Partial<CreateMemoryRequest>,
  ): Promise<Memory> => {
    const response = await apiClient.put<Memory>(`/memories/${memoryId}`, data);
    return response.data;
  },

  /**
   * Delete memory
   */
  delete: async (memoryId: string): Promise<void> => {
    await apiClient.delete(`/memories/${memoryId}`);
  },

  /**
   * Search memories (semantic search)
   */
  search: async (data: SearchMemoriesRequest): Promise<Memory[]> => {
    const response = await apiClient.post<Memory[]>("/memories/search", data);
    return response.data;
  },

  /**
   * Get memories by type
   */
  getByType: async (
    type: MemoryType,
    filters?: MemoryFilter,
  ): Promise<Memory[]> => {
    const response = await apiClient.get<Memory[]>(`/memories/type/${type}`, {
      params: filters,
    });
    return response.data;
  },

  /**
   * Get memories by agent
   */
  getByAgent: async (agentId: string): Promise<Memory[]> => {
    const response = await apiClient.get<Memory[]>(
      `/memories/agent/${agentId}`,
    );
    return response.data;
  },

  /**
   * Share memory
   */
  share: async (
    memoryId: string,
    data: ShareMemoryRequest,
  ): Promise<Memory> => {
    const response = await apiClient.post<Memory>(
      `/memories/${memoryId}/share`,
      data,
    );
    return response.data;
  },

  /**
   * Rebuild vector index for one memory
   */
  reindex: async (memoryId: string): Promise<Memory> => {
    const response = await apiClient.post<Memory>(
      `/memories/${memoryId}/reindex`,
    );
    return response.data;
  },

  /**
   * Inspect index payload for one memory
   */
  getIndex: async (memoryId: string): Promise<MemoryIndexInfo> => {
    const response = await apiClient.get<MemoryIndexInfo>(
      `/memories/${memoryId}/index`,
    );
    return response.data;
  },

  /**
   * Get shared memories
   */
  getShared: async (): Promise<Memory[]> => {
    const response = await apiClient.get<Memory[]>("/memories/shared");
    return response.data;
  },
};
