import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ShieldCheck,
  LayoutGrid,
  Table2,
  ChevronDown,
  ChevronRight,
  Check,
  X as XIcon,
  ShieldAlert,
  Lock,
  Info,
} from 'lucide-react';
import { usePermissions } from '@/hooks/usePermissions';
import { rolesApi } from '@/api/roles';
import type { RoleDetail, PermissionMatrix } from '@/api/roles';

// ─── Role Colors ────────────────────────────────────────────────────────────

const roleColors: Record<string, { bg: string; text: string; border: string; accent: string }> = {
  admin: {
    bg: 'bg-red-50 dark:bg-red-900/20',
    text: 'text-red-700 dark:text-red-400',
    border: 'border-red-200 dark:border-red-800/50',
    accent: 'bg-red-500',
  },
  manager: {
    bg: 'bg-blue-50 dark:bg-blue-900/20',
    text: 'text-blue-700 dark:text-blue-400',
    border: 'border-blue-200 dark:border-blue-800/50',
    accent: 'bg-blue-500',
  },
  user: {
    bg: 'bg-emerald-50 dark:bg-emerald-900/20',
    text: 'text-emerald-700 dark:text-emerald-400',
    border: 'border-emerald-200 dark:border-emerald-800/50',
    accent: 'bg-emerald-500',
  },
  viewer: {
    bg: 'bg-zinc-50 dark:bg-zinc-800/50',
    text: 'text-zinc-600 dark:text-zinc-400',
    border: 'border-zinc-200 dark:border-zinc-700',
    accent: 'bg-zinc-500',
  },
};

// ─── Role Card Component ─────────────────────────────────────────────────────

interface RoleCardProps {
  role: RoleDetail;
}

