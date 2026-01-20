
export enum AgentStatus {
  IDLE = 'IDLE',
  WORKING = 'WORKING',
  OFFLINE = 'OFFLINE',
  ERROR = 'ERROR'
}

export enum TaskStatus {
  PENDING = 'PENDING',
  IN_PROGRESS = 'IN_PROGRESS',
  COMPLETED = 'COMPLETED',
  FAILED = 'FAILED'
}

export interface Agent {
  id: string;
  name: string;
  type: string;
  description: string;
  skills: string[];
  status: AgentStatus;
  avatar: string;
}

export interface Task {
  id: string;
  goal: string;
  status: TaskStatus;
  assignedTo?: string;
  subTasks?: Task[];
  result?: string;
  progress: number;
}

export interface Goal {
  id: string;
  description: string;
  status: TaskStatus;
  tasks: Task[];
  createdAt: string;
}

export interface MemoryEntry {
  id: string;
  content: string;
  type: 'USER' | 'COMPANY' | 'AGENT';
  timestamp: string;
  tags: string[];
}

export interface KnowledgeDoc {
  id: string;
  title: string;
  content: string;
  type: 'DOCUMENT' | 'AUDIO' | 'VIDEO';
  lastModified: string;
}
