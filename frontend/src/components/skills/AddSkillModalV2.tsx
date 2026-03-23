import { X, Upload, FileCode } from 'lucide-react';
import { useEffect, useState } from 'react';
import CodeEditor from './CodeEditor';
import DependencyTagsInput from './DependencyTagsInput';
import SkillTypeSelector, { type SkillType } from './SkillTypeSelector';
import TemplateSelector from './TemplateSelector';
import { skillsApi, type SkillAccessLevel, type SkillShareTargetsResponse } from '@/api/skills';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { LayoutModal } from '@/components/LayoutModal';

interface AddSkillModalV2Props {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: any) => Promise<void>;
}

export default function AddSkillModalV2({ isOpen, onClose, onSubmit }: AddSkillModalV2Props) {
  const { t } = useTranslation();
  const [step, setStep] = useState<'type' | 'template' | 'code'>('type');
  const [skillType, setSkillType] = useState<SkillType>('langchain_tool');
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [shareTargets, setShareTargets] = useState<SkillShareTargetsResponse | null>(null);
  
  const [formData, setFormData] = useState({
    display_name: '',
    skill_slug: '',
    description: '',
    code: '',
    dependencies: [] as string[],
    access_level: 'private' as SkillAccessLevel,
    department_id: '',
  });

  useEffect(() => {
    if (!isOpen) return;
    void skillsApi.getShareTargets().then(setShareTargets).catch((error) => {
      console.error('Failed to load skill share targets:', error);
      setShareTargets(null);
    });
  }, [isOpen]);

  if (!isOpen) return null;

  const handleClose = () => {
    setStep('type');
    setSkillType('langchain_tool');
    setSelectedTemplate(null);
    setUploadedFile(null);
    setIsDragging(false);
    setFormData({
      display_name: '',
      skill_slug: '',
      description: '',
      code: '',
      dependencies: [],
      access_level: 'private',
      department_id: shareTargets?.default_department_id || '',
    });
    onClose();
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setUploadedFile(file);
      // Auto-fill name from filename
      if (!formData.display_name) {
        const nameWithoutExt = file.name.replace(/\.(zip|tar\.gz)$/, '');
        setFormData({ ...formData, display_name: nameWithoutExt });
      }
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const file = e.dataTransfer.files?.[0];
    if (file) {
      // Check file type
      const validTypes = ['.zip', '.tar.gz'];
      const isValid = validTypes.some(type => file.name.toLowerCase().endsWith(type));
      
      if (!isValid) {
        toast.error('Please upload a ZIP or TAR.GZ file.', {
          duration: 4000,
        });
        return;
      }

      setUploadedFile(file);
      // Auto-fill name from filename
      if (!formData.display_name) {
        const nameWithoutExt = file.name.replace(/\.(zip|tar\.gz)$/, '');
        setFormData({ ...formData, display_name: nameWithoutExt });
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Manual validation for agent_skill file upload
    if (skillType === 'agent_skill' && !uploadedFile) {
      toast.error(t('skills.pleaseUploadPackage'), {
        duration: 4000,
      });
      return;
    }

    if (skillType === 'langchain_tool' && !formData.description.trim()) {
      toast.error(t('skills.descriptionRequired', 'Description is required'), {
        duration: 4000,
      });
      return;
    }
    
    setIsSubmitting(true);
    
    try {
      const submitData: any = {
        display_name: formData.display_name,
        skill_slug: formData.skill_slug || undefined,
        skill_type: skillType,
        access_level: formData.access_level,
        department_id:
          formData.access_level === 'team'
            ? (formData.department_id || shareTargets?.default_department_id || undefined)
            : undefined,
      };

      if (skillType === 'langchain_tool') {
        submitData.description = formData.description.trim();
        submitData.code = formData.code;
        submitData.dependencies = formData.dependencies;
      }

      // For agent skills, include file upload (required)
      if (skillType === 'agent_skill' && uploadedFile) {
        submitData.package_file = uploadedFile;
      }

      await onSubmit(submitData);
      handleClose();
    } catch (error) {
      console.error('Failed to create skill:', error);
      // Error notification is handled by apiClient interceptor
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <LayoutModal
      isOpen={isOpen}
      onClose={handleClose}
      closeOnBackdropClick={false}
      closeOnEscape={true}
    >
      <div className="w-full max-w-4xl max-h-[calc(100vh-var(--app-header-height,4rem)-3rem)] overflow-y-auto modal-panel rounded-[24px] shadow-2xl p-6">
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
              
              <div className="flex justify-end pt-4">
                <button
                  type="button"
                  onClick={() => {
                    // Agent skill skips template selection (always package upload)
                    if (skillType === 'agent_skill') {
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
                    value={formData.display_name}
                    onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
                    className="w-full px-4 py-2.5 rounded-xl glass text-gray-800 dark:text-white placeholder:text-gray-500 dark:placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                    placeholder="e.g., My Custom Skill"
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-800 dark:text-white mb-2">
                    {t('skills.skillSlug', { defaultValue: 'Skill Slug' })}
                  </label>
                  <input
                    type="text"
                    value={formData.skill_slug}
                    onChange={(e) => setFormData({ ...formData, skill_slug: e.target.value })}
                    className="w-full px-4 py-2.5 rounded-xl glass text-gray-800 dark:text-white placeholder:text-gray-500 dark:placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 font-mono"
                    placeholder="e.g., my_custom_skill"
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-800 dark:text-white mb-2">
                      {t('skills.visibility', { defaultValue: 'Visibility' })}
                    </label>
                    <select
                      value={formData.access_level}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          access_level: e.target.value as SkillAccessLevel,
                          department_id:
                            e.target.value === 'team'
                              ? (formData.department_id || shareTargets?.default_department_id || '')
                              : '',
                        })
                      }
                      className="w-full px-4 py-2.5 rounded-xl glass text-gray-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                    >
                      <option value="private">
                        {t('skills.private', { defaultValue: 'Private' })}
                      </option>
                      <option value="team">
                        {t('skills.team', { defaultValue: 'Team' })}
                      </option>
                      {shareTargets?.can_publish_public && (
                        <option value="public">
                          {t('skills.public', { defaultValue: 'Public' })}
                        </option>
                      )}
                    </select>
                  </div>

                  {formData.access_level === 'team' && (
                    <div>
                      <label className="block text-sm font-medium text-gray-800 dark:text-white mb-2">
                        {t('skills.department', { defaultValue: 'Department' })}
                      </label>
                      <select
                        value={formData.department_id || shareTargets?.default_department_id || ''}
                        onChange={(e) =>
                          setFormData({ ...formData, department_id: e.target.value })
                        }
                        className="w-full px-4 py-2.5 rounded-xl glass text-gray-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                      >
                        {(shareTargets?.allowed_department_targets || []).map((target) => (
                          <option key={target.department_id} value={target.department_id}>
                            {target.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>

                {skillType === 'langchain_tool' && (
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
                )}

                {/* Code Editor for LangChain Tool */}
                {skillType === 'langchain_tool' && (
                  <>
                    <div>
                      <label className="block text-sm font-medium text-gray-800 dark:text-white mb-2">
                        {t('skills.pythonCode')} *
                      </label>
                      <CodeEditor
                        value={formData.code}
                        onChange={(value) => setFormData({ ...formData, code: value })}
                        height="400px"
                        placeholder={`from langchain_core.tools import tool

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
`}
                      />
                    </div>
                    
                    {/* Dependencies Field */}
                    <div>
                      <label className="block text-sm font-medium text-gray-800 dark:text-white mb-2">
                        {t('skills.dependencies')}
                      </label>
                      <DependencyTagsInput
                        values={formData.dependencies}
                        onChange={(dependencies) =>
                          setFormData({
                            ...formData,
                            dependencies,
                          })
                        }
                        placeholder={t('skills.dependenciesPlaceholder')}
                        helperText={t('skills.dependenciesHint')}
                      />
                    </div>
                  </>
                )}

                {/* File Upload for Agent Skill (Package Only) */}
                {skillType === 'agent_skill' && (
                  <div>
                    <div className="mb-3 text-sm text-gray-700 dark:text-gray-300">
                      {t(
                        'skills.agentSkillDescriptionFromSkillMd',
                        'Description will be parsed from SKILL.md automatically.'
                      )}
                    </div>
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
                            toast.error(t('skills.downloadFailed'), {
                              duration: 4000,
                            });
                          }
                        }}
                        className="text-sm text-indigo-500 hover:text-indigo-600 dark:text-indigo-400 dark:hover:text-indigo-300 flex items-center gap-1.5 transition-all duration-300 hover:gap-2 font-medium"
                      >
                        <FileCode className="w-4 h-4" />
                        {t('skills.downloadTemplate')}
                      </button>
                    </div>
                    <div 
                      className={`border-2 border-dashed rounded-xl p-10 text-center transition-all duration-300 glass ${
                        isDragging 
                          ? 'border-indigo-500 bg-indigo-500/10 scale-[1.02]' 
                          : 'border-gray-300 dark:border-gray-600 hover:border-indigo-500 hover:bg-indigo-500/5'
                      }`}
                      onDragOver={handleDragOver}
                      onDragLeave={handleDragLeave}
                      onDrop={handleDrop}
                    >
                      <input
                        type="file"
                        accept=".zip,.tar.gz"
                        onChange={handleFileUpload}
                        className="hidden"
                        id="package-upload"
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
                            <div className={`w-16 h-16 rounded-full flex items-center justify-center mx-auto transition-colors ${
                              isDragging 
                                ? 'bg-indigo-500/20' 
                                : 'bg-gray-100 dark:bg-gray-800'
                            }`}>
                              <Upload className={`w-8 h-8 transition-colors ${
                                isDragging 
                                  ? 'text-indigo-500' 
                                  : 'text-gray-600 dark:text-gray-400'
                              }`} />
                            </div>
                            <div>
                              <p className="text-gray-800 dark:text-white font-medium mb-1">
                                {isDragging ? t('skills.dropHere') : t('skills.clickToUpload')}
                              </p>
                              <p className="text-sm text-gray-600 dark:text-gray-400">{t('skills.supportedFormats')}</p>
                            </div>
                          </div>
                        )}
                      </label>
                    </div>
                    <div className="mt-3 p-4 rounded-lg bg-purple-500/10 border border-purple-500/20 space-y-2">
                      <p className="text-sm font-semibold text-gray-800 dark:text-white">
                        📦 Package Structure:
                      </p>
                      <div className="text-xs text-gray-700 dark:text-gray-300 font-mono space-y-1 pl-4">
                        <div>├── SKILL.md (required - skill definition)</div>
                        <div>├── README.md (optional - documentation)</div>
                        <div>├── requirements.txt (optional - Python deps)</div>
                        <div>├── scripts/ (optional - executable scripts)</div>
                        <div>│   ├── helper.py</div>
                        <div>│   └── utils.py</div>
                        <div>└── references/ (optional - reference docs)</div>
                      </div>
                      <p className="text-xs text-gray-600 dark:text-gray-400 pt-2">
                        💡 SKILL.md = Instructions + Executable Code (scripts/src/)
                      </p>
                      <p className="text-xs text-gray-600 dark:text-gray-400">
                        🔧 Use {'{baseDir}'} placeholder for script paths
                      </p>
                    </div>
                  </div>
                )}
              </div>

              <div className="flex justify-between pt-6 border-t border-zinc-200 dark:border-zinc-700">
                <button
                  type="button"
                  onClick={() => {
                    // Agent skill goes back to type selection (skips template)
                    if (skillType === 'agent_skill') {
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
    </LayoutModal>
  );
}
