import React from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { Settings as SettingsIcon, Cpu, KeyRound, SlidersHorizontal, Building2, Sparkles } from 'lucide-react';
import { LLMSettings } from '../components/settings/LLMSettings';
import { EnvVarsSettings } from '../components/settings/EnvVarsSettings';
import { ProjectExecutionPolicySettings } from '../components/settings/ProjectExecutionPolicySettings';
import { BusinessBaselineSettings } from '../components/settings/BusinessBaselineSettings';
import { ExperienceSettings } from '../components/settings/ExperienceSettings';

export type SettingsTab = 'baseline' | 'experience' | 'llm' | 'envVars' | 'projectExecution';

interface TabConfig {
  id: SettingsTab;
  label: string;
  icon: React.ReactNode;
  component: React.ReactNode;
}

const DEFAULT_TAB: SettingsTab = 'baseline';
const TAB_PARAM = 'tab';
const VALID_TABS: SettingsTab[] = ['baseline', 'experience', 'llm', 'envVars', 'projectExecution'];

const getSettingsTab = (value: string | null): SettingsTab =>
  VALID_TABS.includes(value as SettingsTab) ? (value as SettingsTab) : DEFAULT_TAB;

export const Settings: React.FC = () => {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = getSettingsTab(searchParams.get(TAB_PARAM));

  const handleTabChange = (tab: SettingsTab) => {
    const nextSearchParams = new URLSearchParams(searchParams);

    if (tab === DEFAULT_TAB) {
      nextSearchParams.delete(TAB_PARAM);
    } else {
      nextSearchParams.set(TAB_PARAM, tab);
    }

    setSearchParams(nextSearchParams, { replace: true });
  };

  const tabs: TabConfig[] = [
    {
      id: 'baseline',
      label: t('settings.tabs.baseline', 'Business Baseline'),
      icon: <Building2 className="w-5 h-5" />,
      component: <BusinessBaselineSettings onOpenTab={handleTabChange} />,
    },
    {
      id: 'experience',
      label: t('settings.tabs.experience', 'UI Experience'),
      icon: <Sparkles className="w-5 h-5" />,
      component: <ExperienceSettings />,
    },
    {
      id: 'llm',
      label: t('settings.tabs.llm', 'LLM Providers'),
      icon: <Cpu className="w-5 h-5" />,
      component: <LLMSettings />,
    },
    {
      id: 'envVars',
      label: t('settings.tabs.envVars', 'Environment Variables'),
      icon: <KeyRound className="w-5 h-5" />,
      component: <EnvVarsSettings />,
    },
    {
      id: 'projectExecution',
      label: t('settings.tabs.projectExecution', 'Project Execution'),
      icon: <SlidersHorizontal className="w-5 h-5" />,
      component: <ProjectExecutionPolicySettings />, 
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
            {t('settings.subtitle', 'Manage platform-level configuration and governance')}
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-zinc-200 dark:border-zinc-700">
        <nav
          className="flex w-full flex-wrap gap-2 pb-2"
          aria-label={t('settings.tabs.ariaLabel', 'Settings tabs')}
        >
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => handleTabChange(tab.id)}
              aria-current={activeTab === tab.id ? 'page' : undefined}
              className={`
                flex shrink-0 items-center gap-2 whitespace-nowrap rounded-t-lg border-b-2 px-3 py-4 text-sm font-medium transition-colors
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
