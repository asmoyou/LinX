import { describe, expect, it } from 'vitest';
import { canEnsureProviderTypedModels } from '@/components/memory/MemoryConfigPanel';

describe('MemoryConfigPanel provider guard', () => {
  it('does not treat a selected provider as loadable before provider list arrives', () => {
    expect(
      canEnsureProviderTypedModels({
        provider: 'vllm',
        availableProviders: {},
        typedModelsByProvider: {},
        loadingModelMetadataByProvider: {},
      }),
    ).toBe(false);
  });

  it('allows typed-model loading once the provider exists in the loaded provider map', () => {
    expect(
      canEnsureProviderTypedModels({
        provider: 'vllm',
        availableProviders: {
          vllm: ['Qwen3.5-27B-FP8'],
        },
        typedModelsByProvider: {},
        loadingModelMetadataByProvider: {},
      }),
    ).toBe(true);
  });

  it('stops duplicate loads when the provider is already cached or loading', () => {
    expect(
      canEnsureProviderTypedModels({
        provider: 'vllm',
        availableProviders: {
          vllm: ['Qwen3.5-27B-FP8'],
        },
        typedModelsByProvider: {
          vllm: {
            embedding: [],
            generation: ['Qwen3.5-27B-FP8'],
            rerank: [],
          },
        },
        loadingModelMetadataByProvider: {},
      }),
    ).toBe(false);

    expect(
      canEnsureProviderTypedModels({
        provider: 'vllm',
        availableProviders: {
          vllm: ['Qwen3.5-27B-FP8'],
        },
        typedModelsByProvider: {},
        loadingModelMetadataByProvider: {
          vllm: true,
        },
      }),
    ).toBe(false);
  });
});
