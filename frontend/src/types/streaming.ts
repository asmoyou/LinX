/**
 * Streaming Types for Agent Error Recovery
 * 
 * Defines types for streaming messages from agent execution,
 * including error recovery, retry attempts, and multi-round conversations.
 * 
 * References:
 * - Backend: backend/agent_framework/base_agent.py
 * - Documentation: docs/backend/agent-error-recovery.md
 */

/**
 * Streaming message types from agent execution
 */
export type StreamingMessageType =
  | 'start'           // Execution started
  | 'info'            // Information message (e.g., round number)
  | 'thinking'        // Agent thinking/reasoning process
  | 'content'         // Final response content
  | 'done'            // Execution completed
  | 'error'           // Terminal error
  | 'tool_call'       // Tool execution started
  | 'tool_result'     // Tool execution succeeded
  | 'tool_error'      // Tool execution failed
  | 'retry_attempt'   // Error recovery retry
  | 'error_feedback'  // Error feedback to LLM
  | 'stats';          // Performance statistics

/**
 * Base streaming message chunk
 */
export interface StreamingChunk {
  type: StreamingMessageType;
  content: string;
  [key: string]: any;
}

/**
 * Retry attempt message
 */
export interface RetryAttemptChunk extends StreamingChunk {
  type: 'retry_attempt';
  retry_count: number;
  max_retries: number;
  error_type: 'parse_error' | 'execution_error';
}

/**
 * Error feedback message
 */
export interface ErrorFeedbackChunk extends StreamingChunk {
  type: 'error_feedback';
  error_type: string;
  retry_count: number;
  max_retries: number;
  suggestions?: string[];
}

/**
 * Info message (e.g., round number)
 */
export interface InfoChunk extends StreamingChunk {
  type: 'info';
  round_number?: number;
  max_rounds?: number;
}

/**
 * Statistics message
 */
export interface StatsChunk extends StreamingChunk {
  type: 'stats';
  timeToFirstToken: number;
  tokensPerSecond: number;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  totalTime: number;
}

/**
 * Conversation round data
 * Represents a single round of agent execution
 */
export interface ConversationRound {
  roundNumber: number;
  thinking: string;
  content: string;
  statusMessages: StatusMessage[];
  stats?: {
    timeToFirstToken: number;
    tokensPerSecond: number;
    inputTokens: number;
    outputTokens: number;
    totalTokens: number;
    totalTime: number;
  };
  retryAttempts?: RetryAttempt[];
  errorFeedback?: ErrorFeedback[];
}

/**
 * Status message within a round
 */
export interface StatusMessage {
  content: string;
  type: 'start' | 'info' | 'thinking' | 'done' | 'error' | 'tool_call' | 'tool_result' | 'tool_error';
  timestamp: Date;
  duration?: number;
}

/**
 * Retry attempt information
 */
export interface RetryAttempt {
  retryCount: number;
  maxRetries: number;
  errorType: 'parse_error' | 'execution_error';
  message: string;
  timestamp: Date;
}

/**
 * Error feedback information
 */
export interface ErrorFeedback {
  errorType: string;
  retryCount: number;
  maxRetries: number;
  message: string;
  suggestions?: string[];
  timestamp: Date;
}

/**
 * Agent message with multi-round support
 */
export interface AgentMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  rounds?: ConversationRound[];  // Multiple rounds for multi-turn execution
  attachments?: AttachedFile[];
}

/**
 * Attached file information
 */
export interface AttachedFile {
  id: string;
  file: File;
  preview?: string;
  type: 'image' | 'document' | 'other';
}
