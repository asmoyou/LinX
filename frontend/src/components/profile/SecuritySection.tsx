import { useEffect, useState } from 'react';
import { AlertCircle, Lock, ShieldCheck, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { GlassPanel } from '../GlassPanel';
import { usersApi, type TwoFactorSetupResponse, type TwoFactorStatus } from '@/api/users';
import { useNotificationStore } from '@/stores/notificationStore';

export const SecuritySection = () => {
  const { t } = useTranslation();
  const { addNotification } = useNotificationStore();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [passwordForm, setPasswordForm] = useState({
    currentPassword: '',
    newPassword: '',
    confirmPassword: '',
  });
  const [twoFactorStatus, setTwoFactorStatus] = useState<TwoFactorStatus | null>(null);
  const [twoFactorSetup, setTwoFactorSetup] = useState<TwoFactorSetupResponse | null>(null);
  const [twoFactorCode, setTwoFactorCode] = useState('');
  const [disableTwoFactorPassword, setDisableTwoFactorPassword] = useState('');
  const [isTwoFactorLoading, setIsTwoFactorLoading] = useState(true);
  const [isTwoFactorSubmitting, setIsTwoFactorSubmitting] = useState(false);

  const loadTwoFactorStatus = async () => {
    setIsTwoFactorLoading(true);
    try {
      const data = await usersApi.getTwoFactorStatus();
      setTwoFactorStatus(data);
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: t('profileSettings.security.twoFactorLoadFailedTitle', 'Failed to Load 2FA Status'),
        message:
          error?.response?.data?.detail ||
          error?.response?.data?.message ||
          t('profileSettings.security.twoFactorLoadFailedMessage', 'Unable to load two-factor status'),
      });
    } finally {
      setIsTwoFactorLoading(false);
    }
  };

  useEffect(() => {
    void loadTwoFactorStatus();
  }, []);

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();

    if (passwordForm.newPassword !== passwordForm.confirmPassword) {
      addNotification({
        type: 'error',
        title: t('profileSettings.security.passwordMismatchTitle', 'Password Mismatch'),
        message: t(
          'profileSettings.security.passwordMismatchMessage',
          'New password and confirmation do not match'
        ),
      });
      return;
    }

    if (passwordForm.newPassword.length < 8) {
      addNotification({
        type: 'error',
        title: t('profileSettings.security.weakPasswordTitle', 'Weak Password'),
        message: t(
          'profileSettings.security.weakPasswordMessage',
          'Password must be at least 8 characters long'
        ),
      });
      return;
    }

    if (passwordForm.currentPassword === passwordForm.newPassword) {
      addNotification({
        type: 'error',
        title: t('profileSettings.security.samePasswordTitle', 'No Change Detected'),
        message: t(
          'profileSettings.security.samePasswordMessage',
          'New password must be different from the current one'
        ),
      });
      return;
    }

    setIsSubmitting(true);
    try {
      await usersApi.changePassword(passwordForm.currentPassword, passwordForm.newPassword);
      addNotification({
        type: 'success',
        title: t('profileSettings.security.passwordChangedTitle', 'Password Changed'),
        message: t(
          'profileSettings.security.passwordChangedMessage',
          'Your password has been updated successfully'
        ),
      });
      setPasswordForm({
        currentPassword: '',
        newPassword: '',
        confirmPassword: '',
      });
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: t('profileSettings.security.passwordChangeFailedTitle', 'Password Change Failed'),
        message:
          error?.response?.data?.detail ||
          error?.response?.data?.message ||
          t(
            'profileSettings.security.passwordChangeFailedMessage',
            'Failed to update password. Please verify your current password and try again.'
          ),
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSetupTwoFactor = async () => {
    setIsTwoFactorSubmitting(true);
    try {
      const setup = await usersApi.setupTwoFactor();
      setTwoFactorSetup(setup);
      addNotification({
        type: 'success',
        title: t('profileSettings.security.twoFactorSetupReadyTitle', '2FA Setup Ready'),
        message: t('profileSettings.security.twoFactorSetupReadyMessage', 'Use your authenticator app and verification code to enable 2FA'),
      });
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: t('profileSettings.security.twoFactorSetupFailedTitle', '2FA Setup Failed'),
        message:
          error?.response?.data?.detail ||
          error?.response?.data?.message ||
          t('profileSettings.security.twoFactorSetupFailedMessage', 'Failed to start 2FA setup'),
      });
    } finally {
      setIsTwoFactorSubmitting(false);
    }
  };

  const handleEnableTwoFactor = async () => {
    if (!/^\d{6}$/.test(twoFactorCode)) {
      addNotification({
        type: 'error',
        title: t('profileSettings.security.twoFactorInvalidCodeTitle', 'Invalid Code'),
        message: t('profileSettings.security.twoFactorInvalidCodeMessage', 'Enter a valid 6-digit verification code'),
      });
      return;
    }

    setIsTwoFactorSubmitting(true);
    try {
      const status = await usersApi.enableTwoFactor(twoFactorCode);
      setTwoFactorStatus(status);
      setTwoFactorSetup(null);
      setTwoFactorCode('');
      addNotification({
        type: 'success',
        title: t('profileSettings.security.twoFactorEnabledTitle', '2FA Enabled'),
        message: t('profileSettings.security.twoFactorEnabledMessage', 'Two-factor authentication is now active'),
      });
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: t('profileSettings.security.twoFactorEnableFailedTitle', 'Enable Failed'),
        message:
          error?.response?.data?.detail ||
          error?.response?.data?.message ||
          t('profileSettings.security.twoFactorEnableFailedMessage', 'Failed to enable two-factor authentication'),
      });
    } finally {
      setIsTwoFactorSubmitting(false);
    }
  };

  const handleDisableTwoFactor = async () => {
    if (!disableTwoFactorPassword.trim()) {
      addNotification({
        type: 'error',
        title: t('profileSettings.security.twoFactorPasswordRequiredTitle', 'Password Required'),
        message: t('profileSettings.security.twoFactorPasswordRequiredMessage', 'Please enter your current password'),
      });
      return;
    }

    setIsTwoFactorSubmitting(true);
    try {
      const status = await usersApi.disableTwoFactor(disableTwoFactorPassword.trim());
      setTwoFactorStatus(status);
      setDisableTwoFactorPassword('');
      addNotification({
        type: 'success',
        title: t('profileSettings.security.twoFactorDisabledTitle', '2FA Disabled'),
        message: t('profileSettings.security.twoFactorDisabledMessage', 'Two-factor authentication has been disabled'),
      });
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: t('profileSettings.security.twoFactorDisableFailedTitle', 'Disable Failed'),
        message:
          error?.response?.data?.detail ||
          error?.response?.data?.message ||
          t('profileSettings.security.twoFactorDisableFailedMessage', 'Failed to disable two-factor authentication'),
      });
    } finally {
      setIsTwoFactorSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <GlassPanel className="p-6">
        <div className="space-y-6">
          <div className="flex items-center gap-3">
            <Lock className="w-5 h-5 text-emerald-500" />
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
              {t('profileSettings.security.changePasswordTitle', 'Change Password')}
            </h2>
          </div>

          <form onSubmit={handlePasswordChange} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                {t('profileSettings.security.currentPassword', 'Current Password')}
              </label>
              <input
                type="password"
                value={passwordForm.currentPassword}
                onChange={(e) =>
                  setPasswordForm({ ...passwordForm, currentPassword: e.target.value })
                }
                className="w-full px-4 py-2 bg-white dark:bg-white/5 border border-zinc-300 dark:border-white/10 rounded-lg text-zinc-900 dark:text-white focus:outline-none focus:border-emerald-500 transition-colors"
                autoComplete="current-password"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                {t('profileSettings.security.newPassword', 'New Password')}
              </label>
              <input
                type="password"
                value={passwordForm.newPassword}
                onChange={(e) => setPasswordForm({ ...passwordForm, newPassword: e.target.value })}
                className="w-full px-4 py-2 bg-white dark:bg-white/5 border border-zinc-300 dark:border-white/10 rounded-lg text-zinc-900 dark:text-white focus:outline-none focus:border-emerald-500 transition-colors"
                autoComplete="new-password"
                minLength={8}
                required
              />
              <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                {t(
                  'profileSettings.security.passwordHint',
                  'Use at least 8 characters, including letters, numbers, and symbols.'
                )}
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                {t('profileSettings.security.confirmPassword', 'Confirm New Password')}
              </label>
              <input
                type="password"
                value={passwordForm.confirmPassword}
                onChange={(e) =>
                  setPasswordForm({ ...passwordForm, confirmPassword: e.target.value })
                }
                className="w-full px-4 py-2 bg-white dark:bg-white/5 border border-zinc-300 dark:border-white/10 rounded-lg text-zinc-900 dark:text-white focus:outline-none focus:border-emerald-500 transition-colors"
                autoComplete="new-password"
                minLength={8}
                required
              />
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="px-6 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubmitting
                ? t('profileSettings.security.updatingPassword', 'Updating...')
                : t('profileSettings.security.updatePassword', 'Update Password')}
            </button>
          </form>
        </div>
      </GlassPanel>

      <GlassPanel className="p-6">
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <ShieldCheck className="w-5 h-5 text-emerald-500" />
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
              {t('profileSettings.security.accountProtectionTitle', 'Account Protection')}
            </h2>
          </div>

          {isTwoFactorLoading ? (
            <div className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-300">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>{t('profileSettings.security.twoFactorLoading', 'Loading 2FA status...')}</span>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="p-4 rounded-lg border border-zinc-300 dark:border-white/10 bg-zinc-50 dark:bg-zinc-900/30">
                <p className="text-sm text-zinc-700 dark:text-zinc-300">
                  {t('profileSettings.security.twoFactorStatusLabel', 'Two-factor status')}:{' '}
                  <span className={twoFactorStatus?.enabled ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'}>
                    {twoFactorStatus?.enabled
                      ? t('profileSettings.security.twoFactorEnabled', 'Enabled')
                      : t('profileSettings.security.twoFactorDisabled', 'Disabled')}
                  </span>
                </p>
                {twoFactorStatus?.enabled && (
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                    {t('profileSettings.security.twoFactorBackupCodes', 'Backup codes remaining')}: {twoFactorStatus.backup_codes_remaining}
                  </p>
                )}
              </div>

              {!twoFactorStatus?.enabled && !twoFactorSetup && (
                <button
                  onClick={handleSetupTwoFactor}
                  disabled={isTwoFactorSubmitting}
                  className="px-4 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors disabled:opacity-50 inline-flex items-center gap-2"
                >
                  {isTwoFactorSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
                  {t('profileSettings.security.startTwoFactorSetup', 'Start 2FA Setup')}
                </button>
              )}

              {!twoFactorStatus?.enabled && twoFactorSetup && (
                <div className="space-y-4 p-4 rounded-lg border border-emerald-300/40 bg-emerald-50 dark:bg-emerald-900/20 dark:border-emerald-700/40">
                  <p className="text-sm text-emerald-800 dark:text-emerald-300">
                    {t('profileSettings.security.twoFactorSetupHint', 'Add this secret to your authenticator app, then enter the 6-digit code.')}
                  </p>
                  <div className="p-3 bg-zinc-100 dark:bg-zinc-900/60 border border-zinc-200 dark:border-zinc-700 rounded-lg">
                    <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-1">
                      {t('profileSettings.security.twoFactorSecret', 'Secret')}
                    </p>
                    <code className="text-sm text-emerald-700 dark:text-emerald-300 break-all">{twoFactorSetup.secret}</code>
                  </div>
                  <div className="p-3 bg-zinc-100 dark:bg-zinc-900/60 border border-zinc-200 dark:border-zinc-700 rounded-lg">
                    <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-1">
                      {t('profileSettings.security.twoFactorBackupList', 'Backup Codes')}
                    </p>
                    <div className="grid grid-cols-2 gap-2">
                      {twoFactorSetup.backup_codes.map((code) => (
                        <code key={code} className="text-xs text-emerald-700 dark:text-emerald-300">
                          {code}
                        </code>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                      {t('profileSettings.security.twoFactorVerificationCode', 'Verification Code')}
                    </label>
                    <input
                      type="text"
                      inputMode="numeric"
                      value={twoFactorCode}
                      onChange={(e) => setTwoFactorCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                      placeholder="123456"
                      className="w-full px-4 py-2 bg-white dark:bg-white/5 border border-zinc-300 dark:border-white/10 rounded-lg text-zinc-900 dark:text-white focus:outline-none focus:border-emerald-500 transition-colors"
                    />
                  </div>
                  <button
                    onClick={handleEnableTwoFactor}
                    disabled={isTwoFactorSubmitting}
                    className="px-4 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors disabled:opacity-50 inline-flex items-center gap-2"
                  >
                    {isTwoFactorSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
                    {t('profileSettings.security.enableTwoFactor', 'Enable 2FA')}
                  </button>
                </div>
              )}

              {twoFactorStatus?.enabled && (
                <div className="space-y-3 p-4 rounded-lg border border-amber-300/50 bg-amber-50 dark:bg-amber-900/20 dark:border-amber-700/50">
                  <div className="flex items-start gap-3">
                    <AlertCircle className="w-4 h-4 text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0" />
                    <p className="text-sm text-amber-800 dark:text-amber-300">
                      {t('profileSettings.security.disableTwoFactorHint', 'Enter your current password to disable two-factor authentication.')}
                    </p>
                  </div>
                  <input
                    type="password"
                    value={disableTwoFactorPassword}
                    onChange={(e) => setDisableTwoFactorPassword(e.target.value)}
                    className="w-full px-4 py-2 bg-white dark:bg-white/5 border border-zinc-300 dark:border-white/10 rounded-lg text-zinc-900 dark:text-white focus:outline-none focus:border-amber-500 transition-colors"
                    placeholder={t('profileSettings.security.currentPassword', 'Current Password')}
                  />
                  <button
                    onClick={handleDisableTwoFactor}
                    disabled={isTwoFactorSubmitting}
                    className="px-4 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 transition-colors disabled:opacity-50 inline-flex items-center gap-2"
                  >
                    {isTwoFactorSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
                    {t('profileSettings.security.disableTwoFactor', 'Disable 2FA')}
                  </button>
                </div>
              )}
            </div>
          )}

          <ul className="space-y-2 text-sm text-zinc-600 dark:text-zinc-300">
            <li>
              {t(
                'profileSettings.security.tipRotatePassword',
                'Rotate credentials regularly and avoid reusing passwords across systems.'
              )}
            </li>
            <li>
              {t(
                'profileSettings.security.tipSessionAwareness',
                'Report suspicious login activity to your workspace administrator immediately.'
              )}
            </li>
          </ul>
        </div>
      </GlassPanel>
    </div>
  );
};
