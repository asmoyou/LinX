import { create } from 'zustand';

import { projectExecutionApi } from '@/api/projectExecution';
import type { ProjectExecutionMode } from '@/utils/projectExecutionPlanning';
import type {
  PlatformExtension,
  ProjectDetail,
  ProjectExecutionSection,
  ProjectSummary,
  ProjectTaskDetail,
  RunDetail,
  RunSummary,
  SkillHubSnapshot,
} from '@/types/projectExecution';

type LoadingMap = Record<ProjectExecutionSection, boolean>;
type ErrorMap = Record<ProjectExecutionSection, string | null>;
type LoadOptions = { force?: boolean };

interface ProjectExecutionState {
  projects: ProjectSummary[];
  projectDetails: Record<string, ProjectDetail>;
  projectTaskDetails: Record<string, ProjectTaskDetail>;
  runs: RunSummary[];
  runDetails: Record<string, RunDetail>;
  skillHub: SkillHubSnapshot | null;
  extensions: PlatformExtension[];
  loading: LoadingMap;
  errors: ErrorMap;
  fallbackSections: ProjectExecutionSection[];
  lastUpdatedAt: string | null;
  loadProjects: (options?: LoadOptions) => Promise<ProjectSummary[]>;
  loadProjectDetail: (projectId: string, options?: LoadOptions) => Promise<ProjectDetail>;
  loadProjectTaskDetail: (projectId: string, taskId: string) => Promise<ProjectTaskDetail>;
  loadRuns: (options?: LoadOptions) => Promise<RunSummary[]>;
  loadRunDetail: (runId: string, options?: LoadOptions) => Promise<RunDetail>;
  loadSkillHub: () => Promise<SkillHubSnapshot>;
  loadExtensions: () => Promise<PlatformExtension[]>;
  createProject: (input: { name: string; description?: string | null }) => Promise<string>;
  updateProject: (projectId: string, payload: Partial<{ name: string; description?: string | null; status: string; configuration: Record<string, unknown>; }>) => Promise<string>;
  deleteProject: (projectId: string) => Promise<void>;
  createProjectTask: (input: {
    projectId: string;
    title: string;
    description?: string | null;
    executionMode?: ProjectExecutionMode;
  }) => Promise<string>;
  deleteProjectTask: (projectId: string, taskId: string) => Promise<void>;
  createProjectTaskAndLaunchRun: (input: {
    projectId: string;
    title: string;
    description?: string | null;
    executionMode?: ProjectExecutionMode;
  }) => Promise<{ taskId: string; runId: string | null; needsClarification: boolean }>;
  launchTaskRun: (input: {
    projectId: string;
    taskId: string;
    title: string;
    description?: string | null;
    executionMode?: ProjectExecutionMode;
  }) => Promise<{ runId: string | null; needsClarification: boolean }>;
  markRunHandled: (
    runId: string,
    handledAt: string,
    handledSignature: string,
    handledByUserId?: string | null,
  ) => Promise<void>;
  rescheduleRun: (runId: string) => Promise<RunDetail>;
  reset: () => void;
}

const createLoadingMap = (): LoadingMap => ({
  projects: false,
  projectDetail: false,
  projectTaskDetail: false,
  runs: false,
  runDetail: false,
  skillHub: false,
  extensions: false,
});

const createErrorMap = (): ErrorMap => ({
  projects: null,
  projectDetail: null,
  projectTaskDetail: null,
  runs: null,
  runDetail: null,
  skillHub: null,
  extensions: null,
});

const updateFallbackSections = (
  sections: ProjectExecutionSection[],
  section: ProjectExecutionSection,
  shouldUseFallback: boolean,
): ProjectExecutionSection[] => {
  if (shouldUseFallback) {
    return sections.includes(section) ? sections : [...sections, section];
  }

  return sections.filter((candidate) => candidate !== section);
};

const getErrorMessage = (error: unknown, fallback: string): string =>
  error instanceof Error ? error.message : fallback;

const taskDetailKey = (projectId: string, taskId: string): string => `${projectId}:${taskId}`;

const REQUEST_STALE_MS = 15_000;

const requestCache = new Map<string, { at: number; promise: Promise<any> }>();

