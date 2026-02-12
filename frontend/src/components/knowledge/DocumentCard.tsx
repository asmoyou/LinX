import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  FileText,
  Image,
  Music,
  Video,
  File,
  Eye,
  Download,
  Trash2,
  MoreVertical,
  Clock,
  CheckCircle,
  XCircle,
  Loader2,
  Layers,
  Hash,
  RotateCcw,
  Pencil,
} from 'lucide-react';
import { GlassPanel } from '@/components/GlassPanel';
import { knowledgeApi } from '@/api/knowledge';
import type { Document } from '@/types/document';

interface DocumentCardProps {
  document: Document;
  onView: (document: Document) => void;
  onDownload: (document: Document) => void;
  onDelete: (document: Document) => void;
  onEdit?: (document: Document) => void;
  onReprocess?: (document: Document) => void;
  draggable?: boolean;
  onDragStart?: (document: Document) => void;
  onDragEnd?: () => void;
}

const MAX_INLINE_IMAGE_PREVIEW_SIZE = 5 * 1024 * 1024; // 5MB
const MAX_INLINE_PDF_PREVIEW_SIZE = 6 * 1024 * 1024; // 6MB
const MAX_INLINE_TEXT_PREVIEW_SIZE = 512 * 1024; // 512KB
const MAX_MEDIA_CACHE_ENTRIES = 80;

const mediaPreviewCache = new Map<string, string>();
const mediaCacheOrder: string[] = [];
const textPreviewCache = new Map<string, string>();

const touchMediaCacheKey = (key: string) => {
  const index = mediaCacheOrder.indexOf(key);
  if (index >= 0) {
    mediaCacheOrder.splice(index, 1);
  }
  mediaCacheOrder.push(key);
};

const setMediaCache = (key: string, objectUrl: string) => {
  if (!mediaPreviewCache.has(key) && mediaCacheOrder.length >= MAX_MEDIA_CACHE_ENTRIES) {
    const oldestKey = mediaCacheOrder.shift();
    if (oldestKey) {
      const oldUrl = mediaPreviewCache.get(oldestKey);
      if (oldUrl) {
        URL.revokeObjectURL(oldUrl);
      }
      mediaPreviewCache.delete(oldestKey);
    }
  }
  mediaPreviewCache.set(key, objectUrl);
  touchMediaCacheKey(key);
};

