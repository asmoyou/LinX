import { create } from "zustand";
import type {
  Document,
  DocumentType,
  DocumentStatus,
  Collection,
} from "../types/document";
import { knowledgeApi } from "../api/knowledge";
import type {
  UploadDocumentRequest,
  ZipUploadResponse,
} from "../api/knowledge";

const MAX_POLL_ATTEMPTS = 60;
const POLL_INTERVAL_MS = 2000;
const DOWNLOAD_DEBOUNCE_MS = 1200;
let batchPollTimer: ReturnType<typeof setTimeout> | null = null;
let batchPollInFlight = false;
let batchPollAttempts = 0;
const downloadState = new Map<string, { lastTriggeredAt: number }>();

const clampProgress = (value: number): number =>
  Math.max(0, Math.min(100, value));

const fallbackProgressForStatus = (status: DocumentStatus): number => {
  if (status === "uploading") return 0;
  if (status === "processing") return 50;
  if (status === "completed") return 100;
  return 100;
};

const normalizeStatus = (status: string): DocumentStatus => {
  if (status === "cancelled" || status === "canceled") {
    return "failed";
  }
  if (status === "completed" || status === "failed" || status === "uploading") {
    return status;
  }
  return "processing";
};

const normalizeProcessingProgress = (doc: Document): Document => {
  const status = doc.status;
  const fallback = fallbackProgressForStatus(status);
  const current =
    doc.processingProgress != null
      ? clampProgress(doc.processingProgress)
      : fallback;

  if (status === "processing") {
    return { ...doc, processingProgress: Math.max(1, Math.min(99, current)) };
  }
  if (status === "uploading") {
    return { ...doc, processingProgress: 0 };
  }
  if (status === "completed") {
    return { ...doc, processingProgress: 100 };
  }
  return { ...doc, processingProgress: current };
};

const isDocumentVisibleInCurrentView = (
  doc: Document,
  activeCollectionId: string | null,
): boolean => {
  if (activeCollectionId === null) {
    return !doc.collectionId;
  }
  return doc.collectionId === activeCollectionId;
};

const upsertCollection = (
  collections: Collection[],
  incoming: Collection,
): Collection[] => {
  const filtered = collections.filter(
    (collection) => collection.id !== incoming.id,
  );
  return [incoming, ...filtered];
};

const stopPollingDocument = (_id: string): void => {
  if (batchPollTimer) {
    clearTimeout(batchPollTimer);
    batchPollTimer = null;
  }
};

const stopAllPolling = (): void => {
  if (batchPollTimer) {
    clearTimeout(batchPollTimer);
    batchPollTimer = null;
  }
  batchPollInFlight = false;
  batchPollAttempts = 0;
};

interface KnowledgeState {
  documents: Document[];
  selectedDocument: Document | null;
  isLoading: boolean;
  error: string | null;
  totalDocuments: number;
  currentPage: number;
  pageSize: number;

  // Collection state
  collections: Collection[];
  activeCollectionId: string | null; // null = root view
  isLoadingCollections: boolean;

  // Upload state
  uploadQueue: Document[];
  isUploading: boolean;

  // Download state
  isDownloading: boolean;
  downloadingId: string | null;

  // Filters
  typeFilter: DocumentType | "all";
  statusFilter: DocumentStatus | "all";
  searchQuery: string;

  // Async API actions
  fetchDocuments: (params?: {
    page?: number;
    search?: string;
    type?: string;
    access_level?: string;
    department_id?: string;
  }) => Promise<void>;
  uploadDocument: (
    data: UploadDocumentRequest,
  ) => Promise<Document | ZipUploadResponse>;
  deleteDocument: (id: string) => Promise<void>;
  downloadDocument: (id: string, filename?: string) => Promise<boolean>;
  reprocessDocument: (id: string) => Promise<void>;
  cancelProcessingDocument: (id: string) => Promise<void>;
  pollProcessingStatus: (id: string) => Promise<void>;
  pollAllProcessing: () => void;

  // Collection actions
  fetchCollections: () => Promise<void>;
  createCollection: (name: string, description?: string) => Promise<Collection>;
  updateCollection: (
    id: string,
    data: { name?: string; description?: string },
  ) => Promise<void>;
  deleteCollection: (id: string) => Promise<void>;
  moveDocumentToCollection: (
    documentId: string,
    collectionId: string,
  ) => Promise<Document>;
  setActiveCollection: (id: string | null) => void;

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
  setTypeFilter: (type: DocumentType | "all") => void;
  setStatusFilter: (status: DocumentStatus | "all") => void;
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
  collections: [],
  activeCollectionId: null,
  isLoadingCollections: false,
  uploadQueue: [],
  isUploading: false,
  isDownloading: false,
  downloadingId: null,
  typeFilter: "all",
  statusFilter: "all",
  searchQuery: "",

