import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Upload as UploadIcon,
  Loader2,
  AlertCircle,
  Settings,
  Search,
  FolderPlus,
  X,
  Save,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { DocumentCard } from '@/components/knowledge/DocumentCard';
import { DocumentViewer } from '@/components/knowledge/DocumentViewer';
import { SearchBar } from '@/components/knowledge/SearchBar';
import { UploadDocumentForm } from '@/components/knowledge/UploadDocumentForm';
import { KBConfigPanel } from '@/components/knowledge/KBConfigPanel';
import { RetrievalTestPanel } from '@/components/knowledge/RetrievalTestPanel';
import { CollectionCard } from '@/components/knowledge/CollectionCard';
import { CollectionBreadcrumb } from '@/components/knowledge/CollectionBreadcrumb';
import { DepartmentSelect } from '@/components/departments/DepartmentSelect';
import { ModalPanel } from '@/components/ModalPanel';
import { useKnowledgeStore } from '@/stores/knowledgeStore';
import { knowledgeApi } from '@/api/knowledge';
import type { Document, Collection } from '@/types/document';
import type { UploadDocumentFormData } from '@/schemas/authSchemas';
import type { ZipUploadResponse } from '@/api/knowledge';

// Reverse map API access levels to form radio values
const accessLevelToFormValue = (level: string): string => {
  switch (level) {
    case 'public': return 'public';
    case 'internal': return 'team';
    case 'restricted':
    case 'confidential':
    default: return 'private';
  }
};

// Map form radio values to API access levels
const formValueToAccessLevel = (value: string): string => {
  switch (value) {
    case 'public': return 'public';
    case 'team': return 'team';
    default: return 'private';
  }
};

