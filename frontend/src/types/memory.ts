export type MemorySurfaceType = "user_memory" | "skill_proposal";

export type MemoryFact = {
  key: string;
  value: string;
  category?: string;
  confidence?: number;
  importance?: number;
  source?: string;
};

export type MemoryMetadata = {
  taskId?: string;
  task_id?: string;
  goalId?: string;
  goal_id?: string;
  documentId?: string;
  document_id?: string;
  facts?: MemoryFact[];
  fact_keys?: string[];
  memory_tier?: string;
  importance_level?: string;
  importance_score?: number;
  auto_generated?: boolean;
  owner_user_id?: string;
  owner_agent_id?: string;
  department_id?: string;
  visibility?:
    | "explicit"
    | "department"
    | "department_tree"
    | "account"
    | "private"
    | "public"
    | string;
  sensitivity?: string;
  source_memory_id?: number;
  last_promoted_memory_id?: number;
  expires_at?: string;
  share_reason?: string;
  publish_mode?: string;
  shared_updated_at?: string;
  [key: string]: unknown;
};

export type MemoryRecord = {
  id: string;
  type: MemorySurfaceType;
  content: string;
  summary?: string;
  agentId?: string;
  agentName?: string;
  userId?: string;
  userName?: string;
  createdAt: string;
  updatedAt?: string;
  tags: string[];
  relevanceScore?: number;
  indexStatus?: "pending" | "synced" | "failed" | string;
  indexError?: string;
  metadata?: MemoryMetadata;
  isShared?: boolean;
  sharedWith?: string[];
  sharedWithNames?: string[];
};

export type MemoryRecordFilter = {
  type?: MemorySurfaceType;
  dateFrom?: string;
  dateTo?: string;
  tags?: string[];
  agentId?: string;
  userId?: string;
};

export type MemoryIndexInfo = {
  memoryId: string;
  milvusId?: number;
  collection?: string;
  vectorStatus?: string;
  vectorError?: string;
  vectorUpdatedAt?: string;
  existsInMilvus: boolean;
  indexedContent?: string;
  indexedTimestamp?: string;
  indexedMetadata?: Record<string, unknown> | null;
  embeddingDimension?: number;
  embeddingPreview?: number[] | null;
  milvusError?: string;
};

export type MemoryConfig = {
  user_memory: MemoryConfigUserMemory;
  skill_learning: MemoryConfigSkillLearning;
  session_ledger?: MemoryConfigSessionLedger;
  runtime_context: MemoryConfigRuntimeContext;
  recommended?: MemoryConfigRecommended;
};

export type MemoryConfigEmbedding = {
  provider?: string;
  model?: string;
  dimension?: number;
  inherit_from_knowledge_base?: boolean;
  effective?: {
    provider?: string;
    model?: string;
    dimension?: number;
  };
  sources?: {
    provider?: string;
    model?: string;
    dimension?: string;
  };
  [key: string]: unknown;
};

export type MemoryConfigRetrieval = {
  similarity_threshold?: number;
  [key: string]: unknown;
};

export type MemoryConfigRuntimeContext = {
  enable_user_memory?: boolean;
  enable_skills?: boolean;
  enable_knowledge_base?: boolean;
  [key: string]: unknown;
};

export type MemoryConfigFactExtraction = {
  provider?: string;
  model?: string;
  timeout_seconds?: number;
  max_facts?: number;
  max_preference_facts?: number;
  max_proposals?: number;
  enable_heuristic_fallback?: boolean;
  secondary_recall_enabled?: boolean;
  failure_backoff_seconds?: number;
  fail_closed_empty_writes?: boolean;
  effective?: {
    provider?: string;
    model?: string;
  };
  sources?: {
    provider?: string;
    model?: string;
  };
  [key: string]: unknown;
};

export type SkillLearningExtractionConfig = {
  enabled?: boolean;
  provider?: string;
  model?: string;
  timeout_seconds?: number;
  max_proposals?: number;
  failure_backoff_seconds?: number;
  effective?: {
    provider?: string;
    model?: string;
  };
  sources?: {
    provider?: string;
    model?: string;
  };
  [key: string]: unknown;
};

export type MemoryConfigSessionLedger = {
  enabled?: boolean;
  retention_days?: number;
  run_on_startup?: boolean;
  startup_delay_seconds?: number;
  cleanup_interval_seconds?: number;
  batch_size?: number;
  dry_run?: boolean;
  use_advisory_lock?: boolean;
  [key: string]: unknown;
};

export type MemoryConfigConsolidation = {
  enabled?: boolean;
  run_on_startup?: boolean;
  startup_delay_seconds?: number;
  interval_seconds?: number;
  dry_run?: boolean;
  limit?: number;
  use_advisory_lock?: boolean;
  [key: string]: unknown;
};

export type MemoryConfigObservability = {
  enable_quality_counters?: boolean;
  [key: string]: unknown;
};

export type SkillLearningPublishPolicyConfig = {
  skill_type?: string;
  storage_type?: string;
  reuse_existing_by_name?: boolean;
  [key: string]: unknown;
};

export type MemoryConfigUserMemory = {
  embedding: MemoryConfigEmbedding;
  retrieval: MemoryConfigRetrieval;
  extraction: MemoryConfigFactExtraction;
  consolidation?: MemoryConfigConsolidation;
  observability?: MemoryConfigObservability;
};

export type MemoryConfigSkillLearning = {
  extraction: SkillLearningExtractionConfig;
  publish_policy?: SkillLearningPublishPolicyConfig;
};

export type MemoryConfigRecommended = {
  user_memory?: Partial<MemoryConfigUserMemory>;
  skill_learning?: Partial<MemoryConfigSkillLearning>;
  session_ledger?: Partial<MemoryConfigSessionLedger>;
  runtime_context?: Partial<MemoryConfigRuntimeContext>;
  [key: string]: unknown;
};
