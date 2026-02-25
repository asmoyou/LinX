import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Key, Plus, Trash2, AlertCircle } from 'lucide-react';
import { skillsApi } from '../../api/skills';
import { LayoutModal } from '../LayoutModal';
import { useNotificationStore } from '../../stores/notificationStore';

interface EnvVar {
  key: string;
  isVisible: boolean;
}

export const EnvVarsSettings: React.FC = () => {
  const { t } = useTranslation();
  const { addNotification } = useNotificationStore();
  
  const [envVars, setEnvVars] = useState<EnvVar[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');
  const [addingVar, setAddingVar] = useState(false);

  useEffect(() => {
    loadEnvVars();
  }, []);

  const loadEnvVars = async () => {
    try {
      setLoading(true);
      const keys = await skillsApi.listEnvVars();
      setEnvVars(keys.map(key => ({ key, isVisible: false })));
    } catch (error) {
      console.error('Failed to load env vars:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAddEnvVar = async () => {
    if (!newKey.trim() || !newValue.trim()) {
      addNotification({
        type: 'error',
        message: t('settings.envVars.keyValueRequired', 'Key and value are required'),
      });
      return;
    }

    // Validate key format
    if (!/^[A-Z][A-Z0-9_]*$/.test(newKey)) {
      addNotification({
        type: 'error',
        message: t('settings.envVars.invalidKeyFormat', 'Key must be uppercase alphanumeric with underscores'),
      });
      return;
    }

    try {
      setAddingVar(true);
      await skillsApi.setEnvVar(newKey, newValue);
      
      addNotification({
        type: 'success',
        message: t('settings.envVars.added', 'Environment variable added successfully'),
      });
      
      setNewKey('');
      setNewValue('');
      setShowAddModal(false);
      loadEnvVars();
    } catch (error) {
      console.error('Failed to add env var:', error);
      addNotification({
        type: 'error',
        message: t('settings.envVars.addFailed', 'Failed to add environment variable'),
      });
    } finally {
      setAddingVar(false);
    }
  };

  const handleDeleteEnvVar = async (key: string) => {
    if (!confirm(t('settings.envVars.confirmDelete', `Delete environment variable ${key}?`))) {
      return;
    }

    try {
      await skillsApi.deleteEnvVar(key);
      
      addNotification({
        type: 'success',
        message: t('settings.envVars.deleted', 'Environment variable deleted'),
      });
      
      loadEnvVars();
    } catch (error) {
      console.error('Failed to delete env var:', error);
      addNotification({
        type: 'error',
        message: t('settings.envVars.deleteFailed', 'Failed to delete environment variable'),
      });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
            {t('settings.envVars.title', 'Environment Variables')}
          </h2>
          <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-1">
            {t('settings.envVars.description', 'Configure API keys and secrets for your skills')}
          </p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors"
        >
          <Plus className="w-4 h-4" />
          {t('settings.envVars.add', 'Add Variable')}
        </button>
      </div>

      {/* Info Banner */}
      <div className="flex items-start gap-3 p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
        <AlertCircle className="w-5 h-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
        <div className="text-sm text-blue-800 dark:text-blue-300">
          <p className="font-medium mb-1">
            {t('settings.envVars.infoTitle', 'About Environment Variables')}
          </p>
          <p>
            {t('settings.envVars.infoText', 'Environment variables are used by skills to access API keys and other sensitive configuration. They are stored securely and only accessible to your skills during execution.')}
          </p>
        </div>
      </div>

      {/* Environment Variables List */}
      {envVars.length === 0 ? (
        <div className="text-center py-12 bg-zinc-50 dark:bg-zinc-800/50 rounded-lg border-2 border-dashed border-zinc-300 dark:border-zinc-700">
          <Key className="w-12 h-12 text-zinc-400 mx-auto mb-3" />
          <p className="text-zinc-600 dark:text-zinc-400 mb-4">
            {t('settings.envVars.empty', 'No environment variables configured')}
          </p>
          <button
            onClick={() => setShowAddModal(true)}
            className="text-emerald-600 dark:text-emerald-400 hover:underline"
          >
            {t('settings.envVars.addFirst', 'Add your first variable')}
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          {envVars.map((envVar) => (
            <div
              key={envVar.key}
              className="flex items-center justify-between p-4 bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-lg hover:border-zinc-300 dark:hover:border-zinc-600 transition-colors"
            >
              <div className="flex items-center gap-3">
                <Key className="w-5 h-5 text-zinc-400" />
                <div>
                  <p className="font-mono text-sm font-medium text-zinc-900 dark:text-zinc-100">
                    {envVar.key}
                  </p>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    {t('settings.envVars.valueHidden', 'Value is hidden for security')}
                  </p>
                </div>
              </div>
              <button
                onClick={() => handleDeleteEnvVar(envVar.key)}
                className="p-2 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                title={t('settings.envVars.delete', 'Delete')}
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Add Modal */}
      {showAddModal && (
        <LayoutModal
          isOpen={showAddModal}
          onClose={() => {
            setShowAddModal(false);
            setNewKey('');
            setNewValue('');
          }}
          closeOnBackdropClick={false}
          closeOnEscape={true}
          backdropClassName="bg-black/50"
        >
          <div className="w-full max-w-2xl my-auto modal-panel rounded-[24px] shadow-2xl max-h-[calc(100vh-var(--app-header-height,4rem)-3rem)] overflow-y-auto p-6">
            <h3 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100 mb-4">
              {t('settings.envVars.addNew', 'Add Environment Variable')}
            </h3>

            <div className="space-y-4">
              {/* Key Input */}
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('settings.envVars.keyLabel', 'Variable Name')}
                </label>
                <input
                  type="text"
                  value={newKey}
                  onChange={(e) => setNewKey(e.target.value.toUpperCase())}
                  placeholder="TAVILY_API_KEY"
                  className="w-full px-3 py-2 bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-600 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-transparent font-mono text-sm text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500"
                />
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                  {t('settings.envVars.keyHint', 'Use uppercase letters, numbers, and underscores')}
                </p>
              </div>

              {/* Value Input */}
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('settings.envVars.valueLabel', 'Value')}
                </label>
                <input
                  type="password"
                  value={newValue}
                  onChange={(e) => setNewValue(e.target.value)}
                  placeholder="tvly-xxxxxxxxxxxxx"
                  className="w-full px-3 py-2 bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-600 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-transparent font-mono text-sm text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500"
                />
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                  {t('settings.envVars.valueHint', 'API key or secret value')}
                </p>
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-3 mt-6">
              <button
                onClick={() => {
                  setShowAddModal(false);
                  setNewKey('');
                  setNewValue('');
                }}
                className="flex-1 px-4 py-2 border border-zinc-300 dark:border-zinc-600 text-zinc-700 dark:text-zinc-300 rounded-lg hover:bg-zinc-50 dark:hover:bg-zinc-700 transition-colors"
                disabled={addingVar}
              >
                {t('common.cancel', 'Cancel')}
              </button>
              <button
                onClick={handleAddEnvVar}
                disabled={addingVar || !newKey.trim() || !newValue.trim()}
                className="flex-1 px-4 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {addingVar ? t('common.adding', 'Adding...') : t('common.add', 'Add')}
              </button>
            </div>
          </div>
        </LayoutModal>
      )}
    </div>
  );
};
