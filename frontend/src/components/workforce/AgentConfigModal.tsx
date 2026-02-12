import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Save, Loader2, AlertCircle, Info } from 'lucide-react';
import toast from 'react-hot-toast';
import type { Agent } from '@/types/agent';
import { llmApi, agentsApi } from '@/api';
import { knowledgeApi } from '@/api/knowledge';
import type { ModelMetadata } from '@/api/llm';
import type { Collection } from '@/types/document';
import { ModelMetadataCard } from '@/components/settings/ModelMetadataCard';
import { ImageCropModal } from '@/components/common/ImageCropModal';
import { DepartmentSelect } from '@/components/departments/DepartmentSelect';

type MemoryScope = 'agent' | 'company' | 'user_context';
const MEMORY_SCOPE_ALIAS_MAP: Record<string, MemoryScope> = {
  agent: 'agent',
  agent_memories: 'agent',
  company: 'company',
  company_memories: 'company',
  user_context: 'user_context',
};

const normalizeMemoryScopes = (scopes?: string[]): MemoryScope[] => {
  if (!scopes || scopes.length === 0) {
    return [];
  }

  const normalized: MemoryScope[] = [];
  for (const rawScope of scopes) {
    const scope = (rawScope || '').trim().toLowerCase();
    const canonicalScope = MEMORY_SCOPE_ALIAS_MAP[scope];
    if (canonicalScope && !normalized.includes(canonicalScope)) {
      normalized.push(canonicalScope);
    }
  }
  return normalized;
};

interface AgentConfigModalProps {
  agent: Agent | null;
  isOpen: boolean;
  onClose: () => void;
  onSave: (agent: Agent) => Promise<void>;
}

