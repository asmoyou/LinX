import { useState } from 'react';
import { Monitor, Smartphone, Tablet, MapPin, Clock, X } from 'lucide-react';
import { GlassPanel } from '../GlassPanel';
import { useNotificationStore } from '../../stores/notificationStore';

interface Session {
  id: string;
  device: string;
  deviceType: 'desktop' | 'mobile' | 'tablet';
  location: string;
  ipAddress: string;
  lastActive: string;
  isCurrent: boolean;
}

export const SessionsSection = () => {
  const { addNotification } = useNotificationStore();
  const [sessions, setSessions] = useState<Session[]>([
    {
      id: '1',
      device: 'Chrome on macOS',
      deviceType: 'desktop',
      location: 'San Francisco, CA',
      ipAddress: '192.168.1.1',
      lastActive: '2024-01-20 14:30',
      isCurrent: true,
    },
    {
      id: '2',
      device: 'Safari on iPhone',
      deviceType: 'mobile',
      location: 'San Francisco, CA',
      ipAddress: '192.168.1.2',
      lastActive: '2024-01-19 10:15',
      isCurrent: false,
    },
  ]);

  const getDeviceIcon = (type: string) => {
    switch (type) {
      case 'mobile':
        return Smartphone;
      case 'tablet':
        return Tablet;
      default:
        return Monitor;
    }
  };

  const handleRevokeSession = async (id: string) => {
    if (!confirm('Are you sure you want to revoke this session?')) {
      return;
    }

    try {
      // TODO: Implement API call
      setSessions(sessions.filter(s => s.id !== id));
      
      addNotification({
        type: 'success',
        title: 'Session Revoked',
        message: 'The session has been terminated',
      });
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: 'Revoke Failed',
        message: error.response?.data?.message || 'Failed to revoke session',
      });
    }
  };

  const handleRevokeAllOthers = async () => {
    if (!confirm('Are you sure you want to revoke all other sessions? You will need to log in again on those devices.')) {
      return;
    }

    try {
      // TODO: Implement API call
      setSessions(sessions.filter(s => s.isCurrent));
      
      addNotification({
        type: 'success',
        title: 'Sessions Revoked',
        message: 'All other sessions have been terminated',
      });
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: 'Revoke Failed',
        message: error.response?.data?.message || 'Failed to revoke sessions',
      });
    }
  };

  return (
    <GlassPanel className="p-6">
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Monitor className="w-5 h-5 text-emerald-400" />
            <div>
              <h2 className="text-xl font-semibold text-white">Active Sessions</h2>
              <p className="text-sm text-gray-400 mt-1">
                Manage your active sessions across devices
              </p>
            </div>
          </div>
          {sessions.filter(s => !s.isCurrent).length > 0 && (
            <button
              onClick={handleRevokeAllOthers}
              className="px-4 py-2 bg-red-500/20 text-red-400 rounded-lg hover:bg-red-500/30 transition-colors"
            >
              Revoke All Others
            </button>
          )}
        </div>

        <div className="space-y-3">
          {sessions.map((session) => {
            const DeviceIcon = getDeviceIcon(session.deviceType);
            
            return (
              <div
                key={session.id}
                className={`p-4 rounded-lg border ${
                  session.isCurrent
                    ? 'bg-emerald-500/10 border-emerald-500/30'
                    : 'bg-white/5 border-white/10'
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex gap-3">
                    <DeviceIcon className={`w-5 h-5 mt-0.5 ${
                      session.isCurrent ? 'text-emerald-400' : 'text-gray-400'
                    }`} />
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-white font-medium">{session.device}</h3>
                        {session.isCurrent && (
                          <span className="px-2 py-0.5 bg-emerald-500/20 text-emerald-400 text-xs rounded-full">
                            Current
                          </span>
                        )}
                      </div>
                      <div className="flex flex-col gap-1 mt-2 text-sm text-gray-400">
                        <div className="flex items-center gap-2">
                          <MapPin className="w-4 h-4" />
                          <span>{session.location}</span>
                          <span className="text-gray-600">•</span>
                          <span>{session.ipAddress}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <Clock className="w-4 h-4" />
                          <span>Last active: {session.lastActive}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                  {!session.isCurrent && (
                    <button
                      onClick={() => handleRevokeSession(session.id)}
                      className="p-2 text-gray-400 hover:text-red-400 transition-colors"
                      title="Revoke session"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <div className="p-4 bg-blue-500/10 border border-blue-500/30 rounded-lg">
          <p className="text-sm text-blue-400">
            <strong>Security Tip:</strong> If you see any unfamiliar sessions, revoke them immediately and change your password.
          </p>
        </div>
      </div>
    </GlassPanel>
  );
};
