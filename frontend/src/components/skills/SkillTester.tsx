import React, { useState, useEffect, useRef } from 'react';
import { Play, Loader2, CheckCircle, XCircle, Clock, Bot } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { skillsApi } from '@/api/skills';
import type { SkillTestStreamChunk } from '@/api/skills';
import apiClient from '@/api/client';
import { useTranslation } from 'react-i18next';

interface Agent {
  id: string;  // API returns 'id', not 'agent_id'
  name: string;
  type: string;
  provider?: string;
  model?: string;
}

interface SkillTesterProps {
  skillId: string;
  skillName: string;
  skillType?: string;
  interfaceDefinition: {
    inputs: Record<string, string>;
    outputs: Record<string, string>;
  };
}

interface TestResult {
  success: boolean;
  output?: any;
  error?: string;
  execution_time: number;
  input?: string;
  agent_name?: string;
  mode?: string;
  execution_trace?: {
    session_id?: string;
    sandbox_id?: string;
    workspace_root?: string;
    synced_skill_files?: number;
    summary?: {
      total_steps?: number;
      successful_steps?: number;
      failed_steps?: number;
      timeout_steps?: number;
    };
    tool_calls?: Array<{
      step: number;
      round_number?: number;
      retry_number?: number;
      tool_name: string;
      status: string;
      arguments?: Record<string, any>;
      error?: string;
      result_preview?: string;
      timestamp?: string;
    }>;
  };
}

interface StreamLogEntry {
  type: string;
  content: string;
  timestamp: string;
}

const STREAM_LOG_COLLAPSE_CHAR_LIMIT = 240;
const STREAM_LOG_COLLAPSE_LINE_LIMIT = 6;
const STREAM_TEXT_COLLAPSE_CHAR_LIMIT = 600;
const STREAM_TEXT_COLLAPSE_LINE_LIMIT = 12;

