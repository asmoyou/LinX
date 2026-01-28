import { create } from 'zustand';

export interface UserProfile {
  id: string;
  username: string;
  email: string;
  role: string;
  displayName?: string;
  attributes?: Record<string, any>;
  createdAt?: string;
  updatedAt?: string;
}

export interface ResourceQuota {
  maxAgents: number;
  maxStorageGb: number;
  maxCpuCores: number;
  maxMemoryGb: number;
  currentAgents: number;
  currentStorageGb: number;
}

interface UserState {
  profile: UserProfile | null;
  quotas: ResourceQuota | null;
  isLoading: boolean;
  error: string | null;
  
  // Actions
  setProfile: (profile: UserProfile) => void;
  setQuotas: (quotas: ResourceQuota) => void;
  updateProfile: (updates: Partial<UserProfile>) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clearError: () => void;
  reset: () => void;
}

export const useUserStore = create<UserState>((set) => ({
  profile: null,
  quotas: null,
  isLoading: false,
  error: null,
  
  setProfile: (profile) => set({ profile: profile ? { ...profile } : null }),
  
  setQuotas: (quotas) => set({ quotas }),
  
  updateProfile: (updates) => set((state) => ({
    profile: state.profile ? { ...state.profile, ...updates } : null,
  })),
  
  setLoading: (loading) => set({ isLoading: loading }),
  
  setError: (error) => set({ error }),
  
  clearError: () => set({ error: null }),
  
  reset: () => set({
    profile: null,
    quotas: null,
    isLoading: false,
    error: null,
  }),
}));