const RoleCard: React.FC<RoleCardProps> = ({ role }) => {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const colors = roleColors[role.name] || roleColors.viewer;

  // Group permissions by resource
  const permissionGroups: Record<string, string[]> = {};
  (role.permissions || []).forEach((perm) => {
    const parts = perm.split(':');
    const resource = parts[0] || 'other';
    const action = parts.slice(1).join(':') || perm;
    if (!permissionGroups[resource]) permissionGroups[resource] = [];
    permissionGroups[resource].push(action);
  });

  return (
    <div
      className={`rounded-xl border ${colors.border} overflow-hidden transition-all hover:shadow-md`}
    >
      {/* Color accent bar */}
      <div className={`h-1 ${colors.accent}`} />

      <div className={`p-5 ${colors.bg}`}>
        {/* Role header */}
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${colors.bg} border ${colors.border}`}>
              <ShieldCheck className={`w-5 h-5 ${colors.text}`} />
            </div>
            <div>
              <h3 className={`text-base font-semibold ${colors.text}`}>
                {t(`roleManagement.roles.${role.name}`, role.displayName)}
              </h3>
              {role.inheritsFrom && (
                <p className="text-xs text-zinc-500 mt-0.5">
                  {t('roleManagement.inheritsFrom')}: {t(`roleManagement.roles.${role.inheritsFrom}`, role.inheritsFrom)}
                </p>
              )}
            </div>
          </div>
          <span className={`px-2.5 py-1 rounded-lg text-xs font-medium ${colors.text} ${colors.bg} border ${colors.border}`}>
            {role.totalPermissions} {t('roleManagement.permissions').toLowerCase()}
          </span>
        </div>

        {/* Description */}
        <p className="text-sm text-zinc-600 dark:text-zinc-400 mb-4">
          {t(`roleManagement.descriptions.${role.name}`, role.description)}
        </p>

        {/* Expandable permissions */}
        <button
          onClick={() => setExpanded(!expanded)}
          className={`flex items-center gap-1.5 text-xs font-medium ${colors.text} hover:opacity-80 transition-opacity`}
        >
          {expanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
          {expanded ? t('common.hide') : t('common.show')} {t('roleManagement.permissions').toLowerCase()}
        </button>

        {expanded && (
          <div className="mt-3 space-y-2.5">
            {Object.entries(permissionGroups).map(([resource, actions]) => (
              <div key={resource} className="bg-white/60 dark:bg-zinc-800/40 rounded-lg p-3">
                <p className="text-xs font-semibold text-zinc-700 dark:text-zinc-300 mb-1.5">
                  {t(`roleManagement.resources.${resource}`, resource)}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {actions.map((action) => (
                    <span
                      key={action}
                      className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] bg-white dark:bg-zinc-800 rounded-md border border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-400"
                    >
                      <Check className="w-3 h-3 text-emerald-500" />
                      {t(`roleManagement.actions.${action}`, action)}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

// ─── Permission Matrix View ──────────────────────────────────────────────────

interface MatrixViewProps {
  matrix: PermissionMatrix;
}

const MatrixView: React.FC<MatrixViewProps> = ({ matrix }) => {
  const { t } = useTranslation();

  if (!matrix.resources.length) {
    return (
      <div className="text-center py-8 text-zinc-500">
        {t('common.loading')}
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-zinc-800/30 rounded-xl border border-zinc-200 dark:border-zinc-700/50 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-200 dark:border-zinc-700/50">
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider w-36">
                {t('roleManagement.resource')}
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider w-28">
                {t('roleManagement.action')}
              </th>
              {matrix.roles.map((role) => {
                const colors = roleColors[role] || roleColors.viewer;
                return (
                  <th
                    key={role}
                    className={`px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider ${colors.text}`}
                  >
                    {t(`roleManagement.roles.${role}`, role)}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {matrix.resources.map((resource, resourceIdx) => (
              <React.Fragment key={resource}>
                {/* Resource group separator */}
                {resourceIdx > 0 && (
                  <tr>
                    <td colSpan={2 + matrix.roles.length} className="h-px bg-zinc-200 dark:bg-zinc-700" />
                  </tr>
                )}
                {matrix.actions.map((action, actionIdx) => (
                  <tr
                    key={`${resource}-${action}`}
                    className="hover:bg-zinc-50 dark:hover:bg-zinc-800/50 transition-colors"
                  >
                    {actionIdx === 0 && (
                      <td
                        rowSpan={matrix.actions.length}
                        className="px-4 py-2 text-xs font-semibold text-zinc-700 dark:text-zinc-300 align-top pt-3 border-r border-zinc-100 dark:border-zinc-800"
                      >
                        {t(`roleManagement.resources.${resource}`, resource)}
                      </td>
                    )}
                    <td className="px-4 py-2 text-xs text-zinc-600 dark:text-zinc-400">
                      {t(`roleManagement.actions.${action}`, action)}
                    </td>
                    {matrix.roles.map((role) => {
                      const allowed =
                        matrix.matrix[resource]?.[action]?.[role] ?? false;
                      return (
                        <td key={role} className="px-4 py-2 text-center">
                          {allowed ? (
                            <Check className="w-4 h-4 mx-auto text-emerald-500" />
                          ) : (
                            <XIcon className="w-4 h-4 mx-auto text-zinc-300 dark:text-zinc-600" />
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// ─── Main Role Management Page ───────────────────────────────────────────────

export const RoleManagement: React.FC = () => {
  const { t } = useTranslation();
  const { isAdminOrManager } = usePermissions();
  const [view, setView] = useState<'cards' | 'matrix'>('cards');
  const [roles, setRoles] = useState<RoleDetail[]>([]);
  const [matrix, setMatrix] = useState<PermissionMatrix>({
    resources: [],
    actions: [],
    roles: [],
    matrix: {},
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isAdminOrManager) return;

    const loadData = async () => {
      setLoading(true);
      try {
        const [rolesData, matrixData] = await Promise.all([
          rolesApi.list(),
          rolesApi.getMatrix(),
        ]);
        setRoles(rolesData);
        setMatrix(matrixData);
      } catch {
        // Error handled by interceptor
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [isAdminOrManager]);

  if (!isAdminOrManager) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center">
          <ShieldAlert className="w-16 h-16 mx-auto mb-4 text-zinc-300 dark:text-zinc-600" />
          <h2 className="text-lg font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
            {t('userManagement.accessDenied')}
          </h2>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-emerald-500/10">
            <ShieldCheck className="w-6 h-6 text-emerald-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-zinc-900 dark:text-white">
              {t('roleManagement.title')}
            </h1>
            <p className="text-sm text-zinc-500">
              {t('roleManagement.subtitle')}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {/* Read-only notice */}
          <div className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800/50">
            <Lock className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
            <span className="text-xs text-amber-700 dark:text-amber-400">{t('roleManagement.readOnly')}</span>
          </div>
          {/* View toggle */}
          <div className="flex items-center bg-zinc-100 dark:bg-zinc-800 rounded-lg p-0.5">
            <button
              onClick={() => setView('cards')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                view === 'cards'
                  ? 'bg-white dark:bg-zinc-700 text-emerald-600 shadow-sm'
                  : 'text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300'
              }`}
            >
              <LayoutGrid className="w-3.5 h-3.5" />
              {t('roleManagement.cardsView')}
            </button>
            <button
              onClick={() => setView('matrix')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                view === 'matrix'
                  ? 'bg-white dark:bg-zinc-700 text-emerald-600 shadow-sm'
                  : 'text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300'
              }`}
            >
              <Table2 className="w-3.5 h-3.5" />
              {t('roleManagement.matrixView')}
            </button>
          </div>
        </div>
      </div>

      {/* Info banner */}
      <div className="flex items-start gap-3 p-4 mb-6 rounded-xl bg-blue-50 dark:bg-blue-900/10 border border-blue-200 dark:border-blue-800/30">
        <Info className="w-4 h-4 text-blue-500 mt-0.5 flex-shrink-0" />
        <p className="text-xs text-blue-700 dark:text-blue-400 leading-relaxed">
          {t('roleManagement.infoMessage')}
        </p>
      </div>

      {loading ? (
        <div className="text-center py-12 text-zinc-500">{t('common.loading')}</div>
      ) : view === 'cards' ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {roles.map((role) => (
            <RoleCard key={role.name} role={role} />
          ))}
        </div>
      ) : (
        <MatrixView matrix={matrix} />
      )}
    </div>
  );
};

export default RoleManagement;
