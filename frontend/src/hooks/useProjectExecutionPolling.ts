import { useEffect, useRef } from 'react';

const PROJECT_EXECUTION_POLL_INTERVAL_MS = 5_000;

export const useProjectExecutionPolling = (
  enabled: boolean,
  callback: () => void | Promise<void>,
  intervalMs = PROJECT_EXECUTION_POLL_INTERVAL_MS,
): void => {
  const callbackRef = useRef(callback);

  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      if (document.visibilityState !== 'visible') {
        return;
      }
      void callbackRef.current();
    }, intervalMs);

    return () => {
      window.clearInterval(timer);
    };
  }, [enabled, intervalMs]);
};

