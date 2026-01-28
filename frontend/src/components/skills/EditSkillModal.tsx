import { X } from 'lucide-react';
import { useState, useEffect } from 'react';
import CodeEditor from './CodeEditor';
import type { Skill } from '@/api/skills';
import { useTranslation } from 'react-i18next';

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
      await onSubmit(skill.skill_id, formData);
      handleClose();
    } catch (error) {
      console.error('Failed to update skill:', error);
      alert(t('skills.updateFailed'));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md" style={{ marginLeft: 'var(--sidebar-width, 0px)' }}>
      <div className="modal-panel w-full max-w-4xl max-h-[90vh] overflow-y-auto rounded-[24px] shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700 bg-gradient-to-r from-indigo-500/5 to-transparent">
          <div>
            <h2 className="text-2xl font-bold text-gray-800 dark:text-white">{t('skills.editSkill')}</h2>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{t('skills.editSkillDesc')}</p>
          </div>
          <button 
            onClick={handleClose} 
            className="p-2 rounded-xl hover:bg-white/30 dark:hover:bg-black/30 transition-all duration-300 hover:rotate-90"
          >
            <X className="w-5 h-5 text-gray-600 dark:text-gray-400" />
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          <div className="space-y-5">
            {/* Basic Info */}
            <div>
              <label className="block text-sm font-medium text-gray-800 dark:text-white mb-2">
                {t('skills.skillName')} *
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="w-full px-4 py-3 rounded-xl glass text-gray-800 dark:text-white placeholder:text-gray-500 dark:placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all"
                placeholder="e.g., my_custom_skill"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-800 dark:text-white mb-2">
                {t('skills.description')} *
              </label>
              <textarea
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="w-full px-4 py-3 rounded-xl glass text-gray-800 dark:text-white placeholder:text-gray-500 dark:placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all resize-none"
                placeholder={t('skills.description')}
                rows={3}
                required
              />
            </div>

            {/* Code Editor */}
            {formData.code && (
              <div>
                <label className="block text-sm font-medium text-gray-800 dark:text-white mb-2">
                  {t('skills.pythonCode')} *
                </label>
                <div className="rounded-xl overflow-hidden border border-gray-200 dark:border-gray-700">
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
              <label className="block text-sm font-medium text-gray-800 dark:text-white mb-2">
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
                className="w-full px-4 py-3 rounded-xl glass text-gray-800 dark:text-white placeholder:text-gray-500 dark:placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all font-mono text-sm"
                placeholder={t('skills.dependenciesPlaceholder')}
              />
              <p className="mt-2 text-xs text-gray-600 dark:text-gray-400">{t('skills.dependenciesNote')}</p>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-6 border-t border-gray-200 dark:border-gray-700">
            <button
              type="button"
              onClick={handleClose}
              className="px-8 py-3 rounded-xl glass hover:bg-white/30 dark:hover:bg-black/30 text-gray-700 dark:text-gray-300 transition-all duration-300 font-medium hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isSubmitting}
            >
              {t('skills.cancel')}
            </button>
            <button
              type="submit"
              className="px-8 py-3 rounded-xl bg-indigo-500 hover:bg-indigo-600 text-white transition-all duration-300 font-medium shadow-lg hover:shadow-indigo-500/25 hover:-translate-y-0.5 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0"
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
    </div>
  );
}
