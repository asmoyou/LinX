import { Code2, Zap, Package, Layers, Trash2, Edit, Eye, Play, Power, PowerOff, TrendingUp } from 'lucide-react';
import { useState } from 'react';
import type { Skill } from '@/api/skills';
import SkillTester from './SkillTester';
import { useTranslation } from 'react-i18next';

interface SkillCardV2Props {
  skill: Skill & {
    skill_type?: string;
    is_active?: boolean;
    execution_count?: number;
    average_execution_time?: number;
  };
  onEdit: (skill: Skill) => void;
  onDelete: (skillId: string) => void;
  onToggleActive?: (skillId: string, isActive: boolean) => void;
  onViewCode?: (skill: Skill) => void;
}

const getSkillTypeInfo = (type: string, t: any) => {
  switch (type) {
    case 'langchain_tool':
      return { icon: Zap, label: t('skills.langchainTool'), color: 'text-green-400', bgColor: 'bg-green-500/10' };
    case 'agent_skill_simple':
      return { icon: Code2, label: t('skills.agentSkill'), color: 'text-blue-400', bgColor: 'bg-blue-500/10' };
    case 'agent_skill_module':
      return { icon: Layers, label: 'Module', color: 'text-purple-400', bgColor: 'bg-purple-500/10' };
    case 'agent_skill_package':
      return { icon: Package, label: 'Package', color: 'text-orange-400', bgColor: 'bg-orange-500/10' };
    default:
      return { icon: Code2, label: 'Skill', color: 'text-white/60', bgColor: 'bg-white/10' };
  }
};

export default function SkillCardV2({
  skill,
  onEdit,
  onDelete,
  onToggleActive,
  onViewCode,
}: SkillCardV2Props) {
  const { t } = useTranslation();
  const [showTester, setShowTester] = useState(false);
  const typeInfo = getSkillTypeInfo(skill.skill_type || 'langchain_tool', t);
  const TypeIcon = typeInfo.icon;

  return (
    <div className="glass-panel group relative rounded-2xl overflow-hidden p-6 hover:-translate-y-1 transition-all duration-300 flex flex-col h-full shadow-xl hover:shadow-2xl">
      {/* Gradient overlay on hover */}
      <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
      
      {/* Content */}
      <div className="relative z-10 flex flex-col h-full">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-start gap-3 flex-1">
            <div className={`p-3 rounded-xl ${typeInfo.bgColor} shadow-lg group-hover:shadow-xl transition-shadow duration-300`}>
              <TypeIcon className={`w-6 h-6 ${typeInfo.color}`} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <h3 className="text-lg font-semibold text-foreground truncate group-hover:text-primary transition-colors">
                  {skill.name}
                </h3>
                <span className={`px-2.5 py-1 rounded-lg text-xs font-medium whitespace-nowrap ${typeInfo.bgColor} ${typeInfo.color}`}>
                  {typeInfo.label}
                </span>
                {skill.is_active !== undefined && (
                  <span
                    className={`px-2.5 py-1 rounded-lg text-xs font-medium whitespace-nowrap ${
                      skill.is_active
                        ? 'bg-green-500/20 text-green-400'
                        : 'bg-gray-500/20 text-gray-400'
                    }`}
                  >
                    {skill.is_active ? t('skills.active') : t('skills.inactive')}
                  </span>
                )}
              </div>
              <p className="text-sm text-muted-foreground line-clamp-2">
                {skill.description}
              </p>
            </div>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-3 mb-4 flex-shrink-0">
          <div className="text-center p-3 rounded-xl bg-muted/30 hover:bg-muted/50 transition-colors">
            <div className="text-lg font-semibold text-foreground">
              {skill.execution_count || 0}
            </div>
            <div className="text-xs text-muted-foreground">{t('skills.executionCount')}</div>
          </div>
          <div className="text-center p-3 rounded-xl bg-muted/30 hover:bg-muted/50 transition-colors">
            <div className="text-lg font-semibold text-foreground">
              {skill.average_execution_time !== undefined && skill.average_execution_time !== null
                ? `${skill.average_execution_time.toFixed(3)}s`
                : '-'}
            </div>
            <div className="text-xs text-muted-foreground">{t('skills.avgTime')}</div>
          </div>
          <div className="text-center p-3 rounded-xl bg-muted/30 hover:bg-muted/50 transition-colors">
            <div className="text-lg font-semibold text-foreground">
              v{skill.version}
            </div>
            <div className="text-xs text-muted-foreground">{t('skills.version')}</div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 mt-auto">
          <button
            onClick={() => setShowTester(!showTester)}
            className="flex-1 px-4 py-2.5 rounded-xl bg-primary/10 hover:bg-primary/20 text-primary transition-all duration-300 flex items-center justify-center gap-2 text-sm font-medium hover:shadow-lg"
          >
            <Play className="w-4 h-4" />
            {t('skills.test')}
          </button>
          
          {onViewCode && (
            <button
              onClick={() => onViewCode(skill)}
              className="px-4 py-2.5 rounded-xl bg-muted/30 hover:bg-muted/50 text-foreground transition-all duration-300 hover:shadow-lg"
              title={t('skills.viewCode')}
            >
              <Eye className="w-4 h-4" />
            </button>
          )}
          
          {onToggleActive && (
            <button
              onClick={() => onToggleActive(skill.skill_id, skill.is_active || false)}
              className={`px-4 py-2.5 rounded-xl transition-all duration-300 hover:shadow-lg ${
                skill.is_active
                  ? 'bg-orange-500/10 hover:bg-orange-500/20 text-orange-400'
                  : 'bg-green-500/10 hover:bg-green-500/20 text-green-400'
              }`}
              title={skill.is_active ? t('skills.deactivate') : t('skills.activate')}
            >
              {skill.is_active ? <PowerOff className="w-4 h-4" /> : <Power className="w-4 h-4" />}
            </button>
          )}
          
          <button
            onClick={() => onEdit(skill)}
            className="px-4 py-2.5 rounded-xl bg-muted/30 hover:bg-muted/50 text-foreground transition-all duration-300 hover:shadow-lg"
            title={t('skills.edit')}
          >
            <Edit className="w-4 h-4" />
          </button>
          
          <button
            onClick={() => onDelete(skill.skill_id)}
            className="px-4 py-2.5 rounded-xl bg-red-500/10 hover:bg-red-500/20 text-red-400 transition-all duration-300 hover:shadow-lg"
            title={t('skills.delete')}
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>

        {/* Skill Tester */}
        {showTester && (
          <div className="mt-4 pt-4 border-t border-border/50">
            <SkillTester
              skillId={skill.skill_id}
              skillName={skill.name}
              interfaceDefinition={skill.interface_definition}
            />
          </div>
        )}
      </div>
    </div>
  );
}
