export type NotificationSeverity = 'info' | 'success' | 'warning' | 'error';

export interface ServerNotification {
  notification_id: string;
  user_id: string;
  mission_id?: string;
  notification_type: string;
  severity: NotificationSeverity;
  title: string;
  message: string;
  action_url?: string;
  action_label?: string;
  notification_metadata?: Record<string, unknown>;
  is_read: boolean;
  read_at?: string;
  created_at: string;
  updated_at?: string;
}

export interface NotificationListResponse {
  items: ServerNotification[];
  total: number;
  unread_count: number;
}
