import type {
  MotionDeviceClass,
  MotionDeviceSignals,
  MotionPreference,
  MotionPreferenceSource,
  MotionTier,
  UiExperienceSettings,
} from './types';

const MOTION_PREFERENCES = new Set<MotionPreference>(['auto', 'full', 'reduced', 'off']);

export const DEFAULT_UI_EXPERIENCE_SETTINGS: UiExperienceSettings = {
  default_motion_preference: 'auto',
  emergency_disable_motion: false,
  telemetry_sample_rate: 0.2,
};

type NavigatorWithConnection = Navigator & {
  connection?: {
    saveData?: boolean;
  };
  deviceMemory?: number;
};

export const normalizeMotionPreference = (
  value: unknown,
  fallback: MotionPreference = 'auto',
): MotionPreference => {
  if (typeof value !== 'string') {
    return fallback;
  }

  const normalized = value.trim().toLowerCase() as MotionPreference;
  return MOTION_PREFERENCES.has(normalized) ? normalized : fallback;
};

export const clampTelemetrySampleRate = (value: unknown, fallback = 0.2): number => {
  const parsed = typeof value === 'number' ? value : Number(value);
  if (Number.isNaN(parsed)) {
    return fallback;
  }

  return Math.min(Math.max(parsed, 0), 1);
};

export const normalizeUiExperienceSettings = (
  value?: Partial<UiExperienceSettings> | null,
): UiExperienceSettings => ({
  default_motion_preference: normalizeMotionPreference(
    value?.default_motion_preference,
    DEFAULT_UI_EXPERIENCE_SETTINGS.default_motion_preference,
  ),
  emergency_disable_motion:
    typeof value?.emergency_disable_motion === 'boolean'
      ? value.emergency_disable_motion
      : DEFAULT_UI_EXPERIENCE_SETTINGS.emergency_disable_motion,
  telemetry_sample_rate: clampTelemetrySampleRate(
    value?.telemetry_sample_rate,
    DEFAULT_UI_EXPERIENCE_SETTINGS.telemetry_sample_rate,
  ),
});

export const resolveMotionDeviceClass = ({
  saveData,
  hardwareConcurrency,
  deviceMemory,
}: Pick<MotionDeviceSignals, 'saveData' | 'hardwareConcurrency' | 'deviceMemory'>): MotionDeviceClass => {
  if (saveData) {
    return 'low';
  }

  if (typeof hardwareConcurrency === 'number' && hardwareConcurrency <= 4) {
    return 'low';
  }

  if (typeof deviceMemory === 'number' && deviceMemory <= 4) {
    return 'low';
  }

  return 'standard';
};

export const detectMotionDeviceSignals = (): MotionDeviceSignals => {
  if (typeof window === 'undefined') {
    return {
      saveData: false,
      hardwareConcurrency: null,
      deviceMemory: null,
      deviceClass: 'standard',
    };
  }

  const navigatorWithConnection = window.navigator as NavigatorWithConnection;
  const saveData = Boolean(navigatorWithConnection.connection?.saveData);
  const hardwareConcurrency =
    typeof window.navigator.hardwareConcurrency === 'number'
      ? window.navigator.hardwareConcurrency
      : null;
  const deviceMemory =
    typeof navigatorWithConnection.deviceMemory === 'number'
      ? navigatorWithConnection.deviceMemory
      : null;

  return {
    saveData,
    hardwareConcurrency,
    deviceMemory,
    deviceClass: resolveMotionDeviceClass({ saveData, hardwareConcurrency, deviceMemory }),
  };
};

export const resolveInitialAutoTier = (signals: MotionDeviceSignals): MotionTier =>
  signals.deviceClass === 'low' ? 'reduced' : 'full';

export const resolveBaseMotionPreference = ({
  platformSettings,
  userPreference,
  hasUserPreferenceOverride,
}: {
  platformSettings: UiExperienceSettings;
  userPreference: MotionPreference;
  hasUserPreferenceOverride: boolean;
}): MotionPreference =>
  hasUserPreferenceOverride
    ? userPreference
    : normalizeMotionPreference(platformSettings.default_motion_preference);

export const resolveEffectiveMotionTier = ({
  basePreference,
  runtimeTier,
  emergencyDisableMotion,
  osReducedMotion,
}: {
  basePreference: MotionPreference;
  runtimeTier: MotionTier;
  emergencyDisableMotion: boolean;
  osReducedMotion: boolean;
}): MotionTier => {
  if (emergencyDisableMotion) {
    return 'off';
  }

  const resolvedTier = basePreference === 'auto' ? runtimeTier : basePreference;

  if (osReducedMotion && resolvedTier === 'full') {
    return 'reduced';
  }

  return resolvedTier;
};

