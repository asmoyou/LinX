import { describe, expect, it } from 'vitest';

import { shouldReportMotionTelemetry } from '@/motion';

describe('motion telemetry gating', () => {
  it('blocks telemetry when privacy settings disable collection', () => {
    expect(
      shouldReportMotionTelemetry({
        isAuthenticated: true,
        allowTelemetry: false,
        isSampled: true,
        windowCount: 3,
      }),
    ).toBe(false);
  });

  it('requires authentication, sampling, and at least one metrics window', () => {
    expect(
      shouldReportMotionTelemetry({
        isAuthenticated: false,
        allowTelemetry: true,
        isSampled: true,
        windowCount: 3,
      }),
    ).toBe(false);

    expect(
      shouldReportMotionTelemetry({
        isAuthenticated: true,
        allowTelemetry: true,
        isSampled: false,
        windowCount: 3,
      }),
    ).toBe(false);

    expect(
      shouldReportMotionTelemetry({
        isAuthenticated: true,
        allowTelemetry: true,
        isSampled: true,
        windowCount: 0,
      }),
    ).toBe(false);

    expect(
      shouldReportMotionTelemetry({
        isAuthenticated: true,
        allowTelemetry: true,
        isSampled: true,
        windowCount: 1,
      }),
    ).toBe(true);
  });
});
