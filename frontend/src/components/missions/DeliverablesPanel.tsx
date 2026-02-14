import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Download, FileText, Folder, Star } from 'lucide-react';
import { missionsApi } from '@/api/missions';
import type { MissionDeliverable } from '@/types/mission';

interface DeliverablesPanelProps {
  missionId: string;
  isOpen: boolean;
  onClose: () => void;
}

function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export const DeliverablesPanel: React.FC<DeliverablesPanelProps> = ({
  missionId,
  isOpen,
  onClose,
}) => {
  const { t } = useTranslation();
  const [deliverables, setDeliverables] = useState<MissionDeliverable[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setIsLoading(true);
    missionsApi
      .getDeliverables(missionId)
      .then(setDeliverables)
      .catch(() => setDeliverables([]))
      .finally(() => setIsLoading(false));
  }, [missionId, isOpen]);

  const handleDownload = async (deliverable: MissionDeliverable) => {
    try {
      const blob = await missionsApi.downloadDeliverable(missionId, deliverable.path);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = deliverable.filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch {
      // error is handled by apiClient interceptor
    }
  };

  if (!isOpen) return null;

  const targetFiles = deliverables.filter((d) => d.is_target);
  const otherFiles = deliverables.filter((d) => !d.is_target);

  return (
    <div className="fixed right-0 top-0 h-full w-96 glass-panel border-l border-zinc-200 dark:border-zinc-700 z-40 flex flex-col animate-in slide-in-from-right duration-300" style={{ marginLeft: 'var(--sidebar-width, 0px)' }}>
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-zinc-200 dark:border-zinc-700">
        <div className="flex items-center gap-2">
          <Folder className="w-4 h-4 text-emerald-500" />
          <h3 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
            {t('missions.deliverables')}
          </h3>
          <span className="text-xs text-zinc-400">({deliverables.length})</span>
        </div>
        <button
          onClick={onClose}
          className="p-1 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors"
        >
          <X className="w-4 h-4 text-zinc-500" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {isLoading && (
          <div className="text-center text-zinc-400 text-sm py-8">Loading...</div>
        )}

        {!isLoading && deliverables.length === 0 && (
          <div className="text-center text-zinc-400 text-sm py-8">
            No deliverables yet
          </div>
        )}

        {/* Target files */}
        {targetFiles.length > 0 && (
          <div className="mb-4">
            <h4 className="text-xs font-semibold text-zinc-500 uppercase mb-2 flex items-center gap-1">
              <Star className="w-3 h-3 text-amber-500" />
              Target Deliverables
            </h4>
            <div className="space-y-2">
              {targetFiles.map((d) => (
                <FileItem key={d.path} deliverable={d} onDownload={handleDownload} highlight />
              ))}
            </div>
          </div>
        )}

        {/* Other files */}
        {otherFiles.length > 0 && (
          <div>
            {targetFiles.length > 0 && (
              <h4 className="text-xs font-semibold text-zinc-500 uppercase mb-2">
                Other Files
              </h4>
            )}
            <div className="space-y-2">
              {otherFiles.map((d) => (
                <FileItem key={d.path} deliverable={d} onDownload={handleDownload} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const FileItem: React.FC<{
  deliverable: MissionDeliverable;
  onDownload: (d: MissionDeliverable) => void;
  highlight?: boolean;
}> = ({ deliverable, onDownload, highlight }) => {
  return (
    <div
      className={`flex items-center gap-3 p-3 rounded-lg border transition-colors ${
        highlight
          ? 'border-amber-200 bg-amber-50/50 dark:border-amber-500/20 dark:bg-amber-500/5'
          : 'border-zinc-200 dark:border-zinc-700 hover:bg-zinc-50 dark:hover:bg-zinc-800'
      }`}
    >
      <FileText className="w-5 h-5 text-zinc-400 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200 truncate">
          {deliverable.filename}
        </p>
        <p className="text-[10px] text-zinc-400">{formatFileSize(deliverable.size)}</p>
      </div>
      <button
        onClick={() => onDownload(deliverable)}
        className="p-1.5 hover:bg-zinc-200 dark:hover:bg-zinc-700 rounded-lg transition-colors"
        title="Download"
      >
        <Download className="w-4 h-4 text-zinc-500" />
      </button>
    </div>
  );
};
