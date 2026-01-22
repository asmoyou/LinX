import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
import { X, Check } from 'lucide-react';
import { GlassPanel } from '@/components/GlassPanel';
import { SubmitButton } from '@/components/forms/SubmitButton';
import { createAgentSchema, type CreateAgentFormData } from '@/schemas/authSchemas';
import toast from 'react-hot-toast';

interface AddAgentModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAdd: (name: string, template: string) => void;
}

interface AgentTemplate {
  id: string;
  nameKey: string;
  descriptionKey: string;
  icon: string;
}

const templates: AgentTemplate[] = [
  { 
    id: 'data-analyst', 
    nameKey: 'agent.templates.dataAnalyst.name',
    descriptionKey: 'agent.templates.dataAnalyst.description',
    icon: '📊'
  },
  { 
    id: 'content-writer', 
    nameKey: 'agent.templates.contentWriter.name',
    descriptionKey: 'agent.templates.contentWriter.description',
    icon: '✍️'
  },
  { 
    id: 'code-assistant', 
    nameKey: 'agent.templates.codeAssistant.name',
    descriptionKey: 'agent.templates.codeAssistant.description',
    icon: '💻'
  },
  { 
    id: 'research-assistant', 
    nameKey: 'agent.templates.researchAssistant.name',
    descriptionKey: 'agent.templates.researchAssistant.description',
    icon: '🔍'
  },
];

export const AddAgentModal: React.FC<AddAgentModalProps> = ({ isOpen, onClose, onAdd }) => {
  const { t } = useTranslation();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<string>('');

  const {
    register,
    handleSubmit,
    formState: { errors, touchedFields },
    reset,
    setValue,
    trigger,
  } = useForm<CreateAgentFormData>({
    resolver: zodResolver(createAgentSchema),
    mode: 'onBlur',
  });

  if (!isOpen) return null;

  const handleClose = () => {
    reset();
    setSelectedTemplate('');
    onClose();
  };

  const handleTemplateSelect = (templateId: string) => {
    setSelectedTemplate(templateId);
    setValue('template', templateId);
    // Trigger validation for template field
    if (touchedFields.template) {
      trigger('template');
    }
  };

  const onSubmit = async (data: CreateAgentFormData) => {
    setIsSubmitting(true);
    
    try {
      // Simulate API call
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      onAdd(data.name, data.template);
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
      <GlassPanel className="w-full max-w-2xl max-h-[90vh] overflow-y-auto animate-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-zinc-800 dark:text-white">
            {t('agent.addAgent', 'Add New Agent')}
          </h2>
          <button
            onClick={handleClose}
            className="p-2 hover:bg-white/20 dark:hover:bg-zinc-800/20 rounded-lg transition-colors"
            disabled={isSubmitting}
          >
            <X className="w-6 h-6 text-zinc-700 dark:text-zinc-300" />
          </button>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
          {/* Agent Name */}
          <div>
            <label 
              htmlFor="agentName" 
              className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2"
            >
              {t('agent.agentName', 'Agent Name')}
            </label>
            <input
              type="text"
              id="agentName"
              {...register('name')}
              disabled={isSubmitting}
              className={`w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border ${
                errors.name 
                  ? 'border-red-500 dark:border-red-400' 
                  : 'border-zinc-300 dark:border-zinc-700'
              } rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed`}
              placeholder={t('agent.agentNamePlaceholder', 'e.g., Data Analyst #1')}
              autoFocus
            />
            {errors.name && (
              <p className="mt-1 text-sm text-red-500 dark:text-red-400">
                {t(`agent.errors.${errors.name.message?.replace(/\s+/g, '')}`, errors.name.message)}
              </p>
            )}
          </div>

          {/* Template Selection */}
          <div>
            <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-3">
              {t('agent.selectTemplate', 'Select Template')}
            </label>
            <input type="hidden" {...register('template')} />
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {templates.map((template) => (
                <button
                  key={template.id}
                  type="button"
                  onClick={() => handleTemplateSelect(template.id)}
                  disabled={isSubmitting}
                  className={`group relative p-5 rounded-xl border-2 transition-all text-left ${
                    selectedTemplate === template.id
                      ? 'border-emerald-500 bg-emerald-500/10 dark:bg-emerald-500/5 shadow-lg shadow-emerald-500/10'
                      : 'border-zinc-300 dark:border-zinc-700 hover:border-emerald-400 dark:hover:border-emerald-600 hover:bg-white/50 dark:hover:bg-zinc-800/50'
                  } disabled:opacity-50 disabled:cursor-not-allowed`}
                >
                  {/* Selection indicator */}
                  {selectedTemplate === template.id && (
                    <div className="absolute top-3 right-3 w-6 h-6 bg-emerald-500 rounded-full flex items-center justify-center">
                      <Check className="w-4 h-4 text-white" />
                    </div>
                  )}
                  
                  {/* Template icon */}
                  <div className="text-3xl mb-2">{template.icon}</div>
                  
                  {/* Template info */}
                  <h3 className="font-semibold text-zinc-800 dark:text-white mb-1">
                    {t(template.nameKey)}
                  </h3>
                  <p className="text-sm text-zinc-600 dark:text-zinc-400">
                    {t(template.descriptionKey)}
                  </p>
                </button>
              ))}
            </div>
            {errors.template && (
              <p className="mt-2 text-sm text-red-500 dark:text-red-400">
                {t('agent.errors.templateRequired', 'Please select a template')}
              </p>
            )}
          </div>

          {/* Description (Optional) */}
          <div>
            <label 
              htmlFor="description" 
              className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2"
            >
              {t('agent.description', 'Description (Optional)')}
            </label>
            <textarea
              id="description"
              {...register('description')}
              disabled={isSubmitting}
              rows={3}
              className={`w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border ${
                errors.description 
                  ? 'border-red-500 dark:border-red-400' 
                  : 'border-zinc-300 dark:border-zinc-700'
              } rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed resize-none`}
              placeholder={t('agent.descriptionPlaceholder', 'Add a description for this agent...')}
            />
            {errors.description && (
              <p className="mt-1 text-sm text-red-500 dark:text-red-400">
                {t('agent.errors.descriptionTooLong', 'Description must not exceed 200 characters')}
              </p>
            )}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-3 pt-2">
            <SubmitButton
              isLoading={isSubmitting}
              loadingText={t('agent.creatingAgent', 'Creating...')}
              text={t('agent.createAgent', 'Create Agent')}
              disabled={isSubmitting}
              variant="primary"
            />
            <button
              type="button"
              onClick={handleClose}
              disabled={isSubmitting}
              className="flex-1 px-4 py-3 bg-white/10 dark:bg-zinc-800/10 text-zinc-700 dark:text-zinc-300 rounded-lg hover:bg-white/20 dark:hover:bg-zinc-800/20 transition-all font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {t('agent.cancel', 'Cancel')}
            </button>
          </div>
        </form>
      </GlassPanel>
    </div>
  );
};
