import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

export type NotificationType = 'info' | 'success' | 'warning' | 'error';

export interface Notification {
  id: string;
  type: NotificationType;
  title: string;
  message: string;
  timestamp: string;
  read: boolean;
  actionUrl?: string;
  actionLabel?: string;
}

interface NotificationState {
  notifications: Notification[];
  unreadCount: number;
  isOpen: boolean;
  
  // Actions
  addNotification: (notification: Omit<Notification, 'id' | 'timestamp' | 'read'>) => void;
  removeNotification: (id: string) => void;
  markAsRead: (id: string) => void;
  markAllAsRead: () => void;
  clearAll: () => void;
  togglePanel: () => void;
  setOpen: (open: boolean) => void;
  
  // Computed
  getUnreadNotifications: () => Notification[];
  getNotificationById: (id: string) => Notification | undefined;
}

const MAX_NOTIFICATIONS = 200;

const computeUnreadCount = (notifications: Notification[]): number =>
  notifications.reduce((count, notification) => count + (notification.read ? 0 : 1), 0);

export const useNotificationStore = create<NotificationState>()(
  persist(
    (set, get) => ({
      notifications: [],
      unreadCount: 0,
      isOpen: false,

      addNotification: (notification) => {
        const newNotification: Notification = {
          ...notification,
          id: `notif-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`,
          timestamp: new Date().toISOString(),
          read: false,
        };

        set((state) => {
          const nextNotifications = [newNotification, ...state.notifications].slice(
            0,
            MAX_NOTIFICATIONS
          );
          return {
            notifications: nextNotifications,
            unreadCount: computeUnreadCount(nextNotifications),
          };
        });
      },

      removeNotification: (id) =>
        set((state) => {
          const nextNotifications = state.notifications.filter((n) => n.id !== id);
          return {
            notifications: nextNotifications,
            unreadCount: computeUnreadCount(nextNotifications),
          };
        }),

      markAsRead: (id) =>
        set((state) => {
          const nextNotifications = state.notifications.map((n) =>
            n.id === id ? { ...n, read: true } : n
          );
          return {
            notifications: nextNotifications,
            unreadCount: computeUnreadCount(nextNotifications),
          };
        }),

      markAllAsRead: () =>
        set((state) => ({
          notifications: state.notifications.map((n) => ({ ...n, read: true })),
          unreadCount: 0,
        })),

      clearAll: () =>
        set({
          notifications: [],
          unreadCount: 0,
        }),

      togglePanel: () => set((state) => ({ isOpen: !state.isOpen })),

      setOpen: (open) => set({ isOpen: open }),

      getUnreadNotifications: () => {
        return get().notifications.filter((n) => !n.read);
      },

      getNotificationById: (id) => {
        return get().notifications.find((n) => n.id === id);
      },
    }),
    {
      name: 'linx-notification-store',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        notifications: state.notifications,
        unreadCount: state.unreadCount,
      }),
    }
  )
);
