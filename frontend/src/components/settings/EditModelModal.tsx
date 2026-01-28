import React, { useState, useEffect } from 'react';
import { X, Save, ChevronDown, ChevronUp, RotateCcw, Eye, Brain, Code, Zap, MessageSquare, Image as ImageIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { ModelMetadata } from '@/api/llm';

interface EditModelModalProps {
  isOpen: boolean;
  onClose: () => void;
  metadata: ModelMetadata;
  onSave: (metadata: ModelMetadata) => Promise<void>;
}

/**
 * Edit Model Modal Component
 * 
 * Modal for editing model metadata with form inputs.
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

  const toggleCapability = (capability: string) => {
    const capabilities = formData.capabilities.includes(capability)
      ? formData.capabilities.filter((c) => c !== capability)
      : [...formData.capabilities, capability];
    updateField('capabilities', capabilities);
  };

  const toggleFeature = (feature: 'supports_vision' | 'supports_reasoning' | 'supports_function_calling' | 'supports_streaming' | 'supports_system_prompt') => {
    updateField(feature, !formData[feature]);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm overflow-auto" style={{ marginLeft: 'var(--sidebar-width, 0px)' }}>
      <div className="w-full max-w-2xl my-auto bg-white dark:bg-zinc-900 rounded-2xl shadow-2xl max-h-[90vh] overflow-y-auto">
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

          {/* Model Capabilities */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                {t('settings.editModel.capabilities')}
              </label>
              {hasChanges && (
                <button
                  onClick={handleReset}
                  className="flex items-center gap-1 px-2 py-1 text-xs text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded transition-colors"
                >
                  <RotateCcw className="w-3 h-3" />
                  {t('settings.editModel.reset')}
                </button>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              <CapabilityTag
                icon={<Eye className="w-3.5 h-3.5" />}
                label={t('settings.editModel.vision')}
                active={formData.supports_vision}
                onClick={() => toggleFeature('supports_vision')}
              />
              <CapabilityTag
                icon={<Brain className="w-3.5 h-3.5" />}
                label={t('settings.editModel.reasoning')}
                active={formData.supports_reasoning}
                onClick={() => toggleFeature('supports_reasoning')}
              />
              <CapabilityTag
                icon={<Code className="w-3.5 h-3.5" />}
                label={t('settings.editModel.functionCalling')}
                active={formData.supports_function_calling}
                onClick={() => toggleFeature('supports_function_calling')}
              />
              <CapabilityTag
                icon={<Zap className="w-3.5 h-3.5" />}
                label={t('settings.editModel.streaming')}
                active={formData.supports_streaming}
                onClick={() => toggleFeature('supports_streaming')}
              />
              <CapabilityTag
                icon={<MessageSquare className="w-3.5 h-3.5" />}
                label={t('settings.editModel.systemPrompt')}
                active={formData.supports_system_prompt}
                onClick={() => toggleFeature('supports_system_prompt')}
              />
            </div>
          </div>

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
    </div>
  );
};

interface CapabilityTagProps {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  onClick: () => void;
}

const CapabilityTag: React.FC<CapabilityTagProps> = ({ icon, label, active, onClick }) => (
  <button
    onClick={onClick}
    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
      active
        ? 'bg-blue-500 text-white shadow-sm'
        : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-200 dark:hover:bg-zinc-700'
    }`}
  >
    {icon}
    {label}
  </button>
);
