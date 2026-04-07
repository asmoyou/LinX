import React from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { agentsApi } from '@/api/agents';
import { ProjectDetail } from '@/pages/ProjectDetail';
import { Projects } from '@/pages/Projects';
import { RunCenter } from '@/pages/RunCenter';
import { RunDetail } from '@/pages/RunDetail';

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (_key: string, options?: string | { defaultValue?: string; value?: string }) => {
        if (typeof options === 'string') {
          return options;
        }
        if (options && typeof options === 'object' && 'defaultValue' in options) {
          return options.defaultValue || _key;
        }
        return _key;
      },
      i18n: { language: 'en' },
    }),
  };
});

vi.mock('@/components/platform/ProjectExecutionFormModal', () => ({
  ProjectCreateModal: () => null,
  ProjectTaskCreateModal: () => null,
  LaunchRunModal: () => null,
}));

vi.mock('@/api/agents', () => ({
  agentsApi: {
    getAll: vi.fn().mockResolvedValue([]),
  },
}));

let storeState: any;

vi.mock('@/stores/projectExecutionStore', () => ({
  useProjectExecutionStore: (selector: (state: any) => unknown) => selector(storeState),
}));

const createStoreState = () => ({
  projects: [],
  projectDetails: {},
  runDetails: {},
  runs: [],
  loading: {
    projects: false,
    projectDetail: false,
    projectTaskDetail: false,
    runs: false,
    runDetail: false,
    skillHub: false,
    extensions: false,
  },
  errors: {
    projects: null,
    projectDetail: null,
    projectTaskDetail: null,
    runs: null,
    runDetail: null,
    skillHub: null,
    extensions: null,
  },
  fallbackSections: [],
  loadProjects: vi.fn().mockResolvedValue([]),
  createProject: vi.fn(),
  loadProjectDetail: vi.fn().mockResolvedValue(undefined),
  createProjectTask: vi.fn(),
  createProjectTaskAndLaunchRun: vi.fn(),
  deleteProject: vi.fn(),
  loadRuns: vi.fn().mockResolvedValue([]),
  loadRunDetail: vi.fn().mockResolvedValue(undefined),
  markRunHandled: vi.fn().mockResolvedValue(undefined),
  rescheduleRun: vi.fn(),
});

