import apiClient from './client';
import type { UiExperienceSettings } from '@/motion';

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
};