export const Knowledge: React.FC = () => {
  const { t } = useTranslation();
  const [showUploadForm, setShowUploadForm] = useState(false);
  const [showConfigPanel, setShowConfigPanel] = useState(false);
  const [showRetrievalTest, setShowRetrievalTest] = useState(false);
  const [showCreateCollection, setShowCreateCollection] = useState(false);
  const [newCollectionName, setNewCollectionName] = useState('');
  const [selectedDocument, setSelectedDocument] = useState<Document | null>(null);
  const [isViewerOpen, setIsViewerOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [accessFilter, setAccessFilter] = useState('all');

  // Edit states
  const [editingCollection, setEditingCollection] = useState<Collection | null>(null);
  const [editingDocument, setEditingDocument] = useState<Document | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // Collection edit form state
  const [editCollName, setEditCollName] = useState('');
  const [editCollDesc, setEditCollDesc] = useState('');
  const [editCollAccess, setEditCollAccess] = useState('private');
  const [editCollDept, setEditCollDept] = useState<string | undefined>();

  // Document edit form state
  const [editDocTitle, setEditDocTitle] = useState('');
  const [editDocDesc, setEditDocDesc] = useState('');
  const [editDocTags, setEditDocTags] = useState('');
  const [editDocAccess, setEditDocAccess] = useState('private');
  const [editDocDept, setEditDocDept] = useState<string | undefined>();

  const {
    documents,
    isLoading,
    error,
    isDownloading,
    collections,
    activeCollectionId,
    isLoadingCollections,
    fetchDocuments,
    fetchCollections,
    createCollection,
    updateCollection,
    deleteCollection: deleteCollectionAction,
    setActiveCollection,
    uploadDocument,
    deleteDocument,
    updateDocument,
    downloadDocument,
    reprocessDocument,
    pollAllProcessing,
  } = useKnowledgeStore();

  // Find active collection object
  const activeCollection = activeCollectionId
    ? collections.find((c) => c.id === activeCollectionId) || null
    : null;

  // Fetch documents and collections on mount
  useEffect(() => {
    fetchCollections();
    fetchDocuments();
  }, [fetchCollections, fetchDocuments]);

  // Re-fetch documents when active collection changes
  useEffect(() => {
    fetchDocuments();
  }, [activeCollectionId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Poll processing status for any documents stuck in processing after page load
  useEffect(() => {
    if (!isLoading && documents.length > 0) {
      pollAllProcessing();
    }
  }, [isLoading]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleUploadSubmit = useCallback(
    async (data: UploadDocumentFormData & { departmentId?: string }, file: File) => {
      const accessLevelMap: Record<string, string> = {
        private: 'private',
        team: 'team',
        public: 'public',
      };

      const tags = data.tags
        ? data.tags.split(',').map((t) => t.trim()).filter(Boolean)
        : undefined;

      const result = await uploadDocument({
        file,
        title: data.title,
        description: data.description,
        tags,
        access_level: accessLevelMap[data.visibility] || 'private',
        department_id: data.departmentId,
      });

      setShowUploadForm(false);

      if (result && 'collection' in result) {
        const zipResult = result as ZipUploadResponse;
        let msg = t('collection.zipExtracted', { count: zipResult.items.length });
        if (zipResult.skipped.length > 0) {
          msg += t('collection.zipSkipped', { skipped: zipResult.skipped.length });
        }
        toast.success(msg, { duration: 5000 });
      }
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
        toast.success(t('document.downloadSuccess', { name: document.name }), { id: `download-${document.id}` });
      } catch {
        toast.error(t('document.downloadFailed'), { id: `download-err-${document.id}` });
      }
    },
    [downloadDocument, t]
  );

  const handleDelete = useCallback(
    async (document: Document) => {
      if (confirm(t('document.deleteConfirm', { name: document.name }))) {
        try {
          await deleteDocument(document.id);
          toast.success(t('document.deleteSuccess', { name: document.name }));
        } catch {
          // Error already handled in store
        }
      }
    },
    [deleteDocument, t]
  );

  const handleReprocess = useCallback(
    async (document: Document) => {
      try {
        await reprocessDocument(document.id);
        toast.success(t('document.reprocessing', { name: document.name }), { id: `reprocess-${document.id}` });
      } catch {
        toast.error(t('document.reprocessFailed'), { id: `reprocess-err-${document.id}` });
      }
    },
    [reprocessDocument, t]
  );

  // ============= Collection handlers =============
  const handleCollectionClick = (collection: Collection) => {
    setActiveCollection(collection.id);
  };

  const openEditCollection = (collection: Collection) => {
    setEditCollName(collection.name);
    setEditCollDesc(collection.description || '');
    setEditCollAccess(accessLevelToFormValue(collection.accessLevel));
    setEditCollDept(collection.departmentId || undefined);
    setEditingCollection(collection);
  };

  const handleSaveCollection = async () => {
    if (!editingCollection || !editCollName.trim()) return;
    setIsSaving(true);
    try {
      await updateCollection(editingCollection.id, {
        name: editCollName.trim(),
        description: editCollDesc.trim() || undefined,
      });
      await knowledgeApi.updateCollection(editingCollection.id, {
        name: editCollName.trim(),
        description: editCollDesc.trim() || undefined,
        access_level: formValueToAccessLevel(editCollAccess),
        department_id: editCollDept || undefined,
      });
      await fetchCollections();
      toast.success(t('collection.updateSuccess'));
      setEditingCollection(null);
    } catch {
      toast.error(t('collection.updateFailed'));
    } finally {
      setIsSaving(false);
    }
  };

  const handleCollectionDelete = async (collection: Collection) => {
    if (
      confirm(
        t('collection.confirmDelete', { name: collection.name, count: collection.itemCount })
      )
    ) {
      try {
        await deleteCollectionAction(collection.id);
        toast.success(t('collection.deleteSuccess'));
      } catch {
        toast.error(t('collection.deleteFailed'));
      }
    }
  };

  const handleCreateCollection = async () => {
    if (!newCollectionName.trim()) return;
    try {
      await createCollection(newCollectionName.trim());
      toast.success(t('collection.createSuccess'));
      setShowCreateCollection(false);
      setNewCollectionName('');
    } catch {
      toast.error(t('collection.createFailed'));
    }
  };

  const handleNavigateRoot = () => {
    setActiveCollection(null);
  };

  // ============= Document edit handlers =============
  const openEditDocument = (doc: Document) => {
    setEditDocTitle(doc.name || '');
    setEditDocDesc(doc.description || '');
    setEditDocTags(doc.tags?.join(', ') || '');
    setEditDocAccess(accessLevelToFormValue(doc.accessLevel));
    setEditDocDept(doc.departmentId || undefined);
    setEditingDocument(doc);
  };

  const handleSaveDocument = async () => {
    if (!editingDocument || !editDocTitle.trim()) return;
    setIsSaving(true);
    try {
      const tags = editDocTags
        ? editDocTags.split(',').map((t) => t.trim()).filter(Boolean)
        : [];
      const updated = await knowledgeApi.update(editingDocument.id, {
        title: editDocTitle.trim(),
        description: editDocDesc.trim() || undefined,
        tags,
        access_level: formValueToAccessLevel(editDocAccess),
        department_id: editDocDept || undefined,
      });
      updateDocument(editingDocument.id, {
        name: updated.name,
        description: updated.description,
        tags: updated.tags,
        accessLevel: updated.accessLevel,
        departmentId: updated.departmentId,
      });
      toast.success(t('document.updateSuccess'));
      setEditingDocument(null);
    } catch {
      toast.error(t('document.updateFailed'));
    } finally {
      setIsSaving(false);
    }
  };

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

  const accessOptions = [
    { value: 'private', label: t('document.visibilityPrivate', 'Private') },
    { value: 'team', label: t('document.visibilityTeam', 'Team') },
    { value: 'public', label: t('document.visibilityPublic', 'Public') },
  ];

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
            title={t('kbConfig.testRetrieval')}
          >
            <Search className="w-5 h-5" />
          </button>
          <button
            onClick={() => setShowConfigPanel(true)}
            className="flex items-center gap-2 px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors font-medium"
            title={t('kbConfig.title')}
          >
            <Settings className="w-5 h-5" />
          </button>
          {!activeCollectionId && (
            <button
              onClick={() => setShowCreateCollection(true)}
              className="flex items-center gap-2 px-4 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 transition-colors font-medium"
            >
              <FolderPlus className="w-5 h-5" />
              {t('collection.create')}
            </button>
          )}
          <button
            onClick={() => setShowUploadForm(!showUploadForm)}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition-colors font-medium"
          >
            <UploadIcon className="w-5 h-5" />
            {t('document.uploadDocument')}
          </button>
        </div>
      </div>

      {/* Breadcrumb */}
      <CollectionBreadcrumb collection={activeCollection} onNavigateRoot={handleNavigateRoot} />

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
          onClick={(e) => { if (e.target === e.currentTarget) setShowUploadForm(false); }}
        >
          <ModalPanel className="w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-2xl font-bold text-gray-800 dark:text-white">
                {t('document.uploadDocument')}
              </h2>
              <button
                onClick={() => setShowUploadForm(false)}
                className="p-2 hover:bg-white/20 rounded-lg transition-colors"
              >
                <X className="w-5 h-5 text-gray-500" />
              </button>
            </div>
            <UploadDocumentForm
              onSubmit={handleUploadSubmit}
              onCancel={() => setShowUploadForm(false)}
              collectionId={activeCollectionId || undefined}
            />
          </ModalPanel>
        </div>
      )}

      {/* Create Collection Modal */}
      {showCreateCollection && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md"
          style={{ marginLeft: 'var(--sidebar-width, 0px)' }}
          onClick={(e) => { if (e.target === e.currentTarget) { setShowCreateCollection(false); setNewCollectionName(''); } }}
        >
          <ModalPanel className="w-full max-w-md">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-gray-800 dark:text-white">
                {t('collection.create')}
              </h2>
              <button
                onClick={() => { setShowCreateCollection(false); setNewCollectionName(''); }}
                className="p-2 hover:bg-white/20 rounded-lg transition-colors"
              >
                <X className="w-5 h-5 text-gray-500" />
              </button>
            </div>
            <input
              type="text"
              value={newCollectionName}
              onChange={(e) => setNewCollectionName(e.target.value)}
              placeholder={t('collection.namePlaceholder')}
              className="w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent transition-all mb-4"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleCreateCollection();
              }}
            />
            <div className="flex gap-3">
              <button
                onClick={handleCreateCollection}
                disabled={!newCollectionName.trim()}
                className="flex-1 px-4 py-3 bg-amber-500 text-white rounded-lg hover:bg-amber-600 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {t('collection.create')}
              </button>
              <button
                onClick={() => { setShowCreateCollection(false); setNewCollectionName(''); }}
                className="flex-1 px-4 py-3 bg-white/10 dark:bg-zinc-800/10 text-zinc-700 dark:text-zinc-300 rounded-lg hover:bg-white/20 dark:hover:bg-zinc-800/20 transition-all font-medium"
              >
                {t('common.cancel')}
              </button>
            </div>
          </ModalPanel>
        </div>
      )}

      {/* Edit Collection Modal */}
      {editingCollection && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md"
          style={{ marginLeft: 'var(--sidebar-width, 0px)' }}
          onClick={(e) => { if (e.target === e.currentTarget) setEditingCollection(null); }}
        >
          <ModalPanel className="w-full max-w-lg">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-bold text-gray-800 dark:text-white">
                {t('collection.edit')}
              </h2>
              <button
                onClick={() => setEditingCollection(null)}
                className="p-2 hover:bg-white/20 rounded-lg transition-colors"
              >
                <X className="w-5 h-5 text-gray-500" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('collection.name')}
                </label>
                <input
                  type="text"
                  value={editCollName}
                  onChange={(e) => setEditCollName(e.target.value)}
                  className="w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent transition-all"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('collection.description')}
                </label>
                <textarea
                  value={editCollDesc}
                  onChange={(e) => setEditCollDesc(e.target.value)}
                  rows={3}
                  className="w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent transition-all resize-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('collection.accessLevel')}
                </label>
                <div className="flex gap-3">
                  {accessOptions.map((opt) => (
                    <label key={opt.value} className="flex-1 cursor-pointer">
                      <input
                        type="radio"
                        name="collAccess"
                        value={opt.value}
                        checked={editCollAccess === opt.value}
                        onChange={(e) => setEditCollAccess(e.target.value)}
                        className="sr-only peer"
                      />
                      <div className="p-3 border-2 border-zinc-300 dark:border-zinc-700 rounded-lg text-center text-sm transition-all peer-checked:border-amber-500 peer-checked:bg-amber-500/10 hover:border-amber-400">
                        {opt.label}
                      </div>
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('departments.label')}
                </label>
                <DepartmentSelect value={editCollDept} onChange={setEditCollDept} />
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button
                onClick={handleSaveCollection}
                disabled={!editCollName.trim() || isSaving}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-amber-500 text-white rounded-lg hover:bg-amber-600 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                {t('common.save')}
              </button>
              <button
                onClick={() => setEditingCollection(null)}
                className="flex-1 px-4 py-3 bg-white/10 dark:bg-zinc-800/10 text-zinc-700 dark:text-zinc-300 rounded-lg hover:bg-white/20 dark:hover:bg-zinc-800/20 transition-all font-medium"
              >
                {t('common.cancel')}
              </button>
            </div>
          </ModalPanel>
        </div>
      )}

      {/* Edit Document Modal */}
      {editingDocument && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md"
          style={{ marginLeft: 'var(--sidebar-width, 0px)' }}
          onClick={(e) => { if (e.target === e.currentTarget) setEditingDocument(null); }}
        >
          <ModalPanel className="w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-bold text-gray-800 dark:text-white">
                {t('document.edit')}
              </h2>
              <button
                onClick={() => setEditingDocument(null)}
                className="p-2 hover:bg-white/20 rounded-lg transition-colors"
              >
                <X className="w-5 h-5 text-gray-500" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('document.editTitle')}
                </label>
                <input
                  type="text"
                  value={editDocTitle}
                  onChange={(e) => setEditDocTitle(e.target.value)}
                  className="w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('document.editDescription')}
                </label>
                <textarea
                  value={editDocDesc}
                  onChange={(e) => setEditDocDesc(e.target.value)}
                  rows={3}
                  className="w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all resize-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('document.editTags')}
                </label>
                <input
                  type="text"
                  value={editDocTags}
                  onChange={(e) => setEditDocTags(e.target.value)}
                  placeholder={t('document.editTagsPlaceholder')}
                  className="w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('document.editAccessLevel')}
                </label>
                <div className="flex gap-3">
                  {accessOptions.map((opt) => (
                    <label key={opt.value} className="flex-1 cursor-pointer">
                      <input
                        type="radio"
                        name="docAccess"
                        value={opt.value}
                        checked={editDocAccess === opt.value}
                        onChange={(e) => setEditDocAccess(e.target.value)}
                        className="sr-only peer"
                      />
                      <div className="p-3 border-2 border-zinc-300 dark:border-zinc-700 rounded-lg text-center text-sm transition-all peer-checked:border-indigo-500 peer-checked:bg-indigo-500/10 hover:border-indigo-400">
                        {opt.label}
                      </div>
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('departments.label')}
                </label>
                <DepartmentSelect value={editDocDept} onChange={setEditDocDept} />
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button
                onClick={handleSaveDocument}
                disabled={!editDocTitle.trim() || isSaving}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                {t('common.save')}
              </button>
              <button
                onClick={() => setEditingDocument(null)}
                className="flex-1 px-4 py-3 bg-white/10 dark:bg-zinc-800/10 text-zinc-700 dark:text-zinc-300 rounded-lg hover:bg-white/20 dark:hover:bg-zinc-800/20 transition-all font-medium"
              >
                {t('common.cancel')}
              </button>
            </div>
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
      {(isLoading || isLoadingCollections) && documents.length === 0 && collections.length === 0 && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 text-indigo-500 animate-spin" />
          <span className="ml-3 text-gray-500 dark:text-gray-400">{t('common.loading')}</span>
        </div>
      )}

      {/* Root View: Collections + Standalone Documents */}
      {!activeCollectionId && (
        <>
          {/* Collections Section */}
          {collections.length > 0 && (
            <div className="mb-8">
              <h2 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-4">
                {t('collection.collections')}
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                {collections.map((collection) => (
                  <CollectionCard
                    key={collection.id}
                    collection={collection}
                    onClick={handleCollectionClick}
                    onEdit={openEditCollection}
                    onDelete={handleCollectionDelete}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Standalone Documents Section */}
          {(!isLoading || documents.length > 0) && (
            <div>
              {collections.length > 0 && documents.length > 0 && (
                <h2 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-4">
                  {t('collection.standaloneDocuments')}
                </h2>
              )}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                {filteredDocuments.length === 0 ? (
                  <div className="col-span-full text-center py-12">
                    <p className="text-gray-500 dark:text-gray-400">
                      {documents.length === 0 && collections.length === 0
                        ? t('collection.noDocuments')
                        : documents.length === 0
                          ? ''
                          : t('collection.noMatch')}
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
                      onEdit={openEditDocument}
                      onReprocess={handleReprocess}
                    />
                  ))
                )}
              </div>
            </div>
          )}
        </>
      )}

      {/* Collection View: Items inside the selected collection */}
      {activeCollectionId && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {filteredDocuments.length === 0 ? (
            <div className="col-span-full text-center py-12">
              <p className="text-gray-500 dark:text-gray-400">
                {isLoading
                  ? ''
                  : documents.length === 0
                    ? t('collection.noFiles')
                    : t('collection.noMatch')}
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
                onEdit={openEditDocument}
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
        activeCollectionId={activeCollectionId}
        collections={collections}
      />
    </div>
  );
};
