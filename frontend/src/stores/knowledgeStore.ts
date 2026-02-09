import { create } from 'zustand';
import type { Document, DocumentType, DocumentStatus } from '../types/document';
import { knowledgeApi } from '../api/knowledge';
import type { UploadDocumentRequest } from '../api/knowledge';

interface KnowledgeState {
  documents: Document[];
  selectedDocument: Document | null;
  isLoading: boolean;
  error: string | null;
  totalDocuments: number;
  currentPage: number;
  pageSize: number;

  // Upload state
  uploadQueue: Document[];
  isUploading: boolean;

  // Download state
  isDownloading: boolean;
  downloadingId: string | null;

  // Filters
  typeFilter: DocumentType | 'all';
  statusFilter: DocumentStatus | 'all';
  searchQuery: string;

  // Async API actions
  fetchDocuments: (params?: {
    page?: number;
    search?: string;
    type?: string;
    access_level?: string;
    department_id?: string;
  }) => Promise<void>;
  uploadDocument: (data: UploadDocumentRequest) => Promise<Document>;
  deleteDocument: (id: string) => Promise<void>;
  downloadDocument: (id: string, filename?: string) => Promise<void>;
  reprocessDocument: (id: string) => Promise<void>;
  pollProcessingStatus: (id: string) => Promise<void>;
  pollAllProcessing: () => void;

  // Actions - Documents
  setDocuments: (documents: Document[]) => void;
  addDocument: (document: Document) => void;
  updateDocument: (id: string, updates: Partial<Document>) => void;
  removeDocument: (id: string) => void;
  setSelectedDocument: (document: Document | null) => void;

  // Upload actions
  addToUploadQueue: (document: Document) => void;
  removeFromUploadQueue: (id: string) => void;
  updateUploadProgress: (id: string, progress: number) => void;
  setUploading: (uploading: boolean) => void;

  // Common actions
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clearError: () => void;

  // Filters
  setTypeFilter: (type: DocumentType | 'all') => void;
  setStatusFilter: (status: DocumentStatus | 'all') => void;
  setSearchQuery: (query: string) => void;

  // Computed
  getFilteredDocuments: () => Document[];
  getDocumentById: (id: string) => Document | undefined;
  getDocumentsByType: (type: DocumentType) => Document[];
  getDocumentsByStatus: (status: DocumentStatus) => Document[];

  // Reset
  reset: () => void;
}