export const DocumentCard: React.FC<DocumentCardProps> = ({
  document,
  onView,
  onDownload,
  onDelete,
  onEdit,
  onReprocess,
  draggable = false,
  onDragStart,
  onDragEnd,
}) => {
  const { t } = useTranslation();
  const previewContainerRef = React.useRef<HTMLDivElement | null>(null);
  const [shouldLoadPreview, setShouldLoadPreview] = React.useState(false);
  const [showMenu, setShowMenu] = React.useState(false);
  const [cardPreviewUrl, setCardPreviewUrl] = React.useState<string | null>(null);
  const [textPreview, setTextPreview] = React.useState<string | null>(null);
  const [isCardPreviewLoading, setIsCardPreviewLoading] = React.useState(false);
  const processingProgress = Math.max(0, Math.min(100, document.processingProgress ?? 0));
  const uploadProgress = Math.max(0, Math.min(100, document.uploadProgress ?? 0));
  const lastUpdatedAt = document.processedAt || document.uploadedAt;
  const previewCacheKey = `${document.id}:${document.processedAt || document.uploadedAt}`;
  const hasGeneratedThumbnail = Boolean(document.thumbnailUrl);
  const previewMediaUrl =
    document.thumbnailUrl ||
    ((document.type === 'image' || document.type === 'video' || document.type === 'pdf')
      ? document.url
      : undefined) ||
    ((document.type === 'image' || document.type === 'video' || document.type === 'pdf')
      ? cardPreviewUrl
      : undefined);
  const hasMediaPreview = Boolean(previewMediaUrl);
  const hasTextPreview = Boolean(textPreview);
  const previewContainerClass = hasMediaPreview
    ? 'h-32 bg-white/10'
    : hasTextPreview
      ? 'h-20 bg-white/5 border border-white/20'
      : 'h-16 bg-white/5 border border-white/20';

  React.useEffect(() => {
    const element = previewContainerRef.current;
    if (!element) return () => undefined;
    if (shouldLoadPreview) return () => undefined;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setShouldLoadPreview(true);
            observer.disconnect();
          }
        });
      },
      { rootMargin: '160px 0px' }
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, [shouldLoadPreview]);

  React.useEffect(() => {
    let cancelled = false;
    let localObjectUrl: string | null = null;

    const hasDirectUrl = Boolean(document.thumbnailUrl || document.url);
    const canLoadPreviewFromStorage =
      document.status === 'completed' && document.fileReference?.startsWith('minio:');
    const wantsRemoteImagePreview =
      document.type === 'image' &&
      !hasDirectUrl &&
      document.size <= MAX_INLINE_IMAGE_PREVIEW_SIZE;
    const wantsRemoteVideoPreview = false;
    const wantsRemotePdfPreview =
      document.type === 'pdf' &&
      !hasDirectUrl &&
      document.size <= MAX_INLINE_PDF_PREVIEW_SIZE;
    const wantsRemoteTextPreview =
      (document.type === 'txt' || document.type === 'md') &&
      document.size <= MAX_INLINE_TEXT_PREVIEW_SIZE;
    const wantsRemoteMediaPreview =
      wantsRemoteImagePreview || wantsRemoteVideoPreview || wantsRemotePdfPreview;

    const cachedMediaUrl = mediaPreviewCache.get(previewCacheKey);
    const cachedText = textPreviewCache.get(previewCacheKey);
    if (wantsRemoteMediaPreview && cachedMediaUrl) {
      touchMediaCacheKey(previewCacheKey);
      setCardPreviewUrl(cachedMediaUrl);
      setTextPreview(null);
      setIsCardPreviewLoading(false);
      return () => undefined;
    }
    if (wantsRemoteTextPreview && cachedText != null) {
      setTextPreview(cachedText);
      setCardPreviewUrl(null);
      setIsCardPreviewLoading(false);
      return () => undefined;
    }

    if (
      !shouldLoadPreview ||
      !canLoadPreviewFromStorage ||
      (!wantsRemoteMediaPreview && !wantsRemoteTextPreview)
    ) {
      setCardPreviewUrl(null);
      setTextPreview(null);
      setIsCardPreviewLoading(false);
      return () => undefined;
    }

    const loadPreview = async () => {
      setIsCardPreviewLoading(true);
      try {
        const { blob } = await knowledgeApi.download(document.id);
        if (cancelled) return;

        if (wantsRemoteTextPreview) {
          const text = await blob.text();
          if (cancelled) return;
          const normalized = text.replace(/\s+/g, ' ').trim();
          const snippet = normalized.slice(0, 180) || '';
          textPreviewCache.set(previewCacheKey, snippet);
          setTextPreview(snippet || null);
          setCardPreviewUrl(null);
          return;
        }

        localObjectUrl = URL.createObjectURL(blob);
        setMediaCache(previewCacheKey, localObjectUrl);
        setCardPreviewUrl(localObjectUrl);
        setTextPreview(null);
      } catch {
        if (!cancelled) {
          setCardPreviewUrl(null);
          setTextPreview(null);
        }
      } finally {
        if (!cancelled) {
          setIsCardPreviewLoading(false);
        }
      }
    };

    void loadPreview();

    return () => {
      cancelled = true;
      if (localObjectUrl && !mediaPreviewCache.has(previewCacheKey)) {
        URL.revokeObjectURL(localObjectUrl);
      }
    };
  }, [
    document.id,
    document.type,
    document.size,
    document.status,
    document.fileReference,
    document.thumbnailUrl,
    document.url,
    previewCacheKey,
    shouldLoadPreview,
  ]);

  const renderCompactHint = () => {
    if (document.type === 'audio') {
      return (
        <div className="flex items-end gap-0.5 h-5">
          {[6, 12, 8, 14, 10].map((height, idx) => (
            <span
              key={idx}
              className="w-1 rounded-full bg-purple-500/60"
              style={{ height: `${height}px` }}
            />
          ))}
        </div>
      );
    }
    if (document.type === 'pdf' || document.type === 'docx') {
      return (
        <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/20 text-gray-600 dark:text-gray-300">
          {document.type.toUpperCase()}
        </span>
      );
    }
    if (document.status === 'completed' && document.chunkCount != null) {
      return (
        <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/20 text-gray-600 dark:text-gray-300">
          {document.chunkCount} chunks
        </span>
      );
    }
    return null;
  };

  const getFileIcon = (type: Document['type'], className: string = 'w-8 h-8') => {
    switch (type) {
      case 'pdf':
      case 'docx':
      case 'txt':
      case 'md':
        return <FileText className={`${className} text-blue-500`} />;
      case 'image':
        return <Image className={`${className} text-green-500`} />;
      case 'audio':
        return <Music className={`${className} text-purple-500`} />;
      case 'video':
        return <Video className={`${className} text-red-500`} />;
      default:
        return <File className={`${className} text-gray-500`} />;
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
    <GlassPanel
      className={`hover:scale-105 transition-transform duration-200 relative ${
        draggable ? 'cursor-grab active:cursor-grabbing' : ''
      }`}
      draggable={draggable}
      onDragStart={(event) => {
        if (!draggable) return;
        event.dataTransfer.effectAllowed = 'move';
        onDragStart?.(document);
      }}
      onDragEnd={() => {
        if (!draggable) return;
        onDragEnd?.();
      }}
    >
      {/* Status Badge */}
      <div className="absolute top-4 right-4 flex items-center gap-2">
        {getStatusIcon(document.status)}
        <span className={`text-xs px-2 py-1 rounded-full ${getAccessLevelColor(document.accessLevel)}`}>
          {document.accessLevel}
        </span>
      </div>

      {/* Thumbnail or compact icon strip */}
      <div
        ref={previewContainerRef}
        className={`mb-4 rounded-lg overflow-hidden relative ${previewContainerClass}`}
      >
        {hasMediaPreview ? (
          hasGeneratedThumbnail ? (
            <img
              src={previewMediaUrl}
              alt={document.name}
              className="h-full w-full object-cover"
              draggable={false}
            />
          ) : document.type === 'video' ? (
            <video
              src={previewMediaUrl}
              className="h-full w-full object-cover"
              muted
              playsInline
              preload="metadata"
            />
          ) : document.type === 'pdf' ? (
            <iframe
              src={`${previewMediaUrl}#page=1&toolbar=0&navpanes=0&scrollbar=0&view=FitH`}
              title={document.name}
              className="h-full w-full pointer-events-none"
            />
          ) : (
            <img
              src={previewMediaUrl}
              alt={document.name}
              className="h-full w-full object-cover"
              draggable={false}
            />
          )
        ) : hasTextPreview ? (
          <div className="h-full px-3 py-2 flex flex-col justify-center">
            <p className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1">
              {document.type} preview
            </p>
            <p className="text-xs text-gray-700 dark:text-gray-300 line-clamp-2 leading-relaxed">
              {textPreview}
            </p>
          </div>
        ) : (
          <div className="h-full px-3 flex items-center justify-between">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-10 h-10 rounded-md bg-white/20 flex items-center justify-center shrink-0">
                {getFileIcon(document.type, 'w-5 h-5')}
              </div>
              <div className="min-w-0">
                <p className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  {document.type}
                </p>
                <p className="text-xs font-medium text-gray-700 dark:text-gray-200 truncate">
                  {formatFileSize(document.size)}
                </p>
              </div>
            </div>
            {renderCompactHint()}
          </div>
        )}
        {!hasMediaPreview && !hasTextPreview && isCardPreviewLoading && (
          <div className="absolute inset-0 bg-black/20 flex items-center justify-center">
            <Loader2 className="w-4 h-4 animate-spin text-indigo-500" />
          </div>
        )}
      </div>

      {/* Document Info */}
      <div className="mb-4">
        <h3
          className="text-sm font-semibold text-gray-800 dark:text-white mb-1 truncate"
          title={document.name}
        >
          {document.name}
        </h3>
        <div className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
          <span className="px-1.5 py-0.5 rounded bg-white/20">{document.type.toUpperCase()}</span>
          <span>{formatFileSize(document.size)}</span>
        </div>
        {document.description && (
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 line-clamp-2">
            {document.description}
          </p>
        )}
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
