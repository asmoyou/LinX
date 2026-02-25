import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { User, Settings, Shield, Bell, Download, LogOut, KeyRound, Monitor, ShieldAlert } from 'lucide-react';
import { GlassPanel } from '../components/GlassPanel';
import { ProfileSection } from '../components/profile/ProfileSection';
import { SecuritySection } from '../components/profile/SecuritySection';
import { PreferencesSection } from '../components/profile/PreferencesSection';
import { NotificationsSection } from '../components/profile/NotificationsSection';
import { QuotaSection } from '../components/profile/QuotaSection';
import { APIKeysSection } from '../components/profile/APIKeysSection';
import { SessionsSection } from '../components/profile/SessionsSection';
import { PrivacySection } from '../components/profile/PrivacySection';
import { useAuthStore } from '../stores';
import { useNotificationStore } from '../stores/notificationStore';

type TabType =
  | 'profile'
  | 'security'
  | 'preferences'
  | 'notifications'
  | 'quotas'
  | 'apiKeys'
  | 'sessions'
  | 'privacy';

export const Profile = () => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<TabType>('profile');
  const navigate = useNavigate();
  const { logout } = useAuthStore();
  const { addNotification } = useNotificationStore();

  const handleLogout = () => {
    if (confirm(t('profileSettings.logOutConfirm'))) {
      logout();
      addNotification({
        type: 'success',
        title: t('profileSettings.logOutSuccess'),
        message: t('profileSettings.logOutSuccess'),
      });
      navigate('/login');
    }
  };

  const tabs = [
    { id: 'profile' as TabType, label: t('profileSettings.tabs.profile'), icon: User },
    { id: 'security' as TabType, label: t('profileSettings.tabs.security'), icon: Shield },
    { id: 'preferences' as TabType, label: t('profileSettings.tabs.preferences'), icon: Settings },
    { id: 'notifications' as TabType, label: t('profileSettings.tabs.notifications'), icon: Bell },
    { id: 'quotas' as TabType, label: t('profileSettings.tabs.quotas'), icon: Download },
    { id: 'apiKeys' as TabType, label: t('profileSettings.tabs.apiKeys'), icon: KeyRound },
    { id: 'sessions' as TabType, label: t('profileSettings.tabs.sessions'), icon: Monitor },
    { id: 'privacy' as TabType, label: t('profileSettings.tabs.privacy'), icon: ShieldAlert },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-zinc-900 dark:text-zinc-100 mb-2">
            {t('profileSettings.title')}
          </h1>
          <p className="text-zinc-600 dark:text-zinc-400">{t('profileSettings.subtitle')}</p>
        </div>
        <button
          onClick={handleLogout}
          className="flex items-center gap-2 px-4 py-2 bg-red-500/20 text-red-400 rounded-lg hover:bg-red-500/30 transition-colors border border-red-500/30"
        >
          <LogOut className="w-4 h-4" />
          <span className="font-medium">{t('profileSettings.logOut')}</span>
        </button>
      </div>

      {/* Tabs */}
      <GlassPanel className="p-2">
        <div className="flex flex-wrap gap-2">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all ${
                  activeTab === tab.id
                    ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                    : 'text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 hover:bg-zinc-100 dark:hover:bg-white/5'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span className="text-sm font-medium">{tab.label}</span>
              </button>
            );
          })}
        </div>
      </GlassPanel>

      {/* Content */}
      <div>
        {activeTab === 'profile' && <ProfileSection />}
        {activeTab === 'security' && <SecuritySection />}
        {activeTab === 'preferences' && <PreferencesSection />}
        {activeTab === 'notifications' && <NotificationsSection />}
        {activeTab === 'quotas' && <QuotaSection />}
        {activeTab === 'apiKeys' && <APIKeysSection />}
        {activeTab === 'sessions' && <SessionsSection />}
        {activeTab === 'privacy' && <PrivacySection />}
      </div>
    </div>
  );
};

export default Profile;
