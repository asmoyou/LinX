import React, { useState, useEffect } from 'react';
import { X, Save, ChevronDown, ChevronUp, RotateCcw, Eye, Brain, Code, Zap, MessageSquare } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { ModelMetadata } from '@/api/llm';
import { LayoutModal } from '@/components/LayoutModal';

interface EditModelModalProps {
  isOpen: boolean;
  onClose: () => void;
  metadata: ModelMetadata;
  onSave: (metadata: ModelMetadata) => Promise<void>;
}

const MODEL_TYPES = [
  { value: 'chat', icon: '💬', colorActive: 'bg-blue-500 text-white', colorInactive: 'bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400' },
  { value: 'embedding', icon: '🔢', colorActive: 'bg-green-500 text-white', colorInactive: 'bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-400' },
  { value: 'rerank', icon: '🔄', colorActive: 'bg-cyan-500 text-white', colorInactive: 'bg-cyan-50 dark:bg-cyan-900/20 text-cyan-600 dark:text-cyan-400' },
  { value: 'vision', icon: '👁️', colorActive: 'bg-purple-500 text-white', colorInactive: 'bg-purple-50 dark:bg-purple-900/20 text-purple-600 dark:text-purple-400' },
  { value: 'reasoning', icon: '🧠', colorActive: 'bg-amber-500 text-white', colorInactive: 'bg-amber-50 dark:bg-amber-900/20 text-amber-600 dark:text-amber-400' },
  { value: 'code', icon: '💻', colorActive: 'bg-indigo-500 text-white', colorInactive: 'bg-indigo-50 dark:bg-indigo-900/20 text-indigo-600 dark:text-indigo-400' },
  { value: 'image_generation', icon: '🎨', colorActive: 'bg-pink-500 text-white', colorInactive: 'bg-pink-50 dark:bg-pink-900/20 text-pink-600 dark:text-pink-400' },
] as const;

/**
 * Edit Model Modal Component
 *
 * Modal for editing model metadata with form inputs.
 * Adapts fields based on model type (embedding/rerank vs chat models).
 * Inspired by cherry-studio's model editing interface.
 */
