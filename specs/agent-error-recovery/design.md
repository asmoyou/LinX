# Agent Error Recovery and Self-Correction - Design

## Related Specs

- Runtime profile unification across adapters: `../agent-test-chat-runtime-strategy/`

## 1. Overview

This document details the technical design for implementing robust error recovery and self-correction in the agent execution loop. The design enables agents to autonomously recover from tool call format errors and execution failures through multi-turn feedback loops.

## 2. Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent Execution Loop                      │
│                                                              │
│  ┌────────────┐    ┌──────────────┐    ┌────────────────┐ │
│  │   Round    │───▶│ Tool Call    │───▶│  Tool          │ │
│  │  Manager   │    │   Parser     │    │  Executor      │ │
│  └────────────┘    └──────────────┘    └────────────────┘ │
│        │                  │                     │           │
│        │                  ▼                     ▼           │
│        │           ┌──────────────┐    ┌────────────────┐ │
│        └──────────▶│   Error      │◀───│  Execution     │ │
│                    │  Detector    │    │   Monitor      │ │
│                    └──────────────┘    └────────────────┘ │
│                           │                                │
│                           ▼                                │
│                    ┌──────────────┐                       │
│                    │   Feedback   │                       │
│                    │  Generator   │                       │
│                    └──────────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Component Responsibilities

**Round Manager**:
- Tracks conversation rounds (current/max)
- Manages conversation state
- Enforces round limits
- Decides when to terminate

**Tool Call Parser**:
- Extracts tool calls from LLM output
- Validates JSON format
- Detects parsing errors
- Returns structured tool call data or errors

**Error Detector**:
- Identifies error types (parse, execution, timeout)
- Classifies error severity
- Determines if error is recoverable
- Tracks retry counts per tool

**Feedback Generator**:
- Creates structured error messages for LLM
- Includes error context and examples
- Formats retry prompts
- Adjusts message based on retry count

**Tool Executor**:
- Executes validated tool calls
- Catches execution exceptions
- Enforces timeouts
- Returns results or errors

**Execution Monitor**:
- Tracks tool execution metrics
- Logs all attempts and results
- Provides observability data
- Triggers alerts on patterns


## 3. Data Structures

### 3.1 Conversation State

```python
@dataclass
class ConversationState:
    """Tracks state of multi-round conversation."""
    
    round_number: int = 0
    max_rounds: int = 20
    tool_calls_made: List[ToolCallRecord] = field(default_factory=list)
    retry_counts: Dict[str, int] = field(default_factory=dict)  # tool_name -> count
    errors: List[ErrorRecord] = field(default_factory=list)
    is_terminated: bool = False
    termination_reason: Optional[str] = None
```

### 3.2 Tool Call Record

```python
@dataclass
class ToolCallRecord:
    """Records a single tool call attempt."""
    
    round_number: int
    tool_name: str
    arguments: Dict[str, Any]
    status: str  # "success", "parse_error", "execution_error", "timeout"
    result: Optional[Any] = None
    error: Optional[str] = None
    retry_number: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
```

### 3.3 Error Record

```python
@dataclass
class ErrorRecord:
    """Records an error occurrence."""
    
    round_number: int
    error_type: str  # "parse_error", "execution_error", "timeout", "validation_error"
    error_message: str
    tool_name: Optional[str] = None
    malformed_input: Optional[str] = None
    is_recoverable: bool = True
    retry_count: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
```

### 3.4 Error Feedback

```python
@dataclass
class ErrorFeedback:
    """Structured feedback for LLM after error."""
    
    error_type: str
    error_message: str
    malformed_input: Optional[str]
    expected_format: str
    retry_count: int
    max_retries: int
    suggestions: List[str]
    
    def to_prompt(self) -> str:
        """Convert to human-readable prompt for LLM."""
        pass
```


## 4. Core Algorithms

### 4.1 Main Execution Loop with Error Recovery

