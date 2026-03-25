import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PropsWithChildren,
} from 'react';
import { MotionConfig } from 'framer-motion';

import {
  detectMotionDeviceSignals,
  evaluateMotionRuntimeWindow,
  normalizeUiExperienceSettings,
  percentile,
  resolveBaseMotionPreference,
  resolveEffectiveMotionTier,
  resolveInitialAutoTier,
  resolveMotionPreferenceSource,
} from './policyResolver';
import { MotionContext } from './context';
import type {
  MotionPreference,
  MotionTier,
  UiExperienceSettings,
} from './types';

export const MotionProvider = ({
  children,
  platformSettings,
}: PropsWithChildren<{ platformSettings?: Partial<UiExperienceSettings> | null }>) => {
  const [resolvedPlatformSettings, setResolvedPlatformSettings] = useState<UiExperienceSettings>(
    normalizeUiExperienceSettings(platformSettings),
  );
  const [userPreference, setUserPreferenceState] = useState<MotionPreference>('auto');
  const [hasUserPreferenceOverride, setHasUserPreferenceOverride] = useState(false);
  const [osReducedMotion, setOsReducedMotion] = useState(false);
  const [deviceSignals, setDeviceSignals] = useState(() => detectMotionDeviceSignals());
  const [runtimeTier, setRuntimeTier] = useState<MotionTier>(resolveInitialAutoTier(deviceSignals));
  const [telemetrySnapshot, setTelemetrySnapshot] = useState({
    avgFps: 60,
    p95FrameMs: 16,
    longTaskCount: 0,
    downgradeCount: 0,
    sampledAt: new Date(0).toISOString(),
    windowCount: 0,
  });

  const lowWindowCountRef = useRef(0);
  const stableWindowMsRef = useRef(0);

  useEffect(() => {
    setResolvedPlatformSettings(normalizeUiExperienceSettings(platformSettings));
  }, [platformSettings]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return undefined;
    }

    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const applyReducedMotion = () => setOsReducedMotion(mediaQuery.matches);

    applyReducedMotion();
    mediaQuery.addEventListener('change', applyReducedMotion);

    return () => mediaQuery.removeEventListener('change', applyReducedMotion);
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return undefined;
    }

    const updateDeviceSignals = () => setDeviceSignals(detectMotionDeviceSignals());

    updateDeviceSignals();
    window.addEventListener('resize', updateDeviceSignals);
    window.addEventListener('online', updateDeviceSignals);
    window.addEventListener('offline', updateDeviceSignals);

    return () => {
      window.removeEventListener('resize', updateDeviceSignals);
      window.removeEventListener('online', updateDeviceSignals);
      window.removeEventListener('offline', updateDeviceSignals);
    };
  }, []);

  const basePreference = useMemo(
    () =>
      resolveBaseMotionPreference({
        platformSettings: resolvedPlatformSettings,
        userPreference,
        hasUserPreferenceOverride,
      }),
    [hasUserPreferenceOverride, resolvedPlatformSettings, userPreference],
  );

  useEffect(() => {
    setRuntimeTier(resolveInitialAutoTier(deviceSignals));
    lowWindowCountRef.current = 0;
    stableWindowMsRef.current = 0;
  }, [
    basePreference,
    deviceSignals.deviceClass,
    deviceSignals.deviceMemory,
    deviceSignals.hardwareConcurrency,
    deviceSignals.saveData,
  ]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return undefined;
    }

    if (basePreference !== 'auto' || resolvedPlatformSettings.emergency_disable_motion) {
      return undefined;
    }

    let animationFrameId = 0;
    let observer: PerformanceObserver | null = null;
    let lastFrameTs = 0;
    let windowStart = window.performance.now();
    let warmupUntil = windowStart + 3000;
    let frameDurations: number[] = [];
    const longTasks: Array<{ ts: number; duration: number }> = [];

    const resetWindow = () => {
      frameDurations = [];
      lastFrameTs = 0;
      windowStart = window.performance.now();
      warmupUntil = windowStart + 3000;
    };

    const pruneLongTasks = (now: number) => {
      while (longTasks.length > 0 && now - longTasks[0].ts > 30000) {
        longTasks.shift();
      }
    };

    const handleDowngrade = (nextTier: MotionTier) => {
      setRuntimeTier((currentTier) => {
        if (currentTier === nextTier) {
          return currentTier;
        }
        return nextTier;
      });
      setTelemetrySnapshot((currentSnapshot) => ({
        ...currentSnapshot,
        downgradeCount: currentSnapshot.downgradeCount + 1,
        sampledAt: new Date().toISOString(),
      }));
      lowWindowCountRef.current = 0;
      stableWindowMsRef.current = 0;
      resetWindow();
    };

    const evaluateWindow = (now: number) => {
      if (now < warmupUntil || now - windowStart < 10000 || frameDurations.length < 10) {
        return;
      }

      pruneLongTasks(now);

      const avgFrameMs =
        frameDurations.reduce((accumulator, value) => accumulator + value, 0) /
        frameDurations.length;
      const avgFps = avgFrameMs > 0 ? 1000 / avgFrameMs : 60;
      const p95FrameMs = percentile(frameDurations, 95);
      const longTaskCountOver80 = longTasks.filter((entry) => entry.duration > 80).length;
      const longTaskCountOver120 = longTasks.filter((entry) => entry.duration > 120).length;

      setTelemetrySnapshot((currentSnapshot) => ({
        ...currentSnapshot,
        avgFps,
        p95FrameMs,
        longTaskCount: longTaskCountOver80,
        sampledAt: new Date().toISOString(),
        windowCount: currentSnapshot.windowCount + 1,
      }));

      const evaluation = evaluateMotionRuntimeWindow({
        runtimeTier,
        avgFps,
        p95FrameMs,
        longTaskCountOver80,
        longTaskCountOver120,
        lowWindowCount: lowWindowCountRef.current,
        stableWindowMs: stableWindowMsRef.current,
      });

      lowWindowCountRef.current = evaluation.lowWindowCount;
      stableWindowMsRef.current = evaluation.stableWindowMs;

      if (evaluation.downgraded) {
        handleDowngrade(evaluation.nextTier);
        return;
      }

      if (evaluation.upgraded) {
        setRuntimeTier(evaluation.nextTier);
        stableWindowMsRef.current = 0;
        lowWindowCountRef.current = 0;
        resetWindow();
        return;
      }

      frameDurations = [];
      windowStart = now;
    };

    const loop = (timestamp: number) => {
      if (document.visibilityState !== 'visible') {
        return;
      }

      if (lastFrameTs > 0) {
        frameDurations.push(timestamp - lastFrameTs);
        if (frameDurations.length > 6000) {
          frameDurations.shift();
        }
      }

      lastFrameTs = timestamp;
      evaluateWindow(timestamp);
      animationFrameId = window.requestAnimationFrame(loop);
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        window.cancelAnimationFrame(animationFrameId);
        resetWindow();
        animationFrameId = window.requestAnimationFrame(loop);
        return;
      }

      window.cancelAnimationFrame(animationFrameId);
    };

    if (
      'PerformanceObserver' in window &&
      Array.isArray(PerformanceObserver.supportedEntryTypes) &&
      PerformanceObserver.supportedEntryTypes.includes('longtask')
    ) {
      observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          longTasks.push({
            ts: entry.startTime,
            duration: entry.duration,
          });
        }
      });
      observer.observe({ entryTypes: ['longtask'] });
    }

    document.addEventListener('visibilitychange', handleVisibilityChange);
    animationFrameId = window.requestAnimationFrame(loop);

    return () => {
      window.cancelAnimationFrame(animationFrameId);
      observer?.disconnect();
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [basePreference, resolvedPlatformSettings.emergency_disable_motion, runtimeTier]);

  const effectiveTier = useMemo(
    () =>
      resolveEffectiveMotionTier({
        basePreference,
        runtimeTier,
        emergencyDisableMotion: resolvedPlatformSettings.emergency_disable_motion,
        osReducedMotion,
      }),
    [basePreference, osReducedMotion, resolvedPlatformSettings.emergency_disable_motion, runtimeTier],
  );

  const source = useMemo(
    () =>
      resolveMotionPreferenceSource({
        emergencyDisableMotion: resolvedPlatformSettings.emergency_disable_motion,
        osReducedMotion,
        basePreference,
        effectiveTier,
        hasUserPreferenceOverride,
      }),
    [
      basePreference,
      effectiveTier,
      hasUserPreferenceOverride,
      osReducedMotion,
      resolvedPlatformSettings.emergency_disable_motion,
    ],
  );

  useEffect(() => {
    if (typeof document === 'undefined') {
      return undefined;
    }

    const root = document.documentElement;
    root.dataset.motionTier = effectiveTier;
    root.dataset.motionSource = source;

    return () => {
      delete root.dataset.motionTier;
      delete root.dataset.motionSource;
    };
  }, [effectiveTier, source]);

  const setPlatformSettings = useCallback((settings: Partial<UiExperienceSettings>) => {
    setResolvedPlatformSettings((currentSettings) =>
      normalizeUiExperienceSettings({
        ...currentSettings,
        ...settings,
      }),
    );
  }, []);

  const setUserPreference = useCallback(
    (preference: MotionPreference, hasOverride = true) => {
      setUserPreferenceState(preference);
      setHasUserPreferenceOverride(hasOverride);
    },
    [],
  );

  const clearUserPreference = useCallback(() => {
    setUserPreferenceState('auto');
    setHasUserPreferenceOverride(false);
  }, []);

  const value = useMemo<MotionContextValue>(
    () => ({
      basePreference,
      effectiveTier,
      source,
      osReducedMotion,
      saveData: deviceSignals.saveData,
      deviceClass: deviceSignals.deviceClass,
      platformSettings: resolvedPlatformSettings,
      userPreference,
      hasUserPreferenceOverride,
      telemetrySnapshot,
      setPlatformSettings,
      setUserPreference,
      clearUserPreference,
    }),
    [
      basePreference,
      clearUserPreference,
      deviceSignals.deviceClass,
      deviceSignals.saveData,
      effectiveTier,
      hasUserPreferenceOverride,
      osReducedMotion,
      resolvedPlatformSettings,
      setPlatformSettings,
      setUserPreference,
      source,
      telemetrySnapshot,
      userPreference,
    ],
  );

  return (
    <MotionContext.Provider value={value}>
      <MotionConfig reducedMotion={effectiveTier === 'full' ? 'never' : 'always'}>
        {children}
      </MotionConfig>
    </MotionContext.Provider>
  );
};
