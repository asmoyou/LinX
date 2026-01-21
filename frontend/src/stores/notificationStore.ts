import { create } from 'zustand';

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

export const useNotificationStore = create<NotificationState>((set, get) => ({
  notifications: [],
  unreadCount: 0,
  isOpen: false,
  
  addNotification: (notification) => {
    const newNotification: Notification = {
      ...notification,
      id: `notif-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      timestamp: new Date().toISOString(),
      read: false,
    };
    
    set((state) => ({
      notifications: [newNotification, ...state.notifications],
      unreadCount: state.unreadCount + 1,
    }));
  },
  
  removeNotification: (id) => set((state) => {
    const notification = state.notifications.find((n) => n.id === id);
    const wasUnread = notification && !notification.read;
    
    return {
      notifications: state.notifications.filter((n) => n.id !== id),
      unreadCount: wasUnread ? state.unreadCount - 1 : state.unreadCount,
    };
  }),
  
  markAsRead: (id) => set((state) => {
    const notification = state.notifications.find((n) => n.id === id);
    const wasUnread = notification && !notification.read;
    
    return {
      notifications: state.notifications.map((n) =>
        n.id === id ? { ...n, read: true } : n
      ),
      unreadCount: wasUnread ? state.unreadCount - 1 : state.unreadCount,
    };
  }),
  
  markAllAsRead: () => set((state) => ({
    notifications: state.notifications.map((n) => ({ ...n, read: true })),
    unreadCount: 0,
  })),
  
  clearAll: () => set({
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
}));
