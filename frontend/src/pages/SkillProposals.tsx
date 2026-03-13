import React from 'react';
import { useTranslation } from 'react-i18next';
import { MemoryWorkspace } from '@/components/memory/MemoryWorkspace';

export const SkillProposals: React.FC = () => {
  const { t } = useTranslation();

  return (
    <MemoryWorkspace
      memoryType="skill_proposal"
      title={t('nav.skillProposals', { defaultValue: 'Skill Proposals' })}
      description={t('memory.description.skillProposal', {
        defaultValue:
          'A learned skill candidate distilled from successful task execution paths. Requires review before reuse.',
      })}
    />
  );
};
