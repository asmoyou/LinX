const PWA_CACHE_PREFIXES = ['workbox-', 'api-cache'];

const shouldDeleteCache = (cacheName: string): boolean =>
  PWA_CACHE_PREFIXES.some((prefix) => cacheName.startsWith(prefix));

export const unregisterLegacyServiceWorkers = async (): Promise<void> => {
  if (typeof window === 'undefined' || !('serviceWorker' in navigator)) {
    return;
  }

  try {
    const registrations = await navigator.serviceWorker.getRegistrations();
    await Promise.all(registrations.map((registration) => registration.unregister()));

    if ('caches' in window) {
      const cacheNames = await window.caches.keys();
      await Promise.all(
        cacheNames
          .filter((cacheName) => shouldDeleteCache(cacheName))
          .map((cacheName) => window.caches.delete(cacheName)),
      );
    }
  } catch (error) {
    console.warn('Failed to clean up legacy service workers', error);
  }
};
