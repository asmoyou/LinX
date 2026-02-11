import { useAuthStore } from '../stores';

export const usePermissions = () => {
  const { user } = useAuthStore();
  const role = user?.role || 'viewer';

  return {
    isAdmin: role === 'admin',
    isManager: role === 'manager',
    isAdminOrManager: role === 'admin' || role === 'manager',
    canManageUsers: role === 'admin' || role === 'manager',
    hasRole: (roles: string[]) => roles.includes(role),
    role,
  };
};
