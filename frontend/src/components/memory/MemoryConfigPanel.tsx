import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  X,
  Save,
  Loader2,
  Settings2,
  Sparkles,
} from "lucide-react";
import toast from "react-hot-toast";
import { LayoutModal } from "@/components/LayoutModal";
import { ModalPanel } from "@/components/ModalPanel";
import { llmApi } from "@/api/llm";
import { memoryWorkbenchApi } from "@/api/memoryWorkbench";
import type { UpdateMemoryConfigRequest } from "@/api/memoryWorkbench";
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
    hybrid_enabled: boolean;
    similarity_threshold: number;
    rerank: {
      enabled: boolean;
      provider: string;
      model: string;
      top_k: number;
      weight: number;
      timeout_seconds: number;
      failure_backoff_seconds: number;
      doc_max_chars: number;
    };
    planner: {
      runtime_mode: string;
      api_mode: string;
      provider: string;
      model: string;
      timeout_seconds: number;
      failure_backoff_seconds: number;
      max_query_variants: number;
    };
    reflection: {
      enabled_api: boolean;
      max_rounds: number;
      min_results: number;
      min_score: number;
    };
  };
  fact_extraction: {
    provider: string;
    model: string;
    timeout_seconds: number;
    max_facts: number;
    max_preference_facts: number;
    enable_heuristic_fallback: boolean;
    secondary_recall_enabled: boolean;
    failure_backoff_seconds: number;
  };
  skill_learning: {
    provider: string;
    model: string;
    timeout_seconds: number;
    max_proposals: number;
    failure_backoff_seconds: number;
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
    projection: {
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
    hybrid_enabled: true,
    similarity_threshold: 0.3,
    rerank: {
      enabled: true,
      provider: "",
      model: "",
      top_k: 30,
      weight: 0.75,
      timeout_seconds: 8,
      failure_backoff_seconds: 30,
      doc_max_chars: 1200,
    },
    planner: {
      runtime_mode: "light",
      api_mode: "full",
      provider: "",
      model: "",
      timeout_seconds: 4,
      failure_backoff_seconds: 60,
      max_query_variants: 3,
    },
    reflection: {
      enabled_api: true,
      max_rounds: 1,
      min_results: 3,
      min_score: 0.45,
    },
  },
  fact_extraction: {
    provider: "",
    model: "",
    timeout_seconds: 120,
    max_facts: 10,
    max_preference_facts: 10,
    enable_heuristic_fallback: true,
    secondary_recall_enabled: true,
    failure_backoff_seconds: 60,
  },
  skill_learning: {
    provider: "",
    model: "",
    timeout_seconds: 120,
    max_proposals: 6,
    failure_backoff_seconds: 60,
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
    projection: {
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
  },
};

const EMBEDDING_MODEL_NAME_PATTERN =
  /embed|embedding|bge|m3e|e5|gte|voyage|jina-embeddings/i;
const CHAT_MODEL_NAME_PATTERN = /chat|instruct|gpt|qwen|llama|claude|deepseek/i;
const RERANK_MODEL_NAME_PATTERN = /rerank|reranker|bge-reranker|jina-reranker/i;

type ModelType = "embedding" | "generation" | "rerank";
type ProviderTypedModels = {
  embedding: string[];
  generation: string[];
  rerank: string[];
};

type ProviderOptionsByType = {
  embedding: string[];
  generation: string[];
  rerank: string[];
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
      if (modelType === "rerank") {
        return normalized === "rerank";
      }
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
        projection: { ...DEFAULT_FORM_STATE.maintenance.projection },
      },
      runtime: { ...DEFAULT_FORM_STATE.runtime },
    };
  }

  const userMemory = asObject(config.user_memory);
  const skillLearning = asObject(config.skill_learning);
  const userMemoryEmbedding = asObject(userMemory.embedding);
  const userMemoryRetrieval = asObject(userMemory.retrieval);
  const userMemoryRerank = asObject(userMemoryRetrieval.rerank);
  const userMemoryPlanner = asObject(userMemoryRetrieval.planner);
  const userMemoryReflection = asObject(userMemoryRetrieval.reflection);
  const userMemoryExtraction = asObject(userMemory.extraction);
  const userMemoryConsolidation = asObject(userMemory.consolidation);
  const skillLearningExtraction = asObject(skillLearning.extraction);
  const skillLearningPublish = asObject(skillLearning.publish_policy);
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
      hybrid_enabled: asBoolean(userMemoryRetrieval.hybrid_enabled, true),
      similarity_threshold: asNumber(
        userMemoryRetrieval.similarity_threshold,
        0.3,
      ),
      rerank: {
        enabled: asBoolean(userMemoryRerank.enabled, true),
        provider: asString(userMemoryRerank.provider, ""),
        model: asString(userMemoryRerank.model, ""),
        top_k: asNumber(userMemoryRerank.top_k, 30),
        weight: asNumber(userMemoryRerank.weight, 0.75),
        timeout_seconds: asNumber(userMemoryRerank.timeout_seconds, 8),
        failure_backoff_seconds: asNumber(
          userMemoryRerank.failure_backoff_seconds,
          30,
        ),
        doc_max_chars: asNumber(userMemoryRerank.doc_max_chars, 1200),
      },
      planner: {
        runtime_mode: asString(userMemoryPlanner.runtime_mode, "light"),
        api_mode: asString(userMemoryPlanner.api_mode, "full"),
        provider: asString(userMemoryPlanner.provider, ""),
        model: asString(userMemoryPlanner.model, ""),
        timeout_seconds: asNumber(userMemoryPlanner.timeout_seconds, 4),
        failure_backoff_seconds: asNumber(
          userMemoryPlanner.failure_backoff_seconds,
          60,
        ),
        max_query_variants: asNumber(
          userMemoryPlanner.max_query_variants,
          3,
        ),
      },
      reflection: {
        enabled_api: asBoolean(userMemoryReflection.enabled_api, true),
        max_rounds: asNumber(userMemoryReflection.max_rounds, 1),
        min_results: asNumber(userMemoryReflection.min_results, 3),
        min_score: asNumber(userMemoryReflection.min_score, 0.45),
      },
    },
    fact_extraction: {
      provider: asString(userMemoryExtraction.provider, ""),
      model: asString(userMemoryExtraction.model, ""),
      timeout_seconds: asNumber(userMemoryExtraction.timeout_seconds, 120),
      max_facts: asNumber(userMemoryExtraction.max_facts, 10),
      max_preference_facts: asNumber(
        userMemoryExtraction.max_preference_facts,
        asNumber(userMemoryExtraction.max_facts, 10),
      ),
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
      provider: asString(skillLearningExtraction.provider, ""),
      model: asString(skillLearningExtraction.model, ""),
      timeout_seconds: asNumber(skillLearningExtraction.timeout_seconds, 120),
      max_proposals: asNumber(skillLearningExtraction.max_proposals, 6),
      failure_backoff_seconds: asNumber(
        skillLearningExtraction.failure_backoff_seconds,
        60,
      ),
      publish_skill_type: asString(
        skillLearningPublish.skill_type,
        "agent_skill",
      ),
      publish_storage_type: asString(
        skillLearningPublish.storage_type,
        "inline",
      ),
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
      projection: {
        enabled: asBoolean(userMemoryConsolidation.enabled, true),
        run_on_startup: asBoolean(userMemoryConsolidation.run_on_startup, true),
        startup_delay_seconds: asNumber(
          userMemoryConsolidation.startup_delay_seconds,
          180,
        ),
        interval_seconds: asNumber(
          userMemoryConsolidation.interval_seconds,
          21600,
        ),
        limit: asNumber(userMemoryConsolidation.limit, 5000),
        dry_run: asBoolean(userMemoryConsolidation.dry_run, false),
      },
    },
    runtime: {
      enable_user_memory: asBoolean(runtime.enable_user_memory, true),
      enable_skills: asBoolean(runtime.enable_skills, true),
      enable_knowledge_base: asBoolean(runtime.enable_knowledge_base, true),
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
        hybrid_enabled: formState.retrieval.hybrid_enabled,
        similarity_threshold: Math.max(
          0,
          formState.retrieval.similarity_threshold,
        ),
        rerank: {
          enabled: formState.retrieval.rerank.enabled,
          provider: formState.retrieval.rerank.provider.trim(),
          model: formState.retrieval.rerank.model.trim(),
          top_k: Math.max(1, Math.floor(formState.retrieval.rerank.top_k)),
          weight: Math.max(0, Math.min(1, formState.retrieval.rerank.weight)),
          timeout_seconds: Math.max(
            1,
            formState.retrieval.rerank.timeout_seconds,
          ),
          failure_backoff_seconds: Math.max(
            1,
            Math.floor(formState.retrieval.rerank.failure_backoff_seconds),
          ),
          doc_max_chars: Math.max(
            256,
            Math.floor(formState.retrieval.rerank.doc_max_chars),
          ),
        },
        planner: {
          runtime_mode: formState.retrieval.planner.runtime_mode.trim() || "light",
          api_mode: formState.retrieval.planner.api_mode.trim() || "full",
          provider: formState.retrieval.planner.provider.trim(),
          model: formState.retrieval.planner.model.trim(),
          timeout_seconds: Math.max(
            1,
            formState.retrieval.planner.timeout_seconds,
          ),
          failure_backoff_seconds: Math.max(
            1,
            Math.floor(formState.retrieval.planner.failure_backoff_seconds),
          ),
          max_query_variants: Math.max(
            1,
            Math.floor(formState.retrieval.planner.max_query_variants),
          ),
        },
        reflection: {
          enabled_api: formState.retrieval.reflection.enabled_api,
          max_rounds: Math.max(
            0,
            Math.floor(formState.retrieval.reflection.max_rounds),
          ),
          min_results: Math.max(
            1,
            Math.floor(formState.retrieval.reflection.min_results),
          ),
          min_score: Math.max(
            0,
            Math.min(1, formState.retrieval.reflection.min_score),
          ),
        },
      },
      extraction: {
        provider: formState.fact_extraction.provider.trim(),
        model: formState.fact_extraction.model.trim(),
        timeout_seconds: Math.max(
          0.5,
          formState.fact_extraction.timeout_seconds,
        ),
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
        enabled: formState.maintenance.projection.enabled,
        run_on_startup: formState.maintenance.projection.run_on_startup,
        startup_delay_seconds: Math.max(
          0,
          Math.floor(
            formState.maintenance.projection.startup_delay_seconds,
          ),
        ),
        interval_seconds: Math.max(
          60,
          Math.floor(formState.maintenance.projection.interval_seconds),
        ),
        limit: Math.max(
          1,
          Math.floor(formState.maintenance.projection.limit),
        ),
        dry_run: formState.maintenance.projection.dry_run,
      },
    },
    skill_learning: {
      extraction: {
        provider: formState.skill_learning.provider.trim(),
        model: formState.skill_learning.model.trim(),
        timeout_seconds: Math.max(
          0.5,
          formState.skill_learning.timeout_seconds,
        ),
        max_proposals: Math.max(
          1,
          Math.floor(formState.skill_learning.max_proposals),
        ),
        failure_backoff_seconds: Math.max(
          1,
          Math.floor(formState.skill_learning.failure_backoff_seconds),
        ),
      },
      publish_policy: {
        skill_type:
          formState.skill_learning.publish_skill_type.trim() || "agent_skill",
        storage_type:
          formState.skill_learning.publish_storage_type.trim() || "inline",
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

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    setTypedModelsByProvider({});
    setLoadingModelMetadataByProvider({});

    const loadConfig = async () => {
      setIsLoading(true);
      try {
        const data = await memoryWorkbenchApi.getConfig();
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

  const getCompatibleModelsForType = useCallback(
    (provider: string, modelType: ModelType): string[] => {
      if (!provider) {
        return [];
      }
      const cached = typedModelsByProvider[provider]?.[modelType];
      if (cached) {
        return cached;
      }
      return selectModelsByType(availableProviders[provider] || [], {}, modelType);
    },
    [availableProviders, typedModelsByProvider],
  );

  const providerOptionsByType = useMemo<ProviderOptionsByType>(
    () => ({
      embedding: providerOptions.filter(
        (provider) => getCompatibleModelsForType(provider, "embedding").length > 0,
      ),
      generation: providerOptions.filter(
        (provider) => getCompatibleModelsForType(provider, "generation").length > 0,
      ),
      rerank: providerOptions.filter(
        (provider) => getCompatibleModelsForType(provider, "rerank").length > 0,
      ),
    }),
    [getCompatibleModelsForType, providerOptions],
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
            generation: [],
            rerank: [],
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
            generation: selectModelsByType(
              providerModels,
              modelsMetadata,
              "generation",
            ),
            rerank: selectModelsByType(
              providerModels,
              modelsMetadata,
              "rerank",
            ),
          },
        }));
      } catch {
        setTypedModelsByProvider((prev) => ({
          ...prev,
          [provider]: {
            embedding: selectModelsByType(providerModels, {}, "embedding"),
            generation: selectModelsByType(providerModels, {}, "generation"),
            rerank: selectModelsByType(providerModels, {}, "rerank"),
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
    if (!formState.fact_extraction.provider) {
      return;
    }
    void ensureProviderTypedModels(formState.fact_extraction.provider);
  }, [ensureProviderTypedModels, formState.fact_extraction.provider]);

  useEffect(() => {
    if (!formState.retrieval.rerank.provider) {
      return;
    }
    void ensureProviderTypedModels(formState.retrieval.rerank.provider);
  }, [ensureProviderTypedModels, formState.retrieval.rerank.provider]);

  useEffect(() => {
    if (!formState.retrieval.planner.provider) {
      return;
    }
    void ensureProviderTypedModels(formState.retrieval.planner.provider);
  }, [ensureProviderTypedModels, formState.retrieval.planner.provider]);

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
    return getCompatibleModelsForType(formState.embedding.provider, "embedding");
  }, [formState.embedding.provider, getCompatibleModelsForType]);

  const factExtractionModels = useMemo(() => {
    if (!formState.fact_extraction.provider) {
      return [];
    }
    return getCompatibleModelsForType(formState.fact_extraction.provider, "generation");
  }, [formState.fact_extraction.provider, getCompatibleModelsForType]);

  const rerankModels = useMemo(() => {
    if (!formState.retrieval.rerank.provider) {
      return [];
    }
    return getCompatibleModelsForType(formState.retrieval.rerank.provider, "rerank");
  }, [formState.retrieval.rerank.provider, getCompatibleModelsForType]);

  const plannerModels = useMemo(() => {
    if (!formState.retrieval.planner.provider) {
      return [];
    }
    return getCompatibleModelsForType(formState.retrieval.planner.provider, "generation");
  }, [formState.retrieval.planner.provider, getCompatibleModelsForType]);

  const skillLearningModels = useMemo(() => {
    if (!formState.skill_learning.provider) {
      return [];
    }
    return getCompatibleModelsForType(formState.skill_learning.provider, "generation");
  }, [formState.skill_learning.provider, getCompatibleModelsForType]);

  const plannerConfigEnabled =
    formState.retrieval.planner.runtime_mode === "full" ||
    formState.retrieval.planner.api_mode === "full";

  const isEmbeddingModelsLoading = Boolean(
    formState.embedding.provider &&
    loadingModelMetadataByProvider[formState.embedding.provider],
  );
  const isFactExtractionModelsLoading = Boolean(
    formState.fact_extraction.provider &&
    loadingModelMetadataByProvider[formState.fact_extraction.provider],
  );
  const isRerankModelsLoading = Boolean(
    formState.retrieval.rerank.provider &&
    loadingModelMetadataByProvider[formState.retrieval.rerank.provider],
  );
  const isPlannerModelsLoading = Boolean(
    formState.retrieval.planner.provider &&
    loadingModelMetadataByProvider[formState.retrieval.planner.provider],
  );
  const isSkillLearningModelsLoading = Boolean(
    formState.skill_learning.provider &&
    loadingModelMetadataByProvider[formState.skill_learning.provider],
  );

  const embeddingModelMissing =
    Boolean(formState.embedding.model) &&
    !embeddingModels.includes(formState.embedding.model);
  const factExtractionModelMissing =
    Boolean(formState.fact_extraction.model) &&
    !factExtractionModels.includes(formState.fact_extraction.model);
  const rerankModelMissing =
    Boolean(formState.retrieval.rerank.model) &&
    !rerankModels.includes(formState.retrieval.rerank.model);
  const plannerModelMissing =
    Boolean(formState.retrieval.planner.model) &&
    !plannerModels.includes(formState.retrieval.planner.model);
  const skillLearningModelMissing =
    Boolean(formState.skill_learning.model) &&
    !skillLearningModels.includes(formState.skill_learning.model);

  const applyRecommended = () => {
    const recommendedRoot = asObject(config?.recommended);
    const recommendedUserMemory = asObject(recommendedRoot.user_memory);
    const recommendedEmbedding = asObject(recommendedUserMemory.embedding);
    const recommendedRetrieval = asObject(recommendedUserMemory.retrieval);
    const recommendedFactExtraction = asObject(
      recommendedUserMemory.extraction,
    );
    const recommendedConsolidation = asObject(
      recommendedUserMemory.consolidation,
    );
    const recommendedSkillLearning = asObject(recommendedRoot.skill_learning);
    const recommendedSkillExtraction = asObject(
      recommendedSkillLearning.extraction,
    );
    const recommendedSkillPublish = asObject(
      recommendedSkillLearning.publish_policy,
    );
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
        hybrid_enabled: asBoolean(
          recommendedRetrieval.hybrid_enabled,
          prev.retrieval.hybrid_enabled,
        ),
        similarity_threshold: asNumber(
          recommendedRetrieval.similarity_threshold,
          prev.retrieval.similarity_threshold,
        ),
        rerank: {
          ...prev.retrieval.rerank,
          ...asObject(recommendedRetrieval.rerank),
        },
        planner: {
          ...prev.retrieval.planner,
          ...asObject(recommendedRetrieval.planner),
        },
        reflection: {
          ...prev.retrieval.reflection,
          ...asObject(recommendedRetrieval.reflection),
        },
      },
      fact_extraction: {
        ...prev.fact_extraction,
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
        provider: asString(
          recommendedSkillExtraction.provider,
          prev.skill_learning.provider,
        ),
        model: asString(
          recommendedSkillExtraction.model,
          prev.skill_learning.model,
        ),
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
        projection: {
          ...prev.maintenance.projection,
          enabled: asBoolean(
            recommendedConsolidation.enabled,
            prev.maintenance.projection.enabled,
          ),
          run_on_startup: asBoolean(
            recommendedConsolidation.run_on_startup,
            prev.maintenance.projection.run_on_startup,
          ),
          startup_delay_seconds: asNumber(
            recommendedConsolidation.startup_delay_seconds,
            prev.maintenance.projection.startup_delay_seconds,
          ),
          interval_seconds: asNumber(
            recommendedConsolidation.interval_seconds,
            prev.maintenance.projection.interval_seconds,
          ),
          limit: asNumber(
            recommendedConsolidation.limit,
            prev.maintenance.projection.limit,
          ),
          dry_run: asBoolean(
            recommendedConsolidation.dry_run,
            prev.maintenance.projection.dry_run,
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
      },
    }));

    toast.success(
      t("memory.config.applyRecommendedSuccess", "Recommended values applied"),
    );
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const payload = toUpdatePayload(formState);
      const updated = await memoryWorkbenchApi.updateConfig(payload);
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
    const candidates = getCompatibleModelsForType(provider, "embedding");
    setFormState((prev) => ({
      ...prev,
      embedding: {
        ...prev.embedding,
        provider,
        model: candidates[0] || "",
      },
    }));
  };

  const handleFactExtractionProviderChange = (provider: string) => {
    void ensureProviderTypedModels(provider);
    const candidates = getCompatibleModelsForType(provider, "generation");
    setFormState((prev) => ({
      ...prev,
      fact_extraction: {
        ...prev.fact_extraction,
        provider,
        model: candidates[0] || "",
      },
    }));
  };

  const handleRerankProviderChange = (provider: string) => {
    void ensureProviderTypedModels(provider);
    const candidates = getCompatibleModelsForType(provider, "rerank");
    setFormState((prev) => ({
      ...prev,
      retrieval: {
        ...prev.retrieval,
        rerank: {
          ...prev.retrieval.rerank,
          provider,
          model: candidates[0] || "",
        },
      },
    }));
  };

  const handlePlannerProviderChange = (provider: string) => {
    void ensureProviderTypedModels(provider);
    const candidates = getCompatibleModelsForType(provider, "generation");
    setFormState((prev) => ({
      ...prev,
      retrieval: {
        ...prev.retrieval,
        planner: {
          ...prev.retrieval.planner,
          provider,
          model: candidates[0] || "",
        },
      },
    }));
  };

  const handleSkillLearningProviderChange = (provider: string) => {
    void ensureProviderTypedModels(provider);
    const candidates = getCompatibleModelsForType(provider, "generation");
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
    const provider = formState.retrieval.rerank.provider;
    if (!provider || rerankModels.length === 0) {
      return;
    }
    if (
      formState.retrieval.rerank.model &&
      rerankModels.includes(formState.retrieval.rerank.model)
    ) {
      return;
    }
    setFormState((prev) => ({
      ...prev,
      retrieval: {
        ...prev.retrieval,
        rerank: {
          ...prev.retrieval.rerank,
          model: rerankModels[0] || "",
        },
      },
    }));
  }, [
    formState.retrieval.rerank.model,
    formState.retrieval.rerank.provider,
    rerankModels,
  ]);

  useEffect(() => {
    const provider = formState.retrieval.planner.provider;
    if (!provider || plannerModels.length === 0) {
      return;
    }
    if (
      formState.retrieval.planner.model &&
      plannerModels.includes(formState.retrieval.planner.model)
    ) {
      return;
    }
    setFormState((prev) => ({
      ...prev,
      retrieval: {
        ...prev.retrieval,
        planner: {
          ...prev.retrieval.planner,
          model: plannerModels[0] || "",
        },
      },
    }));
  }, [
    formState.retrieval.planner.model,
    formState.retrieval.planner.provider,
    plannerModels,
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
                  "Memory Pipeline Configuration",
                )}
              </h2>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                {t(
                  "memory.config.editorSubtitle",
                  "Configure user-memory retrieval and extraction, skill learning, session-ledger retention, and runtime context sources.",
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
                    {providerOptionsByType.embedding.map((provider) => (
                      <option key={provider} value={provider}>
                        {provider}
                      </option>
                    ))}
                  </select>
                  <span className="mt-1 block text-xs text-zinc-500 dark:text-zinc-400">
                    {t(
                      "memory.config.embeddingHint",
                      "Choose the embedding provider/model used to write and query user-memory vectors. Only embedding-capable providers are listed.",
                    )}
                  </span>
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
              <div className="mb-3">
                <h3 className="text-base font-semibold text-zinc-800 dark:text-zinc-100">
                  {t("memory.config.retrieval", "Retrieval")}
                </h3>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                  {t(
                    "memory.config.retrievalHint",
                    "Configure the live hybrid retrieval pipeline used by user-memory runtime and API search.",
                  )}
                </p>
              </div>

              <p className="mb-3 rounded-lg border border-emerald-200/80 bg-emerald-50/80 px-3 py-2 text-xs text-emerald-800 dark:border-emerald-800/70 dark:bg-emerald-950/30 dark:text-emerald-200">
                {t(
                  "memory.config.retrievalEffectiveHint",
                  "These controls are wired into the current user-memory hybrid retrieval path, including rerank, planner, and reflection.",
                )}
              </p>

              <div className="space-y-4">
                <label className="inline-flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                  <input
                    type="checkbox"
                    checked={formState.retrieval.hybrid_enabled}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
                        retrieval: {
                          ...prev.retrieval,
                          hybrid_enabled: event.target.checked,
                        },
                      }))
                    }
                    className="rounded"
                  />
                  {t(
                    "memory.config.hybridEnabled",
                    "Enable Hybrid Retrieval",
                  )}
                </label>

                <label className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="block mb-1">
                    {t("memory.config.similarityThreshold", "Similarity Threshold")}
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
                      "Final floor for memory recall. Lower improves recall; higher improves precision.",
                    )}
                  </span>
                </label>

                <div className="rounded-lg border border-zinc-200/80 dark:border-zinc-700/80 p-3">
                  <div className="mb-3">
                    <h4 className="text-sm font-semibold text-zinc-800 dark:text-zinc-100">
                      {t("memory.config.rerankTitle", "Rerank")}
                    </h4>
                    <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                      {t(
                        "memory.config.rerankHint",
                        "Model-based reranking after hybrid candidate merge.",
                      )}
                    </p>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <label className="inline-flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300 md:col-span-3">
                      <input
                        type="checkbox"
                        checked={formState.retrieval.rerank.enabled}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            retrieval: {
                              ...prev.retrieval,
                              rerank: {
                                ...prev.retrieval.rerank,
                                enabled: event.target.checked,
                              },
                            },
                          }))
                        }
                        className="rounded"
                      />
                      {t("memory.config.rerankEnabled", "Enable Rerank")}
                    </label>

                    <label className="text-sm text-zinc-700 dark:text-zinc-300">
                      <span className="block mb-1">
                        {t("memory.config.provider", "Provider")}
                      </span>
                      <select
                        value={formState.retrieval.rerank.provider}
                        onChange={(event) =>
                          handleRerankProviderChange(event.target.value)
                        }
                        className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                      >
                        <option value="">{t("memory.config.none", "None")}</option>
                        {providerOptionsByType.rerank.map((provider) => (
                          <option key={provider} value={provider}>
                            {provider}
                          </option>
                        ))}
                      </select>
                      <span className="mt-1 block text-xs text-zinc-500 dark:text-zinc-400">
                        {t(
                          "memory.config.rerankProviderHint",
                          "Only providers that expose rerank models are listed here.",
                        )}
                      </span>
                    </label>

                    <label className="text-sm text-zinc-700 dark:text-zinc-300">
                      <span className="block mb-1">
                        {t("memory.config.model", "Model")}
                      </span>
                      <select
                        value={formState.retrieval.rerank.model}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            retrieval: {
                              ...prev.retrieval,
                              rerank: {
                                ...prev.retrieval.rerank,
                                model: event.target.value,
                              },
                            },
                          }))
                        }
                        disabled={!formState.retrieval.rerank.provider}
                        className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                      >
                        {!formState.retrieval.rerank.provider ? (
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
                          <option value={formState.retrieval.rerank.model}>
                            {t("memory.config.currentModel", "Current")}:{" "}
                            {formState.retrieval.rerank.model}
                          </option>
                        )}
                        {rerankModels.map((model) => (
                          <option key={model} value={model}>
                            {model}
                          </option>
                        ))}
                      </select>
                      <span className="mt-1 block text-xs text-zinc-500 dark:text-zinc-400">
                        {t(
                          "memory.config.rerankModelHint",
                          "Choose a rerank model, not a chat or embedding model.",
                        )}
                      </span>
                    </label>

                    <label className="text-sm text-zinc-700 dark:text-zinc-300">
                      <span className="block mb-1">
                        {t("memory.config.rerankTopK", "Rerank Top K")}
                      </span>
                      <input
                        type="number"
                        min={1}
                        value={formState.retrieval.rerank.top_k}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            retrieval: {
                              ...prev.retrieval,
                              rerank: {
                                ...prev.retrieval.rerank,
                                top_k: asNumber(
                                  event.target.value,
                                  prev.retrieval.rerank.top_k,
                                ),
                              },
                            },
                          }))
                        }
                        className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                      />
                      <span className="mt-1 block text-xs text-zinc-500 dark:text-zinc-400">
                        {t(
                          "memory.config.rerankTopKHint",
                          "How many merged candidates enter the reranker.",
                        )}
                      </span>
                    </label>

                    <label className="text-sm text-zinc-700 dark:text-zinc-300">
                      <span className="block mb-1">
                        {t("memory.config.rerankWeight", "Rerank Weight")}
                      </span>
                      <input
                        type="number"
                        min={0}
                        max={1}
                        step="0.01"
                        value={formState.retrieval.rerank.weight}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            retrieval: {
                              ...prev.retrieval,
                              rerank: {
                                ...prev.retrieval.rerank,
                                weight: asNumber(
                                  event.target.value,
                                  prev.retrieval.rerank.weight,
                                ),
                              },
                            },
                          }))
                        }
                        className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                      />
                      <span className="mt-1 block text-xs text-zinc-500 dark:text-zinc-400">
                        {t(
                          "memory.config.rerankWeightHint",
                          "How strongly rerank scores influence the final blended score.",
                        )}
                      </span>
                    </label>

                    <label className="text-sm text-zinc-700 dark:text-zinc-300">
                      <span className="block mb-1">
                        {t("memory.config.timeoutSeconds", "Timeout (s)")}
                      </span>
                      <input
                        type="number"
                        min={1}
                        step="1"
                        value={formState.retrieval.rerank.timeout_seconds}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            retrieval: {
                              ...prev.retrieval,
                              rerank: {
                                ...prev.retrieval.rerank,
                                timeout_seconds: asNumber(
                                  event.target.value,
                                  prev.retrieval.rerank.timeout_seconds,
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
                        {t(
                          "memory.config.failureBackoffSeconds",
                          "Failure Backoff (s)",
                        )}
                      </span>
                      <input
                        type="number"
                        min={1}
                        step="1"
                        value={formState.retrieval.rerank.failure_backoff_seconds}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            retrieval: {
                              ...prev.retrieval,
                              rerank: {
                                ...prev.retrieval.rerank,
                                failure_backoff_seconds: asNumber(
                                  event.target.value,
                                  prev.retrieval.rerank.failure_backoff_seconds,
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
                        {t("memory.config.docMaxChars", "Document Max Chars")}
                      </span>
                      <input
                        type="number"
                        min={256}
                        step="1"
                        value={formState.retrieval.rerank.doc_max_chars}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            retrieval: {
                              ...prev.retrieval,
                              rerank: {
                                ...prev.retrieval.rerank,
                                doc_max_chars: asNumber(
                                  event.target.value,
                                  prev.retrieval.rerank.doc_max_chars,
                                ),
                              },
                            },
                          }))
                        }
                        className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                      />
                      <span className="mt-1 block text-xs text-zinc-500 dark:text-zinc-400">
                        {t(
                          "memory.config.docMaxCharsHint",
                          "Maximum text length sent per candidate to the reranker.",
                        )}
                      </span>
                    </label>
                  </div>
                </div>

                <div className="rounded-lg border border-zinc-200/80 dark:border-zinc-700/80 p-3">
                  <div className="mb-3">
                    <h4 className="text-sm font-semibold text-zinc-800 dark:text-zinc-100">
                      {t("memory.config.plannerTitle", "Planner")}
                    </h4>
                    <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                      {t(
                        "memory.config.plannerHint",
                        "Planner decides how to expand a query before retrieval. Runtime light mode uses rules only; full mode adds one generation-model call to produce query variants and structured filters.",
                      )}
                    </p>
                  </div>

                  <p className="mb-3 rounded-lg border border-sky-200/80 bg-sky-50/80 px-3 py-2 text-xs text-sky-800 dark:border-sky-800/70 dark:bg-sky-950/30 dark:text-sky-200">
                    {t(
                      "memory.config.plannerExplain",
                      "Use light when you want low latency and predictable behavior. Use full when you want stronger recall and can afford one extra chat-model call.",
                    )}
                  </p>

                  {!plannerConfigEnabled && (
                    <p className="mb-3 rounded-lg border border-amber-200/80 bg-amber-50/80 px-3 py-2 text-xs text-amber-800 dark:border-amber-800/70 dark:bg-amber-950/30 dark:text-amber-200">
                      {t(
                        "memory.config.plannerModeDisabledHint",
                        "Planner provider/model settings are only used when runtime mode or API mode is set to full.",
                      )}
                    </p>
                  )}

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <label className="text-sm text-zinc-700 dark:text-zinc-300">
                      <span className="block mb-1">
                        {t("memory.config.runtimeMode", "Runtime Mode")}
                      </span>
                      <select
                        value={formState.retrieval.planner.runtime_mode}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            retrieval: {
                              ...prev.retrieval,
                              planner: {
                                ...prev.retrieval.planner,
                                runtime_mode: event.target.value,
                              },
                            },
                          }))
                        }
                        className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                      >
                        <option value="light">
                          {t("memory.config.plannerModeLight", "Light (rules only)")}
                        </option>
                        <option value="full">
                          {t("memory.config.plannerModeFull", "Full (LLM planner)")}
                        </option>
                      </select>
                      <span className="mt-1 block text-xs text-zinc-500 dark:text-zinc-400">
                        {t(
                          "memory.config.runtimeModeHint",
                          "Agent runtime should usually stay on light to avoid adding extra model latency.",
                        )}
                      </span>
                    </label>

                    <label className="text-sm text-zinc-700 dark:text-zinc-300">
                      <span className="block mb-1">
                        {t("memory.config.apiMode", "API Mode")}
                      </span>
                      <select
                        value={formState.retrieval.planner.api_mode}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            retrieval: {
                              ...prev.retrieval,
                              planner: {
                                ...prev.retrieval.planner,
                                api_mode: event.target.value,
                              },
                            },
                          }))
                        }
                        className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                      >
                        <option value="light">
                          {t("memory.config.plannerModeLight", "Light (rules only)")}
                        </option>
                        <option value="full">
                          {t("memory.config.plannerModeFull", "Full (LLM planner)")}
                        </option>
                      </select>
                      <span className="mt-1 block text-xs text-zinc-500 dark:text-zinc-400">
                        {t(
                          "memory.config.apiModeHint",
                          "API search can use full mode when you want better recall and can afford one extra model call.",
                        )}
                      </span>
                    </label>

                    <label className="text-sm text-zinc-700 dark:text-zinc-300">
                      <span className="block mb-1">
                        {t(
                          "memory.config.maxQueryVariants",
                          "Max Query Variants",
                        )}
                      </span>
                      <input
                        type="number"
                        min={1}
                        value={formState.retrieval.planner.max_query_variants}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            retrieval: {
                              ...prev.retrieval,
                              planner: {
                                ...prev.retrieval.planner,
                                max_query_variants: asNumber(
                                  event.target.value,
                                  prev.retrieval.planner.max_query_variants,
                                ),
                              },
                            },
                          }))
                        }
                        disabled={!plannerConfigEnabled}
                        className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                      />
                      <span className="mt-1 block text-xs text-zinc-500 dark:text-zinc-400">
                        {t(
                          "memory.config.maxQueryVariantsHint",
                          "Upper bound for planner-generated search rewrites in full mode.",
                        )}
                      </span>
                    </label>

                    <label className="text-sm text-zinc-700 dark:text-zinc-300">
                      <span className="block mb-1">
                        {t("memory.config.provider", "Provider")}
                      </span>
                      <select
                        value={formState.retrieval.planner.provider}
                        onChange={(event) =>
                          handlePlannerProviderChange(event.target.value)
                        }
                        disabled={!plannerConfigEnabled}
                        className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                      >
                        <option value="">{t("memory.config.none", "None")}</option>
                        {providerOptionsByType.generation.map((provider) => (
                          <option key={provider} value={provider}>
                            {provider}
                          </option>
                        ))}
                      </select>
                      <span className="mt-1 block text-xs text-zinc-500 dark:text-zinc-400">
                        {t(
                          "memory.config.plannerProviderHint",
                          "Only providers with chat/generation models are listed here. Embedding and rerank models cannot be used as planner models.",
                        )}
                      </span>
                    </label>

                    <label className="text-sm text-zinc-700 dark:text-zinc-300">
                      <span className="block mb-1">
                        {t("memory.config.model", "Model")}
                      </span>
                      <select
                        value={formState.retrieval.planner.model}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            retrieval: {
                              ...prev.retrieval,
                              planner: {
                                ...prev.retrieval.planner,
                                model: event.target.value,
                              },
                            },
                          }))
                        }
                        disabled={
                          !plannerConfigEnabled ||
                          !formState.retrieval.planner.provider
                        }
                        className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                      >
                        {!formState.retrieval.planner.provider ? (
                          <option value="">
                            {t(
                              "memory.config.selectProviderFirst",
                              "Select provider first",
                            )}
                          </option>
                        ) : isPlannerModelsLoading ? (
                          <option value="">
                            {t("memory.config.loadingModels", "Loading models")}
                          </option>
                        ) : plannerModels.length === 0 ? (
                          <option value="">
                            {t("memory.config.noModels", "No models available")}
                          </option>
                        ) : null}
                        {plannerModelMissing && (
                          <option value={formState.retrieval.planner.model}>
                            {t("memory.config.currentModel", "Current")}:{" "}
                            {formState.retrieval.planner.model}
                          </option>
                        )}
                        {plannerModels.map((model) => (
                          <option key={model} value={model}>
                            {model}
                          </option>
                        ))}
                      </select>
                      <span className="mt-1 block text-xs text-zinc-500 dark:text-zinc-400">
                        {t(
                          "memory.config.plannerModelHint",
                          "Choose a chat/generation model that can reliably follow structured instructions.",
                        )}
                      </span>
                    </label>

                    <label className="text-sm text-zinc-700 dark:text-zinc-300">
                      <span className="block mb-1">
                        {t("memory.config.timeoutSeconds", "Timeout (s)")}
                      </span>
                      <input
                        type="number"
                        min={1}
                        step="1"
                        value={formState.retrieval.planner.timeout_seconds}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            retrieval: {
                              ...prev.retrieval,
                              planner: {
                                ...prev.retrieval.planner,
                                timeout_seconds: asNumber(
                                  event.target.value,
                                  prev.retrieval.planner.timeout_seconds,
                                ),
                              },
                            },
                          }))
                        }
                        disabled={!plannerConfigEnabled}
                        className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                      />
                    </label>

                    <label className="text-sm text-zinc-700 dark:text-zinc-300">
                      <span className="block mb-1">
                        {t(
                          "memory.config.failureBackoffSeconds",
                          "Failure Backoff (s)",
                        )}
                      </span>
                      <input
                        type="number"
                        min={1}
                        step="1"
                        value={formState.retrieval.planner.failure_backoff_seconds}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            retrieval: {
                              ...prev.retrieval,
                              planner: {
                                ...prev.retrieval.planner,
                                failure_backoff_seconds: asNumber(
                                  event.target.value,
                                  prev.retrieval.planner.failure_backoff_seconds,
                                ),
                              },
                            },
                          }))
                        }
                        disabled={!plannerConfigEnabled}
                        className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                      />
                    </label>
                  </div>
                </div>

                <div className="rounded-lg border border-zinc-200/80 dark:border-zinc-700/80 p-3">
                  <div className="mb-3">
                    <h4 className="text-sm font-semibold text-zinc-800 dark:text-zinc-100">
                      {t("memory.config.reflectionTitle", "Reflection")}
                    </h4>
                    <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                      {t(
                        "memory.config.reflectionHint",
                        "Optional second-pass search expansion for API retrieval.",
                      )}
                    </p>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                    <label className="inline-flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300 md:col-span-4">
                      <input
                        type="checkbox"
                        checked={formState.retrieval.reflection.enabled_api}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            retrieval: {
                              ...prev.retrieval,
                              reflection: {
                                ...prev.retrieval.reflection,
                                enabled_api: event.target.checked,
                              },
                            },
                          }))
                        }
                        className="rounded"
                      />
                      {t(
                        "memory.config.reflectionEnabledApi",
                        "Enable Reflection For API Search",
                      )}
                    </label>

                    <label className="text-sm text-zinc-700 dark:text-zinc-300">
                      <span className="block mb-1">
                        {t("memory.config.maxRounds", "Max Rounds")}
                      </span>
                      <input
                        type="number"
                        min={0}
                        value={formState.retrieval.reflection.max_rounds}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            retrieval: {
                              ...prev.retrieval,
                              reflection: {
                                ...prev.retrieval.reflection,
                                max_rounds: asNumber(
                                  event.target.value,
                                  prev.retrieval.reflection.max_rounds,
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
                        {t("memory.config.minResults", "Min Results")}
                      </span>
                      <input
                        type="number"
                        min={1}
                        value={formState.retrieval.reflection.min_results}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            retrieval: {
                              ...prev.retrieval,
                              reflection: {
                                ...prev.retrieval.reflection,
                                min_results: asNumber(
                                  event.target.value,
                                  prev.retrieval.reflection.min_results,
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
                        {t("memory.config.minScore", "Min Score")}
                      </span>
                      <input
                        type="number"
                        min={0}
                        max={1}
                        step="0.01"
                        value={formState.retrieval.reflection.min_score}
                        onChange={(event) =>
                          setFormState((prev) => ({
                            ...prev,
                            retrieval: {
                              ...prev.retrieval,
                              reflection: {
                                ...prev.retrieval.reflection,
                                min_score: asNumber(
                                  event.target.value,
                                  prev.retrieval.reflection.min_score,
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

            <div className="rounded-xl border border-zinc-200/80 dark:border-zinc-700/80 bg-white/60 dark:bg-zinc-900/50 p-4">
              <div className="mb-3">
                <h3 className="text-base font-semibold text-zinc-800 dark:text-zinc-100">
                  {t("memory.config.runtimeTitle", "Runtime Context")}
                </h3>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                  {t(
                    "memory.config.runtimeHint",
                    "Control which context sources are injected into the runtime prompt assembler.",
                  )}
                </p>
              </div>

              <p className="mb-3 rounded-lg border border-emerald-200/80 bg-emerald-50/80 px-3 py-2 text-xs text-emerald-800 dark:border-emerald-800/70 dark:bg-emerald-950/30 dark:text-emerald-200">
                {t(
                  "memory.config.runtimeEffectiveHint",
                  "These three source toggles are wired into the runtime context path.",
                )}
              </p>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
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
                  {t(
                    "memory.config.enableKnowledgeBase",
                    "Enable Knowledge Base",
                  )}
                </label>
              </div>
            </div>

            <div className="rounded-xl border border-zinc-200/80 dark:border-zinc-700/80 bg-white/60 dark:bg-zinc-900/50 p-4">
              <div className="mb-3">
                <h3 className="text-base font-semibold text-zinc-800 dark:text-zinc-100">
                  {t("memory.config.factExtraction", "User Memory Extraction")}
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

              <p className="mt-3 rounded-lg border border-emerald-200/80 bg-emerald-50/80 px-3 py-2 text-xs text-emerald-800 dark:border-emerald-800/70 dark:bg-emerald-950/30 dark:text-emerald-200">
                {t(
                  "memory.config.factExtractionEffectiveHint",
                  "These settings are active on the main pipeline. Provider/model, timeout, backoff, max user facts, heuristic fallback, and secondary recall all affect session extraction. Max Facts currently works as a fallback cap when Max User Facts is unset.",
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
                    {providerOptionsByType.generation.map((provider) => (
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

              <p className="mb-3 rounded-lg border border-sky-200/80 bg-sky-50/80 px-3 py-2 text-xs text-sky-800 dark:border-sky-800/70 dark:bg-sky-950/30 dark:text-sky-200">
                {t(
                  "memory.config.skillLearningEffectiveHint",
                  "Proposal extraction settings below are active, and publish settings apply when an approved proposal is manually published into the skill registry.",
                )}
              </p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <label className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="block mb-1">
                    {t("memory.config.provider", "Provider")}
                  </span>
                  <select
                    value={formState.skill_learning.provider}
                    onChange={(event) =>
                      handleSkillLearningProviderChange(event.target.value)
                    }
                    className="w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60"
                  >
                    <option value="">{t("memory.config.none", "None")}</option>
                    {providerOptionsByType.generation.map((provider) => (
                      <option key={provider} value={provider}>
                        {provider}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="block mb-1">
                    {t("memory.config.maxSkillProposals", "Max Skill Proposals")}
                  </span>
                  <input
                    type="number"
                    min={1}
                    value={formState.skill_learning.max_proposals}
                    onChange={(event) =>
                      setFormState((prev) => ({
                        ...prev,
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
                  <span className="mt-1 block text-xs text-zinc-500 dark:text-zinc-400">
                    {t(
                      "memory.config.maxSkillProposalsHint",
                      "Caps how many reusable skill proposals the session extractor can keep per flush.",
                    )}
                  </span>
                </label>
              </div>

              <label className="block text-sm text-zinc-700 dark:text-zinc-300 mt-3">
                <span className="block mb-1">
                  {t("memory.config.model", "Model")}
                </span>
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
                      {t(
                        "memory.config.selectProviderFirst",
                        "Select provider first",
                      )}
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
                      {t("memory.config.currentModel", "Current")}:{" "}
                      {formState.skill_learning.model}
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
                    {t(
                      "memory.config.factExtractionTimeout",
                      "Request Timeout (s)",
                    )}
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
                    {t(
                      "memory.config.factExtractionBackoff",
                      "Failure Backoff (s)",
                    )}
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
                  {t(
                    "memory.config.reuseExistingByName",
                    "Reuse existing published skill by name",
                  )}
                </label>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
                <label className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="block mb-1">
                    {t("memory.config.skillType", "Skill Type")}
                  </span>
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
                {config?.skill_learning?.extraction?.effective?.provider || "-"}{" "}
                / {config?.skill_learning?.extraction?.effective?.model || "-"}
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
                    "Session ledger keeps provenance for recent conversations only; durable entries and projections survive cleanup.",
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
                    "memory.config.projectionMaintenance",
                    "Consolidation",
                  )}
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <label className="inline-flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                    <input
                      type="checkbox"
                      checked={formState.maintenance.projection.enabled}
                      onChange={(event) =>
                        setFormState((prev) => ({
                          ...prev,
                          maintenance: {
                            ...prev.maintenance,
                            projection: {
                              ...prev.maintenance.projection,
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
                      checked={formState.maintenance.projection.dry_run}
                      onChange={(event) =>
                        setFormState((prev) => ({
                          ...prev,
                          maintenance: {
                            ...prev.maintenance,
                            projection: {
                              ...prev.maintenance.projection,
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
                      value={formState.maintenance.projection.interval_seconds}
                      onChange={(event) =>
                        setFormState((prev) => ({
                          ...prev,
                          maintenance: {
                            ...prev.maintenance,
                            projection: {
                              ...prev.maintenance.projection,
                              interval_seconds: asNumber(
                                event.target.value,
                                prev.maintenance.projection.interval_seconds,
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
                      value={formState.maintenance.projection.limit}
                      onChange={(event) =>
                        setFormState((prev) => ({
                          ...prev,
                          maintenance: {
                            ...prev.maintenance,
                            projection: {
                              ...prev.maintenance.projection,
                              limit: asNumber(
                                event.target.value,
                                prev.maintenance.projection.limit,
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
                      value={formState.maintenance.projection.startup_delay_seconds}
                      onChange={(event) =>
                        setFormState((prev) => ({
                          ...prev,
                          maintenance: {
                            ...prev.maintenance,
                            projection: {
                              ...prev.maintenance.projection,
                              startup_delay_seconds: asNumber(
                                event.target.value,
                                prev.maintenance.projection.startup_delay_seconds,
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
