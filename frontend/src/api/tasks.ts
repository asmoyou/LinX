import apiClient from './client';
import type { Task, Goal } from '../types/task';

export interface SubmitGoalRequest {
  title: string;
  description: string;
  priority?: number;
}

export interface SubmitGoalResponse {
  goal: Goal;
  clarification_needed?: boolean;
  clarification_questions?: string[];
}

export interface AnswerClarificationRequest {
  answers: Record<string, string>;
}

export interface CreateTaskRequest {
  title: string;
  description?: string;
  goal_id?: string;
  parent_task_id?: string;
  assigned_agent_id?: string;
  priority?: number;
  dependencies?: string[];
}

/**
 * Tasks API
 */
export const tasksApi = {
  /**
   * Submit a new goal
   */
  submitGoal: async (data: SubmitGoalRequest): Promise<SubmitGoalResponse> => {
    const response = await apiClient.post<SubmitGoalResponse>('/goals', data);
    return response.data;
  },

  /**
   * Answer clarification questions
   */
  answerClarification: async (
    goalId: string,
    data: AnswerClarificationRequest
  ): Promise<Goal> => {
    const response = await apiClient.post<Goal>(`/goals/${goalId}/clarify`, data);
    return response.data;
  },

  /**
   * Get all goals
   */
  getAllGoals: async (): Promise<Goal[]> => {
    const response = await apiClient.get<Goal[]>('/goals');
    return response.data;
  },

  /**
   * Get goal by ID
   */
  getGoalById: async (goalId: string): Promise<Goal> => {
    const response = await apiClient.get<Goal>(`/goals/${goalId}`);
    return response.data;
  },

  /**
   * Delete goal
   */
  deleteGoal: async (goalId: string): Promise<void> => {
    await apiClient.delete(`/goals/${goalId}`);
  },

  /**
   * Get all tasks
   */
  getAllTasks: async (): Promise<Task[]> => {
    const response = await apiClient.get<Task[]>('/tasks');
    return response.data;
  },

  /**
   * Get task by ID
   */
  getTaskById: async (taskId: string): Promise<Task> => {
    const response = await apiClient.get<Task>(`/tasks/${taskId}`);
    return response.data;
  },

  /**
   * Create task
   */
  createTask: async (data: CreateTaskRequest): Promise<Task> => {
    const response = await apiClient.post<Task>('/tasks', data);
    return response.data;
  },

  /**
   * Delete task
   */
  deleteTask: async (taskId: string): Promise<void> => {
    await apiClient.delete(`/tasks/${taskId}`);
  },

  /**
   * Get task flow visualization data
   */
  getTaskFlow: async (goalId: string): Promise<any> => {
    const response = await apiClient.get(`/goals/${goalId}/flow`);
    return response.data;
  },

  /**
   * Cancel task
   */
  cancelTask: async (taskId: string): Promise<void> => {
    await apiClient.post(`/tasks/${taskId}/cancel`);
  },

  /**
   * Retry failed task
   */
  retryTask: async (taskId: string): Promise<Task> => {
    const response = await apiClient.post<Task>(`/tasks/${taskId}/retry`);
    return response.data;
  },
};
