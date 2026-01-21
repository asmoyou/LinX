import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type Language = 'en' | 'zh';

export interface Preferences {
  language: Language;
  sidebarCollapsed: boolean;
  dashboardLayout: 'default' | 'compact' | 'detailed';
  notificationsEnabled: boolean;
  soundEnabled: boolean;
  autoRefresh: boolean;
  refreshInterval: number; // in seconds
}

interface PreferencesState extends Preferences {
  // Actions
  setLanguage: (language: Language) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebar: () => void;
  setDashboardLayout: (layout: Preferences['dashboardLayout']) => void;
  setNotificationsEnabled: (enabled: boolean) => void;
  setSoundEnabled: (enabled: boolean) => void;
  setAutoRefresh: (enabled: boolean) => void;
  setRefreshInterval: (interval: number) => void;
  updatePreferences: (preferences: Partial<Preferences>) => void;
  reset: () => void;
}

const defaultPreferences: Preferences = {
  language: 'en',
  sidebarCollapsed: false,
  dashboardLayout: 'default',
  notificationsEnabled: true,
  soundEnabled: false,
  autoRefresh: true,
  refreshInterval: 30,
};

export const usePreferencesStore = create<PreferencesState>()(
  persist(
    (set) => ({
      ...defaultPreferences,
      
      setLanguage: (language) => set({ language }),
      
      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
      
      toggleSidebar: () => set((state) => ({ 
        sidebarCollapsed: !state.sidebarCollapsed 
      })),
      
      setDashboardLayout: (layout) => set({ dashboardLayout: layout }),
      
      setNotificationsEnabled: (enabled) => set({ notificationsEnabled: enabled }),
      
      setSoundEnabled: (enabled) => set({ soundEnabled: enabled }),
      
      setAutoRefresh: (enabled) => set({ autoRefresh: enabled }),
      
      setRefreshInterval: (interval) => set({ refreshInterval: interval }),
      
      updatePreferences: (preferences) => set((state) => ({
        ...state,
        ...preferences,
      })),
      
      reset: () => set(defaultPreferences),
    }),
    {
      name: 'preferences-storage',
    }
  )
);
