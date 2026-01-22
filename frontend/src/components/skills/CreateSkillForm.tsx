import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
import { Zap, AlertCircle } from 'lucide-react';
import { SubmitButton } from '@/components/forms/SubmitButton';
import { createSkillSchema } from '@/schemas/authSchemas';
import toast from 'react-hot-toast';
import { z } from 'zod';

// Infer the type from the schema
type CreateSkillFormData = z.infer<typeof createSkillSchema>;

interface CreateSkillFormProps {
  onSubmit: (data: CreateSkillFormData) => Promise<void>;
  onCancel: () => void;
}

export const CreateSkillForm: React.FC<CreateSkillFormProps> = ({ onSubmit, onCancel }) => {
  const { t } = useTranslation();
  const [isSubmitting, setIsSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
    watch,
  } = useForm<CreateSkillFormData>({
    resolver: zodResolver(createSkillSchema),
    mode: 'onBlur',
    defaultValues: {
      difficulty: 'intermediate',
    },
  });

  const nameValue = watch('name') || '';
  const descriptionValue = watch('description') || '';
  const parametersValue = watch('parameters') || '';

  const handleFormSubmit = async (data: CreateSkillFormData) => {
    setIsSubmitting(true);
    try {
      await onSubmit(data);
      toast.success(t('skill.success', 'Skill created successfully!'));
    } catch (error: any) {
      console.error('Failed to create skill:', error);
      toast.error(t('skill.errors.failed', 'Failed to create skill. Please try again.'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const categoryOptions = [
    { value: 'data', label: t('skill.categoryData', 'Data Processing'), icon: '📊' },
    { value: 'content', label: t('skill.categoryContent', 'Content Creation'), icon: '✍️' },
    { value: 'code', label: t('skill.categoryCode', 'Code Development'), icon: '💻' },
    { value: 'research', label: t('skill.categoryResearch', 'Research Analysis'), icon: '🔍' },
    { value: 'other', label: t('skill.categoryOther', 'Other'), icon: '⚙️' },
  ] as const;

  const difficultyOptions = [
    { value: 'beginner', label: t('skill.difficultyBeginner', 'Beginner'), color: 'text-green-500 bg-green-500/10 border-green-500/20' },
    { value: 'intermediate', label: t('skill.difficultyIntermediate', 'Intermediate'), color: 'text-yellow-500 bg-yellow-500/10 border-yellow-500/20' },
    { value: 'advanced', label: t('skill.difficultyAdvanced', 'Advanced'), color: 'text-red-500 bg-red-500/10 border-red-500/20' },
  ] as const;

  return (
    <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-6">
      {/* Skill Name */}
      <div>
        <label
          htmlFor="skillName"
          className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2"
        >
          {t('skill.skillName', 'Skill Name')}
        </label>
        <input
          type="text"
          id="skillName"
          {...register('name')}
          disabled={isSubmitting}
          className={`w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border ${
            errors.name
              ? 'border-red-500 dark:border-red-400'
              : 'border-zinc-300 dark:border-zinc-700'
          } rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed`}
          placeholder={t('skill.skillNamePlaceholder', 'e.g., Data Visualization')}
          autoFocus
        />
        {errors.name && (
          <p className="mt-1 text-sm text-red-500 dark:text-red-400 flex items-center gap-1">
            <AlertCircle className="w-4 h-4" />
            {errors.name.message}
          </p>
        )}
        {nameValue && !errors.name && (
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            {nameValue.length} / 50
          </p>
        )}
      </div>

      {/* Description */}
      <div>
        <label
          htmlFor="skillDescription"
          className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2"
        >
          {t('skill.description', 'Description')}
        </label>
        <textarea
          id="skillDescription"
          {...register('description')}
          disabled={isSubmitting}
          rows={4}
          className={`w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border ${
            errors.description
              ? 'border-red-500 dark:border-red-400'
              : 'border-zinc-300 dark:border-zinc-700'
          } rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed resize-none`}
          placeholder={t('skill.descriptionPlaceholder', 'Describe what this skill does and how it\'s used...')}
        />
        {errors.description && (
          <p className="mt-1 text-sm text-red-500 dark:text-red-400 flex items-center gap-1">
            <AlertCircle className="w-4 h-4" />
            {errors.description.message}
          </p>
        )}
        {descriptionValue && !errors.description && (
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            {descriptionValue.length} / 500
          </p>
        )}
      </div>

      {/* Category */}
      <div>
        <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-3">
          {t('skill.category', 'Category')}
        </label>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {categoryOptions.map((option) => (
            <label key={option.value} className="cursor-pointer">
              <input
                type="radio"
                {...register('category')}
                value={option.value}
                disabled={isSubmitting}
                className="sr-only peer"
              />
              <div className="p-4 border-2 border-zinc-300 dark:border-zinc-700 rounded-lg text-center transition-all peer-checked:border-emerald-500 peer-checked:bg-emerald-500/10 hover:border-emerald-400 dark:hover:border-emerald-600">
                <div className="text-2xl mb-1">{option.icon}</div>
                <div className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                  {option.label}
                </div>
              </div>
            </label>
          ))}
        </div>
        {errors.category && (
          <p className="mt-2 text-sm text-red-500 dark:text-red-400 flex items-center gap-1">
            <AlertCircle className="w-4 h-4" />
            {t('skill.errors.categoryRequired', 'Please select a category')}
          </p>
        )}
      </div>

      {/* Difficulty */}
      <div>
        <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-3">
          {t('skill.difficulty', 'Difficulty')}
        </label>
        <div className="flex gap-3">
          {difficultyOptions.map((option) => (
            <label key={option.value} className="flex-1 cursor-pointer">
              <input
                type="radio"
                {...register('difficulty')}
                value={option.value}
                disabled={isSubmitting}
                className="sr-only peer"
              />
              <div className={`p-3 border-2 rounded-lg text-center font-medium transition-all peer-checked:${option.color} border-zinc-300 dark:border-zinc-700 peer-checked:border-transparent hover:border-zinc-400 dark:hover:border-zinc-600 text-zinc-700 dark:text-zinc-300`}>
                {option.label}
              </div>
            </label>
          ))}
        </div>
      </div>

      {/* Parameters */}
      <div>
        <label
          htmlFor="skillParameters"
          className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2"
        >
          {t('skill.parameters', 'Parameters (Optional)')}
        </label>
        <textarea
          id="skillParameters"
          {...register('parameters')}
          disabled={isSubmitting}
          rows={3}
          className="w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed resize-none font-mono text-sm"
          placeholder={t('skill.parametersPlaceholder', 'JSON format parameter configuration...')}
        />
        {parametersValue && (
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            JSON format expected
          </p>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3 pt-2">
        <SubmitButton
          isLoading={isSubmitting}
          loadingText={t('skill.creating', 'Creating...')}
          text={t('skill.createSkill', 'Create Skill')}
          icon={Zap}
          disabled={isSubmitting}
          variant="primary"
        />
        <button
          type="button"
          onClick={onCancel}
          disabled={isSubmitting}
          className="flex-1 px-4 py-3 bg-white/10 dark:bg-zinc-800/10 text-zinc-700 dark:text-zinc-300 rounded-lg hover:bg-white/20 dark:hover:bg-zinc-800/20 transition-all font-medium disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {t('skill.cancel', 'Cancel')}
        </button>
      </div>
    </form>
  );
};