```python
async def execute_task_with_recovery(
    self,
    task_description: str,
    context: Optional[Dict[str, Any]] = None,
    stream_callback: Optional[callable] = None
) -> Dict[str, Any]:
    """Execute task with error recovery."""
    
    # Initialize conversation state
    state = ConversationState(max_rounds=self.config.max_iterations)
    messages = [
        SystemMessage(content=self._create_system_prompt()),
        HumanMessage(content=task_description)
    ]
    
    # Main conversation loop
    while state.round_number < state.max_rounds and not state.is_terminated:
        state.round_number += 1
        
        # 1. Get LLM response
        llm_output = await self._get_llm_response(messages, stream_callback)
        
        # 2. Parse tool calls
        tool_calls, parse_errors = self._parse_tool_calls(llm_output)
        
        # 3. Handle parse errors
        if parse_errors:
            feedback = self._handle_parse_errors(parse_errors, state)
            if feedback:
                messages.append(AIMessage(content=llm_output))
                messages.append(HumanMessage(content=feedback.to_prompt()))
                continue  # Retry in next round
            else:
                # Max retries exceeded, terminate
                state.is_terminated = True
                state.termination_reason = "max_parse_retries_exceeded"
                break
        
        # 4. No tool calls = final answer
        if not tool_calls:
            state.is_terminated = True
            state.termination_reason = "final_answer_provided"
            break
        
        # 5. Execute tool calls
        tool_results = await self._execute_tools_with_recovery(
            tool_calls, state, stream_callback
        )
        
        # 6. Check if all tools failed
        if all(r.status == "error" for r in tool_results):
            feedback = self._handle_execution_failures(tool_results, state)
            if feedback:
                messages.append(AIMessage(content=llm_output))
                messages.append(HumanMessage(content=feedback.to_prompt()))
                continue  # Retry in next round
            else:
                # Max retries exceeded, terminate
                state.is_terminated = True
                state.termination_reason = "max_execution_retries_exceeded"
                break
        
        # 7. Add results to conversation and continue
        messages.append(AIMessage(content=llm_output))
        messages.append(HumanMessage(content=self._format_tool_results(tool_results)))
    
    # Handle max rounds reached
    if state.round_number >= state.max_rounds:
        state.is_terminated = True
        state.termination_reason = "max_rounds_reached"
    
    return {
        "success": state.termination_reason in ["final_answer_provided"],
        "output": llm_output if state.is_terminated else "Incomplete",
        "state": state,
        "messages": messages
    }
```


### 4.2 Tool Call Parsing with Error Detection

```python
def _parse_tool_calls(self, llm_output: str) -> Tuple[List[ToolCall], List[ParseError]]:
    """Parse tool calls from LLM output, collecting all errors."""
    
    tool_calls = []
    parse_errors = []
    
    # Pattern 1: JSON with markdown wrapper
    pattern1 = r'```json\s*\n\s*(\{[^}]*"tool"\s*:\s*"([^"]+)"[^}]*\})\s*\n\s*```'
    matches1 = re.findall(pattern1, llm_output, re.DOTALL)
    
    # Pattern 2: Plain JSON
    pattern2 = r'\{[^}]*"tool"\s*:\s*"([^"]+)"[^}]*\}'
    matches2 = re.findall(pattern2, llm_output, re.DOTALL)
    
    # Combine matches
    json_blocks = [m[0] for m in matches1] if matches1 else []
    if not json_blocks and matches2:
        # Extract full JSON blocks for pattern 2
        for tool_name in matches2:
            match = re.search(
                r'\{[^}]*"tool"\s*:\s*"' + re.escape(tool_name) + r'"[^}]*\}',
                llm_output
            )
            if match:
                json_blocks.append(match.group(0))
    
    # Parse each JSON block
    for json_str in json_blocks:
        try:
            tool_data = json.loads(json_str)
            
            # Validate required fields
            if "tool" not in tool_data:
                parse_errors.append(ParseError(
                    error_type="missing_field",
                    message="Missing required field 'tool'",
                    malformed_input=json_str
                ))
                continue
            
            tool_name = tool_data["tool"]
            
            # Check if tool exists
            if tool_name not in self.tools_by_name:
                parse_errors.append(ParseError(
                    error_type="unknown_tool",
                    message=f"Tool '{tool_name}' not found",
                    malformed_input=json_str
                ))
                continue
            
            # Extract arguments
            args = {k: v for k, v in tool_data.items() if k != "tool"}
            
            tool_calls.append(ToolCall(
                tool_name=tool_name,
                arguments=args,
                raw_json=json_str
            ))
            
        except json.JSONDecodeError as e:
            parse_errors.append(ParseError(
                error_type="json_decode_error",
                message=f"Failed to parse JSON: {str(e)}",
                malformed_input=json_str,
                details={"line": e.lineno, "column": e.colno}
            ))
        except Exception as e:
            parse_errors.append(ParseError(
                error_type="unknown_error",
                message=f"Unexpected error: {str(e)}",
                malformed_input=json_str
            ))
    
    return tool_calls, parse_errors
