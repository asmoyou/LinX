import React, { useState, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Upload, ChevronRight, ChevronLeft, Rocket, FileText, Settings, Eye, Trash2, ChevronDown, ChevronUp } from 'lucide-react';
import toast from 'react-hot-toast';
import { useMissionStore } from '@/stores/missionStore';
import { LayoutModal } from '@/components/LayoutModal';
import { ModalPanel } from '@/components/ModalPanel';
import type { MissionConfig } from '@/types/mission';

interface MissionCreateWizardProps {
  isOpen: boolean;
  onClose: () => void;
}

const STEPS = ['instructions', 'attachments', 'configuration', 'review'] as const;
type Step = typeof STEPS[number];

const stepIcons: Record<Step, React.ElementType> = {
  instructions: FileText,
  attachments: Upload,
  configuration: Settings,
  review: Eye,
};

const LEADING_TITLE_PREFIX_PATTERNS = [
  /^(请你|请帮我|请帮忙|帮我|帮忙|麻烦你|希望你|我需要你|我需要|需要你|需要)\s*/i,
  /^(任务是|需求是|目标是|请完成|完成一下)\s*/i,
  /^(需求|目标|任务)\s*[：:]\s*/i,
];

const stripLeadingTitlePrefix = (value: string): string => {
  let next = value;
  LEADING_TITLE_PREFIX_PATTERNS.forEach((pattern) => {
    next = next.replace(pattern, '').trim();
  });
  return next;
};

const deriveInitialMissionTitle = (instructions: string): string => {
  const normalized = String(instructions || '').replace(/\s+/g, ' ').trim();
  if (!normalized) return 'Untitled Mission';

  const firstSegment = normalized.split(/[。！？.!?;\n]/, 1)[0]?.trim() || '';
  let candidate = stripLeadingTitlePrefix(firstSegment || normalized);
  if (!candidate) {
    candidate = firstSegment || normalized;
  }

  const containsCjk = /[\u4e00-\u9fff]/.test(candidate);
  const maxLength = containsCjk ? 24 : 70;
  if (candidate.length > maxLength) {
    candidate = candidate.slice(0, maxLength).replace(/[ ,;:：。.!?、]+$/g, '');
  }
  return candidate || 'Untitled Mission';
};

