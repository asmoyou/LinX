import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import {
  UserCog,
  Plus,
  Search,
  Edit2,
  Trash2,
  KeyRound,
  X,
  ChevronLeft,
  ChevronRight,
  Ban,
  CheckCircle2,
  ShieldAlert,
  Eye,
  EyeOff,
  Copy,
} from 'lucide-react';
import { usePermissions } from '@/hooks/usePermissions';
import { adminUsersApi } from '@/api/adminUsers';
import type { AdminUser, CreateUserRequest, UpdateUserRequest } from '@/api/adminUsers';
import { DepartmentSelect } from '@/components/departments/DepartmentSelect';
import { useAuthStore } from '@/stores';

// ─── Role Badge ──────────────────────────────────────────────────────────────

const roleBadgeColors: Record<string, string> = {
  admin: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  manager: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  user: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  viewer: 'bg-zinc-100 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-400',
};

const RoleBadge: React.FC<{ role: string }> = ({ role }) => {
  const { t } = useTranslation();
  return (
    <span
      className={`px-2 py-0.5 rounded-full text-xs font-medium ${
        roleBadgeColors[role] || roleBadgeColors.viewer
      }`}
    >
      {t(`roleManagement.roles.${role}`, role)}
    </span>
  );
};

// ─── Password Input with Visibility Toggle ──────────────────────────────────

interface PasswordInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  required?: boolean;
  minLength?: number;
  autoFocus?: boolean;
}