```


### 4.3 Error Feedback Generation

```python
def _handle_parse_errors(
    self,
    parse_errors: List[ParseError],
    state: ConversationState
) -> Optional[ErrorFeedback]:
    """Generate feedback for parse errors."""
    
    # Get the first error (focus on one at a time)
    error = parse_errors[0]
    
    # Check retry count
    retry_key = f"parse_error_{error.error_type}"
    retry_count = state.retry_counts.get(retry_key, 0)
    
    if retry_count >= 3:  # Max retries
        logger.warning(f"Max parse retries exceeded for {error.error_type}")
        return None
    
    # Increment retry count
    state.retry_counts[retry_key] = retry_count + 1
    
    # Record error
    state.errors.append(ErrorRecord(
        round_number=state.round_number,
        error_type=error.error_type,
        error_message=error.message,
        malformed_input=error.malformed_input,
        is_recoverable=True,
        retry_count=retry_count + 1
    ))
    
    # Generate feedback based on error type
    if error.error_type == "json_decode_error":
        return ErrorFeedback(
            error_type="JSON Format Error",
            error_message=error.message,
            malformed_input=error.malformed_input,
            expected_format='{"tool": "tool_name", "arg1": "value1"}',
            retry_count=retry_count + 1,
            max_retries=3,
            suggestions=[
                "Check for unterminated strings (missing closing quotes)",
                "Ensure all quotes are properly escaped",
                "Verify JSON structure is valid",
                "Use double quotes for strings, not single quotes"
            ]
        )
    
    elif error.error_type == "missing_field":
        return ErrorFeedback(
            error_type="Missing Required Field",
            error_message=error.message,
            malformed_input=error.malformed_input,
            expected_format='{"tool": "tool_name", "arg1": "value1"}',
            retry_count=retry_count + 1,
            max_retries=3,
            suggestions=[
                "Every tool call must have a 'tool' field",
                "The 'tool' field specifies which tool to use"
            ]
        )
    
    elif error.error_type == "unknown_tool":
        available_tools = ", ".join(self.tools_by_name.keys())
        return ErrorFeedback(
            error_type="Unknown Tool",
            error_message=error.message,
            malformed_input=error.malformed_input,
            expected_format=f"Available tools: {available_tools}",
            retry_count=retry_count + 1,
            max_retries=3,
            suggestions=[
                f"Use one of these tools: {available_tools}",
                "Check the tool name spelling"
            ]
        )
    
    else:
        return ErrorFeedback(
            error_type="Tool Call Error",
            error_message=error.message,
            malformed_input=error.malformed_input,
            expected_format='{"tool": "tool_name", "arg1": "value1"}',
            retry_count=retry_count + 1,
            max_retries=3,
            suggestions=["Review the tool call format and try again"]
        )
```


### 4.4 Error Feedback Formatting

```python
class ErrorFeedback:
    """Structured feedback for LLM after error."""
    
    def to_prompt(self) -> str:
        """Convert to human-readable prompt for LLM."""
        
        prompt = f"⚠️ **{self.error_type}** (Attempt {self.retry_count}/{self.max_retries})\n\n"
        
        prompt += f"**Error**: {self.error_message}\n\n"
        
        if self.malformed_input:
            prompt += f"**Your input**:\n```\n{self.malformed_input}\n```\n\n"
        
        prompt += f"**Expected format**:\n```json\n{self.expected_format}\n```\n\n"
        
        if self.suggestions:
            prompt += "**Suggestions**:\n"
            for suggestion in self.suggestions:
                prompt += f"- {suggestion}\n"
            prompt += "\n"
        
        if self.retry_count < self.max_retries:
            prompt += "Please try again with the correct format.\n"
        else:
            prompt += "⛔ Maximum retry attempts reached. Please provide a final answer without using tools.\n"
        
        return prompt
