# Agent Error Recovery System

Agent error recovery system enables automatic detection and correction of tool call errors through multi-turn conversations with the LLM.

## Overview

When an agent encounters errors (JSON parsing errors, tool execution failures, timeouts), the system automatically:
1. Detects the error
2. Generates helpful feedback for the LLM
3. Allows the LLM to retry with corrections
4. Tracks retry attempts and enforces limits
5. Provides clear progress indicators to users

## Features

- **Automatic JSON parsing error detection**: Catches malformed tool calls
- **Tool execution error handling**: Handles timeouts and exceptions
- **Multi-turn retry mechanism**: Up to 3 retries per error type
- **Concise feedback prompts**: Optimized to reduce LLM thinking time
- **Progress indicators**: Real-time status updates to frontend
- **Configurable limits**: Retry counts and timeouts via environment variables

## Configuration

Environment variables (optional, with defaults):

```bash
# Maximum retry attempts for parsing errors (default: 3)
export AGENT_MAX_PARSE_RETRIES=3

# Maximum retry attempts for execution errors (default: 3)
export AGENT_MAX_EXECUTION_RETRIES=3

# Tool execution timeout in seconds (default: 30.0)
export AGENT_TOOL_TIMEOUT=30.0

# Enable/disable error recovery (default: true)
export AGENT_ENABLE_ERROR_RECOVERY=true
```

## Streaming Message Types

The error recovery system sends these message types to the frontend:

### 1. `retry_attempt`
Indicates a retry is happening:
```python
("🔄 **检测到错误，正在重试** (第 1/3 次)\n", "retry_attempt")
```

### 2. `error_feedback`
Detailed error feedback for display:
```python
(feedback.to_prompt(), "error_feedback")
```

### 3. `info`
General information messages:
```python
("💭 **第 2 轮对话**\n", "info")
```

### 4. `error`
Terminal error messages:
```python
("⛔ 工具调用格式错误次数过多，无法继续。\n", "error")
```

## Frontend Integration

### TypeScript Types

```typescript
// Add to frontend/src/types/streaming.ts
export type StreamMessageType = 
  | 'content'
  | 'thinking'
  | 'tool_call'
  | 'tool_result'
  | 'tool_error'
  | 'retry_attempt'    // NEW
  | 'error_feedback'   // NEW
  | 'info'             // NEW
  | 'error';

export interface StreamMessage {
  content: string;
  type: StreamMessageType;
}
```

### Message Handler

```typescript
// In your WebSocket message handler
function handleStreamMessage(message: StreamMessage) {
  switch (message.type) {
    case 'retry_attempt':
      // Show retry indicator (e.g., spinner with retry count)
      showRetryIndicator(message.content);
      break;
      
    case 'error_feedback':
      // Display error feedback (can be collapsible)
      showErrorFeedback(message.content);
      break;
      
    case 'info':
      // Show info message (e.g., round number)
      showInfoMessage(message.content);
      break;
      
    case 'error':
      // Show terminal error
      showError(message.content);
      break;
      
    // ... existing cases
  }
}
```

### UI Components (Suggested)

```tsx
// RetryIndicator.tsx
function RetryIndicator({ message }: { message: string }) {
  return (
    <div className="retry-indicator">
      <Spinner />
      <span>{message}</span>
    </div>
  );
}

// ErrorFeedback.tsx
function ErrorFeedback({ content }: { content: string }) {
  const [collapsed, setCollapsed] = useState(false);
  
  return (
    <div className="error-feedback">
      <button onClick={() => setCollapsed(!collapsed)}>
        {collapsed ? '展开' : '收起'} 错误详情
      </button>
      {!collapsed && <pre>{content}</pre>}
    </div>
  );
}
```

## Error Recovery Flow

```
User Query
    ↓
Round 1: LLM generates tool call
    ↓
Parse tool call → Error detected!
    ↓
Send retry_attempt message to frontend
    ↓
Generate error_feedback
    ↓
Round 2: LLM receives feedback and retries
    ↓
Parse tool call → Success!
    ↓
Execute tool → Get result
    ↓
Round 3: LLM generates final answer
    ↓
Done
```

## Logging

All error recovery events are logged with structured data:

```python
logger.warning(
    "[RECOVERY] Found 1 parse errors",
    extra={"agent_id": str(agent_id)}
)
```

Log prefixes:
- `[RECOVERY]`: Error recovery events
- `[TOOL-LOOP]`: Legacy implementation events

## Metrics

Error recovery statistics are returned in the response:

```python
{
  "success": True,
  "state": ConversationState(...),
  "error_recovery_stats": {
    "total_errors": 2,
    "recovered_errors": 2,
    "retry_attempts": 3
  }
}
```

## Testing

Run standalone tests:

```bash
cd backend
python3 test_error_recovery_standalone.py
```

Expected output:
- All data structures work correctly
- Error feedback is concise (< 600 chars)
- Retry logic functions properly

## Troubleshooting

### Issue: LLM takes too long to respond after error

**Solution**: The optimized feedback prompts should reduce thinking time. If still slow:
1. Check LLM model performance
2. Consider reducing `max_parse_retries` to 2
3. Add timeout for LLM streaming (future enhancement)

### Issue: Frontend doesn't show retry indicators

**Solution**: Ensure frontend handles new message types:
- `retry_attempt`
- `error_feedback`
- `info`

### Issue: Too many retries

**Solution**: Adjust environment variables:
```bash
export AGENT_MAX_PARSE_RETRIES=2
export AGENT_MAX_EXECUTION_RETRIES=2
```

## References

- Spec: `.kiro/specs/agent-error-recovery/`
- Code: `backend/agent_framework/base_agent.py`
- Tests: `backend/test_error_recovery_standalone.py`
