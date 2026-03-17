import React, { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { MemoryWorkbench } from '@/components/memory/MemoryWorkbench';
import type { MemorySurfaceType } from '@/types/memory';

const MEMORY_TAB_PARAM = 'tab';

const getTabFromSearchParam = (value: string | null): MemorySurfaceType => {
  return value === 'skill-proposals' ? 'skill_proposal' : 'user_memory';
};

const getSearchParamFromTab = (memoryType: MemorySurfaceType): string => {
  return memoryType === 'skill_proposal' ? 'skill-proposals' : 'user-memory';
};

export const Memory: React.FC = () => {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();

  const memoryType = useMemo(
    () => getTabFromSearchParam(searchParams.get(MEMORY_TAB_PARAM)),
    [searchParams]
  );

  const handleTabChange = useCallback(
    (nextTab: MemorySurfaceType) => {
      const nextSearchParams = new URLSearchParams(searchParams);
      nextSearchParams.set(MEMORY_TAB_PARAM, getSearchParamFromTab(nextTab));
      setSearchParams(nextSearchParams);
    },
    [searchParams, setSearchParams]
  );

  const description =
    memoryType === 'user_memory'
      ? t('memory.description.userMemory', {
          defaultValue:
            'Long-term user facts including relationships, experiences, preferences, goals, and important events.',
        })
      : t('memory.description.skillProposal', {
          defaultValue:
            'A learned skill candidate distilled from successful task execution paths. Requires review before reuse.',
        });

  return (
    <MemoryWorkbench
      memoryType={memoryType}
      title={t('memory.title', { defaultValue: 'Memory System' })}
      description={description}
      onMemoryTypeChange={handleTabChange}
    />
  );
};

export default Memory;