```

### 4.5 Tool Execution with Recovery

```python
async def _execute_tools_with_recovery(
    self,
    tool_calls: List[ToolCall],
    state: ConversationState,
    stream_callback: Optional[callable] = None
) -> List[ToolResult]:
    """Execute tools with error handling and recovery."""
    
    results = []
    
    for tool_call in tool_calls:
        tool_name = tool_call.tool_name
        tool = self.tools_by_name[tool_name]
        
        # Check retry count for this specific tool
        retry_key = f"tool_{tool_name}"
        retry_count = state.retry_counts.get(retry_key, 0)
        
        try:
            # Send "calling tool" message
            if stream_callback:
                stream_callback((
                    f"\n\n🔧 **调用工具: {tool_name}**\n参数: {tool_call.arguments}\n",
                    "tool_call"
                ))
            
            # Execute tool with timeout
            result = await asyncio.wait_for(
                tool.ainvoke(tool_call.arguments),
                timeout=30.0  # 30 second timeout
            )
            
            # Success
            results.append(ToolResult(
                tool_name=tool_name,
                status="success",
                result=result,
                retry_count=retry_count
            ))
            
            # Reset retry count on success
            state.retry_counts[retry_key] = 0
            
            # Send success message
            if stream_callback:
                stream_callback((
                    f"✅ **执行结果**: {result}\n",
                    "tool_result"
                ))
            
            # Record success
            state.tool_calls_made.append(ToolCallRecord(
                round_number=state.round_number,
                tool_name=tool_name,
                arguments=tool_call.arguments,
                status="success",
                result=result,
                retry_number=retry_count
            ))
            
        except asyncio.TimeoutError:
            # Timeout error
            error_msg = f"Tool execution timed out after 30 seconds"
            
            results.append(ToolResult(
                tool_name=tool_name,
                status="error",
                error=error_msg,
                error_type="timeout",
                retry_count=retry_count
            ))
            
            # Increment retry count
            state.retry_counts[retry_key] = retry_count + 1
            
            # Send error message
            if stream_callback:
                stream_callback((
                    f"⏱️ **超时错误**: {error_msg}\n",
                    "tool_error"
                ))
            
            # Record error
            state.tool_calls_made.append(ToolCallRecord(
                round_number=state.round_number,
                tool_name=tool_name,
                arguments=tool_call.arguments,
                status="timeout",
                error=error_msg,
                retry_number=retry_count
            ))
            
        except Exception as e:
            # Execution error
            error_msg = str(e)
            
            results.append(ToolResult(
                tool_name=tool_name,
                status="error",
                error=error_msg,
                error_type="execution_error",
                retry_count=retry_count
            ))
            
            # Increment retry count
            state.retry_counts[retry_key] = retry_count + 1
            
            # Send error message
            if stream_callback:
                stream_callback((
                    f"❌ **执行失败**: {error_msg}\n",
                    "tool_error"
                ))
            
            # Record error
            state.tool_calls_made.append(ToolCallRecord(
                round_number=state.round_number,
                tool_name=tool_name,
                arguments=tool_call.arguments,
                status="execution_error",
                error=error_msg,
                retry_number=retry_count
            ))
    
    return results
```


## 5. Implementation Details

### 5.1 File Modifications

**Primary File**: `backend/agent_framework/base_agent.py`

**Changes Required**:

1. **Add new classes** (at top of file):
   - `ConversationState`
   - `ToolCallRecord`
   - `ErrorRecord`
   - `ErrorFeedback`
   - `ParseError`
   - `ToolCall`
   - `ToolResult`

2. **Refactor `execute_task` method**:
   - Extract current streaming logic into `execute_task_with_recovery`
   - Implement error recovery loop
   - Add conversation state tracking

3. **Add new methods**:
   - `_parse_tool_calls()` - Enhanced parsing with error collection
   - `_handle_parse_errors()` - Generate feedback for parse errors
   - `_handle_execution_failures()` - Generate feedback for execution errors
   - `_execute_tools_with_recovery()` - Tool execution with timeout and error handling
   - `_format_tool_results()` - Format results for LLM

4. **Update existing methods**:
   - `_create_system_prompt()` - Add error recovery instructions
   - Keep backward compatibility for non-streaming mode

### 5.2 Configuration

Add to `AgentConfig`:

```python
@dataclass
class AgentConfig:
    # ... existing fields ...
    
    # Error recovery settings
    max_iterations: int = 20  # Already exists
    max_parse_retries: int = 3
    max_execution_retries: int = 3
    tool_timeout_seconds: float = 30.0
    enable_error_recovery: bool = True  # Feature flag
```

### 5.3 Logging Strategy

**Log Levels**:
- `INFO`: Normal flow (round start, tool calls, success)
- `WARNING`: Recoverable errors (parse errors, execution failures)
- `ERROR`: Unrecoverable errors (max retries exceeded)

**Log Messages**:
```python
# Round tracking
logger.info(f"[RECOVERY] Round {round}/{max_rounds}", extra={...})

# Parse errors
logger.warning(f"[RECOVERY] Parse error: {error_type}", extra={...})

# Execution errors
logger.warning(f"[RECOVERY] Tool execution failed: {tool_name}", extra={...})

# Retry attempts
logger.info(f"[RECOVERY] Retry {retry}/{max_retries} for {tool_name}", extra={...})

# Max retries
logger.error(f"[RECOVERY] Max retries exceeded for {error_type}", extra={...})

# Termination
logger.info(f"[RECOVERY] Conversation terminated: {reason}", extra={...})
```

### 5.4 Metrics Collection

Track the following metrics:

```python
# Error recovery metrics
error_recovery_attempts = Counter(
    'agent_error_recovery_attempts_total',
    'Total error recovery attempts',
    ['agent_id', 'error_type']
)

error_recovery_success = Counter(
    'agent_error_recovery_success_total',
    'Successful error recoveries',
    ['agent_id', 'error_type']
)

conversation_rounds = Histogram(
    'agent_conversation_rounds',
    'Number of rounds per conversation',
    ['agent_id', 'termination_reason']
)

