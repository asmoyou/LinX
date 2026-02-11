import apiClient from './client';

export interface RoleDetail {
  name: string;
  displayName: string;
  description: string;
  inheritsFrom: string | null;
  directPermissions: number;
  totalPermissions: number;
  permissions: string[];
}

export interface PermissionMatrixEntry {
  [role: string]: boolean;
}

export interface PermissionMatrix {
  resources: string[];
  actions: string[];
  roles: string[];
  matrix: Record<string, Record<string, PermissionMatrixEntry>>;
}

export interface RoleHierarchy {
  roles: Array<{
    name: string;
    level: number;
    inheritsFrom: string | null;
  }>;
}

function mapRoleDetail(data: any): RoleDetail {
  return {
    name: data.name,
    displayName: data.display_name || data.name,
    description: data.description || '',
    inheritsFrom: data.inherits_from || null,
    directPermissions: data.direct_permissions || 0,
    totalPermissions: data.total_permissions || 0,
    permissions: data.permissions || [],
  };
}

export const rolesApi = {
  list: async (): Promise<RoleDetail[]> => {
    const response = await apiClient.get<any>('/roles');
    return (response.data.roles || []).map(mapRoleDetail);
  },

  getById: async (roleName: string): Promise<RoleDetail> => {
    const response = await apiClient.get<any>(`/roles/${roleName}`);
    return mapRoleDetail(response.data);
  },

  getMatrix: async (): Promise<PermissionMatrix> => {
    const response = await apiClient.get<any>('/roles/matrix');
    return {
      resources: response.data.resources || [],
      actions: response.data.actions || [],
      roles: response.data.roles || [],
      matrix: response.data.matrix || {},
    };
  },

  getHierarchy: async (): Promise<RoleHierarchy> => {
    const response = await apiClient.get<any>('/roles/hierarchy');
    const hierarchy = response.data.hierarchy || {};
    const order = response.data.order || [];
    return {
      roles: order.map((name: string) => ({
        name,
        level: hierarchy[name] || 0,
        inheritsFrom: null,
      })),
    };
  },
};
