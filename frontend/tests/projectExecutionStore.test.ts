import { afterEach, describe, expect, it, vi } from 'vitest';

import { projectExecutionApi } from '@/api/projectExecution';
import { useProjectExecutionStore } from '@/stores/projectExecutionStore';

vi.mock('@/api/projectExecution', () => ({
  projectExecutionApi: {
    listProjects: vi.fn(),
    getProjectDetail: vi.fn(),
    getProjectTaskDetail: vi.fn(),
    listRuns: vi.fn(),
    getRunDetail: vi.fn(),
    getSkillHubSnapshot: vi.fn(),
    listExtensions: vi.fn(),
    createProject: vi.fn(),
    updateProject: vi.fn(),
    deleteProject: vi.fn(),
    createProjectTask: vi.fn(),
    deleteProjectTask: vi.fn(),
    createProjectTaskAndLaunchRun: vi.fn(),
    launchTaskRun: vi.fn(),
    markRunHandled: vi.fn(),
    rescheduleRun: vi.fn(),
  },
}));

const mockedApi = vi.mocked(projectExecutionApi);

const now = '2026-04-07T12:00:00.000Z';

const createProjectDetail = (overrides: Record<string, unknown> = {}) => ({
  id: 'project-1',
  title: 'Project 1',
  summary: 'Summary',
  instructions: 'Instructions',
  status: 'running',
  progress: 25,
  createdAt: now,
  updatedAt: now,
  totalTasks: 1,
  completedTasks: 0,
  failedTasks: 0,
  needsClarification: false,
  tasks: [],
  runs: [],
  agents: [],
  deliverables: [],
  recentActivity: [],
  ...overrides,
});

const createTaskDetail = (overrides: Record<string, unknown> = {}) => ({
  id: 'task-1',
  projectId: 'project-1',
  projectTitle: 'Project 1',
  projectStatus: 'running',
  title: 'Task 1',
  description: 'Do the work',
  executionMode: 'project_sandbox',
  status: 'running',
  priority: 1,
  updatedAt: now,
  dependencyIds: [],
  assignedSkillNames: [],
  metadata: [],
  events: [],
  ...overrides,
});

const createRunDetail = (overrides: Record<string, unknown> = {}) => ({
  id: 'run-1',
  projectId: 'project-1',
  projectTitle: 'Project 1',
  projectSummary: 'Summary',
  status: 'running',
  createdAt: now,
  triggerSource: 'manual',
  alertSignature: '{"status":"running","taskId":null,"taskTitle":null,"failureReason":null,"latestSignal":null}',
  startedAt: now,
  completedAt: null,
  updatedAt: now,
  totalTasks: 1,
  completedTasks: 0,
  failedTasks: 0,
  timeline: [],
  deliverables: [],
  externalDispatches: [],
  ...overrides,
});

