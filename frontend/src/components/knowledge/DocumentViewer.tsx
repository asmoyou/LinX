import React, { useState } from 'react';
import { X, Download, Share2, Lock, Globe, Building, AlertTriangle, CheckCircle, XCircle, Loader2, Layers, Hash } from 'lucide-react';
import { ModalPanel } from '@/components/ModalPanel';
import { DocumentPreview } from '@/components/knowledge/DocumentPreview';
import { ChunksViewer } from '@/components/knowledge/ChunksViewer';
import type { Document } from '@/types/document';

interface DocumentViewerProps {
  document: Document | null;
  isOpen: boolean;
  onClose: () => void;
  onDownload?: (document: Document) => void;
  isDownloading?: boolean;
}

type ViewerTab = 'preview' | 'chunks';

export const DocumentViewer: React.FC<DocumentViewerProps> = ({
  document,
  isOpen,
  onClose,
  onDownload,
  isDownloading,
}) => {
  const [activeTab, setActiveTab] = useState<ViewerTab>('preview');

  if (!isOpen || !document) return null;

  const hasChunks = document.status === 'completed' && document.chunkCount != null && document.chunkCount > 0;

  const getAccessLevelIcon = (level: Document['accessLevel']) => {
    switch (level) {
      case 'public':
        return <Globe className="w-5 h-5 text-green-500" />;
      case 'internal':
        return <Building className="w-5 h-5 text-blue-500" />;
      case 'confidential':
        return <AlertTriangle className="w-5 h-5 text-orange-500" />;
      case 'restricted':
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
      case 'completed':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-sm font-medium bg-green-500/20 text-green-700 dark:text-green-400">
            <CheckCircle className="w-4 h-4" /> Processed
          </span>
        );
      case 'failed':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-sm font-medium bg-red-500/20 text-red-700 dark:text-red-400">
            <XCircle className="w-4 h-4" /> Failed
          </span>
        );
      case 'processing':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-sm font-medium bg-blue-500/20 text-blue-700 dark:text-blue-400">
            <Loader2 className="w-4 h-4 animate-spin" /> Processing
          </span>
        );
      case 'uploading':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-sm font-medium bg-yellow-500/20 text-yellow-700 dark:text-yellow-400">
            <Loader2 className="w-4 h-4 animate-spin" /> Uploading
          </span>
        );
    }
  };

  const getProcessingTime = (doc: Document) => {
    if (!doc.uploadedAt || !doc.processedAt) return null;
    const start = new Date(doc.uploadedAt).getTime();
    const end = new Date(doc.processedAt).getTime();
    const diffMs = end - start;
    if (diffMs < 0) return null;
    if (diffMs < 1000) return `${diffMs}ms`;
    if (diffMs < 60000) return `${(diffMs / 1000).toFixed(1)}s`;
    return `${(diffMs / 60000).toFixed(1)}min`;
  };

  const handleDownload = () => {
    if (onDownload && document) {
      onDownload(document);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md" style={{ marginLeft: 'var(--sidebar-width, 0px)' }}>
      <ModalPanel className="w-full max-w-5xl max-h-[90vh] overflow-y-auto">
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
              title="Download"
            >
              {isDownloading ? (
                <Loader2 className="w-5 h-5 text-gray-700 dark:text-gray-300 animate-spin" />
              ) : (
                <Download className="w-5 h-5 text-gray-700 dark:text-gray-300" />
              )}
            </button>
            <button
              className="p-2 hover:bg-white/20 rounded-lg transition-colors"
              title="Share"
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
              onClick={() => setActiveTab('preview')}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'preview'
                  ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
              }`}
            >
              Preview
            </button>
            <button
              onClick={() => setActiveTab('chunks')}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'chunks'
                  ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
              }`}
            >
              Chunks ({document.chunkCount})
            </button>
          </div>
        )}

        {/* Tab Content */}
        {activeTab === 'preview' ? (
          <>
            {/* Document Preview */}
            <div className="mb-6 bg-white/10 rounded-lg p-4">
              <DocumentPreview document={document} onDownload={onDownload} />
            </div>

            {/* Metadata Panel */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* File Information */}
              <div>
                <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-4">
                  File Information
                </h3>
                <div className="space-y-3">
                  <div>
                    <p className="text-sm text-gray-600 dark:text-gray-400">File Type</p>
                    <p className="text-gray-800 dark:text-white font-medium">{document.type.toUpperCase()}</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 dark:text-gray-400">File Size</p>
                    <p className="text-gray-800 dark:text-white font-medium">{formatFileSize(document.size)}</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 dark:text-gray-400">Uploaded</p>
                    <p className="text-gray-800 dark:text-white font-medium">
                      {new Date(document.uploadedAt).toLocaleString()}
                    </p>
                  </div>
                  {document.processedAt && (
                    <div>
                      <p className="text-sm text-gray-600 dark:text-gray-400">Processed</p>
                      <p className="text-gray-800 dark:text-white font-medium">
                        {new Date(document.processedAt).toLocaleString()}
                      </p>
                    </div>
                  )}
                  <div>
                    <p className="text-sm text-gray-600 dark:text-gray-400">Owner</p>
                    <p className="text-gray-800 dark:text-white font-medium">{document.owner}</p>
                  </div>
                </div>
              </div>

              {/* Access Control */}
              <div>
                <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-4">
                  Access Control
                </h3>
                <div className="space-y-3">
                  <div>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">Access Level</p>
                    <div className="flex items-center gap-2 p-3 bg-white/10 rounded-lg">
                      {getAccessLevelIcon(document.accessLevel)}
                      <span className="text-gray-800 dark:text-white font-medium capitalize">
                        {document.accessLevel}
                      </span>
                    </div>
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">Description</p>
                    <p className="text-gray-800 dark:text-white">
                      {document.description || 'No description provided'}
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Tags */}
            {document.tags && document.tags.length > 0 && (
              <div className="mt-6">
                <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-3">Tags</h3>
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
                Processing Details
              </h3>
              <div className="space-y-3">
                <div>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">Status</p>
                  {getStatusBadge(document)}
                </div>
                {document.chunkCount != null && (
                  <div className="flex items-center gap-2">
                    <Layers className="w-4 h-4 text-gray-500" />
                    <div>
                      <p className="text-sm text-gray-600 dark:text-gray-400">Chunks</p>
                      <p className="text-gray-800 dark:text-white font-medium">{document.chunkCount}</p>
                    </div>
                  </div>
                )}
                {document.tokenCount != null && (
                  <div className="flex items-center gap-2">
                    <Hash className="w-4 h-4 text-gray-500" />
                    <div>
                      <p className="text-sm text-gray-600 dark:text-gray-400">Tokens</p>
                      <p className="text-gray-800 dark:text-white font-medium">{document.tokenCount.toLocaleString()}</p>
                    </div>
                  </div>
                )}
                {getProcessingTime(document) && (
                  <div>
                    <p className="text-sm text-gray-600 dark:text-gray-400">Processing Time</p>
                    <p className="text-gray-800 dark:text-white font-medium">{getProcessingTime(document)}</p>
                  </div>
                )}
                {document.status === 'failed' && (document.errorMessage || document.error) && (
                  <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
                    <p className="text-sm text-red-700 dark:text-red-400 font-medium mb-1">Error</p>
                    <p className="text-sm text-red-600 dark:text-red-300">{document.errorMessage || document.error}</p>
                  </div>
                )}
              </div>
            </div>
          </>
        ) : (
          /* Chunks Tab */
          <ChunksViewer documentId={document.id} />
        )}
      </ModalPanel>
    </div>
  );
};