export const EditModelModal: React.FC<EditModelModalProps> = ({
  isOpen,
  onClose,
  metadata,
  onSave,
}) => {
  const { t } = useTranslation();
  const [formData, setFormData] = useState<ModelMetadata>(metadata);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  const isEmbeddingOrRerank = formData.model_type === 'embedding' || formData.model_type === 'rerank';
  const isEmbedding = formData.model_type === 'embedding';

  useEffect(() => {
    if (isOpen) {
      setFormData(metadata);
      setHasChanges(false);
      setError(null);
      setShowAdvanced(false);
    }
  }, [isOpen, metadata]);

  const handleSave = async () => {
    setIsSaving(true);
    setError(null);

    try {
      await onSave(formData);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('settings.editModel.errorSaving'));
    } finally {
      setIsSaving(false);
    }
  };

  const handleReset = () => {
    setFormData(metadata);
    setHasChanges(false);
  };

  const updateField = <K extends keyof ModelMetadata>(field: K, value: ModelMetadata[K]) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
    setHasChanges(true);
  };

  const handleModelTypeChange = (newType: string) => {
    const newIsEmbeddingOrRerank = newType === 'embedding' || newType === 'rerank';
    setFormData((prev) => {
      const updated = { ...prev, model_type: newType };
      // When switching to embedding/rerank, clear chat-specific features
      if (newIsEmbeddingOrRerank) {
        updated.supports_vision = false;
        updated.supports_reasoning = false;
        updated.supports_function_calling = false;
        updated.supports_streaming = false;
        updated.supports_system_prompt = false;
        updated.max_output_tokens = undefined;
      }
      // Clear embedding dimension when switching away from embedding
      if (newType !== 'embedding') {
        updated.embedding_dimension = undefined;
      }
      return updated;
    });
    setHasChanges(true);
  };

  const toggleFeature = (feature: 'supports_vision' | 'supports_reasoning' | 'supports_function_calling' | 'supports_streaming' | 'supports_system_prompt') => {
    updateField(feature, !formData[feature]);
  };

  if (!isOpen) return null;

  const typeLabels: Record<string, string> = {
    chat: t('settings.editModel.typeChat'),
    embedding: t('settings.editModel.typeEmbedding'),
    rerank: t('settings.editModel.typeRerank'),
    vision: t('settings.editModel.typeVision'),
    reasoning: t('settings.editModel.typeReasoning'),
    code: t('settings.editModel.typeCode'),
    image_generation: t('settings.editModel.typeImageGen'),
  };

  return (
    <LayoutModal
      isOpen={isOpen}
      onClose={onClose}
      closeOnBackdropClick={false}
      closeOnEscape={true}
    >
      <div className="w-full max-w-2xl my-auto modal-panel rounded-[24px] shadow-2xl max-h-[calc(100vh-var(--app-header-height,4rem)-3rem)] overflow-y-auto">
        {/* Header */}
        <div className="px-4 sm:px-6 py-4 border-b border-zinc-200 dark:border-zinc-700 flex items-center justify-between flex-shrink-0">
          <div className="min-w-0 flex-1">
            <h2 className="text-lg sm:text-xl font-bold text-zinc-900 dark:text-zinc-100 truncate">
              {t('settings.editModel.title')}
            </h2>
            <p className="text-xs sm:text-sm text-zinc-600 dark:text-zinc-400 mt-0.5 truncate">
              {metadata.model_id}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors flex-shrink-0 ml-2"
          >
            <X className="w-5 h-5 text-zinc-600 dark:text-zinc-400" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4 space-y-4">
          {error && (
            <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-sm text-red-700 dark:text-red-400">
              {error}
            </div>
          )}

          {/* Basic Info */}
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
                {t('settings.editModel.modelId')}
              </label>
              <input
                type="text"
                value={formData.model_id}
                disabled
                className="w-full px-3 py-2 bg-zinc-100 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-500 dark:text-zinc-400 cursor-not-allowed"
              />
              <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                {t('settings.editModel.modelIdHint')}
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
                {t('settings.editModel.displayName')}
              </label>
              <input
                type="text"
                value={formData.display_name || ''}
                onChange={(e) => updateField('display_name', e.target.value)}
                placeholder={t('settings.editModel.displayNamePlaceholder')}
                className="w-full px-3 py-2 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
                {t('settings.editModel.description')}
              </label>
              <textarea
                value={formData.description || ''}
                onChange={(e) => updateField('description', e.target.value)}
                placeholder={t('settings.editModel.descriptionPlaceholder')}
                rows={2}
                className="w-full px-3 py-2 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              />
            </div>
          </div>

          {/* Model Type Selector */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                {t('settings.editModel.modelType')}
              </label>
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                {t('settings.editModel.modelTypeHint')}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {MODEL_TYPES.map(({ value, icon, colorActive, colorInactive }) => {
                const isSelected = formData.model_type === value;
                return (
                  <button
                    key={value}
                    onClick={() => handleModelTypeChange(value)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
                      isSelected
                        ? `${colorActive} shadow-sm ring-2 ring-offset-1 ring-offset-white dark:ring-offset-zinc-900 ring-current`
                        : `${colorInactive} hover:opacity-80 cursor-pointer`
                    }`}
                  >
                    <span>{icon}</span>
                    <span>{typeLabels[value] || value}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Model Capabilities - Only for non-embedding/rerank */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                {t('settings.editModel.capabilities')}
              </label>
              <div className="flex items-center gap-2">
                {isEmbeddingOrRerank && (
                  <span className="text-xs text-zinc-400 dark:text-zinc-500 italic">
                    {t('settings.editModel.capabilitiesDisabledHint')}
                  </span>
                )}
                {hasChanges && !isEmbeddingOrRerank && (
                  <button
                    onClick={handleReset}
                    className="flex items-center gap-1 px-2 py-1 text-xs text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded transition-colors"
                  >
                    <RotateCcw className="w-3 h-3" />
                    {t('settings.editModel.reset')}
                  </button>
                )}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <CapabilityTag
                icon={<Eye className="w-3.5 h-3.5" />}
                label={t('settings.editModel.vision')}
                active={formData.supports_vision}
                disabled={isEmbeddingOrRerank}
                onClick={() => toggleFeature('supports_vision')}
              />
              <CapabilityTag
                icon={<Brain className="w-3.5 h-3.5" />}
                label={t('settings.editModel.reasoning')}
                active={formData.supports_reasoning}
                disabled={isEmbeddingOrRerank}
                onClick={() => toggleFeature('supports_reasoning')}
              />
              <CapabilityTag
                icon={<Code className="w-3.5 h-3.5" />}
                label={t('settings.editModel.functionCalling')}
                active={formData.supports_function_calling}
                disabled={isEmbeddingOrRerank}
                onClick={() => toggleFeature('supports_function_calling')}
              />
              <CapabilityTag
                icon={<Zap className="w-3.5 h-3.5" />}
                label={t('settings.editModel.streaming')}
                active={formData.supports_streaming}
                disabled={isEmbeddingOrRerank}
                onClick={() => toggleFeature('supports_streaming')}
              />
              <CapabilityTag
                icon={<MessageSquare className="w-3.5 h-3.5" />}
                label={t('settings.editModel.systemPrompt')}
                active={formData.supports_system_prompt}
                disabled={isEmbeddingOrRerank}
                onClick={() => toggleFeature('supports_system_prompt')}
              />
            </div>
          </div>

          {/* Embedding-Specific Settings */}
          {isEmbedding && (
            <div className="p-4 bg-green-50/50 dark:bg-green-900/10 border border-green-200 dark:border-green-800/30 rounded-lg space-y-3">
              <label className="block text-sm font-semibold text-green-700 dark:text-green-400">
                {t('settings.editModel.embeddingSettings')}
              </label>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
                    {t('settings.editModel.embeddingDimension')}
                  </label>
                  <input
                    type="number"
                    value={formData.embedding_dimension || ''}
                    onChange={(e) => updateField('embedding_dimension', parseInt(e.target.value) || undefined)}
                    placeholder={t('settings.editModel.embeddingDimensionPlaceholder')}
                    className="w-full px-3 py-2 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-green-500"
                  />
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                    {t('settings.editModel.embeddingDimensionHint')}
                  </p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
                    {t('settings.editModel.maxInputTokens')}
                  </label>
                  <input
                    type="number"
                    value={formData.context_window || ''}
                    onChange={(e) => updateField('context_window', parseInt(e.target.value) || undefined)}
                    placeholder={t('settings.editModel.maxInputTokensPlaceholder')}
                    className="w-full px-3 py-2 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-green-500"
                  />
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">{t('settings.editModel.tokens')}</p>
                </div>
              </div>
            </div>
          )}

          {/* Rerank-Specific Settings */}
          {formData.model_type === 'rerank' && (
            <div className="p-4 bg-cyan-50/50 dark:bg-cyan-900/10 border border-cyan-200 dark:border-cyan-800/30 rounded-lg space-y-3">
              <label className="block text-sm font-semibold text-cyan-700 dark:text-cyan-400">
                Rerank {t('settings.editModel.advancedSettings')}
              </label>
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
                  {t('settings.editModel.maxInputTokens')}
                </label>
                <input
                  type="number"
                  value={formData.context_window || ''}
                  onChange={(e) => updateField('context_window', parseInt(e.target.value) || undefined)}
                  placeholder={t('settings.editModel.maxInputTokensPlaceholder')}
                  className="w-full px-3 py-2 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-cyan-500"
                />
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">{t('settings.editModel.tokens')}</p>
              </div>
            </div>
          )}

          {/* Advanced Settings Toggle */}
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="w-full flex items-center justify-between px-4 py-2 bg-zinc-50 dark:bg-zinc-800/50 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors"
          >
            <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
              {t('settings.editModel.advancedSettings')}
            </span>
            {showAdvanced ? (
              <ChevronUp className="w-4 h-4 text-zinc-500" />
            ) : (
              <ChevronDown className="w-4 h-4 text-zinc-500" />
            )}
          </button>

          {/* Advanced Settings */}
          {showAdvanced && (
            <div className="space-y-3 pt-2">
              {/* Context & Output - Only for non-embedding/rerank */}
              {!isEmbeddingOrRerank && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
                      {t('settings.editModel.contextWindow')}
                    </label>
                    <input
                      type="number"
                      value={formData.context_window || ''}
                      onChange={(e) => updateField('context_window', parseInt(e.target.value) || undefined)}
                      placeholder={t('settings.editModel.contextWindowPlaceholder')}
                      className="w-full px-3 py-2 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">{t('settings.editModel.tokens')}</p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
                      {t('settings.editModel.maxOutputTokens')}
                    </label>
                    <input
                      type="number"
                      value={formData.max_output_tokens || ''}
                      onChange={(e) => updateField('max_output_tokens', parseInt(e.target.value) || undefined)}
                      placeholder={t('settings.editModel.maxOutputTokensPlaceholder')}
                      className="w-full px-3 py-2 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">{t('settings.editModel.tokens')}</p>
                  </div>
                </div>
              )}

              {/* Temperature - Only for non-embedding/rerank */}
              {!isEmbeddingOrRerank && (
                <div>
                  <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
                    {t('settings.editModel.defaultTemperature')}
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="2"
                    value={formData.default_temperature}
                    onChange={(e) => updateField('default_temperature', parseFloat(e.target.value))}
                    className="w-full px-3 py-2 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                    {t('settings.editModel.temperatureRange')}: {formData.temperature_range[0]} - {formData.temperature_range[1]}
                  </p>
                </div>
              )}

              {/* Pricing - Shown for all types */}
              <div className="border-t border-zinc-200 dark:border-zinc-700 pt-3">
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('settings.editModel.pricing')}
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-zinc-600 dark:text-zinc-400 mb-1">
                      {t('settings.editModel.inputPrice')}
                    </label>
                    <div className="flex items-center gap-2">
                      <span className="text-zinc-600 dark:text-zinc-400">$</span>
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        value={formData.input_price_per_1m || ''}
                        onChange={(e) => updateField('input_price_per_1m', parseFloat(e.target.value) || undefined)}
                        placeholder="0.00"
                        className="flex-1 px-3 py-2 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs text-zinc-600 dark:text-zinc-400 mb-1">
                      {t('settings.editModel.outputPrice')}
                    </label>
                    <div className="flex items-center gap-2">
                      <span className="text-zinc-600 dark:text-zinc-400">$</span>
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        value={formData.output_price_per_1m || ''}
                        onChange={(e) => updateField('output_price_per_1m', parseFloat(e.target.value) || undefined)}
                        placeholder="0.00"
                        className="flex-1 px-3 py-2 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                    </div>
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
                  {t('settings.editModel.version')}
                </label>
                <input
                  type="text"
                  value={formData.version || ''}
                  onChange={(e) => updateField('version', e.target.value)}
                  placeholder={t('settings.editModel.versionPlaceholder')}
                  className="w-full px-3 py-2 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="deprecated"
                  checked={formData.deprecated}
                  onChange={(e) => updateField('deprecated', e.target.checked)}
                  className="w-4 h-4 text-blue-600 bg-white dark:bg-zinc-800 border-zinc-300 dark:border-zinc-700 rounded focus:ring-2 focus:ring-blue-500"
                />
                <label htmlFor="deprecated" className="text-sm text-zinc-700 dark:text-zinc-300">
                  {t('settings.editModel.markDeprecated')}
                </label>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 sm:px-6 py-3 sm:py-4 border-t border-zinc-200 dark:border-zinc-700 flex items-center justify-end gap-2 sm:gap-3 flex-shrink-0">
          <button
            onClick={onClose}
            disabled={isSaving}
            className="px-3 sm:px-4 py-2 text-sm text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors disabled:opacity-50"
          >
            {t('settings.editModel.cancel')}
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving || !hasChanges}
            className="flex items-center gap-2 px-3 sm:px-4 py-2 text-sm bg-blue-500 hover:bg-blue-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSaving ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                <span className="hidden sm:inline">{t('settings.editModel.saving')}</span>
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                <span className="hidden sm:inline">{t('settings.editModel.saveChanges')}</span>
                <span className="sm:hidden">{t('settings.editModel.save')}</span>
              </>
            )}
          </button>
        </div>
      </div>
    </LayoutModal>
  );
};

interface CapabilityTagProps {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
}

const CapabilityTag: React.FC<CapabilityTagProps> = ({ icon, label, active, disabled, onClick }) => (
  <button
    onClick={disabled ? undefined : onClick}
    disabled={disabled}
    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
      disabled
        ? 'bg-zinc-100 dark:bg-zinc-800 text-zinc-400 dark:text-zinc-600 cursor-not-allowed opacity-50'
        : active
          ? 'bg-blue-500 text-white shadow-sm'
          : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-200 dark:hover:bg-zinc-700'
    }`}
  >
    {icon}
    {label}
  </button>
);
