import React, { useState, useEffect } from 'react';
import { Play, Loader2, CheckCircle, XCircle, Clock, Terminal, Code, Bot } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { skillsApi } from '@/api/skills';
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
  // Agent skill specific fields
  input?: string;
  parsed_commands?: Array<{
    command_type: string;
    command: string;
    description: string;
  }>;
  simulated_output?: string;
  actual_output?: string;
}

const SkillTester: React.FC<SkillTesterProps> = ({
  skillId,
  skillName,
  skillType,
  interfaceDefinition,
}) => {
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [naturalLanguageInput, setNaturalLanguageInput] = useState('');
  const [dryRun] = useState(true);
  const [useAgent, setUseAgent] = useState(false);
  const [selectedAgentId, setSelectedAgentId] = useState<string>('');
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loadingAgents, setLoadingAgents] = useState(false);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<TestResult | null>(null);
  const { t } = useTranslation();

  const isAgentSkill = skillType === 'agent_skill';

  // Load agents when component mounts (only for agent_skill)
  useEffect(() => {
    if (isAgentSkill) {
      loadAgents();
    }
  }, [isAgentSkill]);

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
    setTesting(true);
    setResult(null);
    
    try {
      let testResult;
      if (isAgentSkill) {
        // Natural language testing for agent_skill
        const params: any = {
          natural_language_input: naturalLanguageInput,
        };
        
        // If using agent, pass agent_id instead of dry_run
        if (useAgent && selectedAgentId) {
          params.agent_id = selectedAgentId;
          console.log('Testing with agent:', { skillId, agent_id: selectedAgentId, natural_language_input: naturalLanguageInput });
        } else {
          params.dry_run = dryRun;
          console.log('Testing with dry run:', { skillId, dry_run: dryRun, natural_language_input: naturalLanguageInput });
        }
        
        testResult = await skillsApi.testSkill(skillId, params);
      } else {
        // Structured testing for langchain_tool
        console.log('Testing langchain tool:', { skillId, inputs });
        testResult = await skillsApi.testSkill(skillId, { inputs });
      }
      setResult(testResult);
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
    }
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
          
          {/* Execution Mode Selection */}
          <div className="space-y-2">
            <label className="block text-sm font-medium text-foreground">
              {t('skills.executionMode', '执行模式')}
            </label>
            
            {/* Dry Run Mode */}
            <div 
              className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                !useAgent 
                  ? 'border-primary bg-primary/10' 
                  : 'border-border/50 bg-muted/30 hover:bg-muted/50'
              }`}
              onClick={() => setUseAgent(false)}
            >
              <div className="flex items-start gap-3">
                <input
                  type="radio"
                  checked={!useAgent}
                  onChange={() => setUseAgent(false)}
                  className="mt-0.5"
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <Terminal className="w-4 h-4" />
                    <span className="font-medium text-sm">{t('skills.dryRunMode', '模拟运行')}</span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {t('skills.dryRunModeDesc', '解析指令但不实际执行，快速查看将要执行的命令')}
                  </p>
                </div>
              </div>
            </div>
            
            {/* Agent Execution Mode */}
            <div 
              className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                useAgent 
                  ? 'border-primary bg-primary/10' 
                  : 'border-border/50 bg-muted/30 hover:bg-muted/50'
              }`}
              onClick={() => setUseAgent(true)}
            >
              <div className="flex items-start gap-3">
                <input
                  type="radio"
                  checked={useAgent}
                  onChange={() => setUseAgent(true)}
                  className="mt-0.5"
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <Bot className="w-4 h-4" />
                    <span className="font-medium text-sm">{t('skills.agentExecutionMode', '使用 Agent 执行')}</span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {t('skills.agentExecutionModeDesc', 'Agent 使用 LLM 理解指令并真实执行技能包中的代码')}
                  </p>
                  
                  {/* Agent Selection */}
                  {useAgent && (
                    <div className="mt-3 space-y-2">
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
                              {agent.provider && agent.model 
                                ? ` (${agent.provider}/${agent.model})`
                                : ''}
                            </option>
                          ))}
                        </select>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
          
          <p className="text-xs text-muted-foreground">
            💡 {t('skills.testTip', '提示：模拟运行可快速验证指令解析，使用 Agent 执行可获得真实结果')}
          </p>
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
          (isAgentSkill && useAgent && !selectedAgentId)
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
                  // Agent skill result display
                  <div className="space-y-3">
                    {result.mode === 'agent_execution' ? (
                      // Agent execution result
                      <div>
                        <div className="flex items-center gap-2 mb-2">
                          <Bot className="w-4 h-4 text-muted-foreground" />
                          <div className="text-sm font-medium text-foreground">
                            {t('skills.agentExecutionResult', 'Agent 执行结果：')}
                          </div>
                        </div>
                        <div className="markdown-content bg-muted/30 p-4 rounded-lg overflow-x-auto">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {result.output || ''}
                          </ReactMarkdown>
                        </div>
                      </div>
                    ) : result.parsed_commands ? (
                      // Dry run result with parsed commands
                      <>
                        {/* Parsed Commands */}
                        <div>
                          <div className="flex items-center gap-2 mb-2">
                            <Terminal className="w-4 h-4 text-muted-foreground" />
                            <div className="text-sm font-medium text-foreground">
                              {t('skills.parsedCommands', '解析的命令：')}
                            </div>
                          </div>
                          <div className="space-y-2">
                            {result.parsed_commands.map((cmd, i) => (
                              <div key={i} className="p-3 bg-muted/30 rounded-lg border border-border/30">
                                <div className="flex items-start gap-2 mb-1">
                                  <Code className="w-3 h-3 text-muted-foreground mt-0.5 flex-shrink-0" />
                                  <div className="text-xs text-muted-foreground">{cmd.command_type}</div>
                                </div>
                                <pre className="text-sm text-foreground font-mono mb-1 overflow-x-auto whitespace-pre-wrap break-words">
                                  {cmd.command}
                                </pre>
                                {cmd.description && (
                                  <div className="text-xs text-muted-foreground mt-2">{cmd.description}</div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                        
                        {/* Output */}
                        <div>
                          <div className="text-sm font-medium text-foreground mb-2">
                            {dryRun ? t('skills.simulatedOutput', '模拟输出：') : t('skills.actualOutput', '实际输出：')}
                          </div>
                          <div className="markdown-content bg-muted/30 p-4 rounded-lg overflow-x-auto">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {result.actual_output || result.simulated_output || ''}
                            </ReactMarkdown>
                          </div>
                        </div>
                      </>
                    ) : null}
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
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SkillTester;
