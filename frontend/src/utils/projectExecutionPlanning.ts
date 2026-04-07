export type ProjectExecutionStepKind =
  | 'host_action'
  | 'review'
  | 'writing'
  | 'research'
  | 'implementation';

export type ProjectExecutionMode = 'auto' | 'project_sandbox' | 'external_runtime';

export interface ProjectExecutionPlanPreview {
  initialStepKind: ProjectExecutionStepKind;
  runtimeType: 'external_worktree' | 'project_sandbox';
  requiresExternalRuntime: boolean;
  isMultiStep: boolean;
}

const HOST_KEYWORDS = [
  'deploy',
  'docker',
  'ssh',
  'terminal',
  '服务器',
  '宿主机',
  'browser',
  '浏览器',
];

const REVIEW_KEYWORDS = ['review', '评审', '审查', '检查', 'verify', '验证', '测试'];
const WRITING_KEYWORDS = ['write', '文档', '攻略', '总结', '方案', 'plan', '计划'];
const RESEARCH_KEYWORDS = ['research', '调研', '搜索', '旅游', '分析', '调查'];
const COMPLEXITY_MARKERS = ['并且', '然后', '以及', '同时', 'review', '验证', '部署', '方案', '研究', 'research'];

export const normalizeProjectExecutionMode = (
  value?: string | null,
): ProjectExecutionMode => {
  if (value === 'project_sandbox' || value === 'external_runtime') {
    return value;
  }
  return 'auto';
};

export const inferProjectExecutionStepKind = (
  title: string,
  description?: string | null,
  executionMode: ProjectExecutionMode = 'auto',
): ProjectExecutionStepKind => {
  if (executionMode === 'external_runtime') {
    return 'host_action';
  }
  const combined = `${title} ${description || ''}`.toLowerCase();
  if (executionMode !== 'project_sandbox' && HOST_KEYWORDS.some((keyword) => combined.includes(keyword))) {
    return 'host_action';
  }
  if (REVIEW_KEYWORDS.some((keyword) => combined.includes(keyword))) {
    return 'review';
  }
  if (WRITING_KEYWORDS.some((keyword) => combined.includes(keyword))) {
    return 'writing';
  }
  if (RESEARCH_KEYWORDS.some((keyword) => combined.includes(keyword))) {
    return 'research';
  }
  return 'implementation';
};

export const isComplexProjectExecutionTask = (
  title: string,
  description?: string | null,
): boolean => {
  const combined = `${title} ${description || ''}`;
  const lowerCombined = combined.toLowerCase();
  return (
    combined.length > 120 ||
    COMPLEXITY_MARKERS.some((marker) => lowerCombined.includes(marker.toLowerCase()))
  );
};

export const getProjectExecutionPlanPreview = (
  title: string,
  description?: string | null,
  executionMode: ProjectExecutionMode = 'auto',
): ProjectExecutionPlanPreview => {
  const inferredStepKind = inferProjectExecutionStepKind(title, description, executionMode);
  const isMultiStep =
    inferredStepKind !== 'host_action' && isComplexProjectExecutionTask(title, description);
  const initialStepKind = isMultiStep ? 'research' : inferredStepKind;
  const requiresExternalRuntime =
    executionMode === 'external_runtime' || inferredStepKind === 'host_action';

  return {
    initialStepKind,
    runtimeType: requiresExternalRuntime ? 'external_worktree' : 'project_sandbox',
    requiresExternalRuntime,
    isMultiStep,
  };
};
