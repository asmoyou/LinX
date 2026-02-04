# Agent Skill 执行机制

## 概述

本文档说明 LinX 系统中 Agent Skill 的执行机制，特别是多轮对话和工具调用的工作原理。

## 核心问题：多轮技能无法正常执行

### 症状

- **单轮工具**（如 calculator）正常工作 ✅
- **多轮工具**（如 weather-forcast）只执行一轮就停止 ❌
- LLM 返回编造的数据，而不是真实的 API 调用结果

### 根本原因

**`code_execution` 工具被从系统提示词中过滤掉了！**

查看 `backend/agent_framework/base_agent.py` 第 793 行（已修复）:

```python
# 之前的代码 - 错误！
langchain_tools = [t for t in self.tools if t.name != "code_execution"]
```

这导致:
1. `code_execution` 工具虽然被创建并添加到 `self.tools`
2. 但在生成系统提示词时被**故意过滤掉**
3. **LLM 根本不知道有 `code_execution` 工具可用**
4. 当 LLM 读取 Agent Skill 文档后，看到需要执行 Python 脚本
5. 但因为不知道 `code_execution` 工具，只能根据文档示例编造答案

### 执行流程对比

**单轮工具（Calculator）- 正常工作**:
```
Round 1: 用户问题 → LLM 调用 calculator → 获得结果
Round 2: LLM 基于结果 → 生成最终答案 ✅
```

**多轮工具（Weather）- 之前失败**:
```
Round 1: 用户问题 → LLM 调用 read_skill → 获得技能文档
Round 2: LLM 阅读文档 → 不知道 code_execution 存在 → 编造答案 ❌
```

**多轮工具（Weather）- 修复后应该**:
```
Round 1: 用户问题 → LLM 调用 read_skill → 获得技能文档
Round 2: LLM 阅读文档 → 调用 code_execution 执行脚本 → 获得真实数据
Round 3: LLM 基于真实数据 → 生成最终答案 ✅
```

## 解决方案

### 1. 包含 code_execution 在系统提示词中

**文件**: `backend/agent_framework/base_agent.py`

**修改前**:
```python
# Filter out code_execution tool from the list (it's always available)
langchain_tools = [t for t in self.tools if t.name != "code_execution"]
```

**修改后**:
```python
# Include ALL tools in the prompt (including code_execution)
langchain_tools = self.tools
```

### 2. 添加 code_execution 使用示例

在工具使用说明中添加 `code_execution` 的 JSON 格式示例:

```python
tools_prompt += "Example for code_execution:\n"
tools_prompt += "```json\n"
tools_prompt += '{"tool": "code_execution", "code": "print(\\'Hello World\\')"}\n'
tools_prompt += "```\n\n"
```

### 3. 智能提示词引导

在工具执行结果后，根据情况给出不同的提示:

```python
# 如果刚读取了技能文档
if any(tr.get('tool') == 'read_skill' for tr in tool_results):
    tool_results_text += "\n你已经获得了技能文档。如果需要执行技能中的脚本或命令，请使用 code_execution 工具。如果已经有足够信息，可以直接回答用户。"
else:
    tool_results_text += "\n请根据以上工具执行结果，给出最终回答。如果还需要更多信息或执行其他操作，可以继续调用工具。"
```

## LangChain Tools 状态

**当前状态**: LangChain 的 `bind_tools` 功能已不再使用。

系统现在使用:
- **提示词工具描述**: 在系统提示词中描述可用工具
- **JSON 格式工具调用**: LLM 输出 JSON 格式的工具调用请求
- **自定义解析**: 使用正则表达式解析 LLM 输出中的工具调用

### 为什么不用 bind_tools?

```python
# 日志中可以看到
"LLM does not support bind_tools, using without tool binding"
```

原因:
1. 不是所有 LLM 提供商都支持 function calling
2. 自定义 JSON 格式更灵活，支持更多模型
3. 可以更好地控制工具调用的格式和验证

## 工具类型

### 1. LangChain Tool (单轮工具)

**特点**: 一次调用即可完成任务

**示例**: Calculator 工具
```python
# Round 1: LLM 调用工具
{"tool": "calculator", "expression": "212312123 * 13"}

