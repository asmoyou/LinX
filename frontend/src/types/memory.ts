export type MemoryType = 'agent' | 'company' | 'user_context';

export type Memory = {
  id: string;
  type: MemoryType;
  content: string;
  summary?: string;
  agentId?: string;
  agentName?: string;
  userId?: string;
  userName?: string;
  createdAt: string;
  updatedAt?: string;
  tags: string[];
  relevanceScore?: number;
  metadata?: {
    taskId?: string;
    goalId?: string;
    documentId?: string;
    [key: string]: any;
  };
  isShared?: boolean;
  sharedWith?: string[];
};

export type MemoryFilter = {
  type?: MemoryType;
  dateFrom?: string;
  dateTo?: string;
  tags?: string[];
  agentId?: string;
  userId?: string;
};