  // Async API actions
  fetchDocuments: async (params) => {
    set({ isLoading: true, error: null });
    try {
      const { activeCollectionId } = get();
      const response = await knowledgeApi.getAll({
        page: params?.page || get().currentPage,
        page_size: get().pageSize,
        search: params?.search,
        type: params?.type,
        access_level: params?.access_level,
        department_id: params?.department_id,
        // When at root level, only show items without a collection
        collection_id:
          activeCollectionId === null ? "none" : activeCollectionId,
      });
      set({
        documents: response.items.map(normalizeProcessingProgress),
        totalDocuments: response.total,
        currentPage: response.page,
        isLoading: false,
      });
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : "Failed to fetch documents";
      set({ error: message, isLoading: false });
    }
  },

  uploadDocument: async (data: UploadDocumentRequest) => {
    set({ isUploading: true, error: null });
    try {
      const { activeCollectionId } = get();
      // If inside a collection, set collection_id on upload
      const uploadData = {
        ...data,
        collection_id: activeCollectionId || data.collection_id,
      };
      const result = await knowledgeApi.upload(uploadData);

      // Check if ZIP upload response
      if ("collection" in result) {
        // ZIP upload: only show items in the current view.
        const zipResult = result as ZipUploadResponse;
        const visibleItems = zipResult.items
          .map(normalizeProcessingProgress)
          .filter((item) =>
            isDocumentVisibleInCurrentView(item, activeCollectionId),
          );

        set((state) => ({
          documents: [...visibleItems, ...state.documents],
          totalDocuments: state.totalDocuments + visibleItems.length,
          collections: upsertCollection(
            state.collections,
            zipResult.collection,
          ),
          isUploading: false,
        }));

        // Start polling only for visible extracted items in this view.
        visibleItems.forEach((item) => {
          if (item.status === "processing" || item.status === "uploading") {
            get().pollProcessingStatus(item.id);
          }
        });

        return result;
      } else {
        // Regular file upload
        const doc = normalizeProcessingProgress(result as Document);
        const shouldDisplay = isDocumentVisibleInCurrentView(
          doc,
          activeCollectionId,
        );
        set((state) => ({
          documents: shouldDisplay
            ? [doc, ...state.documents]
            : state.documents,
          totalDocuments: shouldDisplay
            ? state.totalDocuments + 1
            : state.totalDocuments,
          isUploading: false,
        }));

        // Start polling only for documents visible in this view.
        if (
          shouldDisplay &&
          (doc.status === "processing" || doc.status === "uploading")
        ) {
          get().pollProcessingStatus(doc.id);
        }

        return doc;
      }
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : "Failed to upload document";
      set({ error: message, isUploading: false });
      throw error;
    }
  },

  deleteDocument: async (id: string) => {
    try {
      await knowledgeApi.delete(id);
      stopPollingDocument(id);
      downloadState.delete(id);
      set((state) => ({
        documents: state.documents.filter((doc) => doc.id !== id),
        selectedDocument:
          state.selectedDocument?.id === id ? null : state.selectedDocument,
        totalDocuments: state.totalDocuments - 1,
      }));
      if (
        get().documents.some(
          (doc) => doc.status === "processing" || doc.status === "uploading",
        )
      ) {
        get().pollAllProcessing();
      }
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : "Failed to delete document";
      set({ error: message });
      throw error;
    }
  },

  downloadDocument: async (id: string, filename?: string) => {
    const now = Date.now();
    const existing = downloadState.get(id);

    // Prevent duplicate downloads for the same document while in-flight.
    if (get().downloadingId === id) return false;

    // Debounce rapid repeated clicks on the same document.
    if (existing && now - existing.lastTriggeredAt < DOWNLOAD_DEBOUNCE_MS) {
      return false;
    }

    downloadState.set(id, { lastTriggeredAt: now });

    set({ isDownloading: true, downloadingId: id });
    try {
      const { blob, filename: serverFilename } =
        await knowledgeApi.download(id);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = serverFilename || filename || "download";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      return true;
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : "Failed to download document";
      set({ error: message });
      downloadState.delete(id);
      throw error;
    } finally {
      set({ isDownloading: false, downloadingId: null });
    }
  },