tool_retry_count = Histogram(
    'agent_tool_retry_count',
    'Number of retries per tool call',
    ['agent_id', 'tool_name']
)
```


## 6. Error Recovery Strategies

### 6.1 JSON Parse Errors

**Common Errors**:
1. Unterminated strings: `"code": "print('hello)`
2. Unescaped quotes: `"code": "print("hello")"`
3. Missing commas: `{"tool": "calc" "expr": "1+1"}`
4. Trailing commas: `{"tool": "calc", "expr": "1+1",}`

**Recovery Strategy**:
- Provide specific error location (line, column)
- Show the malformed input
- Provide correct example
- Suggest common fixes
- Allow up to 3 retries

**Example Feedback**:
```
⚠️ **JSON Format Error** (Attempt 1/3)

**Error**: Unterminated string starting at: line 1 column 36

**Your input**:
```
{"tool": "code_execution", "code": "print('hello)"}
```

**Expected format**:
```json
{"tool": "code_execution", "code": "print('hello')"}
```

**Suggestions**:
- Check for unterminated strings (missing closing quotes)
- Ensure all quotes are properly escaped
- In this case, the string 'hello) is missing a closing quote

Please try again with the correct format.
```

### 6.2 Tool Execution Errors

**Common Errors**:
1. Code syntax errors
2. Missing dependencies
3. API timeouts
4. Permission errors

**Recovery Strategy**:
- Provide full error message and stack trace
- Suggest alternative approaches
- Allow LLM to modify parameters
- Allow up to 3 retries per tool

