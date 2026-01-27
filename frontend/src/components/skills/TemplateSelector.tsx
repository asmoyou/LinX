import React, { useEffect, useState } from 'react';
import { FileCode, Loader2 } from 'lucide-react';
import { skillsApi } from '@/api/skills';
import { useTranslation } from 'react-i18next';

interface Template {
  id: string;
  name: string;
  description: string;
  category: string;
  difficulty: string;
  skill_type: string;
  code: string;
  dependencies: string[];
}

interface TemplateSelectorProps {
  skillType: string;
  onSelect: (template: Template) => void;
  onSkip: () => void;
  selectedId: string | null;
}

const TemplateSelector: React.FC<TemplateSelectorProps> = ({ skillType, onSelect, onSkip, selectedId }) => {
  const { t } = useTranslation();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadTemplates();
  }, [skillType]);

  const loadTemplates = async () => {
    try {
      setLoading(true);
      const data = await skillsApi.getTemplates();
      // Filter templates based on skill type
      const filtered = data.filter((t: Template) => {
        if (skillType === 'langchain_tool') {
          return t.category === 'langchain_tool';
        } else {
          return t.category === 'agent_skill';
        }
      });
      setTemplates(filtered);
    } catch (err) {
      setError('Failed to load templates');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 animate-spin text-white/60" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12 text-red-400">
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-white/90 mb-1">
          {t('skills.selectTemplate')}
        </label>
        <p className="text-xs text-white/60">
          {t('skills.selectTemplateDesc')}
        </p>
      </div>
      
      {templates.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-white/60 mb-4">{t('skills.noTemplates')}</p>
          <button
            type="button"
            onClick={onSkip}
            className="px-6 py-2 rounded-lg bg-blue-500 hover:bg-blue-600 text-white transition-colors"
          >
            {t('skills.startFromScratch')}
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-96 overflow-y-auto">
          {templates.map((template) => (
            <button
              key={template.id}
              type="button"
              onClick={() => onSelect(template)}
              className={`
                p-4 rounded-lg border-2 transition-all text-left
                ${
                  selectedId === template.id
                    ? 'border-blue-500 bg-blue-500/10'
                    : 'border-white/10 bg-white/5 hover:border-white/20'
                }
              `}
            >
              <div className="flex items-start gap-3">
                <div className="p-2 rounded-lg bg-white/10">
                  <FileCode className="w-5 h-5 text-white/60" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-medium text-white/90 mb-1">{template.name}</h3>
                  <p className="text-sm text-white/60 mb-2">{template.description}</p>
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded text-xs bg-white/10 text-white/70">
                      {template.difficulty}
                    </span>
                    {template.dependencies.length > 0 && (
                      <span className="text-xs text-white/50">
                        {template.dependencies.length} deps
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default TemplateSelector;
