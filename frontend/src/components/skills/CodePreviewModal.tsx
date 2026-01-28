import React from 'react';
import { X, Copy, Check } from 'lucide-react';
import { useState } from 'react';
import CodeEditor from './CodeEditor';
import { ModalPanel } from '@/components/ModalPanel';
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md" style={{ marginLeft: 'var(--sidebar-width, 0px)' }}>
      <ModalPanel className="w-full max-w-4xl max-h-[90vh] overflow-y-auto shadow-2xl p-0">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700 bg-gradient-to-r from-indigo-500/5 to-transparent">
          <div className="flex-1 min-w-0 mr-4">
            <h2 className="text-2xl font-bold text-gray-800 dark:text-white truncate">{skill.name}</h2>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1 line-clamp-2">{skill.description}</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl hover:bg-white/30 dark:hover:bg-black/30 transition-all duration-300 hover:rotate-90 flex-shrink-0"
          >
            <X className="w-5 h-5 text-gray-600 dark:text-gray-400" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Metadata */}
          <div className="grid grid-cols-3 gap-4">
            <div className="p-4 rounded-xl bg-gradient-to-br from-indigo-500/10 to-indigo-500/5 border border-indigo-500/20">
              <div className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">{t('skills.version')}</div>
              <div className="text-lg font-bold text-gray-800 dark:text-white">v{skill.version}</div>
            </div>
            <div className="p-4 rounded-xl bg-gradient-to-br from-blue-500/10 to-blue-500/5 border border-blue-500/20">
              <div className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">{t('skills.dependencies')}</div>
              <div className="text-lg font-bold text-gray-800 dark:text-white">
                {skill.dependencies?.length || 0} {t('skills.packages')}
              </div>
            </div>
            <div className="p-4 rounded-xl bg-gradient-to-br from-green-500/10 to-green-500/5 border border-green-500/20">
              <div className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">{t('skills.createdAt')}</div>
              <div className="text-lg font-bold text-gray-800 dark:text-white">
                {new Date(skill.created_at).toLocaleDateString('zh-CN')}
              </div>
            </div>
          </div>

          {/* Dependencies */}
          {skill.dependencies && skill.dependencies.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-gray-800 dark:text-white mb-3">{t('skills.dependencies')}</h3>
              <div className="flex flex-wrap gap-2">
                {skill.dependencies.map((dep) => (
                  <span
                    key={dep}
                    className="px-3 py-1.5 rounded-lg text-xs glass text-gray-800 dark:text-white font-mono hover:bg-white/30 dark:hover:bg-black/30 transition-colors"
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
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-gray-800 dark:text-white">{t('skills.pythonCode')}</h3>
                <button
                  onClick={handleCopy}
                  className="flex items-center gap-2 px-4 py-2 rounded-xl glass hover:bg-white/30 dark:hover:bg-black/30 text-gray-700 dark:text-gray-300 transition-all duration-300 text-sm font-medium hover:shadow-lg"
                >
                  {copied ? (
                    <>
                      <Check className="w-4 h-4 text-green-500" />
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
              <div className="rounded-xl overflow-hidden border border-gray-200 dark:border-gray-700 shadow-lg">
                <CodeEditor value={skill.code} onChange={() => {}} readOnly height="500px" />
              </div>
            </div>
          )}

          {/* Interface Definition */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <h3 className="text-sm font-semibold text-gray-800 dark:text-white mb-3">{t('skills.inputs')}</h3>
              <div className="space-y-2">
                {Object.entries(skill.interface_definition.inputs).length > 0 ? (
                  Object.entries(skill.interface_definition.inputs).map(([key, type]) => (
                    <div
                      key={key}
                      className="flex items-center justify-between p-3 rounded-xl glass text-sm hover:bg-white/30 dark:hover:bg-black/30 transition-colors"
                    >
                      <span className="text-gray-800 dark:text-white font-mono font-medium">{key}</span>
                      <span className="text-gray-600 dark:text-gray-400 text-xs">{type}</span>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-gray-600 dark:text-gray-400 p-3 text-center glass rounded-xl">{t('skills.noInputs')}</p>
                )}
              </div>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-gray-800 dark:text-white mb-3">{t('skills.outputs')}</h3>
              <div className="space-y-2">
                {Object.entries(skill.interface_definition.outputs).length > 0 ? (
                  Object.entries(skill.interface_definition.outputs).map(([key, type]) => (
                    <div
                      key={key}
                      className="flex items-center justify-between p-3 rounded-xl glass text-sm hover:bg-white/30 dark:hover:bg-black/30 transition-colors"
                    >
                      <span className="text-gray-800 dark:text-white font-mono font-medium">{key}</span>
                      <span className="text-gray-600 dark:text-gray-400 text-xs">{type}</span>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-gray-600 dark:text-gray-400 p-3 text-center glass rounded-xl">{t('skills.noOutputs')}</p>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end p-6 border-t border-gray-200 dark:border-gray-700 bg-gradient-to-r from-indigo-500/5 to-transparent">
          <button
            onClick={onClose}
            className="px-8 py-3 rounded-xl bg-indigo-500 hover:bg-indigo-600 text-white transition-all duration-300 font-medium shadow-lg hover:shadow-indigo-500/25 hover:-translate-y-0.5"
          >
            {t('skills.close')}
          </button>
        </div>
      </ModalPanel>
    </div>
  );
};

export default CodePreviewModal;
