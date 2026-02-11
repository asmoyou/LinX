import React from 'react';
import { useTranslation } from 'react-i18next';
import { FileText, Image, Music, Video, File, Eye, Download, Trash2, MoreVertical, Clock, CheckCircle, XCircle, Loader2, Layers, Hash, RotateCcw, Pencil } from 'lucide-react';
import { GlassPanel } from '@/components/GlassPanel';
import type { Document } from '@/types/document';

interface DocumentCardProps {
  document: Document;
  onView: (document: Document) => void;
  onDownload: (document: Document) => void;
  onDelete: (document: Document) => void;
  onEdit?: (document: Document) => void;
  onReprocess?: (document: Document) => void;
}

export const DocumentCard: React.FC<DocumentCardProps> = ({ document, onView, onDownload, onDelete, onEdit, onReprocess }) => {
  const { t } = useTranslation();
  const [showMenu, setShowMenu] = React.useState(false);
  const processingProgress = Math.max(0, Math.min(100, document.processingProgress ?? 0));
  const uploadProgress = Math.max(0, Math.min(100, document.uploadProgress ?? 0));
  const lastUpdatedAt = document.processedAt || document.uploadedAt;

  const getFileIcon = (type: Document['type']) => {
    switch (type) {
      case 'pdf':
      case 'docx':
      case 'txt':
      case 'md':
        return <FileText className="w-8 h-8 text-blue-500" />;
      case 'image':
        return <Image className="w-8 h-8 text-green-500" />;
      case 'audio':
        return <Music className="w-8 h-8 text-purple-500" />;
      case 'video':
        return <Video className="w-8 h-8 text-red-500" />;
      default:
        return <File className="w-8 h-8 text-gray-500" />;
    }
  };

  const getStatusIcon = (status: Document['status']) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="w-4 h-4 text-green-500" />;
      case 'failed':
        return <XCircle className="w-4 h-4 text-red-500" />;
      case 'processing':
      case 'uploading':
        return <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />;
    }
  };

  const getAccessLevelColor = (level: Document['accessLevel']) => {
    switch (level) {
      case 'public':
        return 'bg-green-500/20 text-green-700 dark:text-green-400';
      case 'internal':
        return 'bg-blue-500/20 text-blue-700 dark:text-blue-400';
      case 'confidential':
        return 'bg-orange-500/20 text-orange-700 dark:text-orange-400';
      case 'restricted':
        return 'bg-red-500/20 text-red-700 dark:text-red-400';
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatDateTime = (value: string) => {
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleString(undefined, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  };

  return (
    <GlassPanel className="hover:scale-105 transition-transform duration-200 relative">
      {/* Status Badge */}
      <div className="absolute top-4 right-4 flex items-center gap-2">
        {getStatusIcon(document.status)}
        <span className={`text-xs px-2 py-1 rounded-full ${getAccessLevelColor(document.accessLevel)}`}>
          {document.accessLevel}
        </span>
      </div>

      {/* Thumbnail or Icon */}
      <div className="flex items-center justify-center h-32 mb-4 bg-white/10 rounded-lg">
        {document.thumbnailUrl ? (
          <img src={document.thumbnailUrl} alt={document.name} className="h-full w-full object-cover rounded-lg" />
        ) : (
          getFileIcon(document.type)
        )}
      </div>

      {/* Document Info */}
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-gray-800 dark:text-white mb-1 truncate" title={document.name}>
          {document.name}
        </h3>
        <p className="text-xs text-gray-600 dark:text-gray-400">
          {formatFileSize(document.size)} • {document.type.toUpperCase()}
        </p>
      </div>

      {/* Progress Bar */}
      {(document.status === 'uploading' || document.status === 'processing') && (
        <div className="mb-4">
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="text-gray-600 dark:text-gray-400">
              {document.status === 'uploading' ? 'Uploading' : 'Processing...'}
            </span>
            <span className="text-gray-800 dark:text-white font-medium">
              {document.status === 'uploading' ? uploadProgress : processingProgress}%
            </span>
          </div>
          <div className="w-full h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all duration-300"
              style={{
                width: `${document.status === 'uploading' ? uploadProgress : processingProgress}%`
              }}
            />
          </div>
        </div>
      )}

      {/* Processing Result Details */}
      {document.status === 'completed' && (document.chunkCount || document.tokenCount) && (
        <div className="mb-4 flex items-center gap-3 text-xs text-gray-600 dark:text-gray-400">
          {document.chunkCount != null && (
            <span className="flex items-center gap-1">
              <Layers className="w-3 h-3" />
              {document.chunkCount} chunks
            </span>
          )}
          {document.tokenCount != null && (
            <span className="flex items-center gap-1">
              <Hash className="w-3 h-3" />
              {document.tokenCount.toLocaleString()} tokens
            </span>
          )}
        </div>
      )}

      {/* Failed Error Banner */}
      {document.status === 'failed' && (document.errorMessage || document.error) && (
        <div className="mb-4 p-2 bg-red-500/10 border border-red-500/30 rounded text-xs text-red-700 dark:text-red-400">
          {document.errorMessage || document.error}
        </div>
      )}

      {/* Reprocess Button for failed/completed documents */}
      {onReprocess && (document.status === 'failed' || document.status === 'completed') && (
        <button
          onClick={() => onReprocess(document)}
          className="mb-4 w-full flex items-center justify-center gap-2 px-3 py-1.5 bg-amber-500/20 text-amber-700 dark:text-amber-400 border border-amber-500/30 rounded-lg hover:bg-amber-500/30 transition-colors text-xs font-medium"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          {document.status === 'failed' ? t('kbConfig.retryProcessing') : t('kbConfig.reprocess')}
        </button>
      )}

      {/* Tags */}
      {document.tags && document.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-4">
          {document.tags.slice(0, 2).map((tag) => (
            <span key={tag} className="text-xs px-2 py-0.5 bg-white/20 rounded-full text-gray-700 dark:text-gray-300">
              {tag}
            </span>
          ))}
          {document.tags.length > 2 && (
            <span className="text-xs px-2 py-0.5 bg-white/20 rounded-full text-gray-700 dark:text-gray-300">
              +{document.tags.length - 2}
            </span>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => onView(document)}
          disabled={document.status === 'uploading' || document.status === 'processing'}
          className="flex-1 px-3 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition-colors text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {t('document.view')}
        </button>
        <div className="relative">
          <button
            onClick={() => setShowMenu(!showMenu)}
            className="p-2 hover:bg-white/20 rounded-lg transition-colors"
          >
            <MoreVertical className="w-5 h-5 text-gray-700 dark:text-gray-300" />
          </button>
          
          {showMenu && (
            <>
              <div
                className="fixed inset-0 z-40"
                onClick={() => setShowMenu(false)}
              />
              <div className="absolute right-0 mt-2 w-48 glass rounded-lg shadow-lg z-50 overflow-hidden">
                <button
                  onClick={() => {
                    onView(document);
                    setShowMenu(false);
                  }}
                  disabled={document.status === 'uploading' || document.status === 'processing'}
                  className="w-full px-4 py-2 text-left text-sm hover:bg-white/20 transition-colors flex items-center gap-2 disabled:opacity-50"
                >
                  <Eye className="w-4 h-4" />
                  {t('document.viewDetails')}
                </button>
                {onEdit && (
                  <button
                    onClick={() => {
                      onEdit(document);
                      setShowMenu(false);
                    }}
                    className="w-full px-4 py-2 text-left text-sm hover:bg-white/20 transition-colors flex items-center gap-2"
                  >
                    <Pencil className="w-4 h-4" />
                    {t('common.edit')}
                  </button>
                )}
                <button
                  onClick={() => {
                    onDownload(document);
                    setShowMenu(false);
                  }}
                  disabled={document.status === 'uploading' || document.status === 'processing'}
                  className="w-full px-4 py-2 text-left text-sm hover:bg-white/20 transition-colors flex items-center gap-2 disabled:opacity-50"
                >
                  <Download className="w-4 h-4" />
                  {t('document.download')}
                </button>
                <button
                  onClick={() => {
                    onDelete(document);
                    setShowMenu(false);
                  }}
                  className="w-full px-4 py-2 text-left text-sm hover:bg-white/20 transition-colors flex items-center gap-2 text-red-500"
                >
                  <Trash2 className="w-4 h-4" />
                  {t('common.delete')}
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Metadata */}
      <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400">
        <div className="flex items-center gap-1">
          <Clock className="w-3 h-3" />
          {t('document.lastUpdated')}: {formatDateTime(lastUpdatedAt)}
        </div>
      </div>
    </GlassPanel>
  );
};
