# Agent Error Recovery and Self-Correction - Requirements

## 1. Overview

Enable agents to autonomously recover from tool call format errors and other execution failures through multi-turn self-correction, inspired by Claude Code and OpenClaw implementations.

## 2. Problem Statement

### Current Behavior (Broken)

When an agent makes a tool call with malformed JSON:

```
Round 1: User asks "查询福州天气"
Round 2: Agent calls read_skill → Success
Round 3: Agent attempts code_execution with malformed JSON → Parse error
Result: Conversation terminates immediately ❌
```

**Error Log**:
```
WARNING: Failed to parse tool JSON: Unterminated string starting at: line 1 column 36
WARNING: [TOOL-LOOP] Tool calls found but none executed
INFO: [TOOL-LOOP] Conversation completed after 2 rounds
```

### Desired Behavior (Fixed)

```
Round 1: User asks "查询福州天气"
Round 2: Agent calls read_skill → Success
Round 3: Agent attempts code_execution with malformed JSON → Parse error
Round 4: System provides error feedback to LLM
Round 5: Agent retries with corrected JSON → Success
Round 6: Agent provides final answer ✅
```

## 3. User Stories

### 3.1 Tool Call Format Error Recovery

**As a** user  
**I want** the agent to automatically fix tool call format errors  
**So that** I get correct results without manual intervention

**Acceptance Criteria**:
- When tool call JSON parsing fails, system provides specific error feedback to LLM
- LLM receives the malformed JSON and the parse error message
- LLM can retry with corrected format
- Maximum 3 retry attempts per tool call
- After 3 failures, system provides helpful error message to user

### 3.2 Tool Execution Error Recovery

**As a** user  
**I want** the agent to handle tool execution failures gracefully  
**So that** the conversation continues productively

**Acceptance Criteria**:
- When tool execution fails (e.g., code error, API timeout), error details are provided to LLM
- LLM can analyze the error and retry with different parameters
- LLM can switch to alternative approaches if tool continues to fail
- System tracks retry count per tool per conversation
- Clear error messages are shown to user when recovery is not possible

### 3.3 Multi-Turn Problem Solving

**As a** user  
**I want** the agent to solve complex problems across multiple rounds  
**So that** I can accomplish tasks that require iterative refinement

**Acceptance Criteria**:
- Agent can execute up to 20 rounds of conversation (configurable)
- Each round can include: thinking, tool calls, error recovery, or final answer
- System provides progress indicators for long-running tasks
- User can interrupt long-running conversations
- Conversation history is preserved for debugging

### 3.4 Graceful Degradation

**As a** user  
**I want** the agent to provide partial results when full execution fails  
**So that** I get some value even when errors occur

**Acceptance Criteria**:
- If tool execution fails after retries, agent explains what went wrong
- Agent provides alternative suggestions or workarounds
- Agent summarizes what was accomplished before the failure
- User receives actionable feedback on how to resolve the issue

## 4. Functional Requirements

### 4.1 Error Detection

**FR-4.1.1**: System shall detect JSON parsing errors in tool calls  
**FR-4.1.2**: System shall detect tool execution errors (exceptions, timeouts)  
**FR-4.1.3**: System shall detect malformed tool call formats (missing fields, wrong types)  
**FR-4.1.4**: System shall track error types and frequencies for monitoring

### 4.2 Error Feedback Loop

**FR-4.2.1**: System shall provide structured error feedback to LLM  
**FR-4.2.2**: Error feedback shall include:
- Original malformed input
- Specific error message
- Expected format example
- Retry count remaining

**FR-4.2.3**: System shall format error feedback as a HumanMessage in conversation history  
**FR-4.2.4**: Error feedback shall be clear and actionable for LLM

### 4.3 Retry Logic

**FR-4.3.1**: System shall allow up to 3 retry attempts per tool call  
**FR-4.3.2**: System shall track retry count per tool per conversation  
**FR-4.3.3**: System shall reset retry count after successful tool execution  
**FR-4.3.4**: System shall provide different error messages based on retry count

### 4.4 Conversation Management

**FR-4.4.1**: System shall support up to 20 conversation rounds (configurable)  
**FR-4.4.2**: System shall track conversation state (round number, tool calls, errors)  
**FR-4.4.3**: System shall provide early termination when:
- LLM provides final answer (no tool calls)
- Maximum rounds reached
- User interrupts
- Unrecoverable error occurs

**FR-4.4.4**: System shall log all conversation rounds for debugging

### 4.5 User Communication

**FR-4.5.1**: System shall stream error recovery attempts to frontend  
**FR-4.5.2**: System shall show retry indicators in UI  
**FR-4.5.3**: System shall provide clear error messages when recovery fails  
**FR-4.5.4**: System shall show progress indicators for multi-round conversations

## 5. Non-Functional Requirements

### 5.1 Performance

