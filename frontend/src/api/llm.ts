/**
 * LLM Provider API
 */
import apiClient from './client';

export interface ProviderModels {
  [providerName: string]: string[];
}

export interface ProviderStatus {
  name: string;
  healthy: boolean;
  available_models: string[];
  is_config_based?: boolean;
}

export interface LLMConfig {
  providers: Record<string, ProviderStatus>;
  default_provider: string;
  fallback_enabled: boolean;
  model_mapping: Record<string, Record<string, string>>;
}

export interface ProviderResponse {
  name: string;
  protocol: string;
  base_url: string;
  timeout: number;
  max_retries: number;
  selected_models: string[];
  enabled: boolean;
  has_api_key: boolean;
  is_config_based?: boolean;
}

export interface ProviderCreateRequest {
  name: string;
  protocol: 'ollama' | 'openai_compatible';
  base_url: string;
  selected_models: string[];
  api_key?: string;
  timeout?: number;
  max_retries?: number;
}

export interface ProviderUpdateRequest {
  base_url?: string;
  selected_models?: string[];
  api_key?: string;
  timeout?: number;
  max_retries?: number;
  enabled?: boolean;
}

export interface TestConnectionRequest {
  protocol: 'ollama' | 'openai_compatible';
  base_url: string;
  api_key?: string;
  timeout?: number;
}

export interface TestConnectionResponse {
  success: boolean;
  message: string;
  available_models?: string[];
  error?: string;
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
  display_name?: string;
  description?: string;
  capabilities: string[];
  context_window?: number;
  max_output_tokens?: number;
  default_temperature: number;
  temperature_range: [number, number];
  supports_streaming: boolean;
  supports_system_prompt: boolean;
  input_price_per_1k?: number;
  output_price_per_1k?: number;
  version?: string;
  release_date?: string;
  deprecated: boolean;
}

export interface ProviderModelsMetadata {
  provider_name: string;
  protocol: string;
  models: Record<string, ModelMetadata>;
}

/**
 * Get available providers and their models for agent configuration
 */
export const getAvailableProviders = async (): Promise<ProviderModels> => {
  const response = await apiClient.get<ProviderModels>('/llm/providers/available');
  return response.data;
};

/**
 * Get all LLM providers configuration
 */
export const getProvidersConfig = async (): Promise<LLMConfig> => {
  const response = await apiClient.get<LLMConfig>('/llm/providers');
  return response.data;
};

/**
 * Get specific provider details
 */
export const getProviderDetail = async (name: string): Promise<ProviderResponse> => {
  const response = await apiClient.get<ProviderResponse>(`/llm/providers/${name}`);
  return response.data;
};

/**
 * Create new provider
 */
export const createProvider = async (data: ProviderCreateRequest): Promise<ProviderResponse> => {
  const response = await apiClient.post<ProviderResponse>('/llm/providers', data);
  return response.data;
};

/**
 * Update provider
 */
export const updateProvider = async (
  name: string,
  data: ProviderUpdateRequest
): Promise<ProviderResponse> => {
  const response = await apiClient.put<ProviderResponse>(`/llm/providers/${name}`, data);
  return response.data;
};

/**
 * Delete provider
 */
export const deleteProvider = async (name: string): Promise<void> => {
  await apiClient.delete(`/llm/providers/${name}`);
};

/**
 * Test provider connection
 */
export const testConnection = async (
  data: TestConnectionRequest
): Promise<TestConnectionResponse> => {
  const response = await apiClient.post<TestConnectionResponse>(
    '/llm/providers/test-connection',
    data
  );
  return response.data;
};

/**
 * Test LLM generation
 */
export const testGeneration = async (
  data: TestGenerationRequest
): Promise<TestGenerationResponse> => {
  const response = await apiClient.post<TestGenerationResponse>('/llm/test', data);
  return response.data;
};



/**
 * Get provider models
 */
export const getProviderModels = async (providerName: string): Promise<string[]> => {
  const response = await apiClient.get<string[]>(`/llm/providers/${providerName}/models`);
  return response.data;
};

/**
 * Check provider health
 */
export const checkProviderHealth = async (providerName: string): Promise<{ healthy: boolean }> => {
  const response = await apiClient.get<{ healthy: boolean }>(
    `/llm/providers/${providerName}/health`
  );
  return response.data;
};

/**
 * Get provider models metadata
 */
export const getProviderModelsMetadata = async (
  providerName: string
): Promise<ProviderModelsMetadata> => {
  const response = await apiClient.get<ProviderModelsMetadata>(
    `/llm/providers/${providerName}/models/metadata`
  );
  return response.data;
};

/**
 * Update model metadata
 */
export const updateModelMetadata = async (
  providerName: string,
  modelName: string,
  metadata: ModelMetadata
): Promise<{ success: boolean; message: string }> => {
  const response = await apiClient.put<{ success: boolean; message: string }>(
    `/llm/providers/${providerName}/models/${modelName}/metadata`,
    metadata
  );
  return response.data;
};

export const llmApi = {
  getAvailableProviders,
  getProvidersConfig,
  getProviderDetail,
  createProvider,
  updateProvider,
  deleteProvider,
  testConnection,
  testGeneration,
  getProviderModels,
  checkProviderHealth,
  getProviderModelsMetadata,
  updateModelMetadata,
};