export const useKnowledgeStore = create<KnowledgeState>((set, get) => ({
  documents: [],
  selectedDocument: null,
  isLoading: false,
  error: null,
  totalDocuments: 0,
  currentPage: 1,
  pageSize: 20,
  uploadQueue: [],
  isUploading: false,
  isDownloading: false,
  downloadingId: null,
  typeFilter: 'all',
  statusFilter: 'all',
  searchQuery: '',

  // Async API actions
  fetchDocuments: async (params) => {
    set({ isLoading: true, error: null });
    try {
      const response = await knowledgeApi.getAll({
        page: params?.page || get().currentPage,
        page_size: get().pageSize,
        search: params?.search,
        type: params?.type,
        access_level: params?.access_level,
        department_id: params?.department_id,
      });
      set({
        documents: response.items,
        totalDocuments: response.total,
        currentPage: response.page,
        isLoading: false,
      });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to fetch documents';
      set({ error: message, isLoading: false });
    }
  },

  uploadDocument: async (data: UploadDocumentRequest) => {
    set({ isUploading: true, error: null });
    try {
      const doc = await knowledgeApi.upload(data);
      set((state) => ({
        documents: [doc, ...state.documents],
        totalDocuments: state.totalDocuments + 1,
        isUploading: false,
      }));

      // Start polling for processing status if document is still processing
      if (doc.status === 'processing' || doc.status === 'uploading') {
        get().pollProcessingStatus(doc.id);
      }

      return doc;
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to upload document';
      set({ error: message, isUploading: false });
      throw error;
    }
  },

  deleteDocument: async (id: string) => {
    try {
      await knowledgeApi.delete(id);
      set((state) => ({
        documents: state.documents.filter((doc) => doc.id !== id),
        selectedDocument: state.selectedDocument?.id === id ? null : state.selectedDocument,
        totalDocuments: state.totalDocuments - 1,
      }));
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to delete document';
      set({ error: message });
      throw error;
    }
  },

  downloadDocument: async (id: string, filename?: string) => {
    // Prevent duplicate downloads
    if (get().downloadingId === id) return;

    set({ isDownloading: true, downloadingId: id });
    try {
      const blob = await knowledgeApi.download(id);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename || 'download';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to download document';
      set({ error: message });
      throw error;
    } finally {
      set({ isDownloading: false, downloadingId: null });
    }
  },

  reprocessDocument: async (id: string) => {
    try {
      const updated = await knowledgeApi.reprocess(id);
      get().updateDocument(id, {
        status: updated.status as DocumentStatus,
        error: undefined,
        errorMessage: undefined,
        chunkCount: undefined,
        tokenCount: undefined,
      });
      // Start polling for the reprocessing result
      get().pollProcessingStatus(id);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to reprocess document';
      set({ error: message });
      throw error;
    }
  },

  pollProcessingStatus: async (id: string) => {
    const maxAttempts = 30;
    let attempts = 0;

    const poll = async () => {
      if (attempts >= maxAttempts) return;
      attempts++;

      try {
        const status = await knowledgeApi.getProcessingStatus(id);

        if (status.status === 'completed' || status.status === 'failed') {
          get().updateDocument(id, {
            status: status.status as DocumentStatus,
            processedAt: status.processed_at || status.completed_at || new Date().toISOString(),
            error: status.error_message || undefined,
            errorMessage: status.error_message || undefined,
            chunkCount: status.chunk_count,
            tokenCount: status.token_count,
          });
          return;
        }

        // Continue polling
        setTimeout(poll, 2000);
      } catch {
        // Stop polling on error
      }
    };

    setTimeout(poll, 2000);
  },

  pollAllProcessing: () => {
    const { documents, pollProcessingStatus } = get();
    documents
      .filter((doc) => doc.status === 'processing' || doc.status === 'uploading')
      .forEach((doc) => pollProcessingStatus(doc.id));
  },

  setDocuments: (documents) => set({ documents }),

  addDocument: (document) => set((state) => ({
    documents: [...state.documents, document],
  })),

  updateDocument: (id, updates) => set((state) => ({
    documents: state.documents.map((doc) =>
      doc.id === id ? { ...doc, ...updates } : doc
    ),
    selectedDocument: state.selectedDocument?.id === id
      ? { ...state.selectedDocument, ...updates }
      : state.selectedDocument,
    uploadQueue: state.uploadQueue.map((doc) =>
      doc.id === id ? { ...doc, ...updates } : doc
    ),
  })),

  removeDocument: (id) => set((state) => ({
    documents: state.documents.filter((doc) => doc.id !== id),
    selectedDocument: state.selectedDocument?.id === id ? null : state.selectedDocument,
  })),

  setSelectedDocument: (document) => set({ selectedDocument: document }),

  addToUploadQueue: (document) => set((state) => ({
    uploadQueue: [...state.uploadQueue, document],
  })),

  removeFromUploadQueue: (id) => set((state) => ({
    uploadQueue: state.uploadQueue.filter((doc) => doc.id !== id),
  })),

  updateUploadProgress: (id, progress) => {
    get().updateDocument(id, { uploadProgress: progress });
  },

  setUploading: (uploading) => set({ isUploading: uploading }),

  setLoading: (loading) => set({ isLoading: loading }),

  setError: (error) => set({ error }),

  clearError: () => set({ error: null }),

  setTypeFilter: (type) => set({ typeFilter: type }),

  setStatusFilter: (status) => set({ statusFilter: status }),

  setSearchQuery: (query) => set({ searchQuery: query }),

  getFilteredDocuments: () => {
    const { documents, typeFilter, statusFilter, searchQuery } = get();

    let filtered = documents;

    // Filter by type
    if (typeFilter !== 'all') {
      filtered = filtered.filter((doc) => doc.type === typeFilter);
    }

    // Filter by status
    if (statusFilter !== 'all') {
      filtered = filtered.filter((doc) => doc.status === statusFilter);
    }

    // Filter by search query (local filter on top of server-side)
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (doc) =>
          doc.name.toLowerCase().includes(query) ||
          doc.description?.toLowerCase().includes(query) ||
          doc.tags?.some((tag) => tag.toLowerCase().includes(query))
      );
    }

    return filtered;
  },

  getDocumentById: (id) => {
    return get().documents.find((doc) => doc.id === id);
  },

  getDocumentsByType: (type) => {
    return get().documents.filter((doc) => doc.type === type);
  },

  getDocumentsByStatus: (status) => {
    return get().documents.filter((doc) => doc.status === status);
  },

  reset: () => set({
    documents: [],
    selectedDocument: null,
    isLoading: false,
    error: null,
    totalDocuments: 0,
    currentPage: 1,
    uploadQueue: [],
    isUploading: false,
    isDownloading: false,
    downloadingId: null,
    typeFilter: 'all',
    statusFilter: 'all',
    searchQuery: '',
  }),
}));
