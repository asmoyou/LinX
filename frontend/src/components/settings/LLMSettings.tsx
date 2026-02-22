import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Cpu,
  CheckCircle2,
  XCircle,
  Zap,
  AlertCircle,
  Plus,
  Edit,
  Trash2,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { useAuthStore } from '../../stores';
import { llmApi } from '../../api';
import type { LLMConfig, ModelMetadata, ProviderModelsMetadata } from '../../api/llm';
import { AddProviderModal } from '../AddProviderModal';
import { EditModelModal } from './EditModelModal';

export const LLMSettings: React.FC = () => {
  const { t } = useTranslation();
  const { user } = useAuthStore();
  const [config, setConfig] = useState<LLMConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [testing, setTesting] = useState<string | null>(null);
  const [testPrompt, setTestPrompt] = useState('Hello, how are you?');
  const [selectedModels, setSelectedModels] = useState<Record<string, string>>({});
  const [expandedProviders, setExpandedProviders] = useState<Record<string, boolean>>({});
  const [modelsMetadata, setModelsMetadata] = useState<Record<string, ProviderModelsMetadata>>({});
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingProvider, setEditingProvider] = useState<any>(null);
  const [deletingProvider, setDeletingProvider] = useState<string | null>(null);
  const [editingModel, setEditingModel] = useState<{ provider: string; model: string; metadata: ModelMetadata } | null>(null);
  const [refreshingMetadata, setRefreshingMetadata] = useState<string | null>(null);

  const isAdmin = user?.role === 'admin';

  useEffect(() => {
    fetchProviders();
  }, []);

  const fetchProviders = async () => {
    setLoading(true);
    try {
      const data = await llmApi.getProvidersConfig();
      setConfig(data);
      
      // Initialize selected models with first available model for each provider
      const initialModels: Record<string, string> = {};
      Object.entries(data.providers).forEach(([name, provider]) => {
        if (provider.available_models.length > 0) {
          initialModels[name] = provider.available_models[0];
        }
      });
      setSelectedModels(initialModels);
    } catch (error: any) {
      console.error('Failed to fetch providers:', error);
      toast.error(t('settings.errors.fetchFailed', 'Failed to load LLM providers'));
    } finally {
      setLoading(false);
    }
  };

  const testProvider = async (providerName: string, model: string) => {
    setTesting(providerName);
    try {
      const result = await llmApi.testGeneration({
        prompt: testPrompt,
        provider: providerName,
        model: model,
        temperature: 0.7,
        max_tokens: 50,
      });

      toast.success(
        t('settings.testSuccess', 'Test successful! Response: {{content}}', {
          content: result.content.substring(0, 50) + '...',
        })
      );
    } catch (error: any) {
      console.error('Test failed:', error);
      
      // Extract detailed error message
      const errorMessage = error.response?.data?.detail || error.message || 'Unknown error';
      
      toast.error(
        t('settings.errors.testFailed', 'Test failed') + ': ' + errorMessage,
        { duration: 5000 }
      );
    } finally {
      setTesting(null);
    }
  };

  const handleDeleteProvider = async (name: string) => {
    if (!window.confirm(t('settings.deleteConfirm', { name }))) {
      return;
    }

    setDeletingProvider(name);
    try {
      await llmApi.deleteProvider(name);
      toast.success(t('settings.deleteSuccess'));
      fetchProviders();
    } catch (error: any) {
      toast.error(t('settings.errors.deleteFailed') + ': ' + error.message);
    } finally {
      setDeletingProvider(null);
    }
  };

  const getProviderIcon = (name: string) => {
    const icons: Record<string, string> = {
      ollama: '🦙',
      vllm: '⚡',
      openai: '🤖',
      anthropic: '🧠',
    };
    return icons[name] || '🔧';
  };

  const getProviderColor = (healthy: boolean) => {
    return healthy
      ? 'border-emerald-500/30 bg-emerald-500/5'
      : 'border-red-500/30 bg-red-500/5';
  };

  const getCapabilityIcon = (capability: string): string => {
    const cap = capability.toLowerCase().replace(/_/g, '');
    const icons: Record<string, string> = {
      text: '📝',
      chat: '💬',
      code: '💻',
      functioncalling: '🔧',
      vision: '👁️',
      audio: '🎵',
      video: '🎬',
      embedding: '🔢',
      embeddings: '🔢',
      reasoning: '🧠',
      multimodal: '🎨',
      streaming: '⚡',
      systemprompt: '📋',
      imagegeneration: '🎨',
      rerank: '🔄',
      codegeneration: '💻',
    };
    return icons[cap] || '✨';  // 使用星星代替问号
  };

  const getCapabilityLabel = (capability: string): string => {
    const labels: Record<string, string> = {
      text: 'Text',
      chat: 'Chat',
      code: 'Code',
      function_calling: 'Functions',
      vision: 'Vision',
      audio: 'Audio',
      video: 'Video',
      embedding: 'Embeddings',
      embeddings: 'Embeddings',
      reasoning: 'Reasoning',
      multimodal: 'Multimodal',
      streaming: 'Streaming',
      system_prompt: 'System Prompt',
      image_generation: 'Image Gen',
      rerank: 'Rerank',
      code_generation: 'Code Gen',
    };
    return labels[capability] || capability.replace(/_/g, ' ');
  };

  const fetchModelMetadata = async (providerName: string) => {
    try {
      const metadata = await llmApi.getProviderModelsMetadata(providerName);
      setModelsMetadata((prev) => ({ ...prev, [providerName]: metadata }));
    } catch (error) {
      console.error(`Failed to fetch metadata for ${providerName}:`, error);
    }
  };

  const refreshModelMetadata = async (providerName: string) => {
    setRefreshingMetadata(providerName);
    try {
      await llmApi.refreshModelsMetadata(providerName);
      toast.success(t('settings.metadataRefreshed', 'Model metadata refreshed successfully'));
      // Re-fetch metadata
      await fetchModelMetadata(providerName);
    } catch (error: any) {
      console.error(`Failed to refresh metadata for ${providerName}:`, error);
      toast.error(
        t('settings.errors.refreshFailed', 'Failed to refresh metadata') + ': ' + 
        (error.response?.data?.detail || error.message)
      );
    } finally {
      setRefreshingMetadata(null);
    }
  };

  const getModelTypeBadge = (modelType?: string) => {
    if (!modelType) return null;
    
    const badges: Record<string, { label: string; color: string; icon: string }> = {
      chat: { label: 'Chat', color: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300', icon: '💬' },
      vision: { label: 'Vision', color: 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300', icon: '👁️' },
      reasoning: { label: 'Reasoning', color: 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300', icon: '🧠' },
      embedding: { label: 'Embedding', color: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300', icon: '🔢' },
      rerank: { label: 'Rerank', color: 'bg-cyan-100 dark:bg-cyan-900/30 text-cyan-700 dark:text-cyan-300', icon: '🔄' },
      code: { label: 'Code', color: 'bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300', icon: '💻' },
      image_generation: { label: 'Image Gen', color: 'bg-pink-100 dark:bg-pink-900/30 text-pink-700 dark:text-pink-300', icon: '🎨' },
    };
    
    const badge = badges[modelType] || badges.chat;
    
    return (
      <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded ${badge.color}`}>
        <span>{badge.icon}</span>
        <span>{badge.label}</span>
      </span>
    );
  };

  const toggleProviderExpanded = (providerName: string) => {
    const isExpanding = !expandedProviders[providerName];
    setExpandedProviders((prev) => ({ ...prev, [providerName]: isExpanding }));
    
    // Fetch metadata when expanding if not already loaded
    if (isExpanding && !modelsMetadata[providerName]) {
      fetchModelMetadata(providerName);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-zinc-600 dark:text-zinc-400">
            {t('settings.loading', 'Loading settings...')}
          </p>
        </div>
      </div>
    );
  }

  if (!config) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <p className="text-zinc-600 dark:text-zinc-400">
            {t('settings.errors.loadFailed', 'Failed to load settings')}
          </p>
          <button
            onClick={fetchProviders}
            className="mt-4 px-4 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors"
          >
            {t('settings.retry', 'Retry')}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-zinc-900 dark:text-zinc-100">
            {t('settings.llm.title', 'LLM Providers')}
          </h2>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            {t('settings.llm.subtitle', 'Manage your AI model providers and configurations')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {isAdmin && (
            <>
              <button
                onClick={() => setShowAddModal(true)}
                className="px-4 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors flex items-center gap-2"
              >
                <Plus className="w-5 h-5" />
                {t('settings.addProvider')}
              </button>
            </>
          )}

        </div>
      </div>

      {/* Configuration Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 bg-white/50 dark:bg-zinc-800/50 backdrop-blur-sm border border-zinc-200 dark:border-zinc-700 rounded-xl">
          <div className="flex items-center gap-2 mb-2">
            <Cpu className="w-5 h-5 text-emerald-500" />
            <span className="text-sm font-medium text-zinc-600 dark:text-zinc-400">
              {t('settings.defaultProvider', 'Default Provider')}
            </span>
          </div>
          <p className="text-xl font-bold text-zinc-900 dark:text-zinc-100 capitalize">
            {config.default_provider}
          </p>
        </div>

        <div className="p-4 bg-white/50 dark:bg-zinc-800/50 backdrop-blur-sm border border-zinc-200 dark:border-zinc-700 rounded-xl">
          <div className="flex items-center gap-2 mb-2">
            <CheckCircle2 className="w-5 h-5 text-emerald-500" />
            <span className="text-sm font-medium text-zinc-600 dark:text-zinc-400">
              {t('settings.activeProviders', 'Active Providers')}
            </span>
          </div>
          <p className="text-xl font-bold text-zinc-900 dark:text-zinc-100">
            {Object.values(config.providers).filter((p) => p.healthy).length} /{' '}
            {Object.keys(config.providers).length}
          </p>
        </div>

        <div className="p-4 bg-white/50 dark:bg-zinc-800/50 backdrop-blur-sm border border-zinc-200 dark:border-zinc-700 rounded-xl">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-5 h-5 text-emerald-500" />
            <span className="text-sm font-medium text-zinc-600 dark:text-zinc-400">
              {t('settings.fallbackEnabled', 'Fallback')}
            </span>
          </div>
          <p className="text-xl font-bold text-zinc-900 dark:text-zinc-100">
            {config.fallback_enabled
              ? t('settings.enabled', 'Enabled')
              : t('settings.disabled', 'Disabled')}
          </p>
        </div>
      </div>

      {/* Providers List */}
      <div className="space-y-4">
        <h3 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          {t('settings.providers', 'Providers')}
        </h3>

        {Object.entries(config.providers).map(([name, provider]) => (
          <div
            key={name}
            className={`p-6 bg-white/50 dark:bg-zinc-800/50 backdrop-blur-sm border-2 rounded-xl transition-all ${getProviderColor(
              provider.healthy
            )}`}
          >
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <span className="text-3xl">{getProviderIcon(name)}</span>
                <div>
                  <div className="flex items-center gap-2">
                    <h4 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 capitalize">
                      {name}
                    </h4>
                    {provider.is_config_based && (
                      <span className="px-2 py-0.5 text-xs font-medium bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded">
                        {t('settings.systemBuiltin', 'System')}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    {provider.healthy ? (
                      <>
                        <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                        <span className="text-sm text-emerald-600 dark:text-emerald-400">
                          {t('settings.healthy', 'Healthy')}
                        </span>
                      </>
                    ) : (
                      <>
                        <XCircle className="w-4 h-4 text-red-500" />
                        <span className="text-sm text-red-600 dark:text-red-400">
                          {t('settings.unhealthy', 'Unhealthy')}
                        </span>
                      </>
                    )}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {isAdmin && (
                  <>
                    <button
                      onClick={async () => {
                        if (provider.is_config_based) {
                          toast.error(
                            t(
                              'settings.cannotEditConfigProvider',
                              'Cannot edit config.yaml provider. Please edit config.yaml file directly.'
                            )
                          );
                          return;
                        }

                        try {
                          const providerDetail = await llmApi.getProviderDetail(name);
                          setEditingProvider(providerDetail);
                        } catch {
                          toast.error(t('settings.errors.fetchProviderFailed'));
                        }
                      }}
                      disabled={provider.is_config_based}
                      className="p-2 hover:bg-white/50 dark:hover:bg-zinc-700/50 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      title={
                        provider.is_config_based
                          ? t('settings.cannotEditConfigProvider')
                          : t('settings.editProvider')
                      }
                    >
                      <Edit className="w-4 h-4 text-zinc-600 dark:text-zinc-400" />
                    </button>
                    <button
                      onClick={() => handleDeleteProvider(name)}
                      disabled={deletingProvider === name || provider.is_config_based}
                      className="p-2 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      title={
                        provider.is_config_based
                          ? t('settings.cannotDeleteConfigProvider')
                          : t('settings.deleteProvider')
                      }
                    >
                      <Trash2 className="w-4 h-4 text-red-600 dark:text-red-400" />
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Available Models */}
            {provider.available_models.length > 0 ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-zinc-600 dark:text-zinc-400">
                      {t('settings.availableModels', 'Available Models')} (
                      {provider.available_models.length})
                    </p>
                    <button
                      onClick={() => toggleProviderExpanded(name)}
                      className="p-1 hover:bg-zinc-200 dark:hover:bg-zinc-700 rounded transition-colors"
                      title={expandedProviders[name] ? t('common.hide', 'Hide details') : t('common.show', 'Show details')}
                    >
                      {expandedProviders[name] ? (
                        <ChevronUp className="w-4 h-4 text-zinc-600 dark:text-zinc-400" />
                      ) : (
                        <ChevronDown className="w-4 h-4 text-zinc-600 dark:text-zinc-400" />
                      )}
                    </button>
                    {/* Refresh Metadata Button - Admin Only */}
                    {/* Debug: isAdmin={isAdmin}, expanded={expandedProviders[name]} */}
                    {isAdmin && expandedProviders[name] && (
                      <button
                        onClick={() => refreshModelMetadata(name)}
                        disabled={refreshingMetadata === name}
                        className="px-3 py-1.5 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 text-sm font-medium shadow-sm"
                        title={t('settings.refreshMetadataTooltip', 'Refresh model metadata from provider API')}
                      >
                        {refreshingMetadata === name ? (
                          <>
                            <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                            <span>{t('settings.refreshing', 'Refreshing...')}</span>
                          </>
                        ) : (
                          <>
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                            </svg>
                            <span>{t('settings.refreshMetadata', 'Refresh Metadata')}</span>
                          </>
                        )}
                      </button>
                    )}
                  </div>
                  {provider.healthy && (
                    <div className="flex items-center gap-2">
                      <select
                        value={selectedModels[name] || provider.available_models[0]}
                        onChange={(e) =>
                          setSelectedModels({ ...selectedModels, [name]: e.target.value })
                        }
                        className="px-3 py-1.5 bg-white dark:bg-zinc-700 border border-zinc-300 dark:border-zinc-600 rounded-lg text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                      >
                        {provider.available_models.map((model) => (
                          <option key={model} value={model}>
                            {model}
                          </option>
                        ))}
                      </select>
                      <button
                        onClick={() =>
                          testProvider(name, selectedModels[name] || provider.available_models[0])
                        }
                        disabled={testing === name}
                        className="px-4 py-1.5 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 text-sm"
                      >
                        {testing === name ? (
                          <>
                            <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                            {t('settings.testing', 'Testing...')}
                          </>
                        ) : (
                          <>
                            <Zap className="w-4 h-4" />
                            {t('settings.test', 'Test')}
                          </>
                        )}
                      </button>
                    </div>
                  )}
                </div>
                
                {/* Model Tags */}
                <div className="flex flex-wrap gap-2">
                  {provider.available_models.map((model) => {
                    const metadata = modelsMetadata[name]?.models[model];
                    return (
                      <div
                        key={model}
                        className={`group relative px-3 py-1.5 rounded-lg text-sm font-mono transition-all cursor-pointer ${
                          selectedModels[name] === model
                            ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 ring-2 ring-emerald-500'
                            : 'bg-zinc-100 dark:bg-zinc-700 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-600'
                        }`}
                        onClick={() => setSelectedModels({ ...selectedModels, [name]: model })}
                      >
                        <div className="flex items-center gap-1.5">
                          <span>{model}</span>
                          {metadata && metadata.capabilities.length > 0 && (
                            <div className="flex items-center gap-0.5">
                              {metadata.capabilities.slice(0, 3).map((cap) => (
                                <span key={cap} className="text-xs" title={getCapabilityLabel(cap)}>
                                  {getCapabilityIcon(cap)}
                                </span>
                              ))}
                              {metadata.capabilities.length > 3 && (
                                <span className="text-xs text-zinc-500">+{metadata.capabilities.length - 3}</span>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Expanded Model Details */}
                {expandedProviders[name] && modelsMetadata[name] && (
                  <div className="mt-4 space-y-3">
                    {provider.available_models.map((model) => {
                      const metadata = modelsMetadata[name]?.models[model];
                      if (!metadata) return null;

                      // Check if this is an embedding or rerank model
                      const isEmbeddingOrRerank = metadata.model_type === 'embedding' || metadata.model_type === 'rerank';

                      return (
                        <div
                          key={model}
                          className="p-4 bg-white dark:bg-zinc-800 rounded-lg border border-zinc-200 dark:border-zinc-700"
                        >
                          {/* Header with Edit Button */}
                          <div className="flex items-start justify-between mb-3">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-1 flex-wrap">
                                <h5 className="font-mono text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                                  {metadata.display_name || model}
                                </h5>
                                {getModelTypeBadge(metadata.model_type)}
                                {metadata.deprecated && (
                                  <span className="px-2 py-0.5 text-xs bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded">
                                    Deprecated
                                  </span>
                                )}
                              </div>
                              {metadata.description && (
                                <p className="text-xs text-zinc-600 dark:text-zinc-400">
                                  {metadata.description}
                                </p>
                              )}
                            </div>
                            {isAdmin && (
                              <button
                                onClick={() => setEditingModel({ provider: name, model, metadata })}
                                className="p-2 hover:bg-zinc-100 dark:hover:bg-zinc-700 rounded-lg transition-colors"
                                title={t('settings.editProvider', 'Edit model metadata')}
                              >
                                <Edit className="w-4 h-4 text-zinc-600 dark:text-zinc-400" />
                              </button>
                            )}
                          </div>

                          {/* Model Properties Grid - Different for embedding/rerank models */}
                          {!isEmbeddingOrRerank && (
                            <div className="grid grid-cols-2 gap-3 mb-3">
                              {metadata.context_window && (
                                <div className="p-2 bg-zinc-50 dark:bg-zinc-800/50 rounded">
                                  <div className="text-xs text-zinc-500 dark:text-zinc-400 mb-0.5">{t('settings.modelDetails.contextWindow')}</div>
                                  <div className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                                    {metadata.context_window.toLocaleString()}
                                  </div>
                                  <div className="text-xs text-zinc-500 dark:text-zinc-400">{t('settings.modelDetails.tokens')}</div>
                                </div>
                              )}
                              {metadata.max_output_tokens && (
                                <div className="p-2 bg-zinc-50 dark:bg-zinc-800/50 rounded">
                                  <div className="text-xs text-zinc-500 dark:text-zinc-400 mb-0.5">{t('settings.modelDetails.maxOutput')}</div>
                                  <div className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                                    {metadata.max_output_tokens.toLocaleString()}
                                  </div>
                                  <div className="text-xs text-zinc-500 dark:text-zinc-400">{t('settings.modelDetails.tokens')}</div>
                                </div>
                              )}
                              <div className="p-2 bg-zinc-50 dark:bg-zinc-800/50 rounded">
                                <div className="text-xs text-zinc-500 dark:text-zinc-400 mb-0.5">{t('settings.modelDetails.temperature')}</div>
                                <div className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                                  {metadata.default_temperature}
                                </div>
                                <div className="text-xs text-zinc-500 dark:text-zinc-400">
                                  {t('settings.modelDetails.range')}: {metadata.temperature_range[0]}-{metadata.temperature_range[1]}
                                </div>
                              </div>
                              {metadata.version && (
                                <div className="p-2 bg-zinc-50 dark:bg-zinc-800/50 rounded">
                                  <div className="text-xs text-zinc-500 dark:text-zinc-400 mb-0.5">{t('settings.modelDetails.version')}</div>
                                  <div className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                                    {metadata.version}
                                  </div>
                                  {metadata.release_date && (
                                    <div className="text-xs text-zinc-500 dark:text-zinc-400">{metadata.release_date}</div>
                                  )}
                                </div>
                              )}
                            </div>
                          )}

                          {/* Embedding/Rerank Model Properties */}
                          {isEmbeddingOrRerank && (
                            <div className="mb-3">
                              <div className="grid grid-cols-2 gap-3 mb-3">
                                <div className="p-2 bg-zinc-50 dark:bg-zinc-800/50 rounded">
                                  <div className="text-xs text-zinc-500 dark:text-zinc-400 mb-0.5">{t('settings.modelDetails.type')}</div>
                                  <div className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                                    {metadata.model_type === 'embedding' ? t('settings.modelDetails.textEmbedding') : t('settings.modelDetails.reranking')}
                                  </div>
                                </div>
                                {metadata.model_type === 'embedding' && metadata.embedding_dimension && (
                                  <div className="p-2 bg-zinc-50 dark:bg-zinc-800/50 rounded">
                                    <div className="text-xs text-zinc-500 dark:text-zinc-400 mb-0.5">{t('settings.modelDetails.embeddingDimension')}</div>
                                    <div className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                                      {metadata.embedding_dimension.toLocaleString()}
                                    </div>
                                    <div className="text-xs text-zinc-500 dark:text-zinc-400">{t('settings.modelDetails.dimensions')}</div>
                                  </div>
                                )}
                                {metadata.context_window && (
                                  <div className="p-2 bg-zinc-50 dark:bg-zinc-800/50 rounded">
                                    <div className="text-xs text-zinc-500 dark:text-zinc-400 mb-0.5">{t('settings.modelDetails.maxInputTokens')}</div>
                                    <div className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                                      {metadata.context_window.toLocaleString()}
                                    </div>
                                    <div className="text-xs text-zinc-500 dark:text-zinc-400">{t('settings.modelDetails.tokens')}</div>
                                  </div>
                                )}
                                {metadata.version && (
                                  <div className="p-2 bg-zinc-50 dark:bg-zinc-800/50 rounded">
                                    <div className="text-xs text-zinc-500 dark:text-zinc-400 mb-0.5">{t('settings.modelDetails.version')}</div>
                                    <div className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                                      {metadata.version}
                                    </div>
                                    {metadata.release_date && (
                                      <div className="text-xs text-zinc-500 dark:text-zinc-400">{metadata.release_date}</div>
                                    )}
                                  </div>
                                )}
                              </div>
                            </div>
                          )}

                          {/* Features - Only show for chat/vision/reasoning models */}
                          {!isEmbeddingOrRerank && (
                            <div className="mb-3">
                              <div className="text-xs font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide mb-2">
                                {t('settings.modelDetails.features')}
                              </div>
                              <div className="flex flex-wrap gap-2">
                                {metadata.supports_vision && (
                                  <span className="inline-flex items-center gap-1 px-2 py-1 bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 rounded text-xs">
                                    👁️ {t('settings.modelDetails.vision')}
                                  </span>
                                )}
                                {metadata.supports_reasoning && (
                                  <span className="inline-flex items-center gap-1 px-2 py-1 bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 rounded text-xs">
                                    🧠 {t('settings.modelDetails.reasoning')}
                                  </span>
                                )}
                                {metadata.supports_function_calling && (
                                  <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded text-xs">
                                    🔧 {t('settings.modelDetails.functions')}
                                  </span>
                                )}
                                {metadata.supports_streaming && (
                                  <span className="inline-flex items-center gap-1 px-2 py-1 bg-cyan-100 dark:bg-cyan-900/30 text-cyan-700 dark:text-cyan-300 rounded text-xs">
                                    ⚡ {t('settings.modelDetails.streaming')}
                                  </span>
                                )}
                                {metadata.supports_system_prompt && (
                                  <span className="inline-flex items-center gap-1 px-2 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded text-xs">
                                    📋 {t('settings.modelDetails.systemPrompt')}
                                  </span>
                                )}
                              </div>
                            </div>
                          )}

                          {/* Pricing */}
                          {(metadata.input_price_per_1m || metadata.output_price_per_1m) && (
                            <div className="pt-3 border-t border-zinc-200 dark:border-zinc-700">
                              <div className="text-xs font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide mb-2">
                                {t('settings.modelDetails.pricing')}
                              </div>
                              <div className="flex gap-4 text-xs">
                                {metadata.input_price_per_1m && (
                                  <div>
                                    <span className="text-zinc-600 dark:text-zinc-400">{t('settings.modelDetails.input')}: </span>
                                    <span className="font-semibold text-zinc-900 dark:text-zinc-100">
                                      ${metadata.input_price_per_1m.toFixed(2)}
                                    </span>
                                  </div>
                                )}
                                {metadata.output_price_per_1m && (
                                  <div>
                                    <span className="text-zinc-600 dark:text-zinc-400">{t('settings.modelDetails.output')}: </span>
                                    <span className="font-semibold text-zinc-900 dark:text-zinc-100">
                                      ${metadata.output_price_per_1m.toFixed(2)}
                                    </span>
                                  </div>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            ) : (
              <p className="text-sm text-zinc-500 dark:text-zinc-500 italic">
                {t('settings.noModels', 'No models available')}
              </p>
            )}
          </div>
        ))}
      </div>

      {/* Test Prompt Input */}
      <div className="p-6 bg-white/50 dark:bg-zinc-800/50 backdrop-blur-sm border border-zinc-200 dark:border-zinc-700 rounded-xl">
        <h3 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100 mb-4">
          {t('settings.testPrompt', 'Test Prompt')}
        </h3>
        <input
          type="text"
          value={testPrompt}
          onChange={(e) => setTestPrompt(e.target.value)}
          className="w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all"
          placeholder={t('settings.testPromptPlaceholder', 'Enter a test prompt...')}
        />
        <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-500">
          {t('settings.testPromptHint', 'This prompt will be used when testing providers')}
        </p>
      </div>

      {/* Modals */}
      <AddProviderModal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        onSuccess={fetchProviders}
      />

      <AddProviderModal
        isOpen={!!editingProvider}
        onClose={() => setEditingProvider(null)}
        onSuccess={fetchProviders}
        editProvider={editingProvider}
      />

      {editingModel && (
        <EditModelModal
          isOpen={true}
          onClose={() => setEditingModel(null)}
          metadata={editingModel.metadata}
          onSave={async (updated) => {
            try {
              await llmApi.updateModelMetadata(editingModel.provider, editingModel.model, updated);
              // Refresh metadata
              await fetchModelMetadata(editingModel.provider);
              toast.success(t('settings.metadataUpdated', 'Model metadata updated successfully'));
            } catch (error: any) {
              throw new Error(error.response?.data?.detail || error.message || 'Failed to update metadata');
            }
          }}
        />
      )}
    </div>
  );
};
