import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  X,
  Save,
  Loader2,
  Settings2,
  Sparkles,
  SlidersHorizontal,
} from "lucide-react";
import toast from "react-hot-toast";
import { LayoutModal } from "@/components/LayoutModal";
import { ModalPanel } from "@/components/ModalPanel";
import { llmApi } from "@/api/llm";
import { memoriesApi } from "@/api/memories";
import type { UpdateMemoryConfigRequest } from "@/api/memories";
import type { ModelMetadata } from "@/api/llm";
import type { MemoryConfig } from "@/types/memory";

interface MemoryConfigPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onSaved?: (config: MemoryConfig) => void;
}

type MemoryConfigFormState = {
  embedding: {
    provider: string;
    model: string;
    dimension: number;
    inherit_from_knowledge_base: boolean;
  };
  retrieval: {
    top_k: number;
    similarity_threshold: number;
    similarity_weight: number;
    recency_weight: number;
    strict_keyword_fallback: boolean;
    enable_reranking: boolean;
    rerank_provider: string;
    rerank_model: string;
    rerank_top_k: number;
    rerank_weight: number;
    rerank_timeout_seconds: number;
    rerank_failure_backoff_seconds: number;
    rerank_doc_max_chars: number;
    milvus_metric_type: string;
    milvus_nprobe: number;
  };
  fact_extraction: {
    enabled: boolean;
    model_enabled: boolean;
    provider: string;
    model: string;
    timeout_seconds: number;
    max_facts: number;
    max_preference_facts: number;
    max_agent_candidates: number;
    enable_heuristic_fallback: boolean;
    secondary_recall_enabled: boolean;
    failure_backoff_seconds: number;
  };
  skill_learning: {
    enabled: boolean;
    provider: string;
    model: string;
    timeout_seconds: number;
    max_proposals: number;
    failure_backoff_seconds: number;
    require_human_review: boolean;
    allow_revise: boolean;
    default_review_status: string;
    publish_enabled: boolean;
    publish_skill_type: string;
    publish_storage_type: string;
    reuse_existing_by_name: boolean;
  };
  session_ledger: {
    enabled: boolean;
    retention_days: number;
    run_on_startup: boolean;
    startup_delay_seconds: number;
    cleanup_interval_seconds: number;
    batch_size: number;
    dry_run: boolean;
  };
  maintenance: {
    materialization: {
      enabled: boolean;
      run_on_startup: boolean;
      startup_delay_seconds: number;
      interval_seconds: number;
      limit: number;
      dry_run: boolean;
    };
  };
  runtime: {
    enable_user_memory: boolean;
    enable_skills: boolean;
    enable_knowledge_base: boolean;
    collection_retry_attempts: number;
    collection_retry_delay_seconds: number;
    search_timeout_seconds: number;
    delete_timeout_seconds: number;
  };
};

const DEFAULT_FORM_STATE: MemoryConfigFormState = {
  embedding: {
    provider: "",
    model: "",
    dimension: 1024,
    inherit_from_knowledge_base: true,
  },
  retrieval: {
    top_k: 10,
    similarity_threshold: 0.3,
    similarity_weight: 0.7,
    recency_weight: 0.3,
    strict_keyword_fallback: true,
    enable_reranking: true,
    rerank_provider: "",
    rerank_model: "",
    rerank_top_k: 30,
    rerank_weight: 0.75,
    rerank_timeout_seconds: 8,
    rerank_failure_backoff_seconds: 30,
    rerank_doc_max_chars: 1200,
    milvus_metric_type: "L2",
    milvus_nprobe: 10,
  },
  fact_extraction: {
    enabled: true,
    model_enabled: true,
    provider: "",
    model: "",
    timeout_seconds: 120,
    max_facts: 10,
    max_preference_facts: 10,
    max_agent_candidates: 6,
    enable_heuristic_fallback: true,
    secondary_recall_enabled: true,
    failure_backoff_seconds: 60,
  },
  skill_learning: {
    enabled: true,
    provider: "",
    model: "",
    timeout_seconds: 120,
    max_proposals: 6,
    failure_backoff_seconds: 60,
    require_human_review: true,
    allow_revise: true,
    default_review_status: "pending",
    publish_enabled: true,
    publish_skill_type: "agent_skill",
    publish_storage_type: "inline",
    reuse_existing_by_name: true,
  },
  session_ledger: {
    enabled: true,
    retention_days: 14,
    run_on_startup: true,
    startup_delay_seconds: 120,
    cleanup_interval_seconds: 21600,
    batch_size: 1000,
    dry_run: false,
  },
  maintenance: {
    materialization: {
      enabled: true,
      run_on_startup: true,
      startup_delay_seconds: 180,
      interval_seconds: 21600,
      limit: 5000,
      dry_run: false,
    },
  },
  runtime: {
    enable_user_memory: true,
    enable_skills: true,
    enable_knowledge_base: true,
    collection_retry_attempts: 3,
    collection_retry_delay_seconds: 0.35,
    search_timeout_seconds: 2,
    delete_timeout_seconds: 2,
  },
};

const METRIC_TYPE_OPTIONS = ["L2", "COSINE", "IP"] as const;
const EMBEDDING_MODEL_NAME_PATTERN =
  /embed|embedding|bge|m3e|e5|gte|voyage|jina-embeddings/i;
const RERANK_MODEL_NAME_PATTERN =
  /rerank|reranker|bge-reranker|jina-reranker|gte-rerank|cohere-rerank|bce-reranker/i;
const CHAT_MODEL_NAME_PATTERN = /chat|instruct|gpt|qwen|llama|claude|deepseek/i;

type ModelType = "embedding" | "rerank" | "generation";
type ProviderTypedModels = {
  embedding: string[];
  rerank: string[];
  generation: string[];
};

const asObject = (value: unknown): Record<string, unknown> => {
  if (value && typeof value === "object") {
    return value as Record<string, unknown>;
  }
  return {};
};

const asString = (value: unknown, fallback = ""): string => {
  if (typeof value === "string") {
    return value;
  }
  return fallback;
};

const asNumber = (value: unknown, fallback: number): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const asBoolean = (value: unknown, fallback: boolean): boolean => {
  if (typeof value === "boolean") {
    return value;
  }
  return fallback;
};

const clamp01 = (value: number): number => Math.max(0, Math.min(1, value));

const dedupeModels = (models: string[]): string[] => {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const model of models) {
    const normalized = model.trim();
    if (!normalized || seen.has(normalized)) {
      continue;
    }
    seen.add(normalized);
    result.push(normalized);
  }
  return result;
};

const selectModelsByType = (
  providerModels: string[],
  metadataModels: Record<string, ModelMetadata>,
  modelType: ModelType,
): string[] => {
  const generationExcludedTypes = new Set([
    "embedding",
    "rerank",
    "image_generation",
  ]);
  const metadataMatches = Object.entries(metadataModels)
    .filter(([, metadata]) => {
      const normalized = metadata.model_type?.toLowerCase();
      if (modelType === "generation") {
        return normalized ? !generationExcludedTypes.has(normalized) : true;
      }
      return normalized === modelType;
    })
    .map(([modelName]) => modelName);

  if (metadataMatches.length > 0) {
    const ordered = providerModels.filter((model) =>
      metadataMatches.includes(model),
    );
    const extra = metadataMatches.filter((model) => !ordered.includes(model));
    return dedupeModels([...ordered, ...extra]);
  }

  const matcher =
    modelType === "embedding"
      ? EMBEDDING_MODEL_NAME_PATTERN
      : modelType === "rerank"
        ? RERANK_MODEL_NAME_PATTERN
        : CHAT_MODEL_NAME_PATTERN;
  const heuristicMatches = providerModels.filter((model) =>
    matcher.test(model),
  );
  if (heuristicMatches.length > 0) {
    return dedupeModels(heuristicMatches);
  }

  return dedupeModels(providerModels);
};

