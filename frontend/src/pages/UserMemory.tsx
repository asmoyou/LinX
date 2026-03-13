import React from 'react';
import { useTranslation } from 'react-i18next';
import { MemoryWorkspace } from '@/components/memory/MemoryWorkspace';

export const UserMemory: React.FC = () => {
  const { t } = useTranslation();

  return (
    <MemoryWorkspace
      memoryType="user_memory"
      title={t('nav.userMemory', { defaultValue: 'User Memory' })}
      description={t('memory.description.userMemory', {
        defaultValue:
          'Long-term user facts including relationships, experiences, preferences, goals, and important events.',
      })}
    />
  );
};
