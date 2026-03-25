import { createContext } from 'react';

import { DEFAULT_UI_EXPERIENCE_SETTINGS } from './policyResolver';
import type {
  MotionPreference,
  MotionPreferenceSource,
  MotionTelemetrySnapshot,
  MotionTier,
  UiExperienceSettings,
} from './types';

export interface MotionContextValue {
  basePreference: MotionPreference;
  effectiveTier: MotionTier;
  source: MotionPreferenceSource;
  osReducedMotion: boolean;
  saveData: boolean;
  deviceClass: 'low' | 'standard';
  platformSettings: UiExperienceSettings;
  userPreference: MotionPreference;
  hasUserPreferenceOverride: boolean;
  telemetrySnapshot: MotionTelemetrySnapshot;
  setPlatformSettings: (settings: Partial<UiExperienceSettings>) => void;
  setUserPreference: (preference: MotionPreference, hasOverride?: boolean) => void;
  clearUserPreference: () => void;
}

const DEFAULT_TELEMETRY_SNAPSHOT: MotionTelemetrySnapshot = {
  avgFps: 60,
  p95FrameMs: 16,
  longTaskCount: 0,
  downgradeCount: 0,
  sampledAt: new Date(0).toISOString(),
  windowCount: 0,
};

export const MotionContext = createContext<MotionContextValue>({
  basePreference: 'auto',
  effectiveTier: 'full',
  source: 'platform_default',
  osReducedMotion: false,
  saveData: false,
  deviceClass: 'standard',
  platformSettings: DEFAULT_UI_EXPERIENCE_SETTINGS,
  userPreference: 'auto',
  hasUserPreferenceOverride: false,
  telemetrySnapshot: DEFAULT_TELEMETRY_SNAPSHOT,
  setPlatformSettings: () => undefined,
  setUserPreference: () => undefined,
  clearUserPreference: () => undefined,
});
