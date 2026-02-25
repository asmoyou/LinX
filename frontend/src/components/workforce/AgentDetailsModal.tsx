import React, { useCallback, useEffect, useState } from 'react';
import {
  X,
  Activity,
  CheckCircle,
  MessageSquare,
  BarChart3,
  Loader2,
  RefreshCw,
  AlertTriangle,
  Clock3,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { agentsApi, type AgentLogEntry, type AgentMetrics } from '@/api/agents';
import type { Agent } from '@/types/agent';
import { LayoutModal } from '@/components/LayoutModal';

const normalizeMemoryScopes = (scopes?: string[]): string[] => {
  if (!scopes || scopes.length === 0) {
    return [];
  }

  const aliasMap: Record<string, string> = {
    agent: 'agent',
    agent_memories: 'agent',
    company: 'company',
    company_memories: 'company',
    user_context: 'user_context',
  };
  const normalized: string[] = [];

  for (const rawScope of scopes) {
    const scope = (rawScope || '').trim().toLowerCase();
    const canonicalScope = aliasMap[scope];
    if (canonicalScope && !normalized.includes(canonicalScope)) {
      normalized.push(canonicalScope);
    }
  }

  return normalized;
};

const formatDateTime = (value?: string | null, locale?: string): string => {
  if (!value) {
    return '-';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString(locale);
};

interface AgentDetailsModalProps {
  agent: Agent | null;
  isOpen: boolean;
  onClose: () => void;
  onTest?: (agent: Agent) => void;
}

export const AgentDetailsModal: React.FC<AgentDetailsModalProps> = ({
  agent,
  isOpen,
  onClose,
  onTest,
}) => {
  const { t, i18n } = useTranslation();
  const [agentDetails, setAgentDetails] = useState<Agent | null>(agent);
  const [metrics, setMetrics] = useState<AgentMetrics | null>(null);
  const [logs, setLogs] = useState<AgentLogEntry[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const agentId = agent?.id;

  useEffect(() => {
    setAgentDetails(agent);
    setMetrics(null);
    setLogs([]);
    setErrorMessage(null);
  }, [agentId, agent]);

  const loadDetails = useCallback(async () => {
    if (!agentId) {
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);

    try {
      const [detailResponse, metricsResponse, logsResponse] = await Promise.all([
        agentsApi.getById(agentId),
        agentsApi.getMetrics(agentId),
        agentsApi.getLogs(agentId, 50),
      ]);
      setAgentDetails(detailResponse);
      setMetrics(metricsResponse);
      setLogs(logsResponse);
    } catch (error) {
      console.error('Failed to load agent details:', error);
      setErrorMessage(t('agent.details.loadFailed'));
      setMetrics(null);
      setLogs([]);
    } finally {
      setIsLoading(false);
    }
  }, [agentId, t]);

  useEffect(() => {
    if (!isOpen || !agentId) {
      return;
    }
    void loadDetails();
  }, [isOpen, agentId, loadDetails]);

  if (!isOpen || !agent) return null;

  const displayAgent = agentDetails ?? agent;
  const configuredMemoryScopes = normalizeMemoryScopes(displayAgent.allowedMemory);
  const effectiveMemoryScopes =
    configuredMemoryScopes.length > 0
      ? configuredMemoryScopes
      : displayAgent.accessLevel === 'team' || displayAgent.accessLevel === 'public'
      ? ['agent', 'company', 'user_context']
      : ['agent', 'user_context'];

  const tasksExecuted = Math.max(
    0,
    metrics?.tasksExecuted ??
      (displayAgent.tasksExecuted ??
        (displayAgent.tasksCompleted ?? 0) + (displayAgent.tasksFailed ?? 0))
  );
  const tasksCompleted = Math.max(0, metrics?.tasksCompleted ?? displayAgent.tasksCompleted ?? 0);
  const tasksFailed = Math.max(0, metrics?.tasksFailed ?? displayAgent.tasksFailed ?? 0);
  const pendingTasks = Math.max(0, metrics?.pendingTasks ?? 0);
  const inProgressTasks = Math.max(0, metrics?.inProgressTasks ?? 0);
  const rawCompletionRate =
    typeof metrics?.completionRate === 'number'
      ? metrics.completionRate > 1
        ? metrics.completionRate / 100
        : metrics.completionRate
      : typeof displayAgent.completionRate === 'number'
      ? displayAgent.completionRate > 1
        ? displayAgent.completionRate / 100
        : displayAgent.completionRate
      : tasksExecuted > 0
      ? tasksCompleted / tasksExecuted
      : 0;
  const completionRate = `${(Math.max(0, Math.min(1, rawCompletionRate)) * 100).toFixed(tasksExecuted > 0 ? 1 : 0)}%`;
  const cardClassName =
    'p-4 rounded-lg border border-zinc-200/70 bg-zinc-50/90 dark:border-zinc-700/60 dark:bg-zinc-900/60';
  const sectionCardClassName =
    'p-4 rounded-lg border border-zinc-200/70 bg-zinc-50/90 dark:border-zinc-700/60 dark:bg-zinc-900/60 space-y-2 text-sm text-zinc-700 dark:text-zinc-300';
  const statusLabel = t(`agent.details.statusValue.${displayAgent.status}`, {
    defaultValue: displayAgent.status,
  });
  const accessLevelValue = displayAgent.accessLevel || 'private';
  const accessLevelLabel = t(`agent.details.accessLevelValue.${accessLevelValue}`, {
    defaultValue: accessLevelValue,
  });
  const translateMemoryScope = (scope: string): string =>
    t(`agent.details.memoryScope.${scope}`, { defaultValue: scope });
  const configuredMemoryScopesLabel =
    configuredMemoryScopes.length > 0
      ? configuredMemoryScopes.map(translateMemoryScope).join(', ')
      : t('agent.details.noExplicitMemoryScope');
  const effectiveMemoryScopesLabel = effectiveMemoryScopes.map(translateMemoryScope).join(', ');
  const knowledgeSelectedCount = displayAgent.allowedKnowledge?.length || 0;

  return (
    <LayoutModal isOpen={isOpen} onClose={onClose} closeOnBackdropClick={false} closeOnEscape={true}>
      <div className="w-full max-w-4xl my-auto max-h-[calc(100vh-var(--app-header-height,4rem)-3rem)] overflow-y-auto modal-panel rounded-[24px] shadow-2xl p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">{displayAgent.name}</h2>
            <p className="text-sm text-zinc-600 dark:text-zinc-400 capitalize">
              {displayAgent.type}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => void loadDetails()}
              disabled={isLoading}
              className="px-3 py-2 rounded-lg font-semibold transition-colors flex items-center gap-2 disabled:opacity-60 bg-zinc-100 hover:bg-zinc-200 text-zinc-700 dark:bg-zinc-800/60 dark:hover:bg-zinc-700 dark:text-zinc-200"
            >
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
              {t('agent.details.refresh')}
            </button>
            {onTest && (
              <button
                onClick={() => onTest(displayAgent)}
                className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg font-semibold transition-colors flex items-center gap-2"
              >
                <MessageSquare className="w-4 h-4" />
                {t('agent.testAgent')}
              </button>
            )}
            <button onClick={onClose} className="p-2 hover:bg-zinc-200 dark:hover:bg-zinc-700 rounded-lg transition-colors">
              <X className="w-6 h-6 text-zinc-700 dark:text-zinc-300" />
            </button>
          </div>
        </div>

        {errorMessage && (
          <div className="mb-6 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-700 dark:text-amber-300 text-sm flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>{errorMessage}</span>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-6">
          <div className={cardClassName}>
            <div className="flex items-center gap-2 mb-2">
              <Activity className="w-5 h-5 text-indigo-500" />
              <span className="text-sm text-zinc-600 dark:text-zinc-400">{t('agent.details.status')}</span>
            </div>
            <p className="text-lg font-semibold text-zinc-900 dark:text-zinc-100 capitalize">
              {statusLabel}
            </p>
          </div>
          <div className={cardClassName}>
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle className="w-5 h-5 text-green-500" />
              <span className="text-sm text-zinc-600 dark:text-zinc-400">{t('agent.details.tasksExecuted')}</span>
            </div>
            <p className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">{tasksExecuted}</p>
          </div>
          <div className={cardClassName}>
            <div className="flex items-center gap-2 mb-2">
              <BarChart3 className="w-5 h-5 text-blue-500" />
              <span className="text-sm text-zinc-600 dark:text-zinc-400">{t('agent.details.completionRate')}</span>
            </div>
            <p className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">{completionRate}</p>
          </div>
          <div className={cardClassName}>
            <div className="flex items-center gap-2 mb-2">
              <Clock3 className="w-5 h-5 text-orange-500" />
              <span className="text-sm text-zinc-600 dark:text-zinc-400">{t('agent.details.queue')}</span>
            </div>
            <p className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
              {t('agent.details.queueValue', { pending: pendingTasks, running: inProgressTasks })}
            </p>
          </div>
          <div className={cardClassName}>
            <div className="flex items-center gap-2 mb-2">
              <Clock3 className="w-5 h-5 text-sky-500" />
              <span className="text-sm text-zinc-600 dark:text-zinc-400">{t('agent.details.lastActivity')}</span>
            </div>
            <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              {formatDateTime(metrics?.lastActivityAt ?? displayAgent.updatedAt, i18n.language)}
            </p>
          </div>
        </div>

        {displayAgent.currentTask && (
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100 mb-2">{t('agent.details.currentTask')}</h3>
            <div className={sectionCardClassName}>
              <p>{displayAgent.currentTask}</p>
            </div>
          </div>
        )}

        <div className="mb-6">
          <h3 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100 mb-2">{t('agent.details.modelAndRetrieval')}</h3>
          <div className={sectionCardClassName}>
            <p>
              <span className="font-semibold">{t('agent.details.providerAndModel')}:</span>{' '}
              {displayAgent.provider || '-'} / {displayAgent.model || '-'}
            </p>
            <p>
              <span className="font-semibold">{t('agent.details.temperature')}:</span> {displayAgent.temperature ?? 0.7}
            </p>
            <p>
              <span className="font-semibold">{t('agent.details.maxTokens')}:</span> {displayAgent.maxTokens ?? 2000}
            </p>
            <p>
              <span className="font-semibold">{t('agent.details.topP')}:</span> {displayAgent.topP ?? 0.9}
            </p>
            <p>
              <span className="font-semibold">{t('agent.details.topK')}:</span>{' '}
              {displayAgent.topK ?? t('agent.details.defaultValue')}
            </p>
            <p>
              <span className="font-semibold">{t('agent.details.similarityThreshold')}:</span>{' '}
              {displayAgent.similarityThreshold ?? t('agent.details.defaultValue')}
            </p>
          </div>
        </div>

        <div className="mb-6">
          <h3 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100 mb-2">{t('agent.details.dataAccess')}</h3>
          <div className={sectionCardClassName}>
            <p>
              <span className="font-semibold">{t('agent.details.accessLevel')}:</span>{' '}
              <span className="capitalize">{accessLevelLabel}</span>
            </p>
            <p>
              <span className="font-semibold">{t('agent.details.allowedKnowledge')}:</span>{' '}
              {knowledgeSelectedCount > 0
                ? t('agent.details.knowledgeSelected', { count: knowledgeSelectedCount })
                : t('agent.details.noKnowledgeWhitelist')}
            </p>
            <p>
              <span className="font-semibold">{t('agent.details.allowedMemoryConfigured')}:</span>{' '}
              {configuredMemoryScopesLabel}
            </p>
            <p>
              <span className="font-semibold">{t('agent.details.allowedMemoryEffective')}:</span>{' '}
              {effectiveMemoryScopesLabel}
            </p>
          </div>
        </div>

        <div>
          <h3 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100 mb-2">{t('agent.details.recentLogs')}</h3>
          <div className="rounded-lg p-4 font-mono text-sm max-h-72 overflow-y-auto border border-zinc-200/70 bg-zinc-100/80 dark:border-zinc-700/60 dark:bg-zinc-950/70">
            {isLoading && (
              <div className="flex items-center gap-2 text-zinc-700 dark:text-zinc-300">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>{t('agent.details.loadingLogs')}</span>
              </div>
            )}

            {!isLoading && logs.length === 0 && (
              <p className="text-zinc-600 dark:text-zinc-400">{t('agent.details.noRecentLogs')}</p>
            )}

            {!isLoading &&
              logs.map((log, index) => (
                <div key={`${log.timestamp}-${index}`} className="mb-1">
                  <span className="text-zinc-500">[{formatDateTime(log.timestamp, i18n.language)}]</span>{' '}
                  <span
                    className={
                      log.level === 'SUCCESS'
                        ? 'text-emerald-600 dark:text-emerald-300'
                        : log.level === 'ERROR'
                        ? 'text-rose-600 dark:text-rose-300'
                        : 'text-blue-600 dark:text-blue-300'
                    }
                  >
                    {log.level}
                  </span>{' '}
                  <span className="text-zinc-700 dark:text-zinc-300">{log.message}</span>{' '}
                  <span className="text-zinc-500">
                    ({log.source === 'audit' ? t('agent.details.logSourceAudit') : t('agent.details.logSourceTask')})
                  </span>
                </div>
              ))}
          </div>
        </div>
      </div>
    </LayoutModal>
  );
};
