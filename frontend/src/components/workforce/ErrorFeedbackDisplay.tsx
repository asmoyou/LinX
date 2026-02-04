/**
 * Error Feedback Display Component
 * 
 * Displays error feedback messages sent to the LLM during error recovery.
 * Shows error type, suggestions, and retry information.
 * Can be collapsed to save space.
 * 
 * References:
 * - Backend: backend/agent_framework/base_agent.py
 * - Documentation: docs/backend/agent-error-recovery.md
 */

import React, { useState } from 'react';
import { AlertCircle, ChevronDown, ChevronUp, Lightbulb } from 'lucide-react';
import type { ErrorFeedback } from '@/types/streaming';

interface ErrorFeedbackDisplayProps {
  feedback: ErrorFeedback;
  defaultCollapsed?: boolean;
}

export const ErrorFeedbackDisplay: React.FC<ErrorFeedbackDisplayProps> = ({ 
  feedback, 
  defaultCollapsed = false 
}) => {
  const [isCollapsed, setIsCollapsed] = useState(defaultCollapsed);

  return (
    <div className="rounded-lg overflow-hidden border border-red-200 dark:border-red-800 bg-red-50/50 dark:bg-red-900/10">
      <button
        onClick={() => setIsCollapsed(!isCollapsed)}
        className="w-full flex items-center justify-between px-3 py-2 bg-red-100/60 dark:bg-red-900/20 hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-red-600 dark:text-red-400" />
          <span className="text-xs font-semibold text-red-700 dark:text-red-300">
            错误反馈 ({feedback.retryCount}/{feedback.maxRetries})
          </span>
          <span className="text-[10px] px-1.5 py-0.5 bg-red-200 dark:bg-red-800 text-red-700 dark:text-red-300 rounded">
            {feedback.errorType}
          </span>
        </div>
        {isCollapsed ? (
          <ChevronDown className="w-4 h-4 text-red-600 dark:text-red-400" />
        ) : (
          <ChevronUp className="w-4 h-4 text-red-600 dark:text-red-400" />
        )}
      </button>
      
      {!isCollapsed && (
        <div className="px-3 py-2 space-y-2">
          {/* Error message */}
          <div className="text-xs text-red-700 dark:text-red-300 leading-relaxed">
            {feedback.message}
          </div>
          
          {/* Suggestions */}
          {feedback.suggestions && feedback.suggestions.length > 0 && (
            <div className="mt-2 pt-2 border-t border-red-200 dark:border-red-800">
              <div className="flex items-center gap-1.5 mb-1.5">
                <Lightbulb className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
                <span className="text-[10px] font-semibold text-red-700 dark:text-red-300">
                  建议修复方法:
                </span>
              </div>
              <ul className="space-y-1 pl-5">
                {feedback.suggestions.map((suggestion, idx) => (
                  <li key={idx} className="text-[10px] text-red-600 dark:text-red-400 list-disc">
                    {suggestion}
                  </li>
                ))}
              </ul>
            </div>
          )}
          
          {/* Timestamp */}
          <div className="text-[10px] text-red-500 dark:text-red-500 text-right">
            {feedback.timestamp.toLocaleTimeString()}
          </div>
        </div>
      )}
    </div>
  );
};