describe('useProjectExecutionStore', () => {
  afterEach(() => {
    vi.clearAllMocks();
    useProjectExecutionStore.getState().reset();
  });

  it('loads project detail with project-scoped runs', async () => {
    mockedApi.getProjectDetail.mockResolvedValue({
      data: createProjectDetail({
        runs: [
          {
            id: 'run-2',
            projectId: 'project-1',
            projectTitle: 'Project 1',
            status: 'failed',
            createdAt: now,
            triggerSource: 'manual',
            startedAt: now,
            completedAt: null,
            updatedAt: '2026-04-07T12:05:00.000Z',
            totalTasks: 1,
            completedTasks: 0,
            failedTasks: 1,
            latestSignal: 'Build failed',
          },
        ],
      }),
      fallback: false,
    });

    const detail = await useProjectExecutionStore.getState().loadProjectDetail('project-1');

    expect(mockedApi.getProjectDetail).toHaveBeenCalledWith('project-1');
    expect(detail.runs).toHaveLength(1);
    expect(detail.runs[0]).toMatchObject({
      id: 'run-2',
      triggerSource: 'manual',
      failedTasks: 1,
    });
  });

  it('creates a project and refreshes project state', async () => {
    mockedApi.createProject.mockResolvedValue('project-1');
    mockedApi.listProjects.mockResolvedValue({ data: [], fallback: false });
    mockedApi.getProjectDetail.mockResolvedValue({
      data: createProjectDetail(),
      fallback: false,
    });

    const projectId = await useProjectExecutionStore.getState().createProject({
      name: 'Project 1',
      description: 'Summary',
    });

    expect(projectId).toBe('project-1');
    expect(mockedApi.createProject).toHaveBeenCalledWith({
      name: 'Project 1',
      description: 'Summary',
    });
    expect(mockedApi.listProjects).toHaveBeenCalledTimes(1);
    expect(mockedApi.getProjectDetail).toHaveBeenCalledWith('project-1');
  });

  it('creates a task and auto-starts a run with one refresh cycle', async () => {
    mockedApi.createProjectTaskAndLaunchRun.mockResolvedValue({
      taskId: 'task-1',
      runId: 'run-1',
      needsClarification: false,
    });
    mockedApi.listProjects.mockResolvedValue({ data: [], fallback: false });
    mockedApi.getProjectDetail.mockResolvedValue({
      data: createProjectDetail({
        totalTasks: 1,
        runs: [
          {
            id: 'run-1',
            projectId: 'project-1',
            projectTitle: 'Project 1',
            status: 'running',
            createdAt: now,
            triggerSource: 'manual',
            startedAt: now,
            completedAt: null,
            updatedAt: now,
            totalTasks: 1,
            completedTasks: 0,
            failedTasks: 0,
          },
        ],
      }),
      fallback: false,
    });
    mockedApi.getProjectTaskDetail.mockResolvedValue({
      data: createTaskDetail(),
      fallback: false,
    });
    mockedApi.listRuns.mockResolvedValue({ data: [], fallback: false });
    mockedApi.getRunDetail.mockResolvedValue({
      data: createRunDetail(),
      fallback: false,
    });

    const result = await useProjectExecutionStore.getState().createProjectTaskAndLaunchRun({
      projectId: 'project-1',
      title: 'Task 1',
      description: 'Do the work',
    });

    expect(result).toEqual({
      taskId: 'task-1',
      runId: 'run-1',
      needsClarification: false,
    });
    expect(mockedApi.createProjectTaskAndLaunchRun).toHaveBeenCalledWith({
      projectId: 'project-1',
      title: 'Task 1',
      description: 'Do the work',
    });
    expect(mockedApi.listProjects).toHaveBeenCalledTimes(1);
    expect(mockedApi.getProjectDetail).toHaveBeenCalledWith('project-1');
    expect(mockedApi.getProjectTaskDetail).toHaveBeenCalledWith('project-1', 'task-1');
    expect(mockedApi.listRuns).toHaveBeenCalledTimes(1);
    expect(mockedApi.getRunDetail).toHaveBeenCalledWith('run-1');
  });

  it('launches a task run and refreshes dependent views', async () => {
    mockedApi.launchTaskRun.mockResolvedValue({
      runId: 'run-1',
      needsClarification: false,
    });
    mockedApi.getProjectTaskDetail.mockResolvedValue({
      data: createTaskDetail(),
      fallback: false,
    });
    mockedApi.getProjectDetail.mockResolvedValue({
      data: createProjectDetail(),
      fallback: false,
    });
    mockedApi.listRuns.mockResolvedValue({ data: [], fallback: false });
    mockedApi.getRunDetail.mockResolvedValue({
      data: createRunDetail(),
      fallback: false,
    });

    const result = await useProjectExecutionStore.getState().launchTaskRun({
      projectId: 'project-1',
      taskId: 'task-1',
      title: 'Task 1',
      description: 'Do the work',
    });

    expect(result).toEqual({ runId: 'run-1', needsClarification: false });
    expect(mockedApi.launchTaskRun).toHaveBeenCalledWith({
      projectId: 'project-1',
      taskId: 'task-1',
      title: 'Task 1',
      description: 'Do the work',
    });
    expect(mockedApi.getProjectTaskDetail).toHaveBeenCalledWith('project-1', 'task-1');
    expect(mockedApi.getProjectDetail).toHaveBeenCalledWith('project-1');
    expect(mockedApi.listRuns).toHaveBeenCalledTimes(1);
    expect(mockedApi.getRunDetail).toHaveBeenCalledWith('run-1');
  });

  it('marks a run as handled and refreshes dependent views', async () => {
    mockedApi.markRunHandled.mockResolvedValue(undefined);
    mockedApi.listRuns.mockResolvedValue({ data: [], fallback: false });
    mockedApi.getRunDetail.mockResolvedValue({
      data: createRunDetail({ handledAt: '2026-04-07T12:10:00.000Z' }),
      fallback: false,
    });
    mockedApi.getProjectDetail.mockResolvedValue({
      data: createProjectDetail(),
      fallback: false,
    });

    useProjectExecutionStore.setState({
      ...useProjectExecutionStore.getState(),
      runs: [
        {
          id: 'run-1',
          projectId: 'project-1',
          projectTitle: 'Project 1',
          status: 'failed',
          createdAt: now,
          triggerSource: 'manual',
          updatedAt: now,
          totalTasks: 1,
          completedTasks: 0,
          failedTasks: 1,
        },
      ],
    });

    await useProjectExecutionStore
      .getState()
      .markRunHandled(
        'run-1',
        '2026-04-07T12:10:00.000Z',
        '{"status":"failed","taskId":null,"taskTitle":null,"failureReason":null,"latestSignal":null}',
        'user-1',
      );

    expect(mockedApi.markRunHandled).toHaveBeenCalledWith('run-1', {
      handledAt: '2026-04-07T12:10:00.000Z',
      handledSignature:
        '{"status":"failed","taskId":null,"taskTitle":null,"failureReason":null,"latestSignal":null}',
      handledByUserId: 'user-1',
    });
    expect(mockedApi.listRuns).toHaveBeenCalledTimes(1);
    expect(mockedApi.getRunDetail).toHaveBeenCalledWith('run-1');
    expect(mockedApi.getProjectDetail).toHaveBeenCalledWith('project-1');
  });

  it('deletes a project and prunes local state', async () => {
    useProjectExecutionStore.setState({
      ...useProjectExecutionStore.getState(),
      projects: [
        {
          id: 'project-1',
          title: 'Project 1',
          summary: 'Summary',
          status: 'draft',
          progress: 0,
          createdAt: now,
          updatedAt: now,
          totalTasks: 0,
          completedTasks: 0,
          failedTasks: 0,
          needsClarification: false,
          latestSignal: null,
          activeNodeCount: 0,
        },
      ],
      projectDetails: {
        'project-1': createProjectDetail({
          status: 'draft',
          progress: 0,
          totalTasks: 0,
        }),
      },
    });
    mockedApi.deleteProject.mockResolvedValue();

    await useProjectExecutionStore.getState().deleteProject('project-1');

    expect(mockedApi.deleteProject).toHaveBeenCalledWith('project-1');
    expect(useProjectExecutionStore.getState().projects).toEqual([]);
    expect(useProjectExecutionStore.getState().projectDetails['project-1']).toBeUndefined();
  });

  it('deletes a project task and refreshes project state', async () => {
    useProjectExecutionStore.setState({
      ...useProjectExecutionStore.getState(),
      projectDetails: {
        'project-1': createProjectDetail({
          tasks: [
            {
              id: 'task-1',
              title: 'Task 1',
              status: 'running',
              priority: 1,
              updatedAt: now,
              dependencyIds: [],
            },
          ],
        }),
      },
      projectTaskDetails: {
        'project-1:task-1': createTaskDetail(),
      },
    });
    mockedApi.deleteProjectTask.mockResolvedValue();
    mockedApi.listProjects.mockResolvedValue({ data: [], fallback: false });
    mockedApi.getProjectDetail.mockResolvedValue({
      data: createProjectDetail({
        totalTasks: 0,
      }),
      fallback: false,
    });

    await useProjectExecutionStore.getState().deleteProjectTask('project-1', 'task-1');

    expect(mockedApi.deleteProjectTask).toHaveBeenCalledWith('task-1');
    expect(useProjectExecutionStore.getState().projectTaskDetails['project-1:task-1']).toBeUndefined();
  });
});