export const AgentConfigModal: React.FC<AgentConfigModalProps> = ({
  agent,
  isOpen,
  onClose,
  onSave,
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'basic' | 'capabilities' | 'model' | 'knowledge' | 'access'>('basic');
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isLoadingProviders, setIsLoadingProviders] = useState(false);
  const [availableProviders, setAvailableProviders] = useState<Record<string, string[]>>({});
  const [providersError, setProvidersError] = useState<string | null>(null);
  const [modelMetadata, setModelMetadata] = useState<ModelMetadata | null>(null);
  const [isLoadingMetadata, setIsLoadingMetadata] = useState(false);
  const [isAvatarCropModalOpen, setIsAvatarCropModalOpen] = useState(false);
  const [avatarPreview, setAvatarPreview] = useState<string>('');  // presigned URL for display
  const [availableKnowledgeBases, setAvailableKnowledgeBases] = useState<Collection[]>([]);
  const [isLoadingKnowledgeBases, setIsLoadingKnowledgeBases] = useState(false);
  const [knowledgeBasesError, setKnowledgeBasesError] = useState<string | null>(null);
  
  // Skills state
  const [availableSkills, setAvailableSkills] = useState<Array<{
    skill_id: string;
    name: string;
    description: string;
    skill_type: string;
    version: string;
  }>>([]);
  const [isLoadingSkills, setIsLoadingSkills] = useState(false);
  const [skillsError, setSkillsError] = useState<string | null>(null);

  const [formData, setFormData] = useState<Partial<Agent>>({
    name: '',
    type: '',
    avatar: '',
    systemPrompt: '',
    skills: [],
    model: '',
    provider: '',
    temperature: 0.7,
    maxTokens: 4096,
    topP: 0.9,
    departmentId: '',
    accessLevel: 'private',
    allowedKnowledge: [],
    allowedMemory: [],
    topK: 5,
    similarityThreshold: 0.7,
  });

  // Initialize form data when agent changes
  useEffect(() => {
    console.log('[AgentConfigModal] Agent or isOpen changed:', { agent, isOpen });
    if (agent && isOpen) {
      console.log('[AgentConfigModal] Initializing form with agent data:', agent);
      setFormData({
        name: agent.name || '',
        type: agent.type || '',
        avatar: agent.avatar || '',
        systemPrompt: agent.systemPrompt || '',
        skills: agent.skills || [],
        model: agent.model || '',
        provider: agent.provider || '',
        temperature: agent.temperature ?? 0.7,
        maxTokens: agent.maxTokens ?? 4096,
        topP: agent.topP ?? 0.9,
        departmentId: agent.departmentId || '',
        accessLevel: agent.accessLevel || 'private',
        allowedKnowledge: agent.allowedKnowledge || [],
        allowedMemory: normalizeMemoryScopes(agent.allowedMemory || []),
        topK: agent.topK || 5,
        similarityThreshold: agent.similarityThreshold || 0.7,
      });
      setAvatarPreview(agent.avatar || '');
      setSaveError(null);
      setModelMetadata(null);
    }
  }, [agent, isOpen]);

  // Fetch available providers and models
  useEffect(() => {
    if (isOpen) {
      fetchAvailableProviders();
      fetchAvailableSkills();
      fetchKnowledgeBases();
    }
  }, [isOpen]);

  // Fetch model metadata when provider and model are selected
  // Only fetch if both are set and not empty, and not currently loading
  useEffect(() => {
    if (isOpen && formData.provider && formData.model && !isLoadingMetadata) {
      fetchModelMetadata(formData.provider, formData.model);
    } else if (!formData.provider || !formData.model) {
      setModelMetadata(null);
    }
  }, [isOpen, formData.provider, formData.model]);

  const fetchAvailableProviders = async () => {
    console.log('[AgentConfigModal] Fetching available providers...');
    setIsLoadingProviders(true);
    setProvidersError(null);
    try {
      const response = await llmApi.getAvailableProviders();
      console.log('[AgentConfigModal] Available providers loaded:', response);
      setAvailableProviders(response);
      
      // DON'T auto-select provider/model - this was causing the bug!
      // The agent's existing configuration should be preserved
      // formData is already initialized from agent prop in the useEffect above
    } catch (error: any) {
      console.error('Failed to fetch available providers:', error);
      const errorMsg = error.response?.data?.message || error.message || 'Failed to load available providers';
      setProvidersError(`${errorMsg}. Please check your LLM configuration.`);
    } finally {
      setIsLoadingProviders(false);
    }
  };

  const fetchKnowledgeBases = async () => {
    setIsLoadingKnowledgeBases(true);
    setKnowledgeBasesError(null);
    try {
      const pageSize = 100;
      let page = 1;
      let total = Number.POSITIVE_INFINITY;
      const allCollections: Collection[] = [];

      while (allCollections.length < total) {
        const response = await knowledgeApi.getCollections({ page, page_size: pageSize });
        allCollections.push(...response.collections);
        total = response.total;
        if (response.collections.length < pageSize) {
          break;
        }
        page += 1;
      }

      allCollections.sort((a, b) => a.name.localeCompare(b.name));
      setAvailableKnowledgeBases(allCollections);
    } catch (error: any) {
      console.error('Failed to fetch knowledge collections:', error);
      const errorMsg =
        error.response?.data?.detail ||
        error.response?.data?.message ||
        error.message ||
        'Failed to load knowledge bases';
      setKnowledgeBasesError(errorMsg);
      setAvailableKnowledgeBases([]);
    } finally {
      setIsLoadingKnowledgeBases(false);
    }
  };
  
  const fetchAvailableSkills = async () => {
    if (!agent?.id) return;
    
    console.log('[AgentConfigModal] Fetching available skills...');
    setIsLoadingSkills(true);
    setSkillsError(null);
    try {
      const response = await agentsApi.getAgentSkills(agent.id);
      console.log('[AgentConfigModal] Skills loaded:', response);
      setAvailableSkills(response.available_skills || []);
      
      // Update form data with configured skills if not already set
      if (!formData.skills || formData.skills.length === 0) {
        setFormData(prev => ({
          ...prev,
          skills: response.configured_skills || []
        }));
      }
    } catch (error: any) {
      console.error('Failed to fetch available skills:', error);
      const errorMsg = error.response?.data?.message || error.message || 'Failed to load skills';
      setSkillsError(errorMsg);
    } finally {
      setIsLoadingSkills(false);
    }
  };
  
  const toggleSkill = (skillName: string) => {
    const currentSkills = formData.skills || [];
    const isSelected = currentSkills.includes(skillName);
    
    const newSkills = isSelected
      ? currentSkills.filter(s => s !== skillName)
      : [...currentSkills, skillName];
    
    setFormData({
      ...formData,
      skills: newSkills
    });
  };

  const toggleKnowledgeBase = (collectionId: string) => {
    const selected = formData.allowedKnowledge || [];
    const nextSelected = selected.includes(collectionId)
      ? selected.filter((id) => id !== collectionId)
      : [...selected, collectionId];
    setFormData({
      ...formData,
      allowedKnowledge: nextSelected,
    });
  };

  const toggleMemoryScope = (scope: string) => {
    const selected = formData.allowedMemory || [];
    const nextSelected = selected.includes(scope)
      ? selected.filter((item) => item !== scope)
      : [...selected, scope];
    setFormData({
      ...formData,
      allowedMemory: nextSelected,
    });
  };

  const resolveEffectiveMemoryScopes = (): string[] => {
    const normalizedSelected = normalizeMemoryScopes(formData.allowedMemory || []);
    if (normalizedSelected.length > 0) {
      return normalizedSelected;
    }
    if (formData.accessLevel === 'team' || formData.accessLevel === 'public') {
      return ['agent', 'company', 'user_context'];
    }
    return ['agent', 'user_context'];
  };

  const fetchModelMetadata = async (provider: string, model: string) => {
    // Prevent duplicate requests
    if (isLoadingMetadata) {
      console.log('[AgentConfigModal] Skipping metadata fetch - already loading');
      return;
    }
    
    console.log(`[AgentConfigModal] Fetching metadata for ${provider}/${model}`);
    setIsLoadingMetadata(true);
    try {
      const metadata = await llmApi.getModelMetadata(provider, model);
      console.log('[AgentConfigModal] Metadata loaded:', metadata);
      setModelMetadata(metadata);
      
      // DON'T auto-update temperature/maxTokens if user has already set them
      // Only update if they're at default values AND agent doesn't have custom values
      // This prevents overwriting user's choices
    } catch (error: any) {
      console.error('Failed to fetch model metadata:', error);
      setModelMetadata(null);
    } finally {
      setIsLoadingMetadata(false);
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

  // Handle avatar crop complete
  const handleAvatarCropComplete = async (croppedBlob: Blob) => {
    try {
      if (!agent) return;
      
      // Upload to MinIO via API
      const result = await agentsApi.uploadAvatar(agent.id, croppedBlob);

      // Store minio reference for DB persistence, presigned URL for display
      setFormData({ ...formData, avatar: result.avatar_ref });
      setAvatarPreview(result.avatar_url);
      
      toast.success('Avatar uploaded successfully');
    } catch (error: any) {
      console.error('Failed to upload avatar:', error);
      const errorMsg = error.response?.data?.detail || error.message || 'Failed to upload avatar';
      toast.error(errorMsg);
    }
  };

  if (!isOpen || !agent) return null;

  const handleSave = async () => {
    console.log('[AgentConfigModal] handleSave called');
    console.log('[AgentConfigModal] formData:', formData);
    
    // Validate required fields
    if (!formData.name?.trim()) {
      console.log('[AgentConfigModal] Validation failed: name required');
      setSaveError('Agent name is required');
      return;
    }
    
    if (!formData.provider) {
      console.log('[AgentConfigModal] Validation failed: provider required');
      setSaveError('Please select a provider');
      return;
    }
    
    if (!formData.model) {
      console.log('[AgentConfigModal] Validation failed: model required');
      setSaveError('Please select a model');
      return;
    }

    // Clear any previous errors and start saving
    console.log('[AgentConfigModal] Validation passed, starting save...');
    setSaveError(null);
    setIsSaving(true);
    
    try {
      const shouldNormalizeKnowledge = !knowledgeBasesError && !isLoadingKnowledgeBases;
      const availableKnowledgeIds = new Set(availableKnowledgeBases.map((item) => item.id));
      const normalizedAllowedKnowledge = shouldNormalizeKnowledge
        ? (formData.allowedKnowledge || []).filter((id) => availableKnowledgeIds.has(id))
        : (formData.allowedKnowledge || []);
      const normalizedAllowedMemory = normalizeMemoryScopes(formData.allowedMemory || []);

      const updatedAgent = {
        ...agent!,
        ...formData,
        allowedKnowledge: normalizedAllowedKnowledge,
        allowedMemory: normalizedAllowedMemory,
      } as Agent;
      console.log('[AgentConfigModal] Calling onSave with:', updatedAgent);
      
      // Call parent's onSave with updated agent data
      await onSave(updatedAgent);
      
      console.log('[AgentConfigModal] Save successful');
      // If we get here, save was successful
      // Parent component will close the modal
    } catch (error: any) {
      // If parent's onSave throws an error, display it in the modal
      console.error('[AgentConfigModal] Save failed:', error);
      
      let errorMessage = 'Failed to save agent configuration';
      
      // Handle validation errors from backend
      if (error.response?.data?.details?.errors) {
        // Backend validation error format: { details: { errors: [...] } }
        const errors = error.response.data.details.errors;
        errorMessage = errors
          .map((err: any) => `${err.field}: ${err.message}`)
          .join('; ');
      } else if (error.response?.data?.message) {
        // Generic error message
        errorMessage = error.response.data.message;
      } else if (error.response?.data?.detail) {
        // FastAPI detail format
        if (typeof error.response.data.detail === 'string') {
          errorMessage = error.response.data.detail;
        } else if (Array.isArray(error.response.data.detail)) {
          errorMessage = error.response.data.detail
            .map((err: any) => `${err.loc.join('.')}: ${err.msg}`)
            .join(', ');
        }
      } else if (error.message) {
        errorMessage = error.message;
      }
      
      console.log('[AgentConfigModal] Setting error:', errorMessage);
      setSaveError(errorMessage);
    } finally {
      console.log('[AgentConfigModal] Save process complete, setting isSaving=false');
      setIsSaving(false);
    }
  };

  const tabs = [
    { id: 'basic', label: t('agent.basicInfo') },
    { id: 'capabilities', label: t('agent.capabilities') },
    { id: 'model', label: t('agent.modelConfig') },
    { id: 'knowledge', label: t('agent.knowledgeBase') },
    { id: 'access', label: t('agent.dataAccess') },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md overflow-auto" style={{ marginLeft: 'var(--sidebar-width, 0px)' }}>
      <div className="w-full max-w-4xl my-auto max-h-[90vh] overflow-hidden flex flex-col modal-panel rounded-[24px] shadow-2xl p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6 pb-4 border-b border-zinc-200 dark:border-zinc-700">
          <div>
            <h2 className="text-2xl font-bold text-zinc-800 dark:text-zinc-200">
              {t('agent.configure')}
            </h2>
            <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-1">{agent.name}</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors text-zinc-600 dark:text-zinc-400"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 mb-6 flex-wrap">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`px-4 py-2 rounded-lg font-semibold text-sm whitespace-nowrap transition-all ${
                activeTab === tab.id
                  ? 'bg-emerald-500 text-white shadow-sm'
                  : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-200 dark:hover:bg-zinc-700'
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
              {/* Avatar Upload */}
              <div>
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('agent.avatar')}
                </label>
                <div className="flex items-center gap-4">
                  {/* Avatar Preview */}
                  <div className="relative w-24 h-24 rounded-full overflow-hidden bg-gradient-to-br from-emerald-400 to-cyan-500 flex items-center justify-center">
                    {avatarPreview ? (
                      <img
                        src={avatarPreview}
                        alt={formData.name}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <span className="text-3xl font-bold text-white">
                        {formData.name?.charAt(0)?.toUpperCase() || 'A'}
                      </span>
                    )}
                  </div>

                  {/* Upload Button */}
                  <button
                    type="button"
                    onClick={() => setIsAvatarCropModalOpen(true)}
                    className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg font-semibold transition-colors"
                  >
                    {avatarPreview ? t('agent.changeAvatar') : t('agent.uploadAvatar')}
                  </button>
                </div>
              </div>

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

              <div>
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('departments.label', 'Department')}
                </label>
                <DepartmentSelect
                  value={formData.departmentId || undefined}
                  onChange={(val) => setFormData({ ...formData, departmentId: val || '' })}
                />
              </div>
            </div>
          )}

          {/* Capabilities Tab */}
          {activeTab === 'capabilities' && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('agent.selectSkills', '选择技能')}
                </label>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-3">
                  {t('agent.skillsDescription', '选择此 Agent 可以使用的技能。技能将在 Agent 初始化时加载。')}
                </p>
                
                {/* Skills Loading State */}
                {isLoadingSkills && (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="w-6 h-6 animate-spin text-emerald-500" />
                    <span className="ml-2 text-zinc-600 dark:text-zinc-400">
                      {t('agent.loadingSkills', '加载技能中...')}
                    </span>
                  </div>
                )}
                
                {/* Skills Error State */}
                {skillsError && (
                  <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl flex items-start gap-3">
                    <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-semibold text-red-700 dark:text-red-400">
                        {skillsError}
                      </p>
                      <button
                        onClick={fetchAvailableSkills}
                        className="mt-2 text-sm text-red-600 dark:text-red-400 hover:underline"
                      >
                        {t('common.retry', '重试')}
                      </button>
                    </div>
                  </div>
                )}
                
                {/* Skills List */}
                {!isLoadingSkills && !skillsError && (
                  <div className="space-y-3">
                    {/* Selected Skills Count */}
                    <div className="flex items-center justify-between p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-lg">
                      <span className="text-sm font-medium text-emerald-700 dark:text-emerald-400">
                        {t('agent.selectedSkills', '已选择技能')}
                      </span>
                      <span className="text-sm font-semibold text-emerald-700 dark:text-emerald-400">
                        {formData.skills?.length || 0} / {availableSkills.length}
                      </span>
                    </div>
                    
                    {/* Skills Grid */}
                    {availableSkills.length === 0 ? (
                      <div className="p-8 text-center bg-zinc-500/5 border border-zinc-500/10 rounded-xl">
                        <Info className="w-8 h-8 text-zinc-400 mx-auto mb-2" />
                        <p className="text-sm text-zinc-500 dark:text-zinc-400">
                          {t('agent.noSkillsAvailable', '暂无可用技能')}
                        </p>
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 gap-2 max-h-[400px] overflow-y-auto p-1">
                        {availableSkills.map((skill) => {
                          const isSelected = formData.skills?.includes(skill.name) || false;
                          const isLangChainTool = skill.skill_type === 'langchain_tool';
                          
                          return (
                            <button
                              key={skill.skill_id}
                              type="button"
                              onClick={() => toggleSkill(skill.name)}
                              className={`
                                p-3 rounded-lg border-2 text-left transition-all
                                ${isSelected
                                  ? 'border-emerald-500 bg-emerald-500/10'
                                  : 'border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 hover:border-emerald-500/50'
                                }
                              `}
                            >
                              <div className="flex items-start gap-3">
                                {/* Checkbox */}
                                <div className={`
                                  w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 mt-0.5
                                  ${isSelected
                                    ? 'border-emerald-500 bg-emerald-500'
                                    : 'border-zinc-300 dark:border-zinc-600'
                                  }
                                `}>
                                  {isSelected && (
                                    <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                                    </svg>
                                  )}
                                </div>
                                
                                {/* Skill Info */}
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2 mb-1">
                                    <h4 className="font-medium text-zinc-900 dark:text-zinc-100">
                                      {skill.name}
                                    </h4>
                                    <span className={`
                                      px-2 py-0.5 text-xs font-medium rounded
                                      ${isLangChainTool
                                        ? 'bg-blue-500/10 text-blue-700 dark:text-blue-400'
                                        : 'bg-purple-500/10 text-purple-700 dark:text-purple-400'
                                      }
                                    `}>
                                      {isLangChainTool ? 'Tool' : 'Agent Skill'}
                                    </span>
                                  </div>
                                  <p className="text-sm text-zinc-600 dark:text-zinc-400 line-clamp-2">
                                    {skill.description}
                                  </p>
                                  {skill.version && (
                                    <p className="text-xs text-zinc-500 dark:text-zinc-500 mt-1">
                                      v{skill.version}
                                    </p>
                                  )}
                                </div>
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}
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

                  {/* Model Metadata Display */}
                  {isLoadingMetadata && (
                    <div className="flex items-center gap-2 p-3 bg-blue-500/10 border border-blue-500/20 rounded-xl">
                      <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                      <span className="text-sm text-blue-700 dark:text-blue-400">
                        Loading model information...
                      </span>
                    </div>
                  )}

                  {modelMetadata && !isLoadingMetadata && (
                    <div className="mt-2">
                      <ModelMetadataCard metadata={modelMetadata} />
                    </div>
                  )}

                  <div>
                    <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                      {t('agent.temperature')}: {formData.temperature?.toFixed(1)}
                      {modelMetadata && (
                        <span className="ml-2 text-xs text-zinc-500 dark:text-zinc-400">
                          (recommended: {modelMetadata.default_temperature})
                        </span>
                      )}
                    </label>
                    <input
                      type="range"
                      min={modelMetadata?.temperature_range[0] ?? 0}
                      max={modelMetadata?.temperature_range[1] ?? 2}
                      step="0.1"
                      value={formData.temperature}
                      onChange={(e) => setFormData({ ...formData, temperature: parseFloat(e.target.value) })}
                      className="w-full"
                    />
                    <div className="flex justify-between text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                      <span>More focused</span>
                      <span>More creative</span>
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                      {t('agent.maxTokens')} (Maximum Output Tokens)
                      {modelMetadata?.max_output_tokens && (
                        <span className="ml-2 text-xs text-zinc-500 dark:text-zinc-400">
                          (model max: {modelMetadata.max_output_tokens.toLocaleString()})
                        </span>
                      )}
                    </label>
                    <input
                      type="number"
                      value={formData.maxTokens}
                      onChange={(e) => setFormData({ ...formData, maxTokens: parseInt(e.target.value) || 0 })}
                      min={1}
                      max={modelMetadata?.max_output_tokens ?? 8000}
                      className="w-full px-4 py-3 bg-zinc-500/5 border border-zinc-500/10 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500/20 text-zinc-800 dark:text-zinc-200"
                      placeholder="4096"
                    />
                    <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                      Maximum number of tokens in the model's response. Default: 4096
                    </p>
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                      {t('agent.topP')}: {formData.topP?.toFixed(1)}
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
                    <div className="flex justify-between text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                      <span>More deterministic</span>
                      <span>More diverse</span>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {/* Knowledge Base Tab */}
          {activeTab === 'knowledge' && (
            <div className="space-y-4">
              <div className="p-4 bg-blue-500/10 border border-blue-500/20 rounded-xl flex items-start gap-3 mb-4">
                <Info className="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-semibold text-blue-700 dark:text-blue-400 mb-1">
                    {t('agent.knowledgeBaseConfig', '知识库配置')}
                  </p>
                  <p className="text-xs text-blue-600 dark:text-blue-500">
                    {t('agent.knowledgeBaseConfigDesc', '配置此代理可访问的知识库；Embedding 模型统一在知识库配置页维护。')}
                  </p>
                </div>
              </div>

              {/* Knowledge Base Access */}
              <div>
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('agent.accessibleKnowledgeBases', '可访问的知识库')}
                </label>
                <div className="p-4 bg-zinc-500/5 border border-zinc-500/10 rounded-xl min-h-[120px]">
                  <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-3">
                    {formData.allowedKnowledge?.length || 0} {t('agent.knowledgeBasesSelected', '个知识库已选择')}
                  </p>

                  {isLoadingKnowledgeBases && (
                    <div className="flex items-center gap-2 text-sm text-zinc-500 dark:text-zinc-400">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>{t('agent.loadingKnowledgeBases', '加载知识库中...')}</span>
                    </div>
                  )}

                  {!isLoadingKnowledgeBases && knowledgeBasesError && (
                    <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
                      <p className="text-sm text-red-700 dark:text-red-400">
                        {t('agent.knowledgeBasesLoadFailed', '知识库加载失败')}: {knowledgeBasesError}
                      </p>
                      <button
                        type="button"
                        onClick={fetchKnowledgeBases}
                        className="mt-2 text-xs text-red-600 dark:text-red-400 hover:underline"
                      >
                        {t('common.retry', '重试')}
                      </button>
                    </div>
                  )}

                  {!isLoadingKnowledgeBases && !knowledgeBasesError && availableKnowledgeBases.length === 0 && (
                    <p className="text-xs text-zinc-500 dark:text-zinc-400">
                      {t('agent.noKnowledgeBasesAvailable', '当前没有可用知识库，请先在知识库页面创建集合。')}
                    </p>
                  )}

                  {!isLoadingKnowledgeBases && !knowledgeBasesError && availableKnowledgeBases.length > 0 && (
                    <>
                      <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                        {availableKnowledgeBases.map((kb) => {
                          const isSelected = (formData.allowedKnowledge || []).includes(kb.id);
                          return (
                            <button
                              key={kb.id}
                              type="button"
                              onClick={() => toggleKnowledgeBase(kb.id)}
                              className={`w-full text-left p-3 rounded-lg border transition-colors ${
                                isSelected
                                  ? 'border-emerald-500 bg-emerald-500/10'
                                  : 'border-zinc-200 dark:border-zinc-700 hover:border-emerald-400/60'
                              }`}
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0">
                                  <p className="text-sm font-semibold text-zinc-800 dark:text-zinc-200 truncate">
                                    {kb.name}
                                  </p>
                                  {kb.description && (
                                    <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1 line-clamp-2">
                                      {kb.description}
                                    </p>
                                  )}
                                </div>
                                <span className="text-xs px-2 py-1 rounded-full bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 whitespace-nowrap">
                                  {kb.itemCount}
                                </span>
                              </div>
                            </button>
                          );
                        })}
                      </div>
                      <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-2">
                        {t('agent.knowledgeBaseAccessDesc', '配置此代理可以查询的知识库。')}
                      </p>
                    </>
                  )}
                </div>
              </div>

              {/* Retrieval Settings */}
              <div>
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('agent.topKResults', 'Top K 结果数')}: {formData.topK || 5}
                </label>
                <input
                  type="range"
                  min="1"
                  max="20"
                  step="1"
                  value={formData.topK || 5}
                  onChange={(e) => setFormData({ ...formData, topK: parseInt(e.target.value) })}
                  className="w-full"
                />
                <div className="flex justify-between text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                  <span>{t('agent.fewerResults', '更少结果（更快）')}</span>
                  <span>{t('agent.moreResults', '更多结果（更全面）')}</span>
                </div>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-2">
                  {t('agent.topKResultsDesc', '每次查询从知识库检索的最相关文档数量。')}
                </p>
              </div>

              {/* Similarity Threshold */}
              <div>
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('agent.similarityThreshold', '相似度阈值')}: {(formData.similarityThreshold || 0.7).toFixed(2)}
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={formData.similarityThreshold || 0.7}
                  onChange={(e) => setFormData({ ...formData, similarityThreshold: parseFloat(e.target.value) })}
                  className="w-full"
                />
                <div className="flex justify-between text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                  <span>{t('agent.morePermissive', '更宽松 (0.0)')}</span>
                  <span>{t('agent.moreStrict', '更严格 (1.0)')}</span>
                </div>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-2">
                  {t('agent.similarityThresholdDesc', '检索文档的最小相似度分数。较高的值仅返回高度相关的结果。')}
                </p>
              </div>
            </div>
          )}

          {/* Data Access Tab */}
          {activeTab === 'access' && (
            <div className="space-y-4">
              <div className="p-4 bg-blue-500/10 border border-blue-500/20 rounded-xl">
                <p className="text-sm text-blue-700 dark:text-blue-400 font-medium">
                  {t(
                    'agent.accessLevelEffectiveRule',
                    '访问级别决定默认数据范围；若配置白名单，则在默认范围上进一步收敛。'
                  )}
                </p>
              </div>

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
                  {t('agent.allowedKnowledge', '允许的知识库')}
                </label>
                <div className="p-4 bg-zinc-500/5 border border-zinc-500/10 rounded-xl min-h-[100px]">
                  <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-1">
                    {formData.allowedKnowledge?.length || 0}{' '}
                    {t('agent.knowledgeBasesSelected', '个知识库已选择')}
                  </p>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    {t(
                      'agent.allowedKnowledgeConfiguredInKnowledgeTab',
                      '知识库白名单请在“知识库”标签页中配置。'
                    )}
                  </p>
                </div>
              </div>

              <div>
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('agent.allowedMemory')}
                </label>
                <div className="p-4 bg-zinc-500/5 border border-zinc-500/10 rounded-xl">
                  <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-1">
                    {formData.allowedMemory?.length || 0}{' '}
                    {t('agent.memoryScopesSelected', '个记忆范围已选择')}
                  </p>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-3">
                    {t('agent.allowedMemoryDesc', '选择代理在执行时可检索的记忆范围。')}
                  </p>
                  <div className="space-y-2">
                    {[
                      {
                        id: 'agent',
                        title: t('agent.memoryScopeAgentTitle', 'Agent 记忆'),
                        desc: t(
                          'agent.memoryScopeAgentDesc',
                          '仅检索当前代理的私有历史记忆。'
                        ),
                      },
                      {
                        id: 'company',
                        title: t('agent.memoryScopeCompanyTitle', 'Company 记忆'),
                        desc: t('agent.memoryScopeCompanyDesc', '检索组织共享的通用记忆。'),
                      },
                      {
                        id: 'user_context',
                        title: t('agent.memoryScopeUserContextTitle', '用户上下文'),
                        desc: t(
                          'agent.memoryScopeUserContextDesc',
                          '检索当前用户的偏好和上下文记忆。'
                        ),
                      },
                    ].map((option) => {
                      const isSelected = (formData.allowedMemory || []).includes(option.id);
                      return (
                        <button
                          key={option.id}
                          type="button"
                          onClick={() => toggleMemoryScope(option.id)}
                          className={`w-full text-left p-3 rounded-lg border transition-colors ${
                            isSelected
                              ? 'border-emerald-500 bg-emerald-500/10'
                              : 'border-zinc-200 dark:border-zinc-700 hover:border-emerald-400/60'
                          }`}
                        >
                          <p className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
                            {option.title}
                          </p>
                          <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                            {option.desc}
                          </p>
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>

              <div className="p-4 bg-zinc-500/5 border border-zinc-500/10 rounded-xl">
                <p className="text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('agent.effectiveAccessSummaryTitle', '当前生效规则')}
                </p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-1">
                  {t(
                    'agent.effectiveKnowledgeRule',
                    '知识库：先按权限过滤，再应用允许的知识库白名单（未配置白名单则不额外限制）。'
                  )}
                </p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  {t(
                    'agent.effectiveMemoryRule',
                    '记忆：优先使用“允许的记忆范围”；未配置时按访问级别使用默认范围。'
                  )}{' '}
                  {t('agent.effectiveMemoryScopes', '实际生效的记忆范围')}:{' '}
                  {resolveEffectiveMemoryScopes().join(', ')}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex flex-col gap-3 pt-4 border-t border-zinc-200 dark:border-zinc-700">
          {/* Save Error Display */}
          {saveError && (
            <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-xl flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-semibold text-red-700 dark:text-red-400">
                  Failed to save configuration
                </p>
                <p className="text-xs text-red-600 dark:text-red-500 mt-1">
                  {saveError}
                </p>
              </div>
              <button
                onClick={() => setSaveError(null)}
                className="text-red-500 hover:text-red-600"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

          <div className="flex justify-end gap-3">
            <button
              onClick={onClose}
              disabled={isSaving}
              className="px-6 py-3 bg-zinc-500/5 hover:bg-zinc-500/10 text-zinc-700 dark:text-zinc-300 rounded-xl font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {t('common.cancel')}
            </button>
            <button
              onClick={handleSave}
              disabled={isSaving}
              className="px-6 py-3 bg-emerald-500 hover:bg-emerald-600 text-white rounded-xl font-semibold transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSaving ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  {t('common.save')}
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Image Crop Modal */}
      <ImageCropModal
        isOpen={isAvatarCropModalOpen}
        onClose={() => setIsAvatarCropModalOpen(false)}
        onCropComplete={handleAvatarCropComplete}
        aspectRatio={1}
        title={t('agent.cropAvatar')}
      />
    </div>
  );
};
