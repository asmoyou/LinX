import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { User, Settings, Shield, Bell, Key, Monitor, Globe, Download, LogOut } from 'lucide-react';
import { GlassPanel } from '../components/GlassPanel';
import { ProfileSection } from '../components/profile/ProfileSection';
import { SecuritySection } from '../components/profile/SecuritySection';
import { PreferencesSection } from '../components/profile/PreferencesSection';
import { NotificationsSection } from '../components/profile/NotificationsSection';
import { APIKeysSection } from '../components/profile/APIKeysSection';
import { SessionsSection } from '../components/profile/SessionsSection';
import { PrivacySection } from '../components/profile/PrivacySection';
import { QuotaSection } from '../components/profile/QuotaSection';
import { useAuthStore } from '../stores';
import { useNotificationStore } from '../stores/notificationStore';

type TabType = 'profile' | 'security' | 'preferences' | 'notifications' | 'api-keys' | 'sessions' | 'privacy' | 'quotas';

export const Profile = () => {
  const [activeTab, setActiveTab] = useState<TabType>('profile');
  const navigate = useNavigate();
  const { logout } = useAuthStore();
  const { addNotification } = useNotificationStore();

  const handleLogout = () => {
    if (confirm('Are you sure you want to log out?')) {
      logout();
      addNotification({
        type: 'success',
        title: 'Logged Out',
        message: 'You have been logged out successfully',
      });
      navigate('/login');
    }
  };

  const tabs = [
    { id: 'profile' as TabType, label: 'Profile', icon: User },
    { id: 'security' as TabType, label: 'Security', icon: Shield },
    { id: 'preferences' as TabType, label: 'Preferences', icon: Settings },
    { id: 'notifications' as TabType, label: 'Notifications', icon: Bell },
    { id: 'api-keys' as TabType, label: 'API Keys', icon: Key },
    { id: 'sessions' as TabType, label: 'Sessions', icon: Monitor },
    { id: 'privacy' as TabType, label: 'Privacy', icon: Globe },
    { id: 'quotas' as TabType, label: 'Resource Quotas', icon: Download },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2">Settings</h1>
          <p className="text-gray-400">Manage your account settings and preferences</p>
        </div>
        <button
          onClick={handleLogout}
          className="flex items-center gap-2 px-4 py-2 bg-red-500/20 text-red-400 rounded-lg hover:bg-red-500/30 transition-colors border border-red-500/30"
        >
          <LogOut className="w-4 h-4" />
          <span className="font-medium">Log Out</span>
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
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
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
        {activeTab === 'api-keys' && <APIKeysSection />}
        {activeTab === 'sessions' && <SessionsSection />}
        {activeTab === 'privacy' && <PrivacySection />}
        {activeTab === 'quotas' && <QuotaSection />}
      </div>
    </div>
  );
};

export default Profile;
