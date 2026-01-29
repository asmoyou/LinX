import { X, Upload, FileCode } from 'lucide-react';
import { useState } from 'react';
import CodeEditor from './CodeEditor';
import SkillTypeSelector, { type SkillType } from './SkillTypeSelector';
import TemplateSelector from './TemplateSelector';
import { skillsApi } from '@/api/skills';
import { useTranslation } from 'react-i18next';

interface AddSkillModalV2Props {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: any) => Promise<void>;
}

type AgentSkillMode = 'single' | 'package';

export default function AddSkillModalV2({ isOpen, onClose, onSubmit }: AddSkillModalV2Props) {
  const { t } = useTranslation();
  const [step, setStep] = useState<'type' | 'template' | 'code'>('type');
  const [skillType, setSkillType] = useState<SkillType>('langchain_tool');
  const [agentSkillMode, setAgentSkillMode] = useState<AgentSkillMode>('single');
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    code: '',
    dependencies: [] as string[],
  });

  if (!isOpen) return null;

  const handleClose = () => {
    setStep('type');
    setSkillType('langchain_tool');
    setAgentSkillMode('single');
    setSelectedTemplate(null);
    setUploadedFile(null);
    setFormData({ name: '', description: '', code: '', dependencies: [] });
    onClose();
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setUploadedFile(file);
      // Auto-fill name from filename
      if (!formData.name) {
        const nameWithoutExt = file.name.replace(/\.(zip|tar\.gz)$/, '');
        setFormData({ ...formData, name: nameWithoutExt });
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      const submitData: any = {
        ...formData,
        skill_type: skillType,
      };

      // For agent skills in package mode, include file upload
      if (skillType === 'agent_skill' && agentSkillMode === 'package' && uploadedFile) {
        // TODO: Handle file upload to MinIO
        submitData.package_file = uploadedFile;
      }

      await onSubmit(submitData);
      handleClose();
    } catch (error) {
      console.error('Failed to create skill:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md animate-in fade-in duration-200" style={{ marginLeft: 'var(--sidebar-width, 0px)' }}>
      <div className="w-full max-w-4xl max-h-[90vh] overflow-y-auto modal-panel rounded-[24px] shadow-2xl p-6 animate-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-zinc-800 dark:text-white">{t('skills.createNewSkill')}</h2>
          <button 
            onClick={handleClose} 
            className="p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors"
          >
            <X className="w-6 h-6 text-zinc-700 dark:text-zinc-300" />
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Step 1: Select Type */}
          {step === 'type' && (
            <>
              <SkillTypeSelector selectedType={skillType} onTypeChange={setSkillType} />
              
              {/* Agent Skill Mode Selection */}
              {skillType === 'agent_skill' && (
                <div className="space-y-3">
                  <label className="block text-sm font-medium text-gray-800 dark:text-white">
                    {t('skills.selectImplementation')}
                  </label>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <button
                      type="button"
                      onClick={() => setAgentSkillMode('single')}
                      className={`
                        relative p-6 rounded-xl transition-all duration-300 text-left
                        ${
                          agentSkillMode === 'single'
                            ? 'bg-indigo-500 text-white shadow-lg shadow-indigo-500/30'
                            : 'glass text-gray-700 dark:text-gray-300 hover:bg-white/30 dark:hover:bg-black/30'
                        }
                      `}
                    >
                      <div className="flex items-start gap-4">
                        <div className={`p-3 rounded-xl transition-all duration-300 ${
                          agentSkillMode === 'single' 
                            ? 'bg-white/20' 
                            : 'bg-gray-100 dark:bg-gray-800'
                        }`}>
                          <FileCode className={`w-6 h-6 ${
                            agentSkillMode === 'single' 
                              ? 'text-white' 
                              : 'text-gray-600 dark:text-gray-400'
                          }`} />
                        </div>
                        <div className="flex-1">
                          <h4 className="font-semibold mb-1">
                            {t('skills.singleFileCode')}
                          </h4>
                          <p className={`text-sm ${
                            agentSkillMode === 'single' 
                              ? 'text-white/80' 
                              : 'text-gray-600 dark:text-gray-400'
                          }`}>
                            {t('skills.singleFileDesc')}
                          </p>
                        </div>
                      </div>
                    </button>
                    
                    <button
                      type="button"
                      onClick={() => setAgentSkillMode('package')}
                      className={`
                        relative p-6 rounded-xl transition-all duration-300 text-left
                        ${
                          agentSkillMode === 'package'
                            ? 'bg-purple-500 text-white shadow-lg shadow-purple-500/30'
                            : 'glass text-gray-700 dark:text-gray-300 hover:bg-white/30 dark:hover:bg-black/30'
                        }
                      `}
                    >
                      <div className="flex items-start gap-4">
                        <div className={`p-3 rounded-xl transition-all duration-300 ${
                          agentSkillMode === 'package' 
                            ? 'bg-white/20' 
                            : 'bg-gray-100 dark:bg-gray-800'
                        }`}>
                          <Upload className={`w-6 h-6 ${
                            agentSkillMode === 'package' 
                              ? 'text-white' 
                              : 'text-gray-600 dark:text-gray-400'
                          }`} />
                        </div>
                        <div className="flex-1">
                          <h4 className="font-semibold mb-1">
                            {t('skills.uploadPackage')}
                          </h4>
                          <p className={`text-sm ${
                            agentSkillMode === 'package' 
                              ? 'text-white/80' 
                              : 'text-gray-600 dark:text-gray-400'
                          }`}>
                            {t('skills.uploadPackageDesc')}
                          </p>
                        </div>
                      </div>
                    </button>
                  </div>
                </div>
              )}
              
              <div className="flex justify-end pt-4">
                <button
                  type="button"
                  onClick={() => {
                    // Agent skill package mode skips template selection
                    if (skillType === 'agent_skill' && agentSkillMode === 'package') {
                      setStep('code');
                    } else {
                      setStep('template');
                    }
                  }}
                  className="px-6 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white transition-colors font-medium"
                >
                  {t('skills.next')}
                </button>
              </div>
            </>
          )}

          {/* Step 2: Select Template (Optional) */}
          {step === 'template' && (
            <>
              <TemplateSelector
                skillType={skillType}
                selectedId={selectedTemplate}
                onSelect={(template: any) => {
                  setSelectedTemplate(template.id);
                  setFormData({
                    ...formData,
                    code: template.code,
                    dependencies: template.dependencies || [],
                  });
                }}
                onSkip={() => setStep('code')}
              />
              <div className="flex justify-between pt-4">
                <button
                  type="button"
                  onClick={() => setStep('type')}
                  className="px-6 py-2.5 rounded-xl hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-700 dark:text-zinc-300 transition-colors font-medium"
                >
                  {t('skills.previous')}
                </button>
                <button
                  type="button"
                  onClick={() => setStep('code')}
                  className="px-6 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white transition-colors font-medium"
                >
                  {selectedTemplate ? t('skills.useTemplate') : t('skills.skip')}
                </button>
              </div>
            </>
          )}

          {/* Step 3: Edit Code or Upload Package */}
          {step === 'code' && (
            <>
              <div className="space-y-4">
                {/* Basic Info */}
                <div>
                  <label className="block text-sm font-medium text-gray-800 dark:text-white mb-2">
                    {t('skills.skillName')} *
                  </label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className="w-full px-4 py-2.5 rounded-xl glass text-gray-800 dark:text-white placeholder:text-gray-500 dark:placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                    placeholder="e.g., my_custom_skill"
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-800 dark:text-white mb-2">
                    {t('skills.description')} *
                  </label>
                  <textarea
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    className="w-full px-4 py-2.5 rounded-xl glass text-gray-800 dark:text-white placeholder:text-gray-500 dark:placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 resize-none"
                    placeholder={t('skills.description')}
                    rows={2}
                    required
                  />
                </div>

                {/* Code Editor for Single File Mode */}
                {(skillType === 'langchain_tool' || (skillType === 'agent_skill' && agentSkillMode === 'single')) && (
                  <div>
                    <label className="block text-sm font-medium text-gray-800 dark:text-white mb-2">
                      {t('skills.pythonCode')} *
                    </label>
                    <CodeEditor
                      value={formData.code}
                      onChange={(value) => setFormData({ ...formData, code: value })}
                      height="400px"
                      placeholder={
                        skillType === 'langchain_tool'
                          ? `from langchain_core.tools import tool

@tool
def my_tool(param: str) -> str:
    """工具描述
    
    Args:
        param: 参数说明
        
    Returns:
        返回值说明
    """
    # 你的代码
    return result
`
                          : `from langchain_core.tools import tool
import requests
from typing import Dict, Any

@tool
def my_skill(url: str, method: str = "GET") -> Dict[str, Any]:
    """技能描述
    
    这是一个灵活的Agent Skill，可以包含更复杂的逻辑
    
    Args:
        url: API地址
        method: HTTP方法
        
    Returns:
        API响应
    """
    response = requests.request(method, url)
    return response.json()
`
                      }
                    />
                  </div>
                )}

                {/* File Upload for Package Mode */}
                {skillType === 'agent_skill' && agentSkillMode === 'package' && (
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <label className="block text-sm font-medium text-gray-800 dark:text-white">
                        {t('skills.uploadProjectPackage')} *
                      </label>
                      <button
                        type="button"
                        onClick={async () => {
                          try {
                            const blob = await skillsApi.downloadPackageTemplate();
                            const url = window.URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = 'agent-skill-package-template.zip';
                            document.body.appendChild(a);
                            a.click();
                            window.URL.revokeObjectURL(url);
                            document.body.removeChild(a);
                          } catch (error) {
                            console.error('下载失败:', error);
                            alert(t('skills.downloadFailed'));
                          }
                        }}
                        className="text-sm text-indigo-500 hover:text-indigo-600 dark:text-indigo-400 dark:hover:text-indigo-300 flex items-center gap-1.5 transition-all duration-300 hover:gap-2 font-medium"
                      >
                        <FileCode className="w-4 h-4" />
                        {t('skills.downloadTemplate')}
                      </button>
                    </div>
                    <div className="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-xl p-10 text-center hover:border-indigo-500 hover:bg-indigo-500/5 transition-all duration-300 glass">
                      <input
                        type="file"
                        accept=".zip,.tar.gz"
                        onChange={handleFileUpload}
                        className="hidden"
                        id="package-upload"
                        required
                      />
                      <label htmlFor="package-upload" className="cursor-pointer block">
                        {uploadedFile ? (
                          <div className="space-y-3">
                            <div className="w-16 h-16 rounded-full bg-green-500/10 flex items-center justify-center mx-auto">
                              <Upload className="w-8 h-8 text-green-500" />
                            </div>
                            <div>
                              <p className="text-gray-800 dark:text-white font-semibold mb-1">{uploadedFile.name}</p>
                              <p className="text-sm text-gray-600 dark:text-gray-400">
                                {(uploadedFile.size / 1024 / 1024).toFixed(2)} MB
                              </p>
                            </div>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.preventDefault();
                                setUploadedFile(null);
                              }}
                              className="mt-3 px-4 py-2 text-sm text-indigo-500 hover:text-indigo-600 dark:text-indigo-400 dark:hover:text-indigo-300 transition-colors font-medium rounded-lg hover:bg-indigo-500/10"
                            >
                              {t('skills.reselect')}
                            </button>
                          </div>
                        ) : (
                          <div className="space-y-3">
                            <div className="w-16 h-16 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center mx-auto">
                              <Upload className="w-8 h-8 text-gray-600 dark:text-gray-400" />
                            </div>
                            <div>
                              <p className="text-gray-800 dark:text-white font-medium mb-1">{t('skills.clickToUpload')}</p>
                              <p className="text-sm text-gray-600 dark:text-gray-400">{t('skills.supportedFormats')}</p>
                            </div>
                          </div>
                        )}
                      </label>
                    </div>
                    <div className="mt-3 p-3 rounded-lg bg-blue-500/10 border border-blue-500/20">
                      <p className="text-xs text-gray-800 dark:text-white">
                        💡 {t('skills.packageNote')}
                      </p>
                    </div>
                  </div>
                )}
              </div>

              <div className="flex justify-between pt-6 border-t border-zinc-200 dark:border-zinc-700">
                <button
                  type="button"
                  onClick={() => {
                    // Agent skill package mode should go back to type selection
                    if (skillType === 'agent_skill' && agentSkillMode === 'package') {
                      setStep('type');
                    } else {
                      setStep('template');
                    }
                  }}
                  className="px-6 py-2.5 rounded-xl hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-700 dark:text-zinc-300 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                  disabled={isSubmitting}
                >
                  {t('skills.previous')}
                </button>
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={handleClose}
                    className="px-6 py-2.5 rounded-xl hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-700 dark:text-zinc-300 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                    disabled={isSubmitting}
                  >
                    {t('skills.cancel')}
                  </button>
                  <button
                    type="submit"
                    className="px-6 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                    disabled={isSubmitting}
                  >
                    {isSubmitting ? (
                      <span className="flex items-center gap-2">
                        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        {t('skills.creating')}
                      </span>
                    ) : (
                      t('skills.createSkill')
                    )}
                  </button>
                </div>
              </div>
            </>
          )}
        </form>
      </div>
    </div>
  );
}
