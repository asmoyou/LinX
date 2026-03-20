import { describe, expect, it } from 'vitest';

import { getRuntimeStatusMessage } from '@/pages/agentConversationRuntime';

describe('getRuntimeStatusMessage', () => {
  const translate = (key: string, fallback: string) => `${key}:${fallback}`;

  it('returns restored message when a new runtime is restored from snapshot', () => {
    expect(
      getRuntimeStatusMessage(
        {
          is_new_runtime: true,
          restored_from_snapshot: true,
        },
        translate,
      ),
    ).toBe('agent.runtimeRestored:Runtime restored from the latest snapshot.');
  });

  it('returns fresh runtime message when a new runtime is created without restore', () => {
    expect(
      getRuntimeStatusMessage(
        {
          is_new_runtime: true,
          restored_from_snapshot: false,
        },
        translate,
      ),
    ).toBe('agent.runtimeFresh:Runtime started for this conversation.');
  });

  it('returns null when the runtime is reused', () => {
    expect(
      getRuntimeStatusMessage(
        {
          is_new_runtime: false,
          restored_from_snapshot: true,
        },
        translate,
      ),
    ).toBeNull();
  });
});
