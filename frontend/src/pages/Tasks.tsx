import React from 'react';
import { useTranslation } from 'react-i18next';
import { GlassPanel } from '@/components/GlassPanel';

export const Tasks: React.FC = () => {
  const { t } = useTranslation();

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-800 dark:text-white mb-6">
        {t('nav.tasks')}
      </h1>
      <GlassPanel>
        <p className="text-gray-700 dark:text-gray-300">
          Task management coming soon...
        </p>
      </GlassPanel>
    </div>
  );
};
