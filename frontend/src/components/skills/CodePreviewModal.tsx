import React from 'react';
import { X, Copy, Check } from 'lucide-react';
import { useState } from 'react';
import CodeEditor from './CodeEditor';
import type { Skill } from '@/api/skills';
import { useTranslation } from 'react-i18next';

interface CodePreviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  skill: Skill & { code?: string };
}

const CodePreviewModal: React.FC<CodePreviewModalProps> = ({ isOpen, onClose, skill }) => {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const handleCopy = async () => {
    if (skill.code) {
      await navigator.clipboard.writeText(skill.code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" style={{ marginLeft: 'var(--sidebar-width, 0px)' }}>
      <div className="glass-panel w-full max-w-4xl max-h-[90vh] overflow-y-auto rounded-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-border/50">
          <div>
            <h2 className="text-xl font-semibold text-foreground">{skill.name}</h2>
            <p className="text-sm text-muted-foreground mt-1">{skill.description}</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl hover:bg-muted/50 transition-colors"
          >
            <X className="w-5 h-5 text-muted-foreground" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4">
          {/* Metadata */}
          <div className="grid grid-cols-3 gap-4">
            <div className="p-3 rounded-xl bg-muted/50">
              <div className="text-xs text-muted-foreground mb-1">{t('skills.version')}</div>
              <div className="text-sm font-medium text-foreground">v{skill.version}</div>
            </div>
            <div className="p-3 rounded-xl bg-muted/50">
              <div className="text-xs text-muted-foreground mb-1">{t('skills.dependencies')}</div>
              <div className="text-sm font-medium text-foreground">
                {skill.dependencies?.length || 0} {t('skills.packages')}
              </div>
            </div>
            <div className="p-3 rounded-xl bg-muted/50">
              <div className="text-xs text-muted-foreground mb-1">{t('skills.createdAt')}</div>
              <div className="text-sm font-medium text-foreground">
                {new Date(skill.created_at).toLocaleDateString('zh-CN')}
              </div>
            </div>
          </div>

          {/* Dependencies */}
          {skill.dependencies && skill.dependencies.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-foreground mb-2">{t('skills.dependencies')}</h3>
              <div className="flex flex-wrap gap-2">
                {skill.dependencies.map((dep) => (
                  <span
                    key={dep}
                    className="px-2 py-1 rounded text-xs bg-muted/50 text-muted-foreground font-mono"
                  >
                    {dep}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Code */}
          {skill.code && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-medium text-foreground">{t('skills.pythonCode')}</h3>
                <button
                  onClick={handleCopy}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-muted/50 hover:bg-muted text-muted-foreground transition-colors text-sm"
                >
                  {copied ? (
                    <>
                      <Check className="w-4 h-4" />
                      {t('skills.copied')}
                    </>
                  ) : (
                    <>
                      <Copy className="w-4 h-4" />
                      {t('skills.copy')}
                    </>
                  )}
                </button>
              </div>
              <CodeEditor value={skill.code} onChange={() => {}} readOnly height="500px" />
            </div>
          )}

          {/* Interface Definition */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <h3 className="text-sm font-medium text-foreground mb-2">{t('skills.inputs')}</h3>
              <div className="space-y-1">
                {Object.entries(skill.interface_definition.inputs).length > 0 ? (
                  Object.entries(skill.interface_definition.inputs).map(([key, type]) => (
                    <div
                      key={key}
                      className="flex items-center justify-between p-2 rounded bg-muted/50 text-sm"
                    >
                      <span className="text-foreground font-mono">{key}</span>
                      <span className="text-muted-foreground">{type}</span>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground">{t('skills.noInputs')}</p>
                )}
              </div>
            </div>
            <div>
              <h3 className="text-sm font-medium text-foreground mb-2">{t('skills.outputs')}</h3>
              <div className="space-y-1">
                {Object.entries(skill.interface_definition.outputs).length > 0 ? (
                  Object.entries(skill.interface_definition.outputs).map(([key, type]) => (
                    <div
                      key={key}
                      className="flex items-center justify-between p-2 rounded bg-muted/50 text-sm"
                    >
                      <span className="text-foreground font-mono">{key}</span>
                      <span className="text-muted-foreground">{type}</span>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground">{t('skills.noOutputs')}</p>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end p-6 border-t border-border/50">
          <button
            onClick={onClose}
            className="px-6 py-2.5 rounded-xl bg-muted/50 hover:bg-muted text-foreground transition-colors font-medium"
          >
            {t('skills.close')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default CodePreviewModal;
