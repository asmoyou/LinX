import { useEffect, useState } from 'react';
import { Monitor, Smartphone, Tablet, MapPin, Clock, X, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { GlassPanel } from '../GlassPanel';
import { useNotificationStore } from '../../stores/notificationStore';
import { usersApi, type UserSession } from '@/api/users';

export const SessionsSection = () => {
  const { t } = useTranslation();
  const { addNotification } = useNotificationStore();
  const [sessions, setSessions] = useState<UserSession[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [revokingOthers, setRevokingOthers] = useState(false);

  const loadSessions = async () => {
    setIsLoading(true);
    try {
      const data = await usersApi.getSessions();
      setSessions(data.sessions);
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: t('profileSettings.sessions.loadFailedTitle', 'Failed to Load Sessions'),
        message:
          error?.response?.data?.detail ||
          error?.response?.data?.message ||
          t('profileSettings.sessions.loadFailedMessage', 'Unable to load active sessions'),
      });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadSessions();
  }, []);

  const detectDeviceType = (userAgent: string): 'desktop' | 'mobile' | 'tablet' => {
    const ua = userAgent.toLowerCase();
    if (ua.includes('ipad') || ua.includes('tablet')) return 'tablet';
    if (ua.includes('iphone') || ua.includes('android') || ua.includes('mobile')) return 'mobile';
    return 'desktop';
  };

  const getDeviceIcon = (type: 'desktop' | 'mobile' | 'tablet') => {
    switch (type) {
      case 'mobile':
        return Smartphone;
      case 'tablet':
        return Tablet;
      default:
        return Monitor;
    }
  };

  const formatDateTime = (value: string) => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString();
  };

  const handleRevokeSession = async (sessionId: string) => {
    if (!confirm(t('profileSettings.sessions.revokeConfirm', 'Are you sure you want to revoke this session?'))) {
      return;
    }

    setRevokingId(sessionId);
    try {
      await usersApi.revokeSession(sessionId);
      await loadSessions();

      addNotification({
        type: 'success',
        title: t('profileSettings.sessions.revokedTitle', 'Session Revoked'),
        message: t('profileSettings.sessions.revokedMessage', 'The session has been terminated'),
      });
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: t('profileSettings.sessions.revokeFailedTitle', 'Revoke Failed'),
        message: error.response?.data?.message || 'Failed to revoke session',
      });
    } finally {
      setRevokingId(null);
    }
  };

  const handleRevokeAllOthers = async () => {
    if (
      !confirm(
        t(
          'profileSettings.sessions.revokeOthersConfirm',
          'Are you sure you want to revoke all other sessions? You will need to log in again on those devices.'
        )
      )
    ) {
      return;
    }

    setRevokingOthers(true);
    try {
      const result = await usersApi.revokeOtherSessions();
      await loadSessions();

      addNotification({
        type: 'success',
        title: t('profileSettings.sessions.revokedOthersTitle', 'Sessions Revoked'),
        message: t(
          'profileSettings.sessions.revokedOthersMessage',
          'All other sessions have been terminated ({{count}})',
          { count: result.revoked_count }
        ),
      });
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: t('profileSettings.sessions.revokeFailedTitle', 'Revoke Failed'),
        message: error.response?.data?.message || 'Failed to revoke sessions',
      });
    } finally {
      setRevokingOthers(false);
    }
  };

  return (
    <GlassPanel className="p-6">
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Monitor className="w-5 h-5 text-emerald-400" />
            <div>
              <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
                {t('profileSettings.sessions.title', 'Active Sessions')}
              </h2>
              <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-1">
                {t('profileSettings.sessions.subtitle', 'Manage your active sessions across devices')}
              </p>
            </div>
          </div>
          {sessions.filter((s) => !s.is_current).length > 0 && (
            <button
              onClick={handleRevokeAllOthers}
              disabled={revokingOthers}
              className="px-4 py-2 bg-red-500/20 text-red-400 rounded-lg hover:bg-red-500/30 transition-colors disabled:opacity-50 inline-flex items-center gap-2"
            >
              {revokingOthers && <Loader2 className="w-4 h-4 animate-spin" />}
              {t('profileSettings.sessions.revokeOthers', 'Revoke All Others')}
            </button>
          )}
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-10 text-zinc-600 dark:text-zinc-400 gap-2">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span>{t('profileSettings.sessions.loading', 'Loading sessions...')}</span>
          </div>
        ) : (
          <div className="space-y-3">
            {sessions.map((session) => {
              const deviceType = detectDeviceType(session.user_agent || '');
              const DeviceIcon = getDeviceIcon(deviceType);

              return (
                <div
                  key={session.session_id}
                  className={`p-4 rounded-lg border ${
                    session.is_current
                      ? 'bg-emerald-500/10 border-emerald-500/30'
                      : 'bg-zinc-50 dark:bg-white/5 border-zinc-200 dark:border-white/10'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex gap-3">
                      <DeviceIcon className={`w-5 h-5 mt-0.5 ${
                        session.is_current ? 'text-emerald-500 dark:text-emerald-400' : 'text-zinc-500 dark:text-zinc-400'
                      }`} />
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="text-zinc-900 dark:text-zinc-100 font-medium">{session.user_agent || 'Unknown Device'}</h3>
                          {session.is_current && (
                            <span className="px-2 py-0.5 bg-emerald-500/20 text-emerald-400 text-xs rounded-full">
                              {t('profileSettings.sessions.current', 'Current')}
                            </span>
                          )}
                        </div>
                        <div className="flex flex-col gap-1 mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                          <div className="flex items-center gap-2">
                            <MapPin className="w-4 h-4" />
                            <span>{t('profileSettings.sessions.ipAddress', 'IP')}: {session.ip_address || '—'}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <Clock className="w-4 h-4" />
                            <span>
                              {t('profileSettings.sessions.lastActive', 'Last active')}: {formatDateTime(session.last_seen_at)}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                    {!session.is_current && (
                    <button
                      onClick={() => handleRevokeSession(session.session_id)}
                      disabled={revokingId === session.session_id}
                      className="p-2 text-zinc-500 dark:text-zinc-400 hover:text-red-500 dark:hover:text-red-400 transition-colors disabled:opacity-50"
                      title={t('profileSettings.sessions.revokeSession', 'Revoke session')}
                    >
                        {revokingId === session.session_id ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <X className="w-4 h-4" />
                        )}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div className="p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
          <p className="text-sm text-blue-700 dark:text-blue-400">
            <strong>{t('profileSettings.sessions.securityTip', 'Security Tip')}:</strong>{' '}
            {t(
              'profileSettings.sessions.securityTipMessage',
              'If you see any unfamiliar sessions, revoke them immediately and change your password.'
            )}
          </p>
        </div>
      </div>
    </GlassPanel>
  );
};
