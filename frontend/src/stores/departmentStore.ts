import { create } from 'zustand';
import type { Department } from '../types/department';
import { departmentsApi } from '../api/departments';

interface DepartmentState {
  departments: Department[];
  selectedDepartment: Department | null;
  isLoading: boolean;
  error: string | null;

  // Actions
  fetchDepartments: (params?: {
    view?: 'flat' | 'tree';
    status?: 'active' | 'archived';
    search?: string;
  }) => Promise<void>;
  setSelectedDepartment: (dept: Department | null) => void;
  createDepartment: (data: Parameters<typeof departmentsApi.create>[0]) => Promise<Department>;
  updateDepartment: (
    id: string,
    data: Parameters<typeof departmentsApi.update>[1]
  ) => Promise<Department>;
  deleteDepartment: (id: string) => Promise<void>;
  setError: (error: string | null) => void;
  reset: () => void;
}

export const useDepartmentStore = create<DepartmentState>((set) => ({
  departments: [],
  selectedDepartment: null,
  isLoading: false,
  error: null,

  fetchDepartments: async (params) => {
    set({ isLoading: true, error: null });
    try {
      const departments = await departmentsApi.list(params);
      set({ departments, isLoading: false });
    } catch (err: any) {
      set({
        error: err.response?.data?.detail || 'Failed to fetch departments',
        isLoading: false,
      });
    }
  },

  setSelectedDepartment: (dept) => set({ selectedDepartment: dept }),

  createDepartment: async (data) => {
    set({ isLoading: true, error: null });
    try {
      const dept = await departmentsApi.create(data);
      set((state) => ({
        departments: [...state.departments, dept],
        isLoading: false,
      }));
      return dept;
    } catch (err: any) {
      set({
        error: err.response?.data?.detail || 'Failed to create department',
        isLoading: false,
      });
      throw err;
    }
  },

  updateDepartment: async (id, data) => {
    set({ isLoading: true, error: null });
    try {
      const updated = await departmentsApi.update(id, data);
      set((state) => ({
        departments: state.departments.map((d) => (d.id === id ? updated : d)),
        selectedDepartment:
          state.selectedDepartment?.id === id ? updated : state.selectedDepartment,
        isLoading: false,
      }));
      return updated;
    } catch (err: any) {
      set({
        error: err.response?.data?.detail || 'Failed to update department',
        isLoading: false,
      });
      throw err;
    }
  },

  deleteDepartment: async (id) => {
    set({ isLoading: true, error: null });
    try {
      await departmentsApi.delete(id);
      set((state) => ({
        departments: state.departments.filter((d) => d.id !== id),
        selectedDepartment:
          state.selectedDepartment?.id === id ? null : state.selectedDepartment,
        isLoading: false,
      }));
    } catch (err: any) {
      set({
        error: err.response?.data?.detail || 'Failed to delete department',
        isLoading: false,
      });
      throw err;
    }
  },

  setError: (error) => set({ error }),

  reset: () =>
    set({
      departments: [],
      selectedDepartment: null,
      isLoading: false,
      error: null,
    }),
}));
