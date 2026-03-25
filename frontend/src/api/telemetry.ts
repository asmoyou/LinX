import apiClient from './client';

export interface FrontendMotionSummaryRequest {
  route_group: string;
  effective_tier: 'auto' | 'full' | 'reduced' | 'off';
  motion_preference: 'auto' | 'full' | 'reduced' | 'off';
  os_reduced_motion: boolean;
  save_data: boolean;
  device_class: 'low' | 'standard';
  avg_fps: number;
  p95_frame_ms: number;
  long_task_count: number;
  downgrade_count: number;
  sampled_at: string;
  app_version: string;
}

export const telemetryApi = {
  postFrontendMotionSummary: async (payload: FrontendMotionSummaryRequest): Promise<void> => {
    await apiClient.post('/telemetry/frontend-motion-summary', payload);
  },
};