export const resolveMotionPreferenceSource = ({
  emergencyDisableMotion,
  osReducedMotion,
  basePreference,
  effectiveTier,
  hasUserPreferenceOverride,
}: {
  emergencyDisableMotion: boolean;
  osReducedMotion: boolean;
  basePreference: MotionPreference;
  effectiveTier: MotionTier;
  hasUserPreferenceOverride: boolean;
}): MotionPreferenceSource => {
  if (emergencyDisableMotion) {
    return 'emergency_disable_motion';
  }

  if (osReducedMotion && basePreference === 'full' && effectiveTier === 'reduced') {
    return 'system_reduced_motion';
  }

  return hasUserPreferenceOverride ? 'user_preference' : 'platform_default';
};

export const percentile = (values: number[], target: number): number => {
  if (!values.length) {
    return 0;
  }

  const sorted = [...values].sort((left, right) => left - right);
  const index = Math.min(
    sorted.length - 1,
    Math.max(0, Math.ceil((target / 100) * sorted.length) - 1),
  );
  return sorted[index] ?? 0;
};

export const buildMotionRouteGroup = (pathname: string): string => {
  if (!pathname || pathname === '/') {
    return '/dashboard';
  }

  const normalized = pathname.replace(
    /^\/workforce\/([^/]+)\/conversations(?:\/[^/]+)?$/,
    '/workforce/conversations',
  );
  const parts = normalized.split('/').filter(Boolean);

  if (parts.length === 0) {
    return '/dashboard';
  }

  return `/${parts.slice(0, 2).join('/')}`.replace(/\/$/, '');
};

interface MotionRuntimeWindowInput {
  runtimeTier: MotionTier;
  avgFps: number;
  p95FrameMs: number;
  longTaskCountOver80: number;
  longTaskCountOver120: number;
  lowWindowCount: number;
  stableWindowMs: number;
  windowMs?: number;
}

interface MotionRuntimeWindowEvaluation {
  nextTier: MotionTier;
  lowWindowCount: number;
  stableWindowMs: number;
  downgraded: boolean;
  upgraded: boolean;
}

export const evaluateMotionRuntimeWindow = ({
  runtimeTier,
  avgFps,
  p95FrameMs,
  longTaskCountOver80,
  longTaskCountOver120,
  lowWindowCount,
  stableWindowMs,
  windowMs = 10_000,
}: MotionRuntimeWindowInput): MotionRuntimeWindowEvaluation => {
  if (runtimeTier === 'full') {
    const nextLowWindowCount =
      avgFps < 50 || p95FrameMs > 28 || longTaskCountOver80 >= 5 ? lowWindowCount + 1 : 0;

    if (nextLowWindowCount >= 2) {
      return {
        nextTier: 'reduced',
        lowWindowCount: 0,
        stableWindowMs: 0,
        downgraded: true,
        upgraded: false,
      };
    }

    return {
      nextTier: runtimeTier,
      lowWindowCount: nextLowWindowCount,
      stableWindowMs:
        avgFps >= 57 && p95FrameMs < 20 && longTaskCountOver80 === 0
          ? Math.min(stableWindowMs + windowMs, 60_000)
          : 0,
      downgraded: false,
      upgraded: false,
    };
  }

  if (runtimeTier === 'reduced') {
    const nextLowWindowCount =
      avgFps < 35 || p95FrameMs > 45 || longTaskCountOver120 >= 8 ? lowWindowCount + 1 : 0;

    if (nextLowWindowCount >= 2) {
      return {
        nextTier: 'off',
        lowWindowCount: 0,
        stableWindowMs: 0,
        downgraded: true,
        upgraded: false,
      };
    }
  }

  if (avgFps >= 57 && p95FrameMs < 20 && longTaskCountOver80 === 0) {
    const nextStableWindowMs = stableWindowMs + windowMs;
    if (nextStableWindowMs >= 60_000) {
      return {
        nextTier: runtimeTier === 'off' ? 'reduced' : 'full',
        lowWindowCount: 0,
        stableWindowMs: 0,
        downgraded: false,
        upgraded: runtimeTier !== 'full',
      };
    }

    return {
      nextTier: runtimeTier,
      lowWindowCount: 0,
      stableWindowMs: nextStableWindowMs,
      downgraded: false,
      upgraded: false,
    };
  }

  return {
    nextTier: runtimeTier,
    lowWindowCount: 0,
    stableWindowMs: 0,
    downgraded: false,
    upgraded: false,
  };
};
