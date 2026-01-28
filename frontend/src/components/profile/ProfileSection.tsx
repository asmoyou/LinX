import { useState, useRef, useEffect } from 'react';
import { Camera, Save, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { GlassPanel } from '../GlassPanel';
import { useUserStore } from '../../stores';
import { usersApi } from '../../api/users';
import { useNotificationStore } from '../../stores/notificationStore';

export const ProfileSection = () => {
  const { t } = useTranslation();
  const { profile, setProfile, setLoading } = useUserStore();
  const { addNotification } = useNotificationStore();
  const [isEditing, setIsEditing] = useState(false);
  const [formData, setFormData] = useState({
    displayName: '',
    email: '',
  });
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Sync formData with profile when profile changes
  useEffect(() => {
    if (profile) {
      setFormData({
        displayName: profile.displayName || profile.attributes?.display_name || '',
        email: profile.email || '',
      });
    }
  }, [profile]);

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
              {/* Avatar upload button - always visible */}
              <button
                type="button"
                onClick={handleAvatarClick}
                className="absolute bottom-0 right-0 p-2 bg-emerald-500 rounded-full hover:bg-emerald-600 transition-colors shadow-lg"
                title={t('profileSettings.profile.uploadAvatar')}
              >
                <Camera className="w-4 h-4 text-white" />
              </button>
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
