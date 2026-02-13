import React, { useState, useRef } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
import { Upload, File, X, AlertCircle } from 'lucide-react';
import { SubmitButton } from '@/components/forms/SubmitButton';
import { uploadDocumentSchema, type UploadDocumentFormData } from '@/schemas/authSchemas';
import { DepartmentSelect } from '@/components/departments/DepartmentSelect';
import toast from 'react-hot-toast';

interface UploadDocumentFormProps {
  onSubmit: (data: UploadDocumentFormData & { departmentId?: string }, file: File) => Promise<void>;
  onCancel: () => void;
  collectionId?: string;
}

const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB
const SUPPORTED_FORMATS = [
  '.pdf', '.doc', '.docx', '.txt', '.md',
  '.jpg', '.jpeg', '.png', '.gif',
  '.mp3', '.wav', '.m4a', '.flac',
  '.mp4', '.avi', '.mov', '.mkv',
  '.zip'
];

export const UploadDocumentForm: React.FC<UploadDocumentFormProps> = ({ onSubmit, onCancel, collectionId }) => {
  const { t } = useTranslation();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [departmentId, setDepartmentId] = useState<string | undefined>();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const {
    register,
    handleSubmit,
    formState: { errors },
    watch,
    setValue,
    getValues,
  } = useForm<UploadDocumentFormData>({
    resolver: zodResolver(uploadDocumentSchema),
    mode: 'onBlur',
    defaultValues: {
      visibility: 'private',
    },
  });

  const titleValue = watch('title') || '';
  const descriptionValue = watch('description') || '';

  const handleFileSelect = (file: File) => {
    // Validate file size
    if (file.size > MAX_FILE_SIZE) {
      toast.error(t('document.errors.fileTooBig', 'File size exceeds limit'));
      return;
    }

    // Validate file format
    const fileExt = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!SUPPORTED_FORMATS.includes(fileExt)) {
      toast.error(t('document.errors.unsupportedFormat', 'Unsupported file format'));
      return;
    }

    setSelectedFile(file);

    // Auto-fill title from filename (without extension) if title is empty
    const currentTitle = getValues('title');
    if (!currentTitle) {
      const nameWithoutExt = file.name.replace(/\.[^/.]+$/, '');
      setValue('title', nameWithoutExt);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFileSelect(files[0]);
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleFileSelect(files[0]);
    }
  };

  const handleFormSubmit = async (data: UploadDocumentFormData) => {
    if (!selectedFile) {
      toast.error(t('document.errors.noFile', 'Please select a file to upload'));
      return;
    }

    setIsSubmitting(true);
    try {
      await onSubmit({ ...data, departmentId }, selectedFile);
      toast.success(t('document.success', 'Document uploaded successfully!'));
    } catch (error: any) {
      console.error('Failed to upload document:', error);
      toast.error(t('document.errors.failed', 'Failed to upload document. Please try again.'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const visibilityOptions = [
    { value: 'private', label: t('document.visibilityPrivate', 'Private'), icon: '🔒' },
    { value: 'team', label: t('document.visibilityTeam', 'Team'), icon: '👥' },
    { value: 'public', label: t('document.visibilityPublic', 'Public'), icon: '🌐' },
  ] as const;

  return (
    <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-6">
      {/* File Upload Area */}
      <div>
        <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-3">
          {t('document.uploadDocument', 'Upload Document')}
        </label>
        
        {!selectedFile ? (
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`relative border-2 border-dashed rounded-xl p-8 text-center transition-all ${
              isDragging
                ? 'border-emerald-500 bg-emerald-500/5'
                : 'border-zinc-300 dark:border-zinc-700 hover:border-emerald-400 dark:hover:border-emerald-600'
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              onChange={handleFileInputChange}
              accept={SUPPORTED_FORMATS.join(',')}
              className="hidden"
            />
            
            <Upload className="w-12 h-12 mx-auto mb-4 text-zinc-400" />
            
            <p className="text-lg font-medium text-zinc-700 dark:text-zinc-300 mb-2">
              {t('document.dragDrop', 'Drag and drop files here')}
            </p>
            
            <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-4">
              {t('document.or', 'or')}
            </p>
            
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="px-6 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg font-medium transition-all"
            >
              {t('document.browse', 'Browse Files')}
            </button>
            
            <div className="mt-6 text-xs text-zinc-500 dark:text-zinc-400 space-y-1">
              <p>
                {t('document.supportedFormats', 'Supported Formats')}: PDF, DOC, DOCX, TXT, MD, Images, Audio, Video, ZIP
              </p>
              <p>
                {t('document.maxSize', 'Max File Size')}: 50MB
              </p>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-4 p-4 bg-emerald-500/5 border border-emerald-500/20 rounded-xl">
            <File className="w-10 h-10 text-emerald-500 flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="font-medium text-zinc-800 dark:text-zinc-200 truncate">
                {selectedFile.name}
              </p>
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
              </p>
            </div>
            <button
              type="button"
              onClick={() => setSelectedFile(null)}
              className="p-2 hover:bg-red-500/10 rounded-lg transition-colors"
            >
              <X className="w-5 h-5 text-red-500" />
            </button>
          </div>
        )}
      </div>

      {/* ZIP Info Note */}
      {selectedFile && selectedFile.name.toLowerCase().endsWith('.zip') && (
        <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-sm text-amber-700 dark:text-amber-400">
          ZIP files will be automatically extracted. Each file inside will be processed independently.
        </div>
      )}

      {/* Collection Context */}
      {collectionId && (
        <div className="p-3 bg-blue-500/10 border border-blue-500/30 rounded-lg text-sm text-blue-700 dark:text-blue-400">
          Uploading into current collection.
        </div>
      )}

      {/* Title */}
      <div>
        <label htmlFor="docTitle" className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
          {t('document.documentTitle', 'Document Title')}
        </label>
        <input
          type="text"
          id="docTitle"
          {...register('title')}
          disabled={isSubmitting}
          className={`w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border ${
            errors.title ? 'border-red-500 dark:border-red-400' : 'border-zinc-300 dark:border-zinc-700'
          } rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed`}
          placeholder={t('document.documentTitlePlaceholder', 'e.g., Q4 Sales Data Analysis')}
        />
        {errors.title && (
          <p className="mt-1 text-sm text-red-500 dark:text-red-400 flex items-center gap-1">
            <AlertCircle className="w-4 h-4" />
            {errors.title.message}
          </p>
        )}
        {titleValue && !errors.title && (
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            {titleValue.length} / 100
          </p>
        )}
      </div>

      {/* Description */}
      <div>
        <label htmlFor="docDescription" className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
          {t('document.description', 'Description (Optional)')}
        </label>
        <textarea
          id="docDescription"
          {...register('description')}
          disabled={isSubmitting}
          rows={3}
          className={`w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border ${
            errors.description ? 'border-red-500 dark:border-red-400' : 'border-zinc-300 dark:border-zinc-700'
          } rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed resize-none`}
          placeholder={t('document.descriptionPlaceholder', 'Add a description for this document...')}
        />
        {errors.description && (
          <p className="mt-1 text-sm text-red-500 dark:text-red-400">{errors.description.message}</p>
        )}
        {descriptionValue && !errors.description && (
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            {descriptionValue.length} / 500
          </p>
        )}
      </div>

      {/* Tags */}
      <div>
        <label htmlFor="docTags" className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
          {t('document.tags', 'Tags (Optional)')}
        </label>
        <input
          type="text"
          id="docTags"
          {...register('tags')}
          disabled={isSubmitting}
          className="w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border border-zinc-300 dark:border-zinc-700 rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          placeholder={t('document.tagsPlaceholder', 'Comma separated, e.g., report, data, Q4')}
        />
      </div>

      {/* Department */}
      <div>
        <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
          {t('departments.label', 'Department')} <span className="text-zinc-400 text-xs font-normal">({t('common.optional', 'Optional')})</span>
        </label>
        <DepartmentSelect
          value={departmentId}
          onChange={setDepartmentId}
          disabled={isSubmitting}
        />
      </div>

      {/* Visibility */}
      <div>
        <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-3">
          {t('document.visibility', 'Visibility')}
        </label>
        <div className="flex gap-3">
          {visibilityOptions.map((option) => (
            <label
              key={option.value}
              className="flex-1 cursor-pointer"
            >
              <input
                type="radio"
                {...register('visibility')}
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
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3 pt-2">
        <SubmitButton
          isLoading={isSubmitting}
          loadingText={t('document.uploading', 'Uploading...')}
          text={t('document.uploadDocument', 'Upload Document')}
          icon={Upload}
          disabled={isSubmitting || !selectedFile}
          variant="primary"
        />
        <button
          type="button"
          onClick={onCancel}
          disabled={isSubmitting}
          className="flex-1 px-4 py-3 bg-white/10 dark:bg-zinc-800/10 text-zinc-700 dark:text-zinc-300 rounded-lg hover:bg-white/20 dark:hover:bg-zinc-800/20 transition-all font-medium disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {t('document.cancel', 'Cancel')}
        </button>
      </div>
    </form>
  );
};