# Round 2: LLM 返回最终答案
"计算结果是 2,760,057,599"
```

### 2. Agent Skill (多轮工具)

**特点**: 需要多次工具调用才能完成任务

**示例**: Weather Forecast 工具
```python
# Round 1: 读取技能文档
{"tool": "read_skill", "skill_name": "weather-forcast"}

# Round 2: 执行技能脚本
{"tool": "code_execution", "code": "python3 /path/to/weather_helper.py current --location Beijing"}

# Round 3: 返回最终答案
"北京今天天气晴朗，温度 15°C..."
```

## 多轮对话机制

### 对话循环

```python
# backend/agent_framework/base_agent.py
for iteration in range(1, max_iterations + 1):
    # 1. LLM 生成输出
    llm_output = llm.invoke(messages)
    
    # 2. 解析工具调用
    tool_calls = parse_tool_calls(llm_output)
    
    if tool_calls:
        # 3. 执行工具
        tool_results = execute_tools(tool_calls)
        
        # 4. 将结果添加到对话历史
        messages.append(AIMessage(content=llm_output))
        messages.append(HumanMessage(content=tool_results_text))
        
        # 5. 继续下一轮
        continue
    else:
        # 没有工具调用，对话结束
        break
```

### 最大轮数

**默认**: 20 轮

```python
max_iterations = 20  # 可配置
```

如果达到最大轮数，系统会强制结束对话并返回当前结果。

## 工具调用格式

### JSON 格式

LLM 需要输出以下格式的 JSON:

```json
{
  "tool": "tool_name",
  "arg1": "value1",
  "arg2": "value2"
}
```

### 支持的包装格式

1. **带 markdown 代码块**:
```
```json
{"tool": "calculator", "expression": "1+1"}
```
```

2. **纯 JSON**:
```
{"tool": "calculator", "expression": "1+1"}
```

### 解析逻辑

```python
# Pattern 1: JSON block with ```json wrapper
json_pattern1 = r'```json\s*\n\s*(\{[^}]*"tool"\s*:\s*"([^"]+)"[^}]*\})\s*\n\s*```'

# Pattern 2: Plain JSON without wrapper
json_pattern2 = r'\{[^}]*"tool"\s*:\s*"([^"]+)"[^}]*\}'
```

## 测试验证

### 测试步骤

1. **重启后端服务**:
```bash
cd backend
uvicorn api_gateway.main:app --reload --host 0.0.0.0 --port 8000
```

2. **测试单轮工具**:
```
用户: 计算 212312123 * 13
预期: 正常返回计算结果
```

3. **测试多轮工具**:
```
用户: 查询北京的天气
预期: 
- Round 1: 调用 read_skill
- Round 2: 调用 code_execution 执行脚本
- Round 3: 返回真实天气数据
```

### 查看日志

```bash
# 查看工具调用
tail -f backend/backend.log | grep "TOOL-LOOP"

# 查看 LLM 输出
tail -f backend/backend.log | grep "Round.*LLM output"

# 查看工具执行
tail -f backend/backend.log | grep "Executing tool\|Tool executed"
```

## 常见问题

### Q1: 为什么之前 code_execution 被过滤掉?

**原因**: 可能是早期设计时认为 `code_execution` 是"内部工具"，不需要在提示词中显示。但这导致 LLM 无法使用它。

### Q2: 修复后会影响其他功能吗?

**答案**: 不会。只是让 LLM 能看到 `code_execution` 工具的描述和使用方法，不影响其他工具的使用。

### Q3: 如果 LLM 仍然不调用 code_execution 怎么办?

**可能原因**:
1. LLM 模型能力不足，无法理解多轮工具调用
2. 提示词不够清晰
3. 技能文档中的说明不够明确

**解决方法**:
1. 在技能文档中更明确地说明需要使用 `code_execution`
2. 在 `read_skill` 结果后的提示词中更强调使用 `code_execution`
3. 考虑使用更强大的 LLM 模型

### Q4: 为什么不直接在 read_skill 中执行脚本?

**原因**: 
1. **安全性**: 代码执行需要沙箱隔离
2. **灵活性**: LLM 可以根据用户需求调整执行参数
3. **可观察性**: 每个工具调用都有独立的日志和监控

## 参考

- [Agent Framework](./agent-framework.md)
- [Skill Library](./skill-library.md)
- [Code Execution](./code-execution.md)
- [Virtualization](./virtualization.md)
