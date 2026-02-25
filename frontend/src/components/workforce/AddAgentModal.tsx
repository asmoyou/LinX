import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { DepartmentSelect } from '@/components/departments/DepartmentSelect';
import { LayoutModal } from '@/components/LayoutModal';

interface AddAgentModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAdd: (name: string, systemPrompt: string, departmentId?: string) => void;
}

export const AddAgentModal: React.FC<AddAgentModalProps> = ({ isOpen, onClose, onAdd }) => {
  const { t } = useTranslation();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [name, setName] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [departmentId, setDepartmentId] = useState<string | undefined>();
  const [nameError, setNameError] = useState('');

  if (!isOpen) return null;

  const handleClose = () => {
    setName('');
    setSystemPrompt('');
    setDepartmentId(undefined);
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
      onAdd(name.trim(), systemPrompt.trim(), departmentId);
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
    <LayoutModal
      isOpen={isOpen}
      onClose={handleClose}
      closeOnBackdropClick={false}
      closeOnEscape={true}
      title={t('agent.addAgent', 'Add New Agent')}
      size="2xl"
      footer={
        <>
          <button
            type="button"
            onClick={handleClose}
            disabled={isSubmitting}
            className="flex-1 sm:flex-none px-6 py-3 bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 rounded-xl hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-all font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {t('agent.cancel', 'Cancel')}
          </button>
          <button
            form="add-agent-form"
            type="submit"
            disabled={isSubmitting}
            className="flex-1 sm:flex-none px-6 py-3 bg-emerald-500 hover:bg-emerald-600 text-white rounded-xl font-semibold transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
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
        </>
      }
    >
      <form id="add-agent-form" onSubmit={handleSubmit} className="space-y-6">
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

        {/* Department */}
        <div>
          <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
            {t('departments.label', 'Department')} <span className="text-zinc-400 text-xs font-normal">({t('common.optional', 'Optional')})</span>
          </label>
          <DepartmentSelect
            value={departmentId}
            onChange={setDepartmentId}
            disabled={isSubmitting}
          />
        </div>
      </form>
    </LayoutModal>
  );
};
