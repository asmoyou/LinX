import React from 'react';
import { usePermissions } from '../hooks/usePermissions';

interface PermissionGateProps {
  requiredRoles?: string[];
  requireAdmin?: boolean;
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

export const PermissionGate: React.FC<PermissionGateProps> = ({
  requiredRoles,
  requireAdmin,
  children,
  fallback = null,
}) => {
  const { isAdmin, hasRole } = usePermissions();

  if (requireAdmin && !isAdmin) return <>{fallback}</>;
  if (requiredRoles && !hasRole(requiredRoles)) return <>{fallback}</>;

  return <>{children}</>;
};
