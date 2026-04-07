import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/api/client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('@/api/agents', () => ({
  agentsApi: {
    getAll: vi.fn(),
  },
}));

vi.mock('@/api/skills', () => ({
  skillsApi: {
    getOverviewStats: vi.fn(),
    listPage: vi.fn(),
    getCandidates: vi.fn(),
    getBindings: vi.fn(),
    getStore: vi.fn(),
  },
}));

import apiClient from '@/api/client';
import { projectExecutionApi } from '@/api/projectExecution';

const mockGet = vi.mocked(apiClient.get);

const respondToGet = (routes: Record<string, unknown>) => {
  mockGet.mockImplementation(async (url: string) => {
    if (!(url in routes)) {
      throw new Error(`Unexpected GET ${url}`);
    }

    return { data: routes[url] };
  });
};

describe('projectExecutionApi run lifecycle normalization', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('auto-completes started runs that no longer have any tasks', async () => {
    respondToGet({
      '/runs': [
        {
          run_id: 'run-1',
          project_id: 'project-1',
          plan_id: null,
          status: 'running',
          trigger_source: 'manual',
          runtime_context: {},
          error_message: null,
          requested_by_user_id: 'user-1',
          started_at: '2026-04-07T10:00:00.000Z',
          completed_at: null,
          created_at: '2026-04-07T09:59:00.000Z',
          updated_at: '2026-04-07T10:05:00.000Z',
        },
      ],
      '/projects': [
        {
          project_id: 'project-1',
          name: 'Orphan Run Project',
          description: 'Project with a stale running run.',
          status: 'running',
          configuration: {},
          created_by_user_id: 'user-1',
          created_at: '2026-04-07T09:00:00.000Z',
          updated_at: '2026-04-07T10:05:00.000Z',
        },
      ],
      '/project-tasks': [],
      '/run-steps': [
        {
          run_step_id: 'step-1',
          run_id: 'run-1',
          project_task_id: null,
          node_id: null,
          name: 'Execute orphaned work',
          step_type: 'task',
          status: 'running',
          sequence_number: 0,
          input_payload: {},
          output_payload: {},
          error_message: null,
          started_at: '2026-04-07T10:00:30.000Z',
          completed_at: null,
          created_at: '2026-04-07T10:00:00.000Z',
          updated_at: '2026-04-07T10:04:00.000Z',
        },
      ],
    });

    const result = await projectExecutionApi.listRuns();

    expect(result.fallback).toBe(false);
    expect(result.data).toHaveLength(1);
    expect(result.data[0]).toMatchObject({
      id: 'run-1',
      status: 'completed',
      totalTasks: 0,
      completedAt: '2026-04-07T10:05:00.000Z',
    });
  });

  it('freezes duration once all tasks in a run are terminal', async () => {
    respondToGet({
      '/runs/run-2': {
        run_id: 'run-2',
        project_id: 'project-2',
        plan_id: null,
        status: 'running',
        trigger_source: 'manual',
        runtime_context: {},
        error_message: null,
        requested_by_user_id: 'user-2',
        started_at: '2026-04-07T11:00:00.000Z',
        completed_at: null,
        created_at: '2026-04-07T10:59:00.000Z',
        updated_at: '2026-04-07T11:20:00.000Z',
      },
      '/projects/project-2': {
        project_id: 'project-2',
        name: 'Completed Task Project',
        description: 'Project with a stale active run.',
        status: 'running',
        configuration: {},
        created_by_user_id: 'user-2',
        created_at: '2026-04-07T09:00:00.000Z',
        updated_at: '2026-04-07T11:20:00.000Z',
      },
      '/project-tasks': [
        {
          project_task_id: 'task-2',
          project_id: 'project-2',
          plan_id: null,
          run_id: 'run-2',
          assignee_agent_id: null,
          title: 'Finish delivery',
          description: 'Finalize the work.',
          status: 'completed',
          priority: 'normal',
          sort_order: 0,
          input_payload: {},
          output_payload: { result: 'done' },
          error_message: null,
          created_by_user_id: 'user-2',
          created_at: '2026-04-07T11:00:00.000Z',
          updated_at: '2026-04-07T11:15:00.000Z',
        },
      ],
      '/run-steps': [
        {
          run_step_id: 'step-2',
          run_id: 'run-2',
          project_task_id: 'task-2',
          node_id: null,
          name: 'Finish delivery',
          step_type: 'task',
          status: 'completed',
          sequence_number: 0,
          input_payload: {},
          output_payload: { result: 'done' },
          error_message: null,
          started_at: '2026-04-07T11:00:30.000Z',
          completed_at: '2026-04-07T11:15:00.000Z',
          created_at: '2026-04-07T11:00:00.000Z',
          updated_at: '2026-04-07T11:15:00.000Z',
        },
      ],
      '/runs/run-2/external-dispatches': [],
    });

    const result = await projectExecutionApi.getRunDetail('run-2');

    expect(result.fallback).toBe(false);
    expect(result.data).toMatchObject({
      id: 'run-2',
      status: 'completed',
      totalTasks: 1,
      completedTasks: 1,
      completedAt: '2026-04-07T11:20:00.000Z',
    });
  });
});
