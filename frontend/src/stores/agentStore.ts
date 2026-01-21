import { create } from 'zustand';
import type { Agent } from '../types/agent';

interface AgentState {
  agents: Agent[];
  selectedAgent: Agent | null;
  isLoading: boolean;
  error: string | null;
  
  // Filters
  statusFilter: 'all' | 'working' | 'idle' | 'offline';
  searchQuery: string;
  
  // Actions
  setAgents: (agents: Agent[]) => void;
  addAgent: (agent: Agent) => void;
  updateAgent: (id: string, updates: Partial<Agent>) => void;
  removeAgent: (id: string) => void;
  setSelectedAgent: (agent: Agent | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clearError: () => void;
  
  // Filters
  setStatusFilter: (status: 'all' | 'working' | 'idle' | 'offline') => void;
  setSearchQuery: (query: string) => void;
  
  // Computed
  getFilteredAgents: () => Agent[];
  getAgentById: (id: string) => Agent | undefined;
  getAgentsByStatus: (status: Agent['status']) => Agent[];
  
  // Real-time updates
  handleAgentUpdate: (update: { id: string; updates: Partial<Agent> }) => void;
  
  // Reset
  reset: () => void;
}

export const useAgentStore = create<AgentState>((set, get) => ({
  agents: [],
  selectedAgent: null,
  isLoading: false,
  error: null,
  statusFilter: 'all',
  searchQuery: '',
  
  setAgents: (agents) => set({ agents }),
  
  addAgent: (agent) => set((state) => ({
    agents: [...state.agents, agent],
  })),
  
  updateAgent: (id, updates) => set((state) => ({
    agents: state.agents.map((agent) =>
      agent.id === id ? { ...agent, ...updates } : agent
    ),
    selectedAgent: state.selectedAgent?.id === id
      ? { ...state.selectedAgent, ...updates }
      : state.selectedAgent,
  })),
  
  removeAgent: (id) => set((state) => ({
    agents: state.agents.filter((agent) => agent.id !== id),
    selectedAgent: state.selectedAgent?.id === id ? null : state.selectedAgent,
  })),
  
  setSelectedAgent: (agent) => set({ selectedAgent: agent }),
  
  setLoading: (loading) => set({ isLoading: loading }),
  
  setError: (error) => set({ error }),
  
  clearError: () => set({ error: null }),
  
  setStatusFilter: (status) => set({ statusFilter: status }),
  
  setSearchQuery: (query) => set({ searchQuery: query }),
  
  getFilteredAgents: () => {
    const { agents, statusFilter, searchQuery } = get();
    
    let filtered = agents;
    
    // Filter by status
    if (statusFilter !== 'all') {
      filtered = filtered.filter((agent) => agent.status === statusFilter);
    }
    
    // Filter by search query
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (agent) =>
          agent.name.toLowerCase().includes(query) ||
          agent.type.toLowerCase().includes(query) ||
          agent.currentTask?.toLowerCase().includes(query)
      );
    }
    
    return filtered;
  },
  
  getAgentById: (id) => {
    return get().agents.find((agent) => agent.id === id);
  },
  
  getAgentsByStatus: (status) => {
    return get().agents.filter((agent) => agent.status === status);
  },
  
  handleAgentUpdate: ({ id, updates }) => {
    get().updateAgent(id, updates);
  },
  
  reset: () => set({
    agents: [],
    selectedAgent: null,
    isLoading: false,
    error: null,
    statusFilter: 'all',
    searchQuery: '',
  }),
}));
