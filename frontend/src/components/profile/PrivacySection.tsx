import { useState } from 'react';
import { Download, Trash2, AlertTriangle } from 'lucide-react';
import { GlassPanel } from '../GlassPanel';
import { useNotificationStore } from '../../stores/notificationStore';
import { useAuthStore } from '../../stores';

export const PrivacySection = () => {
  const { addNotification } = useNotificationStore();
  const { logout } = useAuthStore();
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState('');
  const [isExporting, setIsExporting] = useState(false);

  const handleExportData = async () => {
    setIsExporting(true);
    
    try {
      // TODO: Implement API call
      // const data = await usersApi.exportData();
      
      // Simulate export
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      // Create and download file
      const blob = new Blob([JSON.stringify({ message: 'User data export' }, null, 2)], {
        type: 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `user-data-export-${new Date().toISOString().split('T')[0]}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      
      addNotification({
        type: 'success',
        title: 'Data Exported',
        message: 'Your data has been exported successfully',
      });
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: 'Export Failed',
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
        title: 'Invalid Confirmation',
        message: 'Please type DELETE to confirm',
      });
      return;
    }

    try {
      // TODO: Implement API call
      // await usersApi.deleteAccount();
      
      addNotification({
        type: 'success',
        title: 'Account Deleted',
        message: 'Your account has been deleted',
      });
      
      // Log out and redirect
      setTimeout(() => {
        logout();
      }, 2000);
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: 'Deletion Failed',
        message: error.response?.data?.message || 'Failed to delete account',
      });
    }
  };

  return (
    <div className="space-y-6">
      {/* Data Export */}
      <GlassPanel className="p-6">
        <div className="space-y-6">
          <div className="flex items-center gap-3">
            <Download className="w-5 h-5 text-emerald-400" />
            <div>
              <h2 className="text-xl font-semibold text-white">Export Your Data</h2>
              <p className="text-sm text-gray-400 mt-1">
                Download a copy of your data (GDPR compliance)
              </p>
            </div>
          </div>

          <p className="text-gray-300">
            You can request a copy of all your data stored in the platform. This includes your profile information,
            agents, tasks, documents, and memories.
          </p>

          <button
            onClick={handleExportData}
            disabled={isExporting}
            className="flex items-center gap-2 px-6 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Download className="w-4 h-4" />
            {isExporting ? 'Exporting...' : 'Export Data'}
          </button>
        </div>
      </GlassPanel>

      {/* Account Deletion */}
      <GlassPanel className="p-6">
        <div className="space-y-6">
          <div className="flex items-center gap-3">
            <Trash2 className="w-5 h-5 text-red-400" />
            <div>
              <h2 className="text-xl font-semibold text-white">Delete Account</h2>
              <p className="text-sm text-gray-400 mt-1">
                Permanently delete your account and all associated data
              </p>
            </div>
          </div>

          <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
            <div className="flex gap-3">
              <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-red-400">
                <p className="font-medium mb-2">Warning: This action cannot be undone!</p>
                <ul className="list-disc list-inside space-y-1 text-red-400/80">
                  <li>All your agents will be terminated</li>
                  <li>All your tasks and results will be deleted</li>
                  <li>All your documents and memories will be removed</li>
                  <li>Your account will be permanently deleted</li>
                </ul>
              </div>
            </div>
          </div>

          <button
            onClick={() => setShowDeleteModal(true)}
            className="px-6 py-2 bg-red-500/20 text-red-400 rounded-lg hover:bg-red-500/30 transition-colors"
          >
            Delete My Account
          </button>
        </div>
      </GlassPanel>

      {/* Delete Confirmation Modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-red-500/30 rounded-lg p-6 max-w-md w-full mx-4">
            <div className="flex items-center gap-3 mb-4">
              <AlertTriangle className="w-6 h-6 text-red-400" />
              <h3 className="text-xl font-semibold text-white">Delete Account</h3>
            </div>
            
            <p className="text-gray-300 mb-4">
              This action is permanent and cannot be undone. All your data will be deleted.
            </p>
            
            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Type <span className="text-red-400 font-bold">DELETE</span> to confirm
              </label>
              <input
                type="text"
                value={deleteConfirmation}
                onChange={(e) => setDeleteConfirmation(e.target.value)}
                placeholder="DELETE"
                className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-red-500"
              />
            </div>
            
            <div className="flex gap-3">
              <button
                onClick={handleDeleteAccount}
                disabled={deleteConfirmation !== 'DELETE'}
                className="flex-1 px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Delete Account
              </button>
              <button
                onClick={() => {
                  setShowDeleteModal(false);
                  setDeleteConfirmation('');
                }}
                className="flex-1 px-4 py-2 bg-white/5 text-gray-300 rounded-lg hover:bg-white/10 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
