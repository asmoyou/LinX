import { useAuthStore } from '../stores/authStore';
import { getApiBaseUrl } from '../utils/runtimeUrls';

export type HealthStatus = 'healthy' | 'unhealthy';
export type HealthOverall = 'optimal' | 'degraded' | 'critical';
export type DependencyStatus = 'up' | 'down' | 'disabled';

export interface ComponentCheck {
  name: string;
  healthy: boolean;
  message: string;
}

export interface DependencyHealth {
  id: string;
  name: string;
  required: boolean;
  enabled: boolean;
  healthy: boolean;
  status: DependencyStatus;
  message: string;
  impact: string;
  source: string;
  latency_ms: number | null;
}

export interface HealthSummary {
  required_total: number;
  required_healthy: number;
  required_unhealthy: number;
  optional_total: number;
  optional_healthy: number;
  optional_unhealthy: number;
  disabled_checks: number;
}

export interface SystemHealthResponse {
  status: HealthStatus;
  overall: HealthOverall;
  checks: ComponentCheck[];
  dependencies: DependencyHealth[];
  summary: HealthSummary;
  timestamp: number;
}

const buildHealthUrl = (): string => `${getApiBaseUrl()}/health`;

const buildHeaders = (): HeadersInit => {
  const token = useAuthStore.getState().token;
  return token ? { Authorization: `Bearer ${token}` } : {};
};

export const healthApi = {
  getSystemHealth: async (timeoutMs: number = 8000): Promise<SystemHealthResponse> => {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(buildHealthUrl(), {
        method: 'GET',
        headers: buildHeaders(),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`Health endpoint returned HTTP ${response.status}`);
      }

      return (await response.json()) as SystemHealthResponse;
    } finally {
      window.clearTimeout(timeoutId);
    }
  },
};
