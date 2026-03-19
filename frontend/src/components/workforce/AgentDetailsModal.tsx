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
  Cpu,
  Database,
  Shield,
  Brain,
  List,
  Terminal,
  ChevronRight,
  Code,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { agentsApi, type AgentLogEntry, type AgentMetrics } from '@/api/agents';
import type { Agent } from '@/types/agent';
import { LayoutModal } from '@/components/LayoutModal';
import { motion, AnimatePresence } from 'framer-motion';

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

type TabType = 'overview' | 'capabilities' | 'logs';

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
  const [activeTab, setActiveTab] = useState<TabType>('overview');

  const agentId = agent?.id;

  useEffect(() => {
    setAgentDetails(agent);
    setMetrics(null);
    setLogs([]);
    setErrorMessage(null);
    setActiveTab('overview');
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

  const tasksExecuted = Math.max(
    0,
    metrics?.tasksExecuted ??
      (displayAgent.tasksExecuted ??
        (displayAgent.tasksCompleted ?? 0) + (displayAgent.tasksFailed ?? 0))
  );
  const tasksCompleted = Math.max(0, metrics?.tasksCompleted ?? displayAgent.tasksCompleted ?? 0);
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

  const statusLabel = t(`agent.details.statusValue.${displayAgent.status}`, {
    defaultValue: displayAgent.status,
  });
  const accessLevelValue = displayAgent.accessLevel || 'private';
  const accessLevelLabel = t(`agent.details.accessLevelValue.${accessLevelValue}`, {
    defaultValue: accessLevelValue,
  });
  const knowledgeSelectedCount = displayAgent.allowedKnowledge?.length || 0;

  const StatCard = ({ icon: Icon, label, value, colorClass }: any) => (
    <div className="flex flex-col p-3 rounded-xl border border-zinc-200/60 bg-white/50 dark:border-zinc-700/50 dark:bg-zinc-800/40 shadow-sm transition-all hover:shadow-md">
      <div className="flex items-center gap-2 mb-1">
        <Icon className={`w-4 h-4 ${colorClass}`} />
        <span className="text-[11px] font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
          {label}
        </span>
      </div>
      <p className="text-lg font-bold text-zinc-900 dark:text-zinc-100 truncate">{value}</p>
    </div>
  );

  const SectionHeader = ({ icon: Icon, title }: any) => (
    <div className="flex items-center gap-2 mb-4">
      <div className="p-1.5 rounded-lg bg-indigo-50 dark:bg-indigo-900/30">
        <Icon className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
      </div>
      <h3 className="text-sm font-bold text-zinc-900 dark:text-zinc-100 uppercase tracking-tight">
        {title}
      </h3>
    </div>
  );

  const InfoRow = ({ label, value }: { label: string; value: React.ReactNode }) => (
    <div className="flex items-start justify-between py-2 border-b border-zinc-100 dark:border-zinc-800/50 last:border-0">
      <span className="text-sm text-zinc-500 dark:text-zinc-400">{label}</span>
      <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100 text-right ml-4">
        {value}
      </span>
    </div>
  );

  return (
    <LayoutModal isOpen={isOpen} onClose={onClose} closeOnBackdropClick={false} closeOnEscape={true}>
      <div className="w-full max-w-5xl my-auto max-h-[calc(100vh-var(--app-header-height,4rem)-3rem)] overflow-hidden flex flex-col modal-panel rounded-[24px] shadow-2xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800">
        {/* Header */}
        <div className="p-6 pb-4 border-b border-zinc-100 dark:border-zinc-800 flex items-start justify-between bg-zinc-50/50 dark:bg-zinc-900/50">
          <div className="flex gap-4">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white shadow-lg shrink-0">
              {displayAgent.avatar ? (
                <img src={displayAgent.avatar} alt="" className="w-full h-full object-cover rounded-2xl" />
              ) : (
                <Brain className="w-8 h-8" />
              )}
            </div>
            <div>
              <div className="flex items-center gap-3 mb-1">
                <h2 className="text-2xl font-black text-zinc-900 dark:text-zinc-100 tracking-tight">
                  {displayAgent.name}
                </h2>
                <div
                  className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-widest border ${
                    displayAgent.status === 'working'
                      ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-400 dark:border-emerald-800/50'
                      : displayAgent.status === 'idle'
                      ? 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/30 dark:text-amber-400 dark:border-amber-800/50'
                      : 'bg-zinc-50 text-zinc-600 border-zinc-200 dark:bg-zinc-800 dark:text-zinc-400 dark:border-zinc-700'
                  }`}
                >
                  {statusLabel}
                </div>
              </div>
              <div className="flex items-center gap-2 text-sm text-zinc-500 dark:text-zinc-400">
                <span className="capitalize px-2 py-0.5 bg-zinc-100 dark:bg-zinc-800 rounded font-medium">
                  {displayAgent.type}
                </span>
                <ChevronRight className="w-3 h-3" />
                <span>{displayAgent.model || '-'}</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => void loadDetails()}
              disabled={isLoading}
              className="p-2.5 rounded-xl transition-all disabled:opacity-50 bg-white hover:bg-zinc-100 text-zinc-600 border border-zinc-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 dark:text-zinc-300 dark:border-zinc-700"
              title={t('agent.details.refresh')}
            >
              {isLoading ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <RefreshCw className="w-5 h-5" />
              )}
            </button>
            {onTest && (
              <button
                onClick={() => onTest(displayAgent)}
                className="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-bold transition-all flex items-center gap-2 shadow-lg shadow-indigo-500/20"
              >
                <MessageSquare className="w-4 h-4" />
                {t('agent.testAgent')}
              </button>
            )}
            <button
              onClick={onClose}
              className="p-2.5 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-xl transition-colors"
            >
              <X className="w-6 h-6 text-zinc-400 dark:text-zinc-500" />
            </button>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="px-6 border-b border-zinc-100 dark:border-zinc-800 flex gap-6 bg-zinc-50/30 dark:bg-zinc-900/30">
          {[
            { id: 'overview', label: t('common.show'), icon: List },
            { id: 'capabilities', label: t('agent.capabilities'), icon: Brain },
            { id: 'logs', label: t('agent.details.recentLogs'), icon: Terminal },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as TabType)}
              className={`py-4 text-sm font-bold flex items-center gap-2 transition-all relative ${
                activeTab === tab.id
                  ? 'text-indigo-600 dark:text-indigo-400'
                  : 'text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
              {activeTab === tab.id && (
                <motion.div
                  layoutId="activeTab"
                  className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-600 dark:bg-indigo-400"
                />
              )}
            </button>
          ))}
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto p-6 bg-white dark:bg-zinc-900">
          {errorMessage && (
            <div className="mb-6 p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 dark:bg-rose-900/20 dark:border-rose-800/50 dark:text-rose-400 text-sm flex items-center gap-3">
              <AlertTriangle className="w-5 h-5 shrink-0" />
              <span className="font-medium">{errorMessage}</span>
            </div>
          )}

          <AnimatePresence mode="wait">
            {activeTab === 'overview' && (
              <motion.div
                key="overview"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.2 }}
                className="space-y-8"
              >
                {/* Stats Grid */}
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
                  <StatCard
                    icon={CheckCircle}
                    label={t('agent.details.tasksExecuted')}
                    value={tasksExecuted}
                    colorClass="text-emerald-500"
                  />
                  <StatCard
                    icon={BarChart3}
                    label={t('agent.details.completionRate')}
                    value={completionRate}
                    colorClass="text-indigo-500"
                  />
                  <StatCard
                    icon={Clock3}
                    label={t('agent.details.queue')}
                    value={t('agent.details.queueValue', {
                      pending: pendingTasks,
                      running: inProgressTasks,
                    })}
                    colorClass="text-amber-500"
                  />
                  <StatCard
                    icon={Activity}
                    label={t('agent.details.lastActivity')}
                    value={formatDateTime(
                      metrics?.lastActivityAt ?? displayAgent.updatedAt,
                      i18n.language
                    )}
                    colorClass="text-sky-500"
                  />
                  <StatCard
                    icon={Shield}
                    label={t('agent.details.accessLevel')}
                    value={accessLevelLabel}
                    colorClass="text-purple-500"
                  />
                </div>

                {/* Current Task if any */}
                {displayAgent.currentTask && (
                  <div className="p-4 rounded-2xl bg-indigo-50/50 dark:bg-indigo-900/10 border border-indigo-100 dark:border-indigo-900/30">
                    <div className="flex items-center gap-2 mb-2">
                      <div className="w-2 h-2 rounded-full bg-indigo-600 animate-pulse" />
                      <span className="text-xs font-bold uppercase tracking-widest text-indigo-700 dark:text-indigo-400">
                        {t('agent.details.currentTask')}
                      </span>
                    </div>
                    <p className="text-zinc-700 dark:text-zinc-300 font-medium leading-relaxed">
                      {displayAgent.currentTask}
                    </p>
                  </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                  {/* Model Settings */}
                  <div className="space-y-4">
                    <SectionHeader icon={Cpu} title={t('agent.details.modelAndRetrieval')} />
                    <div className="bg-zinc-50/50 dark:bg-zinc-800/30 rounded-2xl p-4 border border-zinc-100 dark:border-zinc-800/50">
                      <InfoRow
                        label={t('agent.details.providerAndModel')}
                        value={`${displayAgent.provider || '-'} / ${displayAgent.model || '-'}`}
                      />
                      <InfoRow
                        label={t('agent.details.temperature')}
                        value={displayAgent.temperature ?? 0.7}
                      />
                      <InfoRow
                        label={t('agent.details.maxTokens')}
                        value={displayAgent.maxTokens ?? 2000}
                      />
                      <InfoRow
                        label={t('agent.details.topP')}
                        value={displayAgent.topP ?? 0.9}
                      />
                      <InfoRow
                        label={t('agent.details.topK')}
                        value={displayAgent.topK ?? t('agent.details.defaultValue')}
                      />
                      <InfoRow
                        label={t('agent.details.similarityThreshold')}
                        value={displayAgent.similarityThreshold ?? t('agent.details.defaultValue')}
                      />
                    </div>
                  </div>

                  {/* Data Access */}
                  <div className="space-y-4">
                    <SectionHeader icon={Database} title={t('agent.details.dataAccess')} />
                    <div className="bg-zinc-50/50 dark:bg-zinc-800/30 rounded-2xl p-4 border border-zinc-100 dark:border-zinc-800/50">
                      <InfoRow
                        label={t('agent.details.allowedKnowledge')}
                        value={
                          knowledgeSelectedCount > 0
                            ? t('agent.details.knowledgeSelected', { count: knowledgeSelectedCount })
                            : t('agent.details.noKnowledgeWhitelist')
                        }
                      />
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {activeTab === 'capabilities' && (
              <motion.div
                key="capabilities"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.2 }}
                className="space-y-8"
              >
                {/* System Prompt */}
                <div className="space-y-4">
                  <SectionHeader icon={Code} title={t('agent.systemPrompt')} />
                  <div className="bg-zinc-950 rounded-2xl p-6 border border-zinc-800 shadow-inner relative group">
                    <pre className="text-zinc-300 font-mono text-sm whitespace-pre-wrap leading-relaxed max-h-[400px] overflow-y-auto custom-scrollbar">
                      {displayAgent.systemPrompt || t('agent.systemPromptPlaceholder')}
                    </pre>
                    {!displayAgent.systemPrompt && (
                      <div className="absolute inset-0 flex items-center justify-center bg-zinc-950/50 backdrop-blur-sm rounded-2xl">
                        <span className="text-zinc-500 italic">{t('agent.systemPromptPlaceholder')}</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Skills */}
                <div className="space-y-4">
                  <SectionHeader icon={Brain} title={t('agent.selectSkills')} />
                  <div className="flex flex-wrap gap-2">
                    {displayAgent.skill_summaries && displayAgent.skill_summaries.length > 0 ? (
                      displayAgent.skill_summaries.map((skill) => (
                        <div
                          key={skill.skill_id}
                          className="px-4 py-2 rounded-xl bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-100 dark:border-indigo-800/50 text-indigo-700 dark:text-indigo-300 text-sm font-bold flex items-center gap-2"
                        >
                          <Brain className="w-3 h-3" />
                          <span>{skill.display_name}</span>
                          <span className="font-mono text-[11px] text-indigo-500 dark:text-indigo-300/80">
                            {skill.skill_slug}
                          </span>
                        </div>
                      ))
                    ) : (
                      <div className="w-full p-8 rounded-2xl border-2 border-dashed border-zinc-200 dark:border-zinc-800 flex flex-col items-center justify-center text-zinc-500">
                        <Brain className="w-8 h-8 mb-2 opacity-20" />
                        <span className="text-sm">{t('agent.noSkillsSelected')}</span>
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            )}

            {activeTab === 'logs' && (
              <motion.div
                key="logs"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.2 }}
                className="h-full flex flex-col"
              >
                <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 overflow-hidden flex flex-col h-[500px] bg-zinc-50 dark:bg-zinc-950/50">
                  <div className="bg-zinc-100 dark:bg-zinc-900/80 px-4 py-2 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between">
                    <span className="text-[10px] font-black uppercase tracking-widest text-zinc-500">
                      Terminal Output
                    </span>
                    <div className="flex gap-1.5">
                      <div className="w-2.5 h-2.5 rounded-full bg-rose-500/20" />
                      <div className="w-2.5 h-2.5 rounded-full bg-amber-500/20" />
                      <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/20" />
                    </div>
                  </div>
                  <div className="flex-1 overflow-y-auto p-4 font-mono text-[13px] custom-scrollbar">
                    {isLoading && (
                      <div className="flex items-center gap-3 text-zinc-500 py-2">
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>{t('agent.details.loadingLogs')}</span>
                      </div>
                    )}

                    {!isLoading && logs.length === 0 && (
                      <div className="flex flex-col items-center justify-center h-full text-zinc-500 py-10">
                        <Terminal className="w-8 h-8 mb-2 opacity-20" />
                        <p>{t('agent.details.noRecentLogs')}</p>
                      </div>
                    )}

                    {!isLoading &&
                      logs.map((log, index) => (
                        <div
                          key={`${log.timestamp}-${index}`}
                          className="group flex gap-3 py-1 hover:bg-zinc-200/50 dark:hover:bg-zinc-800/30 px-2 -mx-2 rounded transition-colors"
                        >
                          <span className="text-zinc-400 shrink-0 select-none">
                            [{formatDateTime(log.timestamp, i18n.language).split(', ')[1] || '-'}]
                          </span>
                          <span
                            className={`font-bold shrink-0 w-16 ${
                              log.level === 'SUCCESS'
                                ? 'text-emerald-500'
                                : log.level === 'ERROR'
                                ? 'text-rose-500'
                                : 'text-blue-500'
                            }`}
                          >
                            {log.level}
                          </span>
                          <span className="text-zinc-700 dark:text-zinc-300 break-all">
                            {log.message}
                          </span>
                          <span className="ml-auto text-[10px] text-zinc-400 opacity-0 group-hover:opacity-100 transition-opacity uppercase font-bold tracking-tighter">
                            {log.source === 'audit'
                              ? t('agent.details.logSourceAudit')
                              : t('agent.details.logSourceTask')}
                          </span>
                        </div>
                      ))}
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </LayoutModal>
  );
};
