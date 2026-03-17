import apiClient from "./client";
import type {
  MemoryRecord,
  MemorySurfaceType,
  MemoryConfig,
  MemoryConfigEmbedding,
  MemoryConfigFactExtraction,
  MemoryConfigRetrieval,
  MemoryConfigRuntimeContext,
  MemoryConfigSessionLedger,
  MemoryConfigConsolidation,
  SkillLearningExtractionConfig,
  SkillLearningPublishPolicyConfig,
} from "../types/memory";

export interface ListUserMemoryRequest {
  query?: string;
  user_id?: string;
  limit?: number;
  minScore?: number;
}

export interface ListSkillProposalsRequest {
  agent_id?: string;
  review_status?: "pending" | "published" | "rejected" | "all";
  limit?: number;
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
  skill_learning?: {
    extraction?: Partial<
      Omit<SkillLearningExtractionConfig, "effective" | "sources">
    >;
    publish_policy?: Partial<SkillLearningPublishPolicyConfig>;
  };
  session_ledger?: Partial<MemoryConfigSessionLedger>;
  runtime_context?: Partial<MemoryConfigRuntimeContext>;
}

export interface AgentCandidateReviewRequest {
  action: "publish" | "reject" | "revise";
  content?: string;
  summary?: string;
  note?: string;
  metadata?: Record<string, unknown>;
}

const normalizeWorkbenchRecord = (
  record: MemoryRecord,
  surfaceType: MemorySurfaceType,
): MemoryRecord => ({
  ...record,
  type: surfaceType,
  metadata: {
    ...(record.metadata || {}),
    record_type: record.type,
  },
});

/**
 * Memory System API
 */
export const memoryWorkbenchApi = {
  listUserMemory: async (params?: ListUserMemoryRequest): Promise<MemoryRecord[]> => {
    const response = await apiClient.get<MemoryRecord[]>("/user-memory", {
      params,
    });
    return response.data.map((item) => normalizeWorkbenchRecord(item, "user_memory"));
  },

  listUserMemoryProfile: async (
    params?: ListUserMemoryRequest,
  ): Promise<MemoryRecord[]> => {
    const response = await apiClient.get<MemoryRecord[]>("/user-memory/profile", {
      params,
    });
    return response.data.map((item) => normalizeWorkbenchRecord(item, "user_memory"));
  },

  listSkillProposals: async (
    params?: ListSkillProposalsRequest,
  ): Promise<MemoryRecord[]> => {
    const response = await apiClient.get<MemoryRecord[]>("/skill-proposals", {
      params,
    });
    return response.data.map((item) =>
      normalizeWorkbenchRecord(item, "skill_proposal"),
    );
  },

  reviewSkillProposal: async (
    memoryId: string,
    data: AgentCandidateReviewRequest,
  ): Promise<MemoryRecord> => {
    const response = await apiClient.post<MemoryRecord>(
      `/skill-proposals/${memoryId}/review`,
      data,
    );
    return normalizeWorkbenchRecord(response.data, "skill_proposal");
  },

  deleteUserMemory: async (
    memoryId: string,
    memorySource: "entry" | "user_memory_view",
  ): Promise<void> => {
    await apiClient.delete(`/user-memory/${memoryId}`, {
      params: { memory_source: memorySource },
    });
  },

  deleteSkillProposal: async (
    memoryId: string,
    deletePublishedSkill = true,
  ): Promise<void> => {
    await apiClient.delete(`/skill-proposals/${memoryId}`, {
      params: { delete_published_skill: deletePublishedSkill },
    });
  },

  /**
   * Get memory retrieval configuration
   */
  getConfig: async (): Promise<MemoryConfig> => {
    const response = await apiClient.get<MemoryConfig>("/user-memory/config");
    return response.data;
  },

  /**
   * Update memory retrieval configuration (admin only)
   */
  updateConfig: async (
    data: UpdateMemoryConfigRequest,
  ): Promise<MemoryConfig> => {
    const response = await apiClient.put<MemoryConfig>("/user-memory/config", data);
    return response.data;
  },
};