export const MissionCreateWizard: React.FC<MissionCreateWizardProps> = ({ isOpen, onClose }) => {
  const { t } = useTranslation();
  const { createMission, startMission, uploadAttachment, missionSettings, fetchMissionSettings } = useMissionStore();
  const [currentStep, setCurrentStep] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Form state
  const [title, setTitle] = useState('');
  const [instructions, setInstructions] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [config, setConfig] = useState<MissionConfig>({
    max_retries: 3,
    task_timeout_s: 600,
    max_rework_cycles: 2,
    max_qa_cycles: 1,
    network_access: false,
    debug_mode: false,
    enable_team_blueprint: true,
    prefer_existing_agents: true,
    allow_temporary_workers: true,
    auto_select_temp_skills: true,
    temp_worker_skill_limit: 3,
    temp_worker_memory_scopes: ['agent', 'company', 'user_context'],
    temp_worker_knowledge_strategy: 'owner_accessible',
    temp_worker_knowledge_limit: 6,
  });
  const autoDerivedTitle = deriveInitialMissionTitle(instructions);
  const effectiveMissionTitle = title.trim() || autoDerivedTitle;

  // Load saved settings as defaults
  useEffect(() => {
    if (isOpen) {
      fetchMissionSettings();
    }
  }, [isOpen, fetchMissionSettings]);

  useEffect(() => {
    if (missionSettings?.execution_config) {
      setConfig((prev) => ({
        ...prev,
        max_retries: missionSettings.execution_config.max_retries ?? prev.max_retries,
        task_timeout_s: missionSettings.execution_config.task_timeout_s ?? prev.task_timeout_s,
        max_rework_cycles: missionSettings.execution_config.max_rework_cycles ?? prev.max_rework_cycles,
        max_qa_cycles: missionSettings.execution_config.max_qa_cycles ?? prev.max_qa_cycles,
        network_access: missionSettings.execution_config.network_access ?? prev.network_access,
        debug_mode: missionSettings.execution_config.debug_mode ?? prev.debug_mode,
        enable_team_blueprint:
          missionSettings.execution_config.enable_team_blueprint ?? prev.enable_team_blueprint,
        prefer_existing_agents:
          missionSettings.execution_config.prefer_existing_agents ?? prev.prefer_existing_agents,
        allow_temporary_workers:
          missionSettings.execution_config.allow_temporary_workers ?? prev.allow_temporary_workers,
        auto_select_temp_skills:
          missionSettings.execution_config.auto_select_temp_skills ?? prev.auto_select_temp_skills,
        temp_worker_skill_limit:
          missionSettings.execution_config.temp_worker_skill_limit ?? prev.temp_worker_skill_limit,
        temp_worker_memory_scopes:
          missionSettings.execution_config.temp_worker_memory_scopes ??
          prev.temp_worker_memory_scopes,
        temp_worker_knowledge_strategy:
          missionSettings.execution_config.temp_worker_knowledge_strategy ??
          prev.temp_worker_knowledge_strategy,
        temp_worker_knowledge_limit:
          missionSettings.execution_config.temp_worker_knowledge_limit ??
          prev.temp_worker_knowledge_limit,
      }));
    }
  }, [missionSettings]);

  const step = STEPS[currentStep];

  const canProceed = useCallback(() => {
    if (step === 'instructions') return instructions.trim().length > 0;
    return true;
  }, [step, instructions]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const droppedFiles = Array.from(e.dataTransfer.files);
    setFiles((prev) => [...prev, ...droppedFiles]);
  }, []);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles((prev) => [...prev, ...Array.from(e.target.files!)]);
    }
  }, []);

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const submitMission = async () => {
    setIsSubmitting(true);
    try {
      const normalizedUserTitle = title.trim();
      const autoGenerateTitle = normalizedUserTitle.length === 0;
      const missionConfig: MissionConfig = {
        ...config,
        auto_generate_title: autoGenerateTitle,
      };
      if (autoGenerateTitle) {
        missionConfig.auto_title_seed = autoDerivedTitle;
      }

      const mission = await createMission({
        title: normalizedUserTitle || effectiveMissionTitle,
        instructions: instructions.trim(),
        mission_config: missionConfig,
      });

      // Upload attachments
      for (const file of files) {
        await uploadAttachment(mission.mission_id, file);
      }

      onClose();
      resetForm();

      // Start mission in background so UI doesn't hang on long-running startup.
      void startMission(mission.mission_id).catch(() => {
        toast.error(t('missions.startFailed'));
      });
    } catch {
      // error handled by store
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSubmit = async () => {
    await submitMission();
  };

  const resetForm = () => {
    setTitle('');
    setInstructions('');
    setFiles([]);
    setConfig({
      max_retries: 3,
      task_timeout_s: 600,
      max_rework_cycles: 2,
      max_qa_cycles: 1,
      network_access: false,
      debug_mode: false,
      enable_team_blueprint: true,
      prefer_existing_agents: true,
      allow_temporary_workers: true,
      auto_select_temp_skills: true,
      temp_worker_skill_limit: 3,
      temp_worker_memory_scopes: ['agent', 'company', 'user_context'],
      temp_worker_knowledge_strategy: 'owner_accessible',
      temp_worker_knowledge_limit: 6,
    });
    setCurrentStep(0);
    setShowAdvanced(false);
  };

  if (!isOpen) return null;

  return (
    <LayoutModal
      isOpen={isOpen}
      onClose={() => {
        onClose();
        resetForm();
      }}
      closeOnBackdropClick={false}
      closeOnEscape={true}
    >
      <ModalPanel className="w-full max-w-2xl flex flex-col max-h-[calc(100vh-var(--app-header-height,4rem)-3rem)]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-200 dark:border-zinc-700">
          <div className="flex items-center gap-2">
            <Rocket className="w-5 h-5 text-emerald-500" />
            <h2 className="text-lg font-bold text-zinc-800 dark:text-zinc-100">
              {t('missions.create')}
            </h2>
          </div>
          <button
            onClick={() => { onClose(); resetForm(); }}
            className="p-1.5 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-zinc-500" />
          </button>
        </div>

        {/* Step indicator */}
        <div className="flex items-center px-6 py-3 border-b border-zinc-100 dark:border-zinc-800 gap-1">
          {STEPS.map((s, i) => {
            const Icon = stepIcons[s];
            const isActive = i === currentStep;
            const isDone = i < currentStep;
            return (
              <React.Fragment key={s}>
                <button
                  onClick={() => i < currentStep && setCurrentStep(i)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                    isActive
                      ? 'bg-emerald-500/10 text-emerald-600'
                      : isDone
                        ? 'bg-emerald-50 text-emerald-500 cursor-pointer'
                        : 'text-zinc-400'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {t(`missions.${s}`)}
                </button>
                {i < STEPS.length - 1 && (
                  <ChevronRight className="w-3.5 h-3.5 text-zinc-300" />
                )}
              </React.Fragment>
            );
          })}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {step === 'instructions' && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
                  {t('missions.fieldTitleOptional', '标题（可选）')}
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder={t('missions.titlePlaceholder')}
                  className="w-full rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 px-4 py-2.5 text-sm text-zinc-800 dark:text-zinc-200 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
                />
                <p className="mt-1 text-xs text-zinc-500">
                  {t('missions.autoGenerateTitleHint', '留空时会根据需求自动填充初始标题')}
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">
                  {t('missions.instructions')}
                </label>
                <textarea
                  value={instructions}
                  onChange={(e) => setInstructions(e.target.value)}
                  placeholder={t('missions.instructionsPlaceholder')}
                  rows={8}
                  className="w-full rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 px-4 py-2.5 text-sm text-zinc-800 dark:text-zinc-200 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/30 resize-none"
                />
              </div>
            </div>
          )}

          {step === 'attachments' && (
            <div className="space-y-4">
              <div
                onDrop={handleDrop}
                onDragOver={(e) => e.preventDefault()}
                className="border-2 border-dashed border-zinc-300 dark:border-zinc-600 rounded-xl p-8 text-center hover:border-emerald-400 transition-colors cursor-pointer"
                onClick={() => document.getElementById('file-upload')?.click()}
              >
                <Upload className="w-8 h-8 text-zinc-400 mx-auto mb-2" />
                <p className="text-sm text-zinc-600 dark:text-zinc-400">
                  {t('missions.dropFilesHere')}
                </p>
                <p className="text-xs text-zinc-400 mt-1">
                  {t('missions.fileTypesHint')}
                </p>
                <input
                  id="file-upload"
                  type="file"
                  multiple
                  className="hidden"
                  onChange={handleFileSelect}
                />
              </div>

              {files.length > 0 && (
                <div className="space-y-2">
                  {files.map((file, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-3 p-3 rounded-lg border border-zinc-200 dark:border-zinc-700"
                    >
                      <FileText className="w-4 h-4 text-zinc-400" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-zinc-800 dark:text-zinc-200 truncate">
                          {file.name}
                        </p>
                        <p className="text-[10px] text-zinc-400">
                          {(file.size / 1024).toFixed(1)} KB
                        </p>
                      </div>
                      <button
                        onClick={() => removeFile(i)}
                        className="p-1 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg transition-colors"
                      >
                        <Trash2 className="w-3.5 h-3.5 text-red-500" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {step === 'configuration' && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-zinc-500 mb-1">
                    {t('missions.maxRetries')}
                  </label>
                  <input
                    type="number"
                    value={config.max_retries ?? 3}
                    onChange={(e) => setConfig({ ...config, max_retries: parseInt(e.target.value) || 0 })}
                    min={0}
                    max={10}
                    className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 px-3 py-2 text-sm text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-zinc-500 mb-1">
                    {t('missions.taskTimeout')}
                  </label>
                  <input
                    type="number"
                    value={config.task_timeout_s ?? 600}
                    onChange={(e) => setConfig({ ...config, task_timeout_s: parseInt(e.target.value) || 0 })}
                    min={60}
                    max={3600}
                    step={60}
                    className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 px-3 py-2 text-sm text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-zinc-500 mb-1">
                    {t('missions.maxReworkCycles')}
                  </label>
                  <input
                    type="number"
                    value={config.max_rework_cycles ?? 2}
                    onChange={(e) => setConfig({ ...config, max_rework_cycles: parseInt(e.target.value) || 0 })}
                    min={0}
                    max={5}
                    className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 px-3 py-2 text-sm text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-zinc-500 mb-1">
                    {t('missions.maxQaCycles')}
                  </label>
                  <input
                    type="number"
                    value={config.max_qa_cycles ?? 1}
                    onChange={(e) => setConfig({ ...config, max_qa_cycles: parseInt(e.target.value) || 0 })}
                    min={0}
                    max={5}
                    className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 px-3 py-2 text-sm text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
                  />
                </div>
                <div className="flex items-center gap-3 pt-5">
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={config.network_access ?? false}
                      onChange={(e) => setConfig({ ...config, network_access: e.target.checked })}
                      className="sr-only peer"
                    />
                    <div className="w-9 h-5 bg-zinc-200 dark:bg-zinc-700 peer-focus:ring-2 peer-focus:ring-emerald-500/30 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-500" />
                  </label>
                  <span className="text-xs font-medium text-zinc-500">{t('missions.networkAccess')}</span>
                </div>
                <div className="flex items-center gap-3 pt-5">
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={config.debug_mode ?? false}
                      onChange={(e) => setConfig({ ...config, debug_mode: e.target.checked })}
                      className="sr-only peer"
                    />
                    <div className="w-9 h-5 bg-zinc-200 dark:bg-zinc-700 peer-focus:ring-2 peer-focus:ring-emerald-500/30 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-500" />
                  </label>
                  <span className="text-xs font-medium text-zinc-500">{t('missions.debugMode')}</span>
                </div>
              </div>

              {/* Advanced role configuration */}
              {missionSettings && (
                <div className="border border-zinc-200 dark:border-zinc-700 rounded-xl overflow-hidden mt-4">
                  <button
                    onClick={() => setShowAdvanced(!showAdvanced)}
                    className="w-full flex items-center justify-between px-4 py-2.5 bg-zinc-50 dark:bg-zinc-800/50 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
                  >
                    <span className="text-xs font-semibold text-zinc-500">
                      {t('missions.advancedConfig')}
                    </span>
                    {showAdvanced ? (
                      <ChevronUp className="w-3.5 h-3.5 text-zinc-400" />
                    ) : (
                      <ChevronDown className="w-3.5 h-3.5 text-zinc-400" />
                    )}
                  </button>
                  {showAdvanced && (
                    <div className="p-4 space-y-3">
                      {[
                        { label: t('missions.leader'), config: missionSettings.leader_config },
                        { label: t('missions.supervisor'), config: missionSettings.supervisor_config },
                        { label: t('missions.qaAuditor'), config: missionSettings.qa_config },
                        {
                          label: t('missions.temporaryWorker'),
                          config: missionSettings.temporary_worker_config,
                        },
                      ].map(({ label, config: roleConfig }) => (
                        <div key={label} className="flex items-center justify-between text-xs text-zinc-500 py-1.5 border-b border-zinc-100 dark:border-zinc-800 last:border-0">
                          <span className="font-medium text-zinc-600 dark:text-zinc-400">{label}</span>
                          <span>
                            {roleConfig.llm_provider && roleConfig.llm_model
                              ? `${roleConfig.llm_provider} / ${roleConfig.llm_model} (T: ${roleConfig.temperature})`
                              : t('missions.notConfigured')}
                          </span>
                        </div>
                      ))}
                      <p className="text-[10px] text-zinc-400 mt-1">
                        {t('missions.settingsDescription')}
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {step === 'review' && (
            <div className="space-y-4">
              <div className="p-4 rounded-xl bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700">
                <h4 className="text-xs font-semibold text-zinc-500 uppercase mb-2">{t('missions.fieldTitle')}</h4>
                <p className="text-sm text-zinc-800 dark:text-zinc-200">
                  {effectiveMissionTitle || t('missions.autoGenerateTitlePending', '将自动填充标题')}
                </p>
              </div>
              <div className="p-4 rounded-xl bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700">
                <h4 className="text-xs font-semibold text-zinc-500 uppercase mb-2">{t('missions.instructions')}</h4>
                <p className="text-sm text-zinc-800 dark:text-zinc-200 whitespace-pre-wrap">{instructions}</p>
              </div>
              {files.length > 0 && (
                <div className="p-4 rounded-xl bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700">
                  <h4 className="text-xs font-semibold text-zinc-500 uppercase mb-2">
                    {t('missions.attachments')} ({files.length})
                  </h4>
                  <ul className="text-sm text-zinc-600 dark:text-zinc-400 space-y-1">
                    {files.map((f, i) => (
                      <li key={i} className="flex items-center gap-2">
                        <FileText className="w-3.5 h-3.5" />
                        {f.name}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="p-4 rounded-xl bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700">
                <h4 className="text-xs font-semibold text-zinc-500 uppercase mb-2">{t('missions.configuration')}</h4>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <span className="text-zinc-500">{t('missions.maxRetries')}:</span>
                  <span className="text-zinc-800 dark:text-zinc-200">{config.max_retries}</span>
                  <span className="text-zinc-500">{t('missions.timeoutShort')}:</span>
                  <span className="text-zinc-800 dark:text-zinc-200">{config.task_timeout_s}s</span>
                  <span className="text-zinc-500">{t('missions.reworkCyclesShort')}:</span>
                  <span className="text-zinc-800 dark:text-zinc-200">{config.max_rework_cycles}</span>
                  <span className="text-zinc-500">{t('missions.qaCyclesShort')}:</span>
                  <span className="text-zinc-800 dark:text-zinc-200">{config.max_qa_cycles}</span>
                  <span className="text-zinc-500">{t('missions.networkShort')}:</span>
                  <span className="text-zinc-800 dark:text-zinc-200">
                    {config.network_access ? t('missions.yes') : t('missions.no')}
                  </span>
                  <span className="text-zinc-500">{t('missions.debugShort')}:</span>
                  <span className="text-zinc-800 dark:text-zinc-200">
                    {config.debug_mode ? t('missions.yes') : t('missions.no')}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-zinc-200 dark:border-zinc-700">
          <button
            onClick={() => currentStep > 0 ? setCurrentStep(currentStep - 1) : (onClose(), resetForm())}
            className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
            {currentStep > 0 ? t('missions.back') : t('missions.cancel')}
          </button>

          {currentStep < STEPS.length - 1 ? (
            <div className="flex items-center gap-2">
              {currentStep === 0 && (
                <button
                  onClick={handleSubmit}
                  disabled={!canProceed() || isSubmitting}
                  className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-500/10 hover:bg-emerald-100 dark:hover:bg-emerald-500/20 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
                >
                  <Rocket className="w-4 h-4" />
                  {isSubmitting ? t('missions.creating') : t('missions.quickStart')}
                </button>
              )}
              <button
                onClick={() => setCurrentStep(currentStep + 1)}
                disabled={!canProceed() || isSubmitting}
                className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
              >
                {t('missions.next')}
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <button
              onClick={handleSubmit}
              disabled={isSubmitting}
              className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
            >
              <Rocket className="w-4 h-4" />
              {isSubmitting ? t('missions.creating') : t('missions.start')}
            </button>
          )}
        </div>
      </ModalPanel>
    </LayoutModal>
  );
};