  reprocessDocument: async (id: string) => {
    try {
      stopPollingDocument(id);
      const currentDoc = get().documents.find((doc) => doc.id === id);
      const updated = await knowledgeApi.reprocess(id);
      get().updateDocument(id, {
        status: normalizeStatus(updated.status),
        processingProgress: 5,
        error: undefined,
        errorMessage: undefined,
        chunkCount: undefined,
        tokenCount: undefined,
        processingStartedAt: undefined,
        processingCompletedAt: undefined,
        previousProcessedAt:
          currentDoc?.processedAt ||
          currentDoc?.processingCompletedAt ||
          currentDoc?.previousProcessedAt,
      });
      // Start polling for the reprocessing result
      get().pollProcessingStatus(id);
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : "Failed to reprocess document";
      set({ error: message });
      throw error;
    }
  },

  cancelProcessingDocument: async (id: string) => {
    try {
      stopPollingDocument(id);
      const updated = await knowledgeApi.cancelProcessing(id);
      const normalizedStatus = normalizeStatus(updated.status);
      const fallbackError = "Processing cancelled by user.";
      get().updateDocument(id, {
        status: normalizedStatus,
        processingProgress: normalizedStatus === "failed" ? 100 : 99,
        processedAt: updated.processedAt,
        processingCompletedAt: updated.processedAt,
        error: updated.errorMessage || updated.error || fallbackError,
        errorMessage: updated.errorMessage || updated.error || fallbackError,
      });
      if (
        get().documents.some(
          (doc) => doc.status === "processing" || doc.status === "uploading",
        )
      ) {
        get().pollAllProcessing();
      }
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : "Failed to cancel processing";
      set({ error: message });
      throw error;
    }
  },

  pollProcessingStatus: async (id: string) => {
    const doc = get().documents.find((item) => item.id === id);
    if (!doc) return;
    if (doc.status !== "processing" && doc.status !== "uploading") return;
    get().pollAllProcessing();
  },

  pollAllProcessing: () => {
    if (batchPollInFlight || batchPollTimer) {
      return;
    }

    const poll = async () => {
      const activeDocs = get().documents.filter(
        (doc) => doc.status === "processing" || doc.status === "uploading",
      );

      if (activeDocs.length === 0) {
        stopAllPolling();
        return;
      }

      if (batchPollAttempts >= MAX_POLL_ATTEMPTS) {
        stopAllPolling();
        return;
      }

      batchPollInFlight = true;
      batchPollAttempts += 1;

      try {
        const response = await knowledgeApi.getProcessingStatuses(
          activeDocs.map((doc) => doc.id),
        );
        const statusById = new Map(
          response.items.map((item) => [item.knowledge_id, item]),
        );

        activeDocs.forEach((doc) => {
          const status = statusById.get(doc.id);
          if (!status) return;

          const normalizedStatus = normalizeStatus(status.status);
          const progress = clampProgress(
            status.progress_percent ??
              fallbackProgressForStatus(normalizedStatus),
          );

          get().updateDocument(doc.id, {
            status: normalizedStatus,
            processingProgress: progress,
            processedAt:
              status.processed_at || status.completed_at || undefined,
            processingStartedAt:
              status.started_at || status.created_at || undefined,
            processingCompletedAt:
              status.completed_at || status.processed_at || undefined,
            error: status.error_message || undefined,
            errorMessage: status.error_message || undefined,
            chunkCount: status.chunk_count,
            tokenCount: status.token_count,
          });
        });
      } catch {
        // Keep polling; transient failures are expected during heavy uploads.
      } finally {
        batchPollInFlight = false;
      }

      if (
        get().documents.some(
          (doc) => doc.status === "processing" || doc.status === "uploading",
        )
      ) {
        batchPollTimer = setTimeout(() => {
          batchPollTimer = null;
          void poll();
        }, POLL_INTERVAL_MS);
        return;
      }

      stopAllPolling();
    };

    void poll();
  },

  // Collection actions
  fetchCollections: async () => {
    set({ isLoadingCollections: true });
    try {
      const response = await knowledgeApi.getCollections({ page_size: 100 });
      set({ collections: response.collections, isLoadingCollections: false });
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : "Failed to fetch collections";
      set({ error: message, isLoadingCollections: false });
    }
  },

  createCollection: async (name: string, description?: string) => {
    try {
      const collection = await knowledgeApi.createCollection({
        name,
        description,
      });
      set((state) => ({
        collections: [collection, ...state.collections],
      }));
      return collection;
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : "Failed to create collection";
      set({ error: message });
      throw error;
    }
  },

  updateCollection: async (
    id: string,
    data: { name?: string; description?: string },
  ) => {
    try {
      const updated = await knowledgeApi.updateCollection(id, data);
      set((state) => ({
        collections: state.collections.map((c) => (c.id === id ? updated : c)),
      }));
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : "Failed to update collection";
      set({ error: message });
      throw error;
    }
  },

