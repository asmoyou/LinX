import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Save, Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { ModalPanel } from '@/components/ModalPanel';
import { knowledgeApi } from '@/api/knowledge';
import { llmApi } from '@/api/llm';
import type { KBConfigResponse } from '@/api/knowledge';

interface KBConfigPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

export const KBConfigPanel: React.FC<KBConfigPanelProps> = ({ isOpen, onClose }) => {
  const { t } = useTranslation();
  const [config, setConfig] = useState<KBConfigResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  // Provider/model state
  const [availableProviders, setAvailableProviders] = useState<Record<string, string[]>>({});
  const [isLoadingProviders, setIsLoadingProviders] = useState(false);

  useEffect(() => {
    if (isOpen) {
      loadConfig();
      fetchProviders();
    }
  }, [isOpen]);

  const loadConfig = async () => {
    setIsLoading(true);
    try {
      const data = await knowledgeApi.getConfig();
      setConfig(data);
    } catch {
      toast.error(t('kbConfig.loadFailed'));
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
        chunking: config.chunking,
        parsing: config.parsing,
        enrichment: config.enrichment,
        embedding: config.embedding,
        search: config.search,
      });
      setConfig(updated);
      toast.success(t('kbConfig.saveSuccess'));
      onClose();
    } catch {
      toast.error(t('kbConfig.saveFailed'));
    } finally {
      setIsSaving(false);
    }
  };

  const updateChunking = (key: string, value: string | number) => {
    if (!config) return;
    setConfig({ ...config, chunking: { ...config.chunking, [key]: value } });
  };

  const updateParsing = (key: string, value: string) => {
    if (!config) return;
    setConfig({ ...config, parsing: { ...config.parsing, [key]: value } });
  };

  const updateEnrichment = (key: string, value: boolean | number) => {
    if (!config) return;
    setConfig({ ...config, enrichment: { ...config.enrichment, [key]: value } });
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
    setConfig({ ...config, enrichment: { ...config.enrichment, [key]: value } });
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
      embedding: { ...config.embedding, provider, model: models[0] || '' },
    });
  };

  const handleEnrichmentProviderChange = (provider: string) => {
    const models = availableProviders[provider] || [];
    if (!config) return;
    setConfig({
      ...config,
      enrichment: { ...config.enrichment, provider, model: models[0] || '' },
    });
  };

  const handleRerankProviderChange = (provider: string) => {
    const models = availableProviders[provider] || [];
    if (!config) return;
    setConfig({
      ...config,
      search: { ...config.search, rerank_provider: provider, rerank_model: models[0] || '' },
    });
  };

  const handleVisionProviderChange = (provider: string) => {
    const models = availableProviders[provider] || [];
    if (!config) return;
    setConfig({
      ...config,
      parsing: { ...config.parsing, vision_provider: provider, vision_model: models[0] || '' },
    });
  };

  const visionProvider = config?.parsing?.vision_provider || '';
  const visionModels = availableProviders[visionProvider] || [];
  const embeddingProvider = config?.embedding?.provider || '';
  const embeddingModels = availableProviders[embeddingProvider] || [];
  const enrichmentProvider = config?.enrichment?.provider || '';
  const enrichmentModels = availableProviders[enrichmentProvider] || [];
  const rerankProvider = config?.search?.rerank_provider || '';
  const rerankModels = availableProviders[rerankProvider] || [];

  if (!isOpen) return null;

  const selectClass =
    'w-full px-3 py-2 bg-white/10 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-800 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:outline-none';
  const inputClass = selectClass;
  const labelClass = 'block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1';

  const providerSelect = (
    value: string,
    onChange: (v: string) => void,
  ) =>
    isLoadingProviders ? (
      <div className="flex items-center gap-2 px-3 py-2 text-sm text-gray-500">
        <Loader2 className="w-4 h-4 animate-spin" /> {t('kbConfig.loading')}
      </div>
    ) : (
      <select value={value} onChange={(e) => onChange(e.target.value)} className={selectClass}>
        <option value="">{t('kbConfig.selectProvider')}</option>
        {Object.keys(availableProviders).map((name) => (
          <option key={name} value={name}>{name}</option>
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
        {hasProvider ? t('kbConfig.selectModel') : t('kbConfig.selectProviderFirst')}
      </option>
      {models.map((m) => (
        <option key={m} value={m}>{m}</option>
      ))}
    </select>
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md"
      style={{ marginLeft: 'var(--sidebar-width, 0px)' }}
    >
      <ModalPanel className="w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-gray-800 dark:text-white">
            {t('kbConfig.title')}
          </h2>
          <button onClick={onClose} className="p-2 hover:bg-white/20 rounded-lg transition-colors">
            <X className="w-6 h-6 text-gray-700 dark:text-gray-300" />
          </button>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-8 h-8 text-indigo-500 animate-spin" />
          </div>
        ) : config ? (
          <div className="space-y-8">
            {/* Parsing */}
            <section>
              <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-4">
                {t('kbConfig.parsing')}
              </h3>
              <div className="space-y-4">
                <div>
                  <label className={labelClass}>{t('kbConfig.parsingMethod')}</label>
                  <select
                    value={config.parsing.method || 'auto'}
                    onChange={(e) => updateParsing('method', e.target.value)}
                    className={selectClass}
                  >
                    <option value="auto">{t('kbConfig.parsingAuto')}</option>
                    <option value="standard">{t('kbConfig.parsingStandard')}</option>
                    <option value="vision">{t('kbConfig.parsingVision')}</option>
                  </select>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className={labelClass}>{t('kbConfig.visionProvider')}</label>
                    {providerSelect(visionProvider, handleVisionProviderChange)}
                  </div>
                  <div>
                    <label className={labelClass}>{t('kbConfig.visionModel')}</label>
                    {modelSelect(
                      config.parsing.vision_model || '',
                      (v) => updateParsing('vision_model', v),
                      visionModels,
                      !!visionProvider,
                    )}
                  </div>
                </div>
              </div>
            </section>

            {/* Chunking */}
            <section>
              <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-4">
                {t('kbConfig.chunking')}
              </h3>
              <div className="space-y-4">
                <div>
                  <label className={labelClass}>{t('kbConfig.strategy')}</label>
                  <select
                    value={config.chunking.strategy || 'semantic'}
                    onChange={(e) => updateChunking('strategy', e.target.value)}
                    className={selectClass}
                  >
                    <option value="fixed_size">{t('kbConfig.strategyFixed')}</option>
                    <option value="paragraph">{t('kbConfig.strategyParagraph')}</option>
                    <option value="semantic">{t('kbConfig.strategySemantic')}</option>
                  </select>
                </div>
                <div>
                  <label className={labelClass}>
                    {t('kbConfig.chunkSize')}: {config.chunking.chunk_token_num || 512}
                  </label>
                  <input
                    type="range" min={64} max={2048} step={64}
                    value={config.chunking.chunk_token_num || 512}
                    onChange={(e) => updateChunking('chunk_token_num', Number(e.target.value))}
                    className="w-full accent-indigo-500"
                  />
                  <div className="flex justify-between text-xs text-gray-500 mt-1">
                    <span>64</span><span>2048</span>
                  </div>
                </div>
                <div>
                  <label className={labelClass}>
                    {t('kbConfig.overlap')}: {config.chunking.overlap_percent || 10}%
                  </label>
                  <input
                    type="range" min={0} max={50} step={5}
                    value={config.chunking.overlap_percent || 10}
                    onChange={(e) => updateChunking('overlap_percent', Number(e.target.value))}
                    className="w-full accent-indigo-500"
                  />
                  <div className="flex justify-between text-xs text-gray-500 mt-1">
                    <span>0%</span><span>50%</span>
                  </div>
                </div>
              </div>
            </section>

            {/* Enrichment */}
            <section>
              <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-4">
                {t('kbConfig.enrichment')}
              </h3>
              <div className="space-y-4">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config.enrichment.enabled ?? true}
                    onChange={(e) => updateEnrichment('enabled', e.target.checked)}
                    className="w-4 h-4 accent-indigo-500"
                  />
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    {t('kbConfig.enableEnrichment')}
                  </span>
                </label>
                {config.enrichment.enabled !== false && (
                  <>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className={labelClass}>{t('kbConfig.enrichmentProvider')}</label>
                        {providerSelect(enrichmentProvider, handleEnrichmentProviderChange)}
                      </div>
                      <div>
                        <label className={labelClass}>{t('kbConfig.enrichmentModel')}</label>
                        {modelSelect(
                          config.enrichment.model || '',
                          (v) => updateEnrichmentStr('model', v),
                          enrichmentModels,
                          !!enrichmentProvider,
                        )}
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className={labelClass}>{t('kbConfig.keywordsTopn')}</label>
                        <input
                          type="number" min={1} max={20}
                          value={config.enrichment.keywords_topn || 5}
                          onChange={(e) => updateEnrichment('keywords_topn', Number(e.target.value))}
                          className={inputClass}
                        />
                      </div>
                      <div>
                        <label className={labelClass}>{t('kbConfig.questionsTopn')}</label>
                        <input
                          type="number" min={1} max={10}
                          value={config.enrichment.questions_topn || 3}
                          onChange={(e) => updateEnrichment('questions_topn', Number(e.target.value))}
                          className={inputClass}
                        />
                      </div>
                    </div>
                    <label className="flex items-center gap-3 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={config.enrichment.generate_summary ?? true}
                        onChange={(e) => updateEnrichment('generate_summary', e.target.checked)}
                        className="w-4 h-4 accent-indigo-500"
                      />
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        {t('kbConfig.generateSummary')}
                      </span>
                    </label>
                  </>
                )}
              </div>
            </section>

            {/* Embedding */}
            <section>
              <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-4">
                {t('kbConfig.embedding')}
              </h3>
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className={labelClass}>{t('kbConfig.embeddingProvider')}</label>
                    {providerSelect(embeddingProvider, handleEmbeddingProviderChange)}
                  </div>
                  <div>
                    <label className={labelClass}>{t('kbConfig.embeddingModel')}</label>
                    {modelSelect(
                      config.embedding.model || '',
                      (v) => updateEmbedding('model', v),
                      embeddingModels,
                      !!embeddingProvider,
                    )}
                  </div>
                </div>
                <div>
                  <label className={labelClass}>{t('kbConfig.embeddingDimension')}</label>
                  <input
                    type="number" min={128} max={4096}
                    value={config.embedding.dimension || 1024}
                    onChange={(e) => updateEmbedding('dimension', Number(e.target.value))}
                    className={inputClass}
                  />
                </div>
              </div>
            </section>

            {/* Search & Rerank */}
            <section>
              <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-4">
                {t('kbConfig.search')}
              </h3>
              <div className="space-y-4">
                <div>
                  <label className={labelClass}>
                    {t('kbConfig.semanticWeight')}: {config.search.semantic_weight ?? 0.7}
                  </label>
                  <input
                    type="range" min={0} max={1} step={0.05}
                    value={config.search.semantic_weight ?? 0.7}
                    onChange={(e) => updateSearch('semantic_weight', Number(e.target.value))}
                    className="w-full accent-indigo-500"
                  />
                </div>
                <div>
                  <label className={labelClass}>
                    {t('kbConfig.fulltextWeight')}: {config.search.fulltext_weight ?? 0.3}
                  </label>
                  <input
                    type="range" min={0} max={1} step={0.05}
                    value={config.search.fulltext_weight ?? 0.3}
                    onChange={(e) => updateSearch('fulltext_weight', Number(e.target.value))}
                    className="w-full accent-indigo-500"
                  />
                </div>
                <div>
                  <label className={labelClass}>{t('kbConfig.rrfK')}</label>
                  <input
                    type="number" min={1} max={200}
                    value={config.search.rrf_k || 60}
                    onChange={(e) => updateSearch('rrf_k', Number(e.target.value))}
                    className={inputClass}
                  />
                </div>

                {/* Rerank */}
                <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                  <label className="flex items-center gap-3 cursor-pointer mb-4">
                    <input
                      type="checkbox"
                      checked={config.search.rerank_enabled ?? false}
                      onChange={(e) => updateSearch('rerank_enabled', e.target.checked)}
                      className="w-4 h-4 accent-indigo-500"
                    />
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      {t('kbConfig.enableRerank')}
                    </span>
                  </label>
                  {config.search.rerank_enabled && (
                    <>
                      <div className="grid grid-cols-2 gap-4 mb-4">
                        <div>
                          <label className={labelClass}>{t('kbConfig.rerankProvider')}</label>
                          {providerSelect(rerankProvider, handleRerankProviderChange)}
                        </div>
                        <div>
                          <label className={labelClass}>{t('kbConfig.rerankModel')}</label>
                          {modelSelect(
                            config.search.rerank_model || '',
                            (v) => updateSearchStr('rerank_model', v),
                            rerankModels,
                            !!rerankProvider,
                          )}
                        </div>
                      </div>
                      <div>
                        <label className={labelClass}>{t('kbConfig.rerankTopK')}</label>
                        <input
                          type="number" min={1} max={50}
                          value={config.search.rerank_top_k || 5}
                          onChange={(e) => updateSearch('rerank_top_k', Number(e.target.value))}
                          className={inputClass}
                        />
                      </div>
                    </>
                  )}
                </div>
              </div>
            </section>

            {/* Save Button */}
            <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
              <button
                onClick={onClose}
                className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-white/20 rounded-lg transition-colors"
              >
                {t('kbConfig.cancel')}
              </button>
              <button
                onClick={handleSave}
                disabled={isSaving}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition-colors disabled:opacity-50"
              >
                {isSaving ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Save className="w-4 h-4" />
                )}
                {t('kbConfig.save')}
              </button>
            </div>
          </div>
        ) : (
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            {t('kbConfig.loadFailed')}
          </div>
        )}
      </ModalPanel>
    </div>
  );
};
