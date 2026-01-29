import React, { useState } from 'react';
import { Play, Loader2, CheckCircle, XCircle, Clock, Terminal, Code } from 'lucide-react';
import { skillsApi } from '@/api/skills';

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
  const [dryRun, setDryRun] = useState(true);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<TestResult | null>(null);

  const isAgentSkill = skillType === 'agent_skill';

  const handleTest = async () => {
    setTesting(true);
    setResult(null);
    
    try {
      let testResult;
      if (isAgentSkill) {
        // Natural language testing for agent_skill
        testResult = await skillsApi.testSkill(skillId, {
          natural_language_input: naturalLanguageInput,
          dry_run: dryRun,
        });
      } else {
        // Structured testing for langchain_tool
        testResult = await skillsApi.testSkill(skillId, { inputs });
      }
      setResult(testResult);
    } catch (error: any) {
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
        <h3 className="text-lg font-medium text-foreground">测试技能</h3>
      </div>

      {/* Input Fields - Different for agent_skill vs langchain_tool */}
      {isAgentSkill ? (
        // Natural language input for agent_skill
        <div className="space-y-3">
          <label className="block text-sm font-medium text-foreground">
            自然语言输入
          </label>
          <textarea
            value={naturalLanguageInput}
            onChange={(e) => setNaturalLanguageInput(e.target.value)}
            className="w-full px-3 py-2 rounded-xl bg-muted/50 border border-border/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 min-h-[100px]"
            placeholder="例如：获取伦敦的天气信息"
          />
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="dryRun"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
              className="rounded border-border/50"
            />
            <label htmlFor="dryRun" className="text-sm text-muted-foreground cursor-pointer">
              模拟运行（不实际执行命令）
            </label>
          </div>
          <p className="text-xs text-muted-foreground">
            💡 提示：输入自然语言描述，系统会解析并显示将要执行的命令
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
        disabled={testing || (isAgentSkill && !naturalLanguageInput.trim())}
        className="w-full px-4 py-2.5 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 font-medium"
      >
        {testing ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            测试中...
          </>
        ) : (
          <>
            <Play className="w-4 h-4" />
            运行测试
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
                  {result.success ? '测试成功' : '测试失败'}
                </h4>
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Clock className="w-3 h-3" />
                  {result.execution_time.toFixed(3)}s
                </div>
              </div>
              
              {result.success ? (
                isAgentSkill && result.parsed_commands ? (
                  // Agent skill result display
                  <div className="space-y-3">
                    {/* Parsed Commands */}
                    <div>
                      <div className="flex items-center gap-2 mb-2">
                        <Terminal className="w-4 h-4 text-muted-foreground" />
                        <div className="text-sm font-medium text-foreground">解析的命令：</div>
                      </div>
                      <div className="space-y-2">
                        {result.parsed_commands.map((cmd, i) => (
                          <div key={i} className="p-3 bg-black/30 rounded-lg">
                            <div className="flex items-start gap-2 mb-1">
                              <Code className="w-3 h-3 text-muted-foreground mt-0.5 flex-shrink-0" />
                              <div className="text-xs text-muted-foreground">{cmd.command_type}</div>
                            </div>
                            <pre className="text-sm text-foreground font-mono mb-1 overflow-x-auto">
                              {cmd.command}
                            </pre>
                            {cmd.description && (
                              <div className="text-xs text-muted-foreground">{cmd.description}</div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                    
                    {/* Output */}
                    <div>
                      <div className="text-sm font-medium text-foreground mb-2">
                        {dryRun ? '模拟输出：' : '实际输出：'}
                      </div>
                      <pre className="text-sm bg-black/30 p-3 rounded-lg overflow-x-auto text-foreground">
                        {result.actual_output || result.simulated_output}
                      </pre>
                    </div>
                  </div>
                ) : (
                  // LangChain tool result display
                  <div className="space-y-2">
                    <div className="text-sm text-muted-foreground">输出：</div>
                    <pre className="text-sm bg-black/30 p-3 rounded overflow-x-auto text-foreground">
                      {typeof result.output === 'string'
                        ? result.output
                        : JSON.stringify(result.output, null, 2)}
                    </pre>
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
