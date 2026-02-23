import apiClient from "./client";

export interface DashboardStats {
  active_agents: number;
  idle_agents: number;
  offline_agents: number;
  total_agents: number;
  goals_completed: number;
  goals_completed_in_window: number;
  missions_in_progress: number;
  tasks_completed: number;
  tasks_completed_24h: number;
  tasks_failed: number;
  tasks_in_progress: number;
  throughput_per_hour: number;
  success_rate: number;
  compute_load: number;
  memory_load: number;
}

export interface DashboardTaskDistributionPoint {
  date: string;
  tasks: number;
}

export interface DashboardEvent {
  id: string;
  type: "success" | "error" | "info";
  event_type: string;
  message: string;
  timestamp: string;
}

export interface DashboardOverviewResponse {
  stats: DashboardStats;
  task_distribution: DashboardTaskDistributionPoint[];
  task_completion_distribution: DashboardTaskDistributionPoint[];
  recent_events: DashboardEvent[];
  generated_at: string;
}

export const dashboardApi = {
  getOverview: async (params?: {
    days?: number;
    event_limit?: number;
  }): Promise<DashboardOverviewResponse> => {
    const response = await apiClient.get<DashboardOverviewResponse>(
      "/dashboard/overview",
      {
        params,
      },
    );
    return response.data;
  },
};
