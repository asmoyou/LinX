import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import toast from 'react-hot-toast';
import type { ServerNotification } from '@/types/notification';

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
  source?: 'local' | 'server';
  serverNotificationId?: string;
}

interface NotificationState {
  notifications: Notification[];
  unreadCount: number;
  isOpen: boolean;
  
  // Actions
  addNotification: (notification: Omit<Notification, 'id' | 'timestamp' | 'read'>) => void;
  replaceServerNotifications: (notifications: ServerNotification[]) => void;
  markServerNotificationRead: (notificationId: string) => void;
  removeServerNotification: (notificationId: string) => void;
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

const toServerNotification = (notification: ServerNotification): Notification => ({
  id: `server-${notification.notification_id}`,
  serverNotificationId: notification.notification_id,
  source: 'server',
  type: notification.severity,
  title: notification.title,
  message: notification.message,
  timestamp: notification.created_at || new Date().toISOString(),
  read: notification.is_read,
  actionUrl: notification.action_url,
  actionLabel: notification.action_label,
});

const sortByTimestampDesc = (notifications: Notification[]): Notification[] =>
  notifications
    .slice()
    .sort((left, right) => new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime());

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
          source: notification.source || 'local',
        };

        set((state) => {
          const nextNotifications = sortByTimestampDesc([newNotification, ...state.notifications]).slice(
            0,
            MAX_NOTIFICATIONS
          );
          return {
            notifications: nextNotifications,
            unreadCount: computeUnreadCount(nextNotifications),
          };
        });

        const toastMessage = notification.message?.trim() || notification.title?.trim();
        if (!toastMessage) return;

        if (notification.type === 'success') {
          toast.success(toastMessage);
          return;
        }

        if (notification.type === 'warning') {
          toast(toastMessage, {
            icon: '⚠️',
          });
          return;
        }

        if (notification.type === 'info') {
          toast(toastMessage, {
            icon: 'ℹ️',
          });
        }
      },

      replaceServerNotifications: (serverNotifications) =>
        set((state) => {
          const localNotifications = state.notifications.filter((n) => n.source !== 'server');
          const nextServerNotifications = serverNotifications.map(toServerNotification);
          const nextNotifications = sortByTimestampDesc([
            ...nextServerNotifications,
            ...localNotifications,
          ]).slice(0, MAX_NOTIFICATIONS);
          return {
            notifications: nextNotifications,
            unreadCount: computeUnreadCount(nextNotifications),
          };
        }),

      markServerNotificationRead: (notificationId) =>
        set((state) => {
          const nextNotifications = state.notifications.map((n) =>
            n.serverNotificationId === notificationId ? { ...n, read: true } : n
          );
          return {
            notifications: nextNotifications,
            unreadCount: computeUnreadCount(nextNotifications),
          };
        }),

      removeServerNotification: (notificationId) =>
        set((state) => {
          const nextNotifications = state.notifications.filter(
            (n) => n.serverNotificationId !== notificationId
          );
          return {
            notifications: nextNotifications,
            unreadCount: computeUnreadCount(nextNotifications),
          };
        }),

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