  deleteCollection: async (id: string) => {
    try {
      await knowledgeApi.deleteCollection(id);
      set((state) => ({
        collections: state.collections.filter((c) => c.id !== id),
        activeCollectionId:
          state.activeCollectionId === id ? null : state.activeCollectionId,
      }));
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : "Failed to delete collection";
      set({ error: message });
      throw error;
    }
  },

  moveDocumentToCollection: async (
    documentId: string,
    collectionId: string,
  ) => {
    const sourceDocument = get().documents.find((doc) => doc.id === documentId);
    if (!sourceDocument) {
      throw new Error("Document not found");
    }
    if (sourceDocument.collectionId === collectionId) {
      return sourceDocument;
    }

    try {
      const updated = await knowledgeApi.update(documentId, {
        collection_id: collectionId,
      });
      const previousCollectionId = sourceDocument.collectionId;

      set((state) => {
        const updatedCollections = state.collections.map((collection) => {
          if (collection.id === collectionId) {
            return { ...collection, itemCount: collection.itemCount + 1 };
          }
          if (previousCollectionId && collection.id === previousCollectionId) {
            return {
              ...collection,
              itemCount: Math.max(0, collection.itemCount - 1),
            };
          }
          return collection;
        });

        const updatedDocument = normalizeProcessingProgress({
          ...sourceDocument,
          ...updated,
          collectionId,
        });

        const isRootView = state.activeCollectionId === null;
        const nextDocuments = isRootView
          ? state.documents.filter((doc) => doc.id !== documentId)
          : state.documents.map((doc) =>
              doc.id === documentId ? updatedDocument : doc,
            );

        return {
          collections: updatedCollections,
          documents: nextDocuments,
          totalDocuments: isRootView
            ? Math.max(0, state.totalDocuments - 1)
            : state.totalDocuments,
          selectedDocument:
            state.selectedDocument?.id === documentId
              ? updatedDocument
              : state.selectedDocument,
        };
      });

      return updated;
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : "Failed to move document";
      set({ error: message });
      throw error;
    }
  },

  setActiveCollection: (id: string | null) => {
    set({ activeCollectionId: id, documents: [], currentPage: 1 });
  },

  setDocuments: (documents) =>
    set({ documents: documents.map(normalizeProcessingProgress) }),

  addDocument: (document) =>
    set((state) => ({
      documents: [...state.documents, normalizeProcessingProgress(document)],
    })),

  updateDocument: (id, updates) =>
    set((state) => ({
      documents: state.documents.map((doc) =>
        doc.id === id
          ? normalizeProcessingProgress({ ...doc, ...updates })
          : doc,
      ),
      selectedDocument:
        state.selectedDocument?.id === id
          ? normalizeProcessingProgress({
              ...state.selectedDocument,
              ...updates,
            })
          : state.selectedDocument,
      uploadQueue: state.uploadQueue.map((doc) =>
        doc.id === id
          ? normalizeProcessingProgress({ ...doc, ...updates })
          : doc,
      ),
    })),

  removeDocument: (id) => {
    stopPollingDocument(id);
    downloadState.delete(id);
    set((state) => ({
      documents: state.documents.filter((doc) => doc.id !== id),
      selectedDocument:
        state.selectedDocument?.id === id ? null : state.selectedDocument,
    }));
  },

  setSelectedDocument: (document) =>
    set({
      selectedDocument: document ? normalizeProcessingProgress(document) : null,
    }),

  addToUploadQueue: (document) =>
    set((state) => ({
      uploadQueue: [
        ...state.uploadQueue,
        normalizeProcessingProgress(document),
      ],
    })),

  removeFromUploadQueue: (id) =>
    set((state) => ({
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
    if (typeFilter !== "all") {
      filtered = filtered.filter((doc) => doc.type === typeFilter);
    }

    // Filter by status
    if (statusFilter !== "all") {
      filtered = filtered.filter((doc) => doc.status === statusFilter);
    }

    // Filter by search query (local filter on top of server-side)
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (doc) =>
          doc.name.toLowerCase().includes(query) ||
          doc.description?.toLowerCase().includes(query) ||
          doc.tags?.some((tag) => tag.toLowerCase().includes(query)),
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

  reset: () => {
    stopAllPolling();
    downloadState.clear();
    set({
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
      collections: [],
      activeCollectionId: null,
      isLoadingCollections: false,
      typeFilter: "all",
      statusFilter: "all",
      searchQuery: "",
    });
  },
}));
