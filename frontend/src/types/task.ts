export type TaskStatus = 'pending' | 'in_progress' | 'completed' | 'failed' | 'blocked';

export type Task = {
  id: string;
  title: string;
  description?: string;
  status: TaskStatus;
  progress: number;
  assignedAgent?: string;
  dependencies?: string[];
  startTime?: string;
  endTime?: string;
  result?: string;
  error?: string;
};

export type Goal = {
  id: string;
  title: string;
  description: string;
  status: 'submitted' | 'analyzing' | 'decomposing' | 'executing' | 'completed' | 'failed';
  createdAt: string;
  completedAt?: string;
  tasks: Task[];
  clarificationNeeded?: boolean;
  clarificationQuestions?: string[];
};
