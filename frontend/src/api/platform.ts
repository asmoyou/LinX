import apiClient from './client';
import type { UiExperienceSettings } from '@/motion';

export interface ProjectExecutionPlatformSettings {
  default_launch_command_template: string;
  planner_provider: string;
  planner_model: string;
  planner_temperature: number;
  planner_max_tokens: number;
}

export const platformApi = {
  getUiExperience: async (): Promise<UiExperienceSettings> => {
    const response = await apiClient.get<UiExperienceSettings>('/platform/settings/ui-experience');
    return response.data;
  },

  updateUiExperience: async (
    payload: UiExperienceSettings,
  ): Promise<UiExperienceSettings> => {
    const response = await apiClient.put<UiExperienceSettings>(
      '/platform/settings/ui-experience',
      payload,
    );
    return response.data;
  },
  getProjectExecutionSettings: async (): Promise<ProjectExecutionPlatformSettings> => {
    const response = await apiClient.get<ProjectExecutionPlatformSettings>('/platform/settings/project-execution');
    return response.data;
  },

  updateProjectExecutionSettings: async (
    payload: ProjectExecutionPlatformSettings,
  ): Promise<ProjectExecutionPlatformSettings> => {
    const response = await apiClient.put<ProjectExecutionPlatformSettings>('/platform/settings/project-execution', payload);
    return response.data;
  },
};
