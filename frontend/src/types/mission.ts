export type MissionStatus =
  | 'draft'
  | 'requirements'
  | 'planning'
  | 'executing'
  | 'reviewing'
  | 'qa'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type MissionAgentRole = 'leader' | 'supervisor' | 'qa' | 'worker';

export type MissionAgentStatus = 'assigned' | 'active' | 'idle' | 'completed' | 'failed';

export interface MissionConfig {
  max_retries?: number;
  task_timeout_s?: number;
  max_rework_cycles?: number;
  max_qa_cycles?: number;
  network_access?: boolean;
  debug_mode?: boolean;
  enable_team_blueprint?: boolean;
  prefer_existing_agents?: boolean;
  allow_temporary_workers?: boolean;
  auto_select_temp_skills?: boolean;
  temp_worker_skill_limit?: number;
  temp_worker_memory_scopes?: string[];
  temp_worker_knowledge_strategy?: string;
  temp_worker_knowledge_limit?: number;
  base_image?: string;
}

export interface Mission {
  mission_id: string;
  title: string;
  instructions: string;
  requirements_doc?: string;
  status: MissionStatus;
  created_by_user_id: string;
  department_id?: string;
  container_id?: string;
  workspace_bucket?: string;
  mission_config?: MissionConfig;
  result?: Record<string, unknown>;
  error_message?: string;
  total_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  updated_at: string;
}

export interface MissionAgent {
  id: string;
  mission_id: string;
  agent_id: string;
  agent_name?: string;
  role: MissionAgentRole;
  status: MissionAgentStatus;
  is_temporary: boolean;
  avatar?: string;
  assigned_at: string;
}

export interface MissionAttachment {
  attachment_id: string;
  mission_id: string;
  filename: string;
  file_reference: string;
  content_type: string;
  file_size: number;
  uploaded_at: string;
}

export interface MissionEvent {
  event_id: string;
  mission_id: string;
  event_type: string;
  agent_id?: string;
  task_id?: string;
  event_data?: Record<string, unknown>;
  message?: string;
  created_at: string;
}

export interface MissionDeliverable {
  filename: string;
  path: string;
  size: number;
  download_url: string;
  is_target: boolean;
}

export interface MissionTask {
  task_id: string;
  goal_text: string;
  status: string;
  priority: number;
  assigned_agent_id?: string;
  assigned_agent_name?: string;
  acceptance_criteria?: string;
  result?: Record<string, unknown>;
  task_metadata?: Record<string, unknown>;
  dependencies?: string[];
  parent_task_id?: string;
}

export interface MissionRoleConfig {
  llm_provider: string;
  llm_model: string;
  temperature: number;
  max_tokens: number;
}

export interface MissionExecutionConfig {
  max_retries: number;
  task_timeout_s: number;
  max_rework_cycles: number;
  max_qa_cycles: number;
  network_access: boolean;
  max_concurrent_tasks: number;
  debug_mode: boolean;
  enable_team_blueprint: boolean;
  prefer_existing_agents: boolean;
  allow_temporary_workers: boolean;
  auto_select_temp_skills: boolean;
  temp_worker_skill_limit: number;
  temp_worker_memory_scopes: string[];
  temp_worker_knowledge_strategy: string;
  temp_worker_knowledge_limit: number;
}

export interface MissionSettings {
  leader_config: MissionRoleConfig;
  supervisor_config: MissionRoleConfig;
  qa_config: MissionRoleConfig;
  temporary_worker_config: MissionRoleConfig;
  execution_config: MissionExecutionConfig;
}
