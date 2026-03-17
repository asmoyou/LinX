import React from 'react';
import { useTranslation } from 'react-i18next';
import { MemoryWorkbench } from '@/components/memory/MemoryWorkbench';

export const SkillProposals: React.FC = () => {
  const { t } = useTranslation();

  return (
    <MemoryWorkbench
      memoryType="skill_proposal"
      title={t('memory.title', { defaultValue: 'Memory System' })}
      description={t('memory.description.skillProposal', {
        defaultValue:
          'A learned skill candidate distilled from successful task execution paths. Requires review before reuse.',
      })}
    />
  );
};
