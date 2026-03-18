import { useState, useRef, useEffect } from 'react';
import { Camera, Copy, Eye, EyeOff, RefreshCw, Save, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { GlassPanel } from '../GlassPanel';
import { useUserStore, useDepartmentStore } from '../../stores';
import { usersApi } from '../../api/users';
import { useNotificationStore } from '../../stores/notificationStore';
import type { BindingCodeResponse } from '../../api/users';

export const ProfileSection = () => {
  const { t } = useTranslation();
  const { profile, setProfile, setLoading } = useUserStore();
  const { addNotification } = useNotificationStore();
  const { departments, fetchDepartments } = useDepartmentStore();
  const [isEditing, setIsEditing] = useState(false);
  const [formData, setFormData] = useState({
    displayName: '',
    email: '',
  });
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const [bindingCode, setBindingCode] = useState<BindingCodeResponse | null>(null);
  const [showBindingCode, setShowBindingCode] = useState(false);
  const [isBindingCodeLoading, setIsBindingCodeLoading] = useState(false);
  const [isBindingCodeRefreshing, setIsBindingCodeRefreshing] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch departments for display
  useEffect(() => {
    if (departments.length === 0) {
      fetchDepartments({ status: 'active' });
    }
  }, [departments.length, fetchDepartments]);

  // Sync formData with profile when profile changes
  useEffect(() => {
    if (profile) {
      setFormData({
        displayName: profile.displayName || profile.attributes?.display_name || '',
        email: profile.email || '',
      });
    }
  }, [profile]);

  useEffect(() => {
    let cancelled = false;

    const loadBindingCode = async () => {
      setIsBindingCodeLoading(true);
      try {
        const response = await usersApi.getBindingCode();
        if (!cancelled) {
          setBindingCode(response);
        }
      } catch (error: any) {
        if (!cancelled) {
          addNotification({
            type: 'error',
            title: t('profileSettings.profile.bindingCodeLoadFailed', 'Failed to load binding code'),
            message: error.response?.data?.detail || t('profileSettings.profile.bindingCodeLoadFailedMessage', 'Unable to load your binding code right now.'),
          });
        }
      } finally {
        if (!cancelled) {
          setIsBindingCodeLoading(false);
        }
      }
    };

    void loadBindingCode();
    return () => {
      cancelled = true;
    };
  }, [addNotification, t]);

  const handleAvatarClick = () => {
    fileInputRef.current?.click();
  };

  const handleAvatarChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Validate file type
    if (!file.type.startsWith('image/')) {
      addNotification({
        type: 'error',
        title: t('profileSettings.profile.invalidFile'),
        message: t('profileSettings.profile.invalidFileMessage'),
      });
      return;
    }

    // Validate file size (max 5MB)
    if (file.size > 5 * 1024 * 1024) {
      addNotification({
        type: 'error',
        title: t('profileSettings.profile.fileTooLarge'),
        message: t('profileSettings.profile.fileTooLargeMessage'),
      });
      return;
    }

    // Create preview
    const reader = new FileReader();
    reader.onloadend = () => {
      setAvatarPreview(reader.result as string);
    };
    reader.readAsDataURL(file);

    // Upload avatar
    setLoading(true);
    try {
      const result = await usersApi.uploadAvatar(file);
      
      // Update profile with new avatar URL
      if (profile) {
        const updatedProfile = {
          ...profile,
          attributes: {
            ...profile.attributes,
            avatar_url: result.avatar_url,
          },
        };
        setProfile(updatedProfile);
      }
      
      addNotification({
        type: 'success',
        title: t('profileSettings.profile.avatarUpdated'),
        message: t('profileSettings.profile.avatarUpdatedMessage'),
      });
    } catch (error: any) {
      console.error('Failed to upload avatar:', error);
      addNotification({
        type: 'error',
        title: t('profileSettings.profile.uploadFailed'),
        message: error.response?.data?.detail || t('profileSettings.profile.uploadFailedMessage'),
      });
      setAvatarPreview(null);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      // Convert camelCase to snake_case for backend
      const requestData = {
        email: formData.email,
        display_name: formData.displayName,
      };
      
      const updatedProfile = await usersApi.updateProfile(requestData);
      setProfile(updatedProfile);
      setIsEditing(false);
      addNotification({
        type: 'success',
        title: t('profileSettings.profile.profileUpdated'),
        message: t('profileSettings.profile.profileUpdatedMessage'),
      });
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: t('profileSettings.profile.updateFailed'),
        message: error.response?.data?.message || t('profileSettings.profile.updateFailedMessage'),
      });
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    setFormData({
      displayName: profile?.displayName || profile?.attributes?.display_name || '',
      email: profile?.email || '',
    });
    setIsEditing(false);
    setAvatarPreview(null);
  };

  const handleCopyBindingCode = async () => {
    if (!bindingCode?.code) return;
    try {
      await navigator.clipboard.writeText(bindingCode.code);
      addNotification({
        type: 'success',
        title: t('profileSettings.profile.bindingCodeCopied', 'Binding code copied'),
        message: t('profileSettings.profile.bindingCodeCopiedMessage', 'The binding code is ready to paste into Feishu or another platform.'),
      });
    } catch {
      addNotification({
        type: 'error',
        title: t('profileSettings.profile.bindingCodeCopyFailed', 'Copy failed'),
        message: t('profileSettings.profile.bindingCodeCopyFailedMessage', 'Clipboard access is not available in this browser.'),
      });
    }
  };

  const handleRefreshBindingCode = async () => {
    setIsBindingCodeRefreshing(true);
    try {
      const response = await usersApi.refreshBindingCode();
      setBindingCode(response);
      setShowBindingCode(true);
      addNotification({
        type: 'success',
        title: t('profileSettings.profile.bindingCodeRefreshed', 'Binding code refreshed'),
        message: t('profileSettings.profile.bindingCodeRefreshedMessage', 'The old code is now invalid and the new code is active immediately.'),
      });
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: t('profileSettings.profile.bindingCodeRefreshFailed', 'Refresh failed'),
        message: error.response?.data?.detail || t('profileSettings.profile.bindingCodeRefreshFailedMessage', 'Unable to refresh the binding code right now.'),
      });
    } finally {
      setIsBindingCodeRefreshing(false);
    }
  };

  return (
    <GlassPanel className="p-6">
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold text-zinc-900 dark:text-white">{t('profileSettings.profile.title')}</h2>
          {!isEditing && (
            <button
              onClick={() => setIsEditing(true)}
              className="px-4 py-2 bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 rounded-lg hover:bg-emerald-500/30 transition-colors border border-emerald-500/20"
            >
              {t('profileSettings.profile.editProfile')}
            </button>
          )}
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Avatar */}
          <div className="flex items-center gap-6">
            <div className="relative">
              <div className="w-24 h-24 rounded-full bg-gradient-to-br from-emerald-500 to-cyan-500 flex items-center justify-center text-white text-3xl font-bold overflow-hidden">
                {avatarPreview || profile?.attributes?.avatar_url ? (
                  <img 
                    src={avatarPreview || profile?.attributes?.avatar_url} 
                    alt="Avatar" 
                    className="w-full h-full object-cover" 
                  />
                ) : (
                  profile?.username?.charAt(0).toUpperCase() || 'U'
                )}
              </div>
              {/* Avatar upload button - only visible in edit mode */}
              {isEditing && (
                <button
                  type="button"
                  onClick={handleAvatarClick}
                  className="absolute bottom-0 right-0 p-2 bg-emerald-500 rounded-full hover:bg-emerald-600 transition-colors shadow-lg"
                  title={t('profileSettings.profile.uploadAvatar')}
                >
                  <Camera className="w-4 h-4 text-white" />
                </button>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={handleAvatarChange}
                className="hidden"
              />
            </div>
            <div>
              <h3 className="text-zinc-900 dark:text-white font-medium">{profile?.username}</h3>
              <p className="text-zinc-600 dark:text-zinc-400 text-sm">{profile?.email}</p>
              <p className="text-zinc-500 dark:text-zinc-500 text-xs mt-1">{t('profileSettings.profile.role')}: {profile?.role}</p>
            </div>
          </div>

          {/* Form Fields */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                {t('profileSettings.profile.displayName')}
              </label>
              <input
                type="text"
                value={formData.displayName}
                onChange={(e) => setFormData({ ...formData, displayName: e.target.value })}
                disabled={!isEditing}
                placeholder={t('profileSettings.profile.displayNamePlaceholder')}
                className="w-full px-4 py-2 bg-white dark:bg-white/5 border border-zinc-300 dark:border-white/10 rounded-lg text-zinc-900 dark:text-white placeholder-zinc-400 dark:placeholder-gray-500 focus:outline-none focus:border-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              />
              <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">{t('profileSettings.profile.displayNameHint')}</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                {t('profileSettings.profile.username')}
              </label>
              <div className="w-full px-4 py-2 bg-zinc-100 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700/50 rounded-lg text-zinc-600 dark:text-zinc-400">
                {profile?.username || '—'}
              </div>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">{t('profileSettings.profile.usernameHint')}</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                {t('profileSettings.profile.email')}
              </label>
              <input
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                disabled={!isEditing}
                className="w-full px-4 py-2 bg-white dark:bg-white/5 border border-zinc-300 dark:border-white/10 rounded-lg text-zinc-900 dark:text-white placeholder-zinc-400 dark:placeholder-gray-500 focus:outline-none focus:border-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                {t('profileSettings.profile.role')}
              </label>
              <div className="w-full px-4 py-2 bg-zinc-100 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700/50 rounded-lg text-zinc-600 dark:text-zinc-400 capitalize">
                {profile?.role || '—'}
              </div>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">{t('profileSettings.profile.roleHint')}</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                {t('departments.label', 'Department')}
              </label>
              <div className="w-full px-4 py-2 bg-zinc-100 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700/50 rounded-lg text-zinc-600 dark:text-zinc-400">
                {(() => {
                  if (!profile?.departmentId) return '—';
                  const dept = departments.find(d => d.id === profile.departmentId);
                  return dept?.name || profile.departmentId;
                })()}
              </div>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">{t('departments.assignedByAdmin', 'Assigned by administrator')}</p>
            </div>
          </div>

          <div className="rounded-2xl border border-zinc-200 bg-zinc-50/80 p-4 dark:border-zinc-800 dark:bg-zinc-950/40">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <h4 className="text-sm font-semibold text-zinc-900 dark:text-white">
                  {t('profileSettings.profile.bindingCode', 'User binding code')}
                </h4>
                <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                  {t('profileSettings.profile.bindingCodeHint', 'Use this code to bind your LinX identity in Feishu or future third-party platforms.')}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowBindingCode((prev) => !prev)}
                  className="inline-flex items-center gap-2 rounded-lg border border-zinc-200 px-3 py-2 text-xs font-semibold text-zinc-700 transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
                >
                  {showBindingCode ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                  {showBindingCode
                    ? t('profileSettings.profile.hideBindingCode', 'Hide')
                    : t('profileSettings.profile.showBindingCode', 'Show')}
                </button>
                <button
                  type="button"
                  onClick={() => void handleCopyBindingCode()}
                  disabled={!bindingCode}
                  className="inline-flex items-center gap-2 rounded-lg border border-zinc-200 px-3 py-2 text-xs font-semibold text-zinc-700 transition-colors hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
                >
                  <Copy className="w-3.5 h-3.5" />
                  {t('common.copy', 'Copy')}
                </button>
                <button
                  type="button"
                  onClick={() => void handleRefreshBindingCode()}
                  disabled={isBindingCodeRefreshing}
                  className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {isBindingCodeRefreshing ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <RefreshCw className="w-3.5 h-3.5" />
                  )}
                  {t('profileSettings.profile.refreshBindingCode', 'Refresh')}
                </button>
              </div>
            </div>

            <div className="mt-4 rounded-xl border border-dashed border-zinc-300 bg-white px-4 py-3 font-mono text-sm tracking-[0.2em] text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100">
              {isBindingCodeLoading
                ? t('common.loading', 'Loading...')
                : showBindingCode
                  ? bindingCode?.code || '—'
                  : bindingCode?.maskedCode || '—'}
            </div>

            {bindingCode?.updatedAt && (
              <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
                {t('profileSettings.profile.bindingCodeUpdatedAt', 'Last updated')}: {new Date(bindingCode.updatedAt).toLocaleString()}
              </p>
            )}
          </div>

          {/* Action Buttons */}
          {isEditing && (
            <div className="flex gap-3">
              <button
                type="submit"
                className="flex items-center gap-2 px-6 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors"
              >
                <Save className="w-4 h-4" />
                {t('profileSettings.profile.saveChanges')}
              </button>
              <button
                type="button"
                onClick={handleCancel}
                className="flex items-center gap-2 px-6 py-2 bg-zinc-100 dark:bg-white/5 text-zinc-700 dark:text-zinc-300 rounded-lg hover:bg-zinc-200 dark:hover:bg-white/10 transition-colors"
              >
                <X className="w-4 h-4" />
                {t('profileSettings.profile.cancel')}
              </button>
            </div>
          )}
        </form>
      </div>
    </GlassPanel>
  );
};
