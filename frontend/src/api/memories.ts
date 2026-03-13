import apiClient from "./client";
import type {
  Memory,
  MemoryProductType,
  MemoryConfig,
  MemoryConfigEmbedding,
  MemoryConfigFactExtraction,
  MemoryConfigRetrieval,
  MemoryConfigRuntimeContext,
  MemoryConfigSessionLedger,
  MemoryConfigConsolidation,
  MemoryConfigObservability,
  MemoryConfigRetention,
  SkillLearningExtractionConfig,
  SkillLearningProposalReviewConfig,
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
    retention?: Partial<MemoryConfigRetention>;
    embedding?: Partial<Omit<MemoryConfigEmbedding, "effective" | "sources">>;
    retrieval?: Partial<Omit<MemoryConfigRetrieval, "sources">>;
    extraction?: Partial<
      Omit<MemoryConfigFactExtraction, "effective" | "sources">
    >;
    consolidation?: Partial<MemoryConfigConsolidation>;
    observability?: Partial<MemoryConfigObservability>;
  };
  skill_learning?: {
    retention?: Partial<MemoryConfigRetention>;
    extraction?: Partial<
      Omit<SkillLearningExtractionConfig, "effective" | "sources">
    >;
    proposal_review?: Partial<SkillLearningProposalReviewConfig>;
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

const normalizeProductMemory = (
  memory: Memory,
  productType: MemoryProductType,
): Memory => ({
  ...memory,
  type: productType,
  metadata: {
    ...(memory.metadata || {}),
    record_type: memory.type,
  },
});

/**
 * Memory System API
 */
export const memoriesApi = {
  listUserMemory: async (params?: ListUserMemoryRequest): Promise<Memory[]> => {
    const response = await apiClient.get<Memory[]>("/user-memory", {
      params,
    });
    return response.data.map((item) => normalizeProductMemory(item, "user_memory"));
  },

  listUserMemoryProfile: async (
    params?: ListUserMemoryRequest,
  ): Promise<Memory[]> => {
    const response = await apiClient.get<Memory[]>("/user-memory/profile", {
      params,
    });
    return response.data.map((item) => normalizeProductMemory(item, "user_memory"));
  },

  listSkillProposals: async (
    params?: ListSkillProposalsRequest,
  ): Promise<Memory[]> => {
    const response = await apiClient.get<Memory[]>("/skill-proposals", {
      params,
    });
    return response.data.map((item) =>
      normalizeProductMemory(item, "skill_proposal"),
    );
  },

  listSkillExperiences: async (params: {
    agent_id: string;
    query?: string;
    limit?: number;
    minScore?: number;
  }): Promise<Memory[]> => {
    const response = await apiClient.get<Memory[]>("/skill-proposals/experiences", {
      params,
    });
    return response.data.map((item) =>
      normalizeProductMemory(item, "skill_proposal"),
    );
  },

  reviewSkillProposal: async (
    memoryId: string,
    data: AgentCandidateReviewRequest,
  ): Promise<Memory> => {
    const response = await apiClient.post<Memory>(
      `/skill-proposals/${memoryId}/review`,
      data,
    );
    return normalizeProductMemory(response.data, "skill_proposal");
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
