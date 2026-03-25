export { MotionProvider } from './MotionProvider';
export { useMotionPolicy } from './useMotionPolicy';
export { PageTransition } from './routeAnimations';
export { getModalMotionPreset, getPageTransitionProps } from './presets';
export {
  DEFAULT_UI_EXPERIENCE_SETTINGS,
  buildMotionRouteGroup,
  clampTelemetrySampleRate,
  detectMotionDeviceSignals,
  evaluateMotionRuntimeWindow,
  normalizeMotionPreference,
  normalizeUiExperienceSettings,
  percentile,
  resolveBaseMotionPreference,
  resolveEffectiveMotionTier,
  resolveInitialAutoTier,
  resolveMotionDeviceClass,
  resolveMotionPreferenceSource,
} from './policyResolver';
export { shouldReportMotionTelemetry } from './useMotionTelemetry';
export { useMotionTelemetry } from './useMotionTelemetry';
export type {
  MotionDeviceClass,
  MotionDeviceSignals,
  MotionPreference,
  MotionPreferenceSource,
  MotionTelemetrySnapshot,
  MotionTier,
  UiExperienceSettings,
} from './types';
