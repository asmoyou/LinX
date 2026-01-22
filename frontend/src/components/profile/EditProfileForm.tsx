import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
import { Save, AlertCircle } from 'lucide-react';
import { SubmitButton } from '@/components/forms/SubmitButton';
import { editProfileSchema, type EditProfileFormData } from '@/schemas/authSchemas';
import toast from 'react-hot-toast';

interface EditProfileFormProps {
  initialData?: Partial<EditProfileFormData>;
  onSubmit: (data: EditProfileFormData) => Promise<void>;
  onCancel: () => void;
}

export const EditProfileForm: React.FC<EditProfileFormProps> = ({
  initialData,
  onSubmit,
  onCancel,
}) => {
  const { t } = useTranslation();
  const [isSubmitting, setIsSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
    watch,
  } = useForm<EditProfileFormData>({
    resolver: zodResolver(editProfileSchema),
    mode: 'onBlur',
    defaultValues: initialData || {},
  });

  const usernameValue = watch('username') || '';
  const fullNameValue = watch('fullName') || '';
  const bioValue = watch('bio') || '';

  const handleFormSubmit = async (data: EditProfileFormData) => {
    setIsSubmitting(true);
    try {
      await onSubmit(data);
      toast.success(t('profile.success', 'Profile updated successfully!'));
    } catch (error: any) {
      console.error('Failed to update profile:', error);
      toast.error(t('profile.errors.failed', 'Failed to update profile. Please try again.'));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-6">
      {/* Username */}
      <div>
        <label
          htmlFor="username"
          className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2"
        >
          {t('profile.username', 'Username')}
        </label>
        <input
          type="text"
          id="username"
          {...register('username')}
          disabled={isSubmitting}
          className={`w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border ${
            errors.username
              ? 'border-red-500 dark:border-red-400'
              : 'border-zinc-300 dark:border-zinc-700'
          } rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed`}
          placeholder={t('profile.usernamePlaceholder', 'Your username')}
          autoFocus
        />
        {errors.username && (
          <p className="mt-1 text-sm text-red-500 dark:text-red-400 flex items-center gap-1">
            <AlertCircle className="w-4 h-4" />
            {errors.username.message}
          </p>
        )}
        {usernameValue && !errors.username && (
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            {usernameValue.length} / 30
          </p>
        )}
      </div>

      {/* Email */}
      <div>
        <label
          htmlFor="email"
          className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2"
        >
          {t('profile.email', 'Email')}
        </label>
        <input
          type="email"
          id="email"
          {...register('email')}
          disabled={isSubmitting}
          className={`w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border ${
            errors.email
              ? 'border-red-500 dark:border-red-400'
              : 'border-zinc-300 dark:border-zinc-700'
          } rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed`}
          placeholder={t('profile.emailPlaceholder', 'Your email address')}
        />
        {errors.email && (
          <p className="mt-1 text-sm text-red-500 dark:text-red-400 flex items-center gap-1">
            <AlertCircle className="w-4 h-4" />
            {errors.email.message}
          </p>
        )}
      </div>

      {/* Full Name */}
      <div>
        <label
          htmlFor="fullName"
          className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2"
        >
          {t('profile.fullName', 'Full Name (Optional)')}
        </label>
        <input
          type="text"
          id="fullName"
          {...register('fullName')}
          disabled={isSubmitting}
          className={`w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border ${
            errors.fullName
              ? 'border-red-500 dark:border-red-400'
              : 'border-zinc-300 dark:border-zinc-700'
          } rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed`}
          placeholder={t('profile.fullNamePlaceholder', 'Your full name')}
        />
        {errors.fullName && (
          <p className="mt-1 text-sm text-red-500 dark:text-red-400">{errors.fullName.message}</p>
        )}
        {fullNameValue && !errors.fullName && (
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            {fullNameValue.length} / 50
          </p>
        )}
      </div>

      {/* Bio */}
      <div>
        <label
          htmlFor="bio"
          className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2"
        >
          {t('profile.bio', 'Bio (Optional)')}
        </label>
        <textarea
          id="bio"
          {...register('bio')}
          disabled={isSubmitting}
          rows={4}
          className={`w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border ${
            errors.bio
              ? 'border-red-500 dark:border-red-400'
              : 'border-zinc-300 dark:border-zinc-700'
          } rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed resize-none`}
          placeholder={t('profile.bioPlaceholder', 'Tell us about yourself...')}
        />
        {errors.bio && (
          <p className="mt-1 text-sm text-red-500 dark:text-red-400">{errors.bio.message}</p>
        )}
        {bioValue && !errors.bio && (
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            {bioValue.length} / 200
          </p>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3 pt-2">
        <SubmitButton
          isLoading={isSubmitting}
          loadingText={t('profile.saving', 'Saving...')}
          text={t('profile.editProfile', 'Save Changes')}
          icon={Save}
          disabled={isSubmitting}
          variant="primary"
        />
        <button
          type="button"
          onClick={onCancel}
          disabled={isSubmitting}
          className="flex-1 px-4 py-3 bg-white/10 dark:bg-zinc-800/10 text-zinc-700 dark:text-zinc-300 rounded-lg hover:bg-white/20 dark:hover:bg-zinc-800/20 transition-all font-medium disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {t('profile.cancel', 'Cancel')}
        </button>
      </div>
    </form>
  );
};
