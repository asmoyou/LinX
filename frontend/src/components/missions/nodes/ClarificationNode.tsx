import React, { memo } from 'react';
import { Handle, Position } from 'reactflow';
import { MessageSquare } from 'lucide-react';

interface ClarificationNodeData {
  messages: Array<{
    sender: 'leader' | 'user';
    text: string;
  }>;
  is_active: boolean;
}

export const ClarificationNode: React.FC<{ data: ClarificationNodeData }> = memo(({ data }) => {
  const lastMessage = data.messages.length > 0 ? data.messages[data.messages.length - 1] : null;

  return (
    <div className={`px-4 py-3 rounded-xl border-2 ${data.is_active ? 'border-amber-400 bg-amber-50 dark:bg-amber-500/5' : 'border-zinc-300 bg-zinc-50 dark:bg-zinc-800/50'} bg-white dark:bg-zinc-900 shadow-md min-w-[200px] max-w-[260px]`}>
      <Handle type="target" position={Position.Top} className="!bg-amber-500 !w-2.5 !h-2.5" />

      <div className="flex items-center gap-2 mb-2">
        <MessageSquare className={`w-4 h-4 ${data.is_active ? 'text-amber-500' : 'text-zinc-400'}`} />
        <span className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">Clarification</span>
        {data.is_active && (
          <span className="text-[9px] font-medium px-1.5 py-0.5 rounded-full bg-amber-400/20 text-amber-600 animate-pulse">
            Active
          </span>
        )}
      </div>

      {lastMessage && (
        <div className={`text-[10px] p-2 rounded-lg ${lastMessage.sender === 'leader' ? 'bg-emerald-50 dark:bg-emerald-500/10' : 'bg-zinc-100 dark:bg-zinc-800'}`}>
          <span className="font-medium text-zinc-600 dark:text-zinc-400">
            {lastMessage.sender === 'leader' ? 'Leader' : 'You'}:
          </span>
          <p className="text-zinc-500 dark:text-zinc-400 mt-0.5 line-clamp-2">{lastMessage.text}</p>
        </div>
      )}

      {data.messages.length > 1 && (
        <p className="text-[9px] text-zinc-400 mt-1">
          {data.messages.length} messages
        </p>
      )}

      <Handle type="source" position={Position.Bottom} className="!bg-amber-500 !w-2.5 !h-2.5" />
    </div>
  );
});

ClarificationNode.displayName = 'ClarificationNode';
