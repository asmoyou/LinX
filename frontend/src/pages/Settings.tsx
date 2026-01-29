import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Settings as SettingsIcon, Cpu, User, Shield, Bell, Palette, Key } from 'lucide-react';
import { LLMSettings } from '../components/settings/LLMSettings';
import { EnvVarsSettings } from '../components/settings/EnvVarsSettings';

type SettingsTab = 'llm' | 'envVars' | 'profile' | 'security' | 'notifications' | 'appearance';

interface TabConfig {
  id: SettingsTab;
  label: string;
  icon: React.ReactNode;
  component: React.ReactNode;
}

export const Settings: React.FC = () => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<SettingsTab>('llm');

  const tabs: TabConfig[] = [
    {
      id: 'llm',
      label: t('settings.tabs.llm', 'LLM Providers'),
      icon: <Cpu className="w-5 h-5" />,
      component: <LLMSettings />,
    },
    {
      id: 'envVars',
      label: t('settings.tabs.envVars', 'Environment Variables'),
      icon: <Key className="w-5 h-5" />,
      component: <EnvVarsSettings />,
    },
    {
      id: 'profile',
      label: t('settings.tabs.profile', 'Profile'),
      icon: <User className="w-5 h-5" />,
      component: (
        <div className="p-8 text-center text-zinc-500">
          {t('settings.comingSoon', 'Coming soon...')}
        </div>
      ),
    },
    {
      id: 'security',
      label: t('settings.tabs.security', 'Security'),
      icon: <Shield className="w-5 h-5" />,
      component: (
        <div className="p-8 text-center text-zinc-500">
          {t('settings.comingSoon', 'Coming soon...')}
        </div>
      ),
    },
    {
      id: 'notifications',
      label: t('settings.tabs.notifications', 'Notifications'),
      icon: <Bell className="w-5 h-5" />,
      component: (
        <div className="p-8 text-center text-zinc-500">
          {t('settings.comingSoon', 'Coming soon...')}
        </div>
      ),
    },
    {
      id: 'appearance',
      label: t('settings.tabs.appearance', 'Appearance'),
      icon: <Palette className="w-5 h-5" />,
      component: (
        <div className="p-8 text-center text-zinc-500">
          {t('settings.comingSoon', 'Coming soon...')}
        </div>
      ),
    },
  ];

  const activeTabConfig = tabs.find((tab) => tab.id === activeTab);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="p-3 bg-gradient-to-br from-emerald-500/20 to-teal-500/20 rounded-xl">
          <SettingsIcon className="w-6 h-6 text-emerald-500" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">
            {t('settings.title', 'Settings')}
          </h1>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            {t('settings.subtitle', 'Manage your platform configuration and preferences')}
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-zinc-200 dark:border-zinc-700">
        <nav className="flex space-x-8" aria-label="Tabs">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`
                flex items-center gap-2 py-4 px-1 border-b-2 font-medium text-sm transition-colors
                ${
                  activeTab === tab.id
                    ? 'border-emerald-500 text-emerald-600 dark:text-emerald-400'
                    : 'border-transparent text-zinc-500 hover:text-zinc-700 hover:border-zinc-300 dark:text-zinc-400 dark:hover:text-zinc-300'
                }
              `}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      <div className="mt-6">{activeTabConfig?.component}</div>
    </div>
  );
};

