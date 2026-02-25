import { useEffect, useState } from 'react';
import { Key, Plus, Copy, Trash2, Loader2, ShieldCheck } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { GlassPanel } from '../GlassPanel';
import { LayoutModal } from '../LayoutModal';
import { useNotificationStore } from '../../stores/notificationStore';
import { usersApi, type CreateApiKeyResponse, type UserApiKey } from '@/api/users';

interface CreatedKeyInfo {
  keyId: string;
  name: string;
  key: string;
  prefix: string;
  createdAt: string;
}

export const APIKeysSection = () => {
  const { t } = useTranslation();
  const { addNotification } = useNotificationStore();
  const [apiKeys, setApiKeys] = useState<UserApiKey[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [deletingKeyId, setDeletingKeyId] = useState<string | null>(null);
  const [showNewKeyModal, setShowNewKeyModal] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [createdKey, setCreatedKey] = useState<CreatedKeyInfo | null>(null);

  const loadApiKeys = async () => {
    setIsLoading(true);
    try {
      const list = await usersApi.getApiKeys();
      setApiKeys(list);
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: t('profileSettings.apiKeys.loadFailedTitle', 'Failed to Load API Keys'),
        message:
          error?.response?.data?.detail ||
          error?.response?.data?.message ||
          t('profileSettings.apiKeys.loadFailedMessage', 'Unable to load API key list'),
      });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadApiKeys();
  }, []);

  const handleCreateKey = async () => {
    if (!newKeyName.trim()) {
      addNotification({
        type: 'error',
        title: t('profileSettings.apiKeys.invalidNameTitle', 'Invalid Name'),
        message: t('profileSettings.apiKeys.invalidNameMessage', 'Please enter a name for the API key'),
      });
      return;
    }

    setIsCreating(true);
    try {
      const result: CreateApiKeyResponse = await usersApi.createApiKey(newKeyName.trim());
      setCreatedKey({
        keyId: result.key_id,
        name: result.name,
        key: result.key,
        prefix: result.prefix,
        createdAt: result.created_at,
      });
      setNewKeyName('');
      await loadApiKeys();

      addNotification({
        type: 'success',
        title: t('profileSettings.apiKeys.createdTitle', 'API Key Created'),
        message: t(
          'profileSettings.apiKeys.createdMessage',
          'Your new API key has been created. Copy it now, it will not be shown again.'
        ),
      });
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: t('profileSettings.apiKeys.createFailedTitle', 'Creation Failed'),
        message: error.response?.data?.message || 'Failed to create API key',
      });
    } finally {
      setIsCreating(false);
    }
  };

  const handleCopyKey = (key: string) => {
    navigator.clipboard.writeText(key);
    addNotification({
      type: 'success',
      title: t('profileSettings.apiKeys.copiedTitle', 'Copied'),
      message: t('profileSettings.apiKeys.copiedMessage', 'API key copied to clipboard'),
    });
  };

  const handleDeleteKey = async (keyId: string) => {
    if (
      !confirm(
        t(
          'profileSettings.apiKeys.deleteConfirm',
          'Are you sure you want to delete this API key? This action cannot be undone.'
        )
      )
    ) {
      return;
    }

    setDeletingKeyId(keyId);
    try {
      await usersApi.deleteApiKey(keyId);
      await loadApiKeys();

      addNotification({
        type: 'success',
        title: t('profileSettings.apiKeys.deletedTitle', 'API Key Deleted'),
        message: t('profileSettings.apiKeys.deletedMessage', 'The API key has been deleted'),
      });
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: t('profileSettings.apiKeys.deleteFailedTitle', 'Deletion Failed'),
        message: error.response?.data?.message || 'Failed to delete API key',
      });
    } finally {
      setDeletingKeyId(null);
    }
  };

  const formatDateTime = (value?: string | null) => {
    if (!value) return t('profileSettings.apiKeys.neverUsed', 'Never used');
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString();
  };

  return (
    <GlassPanel className="p-6">
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Key className="w-5 h-5 text-emerald-400" />
            <div>
              <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
                {t('profileSettings.apiKeys.title', 'API Keys')}
              </h2>
              <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-1">
                {t('profileSettings.apiKeys.subtitle', 'Manage API keys for programmatic access')}
              </p>
            </div>
          </div>
          <button
            onClick={() => setShowNewKeyModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors"
          >
            <Plus className="w-4 h-4" />
            {t('profileSettings.apiKeys.createKey', 'Create Key')}
          </button>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-10 text-zinc-600 dark:text-zinc-400 gap-2">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span>{t('profileSettings.apiKeys.loading', 'Loading API keys...')}</span>
          </div>
        ) : apiKeys.length === 0 ? (
          <div className="text-center py-12">
            <Key className="w-12 h-12 text-zinc-500 dark:text-zinc-500 mx-auto mb-4" />
            <p className="text-zinc-700 dark:text-zinc-300">{t('profileSettings.apiKeys.empty', 'No API keys yet')}</p>
            <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">
              {t('profileSettings.apiKeys.emptyHint', 'Create your first API key to get started')}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {apiKeys.map((apiKey) => (
              <div
                key={apiKey.key_id}
                className="p-4 bg-zinc-50 dark:bg-white/5 rounded-lg border border-zinc-200 dark:border-white/10"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h3 className="text-zinc-900 dark:text-zinc-100 font-medium">{apiKey.name}</h3>
                    <code className="text-sm text-zinc-600 dark:text-zinc-400 font-mono mt-2 inline-block">
                      {apiKey.prefix}••••••••
                    </code>
                    <div className="flex gap-4 mt-2 text-xs text-zinc-500 dark:text-zinc-500">
                      <span>
                        {t('profileSettings.apiKeys.createdAt', 'Created')}: {formatDateTime(apiKey.created_at)}
                      </span>
                      <span>
                        {t('profileSettings.apiKeys.lastUsedAt', 'Last used')}: {formatDateTime(apiKey.last_used_at)}
                      </span>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleDeleteKey(apiKey.key_id)}
                      disabled={deletingKeyId === apiKey.key_id}
                      className="p-2 text-zinc-500 dark:text-zinc-400 hover:text-red-500 dark:hover:text-red-400 transition-colors disabled:opacity-50"
                      title={t('profileSettings.apiKeys.deleteKey', 'Delete key')}
                    >
                      {deletingKeyId === apiKey.key_id ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Trash2 className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Create Key Modal */}
        {showNewKeyModal && (
          <LayoutModal
            isOpen={showNewKeyModal}
            onClose={() => {
              setShowNewKeyModal(false);
              setNewKeyName('');
              setCreatedKey(null);
            }}
            closeOnBackdropClick={false}
            closeOnEscape={true}
          >
            <div className="w-full max-w-2xl my-auto modal-panel rounded-[24px] shadow-2xl max-h-[calc(100vh-var(--app-header-height,4rem)-3rem)] overflow-y-auto p-6">
              <h3 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100 mb-4">
                {t('profileSettings.apiKeys.createTitle', 'Create API Key')}
              </h3>

              {!createdKey ? (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                      {t('profileSettings.apiKeys.keyName', 'Key Name')}
                    </label>
                    <input
                      type="text"
                      value={newKeyName}
                      onChange={(e) => setNewKeyName(e.target.value)}
                      placeholder={t('profileSettings.apiKeys.keyNamePlaceholder', 'e.g., Production API')}
                      className="w-full px-4 py-2 bg-zinc-50 dark:bg-white/5 border border-zinc-300 dark:border-white/10 rounded-lg text-zinc-900 dark:text-white placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:border-emerald-500"
                    />
                  </div>
                  <div className="flex gap-3">
                    <button
                      onClick={handleCreateKey}
                      disabled={isCreating}
                      className="flex-1 px-4 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors disabled:opacity-50"
                    >
                      {isCreating
                        ? t('profileSettings.apiKeys.creating', 'Creating...')
                        : t('profileSettings.apiKeys.create', 'Create')}
                    </button>
                    <button
                      onClick={() => {
                        setShowNewKeyModal(false);
                        setNewKeyName('');
                        setCreatedKey(null);
                      }}
                      className="flex-1 px-4 py-2 bg-zinc-100 dark:bg-white/5 text-zinc-700 dark:text-zinc-300 rounded-lg hover:bg-zinc-200 dark:hover:bg-white/10 transition-colors"
                    >
                      {t('common.cancel', 'Cancel')}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="p-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 text-sm">
                    <div className="flex items-center gap-2 mb-2">
                      <ShieldCheck className="w-4 h-4" />
                      <span>{t('profileSettings.apiKeys.copyNowTitle', 'Copy this key now')}</span>
                    </div>
                    <p>{t('profileSettings.apiKeys.copyNowHint', 'For security reasons, this key will only be shown once.')}</p>
                  </div>

                  <div className="p-3 rounded-lg bg-zinc-100 dark:bg-zinc-900/60 border border-zinc-200 dark:border-white/10">
                    <code className="text-xs text-emerald-700 dark:text-emerald-300 break-all font-mono">{createdKey.key}</code>
                  </div>

                  <div className="flex gap-3">
                    <button
                      onClick={() => handleCopyKey(createdKey.key)}
                      className="flex-1 px-4 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors inline-flex items-center justify-center gap-2"
                    >
                      <Copy className="w-4 h-4" />
                      {t('profileSettings.apiKeys.copyKey', 'Copy Key')}
                    </button>
                    <button
                      onClick={() => {
                        setShowNewKeyModal(false);
                        setCreatedKey(null);
                        setNewKeyName('');
                      }}
                      className="flex-1 px-4 py-2 bg-zinc-100 dark:bg-white/5 text-zinc-700 dark:text-zinc-300 rounded-lg hover:bg-zinc-200 dark:hover:bg-white/10 transition-colors"
                    >
                      {t('common.done', 'Done')}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </LayoutModal>
        )}
      </div>
    </GlassPanel>
  );
};
