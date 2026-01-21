import { create } from 'zustand';
import type { Task, Goal, TaskStatus } from '../types/task';

interface TaskState {
  goals: Goal[];
  tasks: Task[];
  selectedGoal: Goal | null;
  selectedTask: Task | null;
  isLoading: boolean;
  error: string | null;
  
  // Filters
  statusFilter: TaskStatus | 'all';
  searchQuery: string;
  
  // Actions - Goals
  setGoals: (goals: Goal[]) => void;
  addGoal: (goal: Goal) => void;
  updateGoal: (id: string, updates: Partial<Goal>) => void;
  removeGoal: (id: string) => void;
  setSelectedGoal: (goal: Goal | null) => void;
  
  // Actions - Tasks
  setTasks: (tasks: Task[]) => void;
  addTask: (task: Task) => void;
  updateTask: (id: string, updates: Partial<Task>) => void;
  removeTask: (id: string) => void;
  setSelectedTask: (task: Task | null) => void;
  
  // Common actions
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clearError: () => void;
  
  // Filters
  setStatusFilter: (status: TaskStatus | 'all') => void;
  setSearchQuery: (query: string) => void;
  
  // Computed
  getFilteredTasks: () => Task[];
  getTaskById: (id: string) => Task | undefined;
  getTasksByStatus: (status: TaskStatus) => Task[];
  getGoalById: (id: string) => Goal | undefined;
  
  // Real-time updates (WebSocket)
  handleTaskUpdate: (update: { id: string; updates: Partial<Task> }) => void;
  handleGoalUpdate: (update: { id: string; updates: Partial<Goal> }) => void;
  
  // Reset
  reset: () => void;
}

export const useTaskStore = create<TaskState>((set, get) => ({
  goals: [],
  tasks: [],
  selectedGoal: null,
  selectedTask: null,
  isLoading: false,
  error: null,
  statusFilter: 'all',
  searchQuery: '',
  
  // Goals
  setGoals: (goals) => set({ goals }),
  
  addGoal: (goal) => set((state) => ({
    goals: [...state.goals, goal],
  })),
  
  updateGoal: (id, updates) => set((state) => ({
    goals: state.goals.map((goal) =>
      goal.id === id ? { ...goal, ...updates } : goal
    ),
    selectedGoal: state.selectedGoal?.id === id
      ? { ...state.selectedGoal, ...updates }
      : state.selectedGoal,
  })),
  
  removeGoal: (id) => set((state) => ({
    goals: state.goals.filter((goal) => goal.id !== id),
    selectedGoal: state.selectedGoal?.id === id ? null : state.selectedGoal,
  })),
  
  setSelectedGoal: (goal) => set({ selectedGoal: goal }),
  
  // Tasks
  setTasks: (tasks) => set({ tasks }),
  
  addTask: (task) => set((state) => ({
    tasks: [...state.tasks, task],
  })),
  
  updateTask: (id, updates) => set((state) => ({
    tasks: state.tasks.map((task) =>
      task.id === id ? { ...task, ...updates } : task
    ),
    selectedTask: state.selectedTask?.id === id
      ? { ...state.selectedTask, ...updates }
      : state.selectedTask,
  })),
  
  removeTask: (id) => set((state) => ({
    tasks: state.tasks.filter((task) => task.id !== id),
    selectedTask: state.selectedTask?.id === id ? null : state.selectedTask,
  })),
  
  setSelectedTask: (task) => set({ selectedTask: task }),
  
  // Common
  setLoading: (loading) => set({ isLoading: loading }),
  
  setError: (error) => set({ error }),
  
  clearError: () => set({ error: null }),
  
  // Filters
  setStatusFilter: (status) => set({ statusFilter: status }),
  
  setSearchQuery: (query) => set({ searchQuery: query }),
  
  // Computed
  getFilteredTasks: () => {
    const { tasks, statusFilter, searchQuery } = get();
    
    let filtered = tasks;
    
    // Filter by status
    if (statusFilter !== 'all') {
      filtered = filtered.filter((task) => task.status === statusFilter);
    }
    
    // Filter by search query
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (task) =>
          task.title.toLowerCase().includes(query) ||
          task.description?.toLowerCase().includes(query) ||
          task.assignedAgent?.toLowerCase().includes(query)
      );
    }
    
    return filtered;
  },
  
  getTaskById: (id) => {
    return get().tasks.find((task) => task.id === id);
  },
  
  getTasksByStatus: (status) => {
    return get().tasks.filter((task) => task.status === status);
  },
  
  getGoalById: (id) => {
    return get().goals.find((goal) => goal.id === id);
  },
  
  // Real-time updates
  handleTaskUpdate: ({ id, updates }) => {
    get().updateTask(id, updates);
  },
  
  handleGoalUpdate: ({ id, updates }) => {
    get().updateGoal(id, updates);
  },
  
  reset: () => set({
    goals: [],
    tasks: [],
    selectedGoal: null,
    selectedTask: null,
    isLoading: false,
    error: null,
    statusFilter: 'all',
    searchQuery: '',
  }),
}));
