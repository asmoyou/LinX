import { useCallback, useEffect, useMemo, useRef } from 'react';
import { useLocation } from 'react-router-dom';

import { telemetryApi } from '@/api/telemetry';
import { useAuthStore } from '@/stores';
import { usePrivacyStore } from '@/stores/privacyStore';

import { useMotionPolicy } from './useMotionPolicy';
import { buildMotionRouteGroup } from './policyResolver';

const getAppVersion = (): string =>
  String(import.meta.env.VITE_APP_VERSION || import.meta.env.MODE || 'dev');

export const shouldReportMotionTelemetry = ({
  isAuthenticated,
  allowTelemetry,
  isSampled,
  windowCount,
}: {
  isAuthenticated: boolean;
  allowTelemetry: boolean;
  isSampled: boolean;
  windowCount: number;
}): boolean => isAuthenticated && allowTelemetry && isSampled && windowCount >= 1;

export const useMotionTelemetry = (): void => {
  const location = useLocation();
  const { isAuthenticated } = useAuthStore();
  const allowTelemetry = usePrivacyStore((state) => state.allowTelemetry);
  const {
    basePreference,
    effectiveTier,
    osReducedMotion,
    saveData,
    deviceClass,
    platformSettings,
    telemetrySnapshot,
  } = useMotionPolicy();

  const routeGroup = useMemo(() => buildMotionRouteGroup(location.pathname), [location.pathname]);
  const isSampledRef = useRef(false);
  const lastRouteGroupRef = useRef(routeGroup);
  const lastDowngradeCountRef = useRef(0);
  const stateRef = useRef({
    allowTelemetry,
    basePreference,
    deviceClass,
    effectiveTier,
    isAuthenticated,
    osReducedMotion,
    saveData,
    telemetrySnapshot,
  });

  useEffect(() => {
    isSampledRef.current = Math.random() < platformSettings.telemetry_sample_rate;
  }, [platformSettings.telemetry_sample_rate]);

  useEffect(() => {
    stateRef.current = {
      allowTelemetry,
      basePreference,
      deviceClass,
      effectiveTier,
      isAuthenticated,
      osReducedMotion,
      saveData,
      telemetrySnapshot,
    };
  }, [
    allowTelemetry,
    basePreference,
    deviceClass,
    effectiveTier,
    isAuthenticated,
    osReducedMotion,
    saveData,
    telemetrySnapshot,
  ]);

  const flushTelemetry = useCallback((group: string) => {
    const currentState = stateRef.current;
    if (
      !shouldReportMotionTelemetry({
        isAuthenticated: currentState.isAuthenticated,
        allowTelemetry: currentState.allowTelemetry,
        isSampled: isSampledRef.current,
        windowCount: currentState.telemetrySnapshot.windowCount,
      })
    ) {
      return;
    }

    const downgradeDelta = Math.max(
      0,
      currentState.telemetrySnapshot.downgradeCount - lastDowngradeCountRef.current,
    );
    lastDowngradeCountRef.current = currentState.telemetrySnapshot.downgradeCount;

    void telemetryApi.postFrontendMotionSummary({
      route_group: group,
      effective_tier: currentState.effectiveTier,
      motion_preference: currentState.basePreference,
      os_reduced_motion: currentState.osReducedMotion,
      save_data: currentState.saveData,
      device_class: currentState.deviceClass,
      avg_fps: Number(currentState.telemetrySnapshot.avgFps.toFixed(2)),
      p95_frame_ms: Number(currentState.telemetrySnapshot.p95FrameMs.toFixed(2)),
      long_task_count: currentState.telemetrySnapshot.longTaskCount,
      downgrade_count: downgradeDelta,
      sampled_at: currentState.telemetrySnapshot.sampledAt,
      app_version: getAppVersion(),
    });
  }, []);

  useEffect(() => {
    if (lastRouteGroupRef.current !== routeGroup) {
      flushTelemetry(lastRouteGroupRef.current);
      lastRouteGroupRef.current = routeGroup;
    }
  }, [flushTelemetry, routeGroup]);

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        flushTelemetry(routeGroup);
      }
    };

    const handlePageHide = () => {
      flushTelemetry(routeGroup);
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('pagehide', handlePageHide);

    return () => {
      flushTelemetry(routeGroup);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('pagehide', handlePageHide);
    };
  }, [flushTelemetry, routeGroup]);
};