describe('project execution pages', () => {
  beforeEach(() => {
    storeState = createStoreState();
    vi.mocked(agentsApi.getAll).mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
    cleanup();
  });

  it('renders projects without global run center CTAs', async () => {
    storeState.projects = [
      {
        id: 'project-1',
        title: 'Project One',
        summary: 'Project summary',
        status: 'running',
        progress: 40,
        createdAt: '2026-04-07T10:00:00.000Z',
        updatedAt: '2026-04-07T11:00:00.000Z',
        totalTasks: 5,
        completedTasks: 2,
        failedTasks: 1,
        needsClarification: true,
        latestSignal: 'Old signal',
        activeNodeCount: 3,
      },
    ];

    render(
      <MemoryRouter initialEntries={['/projects']}>
        <Projects />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Project One')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open Project' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Open Run Center' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'See runs' })).not.toBeInTheDocument();
  });

  it('renders project-scoped runs inside project detail', async () => {
    storeState.projectDetails = {
      'project-1': {
        id: 'project-1',
        title: 'Project One',
        summary: 'Project summary',
        instructions: 'Ship the work',
        status: 'running',
        progress: 50,
        createdAt: '2026-04-07T10:00:00.000Z',
        updatedAt: '2026-04-07T11:00:00.000Z',
        totalTasks: 2,
        completedTasks: 1,
        failedTasks: 0,
        needsClarification: false,
        tasks: [],
        agentBindings: [
          {
            id: 'binding-1',
            projectId: 'project-1',
            agentId: 'agent-1',
            agentName: 'agent-1',
            agentType: null,
            priority: 0,
            status: 'active',
            allowedStepKinds: [],
            preferredSkills: [],
            preferredRuntimeTypes: [],
            createdAt: '2026-04-07T10:00:00.000Z',
            updatedAt: '2026-04-07T10:00:00.000Z',
          },
        ],
        runs: [
          {
            id: 'abcd1234-alert',
            projectId: 'project-1',
            projectTitle: 'Project One',
            status: 'failed',
            createdAt: '2026-04-07T10:55:00.000Z',
            triggerSource: 'manual',
            executionMode: 'project_sandbox',
            startedAt: '2026-04-07T11:00:00.000Z',
            completedAt: null,
            updatedAt: '2026-04-07T11:05:00.000Z',
            totalTasks: 1,
            completedTasks: 0,
            failedTasks: 1,
            latestSignal: 'Build failed',
          },
        ],
        agents: [],
        deliverables: [],
        recentActivity: [],
      },
    };
    vi.mocked(agentsApi.getAll).mockResolvedValue([
      {
        id: 'agent-1',
        name: '小白',
        type: 'external_general',
        status: 'offline',
        tasksCompleted: 0,
        uptime: '1h',
        ownerUserId: 'user-1',
        runtimeType: 'external_worktree',
        externalRuntime: {
          status: 'uninstalled',
          bound: false,
          availableForConversation: false,
          availableForExecution: false,
          updateAvailable: false,
          launchCommandSource: 'unset',
          resolvedLaunchCommandTemplate: null,
        },
      } as any,
    ]);

    render(
      <MemoryRouter initialEntries={['/projects/project-1']}>
        <Routes>
          <Route path="/projects/:projectId" element={<ProjectDetail />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText('Project runs')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open Run' })).toBeInTheDocument();
    expect(screen.getByText('Run #abcd1234')).toBeInTheDocument();
    expect(screen.getByText(/Execution mode:/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Mark Handled' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View Project Runs' })).toBeInTheDocument();
    expect(await screen.findByText('小白')).toBeInTheDocument();
    expect(screen.queryByText('Project external runner override')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open Runtime Host' })).toBeInTheDocument();
  });

  it('defaults run alerts to attention runs and hides completed runs', async () => {
    storeState.runs = [
      {
        id: 'abcd1234-alert',
        projectId: 'project-1',
        projectTitle: 'Project One',
        status: 'failed',
        createdAt: '2026-04-07T10:55:00.000Z',
        triggerSource: 'manual',
        taskId: 'task-1',
        taskTitle: 'Fix deployment',
        failureReason: 'External agent is not online',
        alertSignature:
          '{"status":"failed","taskId":"task-1","taskTitle":"Fix deployment","failureReason":"External agent is not online","latestSignal":"Build failed"}',
        startedAt: '2026-04-07T11:00:00.000Z',
        completedAt: null,
        updatedAt: '2026-04-07T11:05:00.000Z',
        totalTasks: 1,
        completedTasks: 0,
        failedTasks: 1,
        latestSignal: 'Build failed',
      },
      {
        id: 'done5678-pass',
        projectId: 'project-2',
        projectTitle: 'Project Two',
        status: 'completed',
        createdAt: '2026-04-07T09:55:00.000Z',
        triggerSource: 'plan_generated',
        startedAt: '2026-04-07T10:00:00.000Z',
        completedAt: '2026-04-07T10:30:00.000Z',
        updatedAt: '2026-04-07T10:30:00.000Z',
        totalTasks: 1,
        completedTasks: 1,
        failedTasks: 0,
        latestSignal: 'Completed cleanly',
      },
      {
        id: 'old99999-fail',
        projectId: 'project-3',
        projectTitle: 'Project Three',
        status: 'failed',
        createdAt: '2026-04-07T08:55:00.000Z',
        triggerSource: 'manual',
        taskId: 'task-9',
        taskTitle: 'Old failure',
        failureReason: 'Already triaged',
        handledAt: '2026-04-07T11:10:00.000Z',
        handledSignature:
          '{"status":"failed","taskId":"task-9","taskTitle":"Old failure","failureReason":"Already triaged","latestSignal":"Already triaged"}',
        alertSignature:
          '{"status":"failed","taskId":"task-9","taskTitle":"Old failure","failureReason":"Already triaged","latestSignal":"Already triaged"}',
        startedAt: '2026-04-07T09:00:00.000Z',
        completedAt: '2026-04-07T09:30:00.000Z',
        updatedAt: '2026-04-07T11:10:00.000Z',
        totalTasks: 1,
        completedTasks: 0,
        failedTasks: 1,
        latestSignal: 'Already triaged',
      },
    ];

    render(
      <MemoryRouter initialEntries={['/runs']}>
        <RunCenter />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Run Alerts')).toBeInTheDocument();
    expect(screen.getByText('Run #abcd1234')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Fix deployment' })).toBeInTheDocument();
    expect(screen.getByText('External agent is not online')).toBeInTheDocument();
    expect(screen.queryByText('Run #old99999')).not.toBeInTheDocument();
    expect(screen.queryByText('Run #done5678')).not.toBeInTheDocument();
  });

  it('renders run detail with a run-first heading', async () => {
    storeState.runDetails = {
      'abcd1234-alert': {
        id: 'abcd1234-alert',
        projectId: 'project-1',
        projectTitle: 'Project One',
        projectSummary: 'Project summary',
        status: 'running',
        createdAt: '2026-04-07T10:55:00.000Z',
        triggerSource: 'manual',
        executionMode: 'project_sandbox',
        taskId: 'task-1',
        taskTitle: 'Fix deployment',
        failureReason: 'External agent is not online',
        alertSignature:
          '{"status":"running","taskId":"task-1","taskTitle":"Fix deployment","failureReason":"External agent is not online","latestSignal":null}',
        startedAt: '2026-04-07T11:00:00.000Z',
        completedAt: null,
        updatedAt: '2026-04-07T11:05:00.000Z',
        totalTasks: 1,
        completedTasks: 0,
        failedTasks: 0,
        timeline: [],
        deliverables: [],
        externalDispatches: [],
      },
    };

    render(
      <MemoryRouter initialEntries={['/runs/abcd1234-alert']}>
        <Routes>
          <Route path="/runs/:runId" element={<RunDetail />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole('heading', { name: 'Run #abcd1234', level: 1 })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Project One' })).toBeInTheDocument();
    expect(screen.getByText('Trigger Manual')).toBeInTheDocument();
    expect(screen.getByText('External agent is not online')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open Task' })).toHaveAttribute('href', '/projects/project-1/tasks/task-1');
  });
});
