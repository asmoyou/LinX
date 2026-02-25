import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useDepartmentStore } from '@/stores/departmentStore';

// Mock the API
vi.mock('@/api/departments', () => ({
  departmentsApi: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
}));

import { departmentsApi } from '@/api/departments';

const mockDepartment = {
  id: 'dept-1',
  name: 'Engineering',
  code: 'eng',
  description: 'Engineering department',
  parentId: null,
  managerId: null,
  managerName: null,
  status: 'active' as const,
  sortOrder: 0,
  memberCount: 5,
  agentCount: 2,
  knowledgeCount: 3,
  children: [],
  createdAt: '2024-01-01T00:00:00Z',
  updatedAt: '2024-01-02T00:00:00Z',
};

describe('departmentStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useDepartmentStore.getState().reset();
  });

  it('should have correct initial state', () => {
    const state = useDepartmentStore.getState();
    expect(state.departments).toEqual([]);
    expect(state.selectedDepartment).toBeNull();
    expect(state.isLoading).toBe(false);
    expect(state.error).toBeNull();
  });

  it('should fetch departments successfully', async () => {
    vi.mocked(departmentsApi.list).mockResolvedValueOnce([mockDepartment]);

    await useDepartmentStore.getState().fetchDepartments();

    const state = useDepartmentStore.getState();
    expect(state.departments).toEqual([mockDepartment]);
    expect(state.isLoading).toBe(false);
    expect(state.error).toBeNull();
  });

  it('should handle fetch error', async () => {
    vi.mocked(departmentsApi.list).mockRejectedValueOnce(new Error('Network error'));

    await useDepartmentStore.getState().fetchDepartments();

    const state = useDepartmentStore.getState();
    expect(state.departments).toEqual([]);
    expect(state.isLoading).toBe(false);
    expect(state.error).toBe('Failed to fetch departments');
  });

  it('should handle fetch error with API detail', async () => {
    const apiError = { response: { data: { detail: 'Unauthorized' } } };
    vi.mocked(departmentsApi.list).mockRejectedValueOnce(apiError);

    await useDepartmentStore.getState().fetchDepartments();

    const state = useDepartmentStore.getState();
    expect(state.error).toBe('Unauthorized');
  });

  it('should set selected department', () => {
    useDepartmentStore.getState().setSelectedDepartment(mockDepartment);
    expect(useDepartmentStore.getState().selectedDepartment).toEqual(mockDepartment);

    useDepartmentStore.getState().setSelectedDepartment(null);
    expect(useDepartmentStore.getState().selectedDepartment).toBeNull();
  });

  it('should create department and add to list', async () => {
    vi.mocked(departmentsApi.create).mockResolvedValueOnce(mockDepartment);

    await useDepartmentStore.getState().createDepartment({
      name: 'Engineering',
      code: 'eng',
    });

    const state = useDepartmentStore.getState();
    expect(state.departments).toContainEqual(mockDepartment);
  });

  it('should update department in list', async () => {
    // Pre-populate with department
    useDepartmentStore.setState({ departments: [mockDepartment] });

    const updated = { ...mockDepartment, name: 'Eng Team' };
    vi.mocked(departmentsApi.update).mockResolvedValueOnce(updated);

    await useDepartmentStore.getState().updateDepartment('dept-1', { name: 'Eng Team' });

    const state = useDepartmentStore.getState();
    expect(state.departments[0].name).toBe('Eng Team');
  });

  it('should delete department from list', async () => {
    useDepartmentStore.setState({ departments: [mockDepartment] });
    vi.mocked(departmentsApi.delete).mockResolvedValueOnce(undefined);

    await useDepartmentStore.getState().deleteDepartment('dept-1');

    const state = useDepartmentStore.getState();
    expect(state.departments).toEqual([]);
  });

  it('should reset state', () => {
    useDepartmentStore.setState({
      departments: [mockDepartment],
      selectedDepartment: mockDepartment,
      isLoading: true,
      error: 'test error',
    });

    useDepartmentStore.getState().reset();

    const state = useDepartmentStore.getState();
    expect(state.departments).toEqual([]);
    expect(state.selectedDepartment).toBeNull();
    expect(state.isLoading).toBe(false);
    expect(state.error).toBeNull();
  });
});
