import apiClient from "./client";
import type {
  MemoryRecord,
  MemoryConfig,
  MemoryConfigSkillCandidates,
  MemoryConfigSkillRuntime,
  MemoryConfigEmbedding,
  MemoryConfigFactExtraction,
  MemoryConfigRetrieval,
  MemoryConfigRuntimeContext,
  MemoryConfigSessionLedger,
  MemoryConfigConsolidation,
} from "../types/memory";

export interface ListUserMemoryRequest {
  query?: string;
  user_id?: string;
  limit?: number;
  offset?: number;
  minScore?: number;
  fact_kind?: string;
  record_type?: string;
  date_from?: string;
  date_to?: string;
  importance_min?: number;
  importance_max?: number;
  status?: string;
}

export interface ListUserMemoryResponse {
  items: MemoryRecord[];
  total: number;
}

export interface UpdateMemoryConfigRequest {
  user_memory?: {
    embedding?: Partial<Omit<MemoryConfigEmbedding, "effective" | "sources">>;
    retrieval?: Partial<MemoryConfigRetrieval>;
    extraction?: Partial<
      Omit<MemoryConfigFactExtraction, "effective" | "sources">
    >;
    consolidation?: Partial<MemoryConfigConsolidation>;
  };
  skill_candidates?: {
    extraction?: Partial<
      Omit<MemoryConfigSkillCandidates["extraction"], "effective" | "sources">
    >;
  };
  skill_runtime?: Partial<MemoryConfigSkillRuntime>;
  session_ledger?: Partial<MemoryConfigSessionLedger>;
  runtime_context?: Partial<MemoryConfigRuntimeContext>;
}

const normalizeUserMemoryRecord = (record: MemoryRecord): MemoryRecord => ({
  ...record,
  type: "user_memory",
  metadata: {
    ...(record.metadata || {}),
    record_type: record.type,
  },
});

export const memoryWorkbenchApi = {
  async listUserMemory(
    params?: ListUserMemoryRequest,
  ): Promise<ListUserMemoryResponse> {
    const response = await apiClient.get<MemoryRecord[]>("/user-memory", {
      params,
    });
    const total = parseInt(
      response.headers?.["x-total-count"] || "0",
      10,
    );
    const items = response.data.map(normalizeUserMemoryRecord);
    return { items, total: total || items.length };
  },

  async listUserMemoryProfile(
    params?: ListUserMemoryRequest,
  ): Promise<MemoryRecord[]> {
    const response = await apiClient.get<MemoryRecord[]>(
      "/user-memory/profile",
      {
        params,
      },
    );
    return response.data.map(normalizeUserMemoryRecord);
  },

  async deleteUserMemory(
    memoryId: string,
    memorySource: "entry" | "user_memory_view",
  ): Promise<void> {
    await apiClient.delete(`/user-memory/${memoryId}`, {
      params: { memory_source: memorySource },
    });
  },

  async getConfig(): Promise<MemoryConfig> {
    const response = await apiClient.get<MemoryConfig>("/user-memory/config");
    return response.data;
  },

  async updateConfig(data: UpdateMemoryConfigRequest): Promise<MemoryConfig> {
    const response = await apiClient.put<MemoryConfig>(
      "/user-memory/config",
      data,
    );
    return response.data;
  },

  async listUsers(): Promise<
    { user_id: string; username: string; display_name?: string }[]
  > {
    const response = await apiClient.get<{
      users: { user_id: string; username: string; display_name?: string }[];
    }>("/admin/users", { params: { page_size: 100 } });
    return response.data.users || [];
  },
};