const SkillTester: React.FC<SkillTesterProps> = ({
  skillId,
  skillName,
  skillType,
  interfaceDefinition,
}) => {
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [naturalLanguageInput, setNaturalLanguageInput] = useState('');
  const [selectedAgentId, setSelectedAgentId] = useState<string>('');
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loadingAgents, setLoadingAgents] = useState(false);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<TestResult | null>(null);
  const [streamSession, setStreamSession] = useState<{
    session_id?: string;
    sandbox_id?: string;
    workspace_root?: string;
    synced_skill_files?: number;
  } | null>(null);
  const [streamLogs, setStreamLogs] = useState<StreamLogEntry[]>([]);
  const [streamThinking, setStreamThinking] = useState('');
  const [streamContent, setStreamContent] = useState('');
  const [streamError, setStreamError] = useState<string | null>(null);
  const [expandedLogKeys, setExpandedLogKeys] = useState<Record<string, boolean>>({});
  const [expandThinking, setExpandThinking] = useState(false);
  const [expandContent, setExpandContent] = useState(false);
  const hasFinalResultRef = useRef(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const { t } = useTranslation();

  const isAgentSkill = skillType === 'agent_skill';

  // Load agents when component mounts (only for agent_skill)
  useEffect(() => {
    if (isAgentSkill) {
      loadAgents();
    }
  }, [isAgentSkill]);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const appendStreamLog = (type: string, content?: string) => {
    if (!content) {
      return;
    }
    const text = String(content).trim();
    if (!text) {
      return;
    }
    const entry: StreamLogEntry = {
      type,
      content: text,
      timestamp: new Date().toISOString(),
    };
    setStreamLogs((prev) => {
      const next = [...prev, entry];
      return next.length > 300 ? next.slice(-300) : next;
    });
  };

  const loadAgents = async () => {
    setLoadingAgents(true);
    try {
      const response = await apiClient.get<Agent[]>('/agents');
      const data = response.data;
      setAgents(data);
      // Auto-select first agent if available
      if (data.length > 0 && !selectedAgentId) {
        setSelectedAgentId(data[0].id);
      }
    } catch (error) {
      console.error('Failed to load agents:', error);
    } finally {
      setLoadingAgents(false);
    }
  };

  const handleTest = async () => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;

    setTesting(true);
    setResult(null);
    setStreamSession(null);
    setStreamLogs([]);
    setStreamThinking('');
    setStreamContent('');
    setStreamError(null);
    setExpandedLogKeys({});
    setExpandThinking(false);
    setExpandContent(false);
    hasFinalResultRef.current = false;

    try {
      let testResult;
      if (isAgentSkill) {
        const abortController = new AbortController();
        abortControllerRef.current = abortController;

        await skillsApi.testSkillStream(
          skillId,
          {
            natural_language_input: naturalLanguageInput,
            agent_id: selectedAgentId,
          },
          (chunk: SkillTestStreamChunk) => {
            if (chunk.type === 'session') {
              setStreamSession({
                session_id: chunk.session_id,
                sandbox_id: chunk.sandbox_id,
                workspace_root: chunk.workspace_root,
                synced_skill_files: chunk.synced_skill_files,
              });
              appendStreamLog(
                'session',
                `session=${chunk.session_id || 'n/a'} sandbox=${chunk.sandbox_id || 'n/a'} files=${chunk.synced_skill_files ?? 0}`
              );
              return;
            }

            if (chunk.type === 'final_result') {
              hasFinalResultRef.current = true;
              if (chunk.result) {
                setResult(chunk.result as TestResult);
              }
              appendStreamLog('final_result', '收到最终执行结果');
              return;
            }

            if (chunk.type === 'thinking') {
              if (chunk.content) {
                setStreamThinking((prev) => prev + chunk.content);
              }
              return;
            }

            if (chunk.type === 'content') {
              if (chunk.content) {
                setStreamContent((prev) => prev + chunk.content);
              }
              return;
            }

            if (chunk.type === 'done') {
              if (!hasFinalResultRef.current && chunk.success === false) {
                setResult({
                  success: false,
                  error: streamError || t('skills.testFailed', '测试失败'),
                  execution_time: 0,
                  mode: 'agent_execution',
                });
              }
              appendStreamLog('done', chunk.success ? '执行完成' : '执行失败');
              return;
            }

            appendStreamLog(chunk.type || 'info', chunk.content);

            if (chunk.type === 'error' && chunk.content && !hasFinalResultRef.current) {
              setStreamError(chunk.content);
            }
          },
          (errorMessage: string) => {
            setStreamError(errorMessage);
            appendStreamLog('error', errorMessage);
          },
          undefined,
          abortController.signal
        );

        if (!hasFinalResultRef.current && !streamError) {
          setResult({
            success: false,
            error: t('skills.testFailed', '测试失败'),
            execution_time: 0,
            mode: 'agent_execution',
          });
        }
      } else {
        testResult = await skillsApi.testSkill(skillId, { inputs });
      }

      if (!isAgentSkill) {
        setResult(testResult);
      }
    } catch (error: any) {
      console.error('Test failed:', error);
      setResult({
        success: false,
        output: null,
        error: error.response?.data?.detail || error.message || 'Test failed',
        execution_time: 0,
      });
    } finally {
      setTesting(false);
      abortControllerRef.current = null;
    }
  };

  const streamLogBadgeClass = (type: string): string => {
    if (type === 'tool_call') return 'bg-blue-500/20 text-blue-300';
    if (type === 'tool_result') return 'bg-green-500/20 text-green-300';
    if (type === 'tool_error' || type === 'error') return 'bg-red-500/20 text-red-300';
    if (type === 'warning') return 'bg-yellow-500/20 text-yellow-300';
    return 'bg-muted text-muted-foreground';
  };

  const isLongText = (text: string, charLimit: number, lineLimit: number): boolean => {
    if (!text) {
      return false;
    }
    return text.length > charLimit || text.split('\n').length > lineLimit;
  };

  const getCollapsedText = (text: string, charLimit: number, lineLimit: number): string => {
    if (!text) {
      return '';
    }
    const lines = text.split('\n');
    const byLine = lines.slice(0, lineLimit).join('\n');
    if (byLine.length > charLimit) {
      return `${byLine.slice(0, charLimit)}...`;
    }
    if (lines.length > lineLimit || text.length > charLimit) {
      return `${byLine}...`;
    }
    return byLine;
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-medium text-foreground">测试技能: {skillName}</h3>
      </div>

      {/* Input Fields - Different for agent_skill vs langchain_tool */}
      {isAgentSkill ? (
        // Natural language input for agent_skill
        <div className="space-y-3">
          <label className="block text-sm font-medium text-foreground">
            {t('skills.naturalLanguageInput', '自然语言输入')}
          </label>
          <textarea
            value={naturalLanguageInput}
            onChange={(e) => setNaturalLanguageInput(e.target.value)}
            className="w-full px-3 py-2 rounded-xl bg-muted/50 border border-border/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 min-h-[100px]"
            placeholder={t('skills.naturalLanguageInputPlaceholder', '例如：获取伦敦的天气信息')}
          />

          <div className="space-y-2">
            <label className="block text-xs font-medium text-foreground">
              {t('skills.selectAgent', '选择 Agent')}
            </label>
            {loadingAgents ? (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="w-3 h-3 animate-spin" />
                {t('common.loading', '加载中...')}
              </div>
            ) : agents.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                {t('skills.noAgentsAvailable', '暂无可用 Agent，请先创建 Agent')}
              </p>
            ) : (
              <select
                value={selectedAgentId}
                onChange={(e) => setSelectedAgentId(e.target.value)}
                className="w-full px-3 py-2 text-sm rounded-lg bg-muted/50 border border-border/50 text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
              >
                {agents.map((agent) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.name}
                    {agent.provider && agent.model ? ` (${agent.provider}/${agent.model})` : ''}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>
      ) : (
        // Structured inputs for langchain_tool
        <div className="space-y-3">
          <label className="block text-sm font-medium text-foreground">
            输入参数
          </label>
          {interfaceDefinition && Object.entries(interfaceDefinition.inputs || {}).length > 0 ? (
            Object.entries(interfaceDefinition.inputs).map(([key, type]) => (
              <div key={key}>
                <label className="block text-sm text-muted-foreground mb-1">
                  {key} <span className="text-muted-foreground/70">({String(type)})</span>
                </label>
                <input
                  type="text"
                  value={inputs[key] || ''}
                  onChange={(e) => setInputs({ ...inputs, [key]: e.target.value })}
                  className="w-full px-3 py-2 rounded-xl bg-muted/50 border border-border/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                  placeholder={`输入 ${key}...`}
                />
              </div>
            ))
          ) : (
            <p className="text-sm text-muted-foreground">此技能无需输入参数</p>
          )}
        </div>
      )}

      {/* Test Button */}
      <button
        onClick={handleTest}
        disabled={
          testing ||
          (isAgentSkill && !naturalLanguageInput.trim()) ||
          (isAgentSkill && !selectedAgentId)
        }
        className="w-full px-4 py-2.5 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 font-medium"
      >
        {testing ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            {t('skills.testing', '测试中...')}
          </>
        ) : (
          <>
            <Play className="w-4 h-4" />
            {t('skills.runTest', '运行测试')}
          </>
        )}
      </button>

      {isAgentSkill && (testing || streamLogs.length > 0 || streamThinking || streamContent || streamSession || streamError) && (
        <div className="p-4 rounded-xl border border-border/40 bg-muted/20 space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-sm font-medium text-foreground">
              {t('skills.liveExecutionProcess', '实时执行过程')}
            </div>
            {testing && (
              <div className="flex items-center gap-1 text-xs text-primary">
                <Loader2 className="w-3 h-3 animate-spin" />
                {t('skills.testing', '测试中...')}
              </div>
            )}
          </div>

          {streamSession && (
            <div className="text-xs text-muted-foreground">
              sandbox: {streamSession.sandbox_id || 'n/a'} | session: {streamSession.session_id || 'n/a'} | files:{' '}
              {streamSession.synced_skill_files ?? 0}
            </div>
          )}

          {streamLogs.length > 0 ? (
            <div className="max-h-56 overflow-y-auto space-y-2 pr-1">
              {streamLogs.map((entry, index) => (
                <div key={`${entry.timestamp}-${index}`} className="p-2 rounded-lg border border-border/30 bg-background/40">
                  {(() => {
                    const logKey = `${entry.timestamp}-${index}`;
                    const isLong = isLongText(
                      entry.content,
                      STREAM_LOG_COLLAPSE_CHAR_LIMIT,
                      STREAM_LOG_COLLAPSE_LINE_LIMIT
                    );
                    const isExpanded = !!expandedLogKeys[logKey];
                    const displayText =
                      isLong && !isExpanded
                        ? getCollapsedText(
                            entry.content,
                            STREAM_LOG_COLLAPSE_CHAR_LIMIT,
                            STREAM_LOG_COLLAPSE_LINE_LIMIT
                          )
                        : entry.content;

                    return (
                      <>
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`px-2 py-0.5 rounded text-[11px] ${streamLogBadgeClass(entry.type)}`}>
                      {entry.type}
                    </span>
                    <span className="text-[11px] text-muted-foreground">
                      {new Date(entry.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                  <div className="text-xs text-foreground/90 whitespace-pre-wrap break-words">
                    {displayText}
                  </div>
                  {isLong && (
                    <button
                      type="button"
                      onClick={() =>
                        setExpandedLogKeys((prev) => ({
                          ...prev,
                          [logKey]: !isExpanded,
                        }))
                      }
                      className="mt-1 text-xs text-primary hover:text-primary/80"
                    >
                      {isExpanded ? t('common.collapse', '收起') : t('common.expand', '展开')}
                    </button>
                  )}
                      </>
                    );
                  })()}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-muted-foreground">
              {t('skills.waitingForExecutionLogs', '等待执行日志...')}
            </div>
          )}

          {streamThinking && (
            <div className="space-y-1">
              <div className="text-xs font-medium text-foreground">
                {t('skills.agentThinking', '思考片段')}
              </div>
              {(() => {
                const isLong = isLongText(
                  streamThinking,
                  STREAM_TEXT_COLLAPSE_CHAR_LIMIT,
                  STREAM_TEXT_COLLAPSE_LINE_LIMIT
                );
                const displayText =
                  isLong && !expandThinking
                    ? getCollapsedText(
                        streamThinking,
                        STREAM_TEXT_COLLAPSE_CHAR_LIMIT,
                        STREAM_TEXT_COLLAPSE_LINE_LIMIT
                      )
                    : streamThinking;
                return (
                  <>
              <pre className="text-xs text-foreground/90 font-mono whitespace-pre-wrap break-words bg-muted/40 p-2 rounded">
                {displayText}
              </pre>
              {isLong && (
                <button
                  type="button"
                  onClick={() => setExpandThinking((prev) => !prev)}
                  className="text-xs text-primary hover:text-primary/80"
                >
                  {expandThinking ? t('common.collapse', '收起') : t('common.expand', '展开')}
                </button>
              )}
                  </>
                );
              })()}
            </div>
          )}

          {streamContent && (
            <div className="space-y-1">
              <div className="text-xs font-medium text-foreground">
                {t('skills.streamingOutput', '实时输出')}
              </div>
              {(() => {
                const isLong = isLongText(
                  streamContent,
                  STREAM_TEXT_COLLAPSE_CHAR_LIMIT,
                  STREAM_TEXT_COLLAPSE_LINE_LIMIT
                );
                const displayText =
                  isLong && !expandContent
                    ? getCollapsedText(
                        streamContent,
                        STREAM_TEXT_COLLAPSE_CHAR_LIMIT,
                        STREAM_TEXT_COLLAPSE_LINE_LIMIT
                      )
                    : streamContent;
                return (
                  <>
              <div className="markdown-content bg-muted/30 p-3 rounded-lg overflow-x-auto">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {displayText}
                </ReactMarkdown>
              </div>
              {isLong && (
                <button
                  type="button"
                  onClick={() => setExpandContent((prev) => !prev)}
                  className="text-xs text-primary hover:text-primary/80"
                >
                  {expandContent ? t('common.collapse', '收起') : t('common.expand', '展开')}
                </button>
              )}
                  </>
                );
              })()}
            </div>
          )}

          {streamError && (
            <div className="text-xs text-red-300 whitespace-pre-wrap break-words">
              {streamError}
            </div>
          )}
        </div>
      )}

      {/* Test Result - Different display for agent_skill */}
      {result && (
        <div
          className={`p-4 rounded-xl border ${
            result.success
              ? 'bg-green-500/10 border-green-500/30'
              : 'bg-red-500/10 border-red-500/30'
          }`}
        >
          <div className="flex items-start gap-3">
            {result.success ? (
              <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
            ) : (
              <XCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            )}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-2">
                <h4 className="font-medium text-foreground">
                  {result.success ? t('skills.testSuccess', '测试成功') : t('skills.testFailed', '测试失败')}
                </h4>
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Clock className="w-3 h-3" />
                  {result.execution_time.toFixed(3)}s
                </div>
                {result.mode === 'agent_execution' && result.agent_name && (
                  <div className="flex items-center gap-1 text-xs text-primary">
                    <Bot className="w-3 h-3" />
                    {result.agent_name}
                  </div>
                )}
              </div>
              
              {result.success ? (
                isAgentSkill ? (
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <Bot className="w-4 h-4 text-muted-foreground" />
                      <div className="text-sm font-medium text-foreground">
                        {t('skills.agentExecutionResult', 'Agent 执行结果：')}
                      </div>
                    </div>
                    <div className="markdown-content bg-muted/30 p-4 rounded-lg overflow-x-auto">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {String(result.output || '')}
                      </ReactMarkdown>
                    </div>
                  </div>
                ) : (
                  // LangChain tool result display
                  <div className="space-y-2">
                    <div className="text-sm text-muted-foreground">{t('skills.output', '输出：')}</div>
                    <div className="markdown-content bg-muted/30 p-4 rounded-lg overflow-x-auto border border-border/30">
                      {typeof result.output === 'string' ? (
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.output}</ReactMarkdown>
                      ) : (
                        <pre className="text-sm text-foreground font-mono whitespace-pre-wrap break-words">
                          {JSON.stringify(result.output, null, 2)}
                        </pre>
                      )}
                    </div>
                  </div>
                )
              ) : (
                <div className="text-sm text-red-300">{result.error}</div>
              )}

              {isAgentSkill &&
                result.execution_trace &&
                (result.execution_trace.summary?.total_steps ?? 0) > 0 &&
                (result.execution_trace.tool_calls?.length ?? 0) > 0 && (
                <div className="mt-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-medium text-foreground">
                      {t('skills.executionProcess', '执行过程')}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {result.execution_trace.summary?.successful_steps ?? 0}/
                      {result.execution_trace.summary?.total_steps ?? 0}
                      {t('skills.stepsSucceeded', ' 步成功')}
                    </div>
                  </div>

                  <div className="text-xs text-muted-foreground">
                    sandbox: {result.execution_trace.sandbox_id || 'n/a'} | session:{' '}
                    {result.execution_trace.session_id || 'n/a'} | files:{' '}
                    {result.execution_trace.synced_skill_files ?? 0}
                  </div>

                  {result.execution_trace.tool_calls && result.execution_trace.tool_calls.length > 0 ? (
                    <div className="space-y-2">
                      {result.execution_trace.tool_calls.map((toolCall) => (
                        <div
                          key={`${toolCall.step}-${toolCall.tool_name}-${toolCall.retry_number ?? 0}`}
                          className="p-3 bg-muted/30 rounded-lg border border-border/30"
                        >
                          <div className="flex items-center gap-2 text-sm mb-2">
                            <span className="text-muted-foreground">#{toolCall.step}</span>
                            <span className="font-medium text-foreground">{toolCall.tool_name}</span>
                            <span
                              className={`px-2 py-0.5 rounded text-xs ${
                                toolCall.status === 'success'
                                  ? 'bg-green-500/20 text-green-300'
                                  : toolCall.status === 'timeout'
                                    ? 'bg-yellow-500/20 text-yellow-300'
                                    : 'bg-red-500/20 text-red-300'
                              }`}
                            >
                              {toolCall.status}
                            </span>
                            {toolCall.round_number !== undefined && (
                              <span className="text-xs text-muted-foreground">
                                round {toolCall.round_number}
                              </span>
                            )}
                          </div>

                          {toolCall.arguments && Object.keys(toolCall.arguments).length > 0 && (
                            <pre className="text-xs text-foreground/90 font-mono whitespace-pre-wrap break-words bg-muted/40 p-2 rounded mb-2">
                              {JSON.stringify(toolCall.arguments, null, 2)}
                            </pre>
                          )}

                          {toolCall.result_preview && (
                            <div className="text-xs text-muted-foreground whitespace-pre-wrap break-words">
                              {toolCall.result_preview}
                            </div>
                          )}

                          {toolCall.error && (
                            <div className="text-xs text-red-300 whitespace-pre-wrap break-words mt-2">
                              {toolCall.error}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-xs text-muted-foreground">
                      {t('skills.noExecutionSteps', '本次执行未记录工具步骤。')}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SkillTester;
