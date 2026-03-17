import React, { useState } from 'react';
import { 
  Info, 
  Edit2, 
  Save, 
  X, 
  Eye, 
  Mic,
  MessageSquare, 
  Zap, 
  Code, 
  Brain,
  CheckCircle2,
  XCircle,
  AlertCircle
} from 'lucide-react';
import type { ModelMetadata } from '@/api/llm';

interface ModelMetadataCardProps {
  metadata: ModelMetadata;
  onUpdate?: (metadata: ModelMetadata) => Promise<void>;
  isEditable?: boolean;
}

/**
 * Model Metadata Card Component
 * 
 * Displays model information in a clean, organized layout inspired by cherry-studio.
 * Supports viewing and editing model metadata.
 */
export const ModelMetadataCard: React.FC<ModelMetadataCardProps> = ({
  metadata,
  onUpdate,
  isEditable = false,
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const [editedMetadata, setEditedMetadata] = useState<ModelMetadata>(metadata);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    if (!onUpdate) return;
    
    setIsSaving(true);
    setError(null);
    
    try {
      await onUpdate(editedMetadata);
      setIsEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update metadata');
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancel = () => {
    setEditedMetadata(metadata);
    setIsEditing(false);
    setError(null);
  };

  return (
    <div className="bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 bg-zinc-50 dark:bg-zinc-800/50 border-b border-zinc-200 dark:border-zinc-700 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Info className="w-4 h-4 text-blue-500" />
          <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            {metadata.display_name || metadata.model_id}
          </h3>
          {metadata.deprecated && (
            <span className="px-2 py-0.5 bg-red-500/10 text-red-700 dark:text-red-400 text-xs rounded border border-red-500/20">
              Deprecated
            </span>
          )}
        </div>
        
        {isEditable && !isEditing && (
          <button
            onClick={() => setIsEditing(true)}
            className="p-1.5 hover:bg-zinc-200 dark:hover:bg-zinc-700 rounded-lg transition-colors"
            title="Edit metadata"
          >
            <Edit2 className="w-4 h-4 text-zinc-600 dark:text-zinc-400" />
          </button>
        )}
        
        {isEditing && (
          <div className="flex items-center gap-1">
            <button
              onClick={handleSave}
              disabled={isSaving}
              className="p-1.5 hover:bg-green-500/10 text-green-600 dark:text-green-400 rounded-lg transition-colors disabled:opacity-50"
              title="Save changes"
            >
              <Save className="w-4 h-4" />
            </button>
            <button
              onClick={handleCancel}
              disabled={isSaving}
              className="p-1.5 hover:bg-red-500/10 text-red-600 dark:text-red-400 rounded-lg transition-colors disabled:opacity-50"
              title="Cancel"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-4 space-y-4">
        {error && (
          <div className="flex items-start gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
            <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
          </div>
        )}

        {/* Description */}
        {metadata.description && (
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            {metadata.description}
          </p>
        )}

        {/* Features */}
        <div>
          <h4 className="text-xs font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide mb-2">
            Features
          </h4>
          <div className="grid grid-cols-2 gap-2">
            <FeatureItem
              label="Vision"
              value={metadata.supports_vision}
              icon={<Eye className="w-3.5 h-3.5" />}
            />
            <FeatureItem
              label="Reasoning"
              value={metadata.supports_reasoning}
              icon={<Brain className="w-3.5 h-3.5" />}
            />
            <FeatureItem
              label="Function Calling"
              value={metadata.supports_function_calling}
              icon={<Code className="w-3.5 h-3.5" />}
            />
            <FeatureItem
              label="Streaming"
              value={metadata.supports_streaming}
              icon={<Zap className="w-3.5 h-3.5" />}
            />
            <FeatureItem
              label="System Prompt"
              value={metadata.supports_system_prompt}
              icon={<MessageSquare className="w-3.5 h-3.5" />}
            />
            <FeatureItem
              label="Speech Transcription"
              value={Boolean(metadata.supports_audio_transcription)}
              icon={<Mic className="w-3.5 h-3.5" />}
            />
          </div>
        </div>

        {/* Model Properties */}
        <div>
          <h4 className="text-xs font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide mb-2">
            Model Properties
          </h4>
          <div className="grid grid-cols-2 gap-3">
            {metadata.context_window && (
              <PropertyItem
                label="Context Window"
                value={`${metadata.context_window.toLocaleString()} tokens`}
                sublabel="Total input + output limit"
              />
            )}
            {metadata.max_output_tokens && (
              <PropertyItem
                label="Max Output"
                value={`${metadata.max_output_tokens.toLocaleString()} tokens`}
                sublabel="Maximum response length"
              />
            )}
            <PropertyItem
              label="Temperature"
              value={`${metadata.default_temperature} (${metadata.temperature_range[0]}-${metadata.temperature_range[1]})`}
              sublabel="Default and range"
            />
            {metadata.version && (
              <PropertyItem
                label="Version"
                value={metadata.version}
                sublabel={metadata.release_date || undefined}
              />
            )}
          </div>
        </div>

        {/* Pricing */}
        {(metadata.input_price_per_1m || metadata.output_price_per_1m) && (
          <div>
            <h4 className="text-xs font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide mb-2">
              Pricing (per 1M tokens)
            </h4>
            <div className="grid grid-cols-2 gap-3">
              {metadata.input_price_per_1m && (
                <PropertyItem
                  label="Input"
                  value={`$${metadata.input_price_per_1m.toFixed(2)}`}
                />
              )}
              {metadata.output_price_per_1m && (
                <PropertyItem
                  label="Output"
                  value={`$${metadata.output_price_per_1m.toFixed(2)}`}
                />
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

interface FeatureItemProps {
  label: string;
  value: boolean;
  icon: React.ReactNode;
}

const FeatureItem: React.FC<FeatureItemProps> = ({ label, value, icon }) => (
  <div className="flex items-center gap-2 px-2.5 py-1.5 bg-zinc-50 dark:bg-zinc-800/50 rounded-lg">
    <div className={`${value ? 'text-green-600 dark:text-green-400' : 'text-zinc-400 dark:text-zinc-600'}`}>
      {icon}
    </div>
    <span className="text-xs text-zinc-700 dark:text-zinc-300 flex-1">{label}</span>
    {value ? (
      <CheckCircle2 className="w-3.5 h-3.5 text-green-600 dark:text-green-400" />
    ) : (
      <XCircle className="w-3.5 h-3.5 text-zinc-400 dark:text-zinc-600" />
    )}
  </div>
);

interface PropertyItemProps {
  label: string;
  value: string;
  sublabel?: string;
}

const PropertyItem: React.FC<PropertyItemProps> = ({ label, value, sublabel }) => (
  <div className="px-2.5 py-2 bg-zinc-50 dark:bg-zinc-800/50 rounded-lg">
    <div className="text-xs text-zinc-500 dark:text-zinc-400 mb-0.5">{label}</div>
    <div className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{value}</div>
    {sublabel && (
      <div className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">{sublabel}</div>
    )}
  </div>
);
