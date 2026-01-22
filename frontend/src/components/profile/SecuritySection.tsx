import { useState } from 'react';
import { Lock, Shield, Check, X } from 'lucide-react';
import { GlassPanel } from '../GlassPanel';
import { useNotificationStore } from '../../stores/notificationStore';

export const SecuritySection = () => {
  const { addNotification } = useNotificationStore();
  const [passwordForm, setPasswordForm] = useState({
    currentPassword: '',
    newPassword: '',
    confirmPassword: '',
  });
  const [twoFactorEnabled, setTwoFactorEnabled] = useState(false);
  const [showQRCode, setShowQRCode] = useState(false);
  const [verificationCode, setVerificationCode] = useState('');

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validation
    if (passwordForm.newPassword !== passwordForm.confirmPassword) {
      addNotification({
        type: 'error',
        title: 'Password Mismatch',
        message: 'New password and confirmation do not match',
      });
      return;
    }

    if (passwordForm.newPassword.length < 8) {
      addNotification({
        type: 'error',
        title: 'Weak Password',
        message: 'Password must be at least 8 characters long',
      });
      return;
    }

    try {
      // TODO: Implement API call
      // await authApi.changePassword(passwordForm);
      
      addNotification({
        type: 'success',
        title: 'Password Changed',
        message: 'Your password has been updated successfully',
      });
      
      setPasswordForm({
        currentPassword: '',
        newPassword: '',
        confirmPassword: '',
      });
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: 'Password Change Failed',
        message: error.response?.data?.message || 'Failed to change password',
      });
    }
  };

  const handleEnable2FA = () => {
    setShowQRCode(true);
  };

  const handleVerify2FA = async () => {
    if (verificationCode.length !== 6) {
      addNotification({
        type: 'error',
        title: 'Invalid Code',
        message: 'Please enter a 6-digit verification code',
      });
      return;
    }

    try {
      // TODO: Implement API call
      // await authApi.enable2FA(verificationCode);
      
      setTwoFactorEnabled(true);
      setShowQRCode(false);
      setVerificationCode('');
      
      addNotification({
        type: 'success',
        title: '2FA Enabled',
        message: 'Two-factor authentication has been enabled',
      });
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: '2FA Setup Failed',
        message: error.response?.data?.message || 'Failed to enable 2FA',
      });
    }
  };

  const handleDisable2FA = async () => {
    try {
      // TODO: Implement API call
      // await authApi.disable2FA();
      
      setTwoFactorEnabled(false);
      
      addNotification({
        type: 'success',
        title: '2FA Disabled',
        message: 'Two-factor authentication has been disabled',
      });
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: '2FA Disable Failed',
        message: error.response?.data?.message || 'Failed to disable 2FA',
      });
    }
  };

  return (
    <div className="space-y-6">
      {/* Password Change */}
      <GlassPanel className="p-6">
        <div className="space-y-6">
          <div className="flex items-center gap-3">
            <Lock className="w-5 h-5 text-emerald-400" />
            <h2 className="text-xl font-semibold text-white">Change Password</h2>
          </div>

          <form onSubmit={handlePasswordChange} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Current Password
              </label>
              <input
                type="password"
                value={passwordForm.currentPassword}
                onChange={(e) => setPasswordForm({ ...passwordForm, currentPassword: e.target.value })}
                className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                New Password
              </label>
              <input
                type="password"
                value={passwordForm.newPassword}
                onChange={(e) => setPasswordForm({ ...passwordForm, newPassword: e.target.value })}
                className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500"
                required
                minLength={8}
              />
              <p className="text-xs text-gray-500 mt-1">
                Must be at least 8 characters long
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Confirm New Password
              </label>
              <input
                type="password"
                value={passwordForm.confirmPassword}
                onChange={(e) => setPasswordForm({ ...passwordForm, confirmPassword: e.target.value })}
                className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500"
                required
              />
            </div>

            <button
              type="submit"
              className="px-6 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors"
            >
              Change Password
            </button>
          </form>
        </div>
      </GlassPanel>

      {/* Two-Factor Authentication */}
      <GlassPanel className="p-6">
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Shield className="w-5 h-5 text-emerald-400" />
              <div>
                <h2 className="text-xl font-semibold text-white">Two-Factor Authentication</h2>
                <p className="text-sm text-gray-400 mt-1">
                  Add an extra layer of security to your account
                </p>
              </div>
            </div>
            <div className={`px-3 py-1 rounded-full text-xs font-medium ${
              twoFactorEnabled
                ? 'bg-emerald-500/20 text-emerald-400'
                : 'bg-gray-500/20 text-gray-400'
            }`}>
              {twoFactorEnabled ? 'Enabled' : 'Disabled'}
            </div>
          </div>

          {!twoFactorEnabled && !showQRCode && (
            <button
              onClick={handleEnable2FA}
              className="px-6 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors"
            >
              Enable 2FA
            </button>
          )}

          {showQRCode && (
            <div className="space-y-4">
              <div className="p-4 bg-white rounded-lg">
                <div className="w-48 h-48 bg-gray-200 mx-auto flex items-center justify-center">
                  <p className="text-gray-600 text-sm">QR Code Placeholder</p>
                </div>
              </div>
              <p className="text-sm text-gray-400">
                Scan this QR code with your authenticator app (Google Authenticator, Authy, etc.)
              </p>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Verification Code
                </label>
                <input
                  type="text"
                  value={verificationCode}
                  onChange={(e) => setVerificationCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  placeholder="000000"
                  className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500"
                  maxLength={6}
                />
              </div>
              <div className="flex gap-3">
                <button
                  onClick={handleVerify2FA}
                  className="flex items-center gap-2 px-6 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors"
                >
                  <Check className="w-4 h-4" />
                  Verify & Enable
                </button>
                <button
                  onClick={() => {
                    setShowQRCode(false);
                    setVerificationCode('');
                  }}
                  className="flex items-center gap-2 px-6 py-2 bg-white/5 text-gray-300 rounded-lg hover:bg-white/10 transition-colors"
                >
                  <X className="w-4 h-4" />
                  Cancel
                </button>
              </div>
            </div>
          )}

          {twoFactorEnabled && (
            <button
              onClick={handleDisable2FA}
              className="px-6 py-2 bg-red-500/20 text-red-400 rounded-lg hover:bg-red-500/30 transition-colors"
            >
              Disable 2FA
            </button>
          )}
        </div>
      </GlassPanel>
    </div>
  );
};
