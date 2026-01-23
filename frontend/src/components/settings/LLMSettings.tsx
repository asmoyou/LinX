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
  Info,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { useAuthStore } from '../../stores';
import { llmApi } from '../../api';
import type { LLMConfig, ModelMetadata, ProviderModelsMetadata } from '../../api/llm';
import { AddProviderModal } from '../AddProviderModal';

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
    const icons: Record<string, string> = {
      text: '📝',
      chat: '💬',
      code: '💻',
      function_calling: '🔧',
      vision: '👁️',
      audio: '🎵',
      video: '🎬',
      embedding: '🔢',
      reasoning: '🧠',
      multimodal: '🎨',
    };
    return icons[capability] || '❓';
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
      reasoning: 'Reasoning',
      multimodal: 'Multimodal',
    };
    return labels[capability] || capability;
  };

  const fetchModelMetadata = async (providerName: string) => {
    try {
      const metadata = await llmApi.getProviderModelsMetadata(providerName);
      setModelsMetadata((prev) => ({ ...prev, [providerName]: metadata }));
    } catch (error) {
      console.error(`Failed to fetch metadata for ${providerName}:`, error);
    }
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
                        } catch (error) {
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
                      title={expandedProviders[name] ? 'Hide details' : 'Show details'}
                    >
                      {expandedProviders[name] ? (
                        <ChevronUp className="w-4 h-4 text-zinc-600 dark:text-zinc-400" />
                      ) : (
                        <ChevronDown className="w-4 h-4 text-zinc-600 dark:text-zinc-400" />
                      )}
                    </button>
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
                  <div className="mt-4 space-y-3 p-4 bg-zinc-50 dark:bg-zinc-800/50 rounded-lg border border-zinc-200 dark:border-zinc-700">
                    {provider.available_models.map((model) => {
                      const metadata = modelsMetadata[name]?.models[model];
                      if (!metadata) return null;

                      return (
                        <div
                          key={model}
                          className="p-3 bg-white dark:bg-zinc-800 rounded-lg border border-zinc-200 dark:border-zinc-700"
                        >
                          <div className="flex items-start justify-between mb-2">
                            <div>
                              <h5 className="font-mono text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                                {metadata.display_name || model}
                              </h5>
                              {metadata.description && (
                                <p className="text-xs text-zinc-600 dark:text-zinc-400 mt-1">
                                  {metadata.description}
                                </p>
                              )}
                            </div>
                            {metadata.deprecated && (
                              <span className="px-2 py-0.5 text-xs bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded">
                                Deprecated
                              </span>
                            )}
                          </div>

                          {/* Capabilities */}
                          <div className="flex flex-wrap gap-1.5 mb-2">
                            {metadata.capabilities.map((cap) => (
                              <span
                                key={cap}
                                className="px-2 py-0.5 text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded flex items-center gap-1"
                              >
                                <span>{getCapabilityIcon(cap)}</span>
                                <span>{getCapabilityLabel(cap)}</span>
                              </span>
                            ))}
                          </div>

                          {/* Technical Details */}
                          <div className="grid grid-cols-2 gap-2 text-xs">
                            {metadata.context_window && (
                              <div className="flex items-center gap-1 text-zinc-600 dark:text-zinc-400">
                                <span className="font-medium">Context:</span>
                                <span>{metadata.context_window.toLocaleString()} tokens</span>
                              </div>
                            )}
                            {metadata.max_output_tokens && (
                              <div className="flex items-center gap-1 text-zinc-600 dark:text-zinc-400">
                                <span className="font-medium">Max Output:</span>
                                <span>{metadata.max_output_tokens.toLocaleString()} tokens</span>
                              </div>
                            )}
                            <div className="flex items-center gap-1 text-zinc-600 dark:text-zinc-400">
                              <span className="font-medium">Temperature:</span>
                              <span>
                                {metadata.default_temperature} ({metadata.temperature_range[0]}-
                                {metadata.temperature_range[1]})
                              </span>
                            </div>
                            <div className="flex items-center gap-1 text-zinc-600 dark:text-zinc-400">
                              <span className="font-medium">Streaming:</span>
                              <span>{metadata.supports_streaming ? '✓' : '✗'}</span>
                            </div>
                            {(metadata.input_price_per_1k || metadata.output_price_per_1k) && (
                              <div className="col-span-2 flex items-center gap-2 text-zinc-600 dark:text-zinc-400">
                                <span className="font-medium">Pricing:</span>
                                {metadata.input_price_per_1k && (
                                  <span>In: ${metadata.input_price_per_1k}/1K</span>
                                )}
                                {metadata.output_price_per_1k && (
                                  <span>Out: ${metadata.output_price_per_1k}/1K</span>
                                )}
                              </div>
                            )}
                          </div>
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
    </div>
  );
};