**Example Feedback**:
```
❌ **Tool Execution Error** (Attempt 1/3)

**Tool**: code_execution
**Error**: SyntaxError: invalid syntax (line 2)

**Your code**:
```python
import requests
response = requests.get('https://api.weather.com/v1/current'
print(response.json())
```

**Suggestions**:
- Line 2 is missing a closing parenthesis
- Fix: `response = requests.get('https://api.weather.com/v1/current')`
- You can retry with corrected code

Please fix the error and try again.
```

### 6.3 Timeout Errors

**Recovery Strategy**:
- Inform LLM of timeout
- Suggest breaking into smaller operations
- Suggest alternative tools
- Allow retry with different approach

**Example Feedback**:
```
⏱️ **Timeout Error** (Attempt 1/3)

**Tool**: code_execution
**Error**: Tool execution timed out after 30 seconds

**Suggestions**:
- The operation took too long to complete
- Consider breaking it into smaller steps
- Check if there's an infinite loop
- Try a simpler approach

Please try again with a different approach.
```

### 6.4 Unknown Tool Errors

**Recovery Strategy**:
- List available tools
- Suggest closest match
- Provide tool descriptions
- No retry needed (immediate correction)

**Example Feedback**:
```
⚠️ **Unknown Tool**

**Error**: Tool 'weather_api' not found

**Available tools**:
- read_skill: Read Agent Skill documentation
- code_execution: Execute Python code
- calculator: Perform calculations

**Suggestion**: Did you mean to use 'read_skill' to access the weather-forcast skill?

Please use one of the available tools.
```


## 7. Frontend Integration

### 7.1 Streaming Protocol

**Message Types**:
```typescript
type StreamMessageType = 
  | "thinking"        // LLM thinking process
  | "content"         // LLM content output
  | "tool_call"       // Tool being called
  | "tool_result"     // Tool execution result
  | "tool_error"      // Tool execution error
  | "error_feedback"  // Error recovery feedback
  | "retry_attempt"   // Retry indicator
  | "info";           // General information

interface StreamMessage {
  type: StreamMessageType;
  content: string;
  metadata?: {
    round?: number;
    retry_count?: number;
    max_retries?: number;
    tool_name?: string;
    error_type?: string;
  };
}
```

**Example Stream Sequence**:
```
1. {type: "thinking", content: "分析用户请求..."}
2. {type: "content", content: "我需要查询天气信息"}
3. {type: "tool_call", content: "调用工具: read_skill", metadata: {tool_name: "read_skill"}}
4. {type: "tool_result", content: "技能文档已读取"}
5. {type: "tool_call", content: "调用工具: code_execution", metadata: {tool_name: "code_execution"}}
6. {type: "tool_error", content: "JSON格式错误", metadata: {error_type: "parse_error"}}
7. {type: "error_feedback", content: "⚠️ JSON Format Error (Attempt 1/3)..."}
8. {type: "retry_attempt", content: "正在重试...", metadata: {retry_count: 1, max_retries: 3}}
9. {type: "tool_call", content: "调用工具: code_execution (重试)", metadata: {tool_name: "code_execution", retry_count: 1}}
10. {type: "tool_result", content: "执行成功: 福州今天晴天..."}
11. {type: "content", content: "根据查询结果，福州今天..."}
```

### 7.2 UI Components

**Retry Indicator**:
```tsx
<RetryIndicator 
  retryCount={1} 
  maxRetries={3}
  errorType="JSON Format Error"
/>
```

**Error Message Display**:
```tsx
<ErrorMessage
  type="parse_error"
  message="Unterminated string"
  suggestions={["Check quotes", "Escape special characters"]}
  canRetry={true}
/>
```

**Progress Indicator**:
```tsx
<ConversationProgress
  currentRound={5}
  maxRounds={20}
  status="recovering"
/>
```

### 7.3 User Controls

**Interrupt Button**:
- Allow user to stop long-running conversations
- Send interrupt signal to backend
- Gracefully terminate current round

**Retry Override**:
- Allow user to manually trigger retry
- Provide input field for corrected tool call
- Bypass automatic retry logic

## 8. Testing Strategy

### 8.1 Unit Tests

**Test Cases**:

1. **Parse Error Detection**:
   - Test various malformed JSON formats
   - Verify error messages are accurate
   - Check retry count tracking

2. **Error Feedback Generation**:
   - Test feedback for each error type
   - Verify suggestions are helpful
   - Check retry limit enforcement

3. **Tool Execution Recovery**:
   - Test timeout handling
   - Test exception catching
   - Verify retry logic

4. **Conversation State Management**:
   - Test round counting
   - Test termination conditions
   - Verify state persistence

**Example Test**:
```python
def test_parse_error_recovery():
    """Test that parse errors trigger retry with feedback."""
    agent = create_test_agent()
    
    # Malformed JSON
    llm_output = '{"tool": "calc", "expr": "1+1"'  # Missing closing brace
    
    tool_calls, errors = agent._parse_tool_calls(llm_output)
    
    assert len(tool_calls) == 0
    assert len(errors) == 1
    assert errors[0].error_type == "json_decode_error"
    
    # Generate feedback
    state = ConversationState()
    feedback = agent._handle_parse_errors(errors, state)
    
    assert feedback is not None
    assert feedback.retry_count == 1
    assert "Unterminated" in feedback.error_message
    assert len(feedback.suggestions) > 0
```

### 8.2 Integration Tests

**Test Scenarios**:

1. **End-to-End Recovery**:
   - Simulate full conversation with errors
   - Verify recovery happens automatically
   - Check final result is correct

2. **Multi-Round Conversation**:
   - Test complex tasks requiring multiple rounds
   - Verify state is maintained across rounds
   - Check termination conditions

3. **Streaming Integration**:
   - Test error messages are streamed correctly
   - Verify UI receives all message types
   - Check timing and ordering

**Example Test**:
```python
@pytest.mark.asyncio
async def test_end_to_end_recovery():
    """Test full conversation with error recovery."""
    agent = create_test_agent()
    
    # Mock LLM to return malformed JSON first, then correct
    mock_llm = MockLLM([
        '{"tool": "calc", "expr": "1+1"',  # Malformed
        '{"tool": "calc", "expr": "1+1"}',  # Correct
        'The result is 2'  # Final answer
    ])
    agent.llm = mock_llm
    
    result = await agent.execute_task("Calculate 1+1")
    
    assert result["success"] is True
    assert "2" in result["output"]
    assert len(result["state"].errors) == 1
    assert result["state"].round_number == 3
```

### 8.3 Property-Based Tests

**Properties to Test**:

1. **Retry Limits Always Enforced**:
   - No matter what errors occur, retry count never exceeds limit
   - Conversation always terminates eventually

2. **State Consistency**:
   - Round number always increases
   - Retry counts are accurate
   - Error records match actual errors

3. **No Infinite Loops**:
   - Conversation always terminates within max rounds
   - No circular error patterns

**Example Test**:
```python
from hypothesis import given, strategies as st

@given(
    malformed_jsons=st.lists(st.text(), min_size=1, max_size=10),
    max_retries=st.integers(min_value=1, max_value=5)
)
def test_retry_limit_always_enforced(malformed_jsons, max_retries):
    """Property: Retry limit is always enforced."""
    agent = create_test_agent()
    agent.config.max_parse_retries = max_retries
    
    state = ConversationState()
    
    for json_str in malformed_jsons:
        errors = [ParseError("test", "test", json_str)]
        feedback = agent._handle_parse_errors(errors, state)
        
        if feedback:
            assert feedback.retry_count <= max_retries
        else:
            # No feedback means max retries exceeded
            assert state.retry_counts.get("parse_error_test", 0) >= max_retries
```


## 9. Performance Considerations

### 9.1 Overhead Analysis

**Per-Round Overhead**:
- Error detection: ~5ms (regex + JSON parsing)
- State tracking: ~1ms (dict operations)
- Feedback generation: ~2ms (string formatting)
- **Total**: ~8ms per round (acceptable)

**Memory Usage**:
- ConversationState: ~1KB per conversation
- Error records: ~500 bytes per error
- Tool call records: ~1KB per tool call
- **Total**: ~5-10KB per conversation (negligible)

**LLM Token Overhead**:
- Error feedback: ~100-200 tokens per error
- System prompt additions: ~50 tokens
- **Impact**: Minimal, only on error paths

### 9.2 Optimization Strategies

**1. Early Termination**:
- Detect final answers quickly
- Skip parsing when no tool call patterns found
- Cache regex compilation

**2. Lazy Evaluation**:
- Only generate feedback when needed
- Defer expensive operations until required
- Stream results as they become available

**3. Resource Limits**:
- Hard timeout on tool execution (30s)
- Maximum conversation rounds (20)
- Maximum retry attempts (3)
- Prevent resource exhaustion

### 9.3 Scalability

**Concurrent Conversations**:
- Each conversation has independent state
- No shared mutable state between agents
- Thread-safe by design

**Load Testing Targets**:
- 100 concurrent conversations
- 1000 conversations per hour
- < 100ms overhead per round
- < 1% memory increase

## 10. Security Considerations

### 10.1 Input Validation

**Malicious JSON**:
- Limit JSON size (max 10KB per tool call)
- Timeout JSON parsing (max 100ms)
- Sanitize error messages (no code injection)

**Code Execution**:
- Already sandboxed in virtualization layer
- No additional risks from error recovery
- Error messages don't expose system internals

### 10.2 Information Disclosure

**Error Messages**:
- Don't expose file paths
- Don't expose API keys or secrets
- Don't expose internal implementation details
- Sanitize stack traces

**Logging**:
- Redact sensitive data in logs
- Don't log full tool arguments (may contain secrets)
- Use structured logging for security auditing

### 10.3 Denial of Service

**Protection Mechanisms**:
- Hard limits on retry counts
- Hard limits on conversation rounds
- Timeout on tool execution
- Rate limiting at API gateway level

**Resource Exhaustion**:
- Monitor memory usage per conversation
- Kill conversations exceeding limits
- Alert on suspicious patterns

## 11. Backward Compatibility

### 11.1 Feature Flag

**Configuration**:
```python
# Enable/disable error recovery
enable_error_recovery: bool = True  # Default: enabled
```

**Behavior**:
- When disabled: Falls back to current behavior (immediate termination)
- When enabled: Uses new error recovery logic
- Allows gradual rollout and A/B testing

### 11.2 API Compatibility

**No Breaking Changes**:
- `execute_task()` signature unchanged
- Return value structure unchanged
- Streaming protocol extended (backward compatible)

**New Fields** (optional):
```python
{
    "success": bool,
    "output": str,
    "messages": List[Message],
    # New optional fields
    "state": ConversationState,  # Only if error recovery enabled
    "error_recovery_stats": {    # Only if errors occurred
        "total_errors": int,
        "recovered_errors": int,
        "retry_attempts": int
    }
}
```

### 11.3 Migration Path

**Phase 1**: Deploy with feature flag disabled
- Verify no regressions
- Monitor performance

**Phase 2**: Enable for subset of users
- A/B test error recovery
- Collect metrics and feedback

**Phase 3**: Enable for all users
- Monitor error recovery success rate
- Tune retry limits and feedback messages

**Phase 4**: Remove feature flag
- Make error recovery default behavior
- Clean up legacy code paths

## 12. Monitoring and Observability

### 12.1 Key Metrics

**Error Recovery Metrics**:
```python
# Success rate by error type
error_recovery_rate = error_recovery_success / error_recovery_attempts

# Average retry count
avg_retry_count = sum(retry_counts) / len(conversations)

# Conversation completion rate
completion_rate = successful_conversations / total_conversations

# Round distribution
round_histogram = {1: 100, 2: 50, 3: 25, ...}
```

**Alerting Thresholds**:
- Error recovery rate < 70% → Warning
- Error recovery rate < 50% → Critical
- Average retry count > 2.0 → Warning
- Completion rate < 85% → Warning

### 12.2 Dashboards

**Error Recovery Dashboard**:
- Error recovery success rate (by type)
- Retry count distribution
- Conversation round distribution
- Top error types
- Recovery time trends

**Agent Performance Dashboard**:
- Conversation completion rate
- Average rounds per conversation
- Tool execution success rate
- Timeout frequency
- Error frequency by agent type

### 12.3 Logging

**Structured Logs**:
```json
{
  "timestamp": "2026-02-03T10:00:00Z",
  "level": "WARNING",
  "component": "agent_framework.base_agent",
  "message": "[RECOVERY] Parse error detected",
  "agent_id": "uuid",
  "round_number": 2,
  "error_type": "json_decode_error",
  "retry_count": 1,
  "max_retries": 3,
  "malformed_input": "{\"tool\": \"calc\"...",
  "correlation_id": "req-123"
}
```

**Log Aggregation**:
- Centralize logs in ELK/Loki
- Create alerts on error patterns
- Build dashboards for visualization

## 13. Future Enhancements

### 13.1 Short-Term (Next Sprint)

1. **Intelligent Retry Strategies**:
   - Exponential backoff for transient errors
   - Different retry limits per error type
   - Adaptive retry based on error patterns

2. **Enhanced Feedback**:
   - Include code snippets with syntax highlighting
   - Provide diff view for corrections
   - Add interactive examples

3. **User Feedback Loop**:
   - Allow users to rate error recovery quality
   - Collect feedback on error messages
   - Use feedback to improve prompts

### 13.2 Medium-Term (Next Quarter)

1. **Error Pattern Learning**:
   - Analyze common error patterns
   - Automatically suggest fixes
   - Build knowledge base of solutions

2. **Proactive Error Prevention**:
   - Validate tool calls before execution
   - Suggest corrections before LLM tries
   - Auto-fix common mistakes

3. **Advanced Recovery Strategies**:
   - Automatic fallback to simpler tools
   - Parallel tool execution with fallbacks
   - Context-aware error handling

### 13.3 Long-Term (Future)

1. **ML-Based Recovery**:
   - Train model to predict error likelihood
   - Learn optimal retry strategies
   - Personalize error messages per user

2. **Cross-Conversation Learning**:
   - Share error patterns across agents
   - Build global error knowledge base
   - Improve system-wide recovery rate

3. **Self-Healing Agents**:
   - Agents learn from their mistakes
   - Automatic prompt optimization
   - Continuous improvement loop

## 14. References

### 14.1 Related Specifications

- `.kiro/specs/agent-error-recovery/requirements.md` - User requirements
- `.kiro/specs/agent-error-recovery/tasks.md` - Implementation tasks

### 14.2 Related Documentation

- `docs/backend/agent-skill-execution.md` - Current agent execution flow
- `docs/backend/agent-framework.md` - Agent framework overview
- `docs/backend/error-handling.md` - General error handling patterns

### 14.3 Code References

- `backend/agent_framework/base_agent.py` - Main implementation file
- `backend/agent_framework/tools/` - Tool implementations
- `backend/api_gateway/routers/agents.py` - API and streaming interface

### 14.4 External References

- [OpenClaw Error Recovery](examples-of-reference/openclaw/) - Reference implementation
- [Claude Code](examples-of-reference/claude-code/) - Error handling patterns
- [LangChain Error Handling](https://python.langchain.com/docs/guides/error_handling)

## 15. Appendix

### 15.1 Error Type Taxonomy

```
Error Types:
├── Parse Errors
│   ├── json_decode_error (JSON syntax invalid)
│   ├── missing_field (Required field missing)
│   ├── invalid_type (Field has wrong type)
│   └── unknown_tool (Tool name not found)
├── Execution Errors
│   ├── timeout (Tool execution timeout)
│   ├── exception (Tool raised exception)
│   ├── validation_error (Arguments invalid)
│   └── permission_error (Access denied)
└── System Errors
    ├── resource_exhausted (Out of memory/CPU)
    ├── network_error (Network failure)
    └── internal_error (Unexpected system error)
```

### 15.2 State Machine Diagram

```
┌─────────────┐
│   START     │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  LLM Call   │◀─────────┐
└──────┬──────┘          │
       │                 │
       ▼                 │
┌─────────────┐          │
│ Parse Tools │          │
└──────┬──────┘          │
       │                 │
       ├─────Parse Error─┤
       │                 │
       ▼                 │
┌─────────────┐          │
│Execute Tools│          │
└──────┬──────┘          │
       │                 │
       ├──Exec Error─────┤
       │                 │
       ▼                 │
┌─────────────┐          │
│Check Result │          │
└──────┬──────┘          │
       │                 │
       ├──Need Retry─────┘
       │
       ▼
┌─────────────┐
│  COMPLETE   │
└─────────────┘
```

### 15.3 Example Conversation Flow

**Scenario**: Weather query with JSON error

```
Round 1:
  User: "查询福州天气"
  LLM: [thinking] → calls read_skill("weather-forcast")
  System: Executes read_skill → Returns skill documentation
  
Round 2:
  LLM: [thinking] → calls code_execution with malformed JSON
  System: Parse error detected → Generates feedback
  Feedback: "⚠️ JSON Format Error (Attempt 1/3)..."
  
Round 3:
  LLM: [thinking] → calls code_execution with corrected JSON
  System: Executes code → Returns weather data
  
Round 4:
  LLM: [content] → "福州今天晴天，温度15°C..."
  System: No tool calls → Conversation complete ✅
```

---

**Document Version**: 1.0  
**Last Updated**: 2026-02-03  
**Status**: Ready for Implementation
