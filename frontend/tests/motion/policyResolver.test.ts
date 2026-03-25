import { describe, expect, it } from 'vitest';

import {
  DEFAULT_UI_EXPERIENCE_SETTINGS,
  evaluateMotionRuntimeWindow,
  resolveBaseMotionPreference,
  resolveEffectiveMotionTier,
  resolveInitialAutoTier,
  resolveMotionDeviceClass,
  resolveMotionPreferenceSource,
} from '@/motion';

describe('motion policy resolver', () => {
  it('prefers user motion preference over platform default when an override exists', () => {
    expect(
      resolveBaseMotionPreference({
        platformSettings: {
          ...DEFAULT_UI_EXPERIENCE_SETTINGS,
          default_motion_preference: 'reduced',
        },
        userPreference: 'full',
        hasUserPreferenceOverride: true,
      }),
    ).toBe('full');

    expect(
      resolveBaseMotionPreference({
        platformSettings: {
          ...DEFAULT_UI_EXPERIENCE_SETTINGS,
          default_motion_preference: 'reduced',
        },
        userPreference: 'full',
        hasUserPreferenceOverride: false,
      }),
    ).toBe('reduced');
  });

  it('forces reduced or off tiers when system preferences or emergency shutdown apply', () => {
    expect(
      resolveEffectiveMotionTier({
        basePreference: 'full',
        runtimeTier: 'full',
        emergencyDisableMotion: false,
        osReducedMotion: true,
      }),
    ).toBe('reduced');

    expect(
      resolveEffectiveMotionTier({
        basePreference: 'full',
        runtimeTier: 'full',
        emergencyDisableMotion: true,
        osReducedMotion: false,
      }),
    ).toBe('off');

    expect(
      resolveMotionPreferenceSource({
        emergencyDisableMotion: true,
        osReducedMotion: false,
        basePreference: 'auto',
        effectiveTier: 'off',
        hasUserPreferenceOverride: false,
      }),
    ).toBe('emergency_disable_motion');
  });

  it('starts auto mode in reduced tier for low-end devices', () => {
    expect(
      resolveMotionDeviceClass({
        saveData: true,
        hardwareConcurrency: 8,
        deviceMemory: 8,
      }),
    ).toBe('low');

    expect(
      resolveInitialAutoTier({
        saveData: false,
        hardwareConcurrency: 8,
        deviceMemory: 8,
        deviceClass: 'standard',
      }),
    ).toBe('full');

    expect(
      resolveInitialAutoTier({
        saveData: true,
        hardwareConcurrency: 2,
        deviceMemory: 2,
        deviceClass: 'low',
      }),
    ).toBe('reduced');
  });

  it('downgrades after consecutive degraded frame windows', () => {
    const firstWindow = evaluateMotionRuntimeWindow({
      runtimeTier: 'full',
      avgFps: 44,
      p95FrameMs: 30,
      longTaskCountOver80: 0,
      longTaskCountOver120: 0,
      lowWindowCount: 0,
      stableWindowMs: 0,
    });

    expect(firstWindow.nextTier).toBe('full');
    expect(firstWindow.lowWindowCount).toBe(1);
    expect(firstWindow.downgraded).toBe(false);

    const secondWindow = evaluateMotionRuntimeWindow({
      runtimeTier: 'full',
      avgFps: 43,
      p95FrameMs: 31,
      longTaskCountOver80: 0,
      longTaskCountOver120: 0,
      lowWindowCount: firstWindow.lowWindowCount,
      stableWindowMs: firstWindow.stableWindowMs,
    });

    expect(secondWindow.nextTier).toBe('reduced');
    expect(secondWindow.downgraded).toBe(true);
  });

  it('recovers only one tier after 60 seconds of stable windows', () => {
    let currentTier: 'reduced' | 'full' = 'reduced';
    let lowWindowCount = 0;
    let stableWindowMs = 0;

    for (let index = 0; index < 5; index += 1) {
      const evaluation = evaluateMotionRuntimeWindow({
        runtimeTier: currentTier,
        avgFps: 60,
        p95FrameMs: 16,
        longTaskCountOver80: 0,
        longTaskCountOver120: 0,
        lowWindowCount,
        stableWindowMs,
      });

      expect(evaluation.upgraded).toBe(false);
      currentTier = evaluation.nextTier;
      lowWindowCount = evaluation.lowWindowCount;
      stableWindowMs = evaluation.stableWindowMs;
    }

    const recoveryWindow = evaluateMotionRuntimeWindow({
      runtimeTier: currentTier,
      avgFps: 60,
      p95FrameMs: 16,
      longTaskCountOver80: 0,
      longTaskCountOver120: 0,
      lowWindowCount,
      stableWindowMs,
    });

    expect(recoveryWindow.nextTier).toBe('full');
    expect(recoveryWindow.upgraded).toBe(true);
  });
});
