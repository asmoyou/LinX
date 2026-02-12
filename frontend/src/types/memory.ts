export type MemoryType = "agent" | "company" | "user_context";

export type Memory = {
  id: string;
  type: MemoryType;
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
  metadata?: {
    taskId?: string;
    goalId?: string;
    documentId?: string;
    [key: string]: unknown;
  };
  isShared?: boolean;
  sharedWith?: string[];
  sharedWithNames?: string[];
};

export type MemoryFilter = {
  type?: MemoryType;
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
  embedding: MemoryConfigEmbedding;
  retrieval: MemoryConfigRetrieval;
  runtime: MemoryConfigRuntime;
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
  top_k?: number;
  similarity_threshold?: number;
  similarity_weight?: number;
  recency_weight?: number;
  enable_reranking?: boolean;
  rerank_provider?: string;
  rerank_model?: string;
  rerank_top_k?: number;
  rerank_weight?: number;
  rerank_timeout_seconds?: number;
  rerank_failure_backoff_seconds?: number;
  rerank_doc_max_chars?: number;
  milvus?: {
    metric_type?: string;
    nprobe?: number;
  };
  sources?: {
    rerank_provider?: string;
    rerank_model?: string;
  };
  [key: string]: unknown;
};

export type MemoryConfigRuntime = {
  collection_retry_attempts?: number;
  collection_retry_delay_seconds?: number;
  search_timeout_seconds?: number;
  delete_timeout_seconds?: number;
  [key: string]: unknown;
};

export type MemoryConfigRecommended = {
  embedding?: Partial<MemoryConfigEmbedding>;
  retrieval?: Partial<MemoryConfigRetrieval>;
  runtime?: Partial<MemoryConfigRuntime>;
  [key: string]: unknown;
};
