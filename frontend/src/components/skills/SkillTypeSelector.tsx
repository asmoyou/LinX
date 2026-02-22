import React from 'react';
import { Code2, BookOpen } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export type SkillType = 'langchain_tool' | 'agent_skill';

interface SkillTypeOption {
  type: SkillType;
  icon: React.ReactNode;
  titleKey: string;
  descriptionKey: string;
  detailsKey: string;
  badgeKey: string;
  badgeColor: string;
  examplesKey: string[];
}

interface SkillTypeSelectorProps {
  selectedType: SkillType;
  onTypeChange: (type: SkillType) => void;
}

const SkillTypeSelector: React.FC<SkillTypeSelectorProps> = ({
  selectedType,
  onTypeChange,
}) => {
  const { t } = useTranslation();

  const skillTypeOptions: SkillTypeOption[] = [
    {
      type: 'langchain_tool',
      icon: <Code2 className="w-6 h-6" />,
      titleKey: 'skills.types.langchainTool.title',
      descriptionKey: 'skills.types.langchainTool.description',
      detailsKey: 'skills.types.langchainTool.details',
      badgeKey: 'skills.types.langchainTool.badge',
      badgeColor: 'bg-blue-100 dark:bg-blue-500/20 text-blue-700 dark:text-blue-400',
      examplesKey: ['skills.types.langchainTool.example1', 'skills.types.langchainTool.example2', 'skills.types.langchainTool.example3'],
    },
    {
      type: 'agent_skill',
      icon: <BookOpen className="w-6 h-6" />,
      titleKey: 'skills.types.agentSkill.title',
      descriptionKey: 'skills.types.agentSkill.description',
      detailsKey: 'skills.types.agentSkill.details',
      badgeKey: 'skills.types.agentSkill.badge',
      badgeColor: 'bg-purple-100 dark:bg-purple-500/20 text-purple-700 dark:text-purple-400',
      examplesKey: ['skills.types.agentSkill.example1', 'skills.types.agentSkill.example2', 'skills.types.agentSkill.example3', 'skills.types.agentSkill.example4'],
    },
  ];
  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-800 dark:text-white mb-1">
          {t('skills.selectSkillType')}
        </label>
        <p className="text-xs text-gray-600 dark:text-gray-400">
          {t('skills.selectSkillTypeDesc')}
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {skillTypeOptions.map((option) => (
          <button
            key={option.type}
            type="button"
            onClick={() => onTypeChange(option.type)}
            className={`
              relative p-6 rounded-xl transition-all duration-300 text-left
              ${
                selectedType === option.type
                  ? 'bg-indigo-500 text-white shadow-lg shadow-indigo-500/30'
                  : 'glass text-gray-700 dark:text-gray-300 hover:bg-white/30 dark:hover:bg-black/30'
              }
            `}
          >
            {/* Icon */}
            <div
              className={`
                inline-flex p-3 rounded-xl mb-4 transition-all duration-300
                ${selectedType === option.type ? 'bg-white/20' : 'bg-gray-100 dark:bg-gray-800'}
              `}
            >
              {option.icon}
            </div>

            {/* Title and Badge */}
            <div className="flex items-center gap-2 mb-2">
              <h3 className="font-semibold">
                {t(option.titleKey)}
              </h3>
              <span className={`px-2.5 py-1 rounded-lg text-xs font-medium ${
                selectedType === option.type 
                  ? 'bg-white/20 text-white' 
                  : option.badgeColor
              }`}>
                {t(option.badgeKey)}
              </span>
            </div>

            {/* Description */}
            <p className={`text-sm mb-4 leading-relaxed ${
              selectedType === option.type 
                ? 'text-white/80' 
                : 'text-gray-600 dark:text-gray-400'
            }`}>{t(option.detailsKey)}</p>

            {/* Examples */}
            <div className="space-y-2">
              <p className={`text-xs font-medium uppercase tracking-wide ${
                selectedType === option.type 
                  ? 'text-white/70' 
                  : 'text-gray-600 dark:text-gray-400'
              }`}>{t('skills.examples')}:</p>
              <div className="flex flex-wrap gap-2">
                {option.examplesKey.map((exampleKey) => (
                  <span
                    key={exampleKey}
                    className={`px-2.5 py-1 rounded-lg text-xs transition-colors ${
                      selectedType === option.type
                        ? 'bg-white/20 text-white'
                        : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300'
                    }`}
                  >
                    {t(exampleKey)}
                  </span>
                ))}
              </div>
            </div>
          </button>
        ))}
      </div>

      {/* Help Text */}
      <div className="p-4 rounded-xl bg-blue-500/10 border border-blue-500/20">
        <p className="text-sm text-gray-800 dark:text-white">
          <strong className="font-semibold">💡 {t('skills.tip')}:</strong> {t('skills.typeSelectionTip')}
        </p>
      </div>
    </div>
  );
};

export default SkillTypeSelector;