const toFormState = (config: MemoryConfig | null): MemoryConfigFormState => {
  if (!config) {
    return {
      embedding: { ...DEFAULT_FORM_STATE.embedding },
      retrieval: { ...DEFAULT_FORM_STATE.retrieval },
      fact_extraction: { ...DEFAULT_FORM_STATE.fact_extraction },
      skill_learning: { ...DEFAULT_FORM_STATE.skill_learning },
      session_ledger: { ...DEFAULT_FORM_STATE.session_ledger },
      maintenance: {
        materialization: { ...DEFAULT_FORM_STATE.maintenance.materialization },
      },
      runtime: { ...DEFAULT_FORM_STATE.runtime },
    };
  }

  const userMemory = asObject(config.user_memory);
  const skillLearning = asObject(config.skill_learning);
  const userMemoryEmbedding = asObject(userMemory.embedding);
  const userMemoryRetrieval = asObject(userMemory.retrieval);
  const userMemoryExtraction = asObject(userMemory.extraction);
  const userMemoryConsolidation = asObject(userMemory.consolidation);
  const skillLearningExtraction = asObject(skillLearning.extraction);
  const skillLearningReview = asObject(skillLearning.proposal_review);
  const skillLearningPublish = asObject(skillLearning.publish_policy);
  const retrievalMilvus = asObject(userMemoryRetrieval.milvus);
  const sessionLedger = asObject(config.session_ledger);
  const runtime = asObject(config.runtime_context);

  return {
    embedding: {
      provider: asString(userMemoryEmbedding.provider, ""),
      model: asString(userMemoryEmbedding.model, ""),
      dimension: asNumber(userMemoryEmbedding.dimension, 1024),
      inherit_from_knowledge_base: asBoolean(
        userMemoryEmbedding.inherit_from_knowledge_base,
        true,
      ),
    },
    retrieval: {
      top_k: asNumber(userMemoryRetrieval.top_k, 10),
      similarity_threshold: asNumber(userMemoryRetrieval.similarity_threshold, 0.3),
      similarity_weight: asNumber(userMemoryRetrieval.similarity_weight, 0.7),
      recency_weight: asNumber(userMemoryRetrieval.recency_weight, 0.3),
      strict_keyword_fallback: asBoolean(
        userMemoryRetrieval.strict_keyword_fallback,
        true,
      ),
      enable_reranking: asBoolean(userMemoryRetrieval.enable_reranking, true),
      rerank_provider: asString(userMemoryRetrieval.rerank_provider, ""),
      rerank_model: asString(userMemoryRetrieval.rerank_model, ""),
      rerank_top_k: asNumber(userMemoryRetrieval.rerank_top_k, 30),
      rerank_weight: asNumber(userMemoryRetrieval.rerank_weight, 0.75),
      rerank_timeout_seconds: asNumber(userMemoryRetrieval.rerank_timeout_seconds, 8),
      rerank_failure_backoff_seconds: asNumber(
        userMemoryRetrieval.rerank_failure_backoff_seconds,
        30,
      ),
      rerank_doc_max_chars: asNumber(userMemoryRetrieval.rerank_doc_max_chars, 1200),
      milvus_metric_type: asString(retrievalMilvus.metric_type, "L2"),
      milvus_nprobe: asNumber(retrievalMilvus.nprobe, 10),
    },
    fact_extraction: {
      enabled: asBoolean(userMemoryExtraction.enabled, true),
      model_enabled: asBoolean(userMemoryExtraction.model_enabled, true),
      provider: asString(userMemoryExtraction.provider, ""),
      model: asString(userMemoryExtraction.model, ""),
      timeout_seconds: asNumber(userMemoryExtraction.timeout_seconds, 120),
      max_facts: asNumber(userMemoryExtraction.max_facts, 10),
      max_preference_facts: asNumber(
        userMemoryExtraction.max_preference_facts,
        asNumber(userMemoryExtraction.max_facts, 10),
      ),
      max_agent_candidates: asNumber(skillLearningExtraction.max_proposals, 6),
      enable_heuristic_fallback: asBoolean(
        userMemoryExtraction.enable_heuristic_fallback,
        true,
      ),
      secondary_recall_enabled: asBoolean(
        userMemoryExtraction.secondary_recall_enabled,
        true,
      ),
      failure_backoff_seconds: asNumber(
        userMemoryExtraction.failure_backoff_seconds,
        60,
      ),
    },
    skill_learning: {
      enabled: asBoolean(skillLearningExtraction.enabled, true),
      provider: asString(skillLearningExtraction.provider, ""),
      model: asString(skillLearningExtraction.model, ""),
      timeout_seconds: asNumber(skillLearningExtraction.timeout_seconds, 120),
      max_proposals: asNumber(skillLearningExtraction.max_proposals, 6),
      failure_backoff_seconds: asNumber(
        skillLearningExtraction.failure_backoff_seconds,
        60,
      ),
      require_human_review: asBoolean(skillLearningReview.require_human_review, true),
      allow_revise: asBoolean(skillLearningReview.allow_revise, true),
      default_review_status: asString(
        skillLearningReview.default_review_status,
        "pending",
      ),
      publish_enabled: asBoolean(skillLearningPublish.enabled, true),
      publish_skill_type: asString(skillLearningPublish.skill_type, "agent_skill"),
      publish_storage_type: asString(skillLearningPublish.storage_type, "inline"),
      reuse_existing_by_name: asBoolean(
        skillLearningPublish.reuse_existing_by_name,
        true,
      ),
    },
    session_ledger: {
      enabled: asBoolean(sessionLedger.enabled, true),
      retention_days: asNumber(sessionLedger.retention_days, 14),
      run_on_startup: asBoolean(sessionLedger.run_on_startup, true),
      startup_delay_seconds: asNumber(sessionLedger.startup_delay_seconds, 120),
      cleanup_interval_seconds: asNumber(
        sessionLedger.cleanup_interval_seconds,
        21600,
      ),
      batch_size: asNumber(sessionLedger.batch_size, 1000),
      dry_run: asBoolean(sessionLedger.dry_run, false),
    },
    maintenance: {
      materialization: {
        enabled: asBoolean(userMemoryConsolidation.enabled, true),
        run_on_startup: asBoolean(userMemoryConsolidation.run_on_startup, true),
        startup_delay_seconds: asNumber(
          userMemoryConsolidation.startup_delay_seconds,
          180,
        ),
        interval_seconds: asNumber(userMemoryConsolidation.interval_seconds, 21600),
        limit: asNumber(userMemoryConsolidation.limit, 5000),
        dry_run: asBoolean(userMemoryConsolidation.dry_run, false),
      },
    },
    runtime: {
      enable_user_memory: asBoolean(runtime.enable_user_memory, true),
      enable_skills: asBoolean(runtime.enable_skills, true),
      enable_knowledge_base: asBoolean(runtime.enable_knowledge_base, true),
      collection_retry_attempts: asNumber(runtime.collection_retry_attempts, 3),
      collection_retry_delay_seconds: asNumber(
        runtime.collection_retry_delay_seconds,
        0.35,
      ),
      search_timeout_seconds: asNumber(runtime.search_timeout_seconds, 2),
      delete_timeout_seconds: asNumber(runtime.delete_timeout_seconds, 2),
    },
  };
};

const toUpdatePayload = (
  formState: MemoryConfigFormState,
): UpdateMemoryConfigRequest => {
  return {
    user_memory: {
      embedding: {
        provider: formState.embedding.provider.trim(),
        model: formState.embedding.model.trim(),
        dimension: Math.max(1, Math.floor(formState.embedding.dimension)),
        inherit_from_knowledge_base:
          formState.embedding.inherit_from_knowledge_base,
      },
      retrieval: {
        top_k: Math.max(1, Math.floor(formState.retrieval.top_k)),
        similarity_threshold: Math.max(
          0,
          formState.retrieval.similarity_threshold,
        ),
        similarity_weight: clamp01(formState.retrieval.similarity_weight),
        recency_weight: clamp01(formState.retrieval.recency_weight),
        strict_keyword_fallback: formState.retrieval.strict_keyword_fallback,
        enable_reranking: formState.retrieval.enable_reranking,
        rerank_provider: formState.retrieval.rerank_provider.trim(),
        rerank_model: formState.retrieval.rerank_model.trim(),
        rerank_top_k: Math.max(1, Math.floor(formState.retrieval.rerank_top_k)),
        rerank_weight: clamp01(formState.retrieval.rerank_weight),
        rerank_timeout_seconds: Math.max(
          1,
          formState.retrieval.rerank_timeout_seconds,
        ),
        rerank_failure_backoff_seconds: Math.max(
          1,
          formState.retrieval.rerank_failure_backoff_seconds,
        ),
        rerank_doc_max_chars: Math.max(
          128,
          Math.floor(formState.retrieval.rerank_doc_max_chars),
        ),
        milvus: {
          metric_type: formState.retrieval.milvus_metric_type.trim() || "L2",
          nprobe: Math.max(1, Math.floor(formState.retrieval.milvus_nprobe)),
        },
      },
      extraction: {
        enabled: formState.fact_extraction.enabled,
        model_enabled: formState.fact_extraction.model_enabled,
        provider: formState.fact_extraction.provider.trim(),
        model: formState.fact_extraction.model.trim(),
        timeout_seconds: Math.max(0.5, formState.fact_extraction.timeout_seconds),
        max_facts: Math.max(1, Math.floor(formState.fact_extraction.max_facts)),
        max_preference_facts: Math.max(
          1,
          Math.floor(formState.fact_extraction.max_preference_facts),
        ),
        enable_heuristic_fallback:
          formState.fact_extraction.enable_heuristic_fallback,
        secondary_recall_enabled:
          formState.fact_extraction.secondary_recall_enabled,
        failure_backoff_seconds: Math.max(
          1,
          formState.fact_extraction.failure_backoff_seconds,
        ),
      },
      consolidation: {
        enabled: formState.maintenance.materialization.enabled,
        run_on_startup: formState.maintenance.materialization.run_on_startup,
        startup_delay_seconds: Math.max(
          0,
          Math.floor(
            formState.maintenance.materialization.startup_delay_seconds,
          ),
        ),
        interval_seconds: Math.max(
          60,
          Math.floor(formState.maintenance.materialization.interval_seconds),
        ),
        limit: Math.max(
          1,
          Math.floor(formState.maintenance.materialization.limit),
        ),
        dry_run: formState.maintenance.materialization.dry_run,
      },
    },
    skill_learning: {
      extraction: {
        enabled: formState.skill_learning.enabled,
        provider: formState.skill_learning.provider.trim(),
        model: formState.skill_learning.model.trim(),
        timeout_seconds: Math.max(0.5, formState.skill_learning.timeout_seconds),
        max_proposals: Math.max(1, Math.floor(formState.skill_learning.max_proposals)),
        failure_backoff_seconds: Math.max(
          1,
          Math.floor(formState.skill_learning.failure_backoff_seconds),
        ),
      },
      proposal_review: {
        require_human_review: formState.skill_learning.require_human_review,
        allow_revise: formState.skill_learning.allow_revise,
        default_review_status:
          formState.skill_learning.default_review_status.trim() || "pending",
      },
      publish_policy: {
        enabled: formState.skill_learning.publish_enabled,
        skill_type: formState.skill_learning.publish_skill_type.trim() || "agent_skill",
        storage_type: formState.skill_learning.publish_storage_type.trim() || "inline",
        reuse_existing_by_name: formState.skill_learning.reuse_existing_by_name,
      },
    },
    session_ledger: {
      enabled: formState.session_ledger.enabled,
      retention_days: Math.max(
        1,
        Math.floor(formState.session_ledger.retention_days),
      ),
      run_on_startup: formState.session_ledger.run_on_startup,
      startup_delay_seconds: Math.max(
        0,
        Math.floor(formState.session_ledger.startup_delay_seconds),
      ),
      cleanup_interval_seconds: Math.max(
        60,
        Math.floor(formState.session_ledger.cleanup_interval_seconds),
      ),
      batch_size: Math.max(1, Math.floor(formState.session_ledger.batch_size)),
      dry_run: formState.session_ledger.dry_run,
    },
    runtime_context: {
      enable_user_memory: formState.runtime.enable_user_memory,
      enable_skills: formState.runtime.enable_skills,
      enable_knowledge_base: formState.runtime.enable_knowledge_base,
      collection_retry_attempts: Math.max(
        1,
        Math.floor(formState.runtime.collection_retry_attempts),
      ),
      collection_retry_delay_seconds: Math.max(
        0,
        formState.runtime.collection_retry_delay_seconds,
      ),
      search_timeout_seconds: Math.max(
        0.1,
        formState.runtime.search_timeout_seconds,
      ),
      delete_timeout_seconds: Math.max(
        0.1,
        formState.runtime.delete_timeout_seconds,
      ),
    },
  };
};

const getErrorDetail = (error: unknown): string | null => {
  if (!error || typeof error !== "object") {
    return null;
  }
  const detail = (error as { response?: { data?: { detail?: unknown } } })
    .response?.data?.detail;
  return typeof detail === "string" && detail.trim() ? detail : null;
};

