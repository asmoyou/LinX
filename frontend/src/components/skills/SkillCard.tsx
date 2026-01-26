import { Code2, Package, Trash2, Edit, ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';
import type { Skill } from '@/api/skills';

interface SkillCardProps {
  skill: Skill;
  onEdit: (skill: Skill) => void;
  onDelete: (skillId: string) => void;
}

export default function SkillCard({ skill, onEdit, onDelete }: SkillCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const inputCount = Object.keys(skill.interface_definition.inputs || {}).length;
  const outputCount = Object.keys(skill.interface_definition.outputs || {}).length;
  const dependencyCount = skill.dependencies?.length || 0;

  return (
    <div className="glass-panel p-6 hover:scale-[1.02] transition-all duration-300">
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-start gap-3 flex-1">
          <div className="p-2 rounded-lg bg-primary/10">
            <Code2 className="w-5 h-5 text-primary" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-lg font-semibold text-foreground mb-1 truncate">
              {skill.name}
            </h3>
            <p className="text-sm text-muted-foreground line-clamp-2">
              {skill.description}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 ml-2">
          <button
            onClick={() => onEdit(skill)}
            className="p-2 rounded-lg hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors"
            title="Edit skill"
          >
            <Edit className="w-4 h-4" />
          </button>
          <button
            onClick={() => onDelete(skill.skill_id)}
            className="p-2 rounded-lg hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
            title="Delete skill"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="flex items-center gap-4 mb-4 text-sm">
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <span className="font-medium text-foreground">{inputCount}</span>
          <span>inputs</span>
        </div>
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <span className="font-medium text-foreground">{outputCount}</span>
          <span>outputs</span>
        </div>
        {dependencyCount > 0 && (
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <Package className="w-3.5 h-3.5" />
            <span className="font-medium text-foreground">{dependencyCount}</span>
            <span>deps</span>
          </div>
        )}
      </div>

      {/* Version Badge */}
      <div className="flex items-center justify-between">
        <span className="px-2 py-1 rounded-md bg-primary/10 text-primary text-xs font-medium">
          v{skill.version}
        </span>
        
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          {isExpanded ? (
            <>
              <span>Hide details</span>
              <ChevronUp className="w-4 h-4" />
            </>
          ) : (
            <>
              <span>Show details</span>
              <ChevronDown className="w-4 h-4" />
            </>
          )}
        </button>
      </div>

      {/* Expanded Details */}
      {isExpanded && (
        <div className="mt-4 pt-4 border-t border-border/50 space-y-4">
          {/* Inputs */}
          {inputCount > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-foreground mb-2">Inputs</h4>
              <div className="space-y-1">
                {Object.entries(skill.interface_definition.inputs).map(([key, type]) => (
                  <div key={key} className="flex items-center justify-between text-sm">
                    <span className="text-foreground font-mono">{key}</span>
                    <span className="text-muted-foreground">{type}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Outputs */}
          {outputCount > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-foreground mb-2">Outputs</h4>
              <div className="space-y-1">
                {Object.entries(skill.interface_definition.outputs).map(([key, type]) => (
                  <div key={key} className="flex items-center justify-between text-sm">
                    <span className="text-foreground font-mono">{key}</span>
                    <span className="text-muted-foreground">{type}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Dependencies */}
          {dependencyCount > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-foreground mb-2">Dependencies</h4>
              <div className="flex flex-wrap gap-2">
                {skill.dependencies.map((dep) => (
                  <span
                    key={dep}
                    className="px-2 py-1 rounded-md bg-muted/50 text-muted-foreground text-xs font-mono"
                  >
                    {dep}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
