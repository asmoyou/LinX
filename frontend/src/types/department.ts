/**
 * Department type definitions
 */

export interface Department {
  id: string;
  name: string;
  code: string;
  description?: string;
  parentId?: string;
  managerId?: string;
  managerName?: string;
  status: 'active' | 'archived';
  sortOrder: number;
  memberCount: number;
  agentCount: number;
  knowledgeCount: number;
  children: Department[];
  createdAt: string;
  updatedAt: string;
}

export interface DepartmentStats {
  memberCount: number;
  agentCount: number;
  knowledgeCount: number;
  activeTaskCount: number;
}

export interface DepartmentMember {
  userId: string;
  username: string;
  email: string;
  role: string;
  displayName?: string;
}

export interface DepartmentAgent {
  agentId: string;
  name: string;
  agentType: string;
  status: string;
  accessLevel?: string;
  ownerUsername?: string;
}

export interface CreateDepartmentRequest {
  name: string;
  code: string;
  description?: string;
  parent_id?: string;
  manager_id?: string;
  sort_order?: number;
}

export interface UpdateDepartmentRequest {
  name?: string;
  description?: string;
  parent_id?: string;
  manager_id?: string;
  status?: 'active' | 'archived';
  sort_order?: number;
}
