import { Loader2, Search, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { Agent } from '@/types/agent';

interface BindSkillModalProps {
  isOpen: boolean;
  skillName: string;
  agents: Agent[];
  selectedAgentIds: string[];
  allowEmptySelection?: boolean;
  isLoadingAgents?: boolean;
  isSubmitting?: boolean;
  error?: string | null;
  onClose: () => void;
  onChangeSelectedAgentIds: (agentIds: string[]) => void;
  onConfirm: () => void;
}

export default function BindSkillModal({
  isOpen,
  skillName,
  agents,
  selectedAgentIds,
  allowEmptySelection = false,
  isLoadingAgents = false,
  isSubmitting = false,
  error,
  onClose,
  onChangeSelectedAgentIds,
  onConfirm,
}: BindSkillModalProps) {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');

  const filteredAgents = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) {
      return agents;
    }
    return agents.filter((agent) =>
      [agent.name, agent.type, agent.id].join('\n').toLowerCase().includes(normalizedQuery),
    );
  }, [agents, query]);

  if (!isOpen) {
    return null;
  }

  const allFilteredSelected =
    filteredAgents.length > 0 && filteredAgents.every((agent) => selectedAgentIds.includes(agent.id));

  const toggleAgent = (agentId: string) => {
    if (selectedAgentIds.includes(agentId)) {
      onChangeSelectedAgentIds(selectedAgentIds.filter((id) => id !== agentId));
    } else {
      onChangeSelectedAgentIds([...selectedAgentIds, agentId]);
    }
  };

  const toggleSelectAllFiltered = () => {
    if (allFilteredSelected) {
      onChangeSelectedAgentIds(
        selectedAgentIds.filter((id) => !filteredAgents.some((agent) => agent.id === id)),
      );
      return;
    }
    const merged = new Set(selectedAgentIds);
    filteredAgents.forEach((agent) => merged.add(agent.id));
    onChangeSelectedAgentIds(Array.from(merged));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-2xl border border-border/50 bg-background shadow-2xl">
        <div className="flex items-start justify-between border-b border-border/40 p-6">
          <div>
            <h2 className="text-xl font-semibold text-foreground">
              {t('skills.bindSkillTitle', { defaultValue: 'Bind skill to agents' })}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {t('skills.bindSkillDescription', {
                defaultValue: 'Select one or more agents to start using {{skillName}}.',
                skillName,
              })}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted/40 hover:text-foreground"
            aria-label={t('skills.close', { defaultValue: 'Close' })}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 p-6">
          <div className="relative">
            <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t('skills.searchAgents', { defaultValue: 'Search agents' })}
              className="w-full rounded-xl border border-border/50 bg-muted/30 py-3 pl-11 pr-4 text-sm text-foreground outline-none transition-colors focus:border-emerald-500"
            />
          </div>

          <div className="flex items-center justify-between text-sm">
            <button
              type="button"
              onClick={toggleSelectAllFiltered}
              disabled={isLoadingAgents || filteredAgents.length === 0}
              className="rounded-lg border border-border/50 px-3 py-1.5 text-foreground transition-colors hover:bg-muted/40 disabled:opacity-60"
            >
              {allFilteredSelected
                ? t('skills.clearFilteredAgents', { defaultValue: 'Clear filtered' })
                : t('skills.selectAllFilteredAgents', { defaultValue: 'Select filtered' })}
            </button>
            <span className="text-muted-foreground">
              {t('skills.selectedAgentsCount', {
                defaultValue: '{{count}} selected',
                count: selectedAgentIds.length,
              })}
            </span>
          </div>

          {isLoadingAgents ? (
            <div className="flex items-center gap-2 rounded-xl border border-border/40 bg-muted/20 px-4 py-3 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              {t('skills.loadingAgents', { defaultValue: 'Loading agents…' })}
            </div>
          ) : filteredAgents.length === 0 ? (
            <div className="rounded-xl border border-border/40 bg-muted/20 px-4 py-3 text-sm text-muted-foreground">
              {t('skills.noAgentsFound', { defaultValue: 'No agents matched your search.' })}
            </div>
          ) : (
            <div className="max-h-80 space-y-2 overflow-y-auto rounded-xl border border-border/40 bg-muted/10 p-3">
              {filteredAgents.map((agent) => {
                const checked = selectedAgentIds.includes(agent.id);
                return (
                  <label
                    key={agent.id}
                    className="flex cursor-pointer items-center justify-between rounded-xl border border-transparent bg-background/70 px-4 py-3 transition-colors hover:border-emerald-300 hover:bg-background"
                  >
                    <div className="min-w-0">
                      <div className="font-medium text-foreground">{agent.name}</div>
                      <div className="mt-1 text-xs text-muted-foreground">{agent.type}</div>
                    </div>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleAgent(agent.id)}
                      className="h-4 w-4 rounded border-border text-emerald-500 focus:ring-emerald-500"
                    />
                  </label>
                );
              })}
            </div>
          )}

          {error ? (
            <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/20 dark:bg-rose-500/10 dark:text-rose-300">
              {error}
            </div>
          ) : null}
        </div>

        <div className="flex items-center justify-end gap-3 border-t border-border/40 p-6">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-border/50 px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted/40"
          >
            {t('skills.cancel', { defaultValue: 'Cancel' })}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={((selectedAgentIds.length === 0 && !allowEmptySelection) || isSubmitting || isLoadingAgents)}
            className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-emerald-500 to-cyan-500 px-5 py-2.5 text-sm font-medium text-white shadow-lg transition-transform hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {t('skills.saveBindings', { defaultValue: 'Save Bindings' })}
          </button>
        </div>
      </div>
    </div>
  );
}
