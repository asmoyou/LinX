import { create } from 'zustand';
import type { Document, DocumentType, DocumentStatus } from '../types/document';

interface KnowledgeState {
  documents: Document[];
  selectedDocument: Document | null;
  isLoading: boolean;
  error: string | null;
  
  // Upload state
  uploadQueue: Document[];
  isUploading: boolean;
  
  // Filters
  typeFilter: DocumentType | 'all';
  statusFilter: DocumentStatus | 'all';
  searchQuery: string;
  
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
  uploadQueue: [],
  isUploading: false,
  typeFilter: 'all',
  statusFilter: 'all',
  searchQuery: '',
  
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
    
    // Filter by search query
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
    uploadQueue: [],
    isUploading: false,
    typeFilter: 'all',
    statusFilter: 'all',
    searchQuery: '',
  }),
}));
