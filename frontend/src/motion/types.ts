export type MotionPreference = 'auto' | 'full' | 'reduced' | 'off';
export type MotionTier = MotionPreference;
export type MotionDeviceClass = 'low' | 'standard';
export type MotionPreferenceSource =
  | 'platform_default'
  | 'user_preference'
  | 'system_reduced_motion'
  | 'emergency_disable_motion';

export interface UiExperienceSettings {
  default_motion_preference: MotionPreference;
  emergency_disable_motion: boolean;
  telemetry_sample_rate: number;
}

export interface MotionDeviceSignals {
  saveData: boolean;
  hardwareConcurrency: number | null;
  deviceMemory: number | null;
  deviceClass: MotionDeviceClass;
}

export interface MotionTelemetrySnapshot {
  avgFps: number;
  p95FrameMs: number;
  longTaskCount: number;
  downgradeCount: number;
  sampledAt: string;
  windowCount: number;
}
