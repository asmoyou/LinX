import { create } from 'zustand';
import type { MemoryRecord, MemorySurfaceType, MemoryRecordFilter } from '../types/memory';

interface MemoryWorkbenchState {
  records: MemoryRecord[];
  selectedRecord: MemoryRecord | null;
  isLoading: boolean;
  error: string | null;

  activeTab: MemorySurfaceType;
  filters: MemoryRecordFilter;
  searchQuery: string;

  setRecords: (records: MemoryRecord[]) => void;
  setRecordsByType: (type: MemorySurfaceType, records: MemoryRecord[]) => void;
  addRecord: (record: MemoryRecord) => void;
  updateRecord: (id: string, updates: Partial<MemoryRecord>) => void;
  removeRecord: (id: string) => void;
  setSelectedRecord: (record: MemoryRecord | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clearError: () => void;

  setActiveTab: (tab: MemorySurfaceType) => void;
  setFilters: (filters: Partial<MemoryRecordFilter>) => void;
  clearFilters: () => void;
  setSearchQuery: (query: string) => void;

  getFilteredRecords: () => MemoryRecord[];
  getRecordById: (id: string) => MemoryRecord | undefined;
  getRecordsByType: (type: MemorySurfaceType) => MemoryRecord[];
  getRecordsByAgent: (agentId: string) => MemoryRecord[];

  reset: () => void;
}

export const useMemoryWorkbenchStore = create<MemoryWorkbenchState>((set, get) => ({
  records: [],
  selectedRecord: null,
  isLoading: false,
  error: null,
  activeTab: 'user_memory',
  filters: {},
  searchQuery: '',

  setRecords: (records) => set({ records }),

  setRecordsByType: (type, records) => set((state) => ({
    records: [
      ...state.records.filter((record) => record.type !== type),
      ...records,
    ],
  })),

  addRecord: (record) => set((state) => ({
    records: [...state.records, record],
  })),

  updateRecord: (id, updates) => set((state) => ({
    records: state.records.map((record) =>
      record.id === id ? { ...record, ...updates } : record
    ),
    selectedRecord: state.selectedRecord?.id === id
      ? { ...state.selectedRecord, ...updates }
      : state.selectedRecord,
  })),

  removeRecord: (id) => set((state) => ({
    records: state.records.filter((record) => record.id !== id),
    selectedRecord: state.selectedRecord?.id === id ? null : state.selectedRecord,
  })),

  setSelectedRecord: (record) => set({ selectedRecord: record }),

  setLoading: (loading) => set({ isLoading: loading }),

  setError: (error) => set({ error }),

  clearError: () => set({ error: null }),

  setActiveTab: (tab) => set({ activeTab: tab }),

  setFilters: (filters) => set((state) => ({
    filters: { ...state.filters, ...filters },
  })),

  clearFilters: () => set({ filters: {} }),

  setSearchQuery: (query) => set({ searchQuery: query }),

  getFilteredRecords: () => {
    const { records, activeTab, filters, searchQuery } = get();

    let filtered = records.filter((record) => record.type === activeTab);

    if (filters.agentId) {
      filtered = filtered.filter((record) => record.agentId === filters.agentId);
    }

    if (filters.userId) {
      filtered = filtered.filter((record) => record.userId === filters.userId);
    }

    if (filters.tags && filters.tags.length > 0) {
      filtered = filtered.filter((record) =>
        filters.tags!.some((tag) => record.tags.includes(tag))
      );
    }

    if (filters.dateFrom) {
      filtered = filtered.filter(
        (record) => new Date(record.createdAt) >= new Date(filters.dateFrom!)
      );
    }

    if (filters.dateTo) {
      filtered = filtered.filter(
        (record) => new Date(record.createdAt) <= new Date(filters.dateTo!)
      );
    }

    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (record) =>
          record.content.toLowerCase().includes(query) ||
          record.summary?.toLowerCase().includes(query) ||
          record.tags.some((tag) => tag.toLowerCase().includes(query))
      );
    }

    filtered.sort((a, b) => {
      if (a.relevanceScore !== undefined && b.relevanceScore !== undefined) {
        return b.relevanceScore - a.relevanceScore;
      }
      return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
    });

    return filtered;
  },

  getRecordById: (id) => {
    return get().records.find((record) => record.id === id);
  },

  getRecordsByType: (type) => {
    return get().records.filter((record) => record.type === type);
  },

  getRecordsByAgent: (agentId) => {
    return get().records.filter((record) => record.agentId === agentId);
  },

  reset: () => set({
    records: [],
    selectedRecord: null,
    isLoading: false,
    error: null,
    activeTab: 'user_memory',
    filters: {},
    searchQuery: '',
  }),
}));
