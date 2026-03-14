/**
 * Central export for all Zustand stores
 * 
 * This file provides a single import point for all application stores.
 * Each store manages a specific domain of the application state.
 */

// Import stores for resetAllStores function
import { useAuthStore } from './authStore';
import { useUserStore } from './userStore';
import { useDepartmentStore } from './departmentStore';
import { useAgentStore } from './agentStore';
import { useTaskStore } from './taskStore';
import { useKnowledgeStore } from './knowledgeStore';
import { useMemoryWorkbenchStore } from './memoryWorkbenchStore';
import { useMissionStore } from './missionStore';
import { useHealthStore } from './healthStore';
import { usePreferencesStore } from './preferencesStore';

// Authentication and user management
export { useAuthStore } from './authStore';
export type { User } from './authStore';

export { useUserStore } from './userStore';
export type { UserProfile, ResourceQuota } from './userStore';

// Department management
export { useDepartmentStore } from './departmentStore';

// Core features
export { useAgentStore } from './agentStore';
export { useTaskStore } from './taskStore';
export { useKnowledgeStore } from './knowledgeStore';
export { useMemoryWorkbenchStore } from './memoryWorkbenchStore';
export { useMissionStore } from './missionStore';
export { useHealthStore } from './healthStore';

// UI and preferences
export { useThemeStore } from './themeStore';
export { usePreferencesStore } from './preferencesStore';
export type { Language, Preferences } from './preferencesStore';

export { useNotificationStore } from './notificationStore';
export type { Notification, NotificationType } from './notificationStore';

/**
 * Store Usage Guide:
 * 
 * 1. Authentication Store (useAuthStore):
 *    - Manages user authentication state
 *    - Persists token and user info to localStorage
 *    - Usage: const { user, token, login, logout } = useAuthStore();
 * 
 * 2. User Store (useUserStore):
 *    - Manages user profile and resource quotas
 *    - Usage: const { profile, quotas } = useUserStore();
 * 
 * 3. Agent Store (useAgentStore):
 *    - Manages agent list and real-time updates
 *    - Supports filtering and search
 *    - Usage: const { agents, updateAgent } = useAgentStore();
 * 
 * 4. Task Store (useTaskStore):
 *    - Manages goals and tasks
 *    - Handles WebSocket updates for real-time sync
 *    - Usage: const { goals, tasks, handleTaskUpdate } = useTaskStore();
 * 
 * 5. Knowledge Store (useKnowledgeStore):
 *    - Manages document uploads and knowledge base
 *    - Tracks upload progress
 *    - Usage: const { documents, uploadQueue } = useKnowledgeStore();
 * 
 * 6. Memory Workbench Store (useMemoryWorkbenchStore):
 *    - Manages user memory and skill proposals
 *    - Supports filtering by product tab, date, tags
 *    - Usage: const { records, activeTab } = useMemoryWorkbenchStore();
 * 
 * 7. Theme Store (useThemeStore):
 *    - Manages light/dark/system theme
 *    - Persists to localStorage
 *    - Usage: const { theme, setTheme } = useThemeStore();
 * 
 * 8. Preferences Store (usePreferencesStore):
 *    - Manages user preferences (language, layout, etc.)
 *    - Persists to localStorage
 *    - Usage: const { language, setLanguage } = usePreferencesStore();
 * 
 * 9. Notification Store (useNotificationStore):
 *    - Manages in-app notifications
 *    - Tracks read/unread status
 *    - Usage: const { notifications, addNotification } = useNotificationStore();
 */

/**
 * Reset all stores (useful for logout)
 */
export const resetAllStores = () => {
  const authStore = useAuthStore.getState();
  const userStore = useUserStore.getState();
  const departmentStore = useDepartmentStore.getState();
  const agentStore = useAgentStore.getState();
  const taskStore = useTaskStore.getState();
  const knowledgeStore = useKnowledgeStore.getState();
  const memoryWorkbenchStore = useMemoryWorkbenchStore.getState();
  const missionStore = useMissionStore.getState();
  const healthStore = useHealthStore.getState();
  const preferencesStore = usePreferencesStore.getState();

  authStore.logout();
  userStore.reset();
  departmentStore.reset();
  agentStore.reset();
  taskStore.reset();
  knowledgeStore.reset();
  memoryWorkbenchStore.reset();
  missionStore.reset();
  healthStore.reset();
  preferencesStore.reset();
  // Note: Theme and notifications are intentionally not reset
};
