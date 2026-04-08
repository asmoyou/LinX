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
      createdAt: '2026-04-07T10:59:00.000Z',
      triggerSource: 'manual',
      taskId: 'task-2',
      taskTitle: 'Finish delivery',
      failureReason: null,
      totalTasks: 1,
      completedTasks: 1,
      completedAt: '2026-04-07T11:20:00.000Z',
    });
  });

  it('injects project-scoped runs into project detail and keeps project activity free of run lifecycle items', async () => {
    respondToGet({
      '/projects/project-3': {
        project_id: 'project-3',
        name: 'Project Detail Scope',
        description: 'Project detail view',
        status: 'running',
        configuration: {},
        created_by_user_id: 'user-3',
        created_at: '2026-04-07T08:00:00.000Z',
        updated_at: '2026-04-07T12:10:00.000Z',
      },
      '/project-tasks': [
        {
          project_task_id: 'task-3',
          project_id: 'project-3',
          plan_id: null,
          run_id: 'run-3b',
          assignee_agent_id: null,
          title: 'Investigate alert',
          description: 'Look into alerting.',
          status: 'running',
          priority: 'high',
          sort_order: 0,
          input_payload: {},
          output_payload: { summary: 'Triaging alert state' },
          error_message: null,
          created_by_user_id: 'user-3',
          created_at: '2026-04-07T11:30:00.000Z',
          updated_at: '2026-04-07T12:05:00.000Z',
        },
      ],
      '/runs': [
        {
          run_id: 'run-3a',
          project_id: 'project-3',
          plan_id: null,
          status: 'completed',
          trigger_source: 'manual',
          runtime_context: { summary: 'Completed cleanly' },
          error_message: null,
          requested_by_user_id: 'user-3',
          started_at: '2026-04-07T09:00:00.000Z',
          completed_at: '2026-04-07T09:30:00.000Z',
          created_at: '2026-04-07T08:55:00.000Z',
          updated_at: '2026-04-07T09:30:00.000Z',
        },
        {
          run_id: 'run-3b',
          project_id: 'project-3',
          plan_id: null,
          status: 'running',
          trigger_source: 'plan_generated',
          runtime_context: { summary: 'Still executing' },
          error_message: null,
          requested_by_user_id: 'user-3',
          started_at: '2026-04-07T12:00:00.000Z',
          completed_at: null,
          created_at: '2026-04-07T11:58:00.000Z',
          updated_at: '2026-04-07T12:10:00.000Z',
        },
      ],
      '/run-steps': [
        {
          run_step_id: 'step-3',
          run_id: 'run-3b',
          project_task_id: 'task-3',
          node_id: null,
          name: 'Investigate alert',
          step_type: 'task',
          status: 'running',
          sequence_number: 0,
          input_payload: {},
          output_payload: {},
          error_message: null,
          started_at: '2026-04-07T12:00:00.000Z',
          completed_at: null,
          created_at: '2026-04-07T12:00:00.000Z',
          updated_at: '2026-04-07T12:05:00.000Z',
        },
      ],
      '/extensions': [],
      '/plans': [],
      '/project-space/project-3': null,
      '/projects/project-3/agent-bindings': [],
      '/projects/project-3/agent-provisioning-profiles': [],
    });

    const result = await projectExecutionApi.getProjectDetail('project-3');

    expect(result.fallback).toBe(false);
    expect(result.data.runs).toHaveLength(2);
    expect(result.data.runs.map((run) => run.id)).toEqual(['run-3b', 'run-3a']);
    expect(result.data.runs[0]).toMatchObject({
      id: 'run-3b',
      createdAt: '2026-04-07T11:58:00.000Z',
      triggerSource: 'plan_generated',
      taskId: 'task-3',
      taskTitle: 'Investigate alert',
    });
    expect(result.data.recentActivity.map((item) => item.id)).toEqual([
      'project-project-3',
      'task-task-3',
    ]);
  });

  it('derives project summary status from task lifecycle instead of stale project status', async () => {
    respondToGet({
      '/projects': [
        {
          project_id: 'project-4',
          name: 'Stale Project Status',
          description: 'Project summary',
          status: 'running',
          configuration: {},
          created_by_user_id: 'user-4',
          created_at: '2026-04-07T08:00:00.000Z',
          updated_at: '2026-04-07T12:00:00.000Z',
        },
      ],
      '/project-tasks': [
        {
          project_task_id: 'task-4',
          project_id: 'project-4',
          plan_id: null,
          run_id: 'run-4',
          assignee_agent_id: null,
          title: 'Ship final report',
          description: 'Finalize the deliverable.',
          status: 'completed',
          priority: 'normal',
          sort_order: 0,
          input_payload: {},
          output_payload: {},
          error_message: null,
          created_by_user_id: 'user-4',
          created_at: '2026-04-07T09:00:00.000Z',
          updated_at: '2026-04-07T11:45:00.000Z',
        },
      ],
      '/runs': [
        {
          run_id: 'run-4',
          project_id: 'project-4',
          plan_id: null,
          status: 'completed',
          trigger_source: 'manual',
          runtime_context: {},
          error_message: null,
          requested_by_user_id: 'user-4',
          started_at: '2026-04-07T10:00:00.000Z',
          completed_at: '2026-04-07T11:45:00.000Z',
          created_at: '2026-04-07T09:55:00.000Z',
          updated_at: '2026-04-07T11:45:00.000Z',
        },
      ],
    });

    const result = await projectExecutionApi.listProjects();

    expect(result.fallback).toBe(false);
    expect(result.data[0]).toMatchObject({
      id: 'project-4',
      status: 'completed',
      progress: 100,
      completedTasks: 1,
      totalTasks: 1,
    });
  });

  it('prefers the latest successful task over older failed history for project card status', async () => {
    respondToGet({
      '/projects': [
        {
          project_id: 'project-5',
          name: 'Recovered Project',
          description: 'Project summary',
          status: 'failed',
          configuration: {},
          created_by_user_id: 'user-5',
          created_at: '2026-04-07T08:00:00.000Z',
          updated_at: '2026-04-07T12:00:00.000Z',
        },
      ],
      '/project-tasks': [
        {
          project_task_id: 'task-5a',
          project_id: 'project-5',
          plan_id: null,
          run_id: null,
          assignee_agent_id: null,
          title: 'Initial attempt',
          description: 'Failed old attempt.',
          status: 'failed',
          priority: 'normal',
          sort_order: 0,
          input_payload: {},
          output_payload: {},
          error_message: 'old error',
          created_by_user_id: 'user-5',
          created_at: '2026-04-07T09:00:00.000Z',
          updated_at: '2026-04-07T10:00:00.000Z',
        },
        {
          project_task_id: 'task-5b',
          project_id: 'project-5',
          plan_id: null,
          run_id: null,
          assignee_agent_id: null,
          title: 'Retry attempt',
          description: 'Succeeded latest attempt.',
          status: 'completed',
          priority: 'normal',
          sort_order: 1,
          input_payload: {},
          output_payload: {},
          error_message: null,
          created_by_user_id: 'user-5',
          created_at: '2026-04-07T10:30:00.000Z',
          updated_at: '2026-04-07T11:30:00.000Z',
        },
      ],
      '/runs': [],
    });

    const result = await projectExecutionApi.listProjects();

    expect(result.fallback).toBe(false);
    expect(result.data[0]).toMatchObject({
      id: 'project-5',
      status: 'completed',
      failedTasks: 1,
      completedTasks: 1,
      totalTasks: 2,
    });
  });
});
