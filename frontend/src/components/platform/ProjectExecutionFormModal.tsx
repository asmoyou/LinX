import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Loader2, Play, Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { LayoutModal } from '@/components/LayoutModal';

const inputClassName =
  'w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100';

interface ProjectCreateModalProps {
  isOpen: boolean;
  isSubmitting?: boolean;
  onClose: () => void;
  onSubmit: (payload: { name: string; description?: string }) => Promise<void>;
}

export const ProjectCreateModal = ({
  isOpen,
  isSubmitting = false,
  onClose,
  onSubmit,
}: ProjectCreateModalProps) => {
  const { t } = useTranslation();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setName('');
    setDescription('');
    setError(null);
  }, [isOpen]);

  const disabled = isSubmitting || !name.trim();

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      setError(t('projectExecution.modals.projectNameRequired', 'Please enter a project name'));
      return;
    }
    setError(null);
    await onSubmit({ name: name.trim(), description: description.trim() || undefined });
  };

  return (
    <LayoutModal
      isOpen={isOpen}
      onClose={onClose}
      closeOnBackdropClick={!isSubmitting}
      closeOnEscape={!isSubmitting}
      title={t('projectExecution.modals.projectCreateTitle', 'Create Project')}
      description={t('projectExecution.modals.projectCreateDescription', 'Create a business container for a new project space. Tasks, runs, and deliverables will belong to this project.')}
      size="xl"
      footer={
        <div className="flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="rounded-full px-4 py-2 text-sm font-semibold text-zinc-600 transition hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800 disabled:opacity-50"
          >
            {t('projectExecution.shared.cancel', 'Cancel')}
          </button>
          <button
            form="project-create-form"
            type="submit"
            disabled={disabled}
            className="inline-flex items-center gap-2 rounded-full bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            {t('projectExecution.shared.createProject', 'Create Project')}
          </button>
        </div>
      }
    >
      <form id="project-create-form" onSubmit={handleSubmit} className="space-y-5">
        <label className="space-y-2 block">
          <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">{t('projectExecution.modals.projectName', 'Project Name')}</span>
          <input
            autoFocus
            value={name}
            onChange={(event) => setName(event.target.value)}
            className={inputClassName}
            placeholder={t('projectExecution.modals.projectNamePlaceholder', 'Example: Workspace Rollout')}
          />
        </label>

        <label className="space-y-2 block">
          <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">{t('projectExecution.modals.projectDescription', 'Project Description')}</span>
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={5}
            className={`${inputClassName} resize-none`}
            placeholder={t('projectExecution.modals.projectDescriptionPlaceholder', 'Describe goals, scope, and context for this project.')}
          />
        </label>

        {error ? <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p> : null}
      </form>
    </LayoutModal>
  );
};

interface ProjectTaskCreateModalProps {
  isOpen: boolean;
  projectTitle?: string | null;
  isSubmitting?: boolean;
  onClose: () => void;
  onSubmit: (payload: { title: string; description?: string; autoStart?: boolean }) => Promise<void>;
}

