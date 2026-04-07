import React from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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
  rescheduleRun: vi.fn(),
});

describe('project execution pages', () => {
  beforeEach(() => {
    storeState = createStoreState();
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
        runs: [
          {
            id: 'abcd1234-alert',
            projectId: 'project-1',
            projectTitle: 'Project One',
            status: 'failed',
            createdAt: '2026-04-07T10:55:00.000Z',
            triggerSource: 'manual',
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
    expect(screen.getByRole('link', { name: 'View Project Runs' })).toBeInTheDocument();
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
    ];

    render(
      <MemoryRouter initialEntries={['/runs']}>
        <RunCenter />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Run Alerts')).toBeInTheDocument();
    expect(screen.getByText('Run #abcd1234')).toBeInTheDocument();
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
  });
});
