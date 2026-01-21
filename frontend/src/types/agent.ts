export type Agent = {
  id: string;
  name: string;
  type: string;
  status: 'working' | 'idle' | 'offline';
  currentTask?: string;
  tasksCompleted: number;
  uptime: string;
};
