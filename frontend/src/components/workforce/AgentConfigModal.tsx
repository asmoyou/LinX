import React, { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import {
  X,
  Save,
  Loader2,
  AlertCircle,
  Info,
  Bot,
  Link as LinkIcon,
  Power,
  Radio,
  RefreshCw,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import toast from "react-hot-toast";
import type { Agent, AgentSkillSummary, ExternalRuntimeOverview, FeishuPublicationConfig } from "@/types/agent";
import { llmApi, agentsApi } from "@/api";
import {
  skillsApi,
  type AgentSkillBindingDraft,
  type AgentSkillBindingMode,
} from "@/api/skills";
import { knowledgeApi } from "@/api/knowledge";
import type { SaveFeishuPublicationRequest } from "@/api/agents";
import type { ModelMetadata } from "@/api/llm";
import type { Collection } from "@/types/document";
import { ModelMetadataCard } from "@/components/settings/ModelMetadataCard";
import { ImageCropModal } from "@/components/common/ImageCropModal";
import { LayoutModal } from "@/components/LayoutModal";
import { getAgentKind } from "@/utils/agentPresentation";

const resolveDefaultBindingMode = (
  skill: AgentSkillSummary,
): AgentSkillBindingMode => {
  const runtimeMode = String(skill.runtime_mode || "").trim().toLowerCase();
  if (
    runtimeMode === "tool" ||
    runtimeMode === "doc" ||
    runtimeMode === "retrieval" ||
    runtimeMode === "hybrid"
  ) {
    return runtimeMode as AgentSkillBindingMode;
  }
  return skill.skill_type === "langchain_tool" || skill.skill_type === "mcp_tool" ? "tool" : "doc";
};

const buildDefaultBinding = (
  skill: AgentSkillSummary,
  priority: number,
): AgentSkillBindingDraft => ({
  skill_id: skill.skill_id,
  binding_mode: resolveDefaultBindingMode(skill),
  enabled: true,
  priority,
  source: "manual",
  auto_update_policy: "follow_active",
  revision_pin_id: null,
});

const bindingModeOptionsForSkill = (
  skill: AgentSkillSummary,
): AgentSkillBindingMode[] => {
  const runtimeMode = resolveDefaultBindingMode(skill);
  if (runtimeMode === "hybrid") {
    return ["tool", "doc", "retrieval", "hybrid"];
  }
  return [runtimeMode];
};

interface AgentConfigModalProps {
  agent: Agent | null;
  isOpen: boolean;
  initialTab?: "basic" | "runtime" | "capabilities" | "model" | "knowledge" | "access" | "channels";
  onClose: () => void;
  onSave: (agent: Agent, bindings: AgentSkillBindingDraft[]) => Promise<void>;
}

export const AgentConfigModal: React.FC<AgentConfigModalProps> = ({
  agent,
  isOpen,
  initialTab = "basic",
  onClose,
  onSave,
}) => {
  const { t, i18n } = useTranslation();
  const [activeTab, setActiveTab] = useState<
    "basic" | "runtime" | "capabilities" | "model" | "knowledge" | "access" | "channels"
  >("basic");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isLoadingProviders, setIsLoadingProviders] = useState(false);
  const [availableProviders, setAvailableProviders] = useState<
    Record<string, string[]>
  >({});
  const [providersError, setProvidersError] = useState<string | null>(null);
  const [modelMetadata, setModelMetadata] = useState<ModelMetadata | null>(
    null,
  );
  const [isLoadingMetadata, setIsLoadingMetadata] = useState(false);
  const [isAvatarCropModalOpen, setIsAvatarCropModalOpen] = useState(false);
  const [avatarPreview, setAvatarPreview] = useState<string>(""); // presigned URL for display
  const [availableKnowledgeBases, setAvailableKnowledgeBases] = useState<
    Collection[]
  >([]);
  const [isLoadingKnowledgeBases, setIsLoadingKnowledgeBases] = useState(false);
  const [knowledgeBasesError, setKnowledgeBasesError] = useState<string | null>(
    null,
  );

  // Skills state
  const [availableSkills, setAvailableSkills] = useState<AgentSkillSummary[]>(
    [],
  );
  const [skillBindings, setSkillBindings] = useState<AgentSkillBindingDraft[]>(
    [],
  );
  const [isLoadingSkills, setIsLoadingSkills] = useState(false);
  const [skillsError, setSkillsError] = useState<string | null>(null);
  const [showAdvancedSkillBindings, setShowAdvancedSkillBindings] =
    useState(false);
  const [feishuPublication, setFeishuPublication] =
    useState<FeishuPublicationConfig | null>(null);
  const [feishuFormData, setFeishuFormData] =
    useState<SaveFeishuPublicationRequest>({
      appId: "",
      appSecret: "",
    });
  const [isLoadingFeishuPublication, setIsLoadingFeishuPublication] =
    useState(false);
  const [isSavingFeishuPublication, setIsSavingFeishuPublication] =
    useState(false);
  const [feishuError, setFeishuError] = useState<string | null>(null);
  const [externalRuntimeOverview, setExternalRuntimeOverview] = useState<ExternalRuntimeOverview | null>(null);
  const [isLoadingExternalRuntime, setIsLoadingExternalRuntime] = useState(false);
  const [externalRuntimeTarget, setExternalRuntimeTarget] = useState<"linux" | "darwin" | "windows">("linux");
  const [externalPathAllowlist, setExternalPathAllowlist] = useState("");
  const [externalLaunchCommandTemplate, setExternalLaunchCommandTemplate] = useState("");
  const [installCommand, setInstallCommand] = useState("");
  const [installCommandExpiresAt, setInstallCommandExpiresAt] = useState<string | null>(null);
  const [maintenanceCommand, setMaintenanceCommand] = useState("");
  const [maintenanceCommandLabel, setMaintenanceCommandLabel] = useState("");
  const [isGeneratingInstallCommand, setIsGeneratingInstallCommand] = useState(false);
  const [isGeneratingUpdateCommand, setIsGeneratingUpdateCommand] = useState(false);
  const [isGeneratingUninstallCommand, setIsGeneratingUninstallCommand] = useState(false);
  const [isRequestingRuntimeUpdate, setIsRequestingRuntimeUpdate] = useState(false);
  const [isRequestingRuntimeUninstall, setIsRequestingRuntimeUninstall] = useState(false);
  const [isSavingExternalRuntimeProfile, setIsSavingExternalRuntimeProfile] = useState(false);

  const [formData, setFormData] = useState<Partial<Agent>>({
    name: "",
    type: "",
    avatar: "",
    systemPrompt: "",
    model: "",
    provider: "",
    temperature: 0.7,
    maxTokens: 4096,
    topP: 0.9,
    departmentId: "",
    accessLevel: "private",
    allowedKnowledge: [],
    topK: 5,
    similarityThreshold: 0.3,
    runtimeType: "project_sandbox",
    projectScopeId: "",
  });

  const agentKind = getAgentKind({
    runtimeType: String(formData.runtimeType || agent?.runtimeType || "project_sandbox"),
  } as Agent);

  // Initialize form data when agent changes
  useEffect(() => {
    console.log("[AgentConfigModal] Agent or isOpen changed:", {
      agent,
      isOpen,
    });
    if (agent && isOpen) {
      console.log(
        "[AgentConfigModal] Initializing form with agent data:",
        agent,
      );
      setFormData({
        name: agent.name || "",
        type: agent.type || "",
        avatar: agent.avatar || "",
        systemPrompt: agent.systemPrompt || "",
        model: agent.model || "",
        provider: agent.provider || "",
        temperature: agent.temperature ?? 0.7,
        maxTokens: agent.maxTokens ?? 4096,
        topP: agent.topP ?? 0.9,
        departmentId: agent.departmentId || "",
        accessLevel:
          agent.accessLevel === "team"
            ? ("department" as any)
            : agent.accessLevel || "private",
        allowedKnowledge: agent.allowedKnowledge || [],
        topK: agent.topK || 5,
        similarityThreshold: agent.similarityThreshold ?? 0.3,
        runtimeType: agent.runtimeType || "project_sandbox",
        projectScopeId: agent.projectScopeId || "",
      });
      setSkillBindings([]);
      setShowAdvancedSkillBindings(false);
      setAvatarPreview(agent.avatar || "");
      setSaveError(null);
      setModelMetadata(null);
      setActiveTab(initialTab);
      setInstallCommand("");
      setInstallCommandExpiresAt(null);
      setMaintenanceCommand("");
      setMaintenanceCommandLabel("");
    }
  }, [agent, initialTab, isOpen]);

  // Fetch available providers and models
  useEffect(() => {
    if (isOpen) {
      fetchAvailableProviders();
      fetchAvailableSkills();
      fetchKnowledgeBases();
      void fetchFeishuPublication();
      void loadExternalRuntimeOverview();
    }
  }, [isOpen, agent?.id, agentKind]);

  useEffect(() => {
    if (
      !isOpen ||
      activeTab !== "channels" ||
      !agent?.id ||
      feishuPublication?.status !== "published"
    ) {
      return;
    }

    const pollIntervalMs =
      getFeishuConnectionState(feishuPublication) === "connecting"
        ? 1000
        : 5000;
    const timer = window.setInterval(() => {
      void fetchFeishuPublication({ silent: true });
    }, pollIntervalMs);

    return () => window.clearInterval(timer);
  }, [
    activeTab,
    agent?.id,
    feishuPublication?.connectionState,
    feishuPublication?.status,
    isOpen,
  ]);

  // Fetch model metadata when provider and model are selected
  // Only fetch if both are set and not empty, and not currently loading
  useEffect(() => {
    if (isOpen && formData.provider && formData.model && !isLoadingMetadata) {
      fetchModelMetadata(formData.provider, formData.model);
    } else if (!formData.provider || !formData.model) {
      setModelMetadata(null);
    }
  }, [isOpen, formData.provider, formData.model]);

  const fetchAvailableProviders = async () => {
    console.log("[AgentConfigModal] Fetching available providers...");
    setIsLoadingProviders(true);
    setProvidersError(null);
    try {
      const response = await llmApi.getAvailableProviders();
      console.log("[AgentConfigModal] Available providers loaded:", response);
      setAvailableProviders(response);

      // DON'T auto-select provider/model - this was causing the bug!
      // The agent's existing configuration should be preserved
      // formData is already initialized from agent prop in the useEffect above
    } catch (error: any) {
      console.error("Failed to fetch available providers:", error);
      const errorMsg =
        error.response?.data?.message ||
        error.message ||
        "Failed to load available providers";
      setProvidersError(`${errorMsg}. Please check your LLM configuration.`);
    } finally {
      setIsLoadingProviders(false);
    }
  };

  const fetchKnowledgeBases = async () => {
    setIsLoadingKnowledgeBases(true);
    setKnowledgeBasesError(null);
    try {
      const pageSize = 100;
      let page = 1;
      let total = Number.POSITIVE_INFINITY;
      const allCollections: Collection[] = [];

      while (allCollections.length < total) {
        const response = await knowledgeApi.getCollections({
          page,
          page_size: pageSize,
        });
        allCollections.push(...response.collections);
        total = response.total;
        if (response.collections.length < pageSize) {
          break;
        }
        page += 1;
      }

      allCollections.sort((a, b) => a.name.localeCompare(b.name));
      setAvailableKnowledgeBases(allCollections);
    } catch (error: any) {
      console.error("Failed to fetch knowledge collections:", error);
      const errorMsg =
        error.response?.data?.detail ||
        error.response?.data?.message ||
        error.message ||
        "Failed to load knowledge bases";
      setKnowledgeBasesError(errorMsg);
      setAvailableKnowledgeBases([]);
    } finally {
      setIsLoadingKnowledgeBases(false);
    }
  };

  const fetchAvailableSkills = async () => {
    if (!agent?.id) return;

    console.log("[AgentConfigModal] Fetching available skills...");
    setIsLoadingSkills(true);
    setSkillsError(null);
    try {
      const response = await skillsApi.getAgentBindings(agent.id);
      console.log("[AgentConfigModal] Skills loaded:", response);
      setAvailableSkills(response.available_skills || []);
      setSkillBindings(
        (response.bindings || []).sort((left, right) => left.priority - right.priority),
      );
    } catch (error: any) {
      console.error("Failed to fetch available skills:", error);
      const errorMsg =
        error.response?.data?.message ||
        error.message ||
        "Failed to load skills";
      setSkillsError(errorMsg);
    } finally {
      setIsLoadingSkills(false);
    }
  };

  const fetchFeishuPublication = async ({
    silent = false,
  }: { silent?: boolean } = {}) => {
    if (!agent?.id) return;
    if (!silent) {
      setIsLoadingFeishuPublication(true);
      setFeishuError(null);
    }
    try {
      const publication = await agentsApi.getFeishuPublication(agent.id);
      setFeishuPublication(publication);
      setFeishuFormData((prev) => {
        const hasUnsavedChanges =
          trimFeishuAppId(prev.appId) !==
            trimFeishuAppId(feishuPublication?.appId || "") ||
          Boolean(prev.appSecret?.trim());
        if (silent && hasUnsavedChanges) {
          return prev;
        }
        return {
          appId: publication.appId || "",
          appSecret: "",
        };
      });
    } catch (error: any) {
      console.error("Failed to fetch Feishu publication:", error);
      if (!silent) {
        setFeishuError(
          error.response?.data?.detail ||
            error.message ||
            t("agent.feishuLoadFailed", "Failed to load Feishu publication"),
        );
        setFeishuPublication(null);
      }
    } finally {
      if (!silent) {
        setIsLoadingFeishuPublication(false);
      }
    }
  };

  const toggleSkill = (skillId: string) => {
    const selectedBinding = skillBindings.find(
      (binding) => binding.skill_id === skillId,
    );
    if (selectedBinding) {
      setSkillBindings((currentBindings) =>
        currentBindings.filter((binding) => binding.skill_id !== skillId),
      );
      return;
    }

    const skill = availableSkills.find((item) => item.skill_id === skillId);
    if (!skill) {
      return;
    }
    setSkillBindings((currentBindings) => [
      ...currentBindings,
      buildDefaultBinding(skill, currentBindings.length),
    ]);
  };

  const toggleKnowledgeBase = (collectionId: string) => {
    const selected = formData.allowedKnowledge || [];
    const nextSelected = selected.includes(collectionId)
      ? selected.filter((id) => id !== collectionId)
      : [...selected, collectionId];
    setFormData({
      ...formData,
      allowedKnowledge: nextSelected,
    });
  };

  const updateSkillBinding = (
    skillId: string,
    updater: (binding: AgentSkillBindingDraft) => AgentSkillBindingDraft,
  ) => {
    setSkillBindings((currentBindings) =>
      currentBindings
        .map((binding) =>
          binding.skill_id === skillId ? updater(binding) : binding,
        )
        .sort((left, right) => left.priority - right.priority),
    );
  };

  const fetchModelMetadata = async (provider: string, model: string) => {
    // Prevent duplicate requests
    if (isLoadingMetadata) {
      console.log(
        "[AgentConfigModal] Skipping metadata fetch - already loading",
      );
      return;
    }

    console.log(
      `[AgentConfigModal] Fetching metadata for ${provider}/${model}`,
    );
    setIsLoadingMetadata(true);
    try {
      const metadata = await llmApi.getModelMetadata(provider, model);
      console.log("[AgentConfigModal] Metadata loaded:", metadata);
      setModelMetadata(metadata);

      // DON'T auto-update temperature/maxTokens if user has already set them
      // Only update if they're at default values AND agent doesn't have custom values
      // This prevents overwriting user's choices
    } catch (error: any) {
      console.error("Failed to fetch model metadata:", error);
      setModelMetadata(null);
    } finally {
      setIsLoadingMetadata(false);
    }
  };

  // Update available models when provider changes
  const handleProviderChange = (newProvider: string) => {
    const models = availableProviders[newProvider] || [];
    setFormData({
      ...formData,
      provider: newProvider,
      model: models[0] || "", // Select first model by default
    });
  };

  // Handle avatar crop complete
  const handleAvatarCropComplete = async (croppedBlob: Blob) => {
    try {
      if (!agent) return;

      // Upload to MinIO via API
      const result = await agentsApi.uploadAvatar(agent.id, croppedBlob);

      // Store minio reference for DB persistence, presigned URL for display
      setFormData({ ...formData, avatar: result.avatar_ref });
      setAvatarPreview(result.avatar_url);

      toast.success("Avatar uploaded successfully");
    } catch (error: any) {
      console.error("Failed to upload avatar:", error);
      const errorMsg =
        error.response?.data?.detail ||
        error.message ||
        "Failed to upload avatar";
      toast.error(errorMsg);
    }
  };

  useEffect(() => {
    if (!isOpen || activeTab !== "runtime" || agentKind !== "external" || !agent?.id) {
      return;
    }

    const timer = window.setInterval(() => {
      void loadExternalRuntimeOverview();
    }, 15000);

    return () => {
      window.clearInterval(timer);
    };
  }, [activeTab, agent?.id, agentKind, isOpen]);

  if (!isOpen || !agent) return null;

  const hasAdvancedSkillBindingOptions = skillBindings.some((binding) => {
    const skill = availableSkills.find((item) => item.skill_id === binding.skill_id);
    return skill ? bindingModeOptionsForSkill(skill).length > 1 : false;
  });

  const getSkillBindingSourceLabel = (source?: string) => {
    if (source === "auto_learned") {
      return t(
        "agent.skillBindingSourceAutoLearned",
        "Auto-added from approved learned skill",
      );
    }
    if (source === "template_default") {
      return t("agent.skillBindingSourceTemplate", "Added by template");
    }
    return t("agent.skillBindingSourceManual", "Added manually");
  };

  const handleSave = async () => {
    console.log("[AgentConfigModal] handleSave called");
    console.log("[AgentConfigModal] formData:", formData);

    // Validate required fields
    if (!formData.name?.trim()) {
      console.log("[AgentConfigModal] Validation failed: name required");
      setSaveError("Agent name is required");
      return;
    }

    if (!formData.provider) {
      console.log("[AgentConfigModal] Validation failed: provider required");
      setSaveError("Please select a provider");
      return;
    }

    if (!formData.model) {
      console.log("[AgentConfigModal] Validation failed: model required");
      setSaveError("Please select a model");
      return;
    }

    // Clear any previous errors and start saving
    console.log("[AgentConfigModal] Validation passed, starting save...");
    setSaveError(null);
    setIsSaving(true);

    try {
      const shouldNormalizeKnowledge =
        !knowledgeBasesError && !isLoadingKnowledgeBases;
      const availableKnowledgeIds = new Set(
        availableKnowledgeBases.map((item) => item.id),
      );
      const normalizedAllowedKnowledge = shouldNormalizeKnowledge
        ? (formData.allowedKnowledge || []).filter((id) =>
            availableKnowledgeIds.has(id),
          )
        : formData.allowedKnowledge || [];
      const updatedAgent = {
        ...agent!,
        ...formData,
        allowedKnowledge: normalizedAllowedKnowledge,
      } as Agent;
      console.log("[AgentConfigModal] Calling onSave with:", updatedAgent);

      if (agentKind === "external" && agent?.id) {
        await agentsApi.updateExternalRuntimeProfile(agent.id, {
          pathAllowlist: externalPathAllowlist
            .split(/\n+/)
            .map((item) => item.trim())
            .filter(Boolean),
          launchCommandTemplate: externalLaunchCommandTemplate.trim() || undefined,
          desiredVersion: externalRuntimeOverview?.profile?.desired_version || undefined,
        });
      }

      // Call parent's onSave with updated agent data
      await onSave(
        updatedAgent,
        skillBindings
          .slice()
          .sort((left, right) => left.priority - right.priority)
          .map((binding, index) => ({
            ...binding,
            priority: index,
          })),
      );

      console.log("[AgentConfigModal] Save successful");
      // If we get here, save was successful
      // Parent component will close the modal
    } catch (error: any) {
      // If parent's onSave throws an error, display it in the modal
      console.error("[AgentConfigModal] Save failed:", error);

      let errorMessage = "Failed to save agent configuration";

      // Handle validation errors from backend
      if (error.response?.data?.details?.errors) {
        // Backend validation error format: { details: { errors: [...] } }
        const errors = error.response.data.details.errors;
        errorMessage = errors
          .map((err: any) => `${err.field}: ${err.message}`)
          .join("; ");
      } else if (error.response?.data?.message) {
        // Generic error message
        errorMessage = error.response.data.message;
      } else if (error.response?.data?.detail) {
        // FastAPI detail format
        if (typeof error.response.data.detail === "string") {
          errorMessage = error.response.data.detail;
        } else if (Array.isArray(error.response.data.detail)) {
          errorMessage = error.response.data.detail
            .map((err: any) => `${err.loc.join(".")}: ${err.msg}`)
            .join(", ");
        }
      } else if (error.message) {
        errorMessage = error.message;
      }

      console.log("[AgentConfigModal] Setting error:", errorMessage);
      setSaveError(errorMessage);
    } finally {
      console.log(
        "[AgentConfigModal] Save process complete, setting isSaving=false",
      );
      setIsSaving(false);
    }
  };

  const tabs = [
    { id: "basic", label: t("agent.basicInfo") },
    { id: "runtime", label: agentKind === "external" ? t("agent.runtimeTabExternal", "Runtime Host") : t("agent.runtimeTab", "Runtime") },
    { id: "capabilities", label: t("agent.capabilities") },
    { id: "model", label: t("agent.modelConfig") },
    { id: "knowledge", label: t("agent.knowledgeBase") },
    { id: "access", label: t("agent.sharingAndKnowledgeAccess") },
    { id: "channels", label: t("agent.channelPublish", "渠道发布") },
  ];

  const trimFeishuAppId = (value: string | undefined) => value?.trim() || "";
  const hasUnsavedFeishuChanges =
    trimFeishuAppId(feishuFormData.appId) !==
      trimFeishuAppId(feishuPublication?.appId || "") ||
    Boolean(feishuFormData.appSecret?.trim());

  const getFeishuConnectionState = (
    publication: FeishuPublicationConfig | null,
  ): string => {
    if (!publication || publication.status !== "published") {
      return "inactive";
    }
    return publication.connectionState || "connecting";
  };

  const getFeishuConnectionStateLabel = (state: string): string => {
    switch (state) {
      case "connected":
        return t("agent.feishuConnectionStateConnected", "Connected");
      case "connecting":
        return t("agent.feishuConnectionStateConnecting", "Connecting");
      case "error":
        return t("agent.feishuConnectionStateError", "Connection failed");
      case "inactive":
      default:
        return t("agent.feishuConnectionStateInactive", "Inactive");
    }
  };

  const getFeishuPublicationStatusLabel = (
    status: string | undefined,
  ): string => {
    switch (status) {
      case "published":
        return t("agent.feishuPublicationStatusPublished", "Published");
      case "draft":
      default:
        return t("agent.feishuPublicationStatusDraft", "Draft");
    }
  };

  const getFeishuConnectionStateTone = (state: string): string => {
    switch (state) {
      case "connected":
        return "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300";
      case "connecting":
        return "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300";
      case "error":
        return "bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-300";
      case "inactive":
      default:
        return "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300";
    }
  };

  const loadExternalRuntimeOverview = async () => {
    if (!agent?.id || agentKind !== "external") {
      setExternalRuntimeOverview(null);
      return;
    }
    try {
      setIsLoadingExternalRuntime(true);
      const overview = await agentsApi.getExternalRuntime(agent.id);
      setExternalRuntimeOverview(overview);
      setExternalPathAllowlist((overview.profile.path_allowlist || []).join("\n"));
      setExternalLaunchCommandTemplate(overview.profile.launch_command_template || "");
    } catch (error) {
      console.error("Failed to load external runtime overview:", error);
    } finally {
      setIsLoadingExternalRuntime(false);
    }
  };

  const copyInstallCommand = async () => {
    if (!agent?.id) return;
    setIsGeneratingInstallCommand(true);
    try {
      const response = await agentsApi.createExternalRuntimeInstallCommand(agent.id, externalRuntimeTarget);
      setInstallCommand(response.command);
      setInstallCommandExpiresAt(response.expires_at);
      await navigator.clipboard.writeText(response.command);
      toast.success(t("agent.externalInstallCommandCopied", "Install command copied"));
    } finally {
      setIsGeneratingInstallCommand(false);
    }
  };

  const copyUpdateCommand = async () => {
    if (!agent?.id) return;
    setIsGeneratingUpdateCommand(true);
    try {
      const response = await agentsApi.createExternalRuntimeUpdateCommand(agent.id, externalRuntimeTarget);
      setMaintenanceCommand(response.command);
      setMaintenanceCommandLabel(
        t("agent.externalMaintenanceCommandLabelUpdate", "Update command"),
      );
      await navigator.clipboard.writeText(response.command);
      toast.success(t("agent.externalUpdateCommandCopied", "Update command copied"));
    } finally {
      setIsGeneratingUpdateCommand(false);
    }
  };

  const copyUninstallCommand = async () => {
    if (!agent?.id) return;
    setIsGeneratingUninstallCommand(true);
    try {
      const response = await agentsApi.createExternalRuntimeUninstallCommand(
        agent.id,
        externalRuntimeTarget,
      );
      setMaintenanceCommand(response.command);
      setMaintenanceCommandLabel(
        t("agent.externalMaintenanceCommandLabelUninstall", "Uninstall command"),
      );
      await navigator.clipboard.writeText(response.command);
      toast.success(
        t("agent.externalUninstallCommandCopied", "Uninstall command copied"),
      );
    } finally {
      setIsGeneratingUninstallCommand(false);
    }
  };

  const handleRequestRuntimeUpdate = async () => {
    if (!agent?.id) return;
    setIsRequestingRuntimeUpdate(true);
    try {
      await agentsApi.requestExternalRuntimeUpdate(agent.id);
      toast.success(
        t(
          "agent.externalRuntimeUpdateQueued",
          "Runtime Host update has been queued",
        ),
      );
      await loadExternalRuntimeOverview();
    } catch (error: any) {
      toast.error(
        error?.response?.data?.detail ||
          t(
            "agent.externalRuntimeUpdateQueueFailed",
            "Failed to queue Runtime Host update",
          ),
      );
    } finally {
      setIsRequestingRuntimeUpdate(false);
    }
  };

  const handleRequestRuntimeUninstall = async () => {
    if (!agent?.id) return;
    setIsRequestingRuntimeUninstall(true);
    try {
      await agentsApi.requestExternalRuntimeUninstall(agent.id);
      toast.success(
        t(
          "agent.externalRuntimeUninstallQueued",
          "Runtime Host uninstall has been queued",
        ),
      );
      await loadExternalRuntimeOverview();
    } catch (error: any) {
      toast.error(
        error?.response?.data?.detail ||
          t(
            "agent.externalRuntimeUninstallQueueFailed",
            "Failed to queue Runtime Host uninstall",
          ),
      );
    } finally {
      setIsRequestingRuntimeUninstall(false);
    }
  };

  const handleUnbindExternalRuntime = async () => {
    if (!agent?.id) return;
    await agentsApi.unbindExternalRuntime(agent.id);
    toast.success(t("agent.externalRuntimeUnbound", "Host unbound"));
    await loadExternalRuntimeOverview();
  };

  const handleSaveExternalRuntimeProfile = async () => {
    if (!agent?.id) return;
    setIsSavingExternalRuntimeProfile(true);
    try {
      const overview = await agentsApi.updateExternalRuntimeProfile(agent.id, {
        pathAllowlist: externalPathAllowlist
          .split(/\n+/)
          .map((item) => item.trim())
          .filter(Boolean),
        launchCommandTemplate: externalLaunchCommandTemplate.trim() || undefined,
        desiredVersion: externalRuntimeOverview?.profile?.desired_version || undefined,
      });
      setExternalRuntimeOverview(overview);
      setExternalPathAllowlist((overview.profile.path_allowlist || []).join("\n"));
      setExternalLaunchCommandTemplate(overview.profile.launch_command_template || "");
      toast.success(
        t("agent.externalRuntimeProfileSaved", "Runtime Host settings saved"),
      );
    } catch (error: any) {
      toast.error(
        error?.response?.data?.detail ||
          t(
            "agent.externalRuntimeProfileSaveFailed",
            "Failed to save Runtime Host settings",
          ),
      );
    } finally {
      setIsSavingExternalRuntimeProfile(false);
    }
  };

  const formatExternalRuntimeLabel = (status?: string | null) =>
    t(`agent.externalRuntimeStatus.${status || "uninstalled"}`, {
      defaultValue: status || "uninstalled",
    });

  const formatLaunchCommandSourceLabel = (source?: string | null) => {
    switch (source) {
      case "agent":
        return t("agent.launchCommandSource.agent", "Agent override");
      case "platform":
        return t("agent.launchCommandSource.platform", "Platform default");
      case "unset":
      default:
        return t("agent.launchCommandSource.unset", "Not configured");
    }
  };

  const formatDispatchStatusLabel = (status?: string | null) => {
    if (!status) {
      return t("agent.externalRuntimeLastActionUnknown", "Unknown");
    }
    return String(status).replace(/_/g, " ");
  };

  const getExternalRuntimeSetupMessage = (overview?: ExternalRuntimeOverview | null) => {
    const state = overview?.state;
    if (!state) {
      return t("agent.externalRuntimeSetupUnknown", "Runtime Host status is unavailable.");
    }
    if (state.launchCommandSource === "unset") {
      return t(
        "agent.externalRuntimeSetupNeedsCommand",
        "Runtime Host is installed, but no launch command is configured yet.",
      );
    }
    switch (state.status) {
      case "uninstalled":
        return t(
          "agent.externalRuntimeSetupUninstalled",
          "Generate the install command and run it on the target machine.",
        );
      case "offline":
        return t(
          "agent.externalRuntimeSetupOffline",
          "This Runtime Host was bound before, but it is not currently connected.",
        );
      case "error":
        return state.lastErrorMessage ||
          t(
            "agent.externalRuntimeSetupError",
            "The Runtime Host reported an error. Review the binding and reconnect it.",
          );
      default:
        return t(
          "agent.externalRuntimeSetupOnline",
          "This Runtime Host is online and ready to accept work.",
        );
    }
  };

  const formatFeishuTimestamp = (value?: string | null) => {
    if (!value) {
      return "—";
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return "—";
    }
    return parsed.toLocaleString(
      i18n.language.startsWith("zh") ? "zh-CN" : "en-US",
    );
  };

  const getFeishuConnectionSummary = (
    publication: FeishuPublicationConfig | null,
  ) => {
    const state = getFeishuConnectionState(publication);
    if (!publication || publication.status !== "published") {
      return t(
        "agent.feishuConnectionSavedDraft",
        "Credentials are saved, but the channel is not enabled yet. Publish to start the long connection.",
      );
    }
    if (state === "connected") {
      return t(
        "agent.feishuConnectionPublishedConnected",
        "The channel is enabled and the long connection is established.",
      );
    }
    if (state === "error") {
      return t(
        "agent.feishuConnectionPublishedError",
        "The channel is enabled, but the latest long-connection attempt failed. Check the error and retry.",
      );
    }
    return t(
      "agent.feishuConnectionPublishedPending",
      "The channel is enabled. The backend is trying to establish the long connection.",
    );
  };

  const persistFeishuPublicationConfig = async ({
    showToast = true,
  }: {
    showToast?: boolean;
  } = {}): Promise<FeishuPublicationConfig> => {
    if (!agent?.id || !feishuFormData.appId.trim()) {
      throw new Error(
        t("agent.feishuAppIdRequired", "Feishu App ID is required"),
      );
    }
    if (!feishuFormData.appSecret?.trim() && !feishuPublication?.hasAppSecret) {
      throw new Error(
        t("agent.feishuAppSecretRequired", "Feishu App secret is required"),
      );
    }

    const saved = await agentsApi.saveFeishuPublication(agent.id, {
      appId: feishuFormData.appId.trim(),
      appSecret: feishuFormData.appSecret?.trim() || undefined,
    });
    setFeishuPublication(saved);
    setFeishuFormData({
      appId: saved.appId || feishuFormData.appId.trim(),
      appSecret: "",
    });
    if (showToast) {
      toast.success(t("agent.feishuConfigSaved", "Feishu config saved"));
    }
    return saved;
  };

  const handleSaveFeishuPublication = async () => {
    setIsSavingFeishuPublication(true);
    setFeishuError(null);
    try {
      await persistFeishuPublicationConfig();
    } catch (error: any) {
      console.error("Failed to save Feishu publication:", error);
      setFeishuError(
        error.response?.data?.detail ||
          error.message ||
          t("agent.feishuSaveFailed", "Failed to save Feishu config"),
      );
    } finally {
      setIsSavingFeishuPublication(false);
    }
  };

  const handlePublishFeishuPublication = async () => {
    if (!agent?.id) return;
    setIsSavingFeishuPublication(true);
    setFeishuError(null);
    try {
      if (hasUnsavedFeishuChanges || !feishuPublication?.publicationId) {
        await persistFeishuPublicationConfig({ showToast: false });
      }
      const published = await agentsApi.publishFeishuPublication(agent.id);
      setFeishuPublication(published);
      toast.success(
        t("agent.feishuPublished", "Feishu long connection enabled"),
      );
    } catch (error: any) {
      console.error("Failed to publish Feishu publication:", error);
      setFeishuError(
        error.response?.data?.detail ||
          error.message ||
          t(
            "agent.feishuPublishFailed",
            "Failed to enable Feishu long connection",
          ),
      );
    } finally {
      setIsSavingFeishuPublication(false);
    }
  };

  const handleUnpublishFeishuPublication = async () => {
    if (!agent?.id) return;
    setIsSavingFeishuPublication(true);
    setFeishuError(null);
    try {
      const unpublished = await agentsApi.unpublishFeishuPublication(agent.id);
      setFeishuPublication(unpublished);
      toast.success(
        t("agent.feishuUnpublished", "Feishu long connection disabled"),
      );
    } catch (error: any) {
      console.error("Failed to unpublish Feishu publication:", error);
      setFeishuError(
        error.response?.data?.detail ||
          error.message ||
          t(
            "agent.feishuUnpublishFailed",
            "Failed to disable Feishu long connection",
          ),
      );
    } finally {
      setIsSavingFeishuPublication(false);
    }
  };

  return (
    <LayoutModal
      isOpen={isOpen}
      onClose={onClose}
      closeOnBackdropClick={false}
      closeOnEscape={true}
    >
      <div className="w-full max-w-4xl my-auto max-h-[calc(100vh-var(--app-header-height,4rem)-3rem)] overflow-hidden flex flex-col modal-panel rounded-[24px] shadow-2xl p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6 pb-4 border-b border-zinc-200 dark:border-zinc-700">
          <div>
            <h2 className="text-2xl font-bold text-zinc-800 dark:text-zinc-200">
              {t("agent.configure")}
            </h2>
            <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-1">
              {agent.name}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors text-zinc-600 dark:text-zinc-400"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 mb-6 flex-wrap">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`px-4 py-2 rounded-lg font-semibold text-sm whitespace-nowrap transition-all ${
                activeTab === tab.id
                  ? "bg-emerald-500 text-white shadow-sm"
                  : "bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-200 dark:hover:bg-zinc-700"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto mb-6">
          {/* Basic Info Tab */}
          {activeTab === "basic" && (
            <div className="space-y-4">
              <div className="rounded-xl border border-indigo-500/20 bg-indigo-500/5 p-4">
                <p className="text-sm font-semibold text-zinc-700 dark:text-zinc-300">
                  {agentKind === "external" ? t("agent.externalAgentBadge", "External Agent") : t("agent.internalAgentBadge", "Internal Agent")}
                </p>
                <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                  {agentKind === "external"
                    ? t("agent.runtimeBannerExternal", "This agent runs through a bound external host. Install, update, and unbind it directly from this panel.")
                    : t("agent.runtimeBannerInternal", "This agent runs inside project run sandboxes and is attached to projects later from Project Agent Pool.")}
                </p>
              </div>
              {/* Avatar Upload */}
              <div>
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t("agent.avatar")}
                </label>
                <div className="flex items-center gap-4">
                  {/* Avatar Preview */}
                  <div className="relative w-24 h-24 rounded-full overflow-hidden bg-gradient-to-br from-emerald-400 to-cyan-500 flex items-center justify-center">
                    {avatarPreview ? (
                      <img
                        src={avatarPreview}
                        alt={formData.name}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <span className="text-3xl font-bold text-white">
                        {formData.name?.charAt(0)?.toUpperCase() || "A"}
                      </span>
                    )}
                  </div>

                  {/* Upload Button */}
                  <button
                    type="button"
                    onClick={() => setIsAvatarCropModalOpen(true)}
                    className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg font-semibold transition-colors"
                  >
                    {avatarPreview
                      ? t("agent.changeAvatar")
                      : t("agent.uploadAvatar")}
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t("agent.agentName")}
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) =>
                    setFormData({ ...formData, name: e.target.value })
                  }
                  className="w-full px-4 py-3 bg-zinc-500/5 border border-zinc-500/10 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500/20 text-zinc-800 dark:text-zinc-200"
                  placeholder={t("agent.agentNamePlaceholder")}
                />
              </div>

              <div>
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t("agent.systemPrompt")}
                </label>
                <textarea
                  value={formData.systemPrompt}
                  onChange={(e) =>
                    setFormData({ ...formData, systemPrompt: e.target.value })
                  }
                  rows={8}
                  className="w-full px-4 py-3 bg-zinc-500/5 border border-zinc-500/10 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500/20 text-zinc-800 dark:text-zinc-200 resize-none"
                  placeholder={t("agent.systemPromptPlaceholder")}
                />
              </div>

              <div className="rounded-xl border border-indigo-500/20 bg-indigo-500/5 p-4">
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t("agent.runtimeConfigTitle", "Runtime Configuration")}
                </label>
                <select
                  value={String(formData.runtimeType || "project_sandbox")}
                  onChange={(e) =>
                    setFormData({ ...formData, runtimeType: e.target.value, projectScopeId: e.target.value === "project_sandbox" ? "" : formData.projectScopeId })
                  }
                  className="w-full px-4 py-3 bg-white/80 dark:bg-zinc-900/60 border border-indigo-500/20 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500/20 text-zinc-800 dark:text-zinc-200"
                >
                  <option value="project_sandbox">{t("agent.runtimeTypeValue.project_sandbox", "project_sandbox")}</option>
                  <option value="external_worktree">{t("agent.runtimeTypeValue.external_worktree", "external_worktree")}</option>
                  <option value="external_same_dir">{t("agent.runtimeTypeValue.external_same_dir", "external_same_dir")}</option>
                  <option value="remote_session">{t("agent.runtimeTypeValue.remote_session", "remote_session")}</option>
                </select>
                <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
                  {String(formData.runtimeType || "project_sandbox") === "project_sandbox"
                    ? t("agent.runtimeConfigInternalDescription", "This agent runs inside project run sandboxes. Project assignment happens from the project workspace, not here.")
                    : t("agent.runtimeConfigExternalDescription", "This agent is an external agent. It still behaves like a normal agent, but it needs a runtime host and may affect an external machine.")}
                </p>
              </div>

              <div className="rounded-xl border border-zinc-500/10 bg-zinc-500/5 p-4">
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t("departments.label", "Department")}
                </label>
                <p className="text-sm text-zinc-700 dark:text-zinc-300">
                  {agent?.departmentName || t("agent.unassignedDepartment", "Unassigned")}
                </p>
                <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                  {t(
                    "agent.boundDepartmentHint",
                    "This agent will automatically bind to your current department. You can change sharing visibility after creation.",
                  )}
                </p>
              </div>

              <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4">
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t("agent.accessLevel")}
                </label>
                <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
                  {t(
                    "agent.sharingScopeDescription",
                    "This controls the agent's sharing scope, not which knowledge bases or data the agent can access.",
                  )}
                </p>
                <select
                  value={formData.accessLevel}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      accessLevel: e.target.value as any,
                    })
                  }
                  className="w-full px-4 py-3 bg-white/80 dark:bg-zinc-900/60 border border-emerald-500/20 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500/20 text-zinc-800 dark:text-zinc-200"
                >
                  <option value="private">{t("agent.accessLevelPrivate")}</option>
                  <option value="department">{t("agent.accessLevelDepartment")}</option>
                  <option value="public">{t("agent.accessLevelPublic")}</option>
                </select>
              </div>
            </div>
          )}

          {activeTab === "runtime" && (
            <div className="space-y-4">
              <div className="rounded-xl border border-indigo-500/20 bg-indigo-500/5 p-4">
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t("agent.runtimeConfigTitle", "Runtime Configuration")}
                </label>
                <select
                  value={String(formData.runtimeType || "project_sandbox")}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      runtimeType: e.target.value,
                    })
                  }
                  className="w-full px-4 py-3 bg-white/80 dark:bg-zinc-900/60 border border-indigo-500/20 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500/20 text-zinc-800 dark:text-zinc-200"
                >
                  <option value="project_sandbox">{t("agent.runtimeTypeValue.project_sandbox", "project_sandbox")}</option>
                  <option value="external_worktree">{t("agent.runtimeTypeValue.external_worktree", "external_worktree")}</option>
                  <option value="external_same_dir">{t("agent.runtimeTypeValue.external_same_dir", "external_same_dir")}</option>
                  <option value="remote_session">{t("agent.runtimeTypeValue.remote_session", "remote_session")}</option>
                </select>
                <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
                  {String(formData.runtimeType || "project_sandbox") === "project_sandbox"
                    ? t("agent.runtimeConfigInternalDescription", "This agent runs inside project run sandboxes. Project assignment happens from the project workspace, not here.")
                    : t("agent.runtimeConfigExternalDescription", "This agent is an external agent. It still behaves like a normal agent, but it needs a runtime host and may affect an external machine.")}
                </p>
              </div>

              {String(formData.runtimeType || "project_sandbox") !== "project_sandbox" ? (
                <div className="space-y-4">
                  <div className="grid gap-4 lg:grid-cols-2">
                    <div className="rounded-xl border border-zinc-500/10 bg-zinc-500/5 p-4">
                      <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                        {t("agent.externalConfigProjectBindingTitle", "Project Usage")}
                      </label>
                      <p className="text-sm text-zinc-700 dark:text-zinc-300">
                        {t("agent.externalConfigProjectBindingDescription", "External agents are not bound to a project here. Add them to a project from Project Detail → Project Agent Pool.")}
                      </p>
                    </div>
                    <div className="rounded-xl border border-zinc-500/10 bg-zinc-500/5 p-4">
                      <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                        {t("agent.externalConfigNodeBindingTitle", "Runtime Host")}
                      </label>
                      <p className="text-sm text-zinc-700 dark:text-zinc-300">
                        {t("agent.externalConfigNodeBindingDescription", "This external agent binds directly to one host. Manage install commands, host status, and path allowlists here.")}
                      </p>
                    </div>
                  </div>
                  <div className="space-y-4 rounded-xl border border-indigo-500/20 bg-indigo-500/5 p-4">
                    <div className="rounded-xl border border-indigo-500/20 bg-white/70 p-4 dark:bg-zinc-950/40">
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-indigo-500">
                        {t("agent.externalRuntimeStep1", "Step 1")}
                      </p>
                      <p className="mt-2 text-sm font-semibold text-zinc-800 dark:text-zinc-100">
                        {t("agent.externalRuntimeInstallTitle", "Generate the one-line install command")}
                      </p>
                      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                        {t("agent.externalRuntimeInstallDescription", "Pick the target OS, then copy and run the installer on the host machine.")}
                      </p>
                      <div className="mt-4 flex items-center gap-2">
                        {(["linux", "darwin", "windows"] as const).map((target) => (
                          <button
                            key={target}
                            type="button"
                            onClick={() => setExternalRuntimeTarget(target)}
                            className={`rounded-full px-3 py-1 text-xs font-semibold transition ${externalRuntimeTarget === target ? "bg-indigo-600 text-white" : "bg-zinc-100 text-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"}`}
                          >
                            {target}
                          </button>
                        ))}
                      </div>
                      <div className="mt-4 flex flex-wrap gap-3">
                        <button
                          type="button"
                          onClick={() => void copyInstallCommand()}
                          disabled={isGeneratingInstallCommand}
                          className="rounded-full bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
                        >
                          {isGeneratingInstallCommand
                            ? t("agent.loading", "Loading...")
                            : t("agent.copyInstallCommand", "Copy Install Command")}
                        </button>
                        {installCommandExpiresAt ? (
                          <p className="self-center text-xs text-zinc-500 dark:text-zinc-400">
                            {t("agent.externalInstallCommandExpires", {
                              value: formatFeishuTimestamp(installCommandExpiresAt),
                              defaultValue: `Expires ${formatFeishuTimestamp(installCommandExpiresAt)}`,
                            })}
                          </p>
                        ) : null}
                      </div>
                      {installCommand ? (
                        <textarea
                          readOnly
                          value={installCommand}
                          rows={4}
                          className="mt-4 w-full rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-900 outline-none dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
                        />
                      ) : null}
                    </div>

                    <div className="rounded-xl border border-zinc-200/80 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/40">
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-indigo-500">
                        {t("agent.externalRuntimeStep2", "Step 2")}
                      </p>
                      <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-zinc-800 dark:text-zinc-100">
                            {t("agent.externalRuntimeStatusTitle", "Host Binding Status")}
                          </p>
                          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                            {isLoadingExternalRuntime
                              ? t("agent.loading", "Loading...")
                              : formatExternalRuntimeLabel(externalRuntimeOverview?.state.status || agent.externalRuntime?.status || "uninstalled")}
                          </p>
                        </div>
                        <div className="flex flex-wrap gap-3">
                          <button type="button" onClick={() => void loadExternalRuntimeOverview()} className="rounded-full border border-zinc-300 px-4 py-2 text-sm font-semibold text-zinc-700 transition hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800">
                            {t("agent.refreshExternalRuntime", "Refresh Status")}
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleRequestRuntimeUpdate()}
                            disabled={!externalRuntimeOverview?.state.bound || isRequestingRuntimeUpdate}
                            className="rounded-full bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
                          >
                            {isRequestingRuntimeUpdate
                              ? t("agent.loading", "Loading...")
                              : t("agent.requestRuntimeUpdate", "Update Now")}
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleRequestRuntimeUninstall()}
                            disabled={!externalRuntimeOverview?.state.bound || isRequestingRuntimeUninstall}
                            className="rounded-full bg-amber-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-amber-500 disabled:opacity-50"
                          >
                            {isRequestingRuntimeUninstall
                              ? t("agent.loading", "Loading...")
                              : t("agent.requestRuntimeUninstall", "Uninstall Now")}
                          </button>
                          <button type="button" onClick={() => void copyUpdateCommand()} disabled={!externalRuntimeOverview?.state.bound || isGeneratingUpdateCommand} className="rounded-full border border-zinc-300 px-4 py-2 text-sm font-semibold text-zinc-700 transition hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800">
                            {isGeneratingUpdateCommand
                              ? t("agent.loading", "Loading...")
                              : t("agent.copyUpdateCommand", "Copy Update Command")}
                          </button>
                          <button type="button" onClick={() => void copyUninstallCommand()} disabled={!externalRuntimeOverview?.state.bound || isGeneratingUninstallCommand} className="rounded-full border border-amber-300 px-4 py-2 text-sm font-semibold text-amber-700 transition hover:bg-amber-50 disabled:opacity-50 dark:border-amber-900/40 dark:text-amber-300 dark:hover:bg-amber-950/30">
                            {isGeneratingUninstallCommand
                              ? t("agent.loading", "Loading...")
                              : t("agent.copyUninstallCommand", "Copy Uninstall Command")}
                          </button>
                          <button type="button" onClick={() => void handleUnbindExternalRuntime()} disabled={!externalRuntimeOverview?.state.bound} className="rounded-full border border-rose-300 px-4 py-2 text-sm font-semibold text-rose-600 transition hover:bg-rose-50 disabled:opacity-50 dark:border-rose-900/40 dark:text-rose-300 dark:hover:bg-rose-950/30">
                            {t("agent.unbindExternalRuntime", "Unbind Host")}
                          </button>
                        </div>
                      </div>
                      <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
                        {getExternalRuntimeSetupMessage(externalRuntimeOverview)}
                      </p>
                      <div className="mt-4 grid gap-3 sm:grid-cols-2 text-sm text-zinc-700 dark:text-zinc-300">
                        <p>{t("agent.externalRuntimeHost", "Host")}: {externalRuntimeOverview?.state.hostName || "—"}</p>
                        <p>{t("agent.externalRuntimeOs", "OS")}: {externalRuntimeOverview?.state.hostOs || "—"}</p>
                        <p>{t("agent.externalRuntimeArch", "Arch")}: {externalRuntimeOverview?.state.hostArch || "—"}</p>
                        <p>{t("agent.externalRuntimeVersion", "Version")}: {externalRuntimeOverview?.state.currentVersion || "—"}</p>
                        <p>{t("agent.externalRuntimeDesiredVersion", "Desired Version")}: {externalRuntimeOverview?.state.desiredVersion || "—"}</p>
                        <p>
                          {t("agent.externalRuntimeUpdateAvailable", {
                            value: externalRuntimeOverview?.state.updateAvailable
                              ? t("settings.enabled", "Enabled")
                              : t("settings.disabled", "Disabled"),
                            defaultValue: `Update available: ${externalRuntimeOverview?.state.updateAvailable ? "Enabled" : "Disabled"}`,
                          })}
                        </p>
                      </div>
                      {(externalRuntimeOverview?.state.lastDispatchAction || externalRuntimeOverview?.state.lastDispatchStatus) ? (
                        <div className="mt-4 rounded-xl border border-zinc-200 bg-zinc-50/80 p-4 dark:border-zinc-800 dark:bg-zinc-950/50">
                          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500 dark:text-zinc-400">
                            {t("agent.externalRuntimeLastActionTitle", "Last Runtime Action")}
                          </p>
                          <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-300">
                            {t("agent.externalRuntimeLastActionSummary", {
                              action: externalRuntimeOverview?.state.lastDispatchAction || "—",
                              status: formatDispatchStatusLabel(externalRuntimeOverview?.state.lastDispatchStatus),
                              defaultValue: `${externalRuntimeOverview?.state.lastDispatchAction || "—"} · ${formatDispatchStatusLabel(externalRuntimeOverview?.state.lastDispatchStatus)}`,
                            })}
                          </p>
                          {externalRuntimeOverview?.state.lastDispatchErrorMessage ? (
                            <p className="mt-2 text-xs text-rose-600 dark:text-rose-300">
                              {externalRuntimeOverview.state.lastDispatchErrorMessage}
                            </p>
                          ) : null}
                        </div>
                      ) : null}
                      {maintenanceCommand ? (
                        <div className="mt-4">
                          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500 dark:text-zinc-400">
                            {maintenanceCommandLabel}
                          </p>
                          <textarea
                            readOnly
                            value={maintenanceCommand}
                            rows={4}
                            className="w-full rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-900 outline-none dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
                          />
                        </div>
                      ) : null}
                      <div className="mt-4 rounded-xl border border-zinc-200 bg-zinc-50/80 p-4 dark:border-zinc-800 dark:bg-zinc-950/50">
                        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500 dark:text-zinc-400">
                          {t("agent.externalRuntimeLocalStatusTitle", "Local Status Page")}
                        </p>
                        {externalRuntimeOverview?.state.localStatusUrl ? (
                          <>
                            <a
                              href={externalRuntimeOverview.state.localStatusUrl}
                              target="_blank"
                              rel="noreferrer"
                              className="mt-2 block break-all text-sm font-medium text-indigo-600 underline-offset-2 hover:underline dark:text-indigo-400"
                            >
                              {externalRuntimeOverview.state.localStatusUrl}
                            </a>
                            <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
                              {t(
                                "agent.externalRuntimeLocalStatusHint",
                                "This page is served from the Runtime Host itself and is usually only reachable on that machine.",
                              )}
                            </p>
                          </>
                        ) : (
                          <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                            {t(
                              "agent.externalRuntimeLocalStatusUnavailable",
                              "The local status page is not available yet.",
                            )}
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="rounded-xl border border-zinc-200/80 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/40">
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-indigo-500">
                        {t("agent.externalRuntimeStep3", "Step 3")}
                      </p>
                      <p className="mt-2 text-sm font-semibold text-zinc-800 dark:text-zinc-100">
                        {t("agent.externalRuntimeCommandTitle", "Confirm how this host launches the agent")}
                      </p>
                      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                        {t("agent.externalRuntimeCommandSource", {
                          value: formatLaunchCommandSourceLabel(externalRuntimeOverview?.state.launchCommandSource),
                          defaultValue: `Current source: ${formatLaunchCommandSourceLabel(externalRuntimeOverview?.state.launchCommandSource)}`,
                        })}
                      </p>
                      <label className="mt-4 block text-sm font-semibold text-zinc-700 dark:text-zinc-300">
                        {t("agent.externalPathAllowlist", "Path Allowlist")}
                        <textarea
                          value={externalPathAllowlist}
                          onChange={(event) => setExternalPathAllowlist(event.target.value)}
                          rows={3}
                          className="mt-2 w-full rounded-xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
                          placeholder={t("agent.externalPathAllowlistPlaceholder", "One path per line")}
                        />
                      </label>
                      <label className="mt-4 block text-sm font-semibold text-zinc-700 dark:text-zinc-300">
                        {t("agent.externalLaunchCommandTemplate", "Launch Command Template")}
                        <textarea
                          value={externalLaunchCommandTemplate}
                          onChange={(event) => setExternalLaunchCommandTemplate(event.target.value)}
                          rows={4}
                          className="mt-2 w-full rounded-xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
                          placeholder={t("agent.externalLaunchCommandTemplatePlaceholder", "Leave blank to inherit the platform default launch command")}
                        />
                      </label>
                      {externalRuntimeOverview?.state.resolvedLaunchCommandTemplate ? (
                        <textarea
                          readOnly
                          value={externalRuntimeOverview.state.resolvedLaunchCommandTemplate}
                          rows={3}
                          className="mt-4 w-full rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-900 outline-none dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
                        />
                      ) : null}
                      <div className="mt-4 flex justify-end">
                        <button
                          type="button"
                          onClick={() => void handleSaveExternalRuntimeProfile()}
                          disabled={isSavingExternalRuntimeProfile}
                          className="rounded-full bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
                        >
                          {isSavingExternalRuntimeProfile
                            ? t("agent.loading", "Loading...")
                            : t("agent.saveExternalRuntimeProfile", "Save Runtime Host Settings")}
                        </button>
                      </div>
                    </div>

                    <div className="rounded-xl border border-zinc-200/80 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/40">
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-indigo-500">
                        {t("agent.externalRuntimeStep4", "Step 4")}
                      </p>
                      <p className="mt-2 text-sm font-semibold text-zinc-800 dark:text-zinc-100">
                        {t("agent.externalConfigProjectBindingTitle", "Project Usage")}
                      </p>
                      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                        {t("agent.externalConfigProjectBindingDescription", "External agents are not bound to a project here. Add them to a project from Project Detail → Project Agent Pool.")}
                      </p>
                      <div className="mt-4">
                        <a
                          href="/projects"
                          className="inline-flex rounded-full border border-zinc-300 px-4 py-2 text-sm font-semibold text-zinc-700 transition hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
                        >
                          {t("agent.openProjectsForBinding", "Open Projects")}
                        </a>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="rounded-xl border border-zinc-500/10 bg-zinc-500/5 p-4">
                  <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                    {t("agent.internalConfigProjectBindingTitle", "Project Usage")}
                  </label>
                  <p className="text-sm text-zinc-700 dark:text-zinc-300">
                    {t("agent.internalConfigProjectBindingDescription", "Internal agents run in project run sandboxes. Bind them to projects later from the project workspace when you want them to participate in project execution.")}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Capabilities Tab */}
          {activeTab === "capabilities" && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t("agent.selectSkills", "选择技能")}
                </label>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-3">
                  {t(
                    "agent.skillsDescription",
                    "Select the skills this agent can use. Approved learned skills from this agent are auto-added by default.",
                  )}
                </p>
                <div className="mb-3 rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-xs text-emerald-700 dark:text-emerald-300">
                  {t(
                    "agent.skillSelectionHint",
                    "Most of the time you only need to check or uncheck skills here. Extra options only appear for a few hybrid skills.",
                  )}
                </div>

                {/* Skills Loading State */}
                {isLoadingSkills && (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="w-6 h-6 animate-spin text-emerald-500" />
                    <span className="ml-2 text-zinc-600 dark:text-zinc-400">
                      {t("agent.loadingSkills", "加载技能中...")}
                    </span>
                  </div>
                )}

                {/* Skills Error State */}
                {skillsError && (
                  <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl flex items-start gap-3">
                    <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-semibold text-red-700 dark:text-red-400">
                        {skillsError}
                      </p>
                      <button
                        onClick={fetchAvailableSkills}
                        className="mt-2 text-sm text-red-600 dark:text-red-400 hover:underline"
                      >
                        {t("common.retry", "重试")}
                      </button>
                    </div>
                  </div>
                )}

                {/* Skills List */}
                {!isLoadingSkills && !skillsError && (
                  <div className="space-y-3">
                    {/* Selected Skills Count */}
                    <div className="flex items-center justify-between p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-lg">
                      <span className="text-sm font-medium text-emerald-700 dark:text-emerald-400">
                        {t("agent.selectedSkills", "已选择技能")}
                      </span>
                      <div className="flex items-center gap-3">
                        <span className="text-sm font-semibold text-emerald-700 dark:text-emerald-400">
                          {skillBindings.length} / {availableSkills.length}
                        </span>
                        {hasAdvancedSkillBindingOptions && (
                          <button
                            type="button"
                            onClick={() =>
                              setShowAdvancedSkillBindings((current) => !current)
                            }
                            className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700 underline-offset-2 hover:underline dark:text-emerald-300"
                          >
                            {showAdvancedSkillBindings
                              ? t(
                                  "agent.hideAdvancedSkillBindings",
                                  "Hide advanced options",
                                )
                              : t(
                                  "agent.showAdvancedSkillBindings",
                                  "Show advanced options",
                                )}
                            {showAdvancedSkillBindings ? (
                              <ChevronUp className="h-3.5 w-3.5" />
                            ) : (
                              <ChevronDown className="h-3.5 w-3.5" />
                            )}
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Skills Grid */}
                    {availableSkills.length === 0 ? (
                      <div className="p-8 text-center bg-zinc-500/5 border border-zinc-500/10 rounded-xl">
                        <Info className="w-8 h-8 text-zinc-400 mx-auto mb-2" />
                        <p className="text-sm text-zinc-500 dark:text-zinc-400">
                          {t("agent.noSkillsAvailable", "暂无可用技能")}
                        </p>
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 gap-2 max-h-[400px] overflow-y-auto p-1">
                        {availableSkills.map((skill) => {
                          const selectedBinding = skillBindings.find(
                            (binding) => binding.skill_id === skill.skill_id,
                          );
                          const isSelected = Boolean(selectedBinding);
                          const isLangChainTool =
                            skill.skill_type === "langchain_tool";
                          const isMcpTool =
                            skill.skill_type === "mcp_tool";

                          return (
                            <div
                              key={skill.skill_id}
                              className={`
                                p-3 rounded-lg border-2 text-left transition-all
                                ${
                                  isSelected
                                    ? "border-emerald-500 bg-emerald-500/10"
                                    : "border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 hover:border-emerald-500/50"
                                }
                              `}
                            >
                              <button
                                type="button"
                                onClick={() => toggleSkill(skill.skill_id)}
                                className="w-full text-left"
                              >
                              <div className="flex items-start gap-3">
                                {/* Checkbox */}
                                <div
                                  className={`
                                  w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 mt-0.5
                                  ${
                                    isSelected
                                      ? "border-emerald-500 bg-emerald-500"
                                      : "border-zinc-300 dark:border-zinc-600"
                                  }
                                `}
                                >
                                  {isSelected && (
                                    <svg
                                      className="w-3 h-3 text-white"
                                      fill="none"
                                      viewBox="0 0 24 24"
                                      stroke="currentColor"
                                    >
                                      <path
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                        strokeWidth={3}
                                        d="M5 13l4 4L19 7"
                                      />
                                    </svg>
                                  )}
                                </div>

                                {/* Skill Info */}
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2 mb-1">
                                    <h4 className="font-medium text-zinc-900 dark:text-zinc-100">
                                      {skill.display_name}
                                    </h4>
                                    <span className="text-xs text-zinc-500 dark:text-zinc-400 font-mono">
                                      {skill.skill_slug}
                                    </span>
                                    <span
                                      className={`
                                      px-2 py-0.5 text-xs font-medium rounded
                                      ${
                                        isMcpTool
                                          ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                                          : isLangChainTool
                                          ? "bg-blue-500/10 text-blue-700 dark:text-blue-400"
                                          : "bg-purple-500/10 text-purple-700 dark:text-purple-400"
                                      }
                                    `}
                                    >
                                      {isMcpTool
                                        ? t("skills.mcpTool", "MCP")
                                        : isLangChainTool
                                        ? t("skills.langchainTool")
                                        : t("skills.agentSkill")}
                                    </span>
                                    {selectedBinding && (
                                      <span className="px-2 py-0.5 text-xs font-medium rounded bg-emerald-500/10 text-emerald-700 dark:text-emerald-300">
                                        {getSkillBindingSourceLabel(
                                          selectedBinding.source,
                                        )}
                                      </span>
                                    )}
                                  </div>
                                  <p className="text-sm text-zinc-600 dark:text-zinc-400 line-clamp-2">
                                    {skill.description}
                                  </p>
                                  <p className="text-xs text-zinc-500 dark:text-zinc-500 mt-1">
                                    {skill.access_level}
                                    {skill.department_name
                                      ? ` · ${skill.department_name}`
                                      : ""}
                                  </p>
                                </div>
                              </div>
                              </button>

                              {selectedBinding &&
                                showAdvancedSkillBindings &&
                                bindingModeOptionsForSkill(skill).length > 1 && (
                                <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3 border-t border-emerald-500/20 pt-3">
                                  <label className="text-xs text-zinc-600 dark:text-zinc-300">
                                    <span className="mb-1 block font-medium">
                                      {t("agent.bindingMode", "绑定模式")}
                                    </span>
                                    <select
                                      value={selectedBinding.binding_mode}
                                      onChange={(event) =>
                                        updateSkillBinding(skill.skill_id, (binding) => ({
                                          ...binding,
                                          binding_mode: event.target
                                            .value as AgentSkillBindingMode,
                                        }))
                                      }
                                      className="w-full rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white/80 dark:bg-zinc-900/60 px-3 py-2"
                                    >
                                      {bindingModeOptionsForSkill(skill).map((mode) => (
                                        <option key={mode} value={mode}>
                                          {mode}
                                        </option>
                                      ))}
                                    </select>
                                  </label>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Model Config Tab */}
          {activeTab === "model" && (
            <div className="space-y-4">
              {/* Loading State */}
              {isLoadingProviders && (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-6 h-6 animate-spin text-emerald-500" />
                  <span className="ml-2 text-zinc-600 dark:text-zinc-400">
                    Loading providers...
                  </span>
                </div>
              )}

              {/* Error State */}
              {providersError && (
                <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-semibold text-red-700 dark:text-red-400">
                      {providersError}
                    </p>
                    <button
                      onClick={fetchAvailableProviders}
                      className="mt-2 text-sm text-red-600 dark:text-red-400 hover:underline"
                    >
                      Retry
                    </button>
                  </div>
                </div>
              )}

              {/* No Providers Available */}
              {!isLoadingProviders &&
                !providersError &&
                Object.keys(availableProviders).length === 0 && (
                  <div className="p-4 bg-yellow-500/10 border border-yellow-500/20 rounded-xl flex items-start gap-3">
                    <AlertCircle className="w-5 h-5 text-yellow-500 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-semibold text-yellow-700 dark:text-yellow-400">
                        No LLM providers configured
                      </p>
                      <p className="text-sm text-yellow-600 dark:text-yellow-500 mt-1">
                        Please configure at least one LLM provider in the system
                        settings.
                      </p>
                    </div>
                  </div>
                )}

              {/* Provider and Model Selection */}
              {!isLoadingProviders &&
                Object.keys(availableProviders).length > 0 && (
                  <>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                          {t("agent.selectProvider")}
                        </label>
                        <select
                          value={formData.provider}
                          onChange={(e) => handleProviderChange(e.target.value)}
                          className="w-full px-4 py-3 bg-zinc-500/5 border border-zinc-500/10 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500/20 text-zinc-800 dark:text-zinc-200"
                        >
                          <option value="">Select Provider</option>
                          {Object.keys(availableProviders).map(
                            (providerName) => (
                              <option key={providerName} value={providerName}>
                                {providerName}
                              </option>
                            ),
                          )}
                        </select>
                      </div>

                      <div>
                        <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                          {t("agent.selectModel")}
                        </label>
                        <select
                          value={formData.model}
                          onChange={(e) =>
                            setFormData({ ...formData, model: e.target.value })
                          }
                          disabled={!formData.provider}
                          className="w-full px-4 py-3 bg-zinc-500/5 border border-zinc-500/10 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500/20 text-zinc-800 dark:text-zinc-200 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          <option value="">Select Model</option>
                          {formData.provider &&
                            availableProviders[formData.provider]?.map(
                              (modelName) => (
                                <option key={modelName} value={modelName}>
                                  {modelName}
                                </option>
                              ),
                            )}
                        </select>
                        {!formData.provider && (
                          <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                            Select a provider first
                          </p>
                        )}
                      </div>
                    </div>

                    {/* Model Metadata Display */}
                    {isLoadingMetadata && (
                      <div className="flex items-center gap-2 p-3 bg-blue-500/10 border border-blue-500/20 rounded-xl">
                        <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                        <span className="text-sm text-blue-700 dark:text-blue-400">
                          Loading model information...
                        </span>
                      </div>
                    )}

                    {modelMetadata && !isLoadingMetadata && (
                      <div className="mt-2">
                        <ModelMetadataCard metadata={modelMetadata} />
                      </div>
                    )}

                    <div>
                      <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                        {t("agent.temperature")}:{" "}
                        {formData.temperature?.toFixed(1)}
                        {modelMetadata && (
                          <span className="ml-2 text-xs text-zinc-500 dark:text-zinc-400">
                            (recommended: {modelMetadata.default_temperature})
                          </span>
                        )}
                      </label>
                      <input
                        type="range"
                        min={modelMetadata?.temperature_range[0] ?? 0}
                        max={modelMetadata?.temperature_range[1] ?? 2}
                        step="0.1"
                        value={formData.temperature}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            temperature: parseFloat(e.target.value),
                          })
                        }
                        className="w-full"
                      />
                      <div className="flex justify-between text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                        <span>More focused</span>
                        <span>More creative</span>
                      </div>
                    </div>

                    <div>
                      <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                        {t("agent.maxTokens")} (Maximum Output Tokens)
                        {modelMetadata?.max_output_tokens && (
                          <span className="ml-2 text-xs text-zinc-500 dark:text-zinc-400">
                            (model max:{" "}
                            {modelMetadata.max_output_tokens.toLocaleString()})
                          </span>
                        )}
                      </label>
                      <input
                        type="number"
                        value={formData.maxTokens}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            maxTokens: parseInt(e.target.value) || 0,
                          })
                        }
                        min={1}
                        max={modelMetadata?.max_output_tokens}
                        className="w-full px-4 py-3 bg-zinc-500/5 border border-zinc-500/10 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500/20 text-zinc-800 dark:text-zinc-200"
                        placeholder="4096"
                      />
                      <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                        Maximum number of tokens in the model's response.
                        Default: 4096
                      </p>
                    </div>

                    <div>
                      <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                        {t("agent.topP")}: {formData.topP?.toFixed(1)}
                      </label>
                      <input
                        type="range"
                        min="0"
                        max="1"
                        step="0.1"
                        value={formData.topP}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            topP: parseFloat(e.target.value),
                          })
                        }
                        className="w-full"
                      />
                      <div className="flex justify-between text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                        <span>More deterministic</span>
                        <span>More diverse</span>
                      </div>
                    </div>
                  </>
                )}
            </div>
          )}

          {/* Knowledge Base Tab */}
          {activeTab === "knowledge" && (
            <div className="space-y-4">
              <div className="p-4 bg-blue-500/10 border border-blue-500/20 rounded-xl flex items-start gap-3 mb-4">
                <Info className="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-semibold text-blue-700 dark:text-blue-400 mb-1">
                    {t("agent.knowledgeBaseConfig", "知识库配置")}
                  </p>
                  <p className="text-xs text-blue-600 dark:text-blue-500">
                    {t(
                      "agent.knowledgeBaseConfigDesc",
                      "配置此代理可访问的知识库；Embedding 模型统一在知识库配置页维护。",
                    )}
                  </p>
                </div>
              </div>

              {/* Knowledge Base Access */}
              <div>
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t("agent.accessibleKnowledgeBases", "可访问的知识库")}
                </label>
                <div className="p-4 bg-zinc-500/5 border border-zinc-500/10 rounded-xl min-h-[120px]">
                  <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-3">
                    {formData.allowedKnowledge?.length || 0}{" "}
                    {t("agent.knowledgeBasesSelected", "个知识库已选择")}
                  </p>

                  {isLoadingKnowledgeBases && (
                    <div className="flex items-center gap-2 text-sm text-zinc-500 dark:text-zinc-400">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>
                        {t("agent.loadingKnowledgeBases", "加载知识库中...")}
                      </span>
                    </div>
                  )}

                  {!isLoadingKnowledgeBases && knowledgeBasesError && (
                    <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
                      <p className="text-sm text-red-700 dark:text-red-400">
                        {t("agent.knowledgeBasesLoadFailed", "知识库加载失败")}:{" "}
                        {knowledgeBasesError}
                      </p>
                      <button
                        type="button"
                        onClick={fetchKnowledgeBases}
                        className="mt-2 text-xs text-red-600 dark:text-red-400 hover:underline"
                      >
                        {t("common.retry", "重试")}
                      </button>
                    </div>
                  )}

                  {!isLoadingKnowledgeBases &&
                    !knowledgeBasesError &&
                    availableKnowledgeBases.length === 0 && (
                      <p className="text-xs text-zinc-500 dark:text-zinc-400">
                        {t(
                          "agent.noKnowledgeBasesAvailable",
                          "当前没有可用知识库，请先在知识库页面创建集合。",
                        )}
                      </p>
                    )}

                  {!isLoadingKnowledgeBases &&
                    !knowledgeBasesError &&
                    availableKnowledgeBases.length > 0 && (
                      <>
                        <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                          {availableKnowledgeBases.map((kb) => {
                            const isSelected = (
                              formData.allowedKnowledge || []
                            ).includes(kb.id);
                            return (
                              <button
                                key={kb.id}
                                type="button"
                                onClick={() => toggleKnowledgeBase(kb.id)}
                                className={`w-full text-left p-3 rounded-lg border transition-colors ${
                                  isSelected
                                    ? "border-emerald-500 bg-emerald-500/10"
                                    : "border-zinc-200 dark:border-zinc-700 hover:border-emerald-400/60"
                                }`}
                              >
                                <div className="flex items-start justify-between gap-3">
                                  <div className="min-w-0">
                                    <p className="text-sm font-semibold text-zinc-800 dark:text-zinc-200 truncate">
                                      {kb.name}
                                    </p>
                                    {kb.description && (
                                      <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1 line-clamp-2">
                                        {kb.description}
                                      </p>
                                    )}
                                  </div>
                                  <span className="text-xs px-2 py-1 rounded-full bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 whitespace-nowrap">
                                    {kb.itemCount}
                                  </span>
                                </div>
                              </button>
                            );
                          })}
                        </div>
                        <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-2">
                          {t(
                            "agent.knowledgeBaseAccessDesc",
                            "配置此代理可以查询的知识库。",
                          )}
                        </p>
                      </>
                    )}
                </div>
              </div>

              {/* Retrieval Settings */}
              <div>
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t("agent.topKResults", "Top K 结果数")}: {formData.topK || 5}
                </label>
                <input
                  type="range"
                  min="1"
                  max="20"
                  step="1"
                  value={formData.topK || 5}
                  onChange={(e) =>
                    setFormData({ ...formData, topK: parseInt(e.target.value) })
                  }
                  className="w-full"
                />
                <div className="flex justify-between text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                  <span>{t("agent.fewerResults", "更少结果（更快）")}</span>
                  <span>{t("agent.moreResults", "更多结果（更全面）")}</span>
                </div>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-2">
                  {t(
                    "agent.topKResultsDesc",
                    "每次查询从知识库检索的最相关文档数量。",
                  )}
                </p>
              </div>

              {/* Similarity Threshold */}
              <div>
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t("agent.similarityThreshold", "知识库最小相关度")}:{" "}
                  {(formData.similarityThreshold ?? 0.3).toFixed(2)}
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={formData.similarityThreshold ?? 0.3}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      similarityThreshold: parseFloat(e.target.value),
                    })
                  }
                  className="w-full"
                />
                <div className="flex justify-between text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                  <span>{t("agent.morePermissive", "更宽松 (0.0)")}</span>
                  <span>{t("agent.moreStrict", "更严格 (1.0)")}</span>
                </div>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-2">
                  {t(
                    "agent.similarityThresholdDesc",
                    "检索文档的最小相似度分数。较高的值仅返回高度相关的结果。",
                  )}
                </p>
              </div>
            </div>
          )}

          {/* Data Access Tab */}
          {activeTab === "access" && (
            <div className="space-y-4">
              <div className="p-4 bg-blue-500/10 border border-blue-500/20 rounded-xl">
                <p className="text-sm text-blue-700 dark:text-blue-400 font-medium">
                  {t(
                    "agent.accessLevelEffectiveRule",
                    "Sharing scope controls who can discover and use this agent. Knowledge base access is configured separately in the Knowledge tab.",
                  )}
                </p>
              </div>

              <div className="rounded-xl border border-zinc-500/10 bg-zinc-500/5 p-4">
                <p className="text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t("agent.accessLevel")}
                </p>
                <p className="text-sm text-zinc-700 dark:text-zinc-300">
                  {formData.accessLevel === "public"
                    ? t("agent.accessLevelPublic")
                    : formData.accessLevel === "department"
                      ? t("agent.accessLevelDepartment")
                      : t("agent.accessLevelPrivate")}
                </p>
                <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                  {t(
                    "agent.sharingScopeConfiguredInBasicTab",
                    "Change sharing scope in the Basic Information tab.",
                  )}
                </p>
              </div>

              <div>
                <label className="block text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t("agent.allowedKnowledge", "允许的知识库")}
                </label>
                <div className="p-4 bg-zinc-500/5 border border-zinc-500/10 rounded-xl min-h-[100px]">
                  <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-1">
                    {formData.allowedKnowledge?.length || 0}{" "}
                    {t("agent.knowledgeBasesSelected", "个知识库已选择")}
                  </p>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    {t(
                      "agent.allowedKnowledgeConfiguredInKnowledgeTab",
                      "知识库白名单请在“知识库”标签页中配置。",
                    )}
                  </p>
                </div>
              </div>

              <div className="p-4 bg-zinc-500/5 border border-zinc-500/10 rounded-xl">
                <p className="text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-2">
                  {t("agent.effectiveAccessSummaryTitle", "当前生效规则")}
                </p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-1">
                  {t(
                    "agent.effectiveKnowledgeRule",
                    "知识库：先按权限过滤，再应用允许的知识库白名单（未配置白名单则不额外限制）。",
                  )}
                </p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  {t(
                    "agent.effectiveMemoryRule",
                    "记忆：运行时默认同时检索技能经验与用户记忆；如需限制，请通过全局 memory config 控制。",
                  )}
                </p>
              </div>
            </div>
          )}

          {activeTab === "channels" && (
            <div className="space-y-4">
              <div className="rounded-xl border border-blue-500/20 bg-blue-500/10 p-4">
                <div className="flex items-start gap-3">
                  <Bot className="mt-0.5 h-5 w-5 flex-shrink-0 text-blue-500" />
                  <div>
                    <p className="text-sm font-semibold text-blue-700 dark:text-blue-400">
                      {t("agent.feishuChannelTitle", "飞书机器人发布")}
                    </p>
                    <p className="mt-1 text-xs text-blue-600 dark:text-blue-500">
                      {t(
                        "agent.feishuChannelDesc",
                        "为企业自建飞书应用保存凭证，通过长连接接收消息。无需配置 webhook、verification token 或 encrypt key。首次聊天仍需先发送用户识别码完成绑定。",
                      )}
                    </p>
                  </div>
                </div>
              </div>

              {isLoadingFeishuPublication ? (
                <div className="flex items-center justify-center py-10">
                  <Loader2 className="h-6 w-6 animate-spin text-emerald-500" />
                  <span className="ml-2 text-sm text-zinc-600 dark:text-zinc-400">
                    {t(
                      "agent.loadingFeishuPublication",
                      "加载飞书发布配置中...",
                    )}
                  </span>
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <div>
                      <label className="mb-2 block text-sm font-semibold text-zinc-700 dark:text-zinc-300">
                        {t("agent.feishuAppId", "App ID")}
                      </label>
                      <input
                        type="text"
                        value={feishuFormData.appId}
                        onChange={(event) =>
                          setFeishuFormData((prev) => ({
                            ...prev,
                            appId: event.target.value,
                          }))
                        }
                        className="w-full rounded-xl border border-zinc-500/10 bg-zinc-500/5 px-4 py-3 text-zinc-800 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 dark:text-zinc-200"
                      />
                    </div>

                    <div>
                      <label className="mb-2 block text-sm font-semibold text-zinc-700 dark:text-zinc-300">
                        {t("agent.feishuAppSecret", "App secret")}
                      </label>
                      <input
                        type="password"
                        value={feishuFormData.appSecret || ""}
                        placeholder={
                          feishuPublication?.hasAppSecret ? "••••••••" : ""
                        }
                        onChange={(event) =>
                          setFeishuFormData((prev) => ({
                            ...prev,
                            appSecret: event.target.value,
                          }))
                        }
                        className="w-full rounded-xl border border-zinc-500/10 bg-zinc-500/5 px-4 py-3 text-zinc-800 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 dark:text-zinc-200"
                      />
                      {feishuPublication?.hasAppSecret && (
                        <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
                          {t(
                            "agent.feishuAppSecretStored",
                            "A secret is already stored. Leave this blank to keep the current value.",
                          )}
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="rounded-xl border border-emerald-500/15 bg-emerald-500/5 p-4 text-sm text-zinc-600 dark:text-zinc-300">
                    {t(
                      "agent.feishuLongConnectionHint",
                      "当前模式为飞书长连接，仅支持企业自建应用。保存仅写入凭证；发布后才会启用渠道。发布时会自动保存当前填写的凭证。",
                    )}
                  </div>

                  <div className="rounded-xl border border-zinc-500/10 bg-zinc-500/5 p-4">
                    <div className="flex flex-wrap items-center gap-3 text-xs text-zinc-500 dark:text-zinc-400">
                      <span className="inline-flex items-center gap-1 rounded-full bg-zinc-100 px-2 py-1 dark:bg-zinc-800">
                        <Radio className="h-3.5 w-3.5" />
                        {t("agent.statusLabel", "Status")}:{" "}
                        {getFeishuPublicationStatusLabel(
                          feishuPublication?.status,
                        )}
                      </span>
                      <span className="inline-flex items-center gap-1 rounded-full bg-zinc-100 px-2 py-1 dark:bg-zinc-800">
                        <LinkIcon className="h-3.5 w-3.5" />
                        {t("agent.deliveryModeLabel", "Delivery mode")}:{" "}
                        {t(
                          "agent.feishuDeliveryModeLongConnection",
                          "long connection",
                        )}
                      </span>
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2 py-1 ${getFeishuConnectionStateTone(getFeishuConnectionState(feishuPublication))}`}
                      >
                        <Bot className="h-3.5 w-3.5" />
                        {t(
                          "agent.feishuConnectionStateLabel",
                          "Connection",
                        )}:{" "}
                        {getFeishuConnectionStateLabel(
                          getFeishuConnectionState(feishuPublication),
                        )}
                      </span>
                      <span>
                        {t("agent.channelIdentity", "Channel identity")}:{" "}
                        {feishuPublication?.channelIdentity || "—"}
                      </span>
                    </div>

                    <div className="mt-4 rounded-xl border border-zinc-500/10 bg-white/70 p-4 dark:bg-zinc-900/40">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
                            {t(
                              "agent.feishuConnectionPanelTitle",
                              "Long connection status",
                            )}
                          </p>
                          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                            {getFeishuConnectionSummary(feishuPublication)}
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => void fetchFeishuPublication()}
                          disabled={
                            isLoadingFeishuPublication ||
                            isSavingFeishuPublication
                          }
                          className="inline-flex items-center gap-2 rounded-xl border border-zinc-200 px-3 py-2 text-xs font-semibold text-zinc-600 transition-colors hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
                        >
                          <RefreshCw
                            className={`h-3.5 w-3.5 ${isLoadingFeishuPublication ? "animate-spin" : ""}`}
                          />
                          {t("agent.feishuRefreshStatus", "Refresh status")}
                        </button>
                      </div>

                      <div className="mt-4 grid grid-cols-1 gap-3 text-xs text-zinc-500 dark:text-zinc-400 md:grid-cols-2">
                        <p>
                          {t(
                            "agent.feishuConnectionLastUpdated",
                            "Status updated",
                          )}
                          :{" "}
                          {formatFeishuTimestamp(
                            feishuPublication?.connectionStatusUpdatedAt,
                          )}
                        </p>
                        <p>
                          {t(
                            "agent.feishuConnectionLastConnected",
                            "Last connected",
                          )}
                          :{" "}
                          {formatFeishuTimestamp(
                            feishuPublication?.lastConnectedAt,
                          )}
                        </p>
                        <p>
                          {t(
                            "agent.feishuConnectionLastEvent",
                            "Last event received",
                          )}
                          :{" "}
                          {formatFeishuTimestamp(
                            feishuPublication?.lastEventAt,
                          )}
                        </p>
                        <p>
                          {t(
                            "agent.feishuConnectionLastError",
                            "Last error time",
                          )}
                          :{" "}
                          {formatFeishuTimestamp(
                            feishuPublication?.lastErrorAt,
                          )}
                        </p>
                      </div>

                      {feishuPublication?.lastErrorMessage && (
                        <div className="mt-4 rounded-xl border border-red-500/20 bg-red-500/10 p-3">
                          <p className="text-xs font-semibold text-red-700 dark:text-red-400">
                            {t(
                              "agent.feishuConnectionErrorTitle",
                              "Latest connection error",
                            )}
                          </p>
                          <p className="mt-1 break-all text-xs text-red-600 dark:text-red-300">
                            {feishuPublication.lastErrorMessage}
                          </p>
                        </div>
                      )}
                    </div>

                    <div className="mt-4 flex flex-wrap gap-3">
                      <button
                        type="button"
                        onClick={() => void handleSaveFeishuPublication()}
                        disabled={isSavingFeishuPublication}
                        className="inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {isSavingFeishuPublication ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Save className="h-4 w-4" />
                        )}
                        {t("agent.saveChannelConfig", "Save credentials")}
                      </button>
                      <button
                        type="button"
                        onClick={() => void handlePublishFeishuPublication()}
                        disabled={isSavingFeishuPublication}
                        className="inline-flex items-center gap-2 rounded-xl border border-zinc-200 px-4 py-2 text-sm font-semibold text-zinc-700 transition-colors hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
                      >
                        <LinkIcon className="h-4 w-4" />
                        {t("agent.publishChannel", "Enable channel")}
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleUnpublishFeishuPublication()}
                        disabled={isSavingFeishuPublication}
                        className="inline-flex items-center gap-2 rounded-xl border border-red-200 px-4 py-2 text-sm font-semibold text-red-600 transition-colors hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-red-900/40 dark:hover:bg-red-950/30"
                      >
                        <Power className="h-4 w-4" />
                        {t("agent.unpublishChannel", "Disable channel")}
                      </button>
                    </div>

                    <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
                      {t(
                        "agent.feishuStatusAutoRefresh",
                        "The status panel refreshes automatically every 5 seconds while this tab is open.",
                      )}
                    </p>
                  </div>

                  {feishuError && (
                    <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4">
                      <p className="text-sm text-red-700 dark:text-red-400">
                        {feishuError}
                      </p>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex flex-col gap-3 pt-4 border-t border-zinc-200 dark:border-zinc-700">
          {/* Save Error Display */}
          {saveError && (
            <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-xl flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-semibold text-red-700 dark:text-red-400">
                  Failed to save configuration
                </p>
                <p className="text-xs text-red-600 dark:text-red-500 mt-1">
                  {saveError}
                </p>
              </div>
              <button
                onClick={() => setSaveError(null)}
                className="text-red-500 hover:text-red-600"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

          <div className="flex justify-end gap-3">
            <button
              onClick={onClose}
              disabled={isSaving}
              className="px-6 py-3 bg-zinc-500/5 hover:bg-zinc-500/10 text-zinc-700 dark:text-zinc-300 rounded-xl font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {t("common.cancel")}
            </button>
            <button
              onClick={handleSave}
              disabled={isSaving}
              className="px-6 py-3 bg-emerald-500 hover:bg-emerald-600 text-white rounded-xl font-semibold transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSaving ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  {t("common.save")}
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Image Crop Modal */}
      <ImageCropModal
        isOpen={isAvatarCropModalOpen}
        onClose={() => setIsAvatarCropModalOpen(false)}
        onCropComplete={handleAvatarCropComplete}
        aspectRatio={1}
        title={t("agent.cropAvatar")}
      />
    </LayoutModal>
  );
};
