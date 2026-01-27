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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" style={{ marginLeft: 'var(--sidebar-width, 0px)' }}>
      <div className="glass-panel w-full max-w-4xl max-h-[90vh] overflow-y-auto rounded-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-border/50">
          <div>
            <h2 className="text-xl font-semibold text-foreground">{t('skills.editSkill')}</h2>
            <p className="text-sm text-muted-foreground mt-1">{t('skills.editSkillDesc')}</p>
          </div>
          <button onClick={handleClose} className="p-2 rounded-xl hover:bg-muted/50 transition-colors">
            <X className="w-5 h-5 text-muted-foreground" />
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          <div className="space-y-4">
            {/* Basic Info */}
            <div>
              <label className="block text-sm font-medium text-foreground mb-2">
                {t('skills.skillName')} *
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="w-full px-4 py-2.5 rounded-xl bg-muted/50 border border-border/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                placeholder="e.g., my_custom_skill"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground mb-2">
                {t('skills.description')} *
              </label>
              <textarea
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="w-full px-4 py-2.5 rounded-xl bg-muted/50 border border-border/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 resize-none"
                placeholder={t('skills.description')}
                rows={2}
                required
              />
            </div>

            {/* Code Editor */}
            {formData.code && (
              <div>
                <label className="block text-sm font-medium text-foreground mb-2">
                  {t('skills.pythonCode')} *
                </label>
                <CodeEditor
                  value={formData.code}
                  onChange={(value) => setFormData({ ...formData, code: value })}
                  height="400px"
                />
              </div>
            )}

            {/* Dependencies */}
            <div>
              <label className="block text-sm font-medium text-foreground mb-2">
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
                className="w-full px-4 py-2.5 rounded-xl bg-muted/50 border border-border/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                placeholder={t('skills.dependenciesPlaceholder')}
              />
              <p className="mt-1 text-xs text-muted-foreground">{t('skills.dependenciesNote')}</p>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-border/50">
            <button
              type="button"
              onClick={handleClose}
              className="px-6 py-2.5 rounded-xl bg-muted/50 hover:bg-muted text-foreground transition-colors font-medium"
              disabled={isSubmitting}
            >
              {t('skills.cancel')}
            </button>
            <button
              type="submit"
              className="px-6 py-2.5 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isSubmitting}
            >
              {isSubmitting ? t('skills.saving') : t('skills.saveChanges')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
