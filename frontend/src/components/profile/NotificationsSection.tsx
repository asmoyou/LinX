import { useState } from 'react';
import { Bell, Mail, MessageSquare, CheckCircle } from 'lucide-react';
import { GlassPanel } from '../GlassPanel';
import { useNotificationStore } from '../../stores/notificationStore';

interface NotificationPreferences {
  emailNotifications: boolean;
  taskUpdates: boolean;
  agentStatus: boolean;
  systemAlerts: boolean;
  weeklyDigest: boolean;
  marketingEmails: boolean;
}

export const NotificationsSection = () => {
  const { addNotification } = useNotificationStore();
  const [preferences, setPreferences] = useState<NotificationPreferences>({
    emailNotifications: true,
    taskUpdates: true,
    agentStatus: true,
    systemAlerts: true,
    weeklyDigest: false,
    marketingEmails: false,
  });

  const handleToggle = (key: keyof NotificationPreferences) => {
    setPreferences(prev => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const handleSave = async () => {
    try {
      // TODO: Implement API call
      // await usersApi.updateNotificationPreferences(preferences);
      
      addNotification({
        type: 'success',
        title: 'Preferences Saved',
        message: 'Your notification preferences have been updated',
      });
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: 'Save Failed',
        message: error.response?.data?.message || 'Failed to save preferences',
      });
    }
  };

  const notificationOptions = [
    {
      key: 'emailNotifications' as keyof NotificationPreferences,
      label: 'Email Notifications',
      description: 'Receive notifications via email',
      icon: Mail,
    },
    {
      key: 'taskUpdates' as keyof NotificationPreferences,
      label: 'Task Updates',
      description: 'Get notified when tasks are completed or updated',
      icon: CheckCircle,
    },
    {
      key: 'agentStatus' as keyof NotificationPreferences,
      label: 'Agent Status Changes',
      description: 'Receive alerts when agent status changes',
      icon: Bell,
    },
    {
      key: 'systemAlerts' as keyof NotificationPreferences,
      label: 'System Alerts',
      description: 'Important system notifications and warnings',
      icon: Bell,
    },
    {
      key: 'weeklyDigest' as keyof NotificationPreferences,
      label: 'Weekly Digest',
      description: 'Receive a weekly summary of your activity',
      icon: Mail,
    },
    {
      key: 'marketingEmails' as keyof NotificationPreferences,
      label: 'Marketing Emails',
      description: 'Receive updates about new features and tips',
      icon: MessageSquare,
    },
  ];

  return (
    <GlassPanel className="p-6">
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Bell className="w-5 h-5 text-emerald-400" />
          <div>
            <h2 className="text-xl font-semibold text-white">Notification Preferences</h2>
            <p className="text-sm text-gray-400 mt-1">
              Manage how you receive notifications
            </p>
          </div>
        </div>

        <div className="space-y-4">
          {notificationOptions.map((option) => {
            const Icon = option.icon;
            return (
              <div
                key={option.key}
                className="flex items-center justify-between p-4 bg-white/5 rounded-lg border border-white/10"
              >
                <div className="flex items-start gap-3">
                  <Icon className="w-5 h-5 text-gray-400 mt-0.5" />
                  <div>
                    <h3 className="text-white font-medium">{option.label}</h3>
                    <p className="text-sm text-gray-400 mt-1">{option.description}</p>
                  </div>
                </div>
                <button
                  onClick={() => handleToggle(option.key)}
                  className={`relative w-12 h-6 rounded-full transition-colors ${
                    preferences[option.key] ? 'bg-emerald-500' : 'bg-gray-600'
                  }`}
                >
                  <div
                    className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-transform ${
                      preferences[option.key] ? 'translate-x-7' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>
            );
          })}
        </div>

        <button
          onClick={handleSave}
          className="px-6 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors"
        >
          Save Preferences
        </button>
      </div>
    </GlassPanel>
  );
};
