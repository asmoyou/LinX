import { X } from 'lucide-react';
import SkillTester from './SkillTester';
import { useTranslation } from 'react-i18next';

interface SkillTesterModalProps {
  isOpen: boolean;
  onClose: () => void;
  skillId: string;
  skillName: string;
  interfaceDefinition: {
    inputs: Record<string, string>;
    outputs: Record<string, string>;
    required_inputs?: string[];
  };
}

export default function SkillTesterModal({
  isOpen,
  onClose,
  skillId,
  skillName,
  interfaceDefinition,
}: SkillTesterModalProps) {
  const { t } = useTranslation();

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md animate-in fade-in duration-200" style={{ marginLeft: 'var(--sidebar-width, 0px)' }}>
      <div className="w-full max-w-4xl max-h-[90vh] overflow-hidden modal-panel rounded-[24px] shadow-2xl p-6 flex flex-col animate-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between mb-6 flex-shrink-0">
          <h2 className="text-2xl font-bold text-zinc-800 dark:text-white">
            {t('skills.testSkill')}
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors"
          >
            <X className="w-6 h-6 text-zinc-700 dark:text-zinc-300" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          <SkillTester
            skillId={skillId}
            skillName={skillName}
            interfaceDefinition={interfaceDefinition}
          />
        </div>
      </div>
    </div>
  );
}
