import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Save, Loader2, AlertCircle } from 'lucide-react';
import { GlassPanel } from '@/components/GlassPanel';
import type { Agent } from '@/types/agent';
import { llmApi } from '@/api';
import type { ProviderModels } from '@/api/llm';

interface AgentConfigModalProps {
  agent: Agent | null;
  isOpen: boolean;
  onClose: () => void;
  onSave: (agent: Agent) => void;
}

export const AgentConfigModal: React.FC<AgentConfigModalProps> = ({
  agent,
  isOpen,
  onClose,
  onSave,
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'basic' | 'capabilities' | 'model' | 'access'>('basic');
  const [isSaving, setIsSaving] = useState(false);
  const [isLoadingProviders, setIsLoadingProviders] = useState(false);
  const [availableProviders, setAvailableProviders] = useState<ProviderModels>({});
  const [providersError, setProvidersError] = useState<string | null>(null);

  const [formData, setFormData] = useState<Partial<Agent>>({
    name: agent?.name || '',
    type: agent?.type || '',
    systemPrompt: agent?.systemPrompt || '',
    skills: agent?.skills || [],
    model: agent?.model || '',
    provider: agent?.provider || '',
    temperature: agent?.temperature || 0.7,
    maxTokens: agent?.maxTokens || 2000,
    topP: agent?.topP || 0.9,
    accessLevel: agent?.accessLevel || 'private',
    allowedKnowledge: agent?.allowedKnowledge || [],
    allowedMemory: agent?.allowedMemory || [],
  });

  // Fetch available providers and models
  useEffect(() => {
    if (isOpen) {
      fetchAvailableProviders();
    }
  }, [isOpen]);

  const fetchAvailableProviders = async () => {
    setIsLoadingProviders(true);
    setProvidersError(null);
    try {
      const response = await llmApi.getAvailableProviders();
      setAvailableProviders(response);
      
      // If no provider is selected and we have available providers, select the first one
      if (!formData.provider && Object.keys(response).length > 0) {
        const firstProvider = Object.keys(response)[0];
        const firstModel = response[firstProvider][0] || '';
        setFormData(prev => ({
          ...prev,
          provider: firstProvider,
          model: firstModel,
        }));
      }
    } catch (error) {
      console.error('Failed to fetch available providers:', error);
      setProvidersError('Failed to load available providers. Please check your LLM configuration.');
    } finally {
      setIsLoadingProviders(false);
    }
  };

  // Update available models when provider changes
  const handleProviderChange = (newProvider: string) => {
    const models = availableProviders[newProvider] || [];
    setFormData({
      ...formData,
      provider: newProvider,
      model: models[0] || '', // Select first model by default
    });
  };

  if (!isOpen || !agent) return null;

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await new Promise(resolve => setTimeout(resolve, 1000)); // Simulate API call
      onSave({ ...agent, ...formData });
      onClose();
    } finally {
      setIsSaving(false);
    }
  };

  const tabs = [
    { id: 'basic', label: t('agent.basicInfo') },
    { id: 'capabilities', label: t('agent.capabilities') },
    { id: 'model', label: t('agent.modelConfig') },
    { id: 'access', label: t('agent.dataAccess') },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <GlassPanel className="w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between mb-6 pb-4 border-b border-zinc-500/10">
          <div>
            <h2 className="text-2xl font-bold text-zinc-800 dark:text-zinc-200">
              {t('agent.configure')}
            </h2>
            <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-1">{agent.name}</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-zinc-500/5 rounded-lg transition-colors text-zinc-600 dark:text-zinc-400"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 mb-6 overflow-x-auto">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`px-4 py-2 rounded-lg font-semibold text-sm whitespace-nowrap transition-all ${
                activeTab === tab.id
                  ? 'bg-emerald-500 text-white'
                  : 'bg-zinc-500/5 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-500/10'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto mb-6">
          {/* Basic Info Tab */}
          {activeTab === 'basic' && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('agent.agentName')}
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="w-full px-4 py-3 bg-zinc-500/5 border border-zinc-500/10 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500/20 text-zinc-800 dark:text-zinc-200"
                  placeholder={t('agent.agentNamePlaceholder')}
                />
              </div>

              <div>
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('agent.selectTemplate')}
                </label>
                <input
                  type="text"
                  value={formData.type}
                  onChange={(e) => setFormData({ ...formData, type: e.target.value })}
                  className="w-full px-4 py-3 bg-zinc-500/5 border border-zinc-500/10 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500/20 text-zinc-800 dark:text-zinc-200"
                  placeholder="Agent Type"
                />
              </div>

              <div>
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('agent.systemPrompt')}
                </label>
                <textarea
                  value={formData.systemPrompt}
                  onChange={(e) => setFormData({ ...formData, systemPrompt: e.target.value })}
                  rows={8}
                  className="w-full px-4 py-3 bg-zinc-500/5 border border-zinc-500/10 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500/20 text-zinc-800 dark:text-zinc-200 resize-none"
                  placeholder={t('agent.systemPromptPlaceholder')}
                />
              </div>
            </div>
          )}

          {/* Capabilities Tab */}
          {activeTab === 'capabilities' && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('agent.selectSkills')}
                </label>
                <div className="p-4 bg-zinc-500/5 border border-zinc-500/10 rounded-xl min-h-[200px]">
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    {formData.skills?.length || 0} {t('agent.noSkillsSelected')}
                  </p>
                  {/* TODO: Add skill selection UI */}
                </div>
              </div>
            </div>
          )}

          {/* Model Config Tab */}
          {activeTab === 'model' && (
            <div className="space-y-4">
              {/* Loading State */}
              {isLoadingProviders && (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-6 h-6 animate-spin text-emerald-500" />
                  <span className="ml-2 text-zinc-600 dark:text-zinc-400">
                    Loading providers...
                  </span>
                </div>
              )}

              {/* Error State */}
              {providersError && (
                <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-semibold text-red-700 dark:text-red-400">
                      {providersError}
                    </p>
                    <button
                      onClick={fetchAvailableProviders}
                      className="mt-2 text-sm text-red-600 dark:text-red-400 hover:underline"
                    >
                      Retry
                    </button>
                  </div>
                </div>
              )}

              {/* No Providers Available */}
              {!isLoadingProviders && !providersError && Object.keys(availableProviders).length === 0 && (
                <div className="p-4 bg-yellow-500/10 border border-yellow-500/20 rounded-xl flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-yellow-500 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-semibold text-yellow-700 dark:text-yellow-400">
                      No LLM providers configured
                    </p>
                    <p className="text-sm text-yellow-600 dark:text-yellow-500 mt-1">
                      Please configure at least one LLM provider in the system settings.
                    </p>
                  </div>
                </div>
              )}

              {/* Provider and Model Selection */}
              {!isLoadingProviders && Object.keys(availableProviders).length > 0 && (
                <>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                        {t('agent.selectProvider')}
                      </label>
                      <select
                        value={formData.provider}
                        onChange={(e) => handleProviderChange(e.target.value)}
                        className="w-full px-4 py-3 bg-zinc-500/5 border border-zinc-500/10 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500/20 text-zinc-800 dark:text-zinc-200"
                      >
                        <option value="">Select Provider</option>
                        {Object.keys(availableProviders).map((providerName) => (
                          <option key={providerName} value={providerName}>
                            {providerName}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                        {t('agent.selectModel')}
                      </label>
                      <select
                        value={formData.model}
                        onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                        disabled={!formData.provider}
                        className="w-full px-4 py-3 bg-zinc-500/5 border border-zinc-500/10 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500/20 text-zinc-800 dark:text-zinc-200 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <option value="">Select Model</option>
                        {formData.provider &&
                          availableProviders[formData.provider]?.map((modelName) => (
                            <option key={modelName} value={modelName}>
                              {modelName}
                            </option>
                          ))}
                      </select>
                      {!formData.provider && (
                        <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                          Select a provider first
                        </p>
                      )}
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                      {t('agent.temperature')}: {formData.temperature}
                    </label>
                    <input
                      type="range"
                      min="0"
                      max="2"
                      step="0.1"
                      value={formData.temperature}
                      onChange={(e) => setFormData({ ...formData, temperature: parseFloat(e.target.value) })}
                      className="w-full"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                      {t('agent.maxTokens')}
                    </label>
                    <input
                      type="number"
                      value={formData.maxTokens}
                      onChange={(e) => setFormData({ ...formData, maxTokens: parseInt(e.target.value) })}
                      className="w-full px-4 py-3 bg-zinc-500/5 border border-zinc-500/10 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500/20 text-zinc-800 dark:text-zinc-200"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                      {t('agent.topP')}: {formData.topP}
                    </label>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.1"
                      value={formData.topP}
                      onChange={(e) => setFormData({ ...formData, topP: parseFloat(e.target.value) })}
                      className="w-full"
                    />
                  </div>
                </>
              )}
            </div>
          )}

          {/* Data Access Tab */}
          {activeTab === 'access' && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('agent.accessLevel')}
                </label>
                <select
                  value={formData.accessLevel}
                  onChange={(e) => setFormData({ ...formData, accessLevel: e.target.value as any })}
                  className="w-full px-4 py-3 bg-zinc-500/5 border border-zinc-500/10 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500/20 text-zinc-800 dark:text-zinc-200"
                >
                  <option value="private">{t('agent.accessLevelPrivate')}</option>
                  <option value="team">{t('agent.accessLevelTeam')}</option>
                  <option value="public">{t('agent.accessLevelPublic')}</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('agent.allowedKnowledge')}
                </label>
                <div className="p-4 bg-zinc-500/5 border border-zinc-500/10 rounded-xl min-h-[100px]">
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    {formData.allowedKnowledge?.length || 0} knowledge bases selected
                  </p>
                </div>
              </div>

              <div>
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('agent.allowedMemory')}
                </label>
                <div className="p-4 bg-zinc-500/5 border border-zinc-500/10 rounded-xl min-h-[100px]">
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    {formData.allowedMemory?.length || 0} memory collections selected
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 pt-4 border-t border-zinc-500/10">
          <button
            onClick={onClose}
            className="px-6 py-3 bg-zinc-500/5 hover:bg-zinc-500/10 text-zinc-700 dark:text-zinc-300 rounded-xl font-semibold transition-colors"
          >
            {t('common.cancel')}
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="px-6 py-3 bg-emerald-500 hover:bg-emerald-600 text-white rounded-xl font-semibold transition-colors flex items-center gap-2 disabled:opacity-50"
          >
            {isSaving ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                {t('agent.configuring')}
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                {t('common.save')}
              </>
            )}
          </button>
        </div>
      </GlassPanel>
    </div>
  );
};
