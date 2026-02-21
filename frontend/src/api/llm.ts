import apiClient from './client';
import type { RequestConfigWithMeta } from './client';

/**
 * LLM Provider API
 * 
 * Provides methods for managing LLM providers and testing connections.
 */

export interface TestConnectionRequest {
  protocol: string;
  base_url: string;
  api_key?: string;
  timeout?: number;
}

export interface TestConnectionResponse {
  success: boolean;
  message: string;
  available_models: string[];
  error?: string;
}

export interface ProviderResponse {
  name: string;
  protocol: string;
  base_url: string;
  timeout: number;
  max_retries: number;
  enabled: boolean;
  selected_models: string[];
  has_api_key: boolean;
  is_config_based?: boolean;
}

export interface CreateProviderRequest {
  name: string;
  protocol: string;
  base_url: string;
  selected_models: string[];
  api_key?: string;
  timeout?: number;
  max_retries?: number;
}

export interface UpdateProviderRequest {
  base_url?: string;
  selected_models?: string[];
  api_key?: string;
  timeout?: number;
  max_retries?: number;
  enabled?: boolean;
}

export interface ProviderListResponse {
  providers: ProviderResponse[];
  total: number;
}

export interface ProviderStatus {
  name: string;
  healthy: boolean;
  available_models: string[];
  is_config_based: boolean;
}

export interface LLMConfig {
  providers: Record<string, ProviderStatus>;
  default_provider: string;
  fallback_enabled: boolean;
  model_mapping: Record<string, Record<string, string>>;
}

export interface TestGenerationRequest {
  prompt: string;
  provider?: string;
  model?: string;
  temperature?: number;
  max_tokens?: number;
}

export interface TestGenerationResponse {
  content: string;
  model: string;
  provider: string;
  tokens_used: number;
  success: boolean;
}

export interface ModelMetadata {
  model_id: string;
  model_type?: string;  // chat, vision, reasoning, embedding, rerank, code, image_generation
  display_name?: string;
  description?: string;
  capabilities: string[];
  context_window?: number;
  max_output_tokens?: number;
  embedding_dimension?: number;  // Vector dimension for embedding models (e.g., 1536, 768)
  default_temperature: number;
  temperature_range: [number, number];
  supports_streaming: boolean;
  supports_system_prompt: boolean;
  supports_function_calling: boolean;
  supports_vision: boolean;
  supports_reasoning: boolean;
  input_price_per_1m?: number;  // Per 1 million tokens
  output_price_per_1m?: number;  // Per 1 million tokens
  version?: string;
  release_date?: string;
  deprecated: boolean;
}

export interface ProviderModelsMetadata {
  provider_name: string;
  protocol: string;
  models: Record<string, ModelMetadata>;
}

export interface ApiRequestOptions {
  suppressErrorToast?: boolean;
}

export const llmApi = {
  /**
   * Test connection to a provider
   */
  testConnection: async (data: TestConnectionRequest): Promise<TestConnectionResponse> => {
    const response = await apiClient.post<TestConnectionResponse>(
      '/llm/providers/test-connection',
      data
    );
    return response.data;
  },

  /**
   * Get LLM configuration (providers status and settings)
   */
  getProvidersConfig: async (): Promise<LLMConfig> => {
    const response = await apiClient.get<LLMConfig>('/llm/providers');
    return response.data;
  },

  /**
   * List all providers (admin only)
   */
  listProviders: async (): Promise<ProviderListResponse> => {
    const response = await apiClient.get<ProviderListResponse>('/llm/providers/list');
    return response.data;
  },

  /**
   * Get provider details (admin only)
   */
  getProviderDetail: async (name: string): Promise<ProviderResponse> => {
    const response = await apiClient.get<ProviderResponse>(`/llm/providers/${name}`);
    return response.data;
  },

  /**
   * Create a new provider (admin only)
   */
  createProvider: async (data: CreateProviderRequest): Promise<ProviderResponse> => {
    const response = await apiClient.post<ProviderResponse>('/llm/providers', data);
    return response.data;
  },

  /**
   * Update an existing provider (admin only)
   */
  updateProvider: async (
    name: string,
    data: UpdateProviderRequest
  ): Promise<ProviderResponse> => {
    const response = await apiClient.put<ProviderResponse>(`/llm/providers/${name}`, data);
    return response.data;
  },

  /**
   * Delete a provider (admin only)
   */
  deleteProvider: async (name: string): Promise<void> => {
    await apiClient.delete(`/llm/providers/${name}`);
  },

  /**
   * Get available providers and models for agent configuration
   */
  getAvailableProviders: async (
    options?: ApiRequestOptions
  ): Promise<Record<string, string[]>> => {
    const requestConfig: RequestConfigWithMeta = {
      suppressErrorToast: options?.suppressErrorToast,
    };
    const response = await apiClient.get<Record<string, string[]>>(
      '/llm/providers/available',
      requestConfig
    );
    return response.data;
  },

  /**
   * Test generation with a provider
   */
  testGeneration: async (data: TestGenerationRequest): Promise<TestGenerationResponse> => {
    const response = await apiClient.post<TestGenerationResponse>('/llm/test', data);
    return response.data;
  },

  /**
   * Get models metadata for a provider
   */
  getProviderModelsMetadata: async (providerName: string): Promise<ProviderModelsMetadata> => {
    const response = await apiClient.get<ProviderModelsMetadata>(
      `/llm/providers/${providerName}/models/metadata`
    );
    return response.data;
  },

  /**
   * Get metadata for a specific model
   */
  getModelMetadata: async (providerName: string, modelName: string): Promise<ModelMetadata> => {
    // URL encode the model name to handle special characters like slashes
    const encodedModelName = encodeURIComponent(modelName);
    const response = await apiClient.get<ModelMetadata>(
      `/llm/providers/${providerName}/models/${encodedModelName}/metadata`
    );
    return response.data;
  },

  /**
   * Update metadata for a specific model (admin only)
   */
  updateModelMetadata: async (
    providerName: string,
    modelName: string,
    metadata: ModelMetadata
  ): Promise<{ success: boolean; message: string }> => {
    const response = await apiClient.put<{ success: boolean; message: string }>(
      `/llm/providers/${providerName}/models/${modelName}/metadata`,
      metadata
    );
    return response.data;
  },

  /**
   * Refresh models metadata from provider API (admin only)
   */
  refreshModelsMetadata: async (
    providerName: string
  ): Promise<{ success: boolean; message: string; models_count: number }> => {
    const response = await apiClient.post<{ success: boolean; message: string; models_count: number }>(
      `/llm/providers/${providerName}/models/refresh-metadata`
    );
    return response.data;
  },
};
