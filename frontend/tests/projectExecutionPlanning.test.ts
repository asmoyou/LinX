import { describe, expect, it } from 'vitest';

import {
  getProjectExecutionPlanPreview,
  inferProjectExecutionStepKind,
  isComplexProjectExecutionTask,
} from '@/utils/projectExecutionPlanning';

describe('project execution planning preview', () => {
  it('classifies deploy and ssh work as host_action with external runtime', () => {
    expect(inferProjectExecutionStepKind('Deploy app to host', 'SSH to server and restart docker')).toBe(
      'host_action',
    );
    expect(
      getProjectExecutionPlanPreview('Deploy app to host', 'SSH to server and restart docker'),
    ).toMatchObject({
      initialStepKind: 'host_action',
      runtimeType: 'external_worktree',
      requiresExternalRuntime: true,
      isMultiStep: false,
    });
  });

  it('keeps regular implementation work in the project sandbox', () => {
    expect(getProjectExecutionPlanPreview('Fix onboarding modal', 'Adjust copy and validation')).toMatchObject({
      initialStepKind: 'implementation',
      runtimeType: 'project_sandbox',
      requiresExternalRuntime: false,
      isMultiStep: false,
    });
  });

  it('allows forcing project sandbox even when host keywords are present', () => {
    expect(
      getProjectExecutionPlanPreview(
        'Deploy app to host',
        'SSH to server and restart docker',
        'project_sandbox',
      ),
    ).toMatchObject({
      initialStepKind: 'implementation',
      runtimeType: 'project_sandbox',
      requiresExternalRuntime: false,
    });
  });

  it('allows forcing external runtime for non-host tasks', () => {
    expect(
      getProjectExecutionPlanPreview(
        'Generate changelog',
        'Summarize release notes',
        'external_runtime',
      ),
    ).toMatchObject({
      initialStepKind: 'host_action',
      runtimeType: 'external_worktree',
      requiresExternalRuntime: true,
    });
  });

  it('marks long research-style requests as multi-step', () => {
    const title = 'Research rollout options';
    const description =
      '调研当前方案，并且输出迁移建议，然后补一版评审说明，最后整理风险和验证方案。';

    expect(isComplexProjectExecutionTask(title, description)).toBe(true);
    expect(getProjectExecutionPlanPreview(title, description)).toMatchObject({
      initialStepKind: 'research',
      runtimeType: 'project_sandbox',
      requiresExternalRuntime: false,
      isMultiStep: true,
    });
  });
});
