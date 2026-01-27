import React from 'react';
import { X, Download, Share2, Lock, Globe, Building, AlertTriangle } from 'lucide-react';
import { GlassPanel } from '@/components/GlassPanel';
import type { Document } from '@/types/document';

interface DocumentViewerProps {
  document: Document | null;
  isOpen: boolean;
  onClose: () => void;
}

export const DocumentViewer: React.FC<DocumentViewerProps> = ({ document, isOpen, onClose }) => {
  if (!isOpen || !document) return null;

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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" style={{ marginLeft: 'var(--sidebar-width, 0px)' }}>
      <GlassPanel className="w-full max-w-5xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-gray-800 dark:text-white truncate flex-1">
            {document.name}
          </h2>
          <div className="flex items-center gap-2">
            <button
              className="p-2 hover:bg-white/20 rounded-lg transition-colors"
              title="Download"
            >
              <Download className="w-5 h-5 text-gray-700 dark:text-gray-300" />
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

        {/* Document Preview */}
        <div className="mb-6 bg-white/10 rounded-lg p-8 min-h-[400px] flex items-center justify-center">
          {document.type === 'image' && document.url ? (
            <img src={document.url} alt={document.name} className="max-w-full max-h-[500px] object-contain" />
          ) : (
            <div className="text-center">
              <p className="text-gray-600 dark:text-gray-400 mb-4">
                Preview not available for this file type
              </p>
              <button className="px-4 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition-colors">
                <Download className="w-4 h-4 inline mr-2" />
                Download to View
              </button>
            </div>
          )}
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
      </GlassPanel>
    </div>
  );
};
