import { create } from 'zustand';
import { healthApi, type SystemHealthResponse } from '@/api/health';

interface FetchHealthOptions {
  force?: boolean;
  showLoading?: boolean;
}

interface HealthState {
  systemHealth: SystemHealthResponse | null;
  healthLoading: boolean;
  healthError: string | null;
  lastFetchedAt: number;
  fetchSystemHealth: (options?: FetchHealthOptions) => Promise<SystemHealthResponse | null>;
  invalidateHealth: () => void;
  reset: () => void;
}

const HEALTH_CACHE_TTL_MS = 60_000;
const HEALTH_FETCH_ERROR_TEXT = 'Failed to fetch system health';

const initialState = {
  systemHealth: null,
  healthLoading: true,
  healthError: null,
  lastFetchedAt: 0,
};

let inFlightRequest: Promise<SystemHealthResponse> | null = null;

const isFresh = (state: Pick<HealthState, 'systemHealth' | 'lastFetchedAt'>): boolean =>
  Boolean(state.systemHealth) && Date.now() - state.lastFetchedAt < HEALTH_CACHE_TTL_MS;

export const useHealthStore = create<HealthState>((set, get) => ({
  ...initialState,

  fetchSystemHealth: async ({ force = false, showLoading = false }: FetchHealthOptions = {}) => {
    const currentState = get();

    if (!force && isFresh(currentState)) {
      if (currentState.healthLoading || currentState.healthError) {
        set({
          healthLoading: false,
          healthError: null,
        });
      }
      return currentState.systemHealth;
    }

    if (showLoading && !currentState.systemHealth) {
      set({ healthLoading: true });
    }

    if (!force && inFlightRequest) {
      try {
        const response = await inFlightRequest;
        set({ healthLoading: false });
        return response;
      } catch (error) {
        const message = error instanceof Error ? error.message : HEALTH_FETCH_ERROR_TEXT;
        set({
          healthError: message,
          healthLoading: false,
        });
        return null;
      }
    }

    const request = healthApi.getSystemHealth();
    inFlightRequest = request;

    try {
      const response = await request;
      set({
        systemHealth: response,
        healthLoading: false,
        healthError: null,
        lastFetchedAt: Date.now(),
      });
      return response;
    } catch (error) {
      const message = error instanceof Error ? error.message : HEALTH_FETCH_ERROR_TEXT;
      set({
        healthError: message,
        healthLoading: false,
      });
      return null;
    } finally {
      if (inFlightRequest === request) {
        inFlightRequest = null;
      }
    }
  },

  invalidateHealth: () => {
    set({ lastFetchedAt: 0 });
  },

  reset: () => {
    inFlightRequest = null;
    set(initialState);
  },
}));