export const ProjectTaskCreateModal = ({
  isOpen,
  projectTitle,
  isSubmitting = false,
  onClose,
  onSubmit,
}: ProjectTaskCreateModalProps) => {
  const { t } = useTranslation();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [autoStart, setAutoStart] = useState(true);

  useEffect(() => {
    if (!isOpen) return;
    setTitle('');
    setDescription('');
    setError(null);
    setAutoStart(true);
  }, [isOpen]);

  const disabled = isSubmitting || !title.trim();

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!title.trim()) {
      setError(t('projectExecution.modals.taskTitleRequired', 'Please enter a task title'));
      return;
    }
    setError(null);
    await onSubmit({ title: title.trim(), description: description.trim() || undefined, autoStart });
  };

  return (
    <LayoutModal
      isOpen={isOpen}
      onClose={onClose}
      closeOnBackdropClick={!isSubmitting}
      closeOnEscape={!isSubmitting}
      title={t('projectExecution.modals.taskCreateTitle', 'Create Task')}
      description={projectTitle ? t('projectExecution.modals.taskCreateDescriptionWithProject', { projectTitle, defaultValue: `Project: ${projectTitle}` }) : t('projectExecution.modals.taskCreateDescription', 'Create a new project task.')}
      size="xl"
      footer={
        <div className="flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="rounded-full px-4 py-2 text-sm font-semibold text-zinc-600 transition hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800 disabled:opacity-50"
          >
            {t('projectExecution.shared.cancel', 'Cancel')}
          </button>
          <button
            form="project-task-create-form"
            type="submit"
            disabled={disabled}
            className="inline-flex items-center gap-2 rounded-full bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            {autoStart ? t('projectExecution.modals.taskCreateAndStart', 'Create and start run') : t('projectExecution.modals.taskCreateOnly', 'Create task only')}
          </button>
        </div>
      }
    >
      <form id="project-task-create-form" onSubmit={handleSubmit} className="space-y-5">
        <label className="space-y-2 block">
          <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">{t('projectExecution.modals.taskTitle', 'Task Title')}</span>
          <input
            autoFocus
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            className={inputClassName}
            placeholder={t('projectExecution.modals.taskTitlePlaceholder', 'Example: Run staging bake and smoke suite')}
          />
        </label>

        <label className="space-y-2 block">
          <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">{t('projectExecution.modals.taskDescription', 'Task Description')}</span>
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={6}
            className={`${inputClassName} resize-none`}
            placeholder={t('projectExecution.modals.taskDescriptionPlaceholder', 'Describe goals, acceptance criteria, constraints, and context.')}
          />
        </label>

        <label className="flex items-center gap-3 rounded-2xl border border-zinc-200 bg-zinc-50/70 px-4 py-3 text-sm text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900/60 dark:text-zinc-200">
          <input
            type="checkbox"
            checked={autoStart}
            onChange={(event) => setAutoStart(event.target.checked)}
            className="h-4 w-4 accent-indigo-500"
          />
          <span>{t('projectExecution.modals.autoStartRun', 'Start run automatically after create')}</span>
        </label>

        {error ? <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p> : null}
      </form>
    </LayoutModal>
  );
};

interface LaunchRunModalProps {
  isOpen: boolean;
  isSubmitting?: boolean;
  taskTitle: string;
  taskDescription?: string | null;
  onClose: () => void;
  onSubmit: () => Promise<void>;
}

export const LaunchRunModal = ({
  isOpen,
  isSubmitting = false,
  taskTitle,
  taskDescription,
  onClose,
  onSubmit,
}: LaunchRunModalProps) => {
  const { t } = useTranslation();
  const helperText = useMemo(
    () =>
      taskDescription?.trim()
        ? taskDescription.trim()
        : t('projectExecution.modals.launchRunHelperFallback', 'A plan, run, and first execution step will be created automatically for this task.'),
    [taskDescription],
  );

  return (
    <LayoutModal
      isOpen={isOpen}
      onClose={onClose}
      closeOnBackdropClick={!isSubmitting}
      closeOnEscape={!isSubmitting}
      title={t('projectExecution.modals.launchRunTitle', 'Start Run')}
      description={t('projectExecution.modals.launchRunDescription', 'Confirm to generate a plan and start execution for the current task.')}
      size="lg"
      footer={
        <div className="flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="rounded-full px-4 py-2 text-sm font-semibold text-zinc-600 transition hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800 disabled:opacity-50"
          >
            {t('projectExecution.shared.cancel', 'Cancel')}
          </button>
          <button
            type="button"
            onClick={() => void onSubmit()}
            disabled={isSubmitting}
            className="inline-flex items-center gap-2 rounded-full bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {t('projectExecution.modals.launchRunAction', 'Generate Plan and Start')}
          </button>
        </div>
      }
    >
      <div className="space-y-4">
        <div className="rounded-2xl border border-zinc-200/70 bg-zinc-50/70 p-4 dark:border-zinc-800 dark:bg-zinc-900/60">
          <p className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">{t('projectExecution.modals.taskTitle', 'Task Title')}</p>
          <p className="mt-2 text-base text-zinc-950 dark:text-zinc-50">{taskTitle}</p>
        </div>
        <div className="rounded-2xl border border-zinc-200/70 bg-zinc-50/70 p-4 dark:border-zinc-800 dark:bg-zinc-900/60">
          <p className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">{t('projectExecution.shared.run', 'Run')} {t('projectExecution.modals.taskDescription', 'Description')}</p>
          <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-400">{helperText}</p>
        </div>
      </div>
    </LayoutModal>
  );
};
