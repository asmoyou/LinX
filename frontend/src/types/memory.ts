export type MemorySurfaceType = "user_memory";

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
  skill_candidates?: MemoryConfigSkillCandidates;
  skill_runtime?: MemoryConfigSkillRuntime;
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
  hybrid_enabled?: boolean;
  similarity_threshold?: number;
  vector?: {
    candidate_top_k?: number;
    collection_prefix?: string;
    metric_type?: string;
    nprobe?: number;
    [key: string]: unknown;
  };
  lexical?: {
    enabled?: boolean;
    top_k?: number;
    fts_enabled?: boolean;
    trigram_enabled?: boolean;
    [key: string]: unknown;
  };
  structured?: {
    enabled?: boolean;
    top_k?: number;
    [key: string]: unknown;
  };
  fusion?: {
    method?: string;
    rrf_k?: number;
    [key: string]: unknown;
  };
  rerank?: {
    enabled?: boolean;
    provider?: string;
    model?: string;
    top_k?: number;
    weight?: number;
    timeout_seconds?: number;
    failure_backoff_seconds?: number;
    doc_max_chars?: number;
    [key: string]: unknown;
  };
  planner?: {
    runtime_mode?: string;
    api_mode?: string;
    provider?: string;
    model?: string;
    timeout_seconds?: number;
    failure_backoff_seconds?: number;
    max_query_variants?: number;
    [key: string]: unknown;
  };
  reflection?: {
    enabled_api?: boolean;
    max_rounds?: number;
    min_results?: number;
    min_score?: number;
    [key: string]: unknown;
  };
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

export type SkillCandidatesExtractionConfig = {
  enabled?: boolean;
  provider?: string;
  model?: string;
  timeout_seconds?: number;
  max_candidates?: number;
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

export type MemoryConfigSkillCandidates = {
  extraction: SkillCandidatesExtractionConfig;
};

export type MemoryConfigSkillRuntime = {
  retrieval?: {
    enabled?: boolean;
    top_k?: number;
    min_similarity?: number;
    [key: string]: unknown;
  };
  auto_bind_source_agent?: boolean;
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

export type MemoryConfigUserMemory = {
  embedding: MemoryConfigEmbedding;
  retrieval: MemoryConfigRetrieval;
  extraction: MemoryConfigFactExtraction;
  consolidation?: MemoryConfigConsolidation;
  observability?: MemoryConfigObservability;
};

export type MemoryConfigRecommended = {
  user_memory?: Partial<MemoryConfigUserMemory>;
  skill_candidates?: Partial<MemoryConfigSkillCandidates>;
  skill_runtime?: Partial<MemoryConfigSkillRuntime>;
  session_ledger?: Partial<MemoryConfigSessionLedger>;
  runtime_context?: Partial<MemoryConfigRuntimeContext>;
  [key: string]: unknown;
};
