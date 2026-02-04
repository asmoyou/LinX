/**
 * Retry Indicator Component
 * 
 * Displays retry attempt information during agent error recovery.
 * Shows retry count, error type, and progress indicator.
 * 
 * References:
 * - Backend: backend/agent_framework/base_agent.py
 * - Documentation: docs/backend/agent-error-recovery.md
 */

import React from 'react';
import { RefreshCw, AlertTriangle } from 'lucide-react';
import type { RetryAttempt } from '@/types/streaming';

interface RetryIndicatorProps {
  retry: RetryAttempt;
  isActive?: boolean;
}

export const RetryIndicator: React.FC<RetryIndicatorProps> = ({ retry, isActive = false }) => {
  const errorTypeLabel = retry.errorType === 'parse_error' ? 'JSON解析错误' : '工具执行错误';
  const progress = (retry.retryCount / retry.maxRetries) * 100;

  return (
    <div className={`rounded-lg px-3 py-2 border ${
      isActive 
        ? 'bg-amber-50 dark:bg-amber-900/20 border-amber-300 dark:border-amber-700' 
        : 'bg-zinc-50 dark:bg-zinc-800/50 border-zinc-200 dark:border-zinc-700'
    }`}>
      <div className="flex items-center gap-2">
        <div className={`p-1.5 rounded-lg ${
          isActive 
            ? 'bg-amber-100 dark:bg-amber-900/40' 
            : 'bg-zinc-100 dark:bg-zinc-800'
        }`}>
          {isActive ? (
            <RefreshCw className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400 animate-spin" />
          ) : (
            <AlertTriangle className="w-3.5 h-3.5 text-zinc-500 dark:text-zinc-400" />
          )}
        </div>
        
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2 mb-1">
            <span className={`text-xs font-semibold ${
              isActive 
                ? 'text-amber-700 dark:text-amber-300' 
                : 'text-zinc-700 dark:text-zinc-300'
            }`}>
              {isActive ? '🔄 正在重试...' : '已重试'}
            </span>
            <span className="text-[10px] font-mono text-zinc-500 dark:text-zinc-400">
              {retry.retryCount}/{retry.maxRetries}
            </span>
          </div>
          
          {/* Progress bar */}
          <div className="w-full h-1 bg-zinc-200 dark:bg-zinc-700 rounded-full overflow-hidden">
            <div 
              className={`h-full transition-all duration-300 ${
                isActive 
                  ? 'bg-amber-500 dark:bg-amber-400' 
                  : 'bg-zinc-400 dark:bg-zinc-500'
              }`}
              style={{ width: `${progress}%` }}
            />
          </div>
          
          <div className="flex items-center justify-between mt-1">
            <span className="text-[10px] text-zinc-600 dark:text-zinc-400">
              {errorTypeLabel}
            </span>
            <span className="text-[10px] text-zinc-500 dark:text-zinc-400">
              {retry.timestamp.toLocaleTimeString()}
            </span>
          </div>
        </div>
      </div>
      
      {retry.message && (
        <p className="text-xs text-zinc-600 dark:text-zinc-400 mt-2 pl-8">
          {retry.message}
        </p>
      )}
    </div>
  );
};
