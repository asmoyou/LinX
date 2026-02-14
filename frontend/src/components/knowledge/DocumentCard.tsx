import React from "react";
import { useTranslation } from "react-i18next";
import {
  FileText,
  FileSpreadsheet,
  Image as ImageIcon,
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
  Square,
  Pencil,
  Shield,
  Globe,
  Users,
  Lock,
  FileBox,
} from "lucide-react";
import { GlassPanel } from "@/components/GlassPanel";
import { motion, AnimatePresence } from "framer-motion";
import { knowledgeApi } from "@/api/knowledge";
import type { Document } from "@/types/document";

interface DocumentCardProps {
  document: Document;
  onView: (document: Document) => void;
  onDownload: (document: Document) => void;
  isDownloading?: boolean;
  onDelete: (document: Document) => void;
  onEdit?: (document: Document) => void;
  onReprocess?: (document: Document) => void;
  onStopProcessing?: (document: Document) => void;
  draggable?: boolean;
  onDragStart?: (document: Document) => void;
  onDragEnd?: () => void;
}

const thumbnailBlobCache = new Map<string, Blob>();

export const DocumentCard: React.FC<DocumentCardProps> = ({
  document,
  onView,
  onDownload,
  isDownloading = false,
  onDelete,
  onEdit,
  onReprocess,
  onStopProcessing,
  draggable = false,
  onDragStart,
  onDragEnd,
}) => {
  const { t } = useTranslation();
  const [showMenu, setShowMenu] = React.useState(false);
  const [isHovered, setIsHovered] = React.useState(false);
  const [thumbnailBlobUrl, setThumbnailBlobUrl] = React.useState<string | null>(
    null,
  );
  const thumbnailObjectUrlRef = React.useRef<string | null>(null);
  const supportsPreviewThumb =
    document.type === "image" ||
    document.type === "video" ||
    document.type === "pdf";
  const canAttemptThumbnail =
    supportsPreviewThumb &&
    document.status === "completed" &&
    (Boolean(document.thumbnailUrl) ||
      document.fileReference?.startsWith("minio:"));
  const thumbnailCacheKey = `${document.id}:${document.processedAt || document.uploadedAt || ""}`;

  const revokeThumbnailObjectUrl = React.useCallback(() => {
    if (thumbnailObjectUrlRef.current) {
      URL.revokeObjectURL(thumbnailObjectUrlRef.current);
      thumbnailObjectUrlRef.current = null;
    }
  }, []);

  React.useEffect(() => {
    let cancelled = false;

    const loadThumbnail = async () => {
      revokeThumbnailObjectUrl();
      setThumbnailBlobUrl(null);

      if (!canAttemptThumbnail) {
        return;
      }

      const cachedBlob = thumbnailBlobCache.get(thumbnailCacheKey);
      if (cachedBlob) {
        const cachedUrl = URL.createObjectURL(cachedBlob);
        if (cancelled) {
          URL.revokeObjectURL(cachedUrl);
          return;
        }
        thumbnailObjectUrlRef.current = cachedUrl;
        setThumbnailBlobUrl(cachedUrl);
        return;
      }

      try {
        const blob = await knowledgeApi.getThumbnail(document.id);
        if (!blob) {
          return;
        }
        thumbnailBlobCache.set(thumbnailCacheKey, blob);
        const nextUrl = URL.createObjectURL(blob);

        if (cancelled) {
          URL.revokeObjectURL(nextUrl);
          return;
        }

        revokeThumbnailObjectUrl();
        thumbnailObjectUrlRef.current = nextUrl;
        setThumbnailBlobUrl(nextUrl);
      } catch {
        if (!cancelled) {
          setThumbnailBlobUrl(null);
        }
      }
    };

    void loadThumbnail();

    return () => {
      cancelled = true;
    };
  }, [
    canAttemptThumbnail,
    document.id,
    revokeThumbnailObjectUrl,
    thumbnailCacheKey,
  ]);

  React.useEffect(
    () => () => {
      revokeThumbnailObjectUrl();
    },
    [revokeThumbnailObjectUrl],
  );

  const processingProgress = Math.max(
    0,
    Math.min(100, document.processingProgress ?? 0),
  );
  const uploadProgress = Math.max(
    0,
    Math.min(100, document.uploadProgress ?? 0),
  );
  const lastUpdatedAt = document.processedAt || document.uploadedAt;
  const hasGeneratedThumbnail = Boolean(thumbnailBlobUrl);
  const documentTypeLabel =
    document.type === "ppt" ? "PPTX" : document.type.toUpperCase();
  const previewMediaUrl =
    thumbnailBlobUrl ||
    (document.type === "image" ||
    document.type === "video" ||
    document.type === "pdf"
      ? document.url
      : undefined);
  const hasMediaPreview = Boolean(previewMediaUrl);
  const previewContainerClass = hasMediaPreview
    ? "h-40 bg-zinc-900/50"
    : "h-20 bg-gradient-to-br from-white/10 to-white/5 dark:from-white/5 dark:to-transparent border border-white/10";

  const renderCompactHint = () => {
    if (document.type === "audio") {
      return (
        <div className="flex items-end gap-1 h-6">
          {[6, 12, 8, 14, 10, 16, 8].map((height, idx) => (
            <motion.span
              key={idx}
              animate={{ height: isHovered ? [height, height * 0.5, height] : height }}
              transition={{ repeat: Infinity, duration: 1, delay: idx * 0.1 }}
              className="w-1 rounded-full bg-indigo-500/60"
              style={{ height: `${height}px` }}
            />
          ))}
        </div>
      );
    }
    return null;
  };

  const getFileIcon = (
    type: Document["type"],
    className: string = "w-8 h-8",
  ) => {
    switch (type) {
      case "pdf":
      case "docx":
      case "ppt":
      case "excel":
      case "txt":
      case "md":
        if (type === "excel") {
          return (
            <FileSpreadsheet className={`${className} text-emerald-500`} />
          );
        }
        if (type === "ppt") {
          return <FileText className={`${className} text-orange-500`} />;
        }
        return <FileText className={`${className} text-blue-500`} />;
      case "image":
        return <ImageIcon className={`${className} text-green-500`} />;
      case "audio":
        return <Music className={`${className} text-purple-500`} />;
      case "video":
        return <Video className={`${className} text-red-500`} />;
      default:
        return <File className={`${className} text-gray-500`} />;
    }
  };

  const getStatusInfo = (status: Document["status"]) => {
    switch (status) {
      case "completed":
        return {
          icon: <CheckCircle className="w-4 h-4" />,
          label: "READY",
          color: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20"
        };
      case "failed":
        return {
          icon: <XCircle className="w-4 h-4" />,
          label: "FAILED",
          color: "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20"
        };
      case "processing":
        return {
          icon: <Loader2 className="w-4 h-4 animate-spin" />,
          label: "PROCESSING",
          color: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border-indigo-500/20"
        };
      case "uploading":
        return {
          icon: <Loader2 className="w-4 h-4 animate-spin" />,
          label: "UPLOADING",
          color: "bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/20"
        };
    }
  };

  const getAccessInfo = (level: Document["accessLevel"]) => {
    switch (level) {
      case "public":
        return {
          icon: <Globe className="w-4 h-4" />,
          color: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20"
        };
      case "internal":
        return {
          icon: <Users className="w-4 h-4" />,
          color: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20"
        };
      case "confidential":
        return {
          icon: <Shield className="w-4 h-4" />,
          color: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20"
        };
      case "restricted":
        return {
          icon: <Lock className="w-4 h-4" />,
          color: "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20"
        };
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
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  };

  const statusInfo = getStatusInfo(document.status);
  const accessInfo = getAccessInfo(document.accessLevel);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -5 }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => {
        setIsHovered(false);
        setShowMenu(false);
      }}
    >
      <GlassPanel
        className={`h-full transition-all duration-300 relative border-transparent hover:border-indigo-500/30 overflow-hidden ${
          draggable ? "cursor-grab active:cursor-grabbing" : ""
        }`}
        draggable={draggable}
        onDragStart={(event) => {
          if (!draggable) return;
          event.dataTransfer.effectAllowed = "move";
          onDragStart?.(document);
        }}
        onDragEnd={() => {
          if (!draggable) return;
          onDragEnd?.();
        }}
      >
        {/* Top-right Badges - Compact Icon-only style */}
        <div className={`absolute top-4 right-4 z-10 flex items-center gap-2 transition-opacity duration-300 ${isHovered ? 'opacity-100' : 'opacity-90'}`}>
          <motion.span
            whileHover={{ scale: 1.1 }}
            title={statusInfo.label}
            className={`flex items-center justify-center w-7 h-7 rounded-full border shadow-lg backdrop-blur-md transition-colors ${statusInfo.color}`}
          >
            {statusInfo.icon}
          </motion.span>
          <motion.span
            whileHover={{ scale: 1.1 }}
            title={document.accessLevel.toUpperCase()}
            className={`flex items-center justify-center w-7 h-7 rounded-full border shadow-lg backdrop-blur-md transition-colors ${accessInfo.color}`}
          >
            {accessInfo.icon}
          </motion.span>
        </div>

        {/* Thumbnail or compact icon strip */}
        <div
          className={`mb-4 rounded-xl overflow-hidden relative z-0 transition-all duration-500 group ${previewContainerClass}`}
        >
          {hasMediaPreview ? (
            <>
              {hasGeneratedThumbnail ? (
                <img
                  src={previewMediaUrl}
                  alt={document.name}
                  className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-110"
                  draggable={false}
                />
              ) : document.type === "video" ? (
                <video
                  src={previewMediaUrl}
                  className="h-full w-full object-cover"
                  muted
                  playsInline
                  preload="metadata"
                />
              ) : document.type === "pdf" ? (
                <iframe
                  src={`${previewMediaUrl}#page=1&toolbar=0&navpanes=0&scrollbar=0&view=FitH`}
                  title={document.name}
                  className="h-full w-full pointer-events-none"
                />
              ) : (
                <img
                  src={previewMediaUrl}
                  alt={document.name}
                  className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-110"
                  draggable={false}
                />
              )}
              <div className="absolute inset-0 bg-indigo-500/0 group-hover:bg-indigo-500/10 transition-colors duration-500 pointer-events-none" />
            </>
          ) : (
            <div className="h-full px-4 flex items-center justify-between bg-gradient-to-br from-indigo-500/5 to-transparent">
              <div className="flex items-center gap-4 min-w-0">
                <div className="w-12 h-12 rounded-xl bg-white/10 flex items-center justify-center shrink-0 border border-white/10 shadow-lg group-hover:border-indigo-500/30 transition-colors">
                  {getFileIcon(document.type, "w-6 h-6")}
                </div>
                <div className="min-w-0">
                  <p className="text-[10px] uppercase font-bold tracking-widest text-indigo-500/70">
                    {document.type}
                  </p>
                  <p className="text-xs font-semibold text-gray-700 dark:text-gray-200 truncate">
                    {formatFileSize(document.size)}
                  </p>
                </div>
              </div>
              {renderCompactHint()}
            </div>
          )}
        </div>

        {/* Document Info */}
        <div className="px-1 mb-4">
          <h3
            className="text-base font-bold text-gray-800 dark:text-white mb-1 truncate group-hover:text-indigo-500 transition-colors"
            title={document.name}
          >
            {document.name}
          </h3>
          <div className="flex items-center gap-2 text-xs font-medium text-gray-500 dark:text-gray-400">
            <span className="px-1.5 py-0.5 rounded bg-zinc-500/10 border border-zinc-500/20 text-[10px] font-bold uppercase tracking-tight">
              {documentTypeLabel}
            </span>
            <span className="flex items-center gap-1.5">
              <div className="w-1 h-1 rounded-full bg-gray-300 dark:bg-gray-600" />
              {formatFileSize(document.size)}
            </span>
          </div>
          {document.description && (
            <p className="mt-2 text-xs text-gray-500 dark:text-gray-500 line-clamp-2 leading-relaxed">
              {document.description}
            </p>
          )}
        </div>

        {/* Progress Bar */}
        <AnimatePresence>
          {(document.status === "uploading" ||
            document.status === "processing") && (
            <motion.div 
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="mb-4"
            >
              <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider mb-1.5">
                <span className="text-indigo-600 dark:text-indigo-400">
                  {document.status === "uploading" ? "Uploading" : "Processing"}
                </span>
                <span className="text-gray-800 dark:text-white">
                  {document.status === "uploading"
                    ? uploadProgress
                    : processingProgress}
                  %
                </span>
              </div>
              <div className="w-full h-1.5 bg-gray-200 dark:bg-zinc-800 rounded-full overflow-hidden border border-black/5 dark:border-white/5">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ 
                    width: `${document.status === "uploading" ? uploadProgress : processingProgress}%` 
                  }}
                  className="h-full bg-gradient-to-r from-indigo-500 to-blue-500"
                />
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Processing Result Details */}
        {document.status === "completed" &&
          (document.chunkCount || document.tokenCount) && (
            <div className="mb-4 flex flex-wrap gap-2">
              {document.chunkCount != null && (
                <div className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-indigo-500/5 border border-indigo-500/10 text-[10px] font-bold text-indigo-600 dark:text-indigo-400">
                  <Layers className="w-3 h-3" />
                  {document.chunkCount} CHUNKS
                </div>
              )}
              {document.tokenCount != null && (
                <div className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-blue-500/5 border border-blue-500/10 text-[10px] font-bold text-blue-600 dark:text-blue-400">
                  <Hash className="w-3 h-3" />
                  {document.tokenCount.toLocaleString()} TOKENS
                </div>
              )}
            </div>
          )}

        {/* Failed Error Banner */}
        {document.status === "failed" &&
          (document.errorMessage || document.error) && (
            <div className="mb-4 p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl text-[11px] text-rose-700 dark:text-rose-400 leading-relaxed italic">
              <span className="font-bold not-italic mr-1">ERROR:</span>
              {document.errorMessage || document.error}
            </div>
          )}

        {/* Tags */}
        {document.tags && document.tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-4">
            {document.tags.slice(0, 3).map((tag) => (
              <span
                key={tag}
                className="text-[10px] font-bold px-2 py-0.5 bg-zinc-500/5 border border-zinc-500/10 rounded-full text-zinc-600 dark:text-zinc-400 hover:bg-zinc-500/10 transition-colors"
              >
                #{tag}
              </span>
            ))}
            {document.tags.length > 3 && (
              <span className="text-[10px] font-bold px-2 py-0.5 bg-zinc-500/5 border border-zinc-500/10 rounded-full text-zinc-600 dark:text-zinc-400">
                +{document.tags.length - 3}
              </span>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2 mt-auto">
          {document.status === "processing" && onStopProcessing ? (
            <button
              onClick={() => onStopProcessing(document)}
              className="flex-1 px-4 py-2 bg-gradient-to-r from-rose-500 to-orange-500 text-white rounded-lg hover:from-rose-600 hover:to-orange-600 transition-all shadow-md shadow-rose-500/20 text-sm font-semibold flex items-center justify-center gap-2"
            >
              <Square className="w-4 h-4" />
              {t("document.stopProcessing", "Stop Analysis")}
            </button>
          ) : (
            <button
              onClick={() => onView(document)}
              disabled={
                document.status === "uploading" || document.status === "processing"
              }
              className="flex-1 px-4 py-2 bg-gradient-to-r from-indigo-500 to-blue-500 text-white rounded-lg hover:from-indigo-600 hover:to-blue-600 transition-all shadow-md shadow-indigo-500/20 text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {t("document.view")}
            </button>
          )}
          
          <div className="relative">
            <button
              onClick={() => setShowMenu(!showMenu)}
              className="p-2 hover:bg-white/10 dark:hover:bg-zinc-800/50 rounded-lg transition-colors border border-transparent hover:border-white/20"
            >
              <MoreVertical className="w-5 h-5 text-gray-600 dark:text-gray-400" />
            </button>

            <AnimatePresence>
              {showMenu && (
                <>
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="fixed inset-0 z-40"
                    onClick={() => setShowMenu(false)}
                  />
                  <motion.div 
                    initial={{ opacity: 0, scale: 0.95, y: 10 }}
                    animate={{ opacity: 1, scale: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95, y: 10 }}
                    className="absolute right-0 bottom-full mb-2 w-52 bg-white dark:bg-zinc-900 rounded-xl shadow-2xl z-50 overflow-hidden border border-gray-200 dark:border-white/10"
                  >
                    <button
                      onClick={() => {
                        onView(document);
                        setShowMenu(false);
                      }}
                      disabled={
                        document.status === "uploading" ||
                        document.status === "processing"
                      }
                      className="w-full px-4 py-3 text-left text-sm hover:bg-gray-100 dark:hover:bg-white/5 transition-colors flex items-center gap-3 text-gray-700 dark:text-gray-200 disabled:opacity-50"
                    >
                      <div className="w-8 h-8 rounded-lg bg-indigo-500/10 flex items-center justify-center">
                        <Eye className="w-4 h-4 text-indigo-500" />
                      </div>
                      <span className="font-semibold">{t("document.viewDetails")}</span>
                    </button>
                    {onEdit && (
                      <button
                        onClick={() => {
                          onEdit(document);
                          setShowMenu(false);
                        }}
                        className="w-full px-4 py-3 text-left text-sm hover:bg-gray-100 dark:hover:bg-white/5 transition-colors flex items-center gap-3 text-gray-700 dark:text-gray-200"
                      >
                        <div className="w-8 h-8 rounded-lg bg-blue-500/10 flex items-center justify-center">
                          <Pencil className="w-4 h-4 text-blue-500" />
                        </div>
                        <span className="font-semibold">{t("common.edit")}</span>
                      </button>
                    )}
                    <button
                      onClick={() => {
                        onDownload(document);
                        setShowMenu(false);
                      }}
                      disabled={
                        document.status === "uploading" ||
                        document.status === "processing" ||
                        isDownloading
                      }
                      className="w-full px-4 py-3 text-left text-sm hover:bg-gray-100 dark:hover:bg-white/5 transition-colors flex items-center gap-3 text-gray-700 dark:text-gray-200 disabled:opacity-50"
                    >
                      <div className="w-8 h-8 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                        {isDownloading ? (
                          <Loader2 className="w-4 h-4 animate-spin text-emerald-500" />
                        ) : (
                          <Download className="w-4 h-4 text-emerald-500" />
                        )}
                      </div>
                      <span className="font-semibold">
                        {isDownloading
                          ? t("document.downloading")
                          : t("document.download")}
                      </span>
                    </button>
                    <div className="h-px bg-gray-100 dark:bg-white/5 mx-2 my-1" />
                    <button
                      onClick={() => {
                        onDelete(document);
                        setShowMenu(false);
                      }}
                      className="w-full px-4 py-3 text-left text-sm hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors flex items-center gap-3 text-red-600 dark:text-red-500"
                    >
                      <div className="w-8 h-8 rounded-lg bg-red-500/10 flex items-center justify-center">
                        <Trash2 className="w-4 h-4 text-red-600 dark:text-red-500" />
                      </div>
                      <span className="font-semibold">{t("common.delete")}</span>
                    </button>
                  </motion.div>
                </>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* Metadata */}
        <div className="mt-4 pt-4 border-t border-gray-100 dark:border-white/5 flex items-center justify-between text-[10px] text-gray-500 dark:text-gray-400">
          <div className="flex items-center gap-1.5 font-medium">
            <Clock className="w-3 h-3 text-indigo-500/70" />
            <span>{formatDateTime(lastUpdatedAt)}</span>
          </div>

          {/* Compact Reprocess Button */}
          {onReprocess &&
            (document.status === "failed" || document.status === "completed") && (
              <motion.button
                whileHover={{ scale: 1.1, backgroundColor: "rgba(245, 158, 11, 0.2)" }}
                whileTap={{ scale: 0.9 }}
                onClick={(e) => {
                  e.stopPropagation();
                  onReprocess(document);
                }}
                className="flex items-center gap-1 px-2 py-0.5 bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 rounded-full transition-colors font-bold uppercase tracking-tighter"
                title={document.status === "failed" ? t("kbConfig.retryProcessing") : t("kbConfig.reprocess")}
              >
                <RotateCcw className="w-3 h-3" />
                <span className="text-[9px]">{document.status === "failed" ? "RETRY" : "REDO"}</span>
              </motion.button>
            )}

          <div className="flex items-center gap-1">
            <FileBox className="w-3 h-3 text-zinc-500" />
            <span className="uppercase">{document.type}</span>
          </div>
        </div>
      </GlassPanel>
    </motion.div>
  );
};