**NFR-5.1.1**: Error detection shall add < 10ms overhead per round  
**NFR-5.1.2**: Retry logic shall not cause infinite loops  
**NFR-5.1.3**: System shall timeout individual tool calls after 30 seconds

### 5.2 Reliability

**NFR-5.2.1**: Error recovery shall not crash the agent  
**NFR-5.2.2**: System shall handle all JSON parsing errors gracefully  
**NFR-5.2.3**: System shall prevent retry storms (exponential backoff)

### 5.3 Observability

**NFR-5.3.1**: All error recovery attempts shall be logged  
**NFR-5.3.2**: System shall track error recovery success rate  
**NFR-5.3.3**: System shall provide metrics on:
- Average retry count per conversation
- Error types distribution
- Recovery success rate by error type

### 5.4 Maintainability

**NFR-5.4.1**: Error recovery logic shall be modular and testable  
**NFR-5.4.2**: Error messages shall be configurable  
**NFR-5.4.3**: Retry limits shall be configurable per deployment

## 6. Technical Constraints

### 6.1 LLM Limitations

- Not all LLMs can self-correct effectively
- Some errors may be beyond LLM's ability to fix
- LLM may hallucinate fixes that don't work

### 6.2 System Constraints

- Maximum conversation history size (memory limits)
- LLM API rate limits
- Tool execution timeouts

### 6.3 Compatibility

- Must work with existing tool call format (JSON)
- Must not break existing working tool calls
- Must be backward compatible with current agent implementation

## 7. Success Metrics

### 7.1 Primary Metrics

- **Error Recovery Rate**: % of tool call errors that are successfully recovered
  - Target: > 80% for JSON format errors
  - Target: > 60% for execution errors

- **User Satisfaction**: % of conversations that complete successfully
  - Target: > 90% completion rate

### 7.2 Secondary Metrics

- **Average Retry Count**: Average number of retries per error
  - Target: < 1.5 retries per error

- **Conversation Length**: Average rounds per conversation
  - Target: < 5 rounds for simple tasks
  - Target: < 15 rounds for complex tasks

- **Error Type Distribution**: Track most common error types
  - Use for targeted improvements

## 8. Out of Scope

### 8.1 Not Included in This Spec

- Automatic tool call format correction (system-side)
- Learning from past errors (ML-based)
- User-configurable retry limits (admin only)
- Cross-conversation error pattern analysis

### 8.2 Future Enhancements

- Intelligent retry strategies based on error type
- Automatic fallback to simpler tools
- Error pattern learning and prevention
- User feedback on error recovery quality

## 9. Dependencies

### 9.1 Existing Components

- `backend/agent_framework/base_agent.py` - Main agent execution loop
- `backend/agent_framework/tools/` - Tool implementations
- `backend/api_gateway/routers/agents.py` - Streaming interface

### 9.2 Reference Implementations

- `examples-of-reference/claude-code/` - Error recovery patterns
- `examples-of-reference/openclaw/` - Multi-turn conversation handling

## 10. Risks and Mitigations

### 10.1 Risk: Infinite Retry Loops

**Mitigation**: Hard limit on retry count (3) and conversation rounds (20)

### 10.2 Risk: Poor Error Messages Confuse LLM

**Mitigation**: Test error messages with multiple LLM models, iterate based on results

### 10.3 Risk: Increased Latency

**Mitigation**: Optimize error detection, use async processing, provide progress indicators

### 10.4 Risk: Increased LLM API Costs

**Mitigation**: Track token usage, implement cost limits, optimize error feedback length

## 11. Testing Strategy

### 11.1 Unit Tests

- Test error detection for various JSON malformations
- Test retry logic with different error types
- Test conversation state management

### 11.2 Integration Tests

- Test end-to-end error recovery flows
- Test with real LLM models
- Test streaming error feedback to frontend

### 11.3 Property-Based Tests

- Generate random malformed JSON and verify recovery
- Test retry limits are enforced
- Test conversation termination conditions

### 11.4 Manual Testing

- Test with various LLM models (Ollama, OpenAI, Anthropic)
- Test user experience during error recovery
- Test edge cases (network failures, timeouts)

## 12. Documentation Requirements

- Update `docs/backend/agent-skill-execution.md` with error recovery details
- Create troubleshooting guide for common errors
- Document retry configuration options
- Add examples of error recovery in action

## 13. Acceptance Criteria Summary

This feature is complete when:

1. ✅ Tool call JSON parsing errors trigger retry with feedback (not termination)
2. ✅ Tool execution errors are communicated to LLM for recovery
3. ✅ System enforces retry limits (3 per tool call)
4. ✅ System enforces conversation round limits (20 rounds)
5. ✅ Error recovery attempts are streamed to frontend
6. ✅ All error recovery logic is unit tested
7. ✅ Integration tests pass with real LLM
8. ✅ Documentation is updated
9. ✅ Error recovery success rate > 80% for format errors
10. ✅ No infinite loops or crashes during error recovery
