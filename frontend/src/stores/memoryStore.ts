import { create } from 'zustand';
import type { Memory, MemoryType, MemoryFilter } from '../types/memory';

interface MemoryState {
  memories: Memory[];
  selectedMemory: Memory | null;
  isLoading: boolean;
  error: string | null;
  
  // Filters
  activeTab: MemoryType;
  filters: MemoryFilter;
  searchQuery: string;
  
  // Actions
  setMemories: (memories: Memory[]) => void;
  addMemory: (memory: Memory) => void;
  updateMemory: (id: string, updates: Partial<Memory>) => void;
  removeMemory: (id: string) => void;
  setSelectedMemory: (memory: Memory | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clearError: () => void;
  
  // Filters
  setActiveTab: (tab: MemoryType) => void;
  setFilters: (filters: Partial<MemoryFilter>) => void;
  clearFilters: () => void;
  setSearchQuery: (query: string) => void;
  
  // Computed
  getFilteredMemories: () => Memory[];
  getMemoryById: (id: string) => Memory | undefined;
  getMemoriesByType: (type: MemoryType) => Memory[];
  getMemoriesByAgent: (agentId: string) => Memory[];
  
  // Reset
  reset: () => void;
}

export const useMemoryStore = create<MemoryState>((set, get) => ({
  memories: [],
  selectedMemory: null,
  isLoading: false,
  error: null,
  activeTab: 'agent',
  filters: {},
  searchQuery: '',
  
  setMemories: (memories) => set({ memories }),
  
  addMemory: (memory) => set((state) => ({
    memories: [...state.memories, memory],
  })),
  
  updateMemory: (id, updates) => set((state) => ({
    memories: state.memories.map((memory) =>
      memory.id === id ? { ...memory, ...updates } : memory
    ),
    selectedMemory: state.selectedMemory?.id === id
      ? { ...state.selectedMemory, ...updates }
      : state.selectedMemory,
  })),
  
  removeMemory: (id) => set((state) => ({
    memories: state.memories.filter((memory) => memory.id !== id),
    selectedMemory: state.selectedMemory?.id === id ? null : state.selectedMemory,
  })),
  
  setSelectedMemory: (memory) => set({ selectedMemory: memory }),
  
  setLoading: (loading) => set({ isLoading: loading }),
  
  setError: (error) => set({ error }),
  
  clearError: () => set({ error: null }),
  
  setActiveTab: (tab) => set({ activeTab: tab }),
  
  setFilters: (filters) => set((state) => ({
    filters: { ...state.filters, ...filters },
  })),
  
  clearFilters: () => set({ filters: {} }),
  
  setSearchQuery: (query) => set({ searchQuery: query }),
  
  getFilteredMemories: () => {
    const { memories, activeTab, filters, searchQuery } = get();
    
    let filtered = memories;
    
    // Filter by active tab (memory type)
    filtered = filtered.filter((memory) => memory.type === activeTab);
    
    // Apply additional filters
    if (filters.agentId) {
      filtered = filtered.filter((memory) => memory.agentId === filters.agentId);
    }
    
    if (filters.userId) {
      filtered = filtered.filter((memory) => memory.userId === filters.userId);
    }
    
    if (filters.tags && filters.tags.length > 0) {
      filtered = filtered.filter((memory) =>
        filters.tags!.some((tag) => memory.tags.includes(tag))
      );
    }
    
    if (filters.dateFrom) {
      filtered = filtered.filter(
        (memory) => new Date(memory.createdAt) >= new Date(filters.dateFrom!)
      );
    }
    
    if (filters.dateTo) {
      filtered = filtered.filter(
        (memory) => new Date(memory.createdAt) <= new Date(filters.dateTo!)
      );
    }
    
    // Filter by search query
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (memory) =>
          memory.content.toLowerCase().includes(query) ||
          memory.summary?.toLowerCase().includes(query) ||
          memory.tags.some((tag) => tag.toLowerCase().includes(query))
      );
    }
    
    // Sort by relevance score if available, otherwise by date
    filtered.sort((a, b) => {
      if (a.relevanceScore !== undefined && b.relevanceScore !== undefined) {
        return b.relevanceScore - a.relevanceScore;
      }
      return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
    });
    
    return filtered;
  },
  
  getMemoryById: (id) => {
    return get().memories.find((memory) => memory.id === id);
  },
  
  getMemoriesByType: (type) => {
    return get().memories.filter((memory) => memory.type === type);
  },
  
  getMemoriesByAgent: (agentId) => {
    return get().memories.filter((memory) => memory.agentId === agentId);
  },
  
  reset: () => set({
    memories: [],
    selectedMemory: null,
    isLoading: false,
    error: null,
    activeTab: 'agent',
    filters: {},
    searchQuery: '',
  }),
}));
