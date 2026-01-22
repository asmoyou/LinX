import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { 
  Settings as SettingsIcon, 
  Cpu, 
  CheckCircle2, 
  XCircle, 
  RefreshCw,
  Zap,
  AlertCircle,
  Plus,
  Edit,
  Trash2
} from 'lucide-react';
import toast from 'react-hot-toast';
import { useAuthStore } from '../stores';
import { AddProviderModal } from '../components/AddProviderModal';

interface ProviderStatus {
  name: string;
  healthy: boolean;
  available_models: string[];
  is_config_based?: boolean;  // True if from config.yaml, cannot be deleted
}

interface LLMConfig {
  providers: Record<string, ProviderStatus>;
  default_provider: string;
  fallback_enabled: boolean;
  model_mapping: Record<string, Record<string, string>>;
}

export const Settings: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { token, isAuthenticated, user } = useAuthStore();
  const [config, setConfig] = useState<LLMConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [testing, setTesting] = useState<string | null>(null);
  const [testPrompt, setTestPrompt] = useState('Hello, how are you?');
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingProvider, setEditingProvider] = useState<any>(null);
  const [deletingProvider, setDeletingProvider] = useState<string | null>(null);

  const isAdmin = user?.role === 'admin';

  useEffect(() => {
    // 检查认证状态
    if (!isAuthenticated || !token) {
      toast.error(t('settings.errors.notAuthenticated', 'Please login to access settings'));
      navigate('/login');
      return;
    }
    
    // 已认证，获取数据
    fetchProviders();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // 只在组件挂载时执行一次

  const fetchProviders = async () => {
    if (!token) {
      return;
    }
    
    setLoading(true);
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000); // 10秒超时

      const response = await fetch('/api/v1/llm/providers', {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        // 统一的错误格式: { error: "error_code", message: "error message" }
        const errorMessage = errorData.message || errorData.detail || 'Failed to fetch providers';
        throw new Error(errorMessage);
      }

      const data = await response.json();
      setConfig(data);
    } catch (error: any) {
      console.error('Failed to fetch providers:', error);
      if (error.name === 'AbortError') {
        toast.error(t('settings.errors.timeout', 'Request timeout. Please check if backend is running.'));
      } else {
        toast.error(t('settings.errors.fetchFailed', 'Failed to load LLM providers') + ': ' + error.message);
      }
    } finally {
      setLoading(false);
    }
  };

  const testProvider = async (providerName: string, model: string) => {
    if (!token) return;
    
    setTesting(providerName);
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 30000); // 30秒超时（LLM 可能需要更长时间）

      const response = await fetch('/api/v1/llm/test', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          prompt: testPrompt,
          provider: providerName,
          model: model,
          temperature: 0.7,
          max_tokens: 50,
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        // 统一的错误格式: { error: "error_code", message: "error message" }
        const errorMessage = errorData.message || errorData.detail || 'Test failed';
        throw new Error(errorMessage);
      }

      const data = await response.json();
      toast.success(
        t('settings.testSuccess', 'Test successful! Response: {{content}}', {
          content: data.content.substring(0, 50) + '...',
        })
      );
    } catch (error: any) {
      console.error('Test failed:', error);
      if (error.name === 'AbortError') {
        toast.error(t('settings.errors.testTimeout', 'Test timeout. The model may be slow or unavailable.'));
      } else {
        toast.error(t('settings.errors.testFailed', 'Test failed'));
      }
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
      const response = await fetch(`/api/v1/llm/providers/${name}`, {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || errorData.detail || 'Delete failed');
      }

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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex flex-col items-center gap-4">
          <RefreshCw className="w-8 h-8 text-emerald-500 animate-spin" />
          <p className="text-zinc-600 dark:text-zinc-400">
            {t('settings.loading', 'Loading settings...')}
          </p>
        </div>
      </div>
    );
  }

  if (!config) {
    return (
      <div className="flex items-center justify-center h-full">
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
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-gradient-to-br from-emerald-500/20 to-teal-500/20 rounded-xl">
            <SettingsIcon className="w-6 h-6 text-emerald-500" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">
              {t('settings.title', 'LLM Settings')}
            </h1>
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              {t('settings.subtitle', 'Manage your AI model providers and configurations')}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isAdmin && (
            <button
              onClick={() => setShowAddModal(true)}
              className="px-4 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors flex items-center gap-2"
            >
              <Plus className="w-5 h-5" />
              {t('settings.addProvider')}
            </button>
          )}
          <button
            onClick={fetchProviders}
            className="p-2 hover:bg-white/50 dark:hover:bg-zinc-800/50 rounded-lg transition-colors"
            title={t('settings.refresh', 'Refresh')}
          >
            <RefreshCw className="w-5 h-5 text-zinc-600 dark:text-zinc-400" />
          </button>
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
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          {t('settings.providers', 'Providers')}
        </h2>

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
                  <h3 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 capitalize">
                    {name}
                  </h3>
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
                      onClick={() => setEditingProvider({ name, ...provider })}
                      className="p-2 hover:bg-white/50 dark:hover:bg-zinc-700/50 rounded-lg transition-colors"
                      title={t('settings.editProvider')}
                    >
                      <Edit className="w-4 h-4 text-zinc-600 dark:text-zinc-400" />
                    </button>
                    <button
                      onClick={() => handleDeleteProvider(name)}
                      disabled={deletingProvider === name || provider.is_config_based}
                      className="p-2 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      title={
                        provider.is_config_based
                          ? t('settings.cannotDeleteConfigProvider', 'Cannot delete config.yaml provider')
                          : t('settings.deleteProvider')
                      }
                    >
                      <Trash2 className="w-4 h-4 text-red-600 dark:text-red-400" />
                    </button>
                  </>
                )}
                {provider.healthy && provider.available_models.length > 0 && (
                  <button
                    onClick={() => testProvider(name, provider.available_models[0])}
                    disabled={testing === name}
                    className="px-4 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                  >
                    {testing === name ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" />
                        {t('settings.testing', 'Testing...')}
                      </>
                    ) : (
                      <>
                        <Zap className="w-4 h-4" />
                        {t('settings.test', 'Test')}
                      </>
                    )}
                  </button>
                )}
              </div>
            </div>

            {/* Available Models */}
            {provider.available_models.length > 0 ? (
              <div>
                <p className="text-sm font-medium text-zinc-600 dark:text-zinc-400 mb-2">
                  {t('settings.availableModels', 'Available Models')} ({provider.available_models.length})
                </p>
                <div className="flex flex-wrap gap-2">
                  {provider.available_models.map((model) => (
                    <span
                      key={model}
                      className="px-3 py-1 bg-zinc-100 dark:bg-zinc-700 text-zinc-700 dark:text-zinc-300 rounded-full text-sm font-mono"
                    >
                      {model}
                    </span>
                  ))}
                </div>
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

