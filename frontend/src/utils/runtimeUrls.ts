const DEFAULT_API_BASE_PATH = '/api/v1';

const trimTrailingSlash = (value: string): string => value.replace(/\/+$/, '');

const isHttpUrl = (value: string): boolean => /^https?:\/\//i.test(value);

const isWebSocketUrl = (value: string): boolean => /^wss?:\/\//i.test(value);

const ensureLeadingSlash = (value: string): string =>
  value.startsWith('/') ? value : `/${value}`;

export const getApiBaseUrl = (): string => {
  const raw = (import.meta.env.VITE_API_URL as string | undefined)?.trim() || '';
  if (!raw) {
    return DEFAULT_API_BASE_PATH;
  }

  const cleaned = trimTrailingSlash(raw);
  if (isHttpUrl(cleaned)) {
    return cleaned.endsWith(DEFAULT_API_BASE_PATH)
      ? cleaned
      : `${cleaned}${DEFAULT_API_BASE_PATH}`;
  }

  const normalizedPath = ensureLeadingSlash(cleaned);
  return normalizedPath.endsWith(DEFAULT_API_BASE_PATH)
    ? normalizedPath
    : `${normalizedPath}${DEFAULT_API_BASE_PATH}`;
};

export const getWebSocketBaseUrl = (): string => {
  const rawWsUrl = (import.meta.env.VITE_WS_URL as string | undefined)?.trim() || '';
  if (rawWsUrl) {
    const cleaned = trimTrailingSlash(rawWsUrl);
    if (isWebSocketUrl(cleaned)) {
      return cleaned;
    }
    if (isHttpUrl(cleaned)) {
      return cleaned.replace(/^http/i, 'ws');
    }

    return `${window.location.origin.replace(/^http/i, 'ws')}${ensureLeadingSlash(cleaned)}`;
  }

  const apiBaseUrl = getApiBaseUrl();
  if (isHttpUrl(apiBaseUrl)) {
    return `${apiBaseUrl.replace(/^http/i, 'ws')}/ws`;
  }

  return `${window.location.origin.replace(/^http/i, 'ws')}${apiBaseUrl}/ws`;
};

export const buildWebSocketUrl = (path: string): string => {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${getWebSocketBaseUrl()}${normalizedPath}`;
};
