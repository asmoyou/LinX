import React, { memo } from 'react';
import { Handle, Position } from 'reactflow';
import { FileText } from 'lucide-react';

interface RequirementsNodeData {
  requirements_doc?: string;
  status: 'pending' | 'ready' | 'approved';
  is_active?: boolean;
}

export const RequirementsNode: React.FC<{ data: RequirementsNodeData }> = memo(({ data }) => {
  const preview = data.requirements_doc
    ? data.requirements_doc.substring(0, 200) + (data.requirements_doc.length > 200 ? '...' : '')
    : 'Awaiting requirements...';

  const statusColor =
    data.status === 'approved'
      ? 'border-green-400 bg-green-400/5'
      : data.status === 'ready'
        ? 'border-blue-400 bg-blue-400/5'
        : 'border-zinc-300 bg-zinc-50 dark:bg-zinc-800/50';

  return (
    <div
      className={`px-4 py-3 rounded-xl border-2 ${statusColor} ${data.is_active ? 'ring-2 ring-blue-300/70 shadow-blue-200/30' : ''} bg-white dark:bg-zinc-900 shadow-md min-w-[220px] max-w-[280px]`}
    >
      <Handle type="target" position={Position.Top} className="!bg-blue-500 !w-2.5 !h-2.5" />

      <div className="flex items-center gap-2 mb-2">
        <FileText className={`w-4 h-4 text-blue-500 ${data.is_active ? 'animate-pulse' : ''}`} />
        <span className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">Requirements</span>
        {data.is_active && (
          <span className="ml-auto text-[9px] font-semibold uppercase px-1.5 py-0.5 rounded-full text-blue-700 bg-blue-100 dark:text-blue-200 dark:bg-blue-500/20">
            Running
          </span>
        )}
      </div>

      <p className="text-[11px] text-zinc-500 dark:text-zinc-400 leading-relaxed whitespace-pre-wrap">
        {preview}
      </p>

      <Handle type="source" position={Position.Bottom} className="!bg-blue-500 !w-2.5 !h-2.5" />
    </div>
  );
});

RequirementsNode.displayName = 'RequirementsNode';
