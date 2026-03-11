import { useEffect, useState } from 'react';
import { Download, Trash2, AlertTriangle, ShieldCheck, Loader2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { GlassPanel } from '../GlassPanel';
import { LayoutModal } from '../LayoutModal';
import { ModalPanel } from '../ModalPanel';
import { useNotificationStore } from '../../stores/notificationStore';
import { usersApi, type PrivacySettings } from '@/api/users';
import { clearClientSession } from '@/utils/clientSession';

export const PrivacySection = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { addNotification } = useNotificationStore();
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [privacySettings, setPrivacySettings] = useState<PrivacySettings>({
    profile_visibility: 'organization',
    searchable_profile: true,
    allow_telemetry: true,
    allow_training: false,
    data_retention_days: 365,
  });

  const loadPrivacySettings = async () => {
    setIsLoading(true);
    try {
      const data = await usersApi.getPrivacySettings();
      setPrivacySettings(data);
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: t('profileSettings.privacy.loadFailedTitle', 'Failed to Load Privacy Settings'),
        message:
          error?.response?.data?.detail ||
          error?.response?.data?.message ||
          t('profileSettings.privacy.loadFailedMessage', 'Unable to load privacy settings'),
      });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadPrivacySettings();
  }, []);

  const savePrivacySettings = async () => {
    setIsSaving(true);
    try {
      const saved = await usersApi.updatePrivacySettings(privacySettings);
      setPrivacySettings(saved);
      addNotification({
        type: 'success',
        title: t('profileSettings.privacy.savedTitle', 'Privacy Settings Updated'),
        message: t('profileSettings.privacy.savedMessage', 'Your privacy settings have been saved'),
      });
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: t('profileSettings.privacy.saveFailedTitle', 'Save Failed'),
        message:
          error?.response?.data?.detail ||
          error?.response?.data?.message ||
          t('profileSettings.privacy.saveFailedMessage', 'Failed to save privacy settings'),
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleExportData = async () => {
    setIsExporting(true);
    
    try {
      const result = await usersApi.exportUserData();

      const blob = new Blob([JSON.stringify(result.data, null, 2)], {
        type: 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = result.filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      
      addNotification({
        type: 'success',
        title: t('profileSettings.privacy.exportedTitle', 'Data Exported'),
        message: t('profileSettings.privacy.exportedMessage', 'Your data has been exported successfully'),
      });
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: t('profileSettings.privacy.exportFailedTitle', 'Export Failed'),
        message: error.response?.data?.message || 'Failed to export data',
      });
    } finally {
      setIsExporting(false);
    }
  };

  const handleDeleteAccount = async () => {
    if (deleteConfirmation !== 'DELETE') {
      addNotification({
        type: 'error',
        title: t('profileSettings.privacy.invalidConfirmationTitle', 'Invalid Confirmation'),
        message: t('profileSettings.privacy.invalidConfirmationMessage', 'Please type DELETE to confirm'),
      });
      return;
    }

    if (!currentPassword.trim()) {
      addNotification({
        type: 'error',
        title: t('profileSettings.privacy.passwordRequiredTitle', 'Password Required'),
        message: t('profileSettings.privacy.passwordRequiredMessage', 'Please enter your current password'),
      });
      return;
    }

    setIsDeleting(true);
    try {
      await usersApi.deleteAccount(currentPassword.trim(), deleteConfirmation);

      addNotification({
        type: 'success',
        title: t('profileSettings.privacy.deletedTitle', 'Account Deleted'),
        message: t('profileSettings.privacy.deletedMessage', 'Your account has been deleted'),
      });

      clearClientSession();
      navigate('/login');
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: t('profileSettings.privacy.deleteFailedTitle', 'Deletion Failed'),
        message: error.response?.data?.message || 'Failed to delete account',
      });
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Privacy Controls */}
      <GlassPanel className="p-6">
        <div className="space-y-6">
          <div className="flex items-center gap-3">
            <ShieldCheck className="w-5 h-5 text-emerald-400" />
            <div>
              <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
                {t('profileSettings.privacy.settingsTitle', 'Privacy Controls')}
              </h2>
              <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-1">
                {t('profileSettings.privacy.settingsSubtitle', 'Control visibility, telemetry and retention settings')}
              </p>
            </div>
          </div>

          {isLoading ? (
            <div className="flex items-center gap-2 text-zinc-600 dark:text-zinc-400">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>{t('profileSettings.privacy.loading', 'Loading privacy settings...')}</span>
            </div>
          ) : (
            <>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                    {t('profileSettings.privacy.profileVisibility', 'Profile Visibility')}
                  </label>
                  <select
                    value={privacySettings.profile_visibility}
                    onChange={(e) =>
                      setPrivacySettings((prev) => ({
                        ...prev,
                        profile_visibility: e.target.value as PrivacySettings['profile_visibility'],
                      }))
                    }
                    className="w-full px-4 py-2 bg-zinc-50 dark:bg-white/5 border border-zinc-300 dark:border-white/10 rounded-lg text-zinc-900 dark:text-white focus:outline-none focus:border-emerald-500"
                  >
                    <option value="private">{t('profileSettings.privacy.visibilityPrivate', 'Private')}</option>
                    <option value="team">{t('profileSettings.privacy.visibilityTeam', 'Team')}</option>
                    <option value="organization">{t('profileSettings.privacy.visibilityOrganization', 'Organization')}</option>
                  </select>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <label className="flex items-center justify-between p-4 rounded-lg bg-zinc-50 dark:bg-white/5 border border-zinc-200 dark:border-white/10">
                    <span className="text-sm text-zinc-700 dark:text-zinc-200">
                      {t('profileSettings.privacy.searchableProfile', 'Allow profile discovery')}
                    </span>
                    <input
                      type="checkbox"
                      checked={privacySettings.searchable_profile}
                      onChange={(e) =>
                        setPrivacySettings((prev) => ({
                          ...prev,
                          searchable_profile: e.target.checked,
                        }))
                      }
                      className="h-4 w-4 accent-emerald-500"
                    />
                  </label>

                  <label className="flex items-center justify-between p-4 rounded-lg bg-zinc-50 dark:bg-white/5 border border-zinc-200 dark:border-white/10">
                    <span className="text-sm text-zinc-700 dark:text-zinc-200">
                      {t('profileSettings.privacy.allowTelemetry', 'Allow telemetry collection')}
                    </span>
                    <input
                      type="checkbox"
                      checked={privacySettings.allow_telemetry}
                      onChange={(e) =>
                        setPrivacySettings((prev) => ({
                          ...prev,
                          allow_telemetry: e.target.checked,
                        }))
                      }
                      className="h-4 w-4 accent-emerald-500"
                    />
                  </label>

                  <label className="flex items-center justify-between p-4 rounded-lg bg-zinc-50 dark:bg-white/5 border border-zinc-200 dark:border-white/10">
                    <span className="text-sm text-zinc-700 dark:text-zinc-200">
                      {t('profileSettings.privacy.allowTraining', 'Allow anonymized model improvement')}
                    </span>
                    <input
                      type="checkbox"
                      checked={privacySettings.allow_training}
                      onChange={(e) =>
                        setPrivacySettings((prev) => ({
                          ...prev,
                          allow_training: e.target.checked,
                        }))
                      }
                      className="h-4 w-4 accent-emerald-500"
                    />
                  </label>

                  <div className="p-4 rounded-lg bg-zinc-50 dark:bg-white/5 border border-zinc-200 dark:border-white/10">
                    <label className="block text-sm text-zinc-700 dark:text-zinc-200 mb-2">
                      {t('profileSettings.privacy.retentionDays', 'Data retention days')}
                    </label>
                    <input
                      type="number"
                      min={30}
                      max={3650}
                      value={privacySettings.data_retention_days}
                      onChange={(e) =>
                        setPrivacySettings((prev) => ({
                          ...prev,
                          data_retention_days: Math.min(3650, Math.max(30, Number(e.target.value) || 365)),
                        }))
                      }
                      className="w-full px-3 py-2 bg-white dark:bg-zinc-900/60 border border-zinc-300 dark:border-white/10 rounded-lg text-zinc-900 dark:text-zinc-100 focus:outline-none focus:border-emerald-500"
                    />
                  </div>
                </div>
              </div>

              <button
                onClick={savePrivacySettings}
                disabled={isSaving}
                className="px-6 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors disabled:opacity-50 inline-flex items-center gap-2"
              >
                {isSaving && <Loader2 className="w-4 h-4 animate-spin" />}
                {isSaving ? t('profileSettings.privacy.saving', 'Saving...') : t('profileSettings.privacy.save', 'Save Privacy Settings')}
              </button>
            </>
          )}
        </div>
      </GlassPanel>

      {/* Data Export */}
      <GlassPanel className="p-6">
        <div className="space-y-6">
          <div className="flex items-center gap-3">
            <Download className="w-5 h-5 text-emerald-400" />
            <div>
              <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
                {t('profileSettings.privacy.exportTitle', 'Export Your Data')}
              </h2>
              <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-1">
                {t('profileSettings.privacy.exportSubtitle', 'Download a copy of your data (GDPR compliance)')}
              </p>
            </div>
          </div>

          <p className="text-zinc-700 dark:text-zinc-300">
            {t(
              'profileSettings.privacy.exportDescription',
              'You can request a copy of your data stored in the platform, including profile, agents, tasks, documents and memory records.'
            )}
          </p>

          <button
            onClick={handleExportData}
            disabled={isExporting}
            className="flex items-center gap-2 px-6 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Download className="w-4 h-4" />
            {isExporting
              ? t('profileSettings.privacy.exporting', 'Exporting...')
              : t('profileSettings.privacy.exportButton', 'Export Data')}
          </button>
        </div>
      </GlassPanel>

      {/* Account Deletion */}
      <GlassPanel className="p-6">
        <div className="space-y-6">
          <div className="flex items-center gap-3">
            <Trash2 className="w-5 h-5 text-red-400" />
            <div>
              <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
                {t('profileSettings.privacy.deleteTitle', 'Delete Account')}
              </h2>
              <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-1">
                {t('profileSettings.privacy.deleteSubtitle', 'Permanently delete your account and all associated data')}
              </p>
            </div>
          </div>

          <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
            <div className="flex gap-3">
              <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-red-700 dark:text-red-400">
                <p className="font-medium mb-2">{t('profileSettings.privacy.deleteWarningTitle', 'Warning: This action cannot be undone!')}</p>
                <ul className="list-disc list-inside space-y-1 text-red-700/80 dark:text-red-400/80">
                  <li>{t('profileSettings.privacy.deleteWarning1', 'All your agents will be terminated')}</li>
                  <li>{t('profileSettings.privacy.deleteWarning2', 'All your tasks and results will be deleted')}</li>
                  <li>{t('profileSettings.privacy.deleteWarning3', 'All your documents and memories will be removed')}</li>
                  <li>{t('profileSettings.privacy.deleteWarning4', 'Your account will be permanently deleted')}</li>
                </ul>
              </div>
            </div>
          </div>

          <button
            onClick={() => setShowDeleteModal(true)}
            className="px-6 py-2 bg-red-500/20 text-red-400 rounded-lg hover:bg-red-500/30 transition-colors"
          >
            {t('profileSettings.privacy.deleteButton', 'Delete My Account')}
          </button>
        </div>
      </GlassPanel>

      {/* Delete Confirmation Modal */}
      {showDeleteModal && (
        <LayoutModal
          isOpen={showDeleteModal}
          onClose={() => {
            setShowDeleteModal(false);
            setDeleteConfirmation('');
            setCurrentPassword('');
          }}
          closeOnBackdropClick={false}
          closeOnEscape={true}
        >
          <ModalPanel className="border border-red-500/30 max-w-md w-full mx-4">
            <div className="flex items-center gap-3 mb-4">
              <AlertTriangle className="w-6 h-6 text-red-400" />
              <h3 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
                {t('profileSettings.privacy.deleteTitle', 'Delete Account')}
              </h3>
            </div>
            
            <p className="text-zinc-700 dark:text-zinc-300 mb-4">
              {t('profileSettings.privacy.deleteModalDescription', 'This action is permanent and cannot be undone. All your data will be deleted.')}
            </p>

            <div className="mb-4">
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                {t('profileSettings.privacy.currentPassword', 'Current password')}
              </label>
              <input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                placeholder={t('profileSettings.privacy.currentPasswordPlaceholder', 'Enter current password')}
                className="w-full px-4 py-2 bg-zinc-50 dark:bg-white/5 border border-zinc-300 dark:border-white/10 rounded-lg text-zinc-900 dark:text-white placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:border-red-500"
              />
            </div>
            
            <div className="mb-6">
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                {t('profileSettings.privacy.typeDeletePrefix', 'Type')}{' '}
                <span className="text-red-400 font-bold">DELETE</span>{' '}
                {t('profileSettings.privacy.typeDeleteSuffix', 'to confirm')}
              </label>
              <input
                type="text"
                value={deleteConfirmation}
                onChange={(e) => setDeleteConfirmation(e.target.value)}
                placeholder="DELETE"
                className="w-full px-4 py-2 bg-zinc-50 dark:bg-white/5 border border-zinc-300 dark:border-white/10 rounded-lg text-zinc-900 dark:text-white placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:border-red-500"
              />
            </div>
            
            <div className="flex gap-3">
              <button
                onClick={handleDeleteAccount}
                disabled={deleteConfirmation !== 'DELETE' || !currentPassword.trim() || isDeleting}
                className="flex-1 px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center justify-center gap-2"
              >
                {isDeleting && <Loader2 className="w-4 h-4 animate-spin" />}
                {isDeleting
                  ? t('profileSettings.privacy.deleting', 'Deleting...')
                  : t('profileSettings.privacy.deleteTitle', 'Delete Account')}
              </button>
              <button
                onClick={() => {
                  setShowDeleteModal(false);
                  setDeleteConfirmation('');
                  setCurrentPassword('');
                }}
                className="flex-1 px-4 py-2 bg-zinc-100 dark:bg-white/5 text-zinc-700 dark:text-zinc-300 rounded-lg hover:bg-zinc-200 dark:hover:bg-white/10 transition-colors"
              >
                {t('common.cancel', 'Cancel')}
              </button>
            </div>
          </ModalPanel>
        </LayoutModal>
      )}
    </div>
  );
};