const withRequestCache = <T>(
  key: string,
  factory: () => Promise<T>,
  options?: LoadOptions,
): Promise<T> => {
  if (options?.force) {
    return factory();
  }

  const now = Date.now();
  const existing = requestCache.get(key);
  if (existing && now - existing.at < REQUEST_STALE_MS) {
    return existing.promise as Promise<T>;
  }

  const promise = factory().finally(() => {
    const latest = requestCache.get(key);
    if (latest?.promise === promise) {
      requestCache.delete(key);
    }
  });

  requestCache.set(key, { at: now, promise });
  return promise;
};

const initialState = () => ({
  projects: [],
  projectDetails: {},
  projectTaskDetails: {},
  runs: [],
  runDetails: {},
  skillHub: null,
  extensions: [],
  loading: createLoadingMap(),
  errors: createErrorMap(),
  fallbackSections: [],
  lastUpdatedAt: null,
});

export const useProjectExecutionStore = create<ProjectExecutionState>((set, get) => ({
  ...initialState(),

  loadProjects: async (options) => {
    set((state) => ({
      loading: { ...state.loading, projects: true },
      errors: { ...state.errors, projects: null },
    }));

    try {
      const result = await withRequestCache(
        'projects',
        () => projectExecutionApi.listProjects(),
        options,
      );
      set((state) => ({
        projects: result.fallback && state.projects.length > 0 ? state.projects : result.data,
        loading: { ...state.loading, projects: false },
        errors: { ...state.errors, projects: result.error || null },
        fallbackSections: updateFallbackSections(state.fallbackSections, 'projects', result.fallback && state.projects.length === 0),
        lastUpdatedAt: new Date().toISOString(),
      }));
      return get().projects;
    } catch (error) {
      const message = getErrorMessage(error, 'Failed to load projects');
      set((state) => ({
        loading: { ...state.loading, projects: false },
        errors: { ...state.errors, projects: message },
      }));
      throw error;
    }
  },

  loadProjectDetail: async (projectId, options) => {
    set((state) => ({
      loading: { ...state.loading, projectDetail: true },
      errors: { ...state.errors, projectDetail: null },
    }));

    try {
      const result = await withRequestCache(
        `projectDetail:${projectId}`,
        () => projectExecutionApi.getProjectDetail(projectId),
        options,
      );
      set((state) => {
        const nextDetail = result.fallback && state.projectDetails[projectId]
          ? state.projectDetails[projectId]
          : result.data;
        return {
          projectDetails: { ...state.projectDetails, [projectId]: nextDetail },
          projects: state.projects.some((project) => project.id === projectId)
            ? state.projects.map((project) =>
                project.id === projectId
                  ? {
                      ...project,
                      activeNodeCount: nextDetail.activeNodeCount,
                      latestSignal: nextDetail.latestSignal,
                      progress: nextDetail.progress,
                      status: nextDetail.status,
                    }
                  : project,
              )
            : state.projects,
          loading: { ...state.loading, projectDetail: false },
          errors: { ...state.errors, projectDetail: result.error || null },
          fallbackSections: updateFallbackSections(
            state.fallbackSections,
            'projectDetail',
            result.fallback && !state.projectDetails[projectId],
          ),
          lastUpdatedAt: new Date().toISOString(),
        };
      });
      return get().projectDetails[projectId];
    } catch (error) {
      const message = getErrorMessage(error, 'Failed to load project detail');
      set((state) => ({
        loading: { ...state.loading, projectDetail: false },
        errors: { ...state.errors, projectDetail: message },
      }));
      throw error;
    }
  },

  loadProjectTaskDetail: async (projectId, taskId) => {
    set((state) => ({
      loading: { ...state.loading, projectTaskDetail: true },
      errors: { ...state.errors, projectTaskDetail: null },
    }));

    try {
      const result = await projectExecutionApi.getProjectTaskDetail(projectId, taskId);
      set((state) => ({
        projectTaskDetails: {
          ...state.projectTaskDetails,
          [taskDetailKey(projectId, taskId)]: result.data,
        },
        loading: { ...state.loading, projectTaskDetail: false },
        errors: { ...state.errors, projectTaskDetail: result.error || null },
        fallbackSections: updateFallbackSections(
          state.fallbackSections,
          'projectTaskDetail',
          result.fallback,
        ),
        lastUpdatedAt: new Date().toISOString(),
      }));
      return result.data;
    } catch (error) {
      const message = getErrorMessage(error, 'Failed to load task detail');
      set((state) => ({
        loading: { ...state.loading, projectTaskDetail: false },
        errors: { ...state.errors, projectTaskDetail: message },
      }));
      throw error;
    }
  },

  loadRuns: async (options) => {
    set((state) => ({
      loading: { ...state.loading, runs: true },
      errors: { ...state.errors, runs: null },
    }));

    try {
      const result = await withRequestCache('runs', () => projectExecutionApi.listRuns(), options);
      set((state) => ({
        runs: result.fallback && state.runs.length > 0 ? state.runs : result.data,
        loading: { ...state.loading, runs: false },
        errors: { ...state.errors, runs: result.error || null },
        fallbackSections: updateFallbackSections(state.fallbackSections, 'runs', result.fallback && state.runs.length === 0),
        lastUpdatedAt: new Date().toISOString(),
      }));
      return get().runs;
    } catch (error) {
      const message = getErrorMessage(error, 'Failed to load runs');
      set((state) => ({
        loading: { ...state.loading, runs: false },
        errors: { ...state.errors, runs: message },
      }));
      throw error;
    }
  },

  loadRunDetail: async (runId, options) => {
    set((state) => ({
      loading: { ...state.loading, runDetail: true },
      errors: { ...state.errors, runDetail: null },
    }));

    try {
      const result = await withRequestCache(
        `runDetail:${runId}`,
        () => projectExecutionApi.getRunDetail(runId),
        options,
      );
      set((state) => ({
        runDetails: { ...state.runDetails, [runId]: result.data },
        loading: { ...state.loading, runDetail: false },
        errors: { ...state.errors, runDetail: result.error || null },
        fallbackSections: updateFallbackSections(
          state.fallbackSections,
          'runDetail',
          result.fallback,
        ),
        lastUpdatedAt: new Date().toISOString(),
      }));
      return result.data;
    } catch (error) {
      const message = getErrorMessage(error, 'Failed to load run detail');
      set((state) => ({
        loading: { ...state.loading, runDetail: false },
        errors: { ...state.errors, runDetail: message },
      }));
      throw error;
    }
  },


  loadSkillHub: async () => {
    set((state) => ({
      loading: { ...state.loading, skillHub: true },
      errors: { ...state.errors, skillHub: null },
    }));

    try {
      const result = await projectExecutionApi.getSkillHubSnapshot();
      set((state) => ({
        skillHub: result.data,
        loading: { ...state.loading, skillHub: false },
        errors: { ...state.errors, skillHub: result.error || null },
        fallbackSections: updateFallbackSections(
          state.fallbackSections,
          'skillHub',
          result.fallback,
        ),
        lastUpdatedAt: new Date().toISOString(),
      }));
      return result.data;
    } catch (error) {
      const message = getErrorMessage(error, 'Failed to load skill hub');
      set((state) => ({
        loading: { ...state.loading, skillHub: false },
        errors: { ...state.errors, skillHub: message },
      }));
      throw error;
    }
  },

  loadExtensions: async () => {
    set((state) => ({
      loading: { ...state.loading, extensions: true },
      errors: { ...state.errors, extensions: null },
    }));

    try {
      const result = await projectExecutionApi.listExtensions();
      set((state) => ({
        extensions: result.data,
        loading: { ...state.loading, extensions: false },
        errors: { ...state.errors, extensions: result.error || null },
        fallbackSections: updateFallbackSections(
          state.fallbackSections,
          'extensions',
          result.fallback,
        ),
        lastUpdatedAt: new Date().toISOString(),
      }));
      return result.data;
    } catch (error) {
      const message = getErrorMessage(error, 'Failed to load extensions');
      set((state) => ({
        loading: { ...state.loading, extensions: false },
        errors: { ...state.errors, extensions: message },
      }));
      throw error;
    }
  },

  createProject: async (input) => {
    const projectId = await projectExecutionApi.createProject(input);
    await Promise.all([
      get().loadProjects({ force: true }),
      get().loadProjectDetail(projectId, { force: true }),
    ]);
    return projectId;
  },

  updateProject: async (projectId, payload) => {
    const updatedId = await projectExecutionApi.updateProject(projectId, payload);
    await Promise.all([
      get().loadProjects({ force: true }),
      get().loadProjectDetail(projectId, { force: true }),
    ]);
    return updatedId;
  },

  deleteProject: async (projectId) => {
    await projectExecutionApi.deleteProject(projectId);
    set((state) => {
      const nextProjectDetails = { ...state.projectDetails };
      delete nextProjectDetails[projectId];
      const nextTaskDetails = Object.fromEntries(
        Object.entries(state.projectTaskDetails).filter(([key]) => !key.startsWith(`${projectId}:`)),
      );
      return {
        projects: state.projects.filter((project) => project.id !== projectId),
        projectDetails: nextProjectDetails,
        projectTaskDetails: nextTaskDetails,
      };
    });
  },

  createProjectTask: async (input) => {
    const taskId = await projectExecutionApi.createProjectTask(input);
    await Promise.all([
      get().loadProjects({ force: true }),
      get().loadProjectDetail(input.projectId, { force: true }),
      get().loadProjectTaskDetail(input.projectId, taskId),
    ]);
    return taskId;
  },

  deleteProjectTask: async (projectId, taskId) => {
    await projectExecutionApi.deleteProjectTask(taskId);
    set((state) => {
      const nextTaskDetails = { ...state.projectTaskDetails };
      delete nextTaskDetails[`${projectId}:${taskId}`];
      const projectDetail = state.projectDetails[projectId];
      const nextProjectDetail = projectDetail
        ? {
            ...projectDetail,
            tasks: projectDetail.tasks.filter((task) => task.id !== taskId),
            totalTasks: Math.max(0, projectDetail.totalTasks - 1),
            completedTasks: projectDetail.completedTasks - (projectDetail.tasks.some((task) => task.id === taskId && task.status === 'completed') ? 1 : 0),
            failedTasks: projectDetail.failedTasks - (projectDetail.tasks.some((task) => task.id === taskId && task.status === 'failed') ? 1 : 0),
          }
        : undefined;
      return {
        projectTaskDetails: nextTaskDetails,
        projectDetails: nextProjectDetail
          ? { ...state.projectDetails, [projectId]: nextProjectDetail }
          : state.projectDetails,
      };
    });
    await Promise.allSettled([
      get().loadProjects({ force: true }),
      get().loadProjectDetail(projectId, { force: true }),
    ]);
  },

  createProjectTaskAndLaunchRun: async (input) => {
    const { taskId, runId, needsClarification } =
      await projectExecutionApi.createProjectTaskAndLaunchRun(input);
    await Promise.allSettled([
      get().loadProjects({ force: true }),
      get().loadProjectDetail(input.projectId, { force: true }),
      get().loadProjectTaskDetail(input.projectId, taskId),
      ...(runId
        ? [get().loadRuns({ force: true }), get().loadRunDetail(runId, { force: true })]
        : []),
    ]);
    return { taskId, runId, needsClarification: Boolean(needsClarification || !runId) };
  },

  launchTaskRun: async (input) => {
    const { runId, needsClarification } = await projectExecutionApi.launchTaskRun(input);
    await Promise.all([
      get().loadProjectTaskDetail(input.projectId, input.taskId),
      get().loadProjectDetail(input.projectId, { force: true }),
      ...(runId
        ? [get().loadRuns({ force: true }), get().loadRunDetail(runId, { force: true })]
        : []),
    ]);
    return { runId, needsClarification: Boolean(needsClarification || !runId) };
  },

  markRunHandled: async (runId, handledAt, handledSignature, handledByUserId) => {
    await projectExecutionApi.markRunHandled(runId, {
      handledAt,
      handledSignature,
      handledByUserId,
    });
    const projectId =
      get().runDetails[runId]?.projectId || get().runs.find((run) => run.id === runId)?.projectId;
    await Promise.allSettled([
      get().loadRuns({ force: true }),
      get().loadRunDetail(runId, { force: true }),
      projectId ? get().loadProjectDetail(projectId, { force: true }) : Promise.resolve(),
    ]);
  },

  rescheduleRun: async (runId) => {
    const detail = await projectExecutionApi.rescheduleRun(runId);
    set((state) => ({
      runDetails: { ...state.runDetails, [runId]: detail },
    }));
    await Promise.allSettled([
      get().loadRuns({ force: true }),
      get().loadRunDetail(runId, { force: true }),
      detail.projectId
        ? get().loadProjectDetail(detail.projectId, { force: true })
        : Promise.resolve(detail.projectSummary),
    ]);
    return detail;
  },

  reset: () => {
    set(initialState());
  },
}));
