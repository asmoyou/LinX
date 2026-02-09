import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Upload as UploadIcon, Loader2, AlertCircle, Settings, Search } from 'lucide-react';
import toast from 'react-hot-toast';
import { DocumentCard } from '@/components/knowledge/DocumentCard';
import { DocumentViewer } from '@/components/knowledge/DocumentViewer';
import { SearchBar } from '@/components/knowledge/SearchBar';
import { UploadDocumentForm } from '@/components/knowledge/UploadDocumentForm';
import { KBConfigPanel } from '@/components/knowledge/KBConfigPanel';
import { RetrievalTestPanel } from '@/components/knowledge/RetrievalTestPanel';
import { ModalPanel } from '@/components/ModalPanel';
import { useKnowledgeStore } from '@/stores/knowledgeStore';
import type { Document } from '@/types/document';
import type { UploadDocumentFormData } from '@/schemas/authSchemas';

export const Knowledge: React.FC = () => {
  const { t } = useTranslation();
  const [showUploadForm, setShowUploadForm] = useState(false);
  const [showConfigPanel, setShowConfigPanel] = useState(false);
  const [showRetrievalTest, setShowRetrievalTest] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState<Document | null>(null);
  const [isViewerOpen, setIsViewerOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [accessFilter, setAccessFilter] = useState('all');

  const {
    documents,
    isLoading,
    error,
    isDownloading,
    fetchDocuments,
    uploadDocument,
    deleteDocument,
    downloadDocument,
    reprocessDocument,
    pollAllProcessing,
  } = useKnowledgeStore();

  // Fetch documents on mount
  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  // Poll processing status for any documents stuck in processing after page load
  useEffect(() => {
    if (!isLoading && documents.length > 0) {
      pollAllProcessing();
    }
  }, [isLoading]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleUploadSubmit = useCallback(
    async (data: UploadDocumentFormData & { departmentId?: string }, file: File) => {
      // Map visibility to backend access_level
      const accessLevelMap: Record<string, string> = {
        private: 'private',
        team: 'team',
        public: 'public',
      };

      // Parse tags from comma-separated string
      const tags = data.tags
        ? data.tags.split(',').map((t) => t.trim()).filter(Boolean)
        : undefined;

      await uploadDocument({
        file,
        title: data.title,
        description: data.description,
        tags,
        access_level: accessLevelMap[data.visibility] || 'private',
        department_id: data.departmentId,
      });

      setShowUploadForm(false);
    },
    [uploadDocument]
  );

  const handleView = (document: Document) => {
    setSelectedDocument(document);
    setIsViewerOpen(true);
  };

  const handleDownload = useCallback(
    async (document: Document) => {
      try {
        await downloadDocument(document.id, document.name);
        toast.success(`${document.name} downloaded`, { id: `download-${document.id}` });
      } catch {
        toast.error('Download failed', { id: `download-err-${document.id}` });
      }
    },
    [downloadDocument]
  );

  const handleDelete = useCallback(
    async (document: Document) => {
      if (confirm(`Are you sure you want to delete ${document.name}?`)) {
        try {
          await deleteDocument(document.id);
          toast.success(`${document.name} deleted successfully`);
        } catch {
          // Error already handled in store
        }
      }
    },
    [deleteDocument]
  );

  const handleReprocess = useCallback(
    async (document: Document) => {
      try {
        await reprocessDocument(document.id);
        toast.success(`Reprocessing ${document.name}...`, { id: `reprocess-${document.id}` });
      } catch {
        toast.error('Failed to reprocess', { id: `reprocess-err-${document.id}` });
      }
    },
    [reprocessDocument]
  );

  // Filter documents locally
  const filteredDocuments = documents.filter((doc) => {
    const matchesSearch =
      !searchQuery ||
      doc.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      doc.tags?.some((tag) => tag.toLowerCase().includes(searchQuery.toLowerCase()));
    const matchesType = typeFilter === 'all' || doc.type === typeFilter;
    const matchesAccess = accessFilter === 'all' || doc.accessLevel === accessFilter;
    return matchesSearch && matchesType && matchesAccess;
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold text-gray-800 dark:text-white">
          {t('nav.knowledge')}
        </h1>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowRetrievalTest(true)}
            className="flex items-center gap-2 px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors font-medium"
            title="Test Retrieval"
          >
            <Search className="w-5 h-5" />
          </button>
          <button
            onClick={() => setShowConfigPanel(true)}
            className="flex items-center gap-2 px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors font-medium"
            title="Pipeline Settings"
          >
            <Settings className="w-5 h-5" />
          </button>
          <button
            onClick={() => setShowUploadForm(!showUploadForm)}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition-colors font-medium"
          >
            <UploadIcon className="w-5 h-5" />
            Upload Documents
          </button>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
          <p className="text-red-700 dark:text-red-300 text-sm">{error}</p>
        </div>
      )}

      {/* Upload Form Modal */}
      {showUploadForm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md"
          style={{ marginLeft: 'var(--sidebar-width, 0px)' }}
        >
          <ModalPanel className="w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <h2 className="text-2xl font-bold text-gray-800 dark:text-white mb-6">
              {t('document.uploadDocument', 'Upload Document')}
            </h2>
            <UploadDocumentForm
              onSubmit={handleUploadSubmit}
              onCancel={() => setShowUploadForm(false)}
            />
          </ModalPanel>
        </div>
      )}

      {/* Search and Filters */}
      <SearchBar
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        typeFilter={typeFilter}
        onTypeFilterChange={setTypeFilter}
        accessFilter={accessFilter}
        onAccessFilterChange={setAccessFilter}
      />

      {/* Loading State */}
      {isLoading && documents.length === 0 && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 text-indigo-500 animate-spin" />
          <span className="ml-3 text-gray-500 dark:text-gray-400">Loading documents...</span>
        </div>
      )}

      {/* Document Grid */}
      {(!isLoading || documents.length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {filteredDocuments.length === 0 ? (
            <div className="col-span-full text-center py-12">
              <p className="text-gray-500 dark:text-gray-400">
                {documents.length === 0
                  ? 'No documents yet. Upload your first document to get started.'
                  : 'No documents match your search criteria.'}
              </p>
            </div>
          ) : (
            filteredDocuments.map((document) => (
              <DocumentCard
                key={document.id}
                document={document}
                onView={handleView}
                onDownload={handleDownload}
                onDelete={handleDelete}
                onReprocess={handleReprocess}
              />
            ))
          )}
        </div>
      )}

      {/* Document Viewer Modal */}
      <DocumentViewer
        document={selectedDocument}
        isOpen={isViewerOpen}
        onClose={() => {
          setIsViewerOpen(false);
          setSelectedDocument(null);
        }}
        onDownload={handleDownload}
        isDownloading={isDownloading}
      />

      {/* KB Config Panel */}
      <KBConfigPanel
        isOpen={showConfigPanel}
        onClose={() => setShowConfigPanel(false)}
      />

      {/* Retrieval Test Panel */}
      <RetrievalTestPanel
        isOpen={showRetrievalTest}
        onClose={() => setShowRetrievalTest(false)}
      />
    </div>
  );
};
