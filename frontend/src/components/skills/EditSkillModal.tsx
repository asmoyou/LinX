import { X } from 'lucide-react';
import { useState, useEffect } from 'react';
import CodeEditor from './CodeEditor';
import type { Skill } from '@/api/skills';
import { useTranslation } from 'react-i18next';
import { LayoutModal } from '@/components/LayoutModal';

interface EditSkillModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (skillId: string, data: any) => Promise<void>;
  skill: Skill & { code?: string };
}

export default function EditSkillModal({ isOpen, onClose, onSubmit, skill }: EditSkillModalProps) {
  const { t } = useTranslation();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    code: '',
    dependencies: [] as string[],
  });

  useEffect(() => {
    if (skill) {
      setFormData({
        name: skill.name,
        description: skill.description,
        code: skill.code || '',
        dependencies: skill.dependencies || [],
      });
    }
  }, [skill]);

  if (!isOpen) return null;

  const handleClose = () => {
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      // Only send fields that can be updated (exclude name)
      const updateData = {
        description: formData.description,
        code: formData.code,
        dependencies: formData.dependencies,
      };
      await onSubmit(skill.skill_id, updateData);
      handleClose();
    } catch (error) {
      console.error('Failed to update skill:', error);
      alert(t('skills.updateFailed'));
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
      containerClassName="animate-in zoom-in-95 duration-200"
    >
      <div className="w-full max-w-4xl max-h-[calc(100vh-var(--app-header-height,4rem)-3rem)] overflow-y-auto modal-panel rounded-[24px] shadow-2xl p-6 animate-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-zinc-800 dark:text-white">{t('skills.editSkill')}</h2>
          <button 
            onClick={handleClose} 
            className="p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors"
            disabled={isSubmitting}
          >
            <X className="w-6 h-6 text-zinc-700 dark:text-zinc-300" />
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="space-y-5">
            {/* Basic Info */}
            <div>
              <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                {t('skills.skillName')} <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="w-full px-4 py-3 rounded-xl glass text-zinc-800 dark:text-white placeholder:text-zinc-500 dark:placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 transition-all"
                placeholder="e.g., my_custom_skill"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                {t('skills.description')} <span className="text-red-500">*</span>
              </label>
              <textarea
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="w-full px-4 py-3 rounded-xl glass text-zinc-800 dark:text-white placeholder:text-zinc-500 dark:placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 transition-all resize-none"
                placeholder={t('skills.description')}
                rows={3}
                required
              />
            </div>

            {/* Code Editor - Always show if code exists */}
            {formData.code && (
              <div>
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t('skills.pythonCode')} <span className="text-red-500">*</span>
                </label>
                <div className="rounded-xl overflow-hidden border border-zinc-200 dark:border-zinc-700">
                  <CodeEditor
                    value={formData.code}
                    onChange={(value) => setFormData({ ...formData, code: value })}
                    height="400px"
                  />
                </div>
              </div>
            )}

            {/* Dependencies */}
            <div>
              <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                {t('skills.dependencies')}
              </label>
              <input
                type="text"
                value={formData.dependencies.join(', ')}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    dependencies: e.target.value.split(',').map((d) => d.trim()).filter(Boolean),
                  })
                }
                className="w-full px-4 py-3 rounded-xl glass text-zinc-800 dark:text-white placeholder:text-zinc-500 dark:placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 transition-all font-mono text-sm"
                placeholder={t('skills.dependenciesPlaceholder')}
              />
              <p className="mt-2 text-xs text-zinc-600 dark:text-zinc-400">{t('skills.dependenciesNote')}</p>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-6 border-t border-zinc-200 dark:border-zinc-700">
            <button
              type="button"
              onClick={handleClose}
              className="px-6 py-2.5 rounded-xl hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-700 dark:text-zinc-300 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isSubmitting}
            >
              {t('skills.cancel')}
            </button>
            <button
              type="submit"
              className="px-6 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  {t('skills.saving')}
                </span>
              ) : (
                t('skills.saveChanges')
              )}
            </button>
          </div>
        </form>
      </div>
    </LayoutModal>
  );
}