const PasswordInput: React.FC<PasswordInputProps> = ({
  value,
  onChange,
  placeholder,
  required,
  minLength = 8,
  autoFocus,
}) => {
  const [visible, setVisible] = useState(false);
  return (
    <div className="relative">
      <input
        type={visible ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        required={required}
        minLength={minLength}
        autoFocus={autoFocus}
        className="w-full px-3 py-2 pr-10 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
      />
      <button
        type="button"
        onClick={() => setVisible(!visible)}
        className="absolute right-2.5 top-1/2 -translate-y-1/2 p-0.5 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors"
        tabIndex={-1}
      >
        {visible ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
      </button>
    </div>
  );
};

// ─── Reset Password Dialog ───────────────────────────────────────────────────

interface ResetPasswordDialogProps {
  user: AdminUser;
  onClose: () => void;
  onSuccess: () => void;
}

const ResetPasswordDialog: React.FC<ResetPasswordDialogProps> = ({ user, onClose, onSuccess }) => {
  const { t } = useTranslation();
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [saving, setSaving] = useState(false);

  const passwordsMatch = newPassword === confirmPassword;
  const isValid = newPassword.length >= 8 && passwordsMatch;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid) return;
    setSaving(true);
    try {
      await adminUsersApi.resetPassword(user.id, newPassword);
      toast.success(t('userManagement.resetPasswordSuccess'));
      onSuccess();
      onClose();
    } catch {
      // Handled by interceptor
    } finally {
      setSaving(false);
    }
  };

  const handleCopyPassword = () => {
    if (newPassword) {
      navigator.clipboard.writeText(newPassword);
      toast.success(t('userManagement.passwordCopied'));
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-zinc-800 rounded-2xl shadow-2xl w-full max-w-md mx-4">
        <div className="flex items-center justify-between p-6 border-b border-zinc-200 dark:border-zinc-700">
          <div>
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
              {t('userManagement.resetPassword')}
            </h2>
            <p className="text-sm text-zinc-500 mt-0.5">
              {t('userManagement.resetPasswordFor', { username: user.username })}
            </p>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-700">
            <X className="w-5 h-5 text-zinc-500" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
              {t('userManagement.newPassword')} *
            </label>
            <div className="flex gap-2">
              <div className="flex-1">
                <PasswordInput
                  value={newPassword}
                  onChange={setNewPassword}
                  required
                  minLength={8}
                  autoFocus
                />
              </div>
              <button
                type="button"
                onClick={handleCopyPassword}
                disabled={!newPassword}
                className="p-2 rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-700 transition-colors disabled:opacity-30"
                title={t('userManagement.copyPassword')}
              >
                <Copy className="w-4 h-4" />
              </button>
            </div>
            {newPassword && newPassword.length < 8 && (
              <p className="text-xs text-amber-500 mt-1">{t('userManagement.passwordMinLength')}</p>
            )}
          </div>
          <div>
            <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
              {t('userManagement.confirmPassword')} *
            </label>
            <PasswordInput
              value={confirmPassword}
              onChange={setConfirmPassword}
              required
              minLength={8}
            />
            {confirmPassword && !passwordsMatch && (
              <p className="text-xs text-red-500 mt-1">{t('userManagement.passwordMismatch')}</p>
            )}
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-700 rounded-lg transition-colors"
            >
              {t('common.cancel')}
            </button>
            <button
              type="submit"
              disabled={saving || !isValid}
              className="px-4 py-2 text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg transition-colors disabled:opacity-50"
            >
              {saving ? t('common.loading') : t('userManagement.resetPassword')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

// ─── User Form Dialog ─────────────────────────────────────────────────────────

interface UserFormDialogProps {
  user?: AdminUser;
  onClose: () => void;
  onSaved: () => void;
}

const UserFormDialog: React.FC<UserFormDialogProps> = ({ user, onClose, onSaved }) => {
  const { t } = useTranslation();
  const isEditing = !!user;
  const { isAdmin } = usePermissions();

  const [username, setUsername] = useState(user?.username || '');
  const [email, setEmail] = useState(user?.email || '');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState(user?.role || 'user');
  const [departmentId, setDepartmentId] = useState<string | undefined>(user?.departmentId);
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (isEditing) {
        const data: UpdateUserRequest = {
          email,
          role,
          department_id: departmentId,
        };
        await adminUsersApi.update(user.id, data);
        toast.success(t('userManagement.updateSuccess'));
      } else {
        const data: CreateUserRequest = {
          username,
          email,
          password,
          role,
          department_id: departmentId,
        };
        await adminUsersApi.create(data);
        toast.success(t('userManagement.createSuccess'));
      }
      onSaved();
      onClose();
    } catch {
      // Error handled by apiClient interceptor
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-zinc-800 rounded-2xl shadow-2xl w-full max-w-md mx-4">
        <div className="flex items-center justify-between p-6 border-b border-zinc-200 dark:border-zinc-700">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
            {isEditing ? t('userManagement.editUser') : t('userManagement.createUser')}
          </h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-700">
            <X className="w-5 h-5 text-zinc-500" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {!isEditing && (
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                {t('userManagement.username')} *
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                minLength={3}
                maxLength={30}
                pattern="^[a-zA-Z0-9_-]+$"
                className="w-full px-3 py-2 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
              />
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
              {t('userManagement.email')} *
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full px-3 py-2 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
            />
          </div>
          {!isEditing && (
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                {t('userManagement.password')} *
              </label>
              <PasswordInput
                value={password}
                onChange={setPassword}
                required
                minLength={8}
              />
              {password && password.length < 8 && (
                <p className="text-xs text-amber-500 mt-1">{t('userManagement.passwordMinLength')}</p>
              )}
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
              {t('userManagement.role')}
            </label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              disabled={!isAdmin}
              className="w-full px-3 py-2 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50 disabled:opacity-50"
            >
              <option value="admin">{t('roleManagement.roles.admin')}</option>
              <option value="manager">{t('roleManagement.roles.manager')}</option>
              <option value="user">{t('roleManagement.roles.user')}</option>
              <option value="viewer">{t('roleManagement.roles.viewer')}</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
              {t('userManagement.department')}
            </label>
            <DepartmentSelect
              value={departmentId}
              onChange={setDepartmentId}
              showAll={false}
            />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-700 rounded-lg transition-colors"
            >
              {t('common.cancel')}
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg transition-colors disabled:opacity-50"
            >
              {saving ? t('common.loading') : t('common.save')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

// ─── Main User Management Page ─────────────────────────────────────────────

export const UserManagement: React.FC = () => {
  const { t } = useTranslation();
  const { isAdmin, isAdminOrManager } = usePermissions();
  const currentUser = useAuthStore((s) => s.user);

  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [departmentFilter, setDepartmentFilter] = useState<string | undefined>(undefined);
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingUser, setEditingUser] = useState<AdminUser | undefined>();
  const [resetPasswordUser, setResetPasswordUser] = useState<AdminUser | undefined>();

  const loadUsers = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, any> = {
        page,
        page_size: pageSize,
      };
      if (search) params.search = search;
      if (roleFilter) params.role = roleFilter;
      if (departmentFilter) params.department_id = departmentFilter;
      if (statusFilter) params.status = statusFilter;

      const response = await adminUsersApi.list(params);
      setUsers(response.users);
      setTotal(response.total);
    } catch {
      // Error handled by interceptor
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, search, roleFilter, departmentFilter, statusFilter]);

  useEffect(() => {
    if (isAdminOrManager) {
      loadUsers();
    }
  }, [loadUsers, isAdminOrManager]);

  // Debounced search
  const [searchInput, setSearchInput] = useState('');
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const handleDelete = async (user: AdminUser) => {
    if (user.id === currentUser?.id) {
      toast.error(t('userManagement.cannotDeleteSelf'));
      return;
    }
    if (!confirm(t('userManagement.confirmDelete'))) return;
    try {
      await adminUsersApi.delete(user.id);
      toast.success(t('userManagement.deleteSuccess'));
      loadUsers();
    } catch {
      // Handled by interceptor
    }
  };

  const handleToggleDisable = async (user: AdminUser) => {
    const msg = user.isDisabled
      ? t('userManagement.confirmEnable')
      : t('userManagement.confirmDisable');
    if (!confirm(msg)) return;
    try {
      await adminUsersApi.update(user.id, { is_disabled: !user.isDisabled });
      toast.success(
        user.isDisabled ? t('userManagement.enableSuccess') : t('userManagement.disableSuccess')
      );
      loadUsers();
    } catch {
      // Handled by interceptor
    }
  };

  const totalPages = Math.ceil(total / pageSize);

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
            <UserCog className="w-6 h-6 text-emerald-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-zinc-900 dark:text-white">
              {t('userManagement.title')}
            </h1>
            <p className="text-sm text-zinc-500">
              {t('userManagement.totalUsers')}: {total}
            </p>
          </div>
        </div>
        {isAdmin && (
          <button
            onClick={() => {
              setEditingUser(undefined);
              setShowForm(true);
            }}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium transition-colors"
          >
            <Plus className="w-4 h-4" />
            {t('userManagement.createUser')}
          </button>
        )}
      </div>

      {/* Filter Bar */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400" />
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder={t('userManagement.searchPlaceholder')}
            className="w-full pl-10 pr-4 py-2.5 bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
          />
        </div>
        <select
          value={roleFilter}
          onChange={(e) => {
            setRoleFilter(e.target.value);
            setPage(1);
          }}
          className="px-3 py-2.5 bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
        >
          <option value="">{t('userManagement.allRoles')}</option>
          <option value="admin">{t('roleManagement.roles.admin')}</option>
          <option value="manager">{t('roleManagement.roles.manager')}</option>
          <option value="user">{t('roleManagement.roles.user')}</option>
          <option value="viewer">{t('roleManagement.roles.viewer')}</option>
        </select>
        <DepartmentSelect
          value={departmentFilter}
          onChange={(v) => {
            setDepartmentFilter(v);
            setPage(1);
          }}
          showAll
          className="min-w-[180px]"
        />
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          className="px-3 py-2.5 bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
        >
          <option value="">{t('userManagement.allStatuses')}</option>
          <option value="active">{t('userManagement.active')}</option>
          <option value="disabled">{t('userManagement.disabled')}</option>
        </select>
      </div>

      {/* User Table */}
      <div className="bg-white dark:bg-zinc-800/30 rounded-xl border border-zinc-200 dark:border-zinc-700/50 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-200 dark:border-zinc-700/50">
                <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">
                  {t('userManagement.username')}
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">
                  {t('userManagement.email')}
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">
                  {t('userManagement.role')}
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">
                  {t('userManagement.department')}
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">
                  {t('userManagement.status')}
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">
                  {t('userManagement.createdAt')}
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-zinc-500 uppercase tracking-wider">
                  {t('userManagement.actions')}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-zinc-500">
                    {t('common.loading')}
                  </td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-zinc-500">
                    {t('userManagement.noUsers')}
                  </td>
                </tr>
              ) : (
                users.map((u) => (
                  <tr
                    key={u.id}
                    className="hover:bg-zinc-50 dark:hover:bg-zinc-800/50 transition-colors"
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-emerald-500 to-cyan-500 flex items-center justify-center text-[10px] font-bold text-white flex-shrink-0">
                          {(u.displayName || u.username).substring(0, 2).toUpperCase()}
                        </div>
                        <span className="font-medium text-zinc-900 dark:text-white">
                          {u.username}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400">{u.email}</td>
                    <td className="px-4 py-3">
                      <RoleBadge role={u.role} />
                    </td>
                    <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400">
                      {u.departmentName || '-'}
                    </td>
                    <td className="px-4 py-3">
                      {u.isDisabled ? (
                        <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400">
                          {t('userManagement.disabled')}
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
                          {t('userManagement.active')}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-zinc-500 text-xs">
                      {u.createdAt ? new Date(u.createdAt).toLocaleDateString() : '-'}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => {
                            setEditingUser(u);
                            setShowForm(true);
                          }}
                          className="p-1.5 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-700 text-zinc-400 hover:text-emerald-600 transition-colors"
                          title={t('userManagement.editUser')}
                        >
                          <Edit2 className="w-4 h-4" />
                        </button>
                        {isAdmin && (
                          <>
                            <button
                              onClick={() => setResetPasswordUser(u)}
                              className="p-1.5 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-700 text-zinc-400 hover:text-amber-600 transition-colors"
                              title={t('userManagement.resetPassword')}
                            >
                              <KeyRound className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => handleToggleDisable(u)}
                              className="p-1.5 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-700 text-zinc-400 hover:text-amber-600 transition-colors"
                              title={u.isDisabled ? t('userManagement.enable') : t('userManagement.disable')}
                            >
                              {u.isDisabled ? (
                                <CheckCircle2 className="w-4 h-4" />
                              ) : (
                                <Ban className="w-4 h-4" />
                              )}
                            </button>
                            {u.id !== currentUser?.id && (
                              <button
                                onClick={() => handleDelete(u)}
                                className="p-1.5 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-700 text-zinc-400 hover:text-red-600 transition-colors"
                                title={t('userManagement.deleteUser')}
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            )}
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-zinc-200 dark:border-zinc-700/50">
            <p className="text-xs text-zinc-500">
              {(page - 1) * pageSize + 1}-{Math.min(page * pageSize, total)} / {total}
            </p>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="p-1.5 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="px-3 py-1 text-xs text-zinc-600 dark:text-zinc-400">
                {page} / {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="p-1.5 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Form Dialog */}
      {showForm && (
        <UserFormDialog
          user={editingUser}
          onClose={() => setShowForm(false)}
          onSaved={loadUsers}
        />
      )}

      {/* Reset Password Dialog */}
      {resetPasswordUser && (
        <ResetPasswordDialog
          user={resetPasswordUser}
          onClose={() => setResetPasswordUser(undefined)}
          onSuccess={loadUsers}
        />
      )}
    </div>
  );
};

export default UserManagement;
