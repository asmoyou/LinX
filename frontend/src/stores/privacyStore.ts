import { create } from 'zustand';

interface PrivacyState {
  allowTelemetry: boolean;
  setAllowTelemetry: (allowTelemetry: boolean) => void;
  reset: () => void;
}

export const usePrivacyStore = create<PrivacyState>()((set) => ({
  allowTelemetry: true,
  setAllowTelemetry: (allowTelemetry) => set({ allowTelemetry }),
  reset: () => set({ allowTelemetry: true }),
}));
