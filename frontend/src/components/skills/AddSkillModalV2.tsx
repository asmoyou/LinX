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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" style={{ marginLeft: 'var(--sidebar-width, 0px)' }}>
      <div className="glass-panel w-full max-w-4xl max-h-[90vh] overflow-y-auto rounded-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-border/50">
          <div>
            <h2 className="text-xl font-semibold text-foreground">{t('skills.createNewSkill')}</h2>
            <p className="text-sm text-muted-foreground mt-1">
              {step === 'type' && t('skills.step1')}
              {step === 'template' && t('skills.step2')}
              {step === 'code' && t('skills.step3')}
            </p>
          </div>
          <button onClick={handleClose} className="p-2 rounded-xl hover:bg-muted/50 transition-colors">
            <X className="w-5 h-5 text-muted-foreground" />
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {/* Step 1: Select Type */}
          {step === 'type' && (
            <>
              <SkillTypeSelector selectedType={skillType} onTypeChange={setSkillType} />
              
              {/* Agent Skill Mode Selection */}
              {skillType === 'agent_skill' && (
                <div className="space-y-3">
                  <label className="block text-sm font-medium text-white/90">
                    {t('skills.selectImplementation')}
                  </label>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <button
                      type="button"
                      onClick={() => setAgentSkillMode('single')}
                      className={`
                        p-4 rounded-xl border-2 transition-all text-left
                        ${
                          agentSkillMode === 'single'
                            ? 'border-primary bg-primary/10'
                            : 'border-border/50 bg-muted/30 hover:border-border'
                        }
                      `}
                    >
                      <div className="flex items-start gap-3">
                        <FileCode className="w-5 h-5 text-primary mt-0.5" />
                        <div>
                          <h4 className="font-medium text-foreground mb-1">{t('skills.singleFileCode')}</h4>
                          <p className="text-sm text-muted-foreground">
                            {t('skills.singleFileDesc')}
                          </p>
                        </div>
                      </div>
                    </button>
                    
                    <button
                      type="button"
                      onClick={() => setAgentSkillMode('package')}
                      className={`
                        p-4 rounded-xl border-2 transition-all text-left
                        ${
                          agentSkillMode === 'package'
                            ? 'border-purple-500 bg-purple-500/10'
                            : 'border-border/50 bg-muted/30 hover:border-border'
                        }
                      `}
                    >
                      <div className="flex items-start gap-3">
                        <Upload className="w-5 h-5 text-purple-400 mt-0.5" />
                        <div>
                          <h4 className="font-medium text-foreground mb-1">{t('skills.uploadPackage')}</h4>
                          <p className="text-sm text-muted-foreground">
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
                  className="px-6 py-2.5 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground transition-colors font-medium"
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
                  className="px-6 py-2.5 rounded-xl bg-muted/50 hover:bg-muted text-foreground transition-colors font-medium"
                >
                  {t('skills.previous')}
                </button>
                <button
                  type="button"
                  onClick={() => setStep('code')}
                  className="px-6 py-2.5 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground transition-colors font-medium"
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
                  <label className="block text-sm font-medium text-foreground mb-2">
                    {t('skills.skillName')} *
                  </label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className="w-full px-4 py-2.5 rounded-xl bg-muted/50 border border-border/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                    placeholder="e.g., my_custom_skill"
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-foreground mb-2">
                    {t('skills.description')} *
                  </label>
                  <textarea
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    className="w-full px-4 py-2.5 rounded-xl bg-muted/50 border border-border/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 resize-none"
                    placeholder={t('skills.description')}
                    rows={2}
                    required
                  />
                </div>

                {/* Code Editor for Single File Mode */}
                {(skillType === 'langchain_tool' || (skillType === 'agent_skill' && agentSkillMode === 'single')) && (
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-2">
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
                    <div className="flex items-center justify-between mb-2">
                      <label className="block text-sm font-medium text-foreground">
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
                        className="text-sm text-primary hover:text-primary/80 flex items-center gap-1 transition-colors"
                      >
                        <FileCode className="w-4 h-4" />
                        {t('skills.downloadTemplate')}
                      </button>
                    </div>
                    <div className="border-2 border-dashed border-border/50 rounded-xl p-8 text-center hover:border-border transition-colors bg-muted/30">
                      <input
                        type="file"
                        accept=".zip,.tar.gz"
                        onChange={handleFileUpload}
                        className="hidden"
                        id="package-upload"
                        required
                      />
                      <label htmlFor="package-upload" className="cursor-pointer">
                        <Upload className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                        {uploadedFile ? (
                          <div>
                            <p className="text-foreground font-medium mb-1">{uploadedFile.name}</p>
                            <p className="text-sm text-muted-foreground">
                              {(uploadedFile.size / 1024 / 1024).toFixed(2)} MB
                            </p>
                            <button
                              type="button"
                              onClick={() => setUploadedFile(null)}
                              className="mt-2 text-sm text-primary hover:text-primary/80 transition-colors"
                            >
                              {t('skills.reselect')}
                            </button>
                          </div>
                        ) : (
                          <div>
                            <p className="text-foreground mb-1">{t('skills.clickToUpload')}</p>
                            <p className="text-sm text-muted-foreground">{t('skills.supportedFormats')}</p>
                          </div>
                        )}
                      </label>
                    </div>
                    <p className="mt-2 text-xs text-muted-foreground">
                      {t('skills.packageNote')}
                    </p>
                  </div>
                )}
              </div>

              <div className="flex justify-between pt-4 border-t border-border/50">
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
                  className="px-6 py-2.5 rounded-xl bg-muted/50 hover:bg-muted text-foreground transition-colors font-medium"
                  disabled={isSubmitting}
                >
                  {t('skills.previous')}
                </button>
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={handleClose}
                    className="px-6 py-2.5 rounded-xl bg-muted/50 hover:bg-muted text-foreground transition-colors font-medium"
                    disabled={isSubmitting}
                  >
                    {t('skills.cancel')}
                  </button>
                  <button
                    type="submit"
                    className="px-6 py-2.5 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                    disabled={isSubmitting}
                  >
                    {isSubmitting ? t('skills.creating') : t('skills.createSkill')}
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
