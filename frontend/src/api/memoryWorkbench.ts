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
  minScore?: number;
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
  ): Promise<MemoryRecord[]> {
    const response = await apiClient.get<MemoryRecord[]>("/user-memory", {
      params,
    });
    return response.data.map(normalizeUserMemoryRecord);
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
};
