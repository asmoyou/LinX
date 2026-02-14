import React, { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { X, Save, Loader2, Sparkles, SlidersHorizontal } from "lucide-react";
import toast from "react-hot-toast";
import { ModalPanel } from "@/components/ModalPanel";
import { knowledgeApi } from "@/api/knowledge";
import { llmApi } from "@/api/llm";
import type { KBConfigResponse } from "@/api/knowledge";

interface KBConfigPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

const isLikelyRerankModel = (model: string) =>
  /rerank|reranker|bge-reranker|jina-reranker|gte-rerank|cohere-rerank/i.test(
    model,
  );

const QUALITY_FIRST_DEFAULTS = {
  processing: {
    transcription: {
      enabled: true,
      engine: "funasr",
      provider: "",
      model: "iic/SenseVoiceSmall",
      language: "auto",
      funasr_service_url: "http://127.0.0.1:10095",
      funasr_service_timeout_seconds: 300,
      funasr_service_api_key: "",
    },
  },
  chunking: {
    strategy: "semantic",
    chunk_token_num: 512,
    overlap_percent: 10,
  },
  parsing: {
    method: "auto",
    vision_timeout_seconds: 120,
  },
  enrichment: {
    enabled: true,
    keywords_topn: 5,
    questions_topn: 3,
    generate_summary: true,
    temperature: 0.2,
    batch_size: 5,
    max_tokens: 0,
  },
  embedding: {
    dimension: 1024,
  },
  search: {
    max_concurrent_requests: 4,
    request_timeout_seconds: 30,
    enable_semantic: true,
    enable_fulltext: true,
    combine_results: true,
    semantic_weight: 0.7,
    fulltext_weight: 0.3,
    fusion_method: "rrf",
    rrf_k: 60,
    min_relevance_score: 0.3,
    hybrid_score_scale: 0.02,
    keyword_min_rank: 4.0,
    keyword_max_terms: 16,
    semantic_timeout_seconds: 8,
    embedding_failure_backoff_seconds: 30,
    rerank_enabled: true,
    rerank_weight: 0.85,
    rerank_top_k: 30,
    rerank_timeout_seconds: 10,
    rerank_failure_backoff_seconds: 60,
    rerank_doc_max_chars: 1600,
  },
};

const normalizeTranscriptionEngine = (engine?: string): string => {
  const normalized = String(engine || "")
    .trim()
    .toLowerCase();
  if (
    ["whisper", "local", "local_whisper", "local_funasr"].includes(normalized)
  ) {
    return "funasr";
  }
  if (["openai", "remote", "llm"].includes(normalized)) {
    return "openai_compatible";
  }
  return normalized || "funasr";
};

export const KBConfigPanel: React.FC<KBConfigPanelProps> = ({
  isOpen,
  onClose,
}) => {
  const { t } = useTranslation();
  const [config, setConfig] = useState<KBConfigResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Provider/model state
  const [availableProviders, setAvailableProviders] = useState<
    Record<string, string[]>
  >({});
  const [isLoadingProviders, setIsLoadingProviders] = useState(false);

  useEffect(() => {
    if (isOpen) {
      loadConfig();
      fetchProviders();
      setShowAdvanced(false);
    }
  }, [isOpen]);

  const loadConfig = async () => {
    setIsLoading(true);
    try {
      const data = await knowledgeApi.getConfig();
      setConfig(data);
    } catch {
      toast.error(t("kbConfig.loadFailed"));
    } finally {
      setIsLoading(false);
    }
  };

  const fetchProviders = async () => {
    setIsLoadingProviders(true);
    try {
      const providers = await llmApi.getAvailableProviders();
      setAvailableProviders(providers);
    } catch {
      // Non-critical
    } finally {
      setIsLoadingProviders(false);
    }
  };

  const handleSave = async () => {
    if (!config) return;
    setIsSaving(true);
    try {
      const updated = await knowledgeApi.updateConfig({
        processing: config.processing,
        chunking: config.chunking,
        parsing: config.parsing,
        enrichment: config.enrichment,
        embedding: config.embedding,
        search: config.search,
      });
      setConfig(updated);
      toast.success(t("kbConfig.saveSuccess"));
      onClose();
    } catch {
      toast.error(t("kbConfig.saveFailed"));
    } finally {
      setIsSaving(false);
    }
  };

  const updateChunking = (key: string, value: string | number) => {
    if (!config) return;
    setConfig({ ...config, chunking: { ...config.chunking, [key]: value } });
  };

  const updateParsing = (key: string, value: string | number) => {
    if (!config) return;
    setConfig({ ...config, parsing: { ...config.parsing, [key]: value } });
  };

  const updateTranscription = (
    key: string,
    value: string | number | boolean,
  ) => {
    if (!config) return;
    setConfig({
      ...config,
      processing: {
        ...config.processing,
        transcription: {
          ...(config.processing?.transcription || {}),
          [key]: value,
        },
      },
    });
  };

  const updateEnrichment = (key: string, value: boolean | number) => {
    if (!config) return;
    setConfig({
      ...config,
      enrichment: { ...config.enrichment, [key]: value },
    });
  };

  const updateSearch = (key: string, value: boolean | number) => {
    if (!config) return;
    setConfig({ ...config, search: { ...config.search, [key]: value } });
  };

  const updateEmbedding = (key: string, value: string | number) => {
    if (!config) return;
    setConfig({ ...config, embedding: { ...config.embedding, [key]: value } });
  };

  const updateEnrichmentStr = (key: string, value: string) => {
    if (!config) return;
    setConfig({
      ...config,
      enrichment: { ...config.enrichment, [key]: value },
    });
  };

  const updateSearchStr = (key: string, value: string) => {
    if (!config) return;
    setConfig({ ...config, search: { ...config.search, [key]: value } });
  };

  const handleEmbeddingProviderChange = (provider: string) => {
    const models = availableProviders[provider] || [];
    if (!config) return;
    setConfig({
      ...config,
      embedding: { ...config.embedding, provider, model: models[0] || "" },
    });
  };

  const handleEnrichmentProviderChange = (provider: string) => {
    const models = availableProviders[provider] || [];
    if (!config) return;
    setConfig({
      ...config,
      enrichment: { ...config.enrichment, provider, model: models[0] || "" },
    });
  };

  const handleRerankProviderChange = (provider: string) => {
    const models = availableProviders[provider] || [];
    if (!config) return;
    setConfig({
      ...config,
      search: {
        ...config.search,
        rerank_provider: provider,
        rerank_model: models[0] || "",
      },
    });
  };

  const handleCrossLangProviderChange = (provider: string) => {
    const models = availableProviders[provider] || [];
    if (!config) return;
    const chatModels = models.filter((m) => !/embed|rerank/i.test(m));
    setConfig({
      ...config,
      search: {
        ...config.search,
        cross_language_provider: provider,
        cross_language_model: chatModels[0] || models[0] || "",
      },
    });
  };

  const handleVisionProviderChange = (provider: string) => {
    const models = availableProviders[provider] || [];
    if (!config) return;
    setConfig({
      ...config,
      parsing: {
        ...config.parsing,
        vision_provider: provider,
        vision_model: models[0] || "",
      },
    });
  };

  const handleTranscriptionProviderChange = (provider: string) => {
    const models = availableProviders[provider] || [];
    if (!config) return;
    setConfig({
      ...config,
      processing: {
        ...config.processing,
        transcription: {
          ...(config.processing?.transcription || {}),
          provider,
          model: models[0] || "",
        },
      },
    });
  };

  const pickRerankTarget = () => {
    const providers = Object.keys(availableProviders);
    const preferredProviders = [
      config?.search?.rerank_provider || "",
      "llm-pool",
      "vllm",
      "ollama",
      ...providers,
    ].filter(Boolean);

    for (const provider of preferredProviders) {
      const models = availableProviders[provider] || [];
      const matchedModel = models.find(isLikelyRerankModel);
      if (matchedModel) {
        return { provider, model: matchedModel };
      }
    }

    for (const provider of preferredProviders) {
      const models = availableProviders[provider] || [];
      if (models.length > 0) {
        return { provider, model: models[0] };
      }
    }

    return {
      provider: config?.search?.rerank_provider || "",
      model: config?.search?.rerank_model || "",
    };
  };

  const recommendedChunking = {
    ...QUALITY_FIRST_DEFAULTS.chunking,
    ...(config?.recommended?.chunking || {}),
  };
  const recommendedProcessing = {
    ...QUALITY_FIRST_DEFAULTS.processing,
    ...(config?.recommended?.processing || {}),
    transcription: {
      ...QUALITY_FIRST_DEFAULTS.processing.transcription,
      ...(config?.recommended?.processing?.transcription || {}),
    },
  };
  const recommendedParsing = {
    ...QUALITY_FIRST_DEFAULTS.parsing,
    ...(config?.recommended?.parsing || {}),
  };
  const recommendedEnrichment = {
    ...QUALITY_FIRST_DEFAULTS.enrichment,
    ...(config?.recommended?.enrichment || {}),
  };
  const recommendedEmbedding = {
    ...QUALITY_FIRST_DEFAULTS.embedding,
    ...(config?.recommended?.embedding || {}),
  };
  const recommendedSearch = {
    ...QUALITY_FIRST_DEFAULTS.search,
    ...(config?.recommended?.search || {}),
  };

  const applyRecommendedDefaults = () => {
    if (!config) return;

    const rerankTarget = pickRerankTarget();
    setConfig({
      ...config,
      processing: {
        ...config.processing,
        transcription: {
          ...(config.processing?.transcription || {}),
          enabled: Boolean(recommendedProcessing.transcription.enabled ?? true),
          engine: normalizeTranscriptionEngine(
            String(recommendedProcessing.transcription.engine || "funasr"),
          ),
          provider: String(recommendedProcessing.transcription.provider || ""),
          model: String(
            recommendedProcessing.transcription.model || "iic/SenseVoiceSmall",
          ),
          language: String(
            recommendedProcessing.transcription.language || "auto",
          ),
          funasr_service_url: String(
            recommendedProcessing.transcription.funasr_service_url ||
              "http://127.0.0.1:10095",
          ),
          funasr_service_timeout_seconds: Number(
            recommendedProcessing.transcription
              .funasr_service_timeout_seconds || 300,
          ),
          funasr_service_api_key: String(
            recommendedProcessing.transcription.funasr_service_api_key || "",
          ),
        },
      },
      chunking: {
        ...config.chunking,
        strategy: String(recommendedChunking.strategy || "semantic"),
        chunk_token_num: Number(recommendedChunking.chunk_token_num || 512),
        overlap_percent: Number(recommendedChunking.overlap_percent || 10),
      },
      parsing: {
        ...config.parsing,
        method: String(recommendedParsing.method || "auto"),
        vision_timeout_seconds: Number(
          recommendedParsing.vision_timeout_seconds || 120,
        ),
      },
      enrichment: {
        ...config.enrichment,
        enabled: Boolean(recommendedEnrichment.enabled ?? true),
        keywords_topn: Number(recommendedEnrichment.keywords_topn || 5),
        questions_topn: Number(recommendedEnrichment.questions_topn || 3),
        generate_summary: Boolean(
          recommendedEnrichment.generate_summary ?? true,
        ),
        temperature: Number(recommendedEnrichment.temperature || 0.2),
        batch_size: Number(recommendedEnrichment.batch_size || 5),
        max_tokens: Number(recommendedEnrichment.max_tokens ?? 0),
      },
      embedding: {
        ...config.embedding,
        dimension: Number(recommendedEmbedding.dimension || 1024),
      },
      search: {
        ...config.search,
        max_concurrent_requests: Number(
          recommendedSearch.max_concurrent_requests || 4,
        ),
        request_timeout_seconds: Number(
          recommendedSearch.request_timeout_seconds || 30,
        ),
        enable_semantic: Boolean(recommendedSearch.enable_semantic ?? true),
        enable_fulltext: Boolean(recommendedSearch.enable_fulltext ?? true),
        combine_results: Boolean(recommendedSearch.combine_results ?? true),
        semantic_weight: Number(recommendedSearch.semantic_weight || 0.7),
        fulltext_weight: Number(recommendedSearch.fulltext_weight || 0.3),
        fusion_method: String(recommendedSearch.fusion_method || "rrf"),
        rrf_k: Number(recommendedSearch.rrf_k || 60),
        min_relevance_score: Number(
          recommendedSearch.min_relevance_score || 0.3,
        ),
        keyword_min_rank: Number(recommendedSearch.keyword_min_rank || 4.0),
        keyword_max_terms: Number(recommendedSearch.keyword_max_terms || 16),
        hybrid_score_scale: Number(
          recommendedSearch.hybrid_score_scale || 0.02,
        ),
        semantic_timeout_seconds: Number(
          recommendedSearch.semantic_timeout_seconds || 8,
        ),
        embedding_failure_backoff_seconds: Number(
          recommendedSearch.embedding_failure_backoff_seconds || 30,
        ),
        rerank_enabled: Boolean(recommendedSearch.rerank_enabled ?? true),
        rerank_weight: Number(recommendedSearch.rerank_weight || 0.85),
        rerank_provider: rerankTarget.provider,
        rerank_model: rerankTarget.model,
        rerank_top_k: Number(recommendedSearch.rerank_top_k || 30),
        rerank_timeout_seconds: Number(
          recommendedSearch.rerank_timeout_seconds || 10,
        ),
        rerank_failure_backoff_seconds: Number(
          recommendedSearch.rerank_failure_backoff_seconds || 60,
        ),
        rerank_doc_max_chars: Number(
          recommendedSearch.rerank_doc_max_chars || 1600,
        ),
      },
    });
    toast.success(t("kbConfig.recommendedApplied"));
  };

  const visionProvider = config?.parsing?.vision_provider || "";
  const visionModels = availableProviders[visionProvider] || [];
  const transcription = config?.processing?.transcription || {};
  const transcriptionEngine = normalizeTranscriptionEngine(
    transcription.engine,
  );
  const transcriptionProvider = transcription.provider || "";
  const transcriptionModels = availableProviders[transcriptionProvider] || [];
  const embeddingProvider = config?.embedding?.provider || "";
  const embeddingModels = availableProviders[embeddingProvider] || [];
  const enrichmentProvider = config?.enrichment?.provider || "";
  const enrichmentModels = availableProviders[enrichmentProvider] || [];
  const rerankProvider = config?.search?.rerank_provider || "";
  const rerankModels = availableProviders[rerankProvider] || [];
  const chunkingStrategy = config?.chunking?.strategy || "semantic";
  const chunkingStrategyHintKey =
    chunkingStrategy === "fixed_size"
      ? "kbConfig.strategyFixedHint"
      : chunkingStrategy === "paragraph"
        ? "kbConfig.strategyParagraphHint"
        : "kbConfig.strategySemanticHint";

  if (!isOpen) return null;

  const selectClass =
    "w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/70 dark:bg-zinc-900/60 text-zinc-800 dark:text-zinc-100 focus:ring-2 focus:ring-indigo-500 focus:outline-none";
  const inputClass = selectClass;
  const labelClass = "block text-sm text-zinc-700 dark:text-zinc-300 mb-1";
  const sectionClass =
    "rounded-xl border border-zinc-200/80 dark:border-zinc-700/80 bg-white/60 dark:bg-zinc-900/50 p-4";
  const sectionTitleClass =
    "text-base font-semibold text-zinc-800 dark:text-zinc-100 mb-3";
  const hintClass = "mt-1 text-xs text-zinc-500 dark:text-zinc-400";

  const providerSelect = (value: string, onChange: (v: string) => void) =>
    isLoadingProviders ? (
      <div className="flex items-center gap-2 px-3 py-2 text-sm text-zinc-500 dark:text-zinc-400">
        <Loader2 className="w-4 h-4 animate-spin" /> {t("kbConfig.loading")}
      </div>
    ) : (
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={selectClass}
      >
        <option value="">{t("kbConfig.selectProvider")}</option>
        {Object.keys(availableProviders).map((name) => (
          <option key={name} value={name}>
            {name}
          </option>
        ))}
      </select>
    );

  const modelSelect = (
    value: string,
    onChange: (v: string) => void,
    models: string[],
    hasProvider: boolean,
  ) => (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={!hasProvider}
      className={`${selectClass} disabled:opacity-50 disabled:cursor-not-allowed`}
    >
      <option value="">
        {hasProvider
          ? t("kbConfig.selectModel")
          : t("kbConfig.selectProviderFirst")}
      </option>
      {models.map((m) => (
        <option key={m} value={m}>
          {m}
        </option>
      ))}
    </select>
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md"
      style={{ marginLeft: "var(--sidebar-width, 0px)" }}
    >
      <ModalPanel className="w-full max-w-4xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <SlidersHorizontal className="w-6 h-6 text-indigo-500" />
            <div>
              <h2 className="text-2xl font-bold text-gray-800 dark:text-white">
                {t("kbConfig.title")}
              </h2>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                {t(
                  "kbConfig.subtitle",
                  "Configure parsing, chunking, enrichment, embedding and retrieval in one place.",
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
        ) : config ? (
          <div className="space-y-5">
            <section className="rounded-xl border border-indigo-200/80 dark:border-indigo-500/30 bg-indigo-50/70 dark:bg-indigo-500/10 p-4">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <h3 className="text-base font-semibold text-indigo-700 dark:text-indigo-200 flex items-center gap-2">
                    <Sparkles className="w-4 h-4" />
                    {t("kbConfig.recommendedTitle")}
                  </h3>
                  <p className="text-xs text-indigo-700/90 dark:text-indigo-200/90 mt-1">
                    {t("kbConfig.recommendedDescription")}
                  </p>
                  <p className="text-xs text-indigo-700/80 dark:text-indigo-200/80 mt-1">
                    {t("kbConfig.recommendedSummary")}
                  </p>
                  <div className="mt-3 space-y-1 text-xs text-indigo-700/85 dark:text-indigo-200/85">
                    <p className="font-medium">
                      {t("kbConfig.defaultPreviewTitle")}
                    </p>
                    <p>
                      {t("kbConfig.defaultPreviewChunking", {
                        strategy: recommendedChunking.strategy,
                        chunkSize: recommendedChunking.chunk_token_num,
                        overlap: recommendedChunking.overlap_percent,
                      })}
                    </p>
                    <p>
                      {t("kbConfig.defaultPreviewSearch", {
                        minScore: Number(
                          recommendedSearch.min_relevance_score || 0.3,
                        ).toFixed(2),
                        timeout: recommendedSearch.semantic_timeout_seconds,
                      })}
                    </p>
                    <p>
                      {t("kbConfig.defaultPreviewRerank", {
                        topK: recommendedSearch.rerank_top_k,
                        timeout: recommendedSearch.rerank_timeout_seconds,
                      })}
                    </p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setShowAdvanced((prev) => !prev)}
                    className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded-md bg-white/20 hover:bg-white/30 text-indigo-700 dark:text-indigo-200 transition-colors"
                  >
                    <SlidersHorizontal className="w-3 h-3" />
                    {showAdvanced
                      ? t("kbConfig.hideAdvanced")
                      : t("kbConfig.showAdvanced")}
                  </button>
                </div>
              </div>
            </section>

            {/* Parsing */}
            <section className={sectionClass}>
              <h3 className={sectionTitleClass}>{t("kbConfig.parsing")}</h3>
              <div className="space-y-3">
                <div>
                  <label className={labelClass}>
                    {t("kbConfig.parsingMethod")}
                  </label>
                  <select
                    value={config.parsing.method || "auto"}
                    onChange={(e) => updateParsing("method", e.target.value)}
                    className={selectClass}
                  >
                    <option value="auto">{t("kbConfig.parsingAuto")}</option>
                    <option value="standard">
                      {t("kbConfig.parsingStandard")}
                    </option>
                    <option value="vision">
                      {t("kbConfig.parsingVision")}
                    </option>
                  </select>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <label className={labelClass}>
                      {t("kbConfig.visionProvider")}
                    </label>
                    {providerSelect(visionProvider, handleVisionProviderChange)}
                  </div>
                  <div>
                    <label className={labelClass}>
                      {t("kbConfig.visionModel")}
                    </label>
                    {modelSelect(
                      config.parsing.vision_model || "",
                      (v) => updateParsing("vision_model", v),
                      visionModels,
                      !!visionProvider,
                    )}
                  </div>
                </div>
                {showAdvanced && (
                  <div>
                    <label className={labelClass}>
                      {t("kbConfig.visionTimeoutSeconds")}
                    </label>
                    <input
                      type="number"
                      min={5}
                      max={300}
                      value={config.parsing.vision_timeout_seconds || 120}
                      onChange={(e) =>
                        updateParsing("vision_timeout_seconds", e.target.value)
                      }
                      className={inputClass}
                    />
                  </div>
                )}
              </div>
            </section>

            {/* Transcription */}
            <section className={sectionClass}>
              <h3 className={sectionTitleClass}>
                {t("kbConfig.transcription")}
              </h3>
              <div className="space-y-3">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={transcription.enabled ?? true}
                    onChange={(e) =>
                      updateTranscription("enabled", e.target.checked)
                    }
                    className="w-4 h-4 accent-indigo-500"
                  />
                  <span className="text-sm text-zinc-700 dark:text-zinc-300">
                    {t("kbConfig.enableTranscription")}
                  </span>
                </label>

                {(transcription.enabled ?? true) && (
                  <>
                    <div>
                      <label className={labelClass}>
                        {t("kbConfig.transcriptionEngine")}
                      </label>
                      <select
                        value={transcriptionEngine}
                        onChange={(e) =>
                          updateTranscription("engine", e.target.value)
                        }
                        className={selectClass}
                      >
                        <option value="funasr">
                          {t("kbConfig.transcriptionEngineFunASR")}
                        </option>
                        <option value="openai_compatible">
                          {t("kbConfig.transcriptionEngineOpenAI")}
                        </option>
                      </select>
                    </div>

                    {transcriptionEngine === "funasr" ? (
                      <div className="space-y-3">
                        <div>
                          <label className={labelClass}>
                            {t("kbConfig.transcriptionModel")}
                          </label>
                          <input
                            type="text"
                            value={transcription.model || "iic/SenseVoiceSmall"}
                            onChange={(e) =>
                              updateTranscription("model", e.target.value)
                            }
                            className={inputClass}
                            placeholder="iic/SenseVoiceSmall"
                          />
                        </div>
                        <div>
                          <label className={labelClass}>
                            {t("kbConfig.funasrServiceUrl")}
                          </label>
                          <input
                            type="text"
                            value={transcription.funasr_service_url || ""}
                            onChange={(e) =>
                              updateTranscription(
                                "funasr_service_url",
                                e.target.value,
                              )
                            }
                            className={inputClass}
                            placeholder="http://127.0.0.1:10095"
                          />
                        </div>
                        {showAdvanced && (
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            <div>
                              <label className={labelClass}>
                                {t("kbConfig.funasrServiceTimeout")}
                              </label>
                              <input
                                type="number"
                                min={5}
                                max={1800}
                                value={
                                  transcription.funasr_service_timeout_seconds ||
                                  300
                                }
                                onChange={(e) =>
                                  updateTranscription(
                                    "funasr_service_timeout_seconds",
                                    Number(e.target.value),
                                  )
                                }
                                className={inputClass}
                              />
                            </div>
                            <div>
                              <label className={labelClass}>
                                {t("kbConfig.funasrServiceApiKey")}
                              </label>
                              <input
                                type="password"
                                value={
                                  transcription.funasr_service_api_key || ""
                                }
                                onChange={(e) =>
                                  updateTranscription(
                                    "funasr_service_api_key",
                                    e.target.value,
                                  )
                                }
                                className={inputClass}
                                placeholder={t("common.optional")}
                              />
                            </div>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div>
                          <label className={labelClass}>
                            {t("kbConfig.transcriptionProvider")}
                          </label>
                          {providerSelect(
                            transcriptionProvider,
                            handleTranscriptionProviderChange,
                          )}
                        </div>
                        <div>
                          <label className={labelClass}>
                            {t("kbConfig.transcriptionModel")}
                          </label>
                          {modelSelect(
                            transcription.model || "",
                            (v) => updateTranscription("model", v),
                            transcriptionModels,
                            !!transcriptionProvider,
                          )}
                        </div>
                      </div>
                    )}

                    <div>
                      <label className={labelClass}>
                        {t("kbConfig.transcriptionLanguage")}
                      </label>
                      <input
                        type="text"
                        value={transcription.language || "auto"}
                        onChange={(e) =>
                          updateTranscription("language", e.target.value)
                        }
                        className={inputClass}
                        placeholder="auto / en / zh"
                      />
                    </div>
                  </>
                )}
              </div>
            </section>

            {/* Chunking */}
            <section className={sectionClass}>
              <h3 className={sectionTitleClass}>{t("kbConfig.chunking")}</h3>
              <div className="space-y-3">
                <div>
                  <label className={labelClass}>{t("kbConfig.strategy")}</label>
                  <select
                    value={config.chunking.strategy || "semantic"}
                    onChange={(e) => updateChunking("strategy", e.target.value)}
                    className={selectClass}
                  >
                    <option value="fixed_size">
                      {t("kbConfig.strategyFixed")}
                    </option>
                    <option value="paragraph">
                      {t("kbConfig.strategyParagraph")}
                    </option>
                    <option value="semantic">
                      {t("kbConfig.strategySemantic")} (
                      {t("kbConfig.recommendedShort")})
                    </option>
                  </select>
                  <p className={hintClass}>{t(chunkingStrategyHintKey)}</p>
                </div>
                <div>
                  <label className={labelClass}>
                    {t("kbConfig.chunkSize")}:{" "}
                    {config.chunking.chunk_token_num || 512}
                  </label>
                  <input
                    type="range"
                    min={64}
                    max={2048}
                    step={64}
                    value={config.chunking.chunk_token_num || 512}
                    onChange={(e) =>
                      updateChunking("chunk_token_num", Number(e.target.value))
                    }
                    className="w-full accent-indigo-500"
                  />
                  <div className="flex justify-between text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                    <span>64</span>
                    <span>2048</span>
                  </div>
                </div>
                <div>
                  <label className={labelClass}>
                    {t("kbConfig.overlap")}:{" "}
                    {config.chunking.overlap_percent || 10}%
                  </label>
                  <input
                    type="range"
                    min={0}
                    max={50}
                    step={5}
                    value={config.chunking.overlap_percent || 10}
                    onChange={(e) =>
                      updateChunking("overlap_percent", Number(e.target.value))
                    }
                    className="w-full accent-indigo-500"
                  />
                  <div className="flex justify-between text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                    <span>0%</span>
                    <span>50%</span>
                  </div>
                </div>
              </div>
            </section>

            {/* Enrichment */}
            <section className={sectionClass}>
              <h3 className={sectionTitleClass}>{t("kbConfig.enrichment")}</h3>
              <div className="space-y-3">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config.enrichment.enabled ?? true}
                    onChange={(e) =>
                      updateEnrichment("enabled", e.target.checked)
                    }
                    className="w-4 h-4 accent-indigo-500"
                  />
                  <span className="text-sm text-zinc-700 dark:text-zinc-300">
                    {t("kbConfig.enableEnrichment")}
                  </span>
                </label>
                {config.enrichment.enabled !== false && (
                  <>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div>
                        <label className={labelClass}>
                          {t("kbConfig.enrichmentProvider")}
                        </label>
                        {providerSelect(
                          enrichmentProvider,
                          handleEnrichmentProviderChange,
                        )}
                      </div>
                      <div>
                        <label className={labelClass}>
                          {t("kbConfig.enrichmentModel")}
                        </label>
                        {modelSelect(
                          config.enrichment.model || "",
                          (v) => updateEnrichmentStr("model", v),
                          enrichmentModels,
                          !!enrichmentProvider,
                        )}
                      </div>
                    </div>
                    <div>
                      <label className={labelClass}>
                        {t("kbConfig.enrichmentMaxTokens")}
                      </label>
                      <input
                        type="number"
                        min={0}
                        max={8192}
                        step={64}
                        value={config.enrichment.max_tokens ?? 0}
                        onChange={(e) =>
                          updateEnrichment(
                            "max_tokens",
                            Math.max(
                              0,
                              Math.min(8192, Number(e.target.value) || 0),
                            ),
                          )
                        }
                        className={inputClass}
                      />
                      <p className={hintClass}>
                        {t("kbConfig.enrichmentMaxTokensHint")}
                      </p>
                    </div>
                    {showAdvanced && (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div>
                          <label className={labelClass}>
                            {t("kbConfig.keywordsTopn")}
                          </label>
                          <input
                            type="number"
                            min={1}
                            max={20}
                            value={config.enrichment.keywords_topn || 5}
                            onChange={(e) =>
                              updateEnrichment(
                                "keywords_topn",
                                Number(e.target.value),
                              )
                            }
                            className={inputClass}
                          />
                        </div>
                        <div>
                          <label className={labelClass}>
                            {t("kbConfig.questionsTopn")}
                          </label>
                          <input
                            type="number"
                            min={1}
                            max={10}
                            value={config.enrichment.questions_topn || 3}
                            onChange={(e) =>
                              updateEnrichment(
                                "questions_topn",
                                Number(e.target.value),
                              )
                            }
                            className={inputClass}
                          />
                        </div>
                      </div>
                    )}
                    <label className="flex items-center gap-3 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={config.enrichment.generate_summary ?? true}
                        onChange={(e) =>
                          updateEnrichment("generate_summary", e.target.checked)
                        }
                        className="w-4 h-4 accent-indigo-500"
                      />
                      <span className="text-sm text-zinc-700 dark:text-zinc-300">
                        {t("kbConfig.generateSummary")}
                      </span>
                    </label>
                  </>
                )}
              </div>
            </section>

            {/* Embedding */}
            <section className={sectionClass}>
              <h3 className={sectionTitleClass}>{t("kbConfig.embedding")}</h3>
              <div className="space-y-3">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <label className={labelClass}>
                      {t("kbConfig.embeddingProvider")}
                    </label>
                    {providerSelect(
                      embeddingProvider,
                      handleEmbeddingProviderChange,
                    )}
                  </div>
                  <div>
                    <label className={labelClass}>
                      {t("kbConfig.embeddingModel")}
                    </label>
                    {modelSelect(
                      config.embedding.model || "",
                      (v) => updateEmbedding("model", v),
                      embeddingModels,
                      !!embeddingProvider,
                    )}
                  </div>
                </div>
                {showAdvanced && (
                  <div>
                    <label className={labelClass}>
                      {t("kbConfig.embeddingDimension")}
                    </label>
                    <input
                      type="number"
                      min={128}
                      max={4096}
                      value={config.embedding.dimension || 1024}
                      onChange={(e) =>
                        updateEmbedding("dimension", Number(e.target.value))
                      }
                      className={inputClass}
                    />
                  </div>
                )}
              </div>
            </section>

            {/* Search & Rerank */}
            <section className={sectionClass}>
              <h3 className={sectionTitleClass}>{t("kbConfig.search")}</h3>
              <div className="space-y-3">
                {showAdvanced && (
                  <div>
                    <label className={labelClass}>
                      {t("kbConfig.semanticWeight")}:{" "}
                      {config.search.semantic_weight ?? 0.7}
                    </label>
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={config.search.semantic_weight ?? 0.7}
                      onChange={(e) =>
                        updateSearch("semantic_weight", Number(e.target.value))
                      }
                      className="w-full accent-indigo-500"
                    />
                  </div>
                )}
                {showAdvanced && (
                  <div>
                    <label className={labelClass}>
                      {t("kbConfig.fulltextWeight")}:{" "}
                      {config.search.fulltext_weight ?? 0.3}
                    </label>
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={config.search.fulltext_weight ?? 0.3}
                      onChange={(e) =>
                        updateSearch("fulltext_weight", Number(e.target.value))
                      }
                      className="w-full accent-indigo-500"
                    />
                  </div>
                )}
                <div>
                  <label className={labelClass}>
                    {t("kbConfig.minRelevanceScore")}:{" "}
                    {config.search.min_relevance_score ?? 0.3}
                  </label>
                  <input
                    type="range"
                    min={0}
                    max={1}
                    step={0.01}
                    value={config.search.min_relevance_score ?? 0.3}
                    onChange={(e) =>
                      updateSearch(
                        "min_relevance_score",
                        Number(e.target.value),
                      )
                    }
                    className="w-full accent-indigo-500"
                  />
                  <p className={hintClass}>
                    {t("kbConfig.minRelevanceScoreHint")}
                  </p>
                </div>
                {showAdvanced && (
                  <div>
                    <label className={labelClass}>{t("kbConfig.rrfK")}</label>
                    <input
                      type="number"
                      min={1}
                      max={200}
                      value={config.search.rrf_k || 60}
                      onChange={(e) =>
                        updateSearch("rrf_k", Number(e.target.value))
                      }
                      className={inputClass}
                    />
                  </div>
                )}
                {showAdvanced && (
                  <div>
                    <label className={labelClass}>
                      {t("kbConfig.keywordMinRank")}
                    </label>
                    <input
                      type="number"
                      min={0}
                      max={30}
                      step={0.5}
                      value={config.search.keyword_min_rank ?? 4}
                      onChange={(e) =>
                        updateSearch("keyword_min_rank", Number(e.target.value))
                      }
                      className={inputClass}
                    />
                  </div>
                )}
                {showAdvanced && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                      <label className={labelClass}>
                        {t("kbConfig.semanticTimeoutSeconds")}
                      </label>
                      <input
                        type="number"
                        min={1}
                        max={60}
                        value={config.search.semantic_timeout_seconds ?? 8}
                        onChange={(e) =>
                          updateSearch(
                            "semantic_timeout_seconds",
                            Number(e.target.value),
                          )
                        }
                        className={inputClass}
                      />
                    </div>
                    <div>
                      <label className={labelClass}>
                        {t("kbConfig.requestTimeoutSeconds")}
                      </label>
                      <input
                        type="number"
                        min={5}
                        max={120}
                        value={config.search.request_timeout_seconds ?? 30}
                        onChange={(e) =>
                          updateSearch(
                            "request_timeout_seconds",
                            Number(e.target.value),
                          )
                        }
                        className={inputClass}
                      />
                    </div>
                  </div>
                )}

                {/* Rerank */}
                <div className="pt-3 border-t border-zinc-200 dark:border-zinc-700">
                  <label className="flex items-center gap-3 cursor-pointer mb-4">
                    <input
                      type="checkbox"
                      checked={config.search.rerank_enabled ?? false}
                      onChange={(e) =>
                        updateSearch("rerank_enabled", e.target.checked)
                      }
                      className="w-4 h-4 accent-indigo-500"
                    />
                    <span className="text-sm text-zinc-700 dark:text-zinc-300">
                      {t("kbConfig.enableRerank")}
                    </span>
                  </label>
                  {config.search.rerank_enabled && (
                    <>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                        <div>
                          <label className={labelClass}>
                            {t("kbConfig.rerankProvider")}
                          </label>
                          {providerSelect(
                            rerankProvider,
                            handleRerankProviderChange,
                          )}
                        </div>
                        <div>
                          <label className={labelClass}>
                            {t("kbConfig.rerankModel")}
                          </label>
                          {modelSelect(
                            config.search.rerank_model || "",
                            (v) => updateSearchStr("rerank_model", v),
                            rerankModels,
                            !!rerankProvider,
                          )}
                        </div>
                      </div>
                      {showAdvanced && (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                          <div>
                            <label className={labelClass}>
                              {t("kbConfig.rerankTopK")}
                            </label>
                            <input
                              type="number"
                              min={1}
                              max={50}
                              value={config.search.rerank_top_k || 30}
                              onChange={(e) =>
                                updateSearch(
                                  "rerank_top_k",
                                  Number(e.target.value),
                                )
                              }
                              className={inputClass}
                            />
                          </div>
                          <div>
                            <label className={labelClass}>
                              {t("kbConfig.rerankTimeoutSeconds")}
                            </label>
                            <input
                              type="number"
                              min={1}
                              max={60}
                              value={config.search.rerank_timeout_seconds || 10}
                              onChange={(e) =>
                                updateSearch(
                                  "rerank_timeout_seconds",
                                  Number(e.target.value),
                                )
                              }
                              className={inputClass}
                            />
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            </section>

            {/* Cross-Language Expansion */}
            {showAdvanced && (
              <section className={sectionClass}>
                <h3 className={sectionTitleClass}>
                  {t("kbConfig.crossLanguage", "跨语言检索扩展")}
                </h3>
                <div className="space-y-3 rounded-lg border border-zinc-200/80 dark:border-zinc-700/80 bg-white/40 dark:bg-zinc-900/40 p-3">
                  <label className="flex items-center gap-3 cursor-pointer mb-4">
                    <input
                      type="checkbox"
                      checked={
                        config.search.cross_language_expansion_enabled ?? true
                      }
                      onChange={(e) =>
                        updateSearch(
                          "cross_language_expansion_enabled",
                          e.target.checked,
                        )
                      }
                      className="w-4 h-4 accent-indigo-500"
                    />
                    <span className="text-sm text-zinc-700 dark:text-zinc-300">
                      {t("kbConfig.enableCrossLanguage", "启用跨语言扩展")}
                    </span>
                  </label>
                  {config.search.cross_language_expansion_enabled && (
                    <>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                        <div>
                          <label className={labelClass}>
                            {t("kbConfig.crossLangProvider", "扩展模型供应商")}
                          </label>
                          <select
                            value={config.search.cross_language_provider || ""}
                            onChange={(e) =>
                              handleCrossLangProviderChange(e.target.value)
                            }
                            className={selectClass}
                          >
                            <option value="">
                              {t("kbConfig.autoResolve", "自动（继承默认）")}
                            </option>
                            {Object.keys(availableProviders).map((p) => (
                              <option key={p} value={p}>
                                {p}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className={labelClass}>
                            {t("kbConfig.crossLangModel", "扩展模型")}
                          </label>
                          <select
                            value={config.search.cross_language_model || ""}
                            onChange={(e) =>
                              updateSearchStr(
                                "cross_language_model",
                                e.target.value,
                              )
                            }
                            className={selectClass}
                          >
                            <option value="">
                              {t("kbConfig.autoResolve", "自动（继承默认）")}
                            </option>
                            {(
                              availableProviders[
                                config.search.cross_language_provider || ""
                              ] || []
                            )
                              .filter((m) => !/embed|rerank/i.test(m))
                              .map((m) => (
                                <option key={m} value={m}>
                                  {m}
                                </option>
                              ))}
                          </select>
                        </div>
                      </div>
                      <p className="text-xs text-zinc-500 dark:text-zinc-400">
                        {t(
                          "kbConfig.crossLanguageHint",
                          "将用户查询自动翻译为其他语言以提升多语言检索效果。留空表示自动从供应商配置中选取。",
                        )}
                      </p>
                    </>
                  )}
                </div>
              </section>
            )}

            <div className="flex items-center justify-between gap-3 mt-6">
              <button
                onClick={applyRecommendedDefaults}
                disabled={isSaving}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-500 text-white hover:bg-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Sparkles className="w-4 h-4" />
                {t("kbConfig.applyRecommended")}
              </button>

              <div className="flex items-center gap-2">
                <button
                  onClick={onClose}
                  disabled={isSaving}
                  className="px-4 py-2 rounded-lg bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-600 disabled:opacity-50"
                >
                  {t("kbConfig.cancel")}
                </button>
                <button
                  onClick={handleSave}
                  disabled={isSaving}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-500 text-white hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isSaving ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Save className="w-4 h-4" />
                  )}
                  {t("kbConfig.save")}
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            {t("kbConfig.loadFailed")}
          </div>
        )}
      </ModalPanel>
    </div>
  );
};