export const MemoryConfigPanel: React.FC<MemoryConfigPanelProps> = ({
  isOpen,
  onClose,
  onSaved,
}) => {
  const { t } = useTranslation();
  const [config, setConfig] = useState<MemoryConfig | null>(null);
  const [formState, setFormState] =
    useState<MemoryConfigFormState>(DEFAULT_FORM_STATE);
  const [availableProviders, setAvailableProviders] = useState<
    Record<string, string[]>
  >({});
  const [typedModelsByProvider, setTypedModelsByProvider] = useState<
    Record<string, ProviderTypedModels>
  >({});
  const [loadingModelMetadataByProvider, setLoadingModelMetadataByProvider] =
    useState<Record<string, boolean>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isLoadingProviders, setIsLoadingProviders] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    setShowAdvanced(false);
    setTypedModelsByProvider({});
    setLoadingModelMetadataByProvider({});

    const loadConfig = async () => {
      setIsLoading(true);
      try {
        const data = await memoriesApi.getConfig();
        setConfig(data);
        setFormState(toFormState(data));
      } catch (error: unknown) {
        toast.error(
          getErrorDetail(error) ||
            t(
              "memory.config.loadFailed",
              "Failed to load memory configuration",
            ),
        );
      } finally {
        setIsLoading(false);
      }
    };

    const loadProviders = async () => {
      setIsLoadingProviders(true);
      try {
        const providers = await llmApi.getAvailableProviders();
        setAvailableProviders(providers);
      } catch {
        setAvailableProviders({});
      } finally {
        setIsLoadingProviders(false);
      }
    };

    loadConfig();
    loadProviders();
  }, [isOpen, t]);

  const providerOptions = useMemo(
    () => Object.keys(availableProviders).sort((a, b) => a.localeCompare(b)),
    [availableProviders],
  );

  const ensureProviderTypedModels = useCallback(
    async (provider: string) => {
      if (!provider) {
        return;
      }
      if (
        typedModelsByProvider[provider] ||
        loadingModelMetadataByProvider[provider]
      ) {
        return;
      }

      const providerModels = availableProviders[provider] || [];
      if (providerModels.length === 0) {
        setTypedModelsByProvider((prev) => ({
          ...prev,
          [provider]: {
            embedding: [],
            rerank: [],
            generation: [],
          },
        }));
        return;
      }

      setLoadingModelMetadataByProvider((prev) => ({
        ...prev,
        [provider]: true,
      }));

      try {
        const metadata = await llmApi.getProviderModelsMetadata(provider);
        const modelsMetadata = metadata.models || {};
        setTypedModelsByProvider((prev) => ({
          ...prev,
          [provider]: {
            embedding: selectModelsByType(
              providerModels,
              modelsMetadata,
              "embedding",
            ),
            rerank: selectModelsByType(
              providerModels,
              modelsMetadata,
              "rerank",
            ),
            generation: selectModelsByType(
              providerModels,
              modelsMetadata,
              "generation",
            ),
          },
        }));
      } catch {
        setTypedModelsByProvider((prev) => ({
          ...prev,
          [provider]: {
            embedding: selectModelsByType(providerModels, {}, "embedding"),
            rerank: selectModelsByType(providerModels, {}, "rerank"),
            generation: selectModelsByType(providerModels, {}, "generation"),
          },
        }));
      } finally {
        setLoadingModelMetadataByProvider((prev) => ({
          ...prev,
          [provider]: false,
        }));
      }
    },
    [availableProviders, loadingModelMetadataByProvider, typedModelsByProvider],
  );

  useEffect(() => {
    if (!formState.embedding.provider) {
      return;
    }
    void ensureProviderTypedModels(formState.embedding.provider);
  }, [ensureProviderTypedModels, formState.embedding.provider]);

  useEffect(() => {
    if (!formState.retrieval.rerank_provider) {
      return;
    }
    void ensureProviderTypedModels(formState.retrieval.rerank_provider);
  }, [ensureProviderTypedModels, formState.retrieval.rerank_provider]);

  useEffect(() => {
    if (!formState.fact_extraction.provider) {
      return;
    }
    void ensureProviderTypedModels(formState.fact_extraction.provider);
  }, [ensureProviderTypedModels, formState.fact_extraction.provider]);

  useEffect(() => {
    if (!formState.skill_learning.provider) {
      return;
    }
    void ensureProviderTypedModels(formState.skill_learning.provider);
  }, [ensureProviderTypedModels, formState.skill_learning.provider]);

  const embeddingModels = useMemo(() => {
    if (!formState.embedding.provider) {
      return [];
    }
    return typedModelsByProvider[formState.embedding.provider]?.embedding || [];
  }, [formState.embedding.provider, typedModelsByProvider]);

  const rerankModels = useMemo(() => {
    if (!formState.retrieval.rerank_provider) {
      return [];
    }
    return (
      typedModelsByProvider[formState.retrieval.rerank_provider]?.rerank || []
    );
  }, [formState.retrieval.rerank_provider, typedModelsByProvider]);

  const factExtractionModels = useMemo(() => {
    if (!formState.fact_extraction.provider) {
      return [];
    }
    return (
      typedModelsByProvider[formState.fact_extraction.provider]?.generation ||
      []
    );
  }, [formState.fact_extraction.provider, typedModelsByProvider]);

  const skillLearningModels = useMemo(() => {
    if (!formState.skill_learning.provider) {
      return [];
    }
    return typedModelsByProvider[formState.skill_learning.provider]?.generation || [];
  }, [formState.skill_learning.provider, typedModelsByProvider]);

  const isEmbeddingModelsLoading = Boolean(
    formState.embedding.provider &&
    loadingModelMetadataByProvider[formState.embedding.provider],
  );
  const isRerankModelsLoading = Boolean(
    formState.retrieval.rerank_provider &&
    loadingModelMetadataByProvider[formState.retrieval.rerank_provider],
  );
  const isFactExtractionModelsLoading = Boolean(
    formState.fact_extraction.provider &&
    loadingModelMetadataByProvider[formState.fact_extraction.provider],
  );
  const isSkillLearningModelsLoading = Boolean(
    formState.skill_learning.provider &&
    loadingModelMetadataByProvider[formState.skill_learning.provider],
  );

  const embeddingModelMissing =
    Boolean(formState.embedding.model) &&
    !embeddingModels.includes(formState.embedding.model);
  const rerankModelMissing =
    Boolean(formState.retrieval.rerank_model) &&
    !rerankModels.includes(formState.retrieval.rerank_model);
  const factExtractionModelMissing =
    Boolean(formState.fact_extraction.model) &&
    !factExtractionModels.includes(formState.fact_extraction.model);
  const skillLearningModelMissing =
    Boolean(formState.skill_learning.model) &&
    !skillLearningModels.includes(formState.skill_learning.model);

  const applyRecommended = () => {
    const recommendedRoot = asObject(config?.recommended);
    const recommendedUserMemory = asObject(recommendedRoot.user_memory);
    const recommendedEmbedding = asObject(recommendedUserMemory.embedding);
    const recommendedRetrieval = asObject(recommendedUserMemory.retrieval);
    const recommendedFactExtraction = asObject(recommendedUserMemory.extraction);
    const recommendedConsolidation = asObject(recommendedUserMemory.consolidation);
    const recommendedSkillLearning = asObject(recommendedRoot.skill_learning);
    const recommendedSkillExtraction = asObject(recommendedSkillLearning.extraction);
    const recommendedSkillReview = asObject(recommendedSkillLearning.proposal_review);
    const recommendedSkillPublish = asObject(recommendedSkillLearning.publish_policy);
    const recommendedSessionLedger = asObject(recommendedRoot.session_ledger);
    const recommendedRuntime = asObject(recommendedRoot.runtime_context);

    setFormState((prev) => ({
      embedding: {
        ...prev.embedding,
        provider: asString(
          recommendedEmbedding.provider,
          prev.embedding.provider,
        ),
        model: asString(recommendedEmbedding.model, prev.embedding.model),
        dimension: asNumber(
          recommendedEmbedding.dimension,
          prev.embedding.dimension,
        ),
        inherit_from_knowledge_base: asBoolean(
          recommendedEmbedding.inherit_from_knowledge_base,
          prev.embedding.inherit_from_knowledge_base,
        ),
      },
      retrieval: {
        ...prev.retrieval,
        top_k: asNumber(recommendedRetrieval.top_k, prev.retrieval.top_k),
        similarity_threshold: asNumber(
          recommendedRetrieval.similarity_threshold,
          prev.retrieval.similarity_threshold,
        ),
        similarity_weight: asNumber(
          recommendedRetrieval.similarity_weight,
          prev.retrieval.similarity_weight,
        ),
        recency_weight: asNumber(
          recommendedRetrieval.recency_weight,
          prev.retrieval.recency_weight,
        ),
        strict_keyword_fallback: asBoolean(
          recommendedRetrieval.strict_keyword_fallback,
          prev.retrieval.strict_keyword_fallback,
        ),
        enable_reranking: asBoolean(
          recommendedRetrieval.enable_reranking,
          prev.retrieval.enable_reranking,
        ),
        rerank_provider: asString(
          recommendedRetrieval.rerank_provider,
          prev.retrieval.rerank_provider,
        ),
        rerank_model: asString(
          recommendedRetrieval.rerank_model,
          prev.retrieval.rerank_model,
        ),
        rerank_top_k: asNumber(
          recommendedRetrieval.rerank_top_k,
          prev.retrieval.rerank_top_k,
        ),
        rerank_weight: asNumber(
          recommendedRetrieval.rerank_weight,
          prev.retrieval.rerank_weight,
        ),
        rerank_timeout_seconds: asNumber(
          recommendedRetrieval.rerank_timeout_seconds,
          prev.retrieval.rerank_timeout_seconds,
        ),
        rerank_failure_backoff_seconds: asNumber(
          recommendedRetrieval.rerank_failure_backoff_seconds,
          prev.retrieval.rerank_failure_backoff_seconds,
        ),
        rerank_doc_max_chars: asNumber(
          recommendedRetrieval.rerank_doc_max_chars,
          prev.retrieval.rerank_doc_max_chars,
        ),
        milvus_metric_type: asString(
          asObject(recommendedRetrieval.milvus).metric_type,
          prev.retrieval.milvus_metric_type,
        ),
        milvus_nprobe: asNumber(
          asObject(recommendedRetrieval.milvus).nprobe,
          prev.retrieval.milvus_nprobe,
        ),
      },
      fact_extraction: {
        ...prev.fact_extraction,
        enabled: true,
        model_enabled: true,
        provider: asString(
          recommendedFactExtraction.provider,
          prev.fact_extraction.provider,
        ),
        model: asString(
          recommendedFactExtraction.model,
          prev.fact_extraction.model,
        ),
        timeout_seconds: asNumber(
          recommendedFactExtraction.timeout_seconds,
          prev.fact_extraction.timeout_seconds,
        ),
        max_facts: asNumber(
          recommendedFactExtraction.max_facts,
          prev.fact_extraction.max_facts,
        ),
        max_preference_facts: asNumber(
          recommendedFactExtraction.max_preference_facts,
          prev.fact_extraction.max_preference_facts,
        ),
        max_agent_candidates: asNumber(
          recommendedSkillExtraction.max_proposals,
          prev.fact_extraction.max_agent_candidates,
        ),
        enable_heuristic_fallback: asBoolean(
          recommendedFactExtraction.enable_heuristic_fallback,
          prev.fact_extraction.enable_heuristic_fallback,
        ),
        secondary_recall_enabled: asBoolean(
          recommendedFactExtraction.secondary_recall_enabled,
          prev.fact_extraction.secondary_recall_enabled,
        ),
        failure_backoff_seconds: asNumber(
          recommendedFactExtraction.failure_backoff_seconds,
          prev.fact_extraction.failure_backoff_seconds,
        ),
      },
      skill_learning: {
        ...prev.skill_learning,
        enabled: asBoolean(recommendedSkillExtraction.enabled, prev.skill_learning.enabled),
        provider: asString(recommendedSkillExtraction.provider, prev.skill_learning.provider),
        model: asString(recommendedSkillExtraction.model, prev.skill_learning.model),
        timeout_seconds: asNumber(
          recommendedSkillExtraction.timeout_seconds,
          prev.skill_learning.timeout_seconds,
        ),
        max_proposals: asNumber(
          recommendedSkillExtraction.max_proposals,
          prev.skill_learning.max_proposals,
        ),
        failure_backoff_seconds: asNumber(
          recommendedSkillExtraction.failure_backoff_seconds,
          prev.skill_learning.failure_backoff_seconds,
        ),
        require_human_review: asBoolean(
          recommendedSkillReview.require_human_review,
          prev.skill_learning.require_human_review,
        ),
        allow_revise: asBoolean(
          recommendedSkillReview.allow_revise,
          prev.skill_learning.allow_revise,
        ),
        default_review_status: asString(
          recommendedSkillReview.default_review_status,
          prev.skill_learning.default_review_status,
        ),
        publish_enabled: asBoolean(
          recommendedSkillPublish.enabled,
          prev.skill_learning.publish_enabled,
        ),
        publish_skill_type: asString(
          recommendedSkillPublish.skill_type,
          prev.skill_learning.publish_skill_type,
        ),
        publish_storage_type: asString(
          recommendedSkillPublish.storage_type,
          prev.skill_learning.publish_storage_type,
        ),
        reuse_existing_by_name: asBoolean(
          recommendedSkillPublish.reuse_existing_by_name,
          prev.skill_learning.reuse_existing_by_name,
        ),
      },
      session_ledger: {
        ...prev.session_ledger,
        enabled: asBoolean(
          recommendedSessionLedger.enabled,
          prev.session_ledger.enabled,
        ),
        retention_days: asNumber(
          recommendedSessionLedger.retention_days,
          prev.session_ledger.retention_days,
        ),
        run_on_startup: asBoolean(
          recommendedSessionLedger.run_on_startup,
          prev.session_ledger.run_on_startup,
        ),
        startup_delay_seconds: asNumber(
          recommendedSessionLedger.startup_delay_seconds,
          prev.session_ledger.startup_delay_seconds,
        ),
        cleanup_interval_seconds: asNumber(
          recommendedSessionLedger.cleanup_interval_seconds,
          prev.session_ledger.cleanup_interval_seconds,
        ),
        batch_size: asNumber(
          recommendedSessionLedger.batch_size,
          prev.session_ledger.batch_size,
        ),
        dry_run: asBoolean(
          recommendedSessionLedger.dry_run,
          prev.session_ledger.dry_run,
        ),
      },
      maintenance: {
        materialization: {
          ...prev.maintenance.materialization,
          enabled: asBoolean(
            recommendedConsolidation.enabled,
            prev.maintenance.materialization.enabled,
          ),
          run_on_startup: asBoolean(
            recommendedConsolidation.run_on_startup,
            prev.maintenance.materialization.run_on_startup,
          ),
          startup_delay_seconds: asNumber(
            recommendedConsolidation.startup_delay_seconds,
            prev.maintenance.materialization.startup_delay_seconds,
          ),
          interval_seconds: asNumber(
            recommendedConsolidation.interval_seconds,
            prev.maintenance.materialization.interval_seconds,
          ),
          limit: asNumber(
            recommendedConsolidation.limit,
            prev.maintenance.materialization.limit,
          ),
          dry_run: asBoolean(
            recommendedConsolidation.dry_run,
            prev.maintenance.materialization.dry_run,
          ),
        },
      },
      runtime: {
        ...prev.runtime,
        enable_user_memory: asBoolean(
          recommendedRuntime.enable_user_memory,
          prev.runtime.enable_user_memory,
        ),
        enable_skills: asBoolean(
          recommendedRuntime.enable_skills,
          prev.runtime.enable_skills,
        ),
        enable_knowledge_base: asBoolean(
          recommendedRuntime.enable_knowledge_base,
          prev.runtime.enable_knowledge_base,
        ),
        collection_retry_attempts: asNumber(
          recommendedRuntime.collection_retry_attempts,
          prev.runtime.collection_retry_attempts,
        ),
        collection_retry_delay_seconds: asNumber(
          recommendedRuntime.collection_retry_delay_seconds,
          prev.runtime.collection_retry_delay_seconds,
        ),
        search_timeout_seconds: asNumber(
          recommendedRuntime.search_timeout_seconds,
          prev.runtime.search_timeout_seconds,
        ),
        delete_timeout_seconds: asNumber(
          recommendedRuntime.delete_timeout_seconds,
          prev.runtime.delete_timeout_seconds,
        ),
      },
    }));

    toast.success(
      t("memory.config.applyRecommended", "Recommended values applied"),
    );
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const payload = toUpdatePayload(formState);
      const updated = await memoriesApi.updateConfig(payload);
      setConfig(updated);
      setFormState(toFormState(updated));
      onSaved?.(updated);
      toast.success(
        t("memory.config.saveSuccess", "Memory configuration saved"),
      );
      onClose();
    } catch (error: unknown) {
      toast.error(
        getErrorDetail(error) ||
          t("memory.config.saveFailed", "Failed to save memory configuration"),
      );
    } finally {
      setIsSaving(false);
    }
  };

  const handleEmbeddingProviderChange = (provider: string) => {
    void ensureProviderTypedModels(provider);
    const candidates = typedModelsByProvider[provider]?.embedding || [];
    setFormState((prev) => ({
      ...prev,
      embedding: {
        ...prev.embedding,
        provider,
        model: candidates[0] || "",
      },
    }));
  };

  const handleRerankProviderChange = (provider: string) => {
    void ensureProviderTypedModels(provider);
    const candidates = typedModelsByProvider[provider]?.rerank || [];
    setFormState((prev) => ({
      ...prev,
      retrieval: {
        ...prev.retrieval,
        rerank_provider: provider,
        rerank_model: candidates[0] || "",
      },
    }));
  };

  const handleFactExtractionProviderChange = (provider: string) => {
    void ensureProviderTypedModels(provider);
    const candidates = typedModelsByProvider[provider]?.generation || [];
    setFormState((prev) => ({
      ...prev,
      fact_extraction: {
        ...prev.fact_extraction,
        provider,
        model: candidates[0] || "",
      },
    }));
  };

  const handleSkillLearningProviderChange = (provider: string) => {
    void ensureProviderTypedModels(provider);
    const candidates = typedModelsByProvider[provider]?.generation || [];
    setFormState((prev) => ({
      ...prev,
      skill_learning: {
        ...prev.skill_learning,
        provider,
        model: candidates[0] || "",
      },
    }));
  };

  useEffect(() => {
    const provider = formState.embedding.provider;
    if (!provider || embeddingModels.length === 0) {
      return;
    }
    if (
      formState.embedding.model &&
      embeddingModels.includes(formState.embedding.model)
    ) {
      return;
    }
    setFormState((prev) => ({
      ...prev,
      embedding: {
        ...prev.embedding,
        model: embeddingModels[0] || "",
      },
    }));
  }, [
    embeddingModels,
    formState.embedding.model,
    formState.embedding.provider,
  ]);

  useEffect(() => {
    const provider = formState.retrieval.rerank_provider;
    if (!provider || rerankModels.length === 0) {
      return;
    }
    if (
      formState.retrieval.rerank_model &&
      rerankModels.includes(formState.retrieval.rerank_model)
    ) {
      return;
    }
    setFormState((prev) => ({
      ...prev,
      retrieval: {
        ...prev.retrieval,
        rerank_model: rerankModels[0] || "",
      },
    }));
  }, [
    formState.retrieval.rerank_model,
    formState.retrieval.rerank_provider,
    rerankModels,
  ]);

  useEffect(() => {
    const provider = formState.fact_extraction.provider;
    if (!provider || factExtractionModels.length === 0) {
      return;
    }
    if (
      formState.fact_extraction.model &&
      factExtractionModels.includes(formState.fact_extraction.model)
    ) {
      return;
    }
    setFormState((prev) => ({
      ...prev,
      fact_extraction: {
        ...prev.fact_extraction,
        model: factExtractionModels[0] || "",
      },
    }));
  }, [
    factExtractionModels,
    formState.fact_extraction.model,
    formState.fact_extraction.provider,
  ]);

  useEffect(() => {
    const provider = formState.skill_learning.provider;
    if (!provider || skillLearningModels.length === 0) {
      return;
    }
    if (
      formState.skill_learning.model &&
      skillLearningModels.includes(formState.skill_learning.model)
    ) {
      return;
    }
    setFormState((prev) => ({
      ...prev,
      skill_learning: {
        ...prev.skill_learning,
        model: skillLearningModels[0] || "",
      },
    }));
  }, [
    formState.skill_learning.model,
    formState.skill_learning.provider,
    skillLearningModels,
  ]);

  if (!isOpen) {
    return null;
  }

  return (
    <LayoutModal
      isOpen={isOpen}
      onClose={onClose}
      closeOnBackdropClick={false}
      closeOnEscape={true}
    >
      <ModalPanel className="w-full max-w-4xl max-h-[calc(100vh-var(--app-header-height,4rem)-3rem)] overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Settings2 className="w-6 h-6 text-indigo-500" />
            <div>
              <h2 className="text-2xl font-bold text-gray-800 dark:text-white">
                {t(
                  "memory.config.editorTitle",
                  "Memory Retrieval Configuration",
                )}
              </h2>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                {t(
                  "memory.config.editorSubtitle",
                  "Configure embedding and rerank models independently from knowledge base.",
                )}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/20 rounded-lg transition-colors"
          >
            <X className="w-6 h-6 text-gray-700 dark:text-gray-300" />
          </button>
        </div>

        {isLoading ? (
          <div className="py-14 flex items-center justify-center gap-3 text-gray-600 dark:text-gray-300">
            <Loader2 className="w-5 h-5 animate-spin" />
            <span>{t("common.loading", "Loading...")}</span>
          </div>
        ) : (
          <div className="space-y-5">
            <div className="rounded-xl border border-zinc-200/80 dark:border-zinc-700/80 bg-white/60 dark:bg-zinc-900/50 p-4">
              <div className="flex items-center justify-between gap-3 mb-3">
                <div>
                  <h3 className="text-base font-semibold text-zinc-800 dark:text-zinc-100">
                    {t("memory.config.embedding", "Embedding")}
                  </h3>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                    {t(
                      "memory.config.embeddingHint",
                      "Used to generate memory vectors during write and query.",
                    )}
                  </p>
                </div>
                {isLoadingProviders && (
                  <span className="inline-flex items-center gap-1 text-xs text-zinc-500">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    {t("memory.config.loadingProviders", "Loading providers")}
                  </span>
                )}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <label className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="block mb-1">
                    {t("memory.config.provider", "Provider")}
                  </span>
                  <select
                    value={formState.embedding.provider}
                    onChange={(event) =>
                      handleEmbeddingProviderChange(event.target.value)
                    }
                    className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                  >
                    <option value="">{t("memory.config.none", "None")}</option>
                    {providerOptions.map((provider) => (
                      <option key={provider} value={provider}>
                        {provider}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="block mb-1">
                    {t("memory.config.dimension", "Dimension")}
                  </span>
                  <input
                    type="number"
                    min={1}
                    value={formState.embedding.dimension}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        embedding: {
                          ...prev.embedding,
                          dimension: asNumber(
                            event.target.value,
                            prev.embedding.dimension,
                          ),
                        },
                      }))
                    }
                    className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                  />
                </label>
              </div>

              <label className="block text-sm text-zinc-700 dark:text-zinc-300 mt-3">
                <span className="block mb-1">
                  {t("memory.config.model", "Model")}
                </span>
                <select
                  value={formState.embedding.model}
                  onChange={(event) =>
                    setFormState((prev) => ({
                      ...prev,
                      embedding: {
                        ...prev.embedding,
                        model: event.target.value,
                      },
                    }))
                  }
                  disabled={!formState.embedding.provider}
                  className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                >
                  {!formState.embedding.provider ? (
                    <option value="">
                      {t(
                        "memory.config.selectProviderFirst",
                        "Select provider first",
                      )}
                    </option>
                  ) : isEmbeddingModelsLoading ? (
                    <option value="">
                      {t("memory.config.loadingModels", "Loading models")}
                    </option>
                  ) : embeddingModels.length === 0 ? (
                    <option value="">
                      {t("memory.config.noModels", "No models available")}
                    </option>
                  ) : null}
                  {embeddingModelMissing && (
                    <option value={formState.embedding.model}>
                      {t("memory.config.currentModel", "Current")}:{" "}
                      {formState.embedding.model}
                    </option>
                  )}
                  {embeddingModels.map((model) => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  ))}
                </select>
              </label>

              <label className="mt-3 inline-flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                <input
                  type="checkbox"
                  checked={formState.embedding.inherit_from_knowledge_base}
                  onChange={(event) =>
                    setFormState((prev) => ({
                      ...prev,
                      embedding: {
                        ...prev.embedding,
                        inherit_from_knowledge_base: event.target.checked,
                      },
                    }))
                  }
                  className="rounded"
                />
                {t(
                  "memory.config.inheritEmbedding",
                  "Allow fallback to knowledge-base embedding when memory embedding is blank",
                )}
              </label>

              <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
                {t("memory.config.effective", "Effective")}:{" "}
                {config?.user_memory?.embedding?.effective?.provider || "-"} /{" "}
                {config?.user_memory?.embedding?.effective?.model || "-"}
                {` (${t("memory.config.source", "Source")}: ${config?.user_memory?.embedding?.sources?.provider || "-"})`}
              </p>
            </div>

            <div className="rounded-xl border border-zinc-200/80 dark:border-zinc-700/80 bg-white/60 dark:bg-zinc-900/50 p-4">
              <div className="flex items-center justify-between gap-3 mb-3">
                <div>
                  <h3 className="text-base font-semibold text-zinc-800 dark:text-zinc-100">
                    {t("memory.config.retrieval", "Retrieval")}
                  </h3>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                    {t(
                      "memory.config.retrievalHint",
                      "Tune recall, scoring and rerank behavior for memory search.",
                    )}
                  </p>
                </div>
                <button
                  onClick={() => setShowAdvanced((prev) => !prev)}
                  className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-white/15 hover:bg-white/25 text-zinc-700 dark:text-zinc-300"
                >
                  <SlidersHorizontal className="w-3 h-3" />
                  {showAdvanced
                    ? t("memory.config.hideAdvanced", "Hide Advanced")
                    : t("memory.config.showAdvanced", "Show Advanced")}
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                <label className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="block mb-1">
                    {t("memory.config.topk", "Top-K")}
                  </span>
                  <input
                    type="number"
                    min={1}
                    value={formState.retrieval.top_k}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        retrieval: {
                          ...prev.retrieval,
                          top_k: asNumber(
                            event.target.value,
                            prev.retrieval.top_k,
                          ),
                        },
                      }))
                    }
                    className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                  />
                  <span className="mt-1 block text-xs text-zinc-500 dark:text-zinc-400">
                    {t(
                      "memory.config.topkHint",
                      "Max candidate memories returned per query before post-filtering.",
                    )}
                  </span>
                </label>

                <label className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="block mb-1">
                    {t(
                      "memory.config.similarityThreshold",
                      "Similarity Threshold",
                    )}
                  </span>
                  <input
                    type="number"
                    step="0.01"
                    min={0}
                    value={formState.retrieval.similarity_threshold}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        retrieval: {
                          ...prev.retrieval,
                          similarity_threshold: asNumber(
                            event.target.value,
                            prev.retrieval.similarity_threshold,
                          ),
                        },
                      }))
                    }
                    className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                  />
                  <span className="mt-1 block text-xs text-zinc-500 dark:text-zinc-400">
                    {t(
                      "memory.config.similarityThresholdHint",
                      "Global floor for memory recall in agent runtime. Lower improves recall; higher improves precision.",
                    )}
                  </span>
                </label>

                {showAdvanced && (
                  <>
                    <label className="text-sm text-zinc-700 dark:text-zinc-300">
                      <span className="block mb-1">
                        {t(
                          "memory.config.similarityWeight",
                          "Similarity Weight",
                        )}
                      </span>
                      <input
                        type="number"
                        step="0.01"
                        min={0}
                        max={1}
                        value={formState.retrieval.similarity_weight}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            retrieval: {
                              ...prev.retrieval,
                              similarity_weight: asNumber(
                                event.target.value,
                                prev.retrieval.similarity_weight,
                              ),
                            },
                          }))
                        }
                        className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                      />
                    </label>

                    <label className="text-sm text-zinc-700 dark:text-zinc-300">
                      <span className="block mb-1">
                        {t("memory.config.recencyWeight", "Recency Weight")}
                      </span>
                      <input
                        type="number"
                        step="0.01"
                        min={0}
                        max={1}
                        value={formState.retrieval.recency_weight}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            retrieval: {
                              ...prev.retrieval,
                              recency_weight: asNumber(
                                event.target.value,
                                prev.retrieval.recency_weight,
                              ),
                            },
                          }))
                        }
                        className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                      />
                    </label>
                  </>
                )}
              </div>

              <label className="mt-3 inline-flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                <input
                  type="checkbox"
                  checked={formState.retrieval.strict_keyword_fallback}
                  onChange={(event) =>
                    setFormState((prev) => ({
                      ...prev,
                      retrieval: {
                        ...prev.retrieval,
                        strict_keyword_fallback: event.target.checked,
                      },
                    }))
                  }
                  className="rounded"
                />
                {t(
                  "memory.config.strictKeywordFallback",
                  "Strict keyword fallback",
                )}
              </label>
              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                {t(
                  "memory.config.strictKeywordFallbackHint",
                  "When semantic search misses, only return keyword matches with stronger lexical constraints.",
                )}
              </p>

              <label className="mt-3 inline-flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                <input
                  type="checkbox"
                  checked={formState.retrieval.enable_reranking}
                  onChange={(event) =>
                    setFormState((prev) => ({
                      ...prev,
                      retrieval: {
                        ...prev.retrieval,
                        enable_reranking: event.target.checked,
                      },
                    }))
                  }
                  className="rounded"
                />
                {t("memory.config.enableRerank", "Enable model rerank")}
              </label>

              {formState.retrieval.enable_reranking && (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
                    <label className="text-sm text-zinc-700 dark:text-zinc-300">
                      <span className="block mb-1">
                        {t("memory.config.rerankProvider", "Rerank Provider")}
                      </span>
                      <select
                        value={formState.retrieval.rerank_provider}
                        onChange={(event) =>
                          handleRerankProviderChange(event.target.value)
                        }
                        className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                      >
                        <option value="">
                          {t("memory.config.none", "None")}
                        </option>
                        {providerOptions.map((provider) => (
                          <option key={provider} value={provider}>
                            {provider}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label className="text-sm text-zinc-700 dark:text-zinc-300">
                      <span className="block mb-1">
                        {t("memory.config.rerankTopK", "Rerank Top-K")}
                      </span>
                      <input
                        type="number"
                        min={1}
                        value={formState.retrieval.rerank_top_k}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            retrieval: {
                              ...prev.retrieval,
                              rerank_top_k: asNumber(
                                event.target.value,
                                prev.retrieval.rerank_top_k,
                              ),
                            },
                          }))
                        }
                        className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                      />
                    </label>
                  </div>

                  <label className="block text-sm text-zinc-700 dark:text-zinc-300 mt-3">
                    <span className="block mb-1">
                      {t("memory.config.rerankModel", "Rerank Model")}
                    </span>
                    <select
                      value={formState.retrieval.rerank_model}
                      onChange={(event) =>
                        setFormState((prev) => ({
                          ...prev,
                          retrieval: {
                            ...prev.retrieval,
                            rerank_model: event.target.value,
                          },
                        }))
                      }
                      disabled={!formState.retrieval.rerank_provider}
                      className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                    >
                      {!formState.retrieval.rerank_provider ? (
                        <option value="">
                          {t(
                            "memory.config.selectProviderFirst",
                            "Select provider first",
                          )}
                        </option>
                      ) : isRerankModelsLoading ? (
                        <option value="">
                          {t("memory.config.loadingModels", "Loading models")}
                        </option>
                      ) : rerankModels.length === 0 ? (
                        <option value="">
                          {t("memory.config.noModels", "No models available")}
                        </option>
                      ) : null}
                      {rerankModelMissing && (
                        <option value={formState.retrieval.rerank_model}>
                          {t("memory.config.currentModel", "Current")}:{" "}
                          {formState.retrieval.rerank_model}
                        </option>
                      )}
                      {rerankModels.map((model) => (
                        <option key={model} value={model}>
                          {model}
                        </option>
                      ))}
                    </select>
                  </label>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
                    <label className="text-sm text-zinc-700 dark:text-zinc-300">
                      <span className="block mb-1">
                        {t("memory.config.rerankWeight", "Rerank Weight")}
                      </span>
                      <input
                        type="number"
                        step="0.01"
                        min={0}
                        max={1}
                        value={formState.retrieval.rerank_weight}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            retrieval: {
                              ...prev.retrieval,
                              rerank_weight: asNumber(
                                event.target.value,
                                prev.retrieval.rerank_weight,
                              ),
                            },
                          }))
                        }
                        className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                      />
                    </label>

                    {showAdvanced && (
                      <label className="text-sm text-zinc-700 dark:text-zinc-300">
                        <span className="block mb-1">
                          {t(
                            "memory.config.rerankDocMaxChars",
                            "Rerank Doc Max Chars",
                          )}
                        </span>
                        <input
                          type="number"
                          min={128}
                          value={formState.retrieval.rerank_doc_max_chars}
                          onChange={(event) =>
                            setFormState((prev) => ({
                              ...prev,
                              retrieval: {
                                ...prev.retrieval,
                                rerank_doc_max_chars: asNumber(
                                  event.target.value,
                                  prev.retrieval.rerank_doc_max_chars,
                                ),
                              },
                            }))
                          }
                          className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                        />
                      </label>
                    )}
                  </div>

                  {showAdvanced && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
                      <label className="text-sm text-zinc-700 dark:text-zinc-300">
                        <span className="block mb-1">
                          {t(
                            "memory.config.rerankTimeout",
                            "Rerank Timeout (s)",
                          )}
                        </span>
                        <input
                          type="number"
                          min={1}
                          value={formState.retrieval.rerank_timeout_seconds}
                          onChange={(event) =>
                            setFormState((prev) => ({
                              ...prev,
                              retrieval: {
                                ...prev.retrieval,
                                rerank_timeout_seconds: asNumber(
                                  event.target.value,
                                  prev.retrieval.rerank_timeout_seconds,
                                ),
                              },
                            }))
                          }
                          className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                        />
                      </label>

                      <label className="text-sm text-zinc-700 dark:text-zinc-300">
                        <span className="block mb-1">
                          {t(
                            "memory.config.rerankBackoff",
                            "Rerank Failure Backoff (s)",
                          )}
                        </span>
                        <input
                          type="number"
                          min={1}
                          value={
                            formState.retrieval.rerank_failure_backoff_seconds
                          }
                          onChange={(event) =>
                            setFormState((prev) => ({
                              ...prev,
                              retrieval: {
                                ...prev.retrieval,
                                rerank_failure_backoff_seconds: asNumber(
                                  event.target.value,
                                  prev.retrieval.rerank_failure_backoff_seconds,
                                ),
                              },
                            }))
                          }
                          className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                        />
                      </label>
                    </div>
                  )}
                </>
              )}

              {showAdvanced && (
                <div className="mt-4 p-3 rounded-lg border border-zinc-200/80 dark:border-zinc-700/80 bg-white/40 dark:bg-zinc-900/40">
                  <div className="text-sm font-medium text-zinc-700 dark:text-zinc-200 mb-2">
                    {t("memory.config.milvusTitle", "Milvus Search")}
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <label className="text-sm text-zinc-700 dark:text-zinc-300">
                      <span className="block mb-1">
                        {t("memory.config.milvusMetricType", "Metric Type")}
                      </span>
                      <select
                        value={formState.retrieval.milvus_metric_type}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            retrieval: {
                              ...prev.retrieval,
                              milvus_metric_type: event.target.value,
                            },
                          }))
                        }
                        className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                      >
                        {METRIC_TYPE_OPTIONS.map((metricType) => (
                          <option key={metricType} value={metricType}>
                            {metricType}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="text-sm text-zinc-700 dark:text-zinc-300">
                      <span className="block mb-1">
                        {t("memory.config.milvusNprobe", "NProbe")}
                      </span>
                      <input
                        type="number"
                        min={1}
                        value={formState.retrieval.milvus_nprobe}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            retrieval: {
                              ...prev.retrieval,
                              milvus_nprobe: asNumber(
                                event.target.value,
                                prev.retrieval.milvus_nprobe,
                              ),
                            },
                          }))
                        }
                        className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                      />
                    </label>
                  </div>
                </div>
              )}

              {showAdvanced && (
                <div className="mt-4 p-3 rounded-lg border border-zinc-200/80 dark:border-zinc-700/80 bg-white/40 dark:bg-zinc-900/40">
                  <div className="text-sm font-medium text-zinc-700 dark:text-zinc-200 mb-1">
                    {t("memory.config.runtimeTitle", "Runtime")}
                  </div>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-3">
                    {t(
                      "memory.config.runtimeHint",
                      "Control which context sources are injected at runtime and how retrieval retries/timeouts behave.",
                    )}
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
                    <label className="inline-flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                      <input
                        type="checkbox"
                        checked={formState.runtime.enable_user_memory}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            runtime: {
                              ...prev.runtime,
                              enable_user_memory: event.target.checked,
                            },
                          }))
                        }
                        className="rounded"
                      />
                      {t("memory.config.enableUserMemory", "Enable User Memory")}
                    </label>
                    <label className="inline-flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                      <input
                        type="checkbox"
                        checked={formState.runtime.enable_skills}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            runtime: {
                              ...prev.runtime,
                              enable_skills: event.target.checked,
                            },
                          }))
                        }
                        className="rounded"
                      />
                      {t("memory.config.enableSkills", "Enable Skills")}
                    </label>
                    <label className="inline-flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                      <input
                        type="checkbox"
                        checked={formState.runtime.enable_knowledge_base}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            runtime: {
                              ...prev.runtime,
                              enable_knowledge_base: event.target.checked,
                            },
                          }))
                        }
                        className="rounded"
                      />
                      {t("memory.config.enableKnowledgeBase", "Enable Knowledge Base")}
                    </label>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <label className="text-sm text-zinc-700 dark:text-zinc-300">
                      <span className="block mb-1">
                        {t(
                          "memory.config.collectionRetryAttempts",
                          "Collection Retry Attempts",
                        )}
                      </span>
                      <input
                        type="number"
                        min={1}
                        value={formState.runtime.collection_retry_attempts}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            runtime: {
                              ...prev.runtime,
                              collection_retry_attempts: asNumber(
                                event.target.value,
                                prev.runtime.collection_retry_attempts,
                              ),
                            },
                          }))
                        }
                        className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                      />
                    </label>

                    <label className="text-sm text-zinc-700 dark:text-zinc-300">
                      <span className="block mb-1">
                        {t(
                          "memory.config.collectionRetryDelay",
                          "Collection Retry Delay (s)",
                        )}
                      </span>
                      <input
                        type="number"
                        min={0}
                        step="0.01"
                        value={formState.runtime.collection_retry_delay_seconds}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            runtime: {
                              ...prev.runtime,
                              collection_retry_delay_seconds: asNumber(
                                event.target.value,
                                prev.runtime.collection_retry_delay_seconds,
                              ),
                            },
                          }))
                        }
                        className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                      />
                    </label>

                    <label className="text-sm text-zinc-700 dark:text-zinc-300">
                      <span className="block mb-1">
                        {t("memory.config.searchTimeout", "Search Timeout (s)")}
                      </span>
                      <input
                        type="number"
                        min={0.1}
                        step="0.1"
                        value={formState.runtime.search_timeout_seconds}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            runtime: {
                              ...prev.runtime,
                              search_timeout_seconds: asNumber(
                                event.target.value,
                                prev.runtime.search_timeout_seconds,
                              ),
                            },
                          }))
                        }
                        className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                      />
                    </label>

                    <label className="text-sm text-zinc-700 dark:text-zinc-300">
                      <span className="block mb-1">
                        {t("memory.config.deleteTimeout", "Delete Timeout (s)")}
                      </span>
                      <input
                        type="number"
                        min={0.1}
                        step="0.1"
                        value={formState.runtime.delete_timeout_seconds}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            runtime: {
                              ...prev.runtime,
                              delete_timeout_seconds: asNumber(
                                event.target.value,
                                prev.runtime.delete_timeout_seconds,
                              ),
                            },
                          }))
                        }
                        className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                      />
                    </label>
                  </div>
                </div>
              )}

              <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
                {t("memory.config.effective", "Effective")}:{" "}
                {config?.user_memory?.retrieval?.rerank_provider || "-"} /{" "}
                {config?.user_memory?.retrieval?.rerank_model || "-"}
                {` (${t("memory.config.source", "Source")}: ${config?.user_memory?.retrieval?.sources?.rerank_provider || "-"})`}
              </p>
            </div>

            <div className="rounded-xl border border-zinc-200/80 dark:border-zinc-700/80 bg-white/60 dark:bg-zinc-900/50 p-4">
              <div className="mb-3">
                <h3 className="text-base font-semibold text-zinc-800 dark:text-zinc-100">
                  {t(
                    "memory.config.factExtraction",
                    "User Memory Extraction",
                  )}
                </h3>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                  {t(
                    "memory.config.factExtractionHint",
                    "Extract stable user facts and preferences from completed sessions before projecting them into user memory views.",
                  )}
                </p>
              </div>

              <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-2">
                {t(
                  "memory.config.factExtractionModeHint",
                  "These controls tune the user-memory fact extractor. Skill-learning proposal extraction is configured separately below.",
                )}
              </p>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3">
                <label className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="block mb-1">
                    {t("memory.config.provider", "Provider")}
                  </span>
                  <select
                    value={formState.fact_extraction.provider}
                    onChange={(event) =>
                      handleFactExtractionProviderChange(event.target.value)
                    }
                    className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                  >
                    <option value="">{t("memory.config.none", "None")}</option>
                    {providerOptions.map((provider) => (
                      <option key={provider} value={provider}>
                        {provider}
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                    {t(
                      "memory.config.factExtractionProviderHint",
                      "Primary provider for session extraction; if unavailable, system falls back to agent/global model.",
                    )}
                  </p>
                </label>

                <label className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="block mb-1">
                    {t(
                      "memory.config.factExtractionMaxFacts",
                      "Max Facts / Memory",
                    )}
                  </span>
                  <input
                    type="number"
                    min={1}
                    value={formState.fact_extraction.max_facts}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        fact_extraction: {
                          ...prev.fact_extraction,
                          max_facts: asNumber(
                            event.target.value,
                            prev.fact_extraction.max_facts,
                          ),
                        },
                      }))
                    }
                    className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                  />
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                    {t(
                      "memory.config.factExtractionMaxFactsHint",
                      "Second-stage storage normalization cap per memory item (all write paths).",
                    )}
                  </p>
                </label>

                <label className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="block mb-1">
                    {t(
                      "memory.config.factExtractionMaxPreferenceFacts",
                      "Max User Facts",
                    )}
                  </span>
                  <input
                    type="number"
                    min={1}
                    value={formState.fact_extraction.max_preference_facts}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        fact_extraction: {
                          ...prev.fact_extraction,
                          max_preference_facts: asNumber(
                            event.target.value,
                            prev.fact_extraction.max_preference_facts,
                          ),
                        },
                      }))
                    }
                    className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                  />
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                    {t(
                      "memory.config.factExtractionMaxPreferenceFactsHint",
                      "First-stage session extraction cap for user profile/preference items per flush.",
                    )}
                  </p>
                </label>
              </div>

              <label className="block text-sm text-zinc-700 dark:text-zinc-300 mt-3">
                <span className="block mb-1">
                  {t("memory.config.model", "Model")}
                </span>
                <select
                  value={formState.fact_extraction.model}
                  onChange={(event) =>
                    setFormState((prev) => ({
                      ...prev,
                      fact_extraction: {
                        ...prev.fact_extraction,
                        model: event.target.value,
                      },
                    }))
                  }
                  disabled={!formState.fact_extraction.provider}
                  className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                >
                  {!formState.fact_extraction.provider ? (
                    <option value="">
                      {t(
                        "memory.config.selectProviderFirst",
                        "Select provider first",
                      )}
                    </option>
                  ) : isFactExtractionModelsLoading ? (
                    <option value="">
                      {t("memory.config.loadingModels", "Loading models")}
                    </option>
                  ) : factExtractionModels.length === 0 ? (
                    <option value="">
                      {t("memory.config.noModels", "No models available")}
                    </option>
                  ) : null}
                  {factExtractionModelMissing && (
                    <option value={formState.fact_extraction.model}>
                      {t("memory.config.currentModel", "Current")}:{" "}
                      {formState.fact_extraction.model}
                    </option>
                  )}
                  {factExtractionModels.map((model) => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                  {t(
                    "memory.config.factExtractionModelHintNew",
                    "Primary model for session extraction and storage normalization.",
                  )}
                </p>
              </label>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
                <label className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="block mb-1">
                    {t(
                      "memory.config.factExtractionTimeout",
                      "Request Timeout (s)",
                    )}
                  </span>
                  <input
                    type="number"
                    min={0.5}
                    step="0.1"
                    value={formState.fact_extraction.timeout_seconds}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        fact_extraction: {
                          ...prev.fact_extraction,
                          timeout_seconds: asNumber(
                            event.target.value,
                            prev.fact_extraction.timeout_seconds,
                          ),
                        },
                      }))
                    }
                    className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                  />
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                    {t(
                      "memory.config.factExtractionTimeoutHint",
                      "Per-attempt timeout for first-stage session extraction requests.",
                    )}
                  </p>
                </label>

                <label className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="block mb-1">
                    {t(
                      "memory.config.factExtractionBackoff",
                      "Failure Backoff (s)",
                    )}
                  </span>
                  <input
                    type="number"
                    min={1}
                    value={formState.fact_extraction.failure_backoff_seconds}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        fact_extraction: {
                          ...prev.fact_extraction,
                          failure_backoff_seconds: asNumber(
                            event.target.value,
                            prev.fact_extraction.failure_backoff_seconds,
                          ),
                        },
                      }))
                    }
                    className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                  />
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                    {t(
                      "memory.config.factExtractionBackoffHint",
                      "After first-stage extraction failures, skip new attempts for this duration.",
                    )}
                  </p>
                </label>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
                <label className="inline-flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                  <input
                    type="checkbox"
                    checked={
                      formState.fact_extraction.enable_heuristic_fallback
                    }
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        fact_extraction: {
                          ...prev.fact_extraction,
                          enable_heuristic_fallback: event.target.checked,
                        },
                      }))
                    }
                    className="rounded"
                  />
                  {t(
                    "memory.config.enableHeuristicFallback",
                    "Enable heuristic fallback when LLM extraction returns no user facts",
                  )}
                </label>

                <label className="inline-flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                  <input
                    type="checkbox"
                    checked={formState.fact_extraction.secondary_recall_enabled}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        fact_extraction: {
                          ...prev.fact_extraction,
                          secondary_recall_enabled: event.target.checked,
                        },
                      }))
                    }
                    className="rounded"
                  />
                  {t(
                    "memory.config.secondaryRecallEnabled",
                    "Run a second explicit-recall pass when the primary extraction misses user facts",
                  )}
                </label>
              </div>

              <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
                {t("memory.config.effective", "Effective")}:{" "}
                {config?.user_memory?.extraction?.effective?.provider || "-"} /{" "}
                {config?.user_memory?.extraction?.effective?.model || "-"}
                {` (${t("memory.config.source", "Source")}: ${config?.user_memory?.extraction?.sources?.provider || "-"})`}
              </p>
            </div>

            <div className="rounded-xl border border-zinc-200/80 dark:border-zinc-700/80 bg-white/60 dark:bg-zinc-900/50 p-4">
              <div className="mb-3">
                <h3 className="text-base font-semibold text-zinc-800 dark:text-zinc-100">
                  {t("memory.config.skillLearning", "Skill Learning")}
                </h3>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                  {t(
                    "memory.config.skillLearningHint",
                    "Configure how successful execution paths become reviewable skill proposals and how approved proposals publish into the skill registry.",
                  )}
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <label className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="block mb-1">{t("memory.config.provider", "Provider")}</span>
                  <select
                    value={formState.skill_learning.provider}
                    onChange={(event) =>
                      handleSkillLearningProviderChange(event.target.value)
                    }
                    className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                  >
                    <option value="">{t("memory.config.none", "None")}</option>
                    {providerOptions.map((provider) => (
                      <option key={provider} value={provider}>
                        {provider}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="block mb-1">
                    {t("memory.config.factExtractionMaxAgentCandidates", "Max Skill Proposals")}
                  </span>
                  <input
                    type="number"
                    min={1}
                    value={formState.skill_learning.max_proposals}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        fact_extraction: {
                          ...prev.fact_extraction,
                          max_agent_candidates: asNumber(
                            event.target.value,
                            prev.fact_extraction.max_agent_candidates,
                          ),
                        },
                        skill_learning: {
                          ...prev.skill_learning,
                          max_proposals: asNumber(
                            event.target.value,
                            prev.skill_learning.max_proposals,
                          ),
                        },
                      }))
                    }
                    className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                  />
                </label>

                <label className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="block mb-1">
                    {t("memory.config.reviewDefaultStatus", "Default Review Status")}
                  </span>
                  <select
                    value={formState.skill_learning.default_review_status}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        skill_learning: {
                          ...prev.skill_learning,
                          default_review_status: event.target.value,
                        },
                      }))
                    }
                    className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                  >
                    <option value="pending">pending</option>
                    <option value="published">published</option>
                    <option value="rejected">rejected</option>
                  </select>
                </label>
              </div>

              <label className="block text-sm text-zinc-700 dark:text-zinc-300 mt-3">
                <span className="block mb-1">{t("memory.config.model", "Model")}</span>
                <select
                  value={formState.skill_learning.model}
                  onChange={(event) =>
                    setFormState((prev) => ({
                      ...prev,
                      skill_learning: {
                        ...prev.skill_learning,
                        model: event.target.value,
                      },
                    }))
                  }
                  disabled={!formState.skill_learning.provider}
                  className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                >
                  {!formState.skill_learning.provider ? (
                    <option value="">
                      {t("memory.config.selectProviderFirst", "Select provider first")}
                    </option>
                  ) : isSkillLearningModelsLoading ? (
                    <option value="">
                      {t("memory.config.loadingModels", "Loading models")}
                    </option>
                  ) : skillLearningModels.length === 0 ? (
                    <option value="">
                      {t("memory.config.noModels", "No models available")}
                    </option>
                  ) : null}
                  {skillLearningModelMissing && (
                    <option value={formState.skill_learning.model}>
                      {t("memory.config.currentModel", "Current")}: {formState.skill_learning.model}
                    </option>
                  )}
                  {skillLearningModels.map((model) => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  ))}
                </select>
              </label>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
                <label className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="block mb-1">
                    {t("memory.config.factExtractionTimeout", "Request Timeout (s)")}
                  </span>
                  <input
                    type="number"
                    min={0.5}
                    step="0.1"
                    value={formState.skill_learning.timeout_seconds}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        skill_learning: {
                          ...prev.skill_learning,
                          timeout_seconds: asNumber(
                            event.target.value,
                            prev.skill_learning.timeout_seconds,
                          ),
                        },
                      }))
                    }
                    className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                  />
                </label>

                <label className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="block mb-1">
                    {t("memory.config.factExtractionBackoff", "Failure Backoff (s)")}
                  </span>
                  <input
                    type="number"
                    min={1}
                    value={formState.skill_learning.failure_backoff_seconds}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        skill_learning: {
                          ...prev.skill_learning,
                          failure_backoff_seconds: asNumber(
                            event.target.value,
                            prev.skill_learning.failure_backoff_seconds,
                          ),
                        },
                      }))
                    }
                    className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                  />
                </label>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
                <label className="inline-flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                  <input
                    type="checkbox"
                    checked={formState.skill_learning.require_human_review}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        skill_learning: {
                          ...prev.skill_learning,
                          require_human_review: event.target.checked,
                        },
                      }))
                    }
                    className="rounded"
                  />
                  {t("memory.config.requireHumanReview", "Require human review before publish")}
                </label>

                <label className="inline-flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                  <input
                    type="checkbox"
                    checked={formState.skill_learning.allow_revise}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        skill_learning: {
                          ...prev.skill_learning,
                          allow_revise: event.target.checked,
                        },
                      }))
                    }
                    className="rounded"
                  />
                  {t("memory.config.allowRevise", "Allow revise workflow")}
                </label>

                <label className="inline-flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                  <input
                    type="checkbox"
                    checked={formState.skill_learning.publish_enabled}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        skill_learning: {
                          ...prev.skill_learning,
                          publish_enabled: event.target.checked,
                        },
                      }))
                    }
                    className="rounded"
                  />
                  {t("memory.config.publishEnabled", "Enable publish to skill registry")}
                </label>

                <label className="inline-flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                  <input
                    type="checkbox"
                    checked={formState.skill_learning.reuse_existing_by_name}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        skill_learning: {
                          ...prev.skill_learning,
                          reuse_existing_by_name: event.target.checked,
                        },
                      }))
                    }
                    className="rounded"
                  />
                  {t("memory.config.reuseExistingByName", "Reuse existing published skill by name")}
                </label>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
                <label className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="block mb-1">{t("memory.config.skillType", "Skill Type")}</span>
                  <input
                    type="text"
                    value={formState.skill_learning.publish_skill_type}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        skill_learning: {
                          ...prev.skill_learning,
                          publish_skill_type: event.target.value,
                        },
                      }))
                    }
                    className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                  />
                </label>

                <label className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="block mb-1">
                    {t("memory.config.storageType", "Storage Type")}
                  </span>
                  <input
                    type="text"
                    value={formState.skill_learning.publish_storage_type}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        skill_learning: {
                          ...prev.skill_learning,
                          publish_storage_type: event.target.value,
                        },
                      }))
                    }
                    className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                  />
                </label>
              </div>

              <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
                {t("memory.config.effective", "Effective")}:{" "}
                {config?.skill_learning?.extraction?.effective?.provider || "-"} /{" "}
                {config?.skill_learning?.extraction?.effective?.model || "-"}
                {` (${t("memory.config.source", "Source")}: ${config?.skill_learning?.extraction?.sources?.provider || "-"})`}
              </p>
            </div>

            <div className="rounded-xl border border-zinc-200/80 dark:border-zinc-700/80 bg-white/60 dark:bg-zinc-900/50 p-4">
              <div className="mb-3">
                <h3 className="text-base font-semibold text-zinc-800 dark:text-zinc-100">
                  {t("memory.config.sessionLedger", "Session Ledger Retention")}
                </h3>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                  {t(
                    "memory.config.sessionLedgerHint",
                    "Session ledger keeps provenance for recent conversations only; durable entries and materializations survive cleanup.",
                  )}
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <label className="inline-flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                  <input
                    type="checkbox"
                    checked={formState.session_ledger.enabled}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        session_ledger: {
                          ...prev.session_ledger,
                          enabled: event.target.checked,
                        },
                      }))
                    }
                    className="rounded"
                  />
                  {t("memory.config.sessionLedgerEnabled", "Enable cleanup")}
                </label>

                <label className="inline-flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                  <input
                    type="checkbox"
                    checked={formState.session_ledger.run_on_startup}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        session_ledger: {
                          ...prev.session_ledger,
                          run_on_startup: event.target.checked,
                        },
                      }))
                    }
                    className="rounded"
                  />
                  {t("memory.config.runOnStartup", "Run on startup")}
                </label>

                <label className="inline-flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                  <input
                    type="checkbox"
                    checked={formState.session_ledger.dry_run}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        session_ledger: {
                          ...prev.session_ledger,
                          dry_run: event.target.checked,
                        },
                      }))
                    }
                    className="rounded"
                  />
                  {t("memory.config.dryRun", "Dry run")}
                </label>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mt-3">
                <label className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="block mb-1">
                    {t("memory.config.retentionDays", "Retention Days")}
                  </span>
                  <input
                    type="number"
                    min={1}
                    value={formState.session_ledger.retention_days}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        session_ledger: {
                          ...prev.session_ledger,
                          retention_days: asNumber(
                            event.target.value,
                            prev.session_ledger.retention_days,
                          ),
                        },
                      }))
                    }
                    className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                  />
                </label>
                <label className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="block mb-1">
                    {t("memory.config.cleanupInterval", "Cleanup Interval (s)")}
                  </span>
                  <input
                    type="number"
                    min={60}
                    value={formState.session_ledger.cleanup_interval_seconds}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        session_ledger: {
                          ...prev.session_ledger,
                          cleanup_interval_seconds: asNumber(
                            event.target.value,
                            prev.session_ledger.cleanup_interval_seconds,
                          ),
                        },
                      }))
                    }
                    className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                  />
                </label>
                <label className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="block mb-1">
                    {t("memory.config.startupDelay", "Startup Delay (s)")}
                  </span>
                  <input
                    type="number"
                    min={0}
                    value={formState.session_ledger.startup_delay_seconds}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        session_ledger: {
                          ...prev.session_ledger,
                          startup_delay_seconds: asNumber(
                            event.target.value,
                            prev.session_ledger.startup_delay_seconds,
                          ),
                        },
                      }))
                    }
                    className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                  />
                </label>
                <label className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="block mb-1">
                    {t("memory.config.batchSize", "Batch Size")}
                  </span>
                  <input
                    type="number"
                    min={1}
                    value={formState.session_ledger.batch_size}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        session_ledger: {
                          ...prev.session_ledger,
                          batch_size: asNumber(
                            event.target.value,
                            prev.session_ledger.batch_size,
                          ),
                        },
                      }))
                    }
                    className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                  />
                </label>
              </div>
            </div>

            <div className="rounded-xl border border-zinc-200/80 dark:border-zinc-700/80 bg-white/60 dark:bg-zinc-900/50 p-4">
              <div className="mb-3">
                <h3 className="text-base font-semibold text-zinc-800 dark:text-zinc-100">
                  {t("memory.config.maintenance", "User Memory Consolidation")}
                </h3>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                  {t(
                    "memory.config.maintenanceHint",
                    "Tune post-write consolidation separately from extraction so user-memory views stay deduplicated.",
                  )}
                </p>
              </div>

              <div className="rounded-lg border border-zinc-200/80 dark:border-zinc-700/80 p-3">
                <div className="text-sm font-medium text-zinc-700 dark:text-zinc-200 mb-3">
                  {t(
                    "memory.config.materializationMaintenance",
                    "Consolidation",
                  )}
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <label className="inline-flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                    <input
                      type="checkbox"
                      checked={formState.maintenance.materialization.enabled}
                      onChange={(event) =>
                        setFormState((prev) => ({
                          ...prev,
                          maintenance: {
                            ...prev.maintenance,
                            materialization: {
                              ...prev.maintenance.materialization,
                              enabled: event.target.checked,
                            },
                          },
                        }))
                      }
                      className="rounded"
                    />
                    {t("memory.config.enabled", "Enabled")}
                  </label>
                  <label className="inline-flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                    <input
                      type="checkbox"
                      checked={formState.maintenance.materialization.dry_run}
                      onChange={(event) =>
                        setFormState((prev) => ({
                          ...prev,
                          maintenance: {
                            ...prev.maintenance,
                            materialization: {
                              ...prev.maintenance.materialization,
                              dry_run: event.target.checked,
                            },
                          },
                        }))
                      }
                      className="rounded"
                    />
                    {t("memory.config.dryRun", "Dry run")}
                  </label>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3">
                  <label className="text-sm text-zinc-700 dark:text-zinc-300">
                    <span className="block mb-1">
                      {t("memory.config.interval", "Interval (s)")}
                    </span>
                    <input
                      type="number"
                      min={60}
                      value={formState.maintenance.materialization.interval_seconds}
                      onChange={(event) =>
                        setFormState((prev) => ({
                          ...prev,
                          maintenance: {
                            ...prev.maintenance,
                            materialization: {
                              ...prev.maintenance.materialization,
                              interval_seconds: asNumber(
                                event.target.value,
                                prev.maintenance.materialization.interval_seconds,
                              ),
                            },
                          },
                        }))
                      }
                      className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                    />
                  </label>
                  <label className="text-sm text-zinc-700 dark:text-zinc-300">
                    <span className="block mb-1">
                      {t("memory.config.limit", "Limit")}
                    </span>
                    <input
                      type="number"
                      min={1}
                      value={formState.maintenance.materialization.limit}
                      onChange={(event) =>
                        setFormState((prev) => ({
                          ...prev,
                          maintenance: {
                            ...prev.maintenance,
                            materialization: {
                              ...prev.maintenance.materialization,
                              limit: asNumber(
                                event.target.value,
                                prev.maintenance.materialization.limit,
                              ),
                            },
                          },
                        }))
                      }
                      className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                    />
                  </label>
                  <label className="text-sm text-zinc-700 dark:text-zinc-300">
                    <span className="block mb-1">
                      {t("memory.config.startupDelay", "Startup Delay (s)")}
                    </span>
                    <input
                      type="number"
                      min={0}
                      value={formState.maintenance.materialization.startup_delay_seconds}
                      onChange={(event) =>
                        setFormState((prev) => ({
                          ...prev,
                          maintenance: {
                            ...prev.maintenance,
                            materialization: {
                              ...prev.maintenance.materialization,
                              startup_delay_seconds: asNumber(
                                event.target.value,
                                prev.maintenance.materialization.startup_delay_seconds,
                              ),
                            },
                          },
                        }))
                      }
                      className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                    />
                  </label>
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="flex items-center justify-between gap-3 mt-6">
          <button
            onClick={applyRecommended}
            disabled={isLoading || isSaving}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-500 text-white hover:bg-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Sparkles className="w-4 h-4" />
            {t("memory.config.applyRecommended", "Apply Recommended")}
          </button>

          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              disabled={isSaving}
              className="px-4 py-2 rounded-lg bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-600 disabled:opacity-50"
            >
              {t("common.cancel", "Cancel")}
            </button>
            <button
              onClick={handleSave}
              disabled={isLoading || isSaving}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-500 text-white hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSaving ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Save className="w-4 h-4" />
              )}
              {t("common.save", "Save")}
            </button>
          </div>
        </div>
      </ModalPanel>
    </LayoutModal>
  );
};
