import { useState } from 'react';
import { Key, Plus, Copy, Trash2, Eye, EyeOff } from 'lucide-react';
import { GlassPanel } from '../GlassPanel';
import { useNotificationStore } from '../../stores/notificationStore';

interface APIKey {
  id: string;
  name: string;
  key: string;
  createdAt: string;
  lastUsed: string | null;
}

export const APIKeysSection = () => {
  const { addNotification } = useNotificationStore();
  const [apiKeys, setApiKeys] = useState<APIKey[]>([
    {
      id: '1',
      name: 'Production API',
      key: 'sk_live_1234567890abcdef',
      createdAt: '2024-01-15',
      lastUsed: '2024-01-20',
    },
  ]);
  const [showNewKeyModal, setShowNewKeyModal] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [visibleKeys, setVisibleKeys] = useState<Set<string>>(new Set());

  const handleCreateKey = async () => {
    if (!newKeyName.trim()) {
      addNotification({
        type: 'error',
        title: 'Invalid Name',
        message: 'Please enter a name for the API key',
      });
      return;
    }

    try {
      // TODO: Implement API call
      const newKey: APIKey = {
        id: Date.now().toString(),
        name: newKeyName,
        key: `sk_live_${Math.random().toString(36).substring(2, 15)}`,
        createdAt: new Date().toISOString().split('T')[0],
        lastUsed: null,
      };
      
      setApiKeys([...apiKeys, newKey]);
      setNewKeyName('');
      setShowNewKeyModal(false);
      
      addNotification({
        type: 'success',
        title: 'API Key Created',
        message: 'Your new API key has been created. Make sure to copy it now!',
      });
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: 'Creation Failed',
        message: error.response?.data?.message || 'Failed to create API key',
      });
    }
  };

  const handleCopyKey = (key: string) => {
    navigator.clipboard.writeText(key);
    addNotification({
      type: 'success',
      title: 'Copied',
      message: 'API key copied to clipboard',
    });
  };

  const handleDeleteKey = async (id: string) => {
    if (!confirm('Are you sure you want to delete this API key? This action cannot be undone.')) {
      return;
    }

    try {
      // TODO: Implement API call
      setApiKeys(apiKeys.filter(k => k.id !== id));
      
      addNotification({
        type: 'success',
        title: 'API Key Deleted',
        message: 'The API key has been deleted',
      });
    } catch (error: any) {
      addNotification({
        type: 'error',
        title: 'Deletion Failed',
        message: error.response?.data?.message || 'Failed to delete API key',
      });
    }
  };

  const toggleKeyVisibility = (id: string) => {
    setVisibleKeys(prev => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  };

  const maskKey = (key: string) => {
    return key.substring(0, 8) + '••••••••••••••••';
  };

  return (
    <GlassPanel className="p-6">
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Key className="w-5 h-5 text-emerald-400" />
            <div>
              <h2 className="text-xl font-semibold text-white">API Keys</h2>
              <p className="text-sm text-gray-400 mt-1">
                Manage API keys for programmatic access
              </p>
            </div>
          </div>
          <button
            onClick={() => setShowNewKeyModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors"
          >
            <Plus className="w-4 h-4" />
            Create Key
          </button>
        </div>

        {apiKeys.length === 0 ? (
          <div className="text-center py-12">
            <Key className="w-12 h-12 text-gray-600 mx-auto mb-4" />
            <p className="text-gray-400">No API keys yet</p>
            <p className="text-sm text-gray-500 mt-1">Create your first API key to get started</p>
          </div>
        ) : (
          <div className="space-y-3">
            {apiKeys.map((apiKey) => (
              <div
                key={apiKey.id}
                className="p-4 bg-white/5 rounded-lg border border-white/10"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h3 className="text-white font-medium">{apiKey.name}</h3>
                    <div className="flex items-center gap-2 mt-2">
                      <code className="text-sm text-gray-400 font-mono">
                        {visibleKeys.has(apiKey.id) ? apiKey.key : maskKey(apiKey.key)}
                      </code>
                      <button
                        onClick={() => toggleKeyVisibility(apiKey.id)}
                        className="p-1 text-gray-400 hover:text-white transition-colors"
                      >
                        {visibleKeys.has(apiKey.id) ? (
                          <EyeOff className="w-4 h-4" />
                        ) : (
                          <Eye className="w-4 h-4" />
                        )}
                      </button>
                    </div>
                    <div className="flex gap-4 mt-2 text-xs text-gray-500">
                      <span>Created: {apiKey.createdAt}</span>
                      {apiKey.lastUsed && <span>Last used: {apiKey.lastUsed}</span>}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleCopyKey(apiKey.key)}
                      className="p-2 text-gray-400 hover:text-emerald-400 transition-colors"
                      title="Copy key"
                    >
                      <Copy className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleDeleteKey(apiKey.id)}
                      className="p-2 text-gray-400 hover:text-red-400 transition-colors"
                      title="Delete key"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Create Key Modal */}
        {showNewKeyModal && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" style={{ marginLeft: 'var(--sidebar-width, 0px)' }}>
            <div className="bg-gray-900 border border-white/10 rounded-lg p-6 max-w-md w-full mx-4">
              <h3 className="text-xl font-semibold text-white mb-4">Create API Key</h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Key Name
                  </label>
                  <input
                    type="text"
                    value={newKeyName}
                    onChange={(e) => setNewKeyName(e.target.value)}
                    placeholder="e.g., Production API"
                    className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500"
                  />
                </div>
                <div className="flex gap-3">
                  <button
                    onClick={handleCreateKey}
                    className="flex-1 px-4 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors"
                  >
                    Create
                  </button>
                  <button
                    onClick={() => {
                      setShowNewKeyModal(false);
                      setNewKeyName('');
                    }}
                    className="flex-1 px-4 py-2 bg-white/5 text-gray-300 rounded-lg hover:bg-white/10 transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </GlassPanel>
  );
};
