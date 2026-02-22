import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
import { Send, Sparkles, AlertCircle } from 'lucide-react';
import { SubmitButton } from '@/components/forms/SubmitButton';
import { submitGoalSchema, type SubmitGoalFormData } from '@/schemas/authSchemas';
import toast from 'react-hot-toast';

interface GoalInputProps {
  onSubmit: (title: string, description: string) => void;
  isLoading: boolean;
}

export const GoalInput: React.FC<GoalInputProps> = ({ onSubmit, isLoading }) => {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(false);
  const [selectedPriority, setSelectedPriority] = useState<'low' | 'medium' | 'high'>('medium');

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
    watch,
  } = useForm<SubmitGoalFormData>({
    resolver: zodResolver(submitGoalSchema),
    mode: 'onBlur',
    defaultValues: {
      priority: 'medium',
    },
  });

  const titleValue = watch('title') || '';
  const descriptionValue = watch('description') || '';

  const handleFormSubmit = async (data: SubmitGoalFormData) => {
    try {
      onSubmit(data.title, data.description);
      reset();
      setIsExpanded(false);
      setSelectedPriority('medium');
    } catch (error: any) {
      console.error('Failed to submit goal:', error);
      toast.error(t('goal.errors.failed', 'Failed to submit goal. Please try again.'));
    }
  };

  const handleCancel = () => {
    reset();
    setIsExpanded(false);
    setSelectedPriority('medium');
  };

  const priorityOptions = [
    { value: 'low', label: t('goal.priorityLow', 'Low'), color: 'text-blue-500 bg-blue-500/10 border-blue-500/20' },
    { value: 'medium', label: t('goal.priorityMedium', 'Medium'), color: 'text-yellow-500 bg-yellow-500/10 border-yellow-500/20' },
    { value: 'high', label: t('goal.priorityHigh', 'High'), color: 'text-red-500 bg-red-500/10 border-red-500/20' },
  ] as const;

  return (
    <form onSubmit={handleSubmit(handleFormSubmit)} className="relative group">
      <div className={`glass-panel rounded-2xl transition-all duration-300 ${
        isExpanded ? 'p-6' : 'p-3'
      }`}>
        {/* Compact View */}
        {!isExpanded && (
          <div className="flex items-center gap-3">
            <div className="p-3">
              <Sparkles className="w-6 h-6 text-emerald-500" />
            </div>
            <input
              type="text"
              onClick={() => setIsExpanded(true)}
              placeholder={t('goal.goalTitlePlaceholder', 'e.g., Generate Q4 Market Strategy Report')}
              className="flex-1 bg-transparent border-none py-4 text-lg focus:ring-0 placeholder:text-zinc-400 font-medium text-zinc-800 dark:text-zinc-200 cursor-text"
              readOnly
            />
            <button
              type="button"
              onClick={() => setIsExpanded(true)}
              className="bg-emerald-500 hover:bg-emerald-600 text-white dark:text-black px-8 py-4 rounded-xl font-bold flex items-center gap-2 transition-all active:scale-95 shadow-lg shadow-emerald-500/10"
            >
              <Send className="w-5 h-5" />
              {t('goal.submitGoal', 'Submit Goal')}
            </button>
          </div>
        )}

        {/* Expanded Form */}
        {isExpanded && (
          <div className="space-y-5 animate-in fade-in slide-in-from-top-4 duration-300">
            {/* Header */}
            <div className="flex items-center gap-3 pb-4 border-b border-zinc-200 dark:border-zinc-800">
              <Sparkles className="w-6 h-6 text-emerald-500" />
              <h3 className="text-xl font-bold text-zinc-800 dark:text-zinc-200">
                {t('goal.submitGoal', 'Submit Goal')}
              </h3>
            </div>

            {/* Title Input */}
            <div>
              <label
                htmlFor="goalTitle"
                className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2"
              >
                {t('goal.goalTitle', 'Goal Title')}
              </label>
              <input
                type="text"
                id="goalTitle"
                {...register('title')}
                disabled={isLoading}
                className={`w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border ${
                  errors.title
                    ? 'border-red-500 dark:border-red-400'
                    : 'border-zinc-300 dark:border-zinc-700'
                } rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed`}
                placeholder={t('goal.goalTitlePlaceholder', 'e.g., Generate Q4 Market Strategy Report')}
                autoFocus
              />
              {errors.title && (
                <p className="mt-1 text-sm text-red-500 dark:text-red-400 flex items-center gap-1">
                  <AlertCircle className="w-4 h-4" />
                  {t(`goal.errors.${errors.title.message?.replace(/\s+/g, '')}`, errors.title.message)}
                </p>
              )}
              {titleValue && !errors.title && (
                <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                  {titleValue.length} / 100 {t('goal.characterCount', 'characters')}
                </p>
              )}
            </div>

            {/* Description Textarea */}
            <div>
              <label
                htmlFor="goalDescription"
                className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2"
              >
                {t('goal.goalDescription', 'Goal Description')}
              </label>
              <textarea
                id="goalDescription"
                {...register('description')}
                disabled={isLoading}
                rows={6}
                className={`w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border ${
                  errors.description
                    ? 'border-red-500 dark:border-red-400'
                    : 'border-zinc-300 dark:border-zinc-700'
                } rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed resize-none font-mono text-sm leading-relaxed`}
                placeholder={t('goal.goalDescriptionPlaceholder', 'Describe in detail what you want to achieve...')}
              />
              {errors.description && (
                <p className="mt-1 text-sm text-red-500 dark:text-red-400 flex items-center gap-1">
                  <AlertCircle className="w-4 h-4" />
                  {t(`goal.errors.${errors.description.message?.replace(/\s+/g, '')}`, errors.description.message)}
                </p>
              )}
              {descriptionValue && !errors.description && (
                <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                  {descriptionValue.length} / 2000 {t('goal.characterCount', 'characters')}
                </p>
              )}
            </div>

            {/* Priority Selection */}
            <div>
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-3">
                {t('goal.priority', 'Priority')}
              </label>
              <input type="hidden" {...register('priority')} value={selectedPriority} />
              <div className="flex gap-3">
                {priorityOptions.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => setSelectedPriority(option.value)}
                    disabled={isLoading}
                    className={`flex-1 px-4 py-3 rounded-lg border-2 font-medium transition-all ${
                      selectedPriority === option.value
                        ? option.color
                        : 'border-zinc-300 dark:border-zinc-700 text-zinc-600 dark:text-zinc-400 hover:border-zinc-400 dark:hover:border-zinc-600'
                    } disabled:opacity-50 disabled:cursor-not-allowed`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-3 pt-2">
              <SubmitButton
                isLoading={isLoading}
                loadingText={t('goal.submittingGoal', 'Submitting...')}
                text={t('goal.submitGoal', 'Submit Goal')}
                icon={Send}
                disabled={isLoading}
                variant="primary"
              />
              <button
                type="button"
                onClick={handleCancel}
                disabled={isLoading}
                className="flex-1 px-4 py-3 bg-white/10 dark:bg-zinc-800/10 text-zinc-700 dark:text-zinc-300 rounded-lg hover:bg-white/20 dark:hover:bg-zinc-800/20 transition-all font-medium disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {t('goal.cancel', 'Cancel')}
              </button>
            </div>
          </div>
        )}
      </div>
    </form>
  );
};
