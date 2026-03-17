import React, { useState, useEffect } from 'react';
import { Loader2, AlertCircle, RefreshCw, ChevronDown, ChevronRight } from 'lucide-react';
import { llmApi } from '@/api';
import type { ProviderModelsMetadata, ModelMetadata } from '@/api/llm';
import { ModelMetadataCard } from './ModelMetadataCard';

interface ProviderModelsManagerProps {
  providerName: string;
}

/**
 * Provider Models Manager Component
 * 
 * Manages and displays all models for a specific provider.
 * Allows viewing and editing model metadata.
 */
export const ProviderModelsManager: React.FC<ProviderModelsManagerProps> = ({ providerName }) => {
  const [providerData, setProviderData] = useState<ProviderModelsMetadata | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedModels, setExpandedModels] = useState<Set<string>>(new Set());
  const [isRefreshing, setIsRefreshing] = useState(false);

  useEffect(() => {
    loadProviderModels();
  }, [providerName]);

  const loadProviderModels = async () => {
    setIsLoading(true);
    setError(null);
    
    try {
      const data = await llmApi.getProviderModelsMetadata(providerName);
      setProviderData(data);
      
      // Auto-expand first model
      if (data.models && Object.keys(data.models).length > 0) {
        setExpandedModels(new Set([Object.keys(data.models)[0]]));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load models');
    } finally {
      setIsLoading(false);
    }
  };

  const handleRefreshMetadata = async () => {
    setIsRefreshing(true);
    setError(null);
    
    try {
      // Call refresh endpoint (admin only)
      await fetch(`/api/v1/llm/providers/${providerName}/models/refresh-metadata`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
        },
      });
      
      // Reload data
      await loadProviderModels();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refresh metadata');
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleUpdateMetadata = async (modelName: string, metadata: ModelMetadata) => {
    await llmApi.updateModelMetadata(providerName, modelName, metadata);

    // Update local state
    if (providerData) {
      setProviderData({
        ...providerData,
        models: {
          ...providerData.models,
          [modelName]: metadata,
        },
      });
    }
  };

  const toggleModel = (modelName: string) => {
    setExpandedModels((prev) => {
      const next = new Set(prev);
      if (next.has(modelName)) {
        next.delete(modelName);
      } else {
        next.add(modelName);
      }
      return next;
    });
  };

  const getModelFeatures = (metadata: ModelMetadata): string[] => {
    const features: string[] = [];
    const seen = new Set<string>();
    const addFeature = (feature: string) => {
      if (seen.has(feature)) return;
      seen.add(feature);
      features.push(feature);
    };

    const modelTypeFeatures: Record<string, string> = {
      embedding: 'Embedding',
      rerank: 'Rerank',
      audio: 'Speech Transcription',
      asr: 'Speech Transcription',
      image_generation: 'Image Generation',
      code: 'Code',
      vision: 'Vision',
      reasoning: 'Reasoning',
    };

    if (metadata.model_type && modelTypeFeatures[metadata.model_type]) {
      addFeature(modelTypeFeatures[metadata.model_type]);
    }
    if (metadata.supports_vision) addFeature('Vision');
    if (metadata.supports_reasoning) addFeature('Reasoning');
    if (metadata.supports_function_calling) addFeature('Function Calling');
    if (metadata.supports_streaming) addFeature('Streaming');
    if (metadata.supports_system_prompt) addFeature('System Prompt');
    if (metadata.supports_audio_transcription) addFeature('Speech Transcription');

    return features;
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
        <span className="ml-2 text-sm text-zinc-600 dark:text-zinc-400">
          Loading models...
        </span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-start gap-2 p-4 bg-red-500/10 border border-red-500/20 rounded-xl">
        <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
        <div className="flex-1">
          <p className="text-sm font-semibold text-red-700 dark:text-red-400">Error</p>
          <p className="text-sm text-red-600 dark:text-red-500 mt-1">{error}</p>
        </div>
        <button
          onClick={loadProviderModels}
          className="px-3 py-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-700 dark:text-red-400 rounded-lg text-sm font-medium transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!providerData || Object.keys(providerData.models).length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          No models found for this provider
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
            {providerData.provider_name} Models
          </h3>
          <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-0.5">
            {Object.keys(providerData.models).length} models • Protocol: {providerData.protocol}
          </p>
        </div>
        
        <button
          onClick={handleRefreshMetadata}
          disabled={isRefreshing}
          className="flex items-center gap-2 px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
          {isRefreshing ? 'Refreshing...' : 'Refresh Metadata'}
        </button>
      </div>

      {/* Models List */}
      <div className="space-y-2">
        {Object.entries(providerData.models).map(([modelName, metadata]) => {
          const isExpanded = expandedModels.has(modelName);
          const modelFeatures = getModelFeatures(metadata);
          
          return (
            <div
              key={modelName}
              className="border border-zinc-200 dark:border-zinc-700 rounded-xl overflow-hidden"
            >
              {/* Model Header */}
              <button
                onClick={() => toggleModel(modelName)}
                className="w-full px-4 py-3 bg-zinc-50 dark:bg-zinc-800/50 hover:bg-zinc-100 dark:hover:bg-zinc-800 flex items-center justify-between transition-colors"
              >
                <div className="flex items-center gap-3">
                  {isExpanded ? (
                    <ChevronDown className="w-4 h-4 text-zinc-500" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-zinc-500" />
                  )}
                  <div className="text-left">
                    <h4 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                      {modelName}
                    </h4>
                    <p className="text-xs text-zinc-600 dark:text-zinc-400 mt-0.5">
                      {modelFeatures.length > 0
                        ? modelFeatures.slice(0, 3).join(', ')
                        : metadata.model_type || 'chat'}
                      {modelFeatures.length > 3 && ` +${modelFeatures.length - 3} more`}
                    </p>
                  </div>
                </div>
                
                <div className="flex items-center gap-2">
                  {metadata.supports_vision && (
                    <span className="px-2 py-0.5 bg-purple-500/10 text-purple-700 dark:text-purple-400 text-xs rounded border border-purple-500/20">
                      Vision
                    </span>
                  )}
                  {metadata.supports_reasoning && (
                    <span className="px-2 py-0.5 bg-amber-500/10 text-amber-700 dark:text-amber-400 text-xs rounded border border-amber-500/20">
                      Reasoning
                    </span>
                  )}
                  {metadata.supports_function_calling && (
                    <span className="px-2 py-0.5 bg-green-500/10 text-green-700 dark:text-green-400 text-xs rounded border border-green-500/20">
                      Functions
                    </span>
                  )}
                  {metadata.supports_audio_transcription && (
                    <span className="px-2 py-0.5 bg-orange-500/10 text-orange-700 dark:text-orange-400 text-xs rounded border border-orange-500/20">
                      ASR
                    </span>
                  )}
                  {metadata.deprecated && (
                    <span className="px-2 py-0.5 bg-red-500/10 text-red-700 dark:text-red-400 text-xs rounded border border-red-500/20">
                      Deprecated
                    </span>
                  )}
                </div>
              </button>

              {/* Model Details */}
              {isExpanded && (
                <div className="p-4 bg-white dark:bg-zinc-900">
                  <ModelMetadataCard
                    metadata={metadata}
                    onUpdate={(updated) => handleUpdateMetadata(modelName, updated)}
                    isEditable={true}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
