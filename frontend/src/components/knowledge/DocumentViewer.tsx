import React, { useState } from "react";
import {
  X,
  Download,
  Share2,
  Lock,
  Globe,
  Building,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Loader2,
  Layers,
  Hash,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { LayoutModal } from "@/components/LayoutModal";
import { ModalPanel } from "@/components/ModalPanel";
import { DocumentPreview } from "@/components/knowledge/DocumentPreview";
import { ChunksViewer } from "@/components/knowledge/ChunksViewer";
import type { Document } from "@/types/document";

interface DocumentViewerProps {
  document: Document | null;
  isOpen: boolean;
  onClose: () => void;
  onDownload?: (document: Document) => void;
  isDownloading?: boolean;
}

type ViewerTab = "preview" | "chunks";

export const DocumentViewer: React.FC<DocumentViewerProps> = ({
  document,
  isOpen,
  onClose,
  onDownload,
  isDownloading,
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<ViewerTab>("preview");
  const [activeTabDocumentId, setActiveTabDocumentId] = useState<string | null>(
    null,
  );

  if (!isOpen || !document) return null;

  const currentTab: ViewerTab =
    activeTabDocumentId === document.id ? activeTab : "preview";

  const handleTabChange = (tab: ViewerTab) => {
    setActiveTab(tab);
    setActiveTabDocumentId(document.id);
  };

  const hasChunks =
    document.status === "completed" &&
    document.chunkCount != null &&
    document.chunkCount > 0;

  const getAccessLevelIcon = (level: Document["accessLevel"]) => {
    switch (level) {
      case "public":
        return <Globe className="w-5 h-5 text-green-500" />;
      case "internal":
        return <Building className="w-5 h-5 text-blue-500" />;
      case "confidential":
        return <AlertTriangle className="w-5 h-5 text-orange-500" />;
      case "restricted":
        return <Lock className="w-5 h-5 text-red-500" />;
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const getStatusBadge = (doc: Document) => {
    switch (doc.status) {
      case "completed":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-sm font-medium bg-green-500/20 text-green-700 dark:text-green-400">
            <CheckCircle className="w-4 h-4" />{" "}
            {t("document.viewer.statusProcessed")}
          </span>
        );
      case "failed":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-sm font-medium bg-red-500/20 text-red-700 dark:text-red-400">
            <XCircle className="w-4 h-4" /> {t("document.viewer.statusFailed")}
          </span>
        );
      case "processing":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-sm font-medium bg-blue-500/20 text-blue-700 dark:text-blue-400">
            <Loader2 className="w-4 h-4 animate-spin" />{" "}
            {t("document.viewer.statusProcessing")}
          </span>
        );
      case "uploading":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-sm font-medium bg-yellow-500/20 text-yellow-700 dark:text-yellow-400">
            <Loader2 className="w-4 h-4 animate-spin" />{" "}
            {t("document.viewer.statusUploading")}
          </span>
        );
    }
  };

  const getProcessingTime = (doc: Document) => {
    const startRaw =
      doc.processingStartedAt || doc.previousProcessedAt || doc.uploadedAt;
    const endRaw = doc.processingCompletedAt || doc.processedAt;
    if (!startRaw || !endRaw) return null;

    const start = new Date(startRaw).getTime();
    const end = new Date(endRaw).getTime();
    if (Number.isNaN(start) || Number.isNaN(end)) return null;

    const diffMs = end - start;
    if (diffMs < 0) return null;
    if (diffMs < 1000) return `${Math.round(diffMs)}ms`;

    const totalSeconds = diffMs / 1000;
    if (totalSeconds < 60) return `${totalSeconds.toFixed(1)}s`;

    const minutes = Math.floor(totalSeconds / 60);
    const seconds = Math.round(totalSeconds % 60);
    if (minutes < 60) return `${minutes}m ${seconds}s`;

    const hours = Math.floor(minutes / 60);
    const remainMinutes = minutes % 60;
    return `${hours}h ${remainMinutes}m`;
  };

  const handleDownload = () => {
    if (isDownloading) return;
    if (onDownload && document) {
      onDownload(document);
    }
  };

  return (
    <LayoutModal
      isOpen={isOpen}
      onClose={onClose}
      closeOnBackdropClick={false}
      closeOnEscape={true}
    >
      <ModalPanel className="w-full max-w-5xl max-h-[calc(100vh-var(--app-header-height,4rem)-3rem)] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-gray-800 dark:text-white truncate flex-1">
            {document.name}
          </h2>
          <div className="flex items-center gap-2">
            <button
              onClick={handleDownload}
              disabled={isDownloading}
              className="p-2 hover:bg-white/20 rounded-lg transition-colors disabled:opacity-50"
              title={t("document.download")}
            >
              {isDownloading ? (
                <Loader2 className="w-5 h-5 text-gray-700 dark:text-gray-300 animate-spin" />
              ) : (
                <Download className="w-5 h-5 text-gray-700 dark:text-gray-300" />
              )}
            </button>
            <button
              className="p-2 hover:bg-white/20 rounded-lg transition-colors"
              title={t("document.viewer.share")}
            >
              <Share2 className="w-5 h-5 text-gray-700 dark:text-gray-300" />
            </button>
            <button
              onClick={onClose}
              className="p-2 hover:bg-white/20 rounded-lg transition-colors"
            >
              <X className="w-6 h-6 text-gray-700 dark:text-gray-300" />
            </button>
          </div>
        </div>

        {/* Tabs */}
        {hasChunks && (
          <div className="flex gap-1 mb-6 border-b border-gray-200 dark:border-gray-700">
            <button
              onClick={() => handleTabChange("preview")}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                currentTab === "preview"
                  ? "border-indigo-500 text-indigo-600 dark:text-indigo-400"
                  : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
              }`}
            >
              {t("document.viewer.previewTab")}
            </button>
            <button
              onClick={() => handleTabChange("chunks")}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                currentTab === "chunks"
                  ? "border-indigo-500 text-indigo-600 dark:text-indigo-400"
                  : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
              }`}
            >
              {t("document.viewer.chunksTab", { count: document.chunkCount })}
            </button>
          </div>
        )}

        {/* Tab Content */}
        {currentTab === "preview" ? (
          <>
            {/* Document Preview */}
            <div className="mb-6 bg-white/10 rounded-lg p-4">
              <DocumentPreview
                document={document}
                onDownload={onDownload}
                isDownloading={Boolean(isDownloading)}
              />
            </div>

            {/* Metadata Panel */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* File Information */}
              <div>
                <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-4">
                  {t("document.viewer.fileInformation")}
                </h3>
                <div className="space-y-3">
                  <div>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {t("document.viewer.fileType")}
                    </p>
                    <p className="text-gray-800 dark:text-white font-medium">
                      {document.type.toUpperCase()}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {t("document.viewer.fileSize")}
                    </p>
                    <p className="text-gray-800 dark:text-white font-medium">
                      {formatFileSize(document.size)}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {t("document.viewer.uploadedAt")}
                    </p>
                    <p className="text-gray-800 dark:text-white font-medium">
                      {new Date(document.uploadedAt).toLocaleString()}
                    </p>
                  </div>
                  {document.processedAt && (
                    <div>
                      <p className="text-sm text-gray-600 dark:text-gray-400">
                        {t("document.viewer.processedAt")}
                      </p>
                      <p className="text-gray-800 dark:text-white font-medium">
                        {new Date(document.processedAt).toLocaleString()}
                      </p>
                    </div>
                  )}
                  <div>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {t("document.viewer.owner")}
                    </p>
                    <p className="text-gray-800 dark:text-white font-medium">
                      {document.owner}
                    </p>
                  </div>
                </div>
              </div>

              {/* Access Control */}
              <div>
                <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-4">
                  {t("document.viewer.accessControl")}
                </h3>
                <div className="space-y-3">
                  <div>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                      {t("document.viewer.accessLevel")}
                    </p>
                    <div className="flex items-center gap-2 p-3 bg-white/10 rounded-lg">
                      {getAccessLevelIcon(document.accessLevel)}
                      <span className="text-gray-800 dark:text-white font-medium capitalize">
                        {document.accessLevel}
                      </span>
                    </div>
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                      {t("document.viewer.description")}
                    </p>
                    <p className="text-gray-800 dark:text-white">
                      {document.description ||
                        t("document.viewer.noDescription")}
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Tags */}
            {document.tags && document.tags.length > 0 && (
              <div className="mt-6">
                <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-3">
                  {t("document.viewer.tags")}
                </h3>
                <div className="flex flex-wrap gap-2">
                  {document.tags.map((tag) => (
                    <span
                      key={tag}
                      className="px-3 py-1 bg-white/20 rounded-full text-sm text-gray-700 dark:text-gray-300"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Processing Details */}
            <div className="mt-6">
              <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-4">
                {t("document.viewer.processingDetails")}
              </h3>
              <div className="space-y-3">
                <div>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">
                    {t("document.viewer.status")}
                  </p>
                  {getStatusBadge(document)}
                </div>
                {document.chunkCount != null && (
                  <div className="flex items-center gap-2">
                    <Layers className="w-4 h-4 text-gray-500" />
                    <div>
                      <p className="text-sm text-gray-600 dark:text-gray-400">
                        {t("document.viewer.chunks")}
                      </p>
                      <p className="text-gray-800 dark:text-white font-medium">
                        {document.chunkCount}
                      </p>
                    </div>
                  </div>
                )}
                {document.tokenCount != null && (
                  <div className="flex items-center gap-2">
                    <Hash className="w-4 h-4 text-gray-500" />
                    <div>
                      <p className="text-sm text-gray-600 dark:text-gray-400">
                        {t("document.viewer.tokens")}
                      </p>
                      <p className="text-gray-800 dark:text-white font-medium">
                        {document.tokenCount.toLocaleString()}
                      </p>
                    </div>
                  </div>
                )}
                {getProcessingTime(document) && (
                  <div>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {t("document.viewer.processingTime")}
                    </p>
                    <p className="text-gray-800 dark:text-white font-medium">
                      {getProcessingTime(document)}
                    </p>
                  </div>
                )}
                {document.status === "failed" &&
                  (document.errorMessage || document.error) && (
                    <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
                      <p className="text-sm text-red-700 dark:text-red-400 font-medium mb-1">
                        {t("document.viewer.error")}
                      </p>
                      <p className="text-sm text-red-600 dark:text-red-300">
                        {document.errorMessage || document.error}
                      </p>
                    </div>
                  )}
              </div>
            </div>
          </>
        ) : (
          /* Chunks Tab */
          <ChunksViewer
            documentId={document.id}
            documentStatus={document.status}
            expectedChunkCount={document.chunkCount}
          />
        )}
      </ModalPanel>
    </LayoutModal>
  );
};
