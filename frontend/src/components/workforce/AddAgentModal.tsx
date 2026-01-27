import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';

interface AddAgentModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAdd: (name: string, systemPrompt: string) => void;
}

export const AddAgentModal: React.FC<AddAgentModalProps> = ({ isOpen, onClose, onAdd }) => {
  const { t } = useTranslation();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [name, setName] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [nameError, setNameError] = useState('');

  if (!isOpen) return null;

  const handleClose = () => {
    setName('');
    setSystemPrompt('');
    setNameError('');
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Validate name
    if (!name.trim()) {
      setNameError('Agent name is required');
      return;
    }
    
    if (name.trim().length < 2) {
      setNameError('Agent name must be at least 2 characters');
      return;
    }
    
    setIsSubmitting(true);
    
    try {
      onAdd(name.trim(), systemPrompt.trim());
      toast.success(t('agent.success', 'Agent created successfully!'));
      handleClose();
    } catch (error: any) {
      console.error('Failed to create agent:', error);
      toast.error(t('agent.errors.failed', 'Failed to create agent. Please try again.'));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-in fade-in duration-200" style={{ marginLeft: 'var(--sidebar-width, 0px)' }}>
      <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto bg-white dark:bg-zinc-900 rounded-3xl shadow-2xl p-6 animate-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-zinc-800 dark:text-white">
            {t('agent.addAgent', 'Add New Agent')}
          </h2>
          <button
            onClick={handleClose}
            className="p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors"
            disabled={isSubmitting}
          >
            <X className="w-6 h-6 text-zinc-700 dark:text-zinc-300" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Agent Name */}
          <div>
            <label 
              htmlFor="agentName" 
              className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2"
            >
              {t('agent.agentName', 'Agent Name')} <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              id="agentName"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setNameError('');
              }}
              disabled={isSubmitting}
              className={`w-full px-4 py-3 bg-zinc-50 dark:bg-zinc-800 border ${
                nameError 
                  ? 'border-red-500 dark:border-red-400' 
                  : 'border-zinc-200 dark:border-zinc-700'
              } rounded-xl text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed`}
              placeholder={t('agent.agentNamePlaceholder', 'e.g., Data Analyst, Content Writer')}
              autoFocus
            />
            {nameError && (
              <p className="mt-1 text-sm text-red-500 dark:text-red-400">
                {nameError}
              </p>
            )}
          </div>

          {/* System Prompt */}
          <div>
            <label 
              htmlFor="systemPrompt" 
              className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2"
            >
              {t('agent.systemPrompt', 'System Prompt')} <span className="text-zinc-400 text-xs font-normal">(Optional)</span>
            </label>
            <textarea
              id="systemPrompt"
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              disabled={isSubmitting}
              rows={8}
              className="w-full px-4 py-3 bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed resize-none"
              placeholder={t('agent.systemPromptPlaceholder', 'Define the agent\'s role, behavior, and capabilities...')}
            />
            <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
              You can configure the model, temperature, and other settings after creating the agent.
            </p>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-3 pt-2">
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex-1 px-6 py-3 bg-emerald-500 hover:bg-emerald-600 text-white rounded-xl font-semibold transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  {t('agent.creatingAgent', 'Creating...')}
                </>
              ) : (
                t('agent.createAgent', 'Create Agent')
              )}
            </button>
            <button
              type="button"
              onClick={handleClose}
              disabled={isSubmitting}
              className="flex-1 px-6 py-3 bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 rounded-xl hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-all font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {t('agent.cancel', 'Cancel')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
