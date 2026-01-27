import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Zap, AlertCircle, CheckCircle2, Eye, EyeOff, Plus, Trash2 } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import toast from 'react-hot-toast';
import { llmApi } from '../api';

const providerSchema = z.object({
  name: z
    .string()
    .min(1, 'settings.errors.nameRequired')
    .regex(/^[a-zA-Z0-9_-]+$/, 'settings.errors.nameInvalid'),
  protocol: z.enum(['ollama', 'openai_compatible']),
  base_url: z
    .string()
    .min(1, 'settings.errors.baseUrlRequired')
    .regex(/^https?:\/\//, 'settings.errors.baseUrlInvalid'),
  api_key: z.string().optional(),
  timeout: z.number().min(5).max(300),
  max_retries: z.number().min(0).max(10),
  selected_models: z.array(z.string()).min(1, 'settings.errors.noModelsSelected'),
});

type ProviderFormData = z.infer<typeof providerSchema>;

interface AddProviderModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  editProvider?: {
    name: string;
    protocol: string;
    base_url: string;
    timeout: number;
    max_retries: number;
    selected_models: string[];
    has_api_key: boolean;
    is_config_based?: boolean;
  };
}

export const AddProviderModal: React.FC<AddProviderModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  editProvider,
}) => {
  const { t } = useTranslation();
  const [testingConnection, setTestingConnection] = useState(false);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [connectionTested, setConnectionTested] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [manualModelInput, setManualModelInput] = useState('');
  const [manualModels, setManualModels] = useState<string[]>([]);
  const [isConfigBased, setIsConfigBased] = useState(false);
  const [modelSearchQuery, setModelSearchQuery] = useState('');

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ProviderFormData>({
    resolver: zodResolver(providerSchema),
    defaultValues: {
      protocol: 'ollama',
      timeout: 30,
      max_retries: 3,
      selected_models: [],
    },
  });

  const protocol = watch('protocol');
  const selectedModels = watch('selected_models') || [];

  // 编辑模式下，初始化表单和手动模型列表
  useEffect(() => {
    if (editProvider) {
      // 记录是否是 config.yaml 提供商
      setIsConfigBased(editProvider.is_config_based || false);
      
      // 重置表单为编辑模式的值
      reset({
        name: editProvider.name,
        protocol: editProvider.protocol as 'ollama' | 'openai_compatible',
        base_url: editProvider.base_url,
        api_key: '',
        timeout: editProvider.timeout,
        max_retries: editProvider.max_retries,
        selected_models: editProvider.selected_models || [],
      });
      
      // 设置手动模型列表
      if (editProvider.selected_models && editProvider.selected_models.length > 0) {
        setManualModels(editProvider.selected_models);
        setConnectionTested(true);
      }
    } else {
      // 新建模式，重置为默认值
      setIsConfigBased(false);
      reset({
        protocol: 'ollama',
        timeout: 30,
        max_retries: 3,
        selected_models: [],
      });
      setManualModels([]);
      setConnectionTested(false);
      setAvailableModels([]);
    }
  }, [editProvider, reset]);

  const testConnection = async () => {
    const base_url = watch('base_url');
    const api_key = watch('api_key');
    const timeout = watch('timeout');

    if (!base_url) {
      toast.error(t('settings.errors.baseUrlRequired'));
      return;
    }

    // 新建模式下，OpenAI 兼容协议必须提供 API Key
    if (protocol === 'openai_compatible' && !api_key && !editProvider) {
      toast.error(t('settings.errors.apiKeyRequired'));
      return;
    }

    setTestingConnection(true);
    try {
      const data = await llmApi.testConnection({
        protocol,
        base_url,
        api_key: api_key || undefined,
        timeout,
      });

      if (data.success && data.available_models && data.available_models.length > 0) {
        setAvailableModels(data.available_models);
        setConnectionTested(true);
        toast.success(
          t('settings.connectionSuccess', { count: data.available_models.length })
        );
      } else {
        // 连接失败，显示详细错误信息
        const errorMsg = data.error || data.message || t('settings.connectionFailed');
        toast.error(`${t('settings.connectionFailed')}: ${errorMsg}`);
        setConnectionTested(false);
        setAvailableModels([]);
      }
    } catch (error: any) {
      // API client 已经处理了 500 错误，这里只处理其他错误
      const errorMsg = error.response?.data?.detail || error.message || t('settings.errors.networkError');
      toast.error(`${t('settings.errors.testFailed')}: ${errorMsg}`);
      setConnectionTested(false);
      setAvailableModels([]);
    } finally {
      setTestingConnection(false);
    }
  };

  const addManualModel = () => {
    const trimmed = manualModelInput.trim();
    if (!trimmed) {
      toast.error(t('settings.errors.modelNameEmpty'));
      return;
    }
    
    if (manualModels.includes(trimmed)) {
      toast.error(t('settings.errors.modelAlreadyExists'));
      return;
    }

    const newModels = [...manualModels, trimmed];
    setManualModels(newModels);
    
    // 自动选中新添加的模型
    if (!selectedModels.includes(trimmed)) {
      setValue('selected_models', [...selectedModels, trimmed]);
    }
    
    setManualModelInput('');
    toast.success(t('settings.modelAdded'));
  };

  const removeManualModel = (model: string) => {
    setManualModels(manualModels.filter(m => m !== model));
    setValue('selected_models', selectedModels.filter(m => m !== model));
  };

  // 合并自动获取的模型和手动添加的模型
  const allModels = [...new Set([...availableModels, ...manualModels])];
  
  // Filter models based on search query
  const filteredModels = allModels.filter(model =>
    model.toLowerCase().includes(modelSearchQuery.toLowerCase())
  );
  
  // Select all filtered models
  const handleSelectAll = () => {
    const newSelected = [...new Set([...selectedModels, ...filteredModels])];
    setValue('selected_models', newSelected);
  };
  
  // Deselect all filtered models
  const handleDeselectAll = () => {
    const newSelected = selectedModels.filter(m => !filteredModels.includes(m));
    setValue('selected_models', newSelected);
  };

  const onSubmit = async (data: ProviderFormData) => {
    try {
      if (editProvider) {
        // 编辑模式
        const payload: any = {
          base_url: data.base_url,
          selected_models: data.selected_models,
          timeout: data.timeout,
          max_retries: data.max_retries,
          enabled: true,
        };
        
        // 如果提供了新的 API key，则更新
        if (data.api_key) {
          payload.api_key = data.api_key;
        }
        
        await llmApi.updateProvider(editProvider.name, payload);
        toast.success(t('settings.updateSuccess'));
      } else {
        // 新建模式
        await llmApi.createProvider({
          name: data.name,
          protocol: data.protocol,
          base_url: data.base_url,
          selected_models: data.selected_models,
          api_key: data.api_key,
          timeout: data.timeout,
          max_retries: data.max_retries,
        });
        toast.success(t('settings.createSuccess'));
      }
      
      onSuccess();
      onClose();
    } catch (error: any) {
      const errorMsg = error.response?.data?.detail || error.message || 'Unknown error';
      toast.error(
        (editProvider ? t('settings.errors.updateFailed') : t('settings.errors.createFailed')) +
          ': ' +
          errorMsg
      );
    }
  };

  const toggleModel = (model: string) => {
    const current = selectedModels;
    if (current.includes(model)) {
      setValue(
        'selected_models',
        current.filter((m) => m !== model)
      );
    } else {
      setValue('selected_models', [...current, model]);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm overflow-auto" style={{ marginLeft: 'var(--sidebar-width, 0px)' }}>
      <div className="w-full max-w-2xl my-auto bg-white dark:bg-zinc-900 rounded-2xl shadow-2xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-zinc-200 dark:border-zinc-800">
          <h2 className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">
            {editProvider ? t('settings.editProvider') : t('settings.addProvider')}
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-zinc-600 dark:text-zinc-400" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit(onSubmit)} className="p-6 space-y-6">
          {/* Config-based Provider Warning */}
          {isConfigBased && (
            <div className="flex items-start gap-3 p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg">
              <AlertCircle className="w-5 h-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-amber-800 dark:text-amber-300 mb-1">
                  {t('settings.configProviderWarning', 'Config.yaml Provider')}
                </p>
                <p className="text-xs text-amber-700 dark:text-amber-400">
                  {t('settings.configProviderWarningDetail', 'Changes will take effect immediately but will NOT be saved to config.yaml. After restarting the service, settings will revert to config.yaml values. To make permanent changes, edit config.yaml directly.')}
                </p>
              </div>
            </div>
          )}
          
          {/* Provider Name */}
          <div>
            <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
              {t('settings.providerName')}
            </label>
            <input
              {...register('name')}
              disabled={!!editProvider}
              className="w-full px-4 py-3 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
              placeholder={t('settings.providerNamePlaceholder')}
            />
            {errors.name && (
              <p className="mt-1 text-sm text-red-500">{t(errors.name.message!)}</p>
            )}
          </div>

          {/* Protocol */}
          <div>
            <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
              {t('settings.protocol')}
            </label>
            <select
              {...register('protocol')}
              className="w-full px-4 py-3 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
            >
              <option value="ollama">{t('settings.protocolOllama')}</option>
              <option value="openai_compatible">{t('settings.protocolOpenAI')}</option>
            </select>
            {errors.protocol && (
              <p className="mt-1 text-sm text-red-500">{t(errors.protocol.message!)}</p>
            )}
          </div>

          {/* Base URL */}
          <div>
            <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
              {t('settings.baseUrl')}
            </label>
            <input
              {...register('base_url')}
              className="w-full px-4 py-3 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
              placeholder={t('settings.baseUrlPlaceholder')}
            />
            {errors.base_url && (
              <p className="mt-1 text-sm text-red-500">{t(errors.base_url.message!)}</p>
            )}
          </div>

          {/* API Key (conditional) */}
          {protocol === 'openai_compatible' && (
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                {t('settings.apiKey')}
                {editProvider && <span className="text-xs text-zinc-500 ml-2">({t('settings.leaveEmptyToKeep')})</span>}
              </label>
              <div className="relative">
                <input
                  {...register('api_key')}
                  type={showApiKey ? 'text' : 'password'}
                  className="w-full px-4 py-3 pr-12 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
                  placeholder={editProvider ? t('settings.apiKeyPlaceholderOptional') : t('settings.apiKeyPlaceholder')}
                />
                <button
                  type="button"
                  onClick={() => setShowApiKey(!showApiKey)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 p-1 hover:bg-zinc-100 dark:hover:bg-zinc-700 rounded transition-colors"
                >
                  {showApiKey ? (
                    <EyeOff className="w-5 h-5 text-zinc-500 dark:text-zinc-400" />
                  ) : (
                    <Eye className="w-5 h-5 text-zinc-500 dark:text-zinc-400" />
                  )}
                </button>
              </div>
              {errors.api_key && (
                <p className="mt-1 text-sm text-red-500">{t(errors.api_key.message!)}</p>
              )}
            </div>
          )}

          {/* Timeout and Max Retries */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                {t('settings.timeout')}
              </label>
              <input
                {...register('timeout', { valueAsNumber: true })}
                type="number"
                min="5"
                max="300"
                className="w-full px-4 py-3 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
              />
              {errors.timeout && (
                <p className="mt-1 text-sm text-red-500">{t('settings.errors.timeoutInvalid')}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                {t('settings.maxRetries')}
              </label>
              <input
                {...register('max_retries', { valueAsNumber: true })}
                type="number"
                min="0"
                max="10"
                className="w-full px-4 py-3 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
              />
              {errors.max_retries && (
                <p className="mt-1 text-sm text-red-500">
                  {t('settings.errors.maxRetriesInvalid')}
                </p>
              )}
            </div>
          </div>

          {/* Test Connection Button */}
          <div className="flex gap-3">
            <button
              type="button"
              onClick={testConnection}
              disabled={testingConnection}
              className="flex-1 px-4 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {testingConnection ? (
                <>
                  <Zap className="w-5 h-5 animate-spin" />
                  {t('settings.testingConnection')}
                </>
              ) : (
                <>
                  <Zap className="w-5 h-5" />
                  {t('settings.testConnection')}
                </>
              )}
            </button>
            {!connectionTested && (
              <button
                type="button"
                onClick={() => setConnectionTested(true)}
                className="px-4 py-3 bg-zinc-500 text-white rounded-lg hover:bg-zinc-600 transition-colors"
              >
                {t('settings.skipTest')}
              </button>
            )}
          </div>

          {/* Manual Model Input */}
          {connectionTested && (
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                {t('settings.manualAddModel')}
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={manualModelInput}
                  onChange={(e) => setManualModelInput(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), addManualModel())}
                  className="flex-1 px-4 py-2 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
                  placeholder={t('settings.manualModelPlaceholder')}
                />
                <button
                  type="button"
                  onClick={addManualModel}
                  className="px-4 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors flex items-center gap-2"
                >
                  <Plus className="w-4 h-4" />
                  {t('settings.add')}
                </button>
              </div>
              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                {t('settings.manualModelHint')}
              </p>
            </div>
          )}

          {/* Model Selection */}
          {connectionTested && allModels.length > 0 && (
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                {t('settings.selectModels')} ({selectedModels.length} {t('settings.selected')})
              </label>
              <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-3">
                {t('settings.selectModelsHint')}
              </p>
              
              {/* Search and Select All/None Controls */}
              <div className="mb-3 space-y-2">
                {/* Search Input */}
                <input
                  type="text"
                  value={modelSearchQuery}
                  onChange={(e) => setModelSearchQuery(e.target.value)}
                  placeholder={t('settings.searchModels', 'Search models...')}
                  className="w-full px-4 py-2 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent text-sm"
                />
                
                {/* Select All / Deselect All Buttons */}
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={handleSelectAll}
                    className="flex-1 px-3 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg transition-colors text-sm font-medium"
                  >
                    {t('settings.selectAll', 'Select All')} ({filteredModels.length})
                  </button>
                  <button
                    type="button"
                    onClick={handleDeselectAll}
                    className="flex-1 px-3 py-2 bg-zinc-500 hover:bg-zinc-600 text-white rounded-lg transition-colors text-sm font-medium"
                  >
                    {t('settings.deselectAll', 'Deselect All')}
                  </button>
                </div>
              </div>
              
              <div className="max-h-48 overflow-y-auto space-y-2 p-4 bg-zinc-50 dark:bg-zinc-800/50 rounded-lg border border-zinc-200 dark:border-zinc-700">
                {filteredModels.length > 0 ? (
                  filteredModels.map((model) => {
                    const isManual = manualModels.includes(model);
                    return (
                      <div
                        key={model}
                        className="flex items-center gap-3 p-2 hover:bg-white dark:hover:bg-zinc-800 rounded-lg transition-colors"
                      >
                        <label className="flex items-center gap-3 flex-1 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={selectedModels.includes(model)}
                            onChange={() => toggleModel(model)}
                            className="w-4 h-4 text-emerald-500 border-zinc-300 dark:border-zinc-600 rounded focus:ring-emerald-500"
                          />
                          <span className="text-sm font-mono text-zinc-700 dark:text-zinc-300">
                            {model}
                          </span>
                          {isManual && (
                            <span className="text-xs px-2 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded">
                              {t('settings.manual')}
                            </span>
                          )}
                          {selectedModels.includes(model) && (
                            <CheckCircle2 className="w-4 h-4 text-emerald-500 ml-auto" />
                          )}
                        </label>
                        {isManual && (
                          <button
                            type="button"
                            onClick={() => removeManualModel(model)}
                            className="p-1 hover:bg-red-100 dark:hover:bg-red-900/30 rounded transition-colors"
                            title={t('settings.removeModel')}
                          >
                            <Trash2 className="w-4 h-4 text-red-500" />
                          </button>
                        )}
                      </div>
                    );
                  })
                ) : (
                  <p className="text-sm text-zinc-500 dark:text-zinc-400 text-center py-4">
                    {t('settings.noModelsFound', 'No models found matching your search')}
                  </p>
                )}
              </div>
              {errors.selected_models && (
                <p className="mt-1 text-sm text-red-500">
                  {t(errors.selected_models.message!)}
                </p>
              )}
            </div>
          )}

          {/* Warning if not tested */}
          {!connectionTested && (
            <div className="flex items-start gap-3 p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
              <AlertCircle className="w-5 h-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-blue-700 dark:text-blue-300 mb-1">
                  {t('settings.testConnectionOptional')}
                </p>
                <p className="text-xs text-blue-600 dark:text-blue-400">
                  {t('settings.testConnectionOptionalHint')}
                </p>
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-3 bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 rounded-lg hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-colors"
            >
              {t('settings.cancel')}
            </button>
            <button
              type="submit"
              disabled={isSubmitting || !connectionTested}
              className="flex-1 px-4 py-3 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubmitting ? t('settings.saving') : t('settings.save')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
