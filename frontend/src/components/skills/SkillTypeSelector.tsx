import React from 'react';
import { Code2, Zap } from 'lucide-react';
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
      icon: <Zap className="w-6 h-6" />,
      titleKey: 'skills.types.langchainTool.title',
      descriptionKey: 'skills.types.langchainTool.description',
      detailsKey: 'skills.types.langchainTool.details',
      badgeKey: 'skills.types.langchainTool.badge',
      badgeColor: 'bg-blue-500/20 text-blue-400',
      examplesKey: ['skills.types.langchainTool.example1', 'skills.types.langchainTool.example2', 'skills.types.langchainTool.example3'],
    },
    {
      type: 'agent_skill',
      icon: <Code2 className="w-6 h-6" />,
      titleKey: 'skills.types.agentSkill.title',
      descriptionKey: 'skills.types.agentSkill.description',
      detailsKey: 'skills.types.agentSkill.details',
      badgeKey: 'skills.types.agentSkill.badge',
      badgeColor: 'bg-purple-500/20 text-purple-400',
      examplesKey: ['skills.types.agentSkill.example1', 'skills.types.agentSkill.example2', 'skills.types.agentSkill.example3', 'skills.types.agentSkill.example4'],
    },
  ];
  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-white/90 mb-1">
          {t('skills.selectSkillType')}
        </label>
        <p className="text-xs text-white/60">
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
              relative p-5 rounded-lg border-2 transition-all text-left
              ${
                selectedType === option.type
                  ? 'border-blue-500 bg-blue-500/10'
                  : 'border-white/10 bg-white/5 hover:border-white/20 hover:bg-white/10'
              }
            `}
          >
            {/* Selection Indicator */}
            {selectedType === option.type && (
              <div className="absolute top-3 right-3">
                <div className="w-6 h-6 rounded-full bg-blue-500/20 flex items-center justify-center">
                  <svg className="w-4 h-4 text-blue-400" fill="currentColor" viewBox="0 0 20 20">
                    <path
                      fillRule="evenodd"
                      d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                      clipRule="evenodd"
                    />
                  </svg>
                </div>
              </div>
            )}

            {/* Icon */}
            <div
              className={`
                inline-flex p-3 rounded-lg mb-3
                ${selectedType === option.type ? 'bg-blue-500/20 text-blue-400' : 'bg-white/10 text-white/60'}
              `}
            >
              {option.icon}
            </div>

            {/* Title and Badge */}
            <div className="flex items-center gap-2 mb-2">
              <h3 className="font-semibold text-white/90">{t(option.titleKey)}</h3>
              <span className={`px-2 py-0.5 rounded text-xs font-medium ${option.badgeColor}`}>
                {t(option.badgeKey)}
              </span>
            </div>

            {/* Description */}
            <p className="text-sm text-white/70 mb-3">{t(option.detailsKey)}</p>

            {/* Examples */}
            <div className="space-y-2">
              <p className="text-xs text-white/50 uppercase tracking-wide">{t('skills.examples')}:</p>
              <div className="flex flex-wrap gap-2">
                {option.examplesKey.map((exampleKey) => (
                  <span
                    key={exampleKey}
                    className="px-2 py-1 rounded-md bg-white/5 text-xs text-white/70"
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
      <div className="p-4 rounded-lg bg-white/5 border border-white/10">
        <p className="text-sm text-white/60">
          <strong className="text-white/90">💡 {t('skills.tip')}:</strong> {t('skills.typeSelectionTip')}
        </p>
      </div>
    </div>
  );
};

export default SkillTypeSelector;
