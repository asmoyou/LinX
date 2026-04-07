import { afterEach, describe, expect, it, vi } from 'vitest';

import { useProjectExecutionStore } from '@/stores/projectExecutionStore';
import { projectExecutionApi } from '@/api/projectExecution';

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
    deleteProject: vi.fn(),
    createProjectTask: vi.fn(),
    deleteProjectTask: vi.fn(),
    createProjectTaskAndLaunchRun: vi.fn(),
    launchTaskRun: vi.fn(),
  },
}));

const mockedApi = vi.mocked(projectExecutionApi);

describe('useProjectExecutionStore', () => {
  afterEach(() => {
    vi.clearAllMocks();
    useProjectExecutionStore.getState().reset();
  });

  it('creates a project and refreshes project state', async () => {
    mockedApi.createProject.mockResolvedValue('project-1');
    mockedApi.listProjects.mockResolvedValue({ data: [], fallback: false });
    mockedApi.getProjectDetail.mockResolvedValue({
      data: {
        id: 'project-1',
        title: 'Project 1',
        summary: 'Summary',
        instructions: 'Instructions',
        status: 'draft',
        progress: 0,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        totalTasks: 0,
        completedTasks: 0,
        failedTasks: 0,
        needsClarification: false,
        tasks: [],
        agents: [],
        deliverables: [],
        recentActivity: [],
      },
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
    mockedApi.createProjectTaskAndLaunchRun.mockResolvedValue({ taskId: 'task-1', runId: 'run-1' });
    mockedApi.listProjects.mockResolvedValue({ data: [], fallback: false });
    mockedApi.getProjectDetail.mockResolvedValue({
      data: {
        id: 'project-1',
        title: 'Project 1',
        summary: 'Summary',
        instructions: 'Instructions',
        status: 'running',
        progress: 25,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        totalTasks: 1,
        completedTasks: 0,
        failedTasks: 0,
        needsClarification: false,
        tasks: [],
        agents: [],
        deliverables: [],
        recentActivity: [],
      },
      fallback: false,
    });
    mockedApi.getProjectTaskDetail.mockResolvedValue({
      data: {
        id: 'task-1',
        projectId: 'project-1',
        projectTitle: 'Project 1',
        projectStatus: 'running',
        title: 'Task 1',
        description: 'Do the work',
        status: 'running',
        priority: 1,
        updatedAt: new Date().toISOString(),
        dependencyIds: [],
        assignedSkillNames: [],
        metadata: [],
        events: [],
      },
      fallback: false,
    });
    mockedApi.listRuns.mockResolvedValue({ data: [], fallback: false });
    mockedApi.getRunDetail.mockResolvedValue({
      data: {
        id: 'run-1',
        projectId: 'project-1',
        projectTitle: 'Project 1',
        projectSummary: 'Summary',
        status: 'running',
        updatedAt: new Date().toISOString(),
        totalTasks: 1,
        completedTasks: 0,
        failedTasks: 0,
        timeline: [],
        nodes: [],
        deliverables: [],
      },
      fallback: false,
    });

    const result = await useProjectExecutionStore.getState().createProjectTaskAndLaunchRun({
      projectId: 'project-1',
      title: 'Task 1',
      description: 'Do the work',
    });

    expect(result).toEqual({ taskId: 'task-1', runId: 'run-1' });
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
    mockedApi.launchTaskRun.mockResolvedValue('run-1');
    mockedApi.getProjectTaskDetail.mockResolvedValue({
      data: {
        id: 'task-1',
        projectId: 'project-1',
        projectTitle: 'Project 1',
        projectStatus: 'running',
        title: 'Task 1',
        description: 'Do the work',
        status: 'running',
        priority: 1,
        updatedAt: new Date().toISOString(),
        dependencyIds: [],
        assignedSkillNames: [],
        metadata: [],
        events: [],
      },
      fallback: false,
    });
    mockedApi.getProjectDetail.mockResolvedValue({
      data: {
        id: 'project-1',
        title: 'Project 1',
        summary: 'Summary',
        instructions: 'Instructions',
        status: 'running',
        progress: 25,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        totalTasks: 1,
        completedTasks: 0,
        failedTasks: 0,
        needsClarification: false,
        tasks: [],
        agents: [],
        deliverables: [],
        recentActivity: [],
      },
      fallback: false,
    });
    mockedApi.listRuns.mockResolvedValue({ data: [], fallback: false });
    mockedApi.getRunDetail.mockResolvedValue({
      data: {
        id: 'run-1',
        projectId: 'project-1',
        projectTitle: 'Project 1',
        projectSummary: 'Summary',
        status: 'running',
        updatedAt: new Date().toISOString(),
        totalTasks: 1,
        completedTasks: 0,
        failedTasks: 0,
        timeline: [],
        nodes: [],
        deliverables: [],
      },
      fallback: false,
    });

    const runId = await useProjectExecutionStore.getState().launchTaskRun({
      projectId: 'project-1',
      taskId: 'task-1',
      title: 'Task 1',
      description: 'Do the work',
    });

    expect(runId).toBe('run-1');
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
});


  it('deletes a project and prunes local state', async () => {
    useProjectExecutionStore.setState({
      ...useProjectExecutionStore.getState(),
      projects: [{
        id: 'project-1', title: 'Project 1', summary: 'Summary', status: 'draft', progress: 0,
        totalTasks: 0, completedTasks: 0, failedTasks: 0, needsClarification: false,
        updatedAt: new Date().toISOString(), latestSignal: null, activeNodeCount: 0,
      }],
      projectDetails: { 'project-1': {
        id: 'project-1', title: 'Project 1', summary: 'Summary', instructions: 'Instructions', status: 'draft', progress: 0,
        createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), totalTasks: 0, completedTasks: 0, failedTasks: 0,
        needsClarification: false, tasks: [], agents: [], deliverables: [], recentActivity: [],
      } },
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
      projectDetails: { 'project-1': {
        id: 'project-1', title: 'Project 1', summary: 'Summary', instructions: 'Instructions', status: 'running', progress: 25,
        createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), totalTasks: 1, completedTasks: 0, failedTasks: 0,
        needsClarification: false, tasks: [{ id: 'task-1', title: 'Task 1', status: 'running', priority: 1, updatedAt: new Date().toISOString(), dependencyIds: [] }],
        agents: [], deliverables: [], recentActivity: [],
      } },
      projectTaskDetails: { 'project-1:task-1': {
        id: 'task-1', projectId: 'project-1', projectTitle: 'Project 1', projectStatus: 'running', title: 'Task 1', status: 'running',
        priority: 1, updatedAt: new Date().toISOString(), dependencyIds: [], assignedSkillNames: [], metadata: [], events: [],
      } },
    });
    mockedApi.deleteProjectTask.mockResolvedValue();
    mockedApi.listProjects.mockResolvedValue({ data: [], fallback: false });
    mockedApi.getProjectDetail.mockResolvedValue({
      data: {
        id: 'project-1', title: 'Project 1', summary: 'Summary', instructions: 'Instructions', status: 'running', progress: 0,
        createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), totalTasks: 0, completedTasks: 0, failedTasks: 0,
        needsClarification: false, tasks: [], agents: [], deliverables: [], recentActivity: [],
      },
      fallback: false,
    });

    await useProjectExecutionStore.getState().deleteProjectTask('project-1', 'task-1');

    expect(mockedApi.deleteProjectTask).toHaveBeenCalledWith('task-1');
    expect(useProjectExecutionStore.getState().projectTaskDetails['project-1:task-1']).toBeUndefined();
  });
