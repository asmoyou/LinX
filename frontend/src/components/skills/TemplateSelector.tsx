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
        <div className="text-center">
          <Loader2 className="w-8 h-8 animate-spin text-indigo-500 mx-auto mb-2" />
          <p className="text-sm text-gray-600 dark:text-gray-400">{t('skills.loadingTemplates')}</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <div className="w-16 h-16 rounded-full bg-red-500/10 flex items-center justify-center mx-auto mb-4">
          <svg className="w-8 h-8 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <p className="text-red-500 font-medium">{error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-800 dark:text-white mb-1">
          {t('skills.selectTemplate')}
        </label>
        <p className="text-xs text-gray-600 dark:text-gray-400">
          {t('skills.selectTemplateDesc')}
        </p>
      </div>
      
      {templates.length === 0 ? (
        <div className="text-center py-12">
          <div className="w-16 h-16 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center mx-auto mb-4">
            <FileCode className="w-8 h-8 text-gray-600 dark:text-gray-400" />
          </div>
          <p className="text-gray-600 dark:text-gray-400 mb-4">{t('skills.noTemplates')}</p>
          <button
            type="button"
            onClick={onSkip}
            className="px-6 py-3 rounded-xl bg-indigo-500 hover:bg-indigo-600 text-white transition-all duration-300 font-medium shadow-lg hover:shadow-indigo-500/25 hover:-translate-y-0.5"
          >
            {t('skills.startFromScratch')}
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-h-96 overflow-y-auto pr-2">
          {templates.map((template) => (
            <button
              key={template.id}
              type="button"
              onClick={() => onSelect(template)}
              className={`
                p-5 rounded-xl transition-all duration-300 text-left
                ${
                  selectedId === template.id
                    ? 'bg-indigo-500 text-white shadow-lg shadow-indigo-500/30'
                    : 'glass text-gray-700 dark:text-gray-300 hover:bg-white/30 dark:hover:bg-black/30'
                }
              `}
            >
              <div className="flex items-start gap-3">
                <div className={`p-2.5 rounded-lg transition-all duration-300 ${
                  selectedId === template.id 
                    ? 'bg-white/20' 
                    : 'bg-gray-100 dark:bg-gray-800'
                }`}>
                  <FileCode className="w-5 h-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold mb-1">
                    {template.name}
                  </h3>
                  <p className={`text-sm mb-3 line-clamp-2 ${
                    selectedId === template.id 
                      ? 'text-white/80' 
                      : 'text-gray-600 dark:text-gray-400'
                  }`}>{template.description}</p>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                      selectedId === template.id
                        ? 'bg-white/20 text-white'
                        : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300'
                    }`}>
                      {template.difficulty}
                    </span>
                    {template.dependencies.length > 0 && (
                      <span className={`text-xs ${
                        selectedId === template.id 
                          ? 'text-white/70' 
                          : 'text-gray-600 dark:text-gray-400'
                      }`}>
                        {template.dependencies.length} {t('skills.dependencies')}
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
