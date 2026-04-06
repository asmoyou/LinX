/**
 * Skills API client
 * Handles all skill-related API calls
 */

import apiClient, { getAuthToken } from "./client";
import type { AgentSkillSummary } from "../types/agent";

export interface SkillMetadata {
  emoji?: string;
  requires?: {
    bins?: string[];
    env?: string[];
    config?: string[];
  };
  os?: string[];
}

export interface SkillPackageStatus {
  package_missing: boolean;
  fallback_mode: boolean;
  limited_files: boolean;
  message?: string | null;
}

export type SkillAccessLevel = "private" | "team" | "public";

export interface Skill {
  skill_id: string;
  skill_slug: string;
  display_name: string;
  description: string;
  version: string;
  access_level: SkillAccessLevel;
  department_id?: string | null;
  department_name?: string | null;
  source_kind?: string | null;
  artifact_kind?: string | null;
  runtime_mode?: string | null;
  lifecycle_state?: string | null;
  active_revision_id?: string | null;
  can_edit?: boolean;
  can_delete?: boolean;
  can_publish_public?: boolean;
  skill_type?: string;
  storage_type?: string;
  storage_path?: string;
  code?: string | null;
  config?: Record<string, any>;
  manifest?: Record<string, any>;
  is_active?: boolean;
  execution_count?: number;
  last_executed_at?: string;
  average_execution_time?: number;
  updated_at?: string;
  interface_definition: {
    inputs: Record<string, string>;
    outputs: Record<string, string>;
    required_inputs?: string[];
  };
  dependencies: string[];
  created_at: string;
  created_by?: string;
  skill_md_content?: string;
  homepage?: string;
  metadata?: SkillMetadata;
  skill_metadata?: SkillMetadata;
  gating_status?: {
    eligible: boolean;
    missing_bins?: string[];
    missing_env?: string[];
    missing_config?: string[];
    os_compatible?: boolean;
    reason?: string;
  };
}

export interface StoreSkill extends Skill {
  is_installed: boolean;
  installed_skill_id?: string | null;
  installed_skill_slug?: string | null;
  installed_binding_count?: number;
}

export interface SkillInstallResult {
  installed_skill_id: string;
  installed_skill_slug: string;
  canonical_skill_id: string;
  source: string;
}

export interface CreateSkillRequest {
  display_name: string;
  skill_slug?: string;
  description?: string;
  skill_type?: string;
  code?: string;
  config?: Record<string, any>;
  dependencies?: string[];
  version?: string;
  access_level?: SkillAccessLevel;
  department_id?: string;
  package_file?: File;
}

export interface UpdateSkillRequest {
  display_name?: string;
  description?: string;
  code?: string;
  dependencies?: string[];
  access_level?: SkillAccessLevel;
  department_id?: string | null;
  is_active?: boolean;
}

export interface SkillShareTarget {
  department_id: string;
  name: string;
}

export interface SkillShareTargetsResponse {
  can_publish_public: boolean;
  default_department_id?: string | null;
  allowed_department_targets: SkillShareTarget[];
}

export interface SkillTestRequest {
  inputs?: Record<string, any>;
  natural_language_input?: string;
  agent_id?: string;
}

export interface SkillTestStreamChunk {
  type: string;
  content?: string;
  result?: any;
  success?: boolean;
  session_id?: string;
  sandbox_id?: string;
  workspace_root?: string;
  synced_skill_files?: number;
  [key: string]: any;
}

export interface SkillOverviewStats {
  total_skills: number;
  active_skills: number;
  inactive_skills: number;
  agent_skills: number;
  langchain_tool_skills: number;
  skills_with_dependencies: number;
  total_execution_count: number;
  average_execution_time: number;
  last_executed_at?: string | null;
}

export interface ListSkillsRequest {
  limit?: number;
  offset?: number;
  includeCode?: boolean;
  query?: string;
  sourceKind?: string;
}

export interface PaginatedSkillsResponse {
  items: Skill[];
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
}

export type SkillCandidateStatus =
  | "pending"
  | "published"
  | "rejected"
  | "revise"
  | string;

export interface SkillCandidate {
  candidate_id: string;
  title: string;
  summary: string;
  content: string;
  status: SkillCandidateStatus;
  tags: string[];
  skill_id?: string | null;
  skill_slug?: string | null;
  skill_type?: string | null;
  source_memory_id?: string | null;
  source_agent_id?: string | null;
  source_agent_name?: string | null;
  review_note?: string | null;
  created_at: string;
  updated_at?: string | null;
  metadata?: Record<string, any>;
}

export interface ListSkillCandidatesRequest {
  status?: SkillCandidateStatus | "all";
  query?: string;
  limit?: number;
}

export interface SkillBinding {
  binding_id: string;
  owner_id: string;
  owner_name: string;
  owner_type: string;
  skill_id: string;
  skill_slug: string;
  display_name: string;
  skill_type?: string | null;
  artifact_kind?: string | null;
  runtime_mode?: string | null;
  binding_mode?: string | null;
  enabled?: boolean;
  priority?: number;
  source?: string | null;
  auto_update_policy?: string | null;
  revision_pin_id?: string | null;
  access_level?: SkillAccessLevel;
  department_name?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ListSkillBindingsRequest {
  owner_type?: string;
  owner_id?: string;
  limit?: number;
}

export type AgentSkillBindingMode =
  | "tool"
  | "doc"
  | "retrieval"
  | "hybrid";

export type AgentSkillAutoUpdatePolicy = "follow_active" | "pin_revision";

export interface AgentSkillBindingDraft {
  skill_id: string;
  binding_mode: AgentSkillBindingMode;
  enabled: boolean;
  priority: number;
  source: string;
  auto_update_policy: AgentSkillAutoUpdatePolicy;
  revision_pin_id?: string | null;
}

export interface AgentSkillBindingConfig {
  owner_id: string;
  owner_type: "agent";
  bindings: AgentSkillBindingDraft[];
  available_skills: AgentSkillSummary[];
}

const asRecord = (value: unknown): Record<string, any> => {
  if (value && typeof value === "object") {
    return value as Record<string, any>;
  }
  return {};
};

const asOptionalString = (value: unknown): string | null => {
  if (typeof value !== "string") {
    return null;
  }
  const normalized = value.trim();
  return normalized ? normalized : null;
};

const asStringArray = (value: unknown): string[] => {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string");
};

const normalizeSkillCandidate = (raw: unknown): SkillCandidate => {
  const record = asRecord(raw);
  const metadata = asRecord(record.metadata);
  const title =
    asOptionalString(record.title) ||
    asOptionalString(record.summary) ||
    asOptionalString(record.display_name) ||
    asOptionalString(record.skill_slug) ||
    "Untitled candidate";
  const summary =
    asOptionalString(record.summary) ||
    asOptionalString(record.description) ||
    asOptionalString(record.content) ||
    title;

  return {
    candidate_id: String(record.candidate_id || record.id || ""),
    title,
    summary,
    content:
      asOptionalString(record.content) ||
      asOptionalString(record.description) ||
      summary,
    status:
      asOptionalString(record.status) ||
      asOptionalString(record.review_status) ||
      asOptionalString(metadata.review_status) ||
      "pending",
    tags: asStringArray(record.tags),
    skill_id:
      asOptionalString(record.skill_id) || asOptionalString(metadata.skill_id),
    skill_slug:
      asOptionalString(record.skill_slug) ||
      asOptionalString(metadata.skill_slug),
    skill_type:
      asOptionalString(record.skill_type) ||
      asOptionalString(metadata.skill_type),
    source_memory_id:
      asOptionalString(record.source_memory_id) ||
      asOptionalString(metadata.source_memory_id) ||
      asOptionalString(metadata.memory_id),
    source_agent_id:
      asOptionalString(record.source_agent_id) ||
      asOptionalString(record.agent_id) ||
      asOptionalString(record.agentId) ||
      asOptionalString(metadata.agent_id),
    source_agent_name:
      asOptionalString(record.source_agent_name) ||
      asOptionalString(record.agent_name) ||
      asOptionalString(record.agentName) ||
      asOptionalString(metadata.agent_name),
    review_note:
      asOptionalString(record.review_note) ||
      asOptionalString(metadata.review_note),
    created_at:
      asOptionalString(record.created_at) ||
      asOptionalString(record.createdAt) ||
      "",
    updated_at:
      asOptionalString(record.updated_at) || asOptionalString(record.updatedAt),
    metadata,
  };
};

const normalizeSkillBinding = (raw: unknown): SkillBinding => {
  const record = asRecord(raw);
  const owner = asRecord(record.owner);
  const skill = asRecord(record.skill);

  return {
    binding_id: String(
      record.binding_id ||
        record.id ||
        `${record.owner_id || owner.id || ""}:${record.skill_id || skill.skill_id || ""}`,
    ),
    owner_id: String(record.owner_id || record.target_id || owner.id || ""),
    owner_name:
      asOptionalString(record.owner_name) ||
      asOptionalString(record.target_name) ||
      asOptionalString(owner.name) ||
      "Unknown owner",
    owner_type:
      asOptionalString(record.owner_type) ||
      asOptionalString(record.target_type) ||
      asOptionalString(owner.type) ||
      "agent",
    skill_id: String(record.skill_id || skill.skill_id || skill.id || ""),
    skill_slug:
      asOptionalString(record.skill_slug) ||
      asOptionalString(skill.skill_slug) ||
      "",
    display_name:
      asOptionalString(record.display_name) ||
      asOptionalString(record.skill_name) ||
      asOptionalString(skill.display_name) ||
      asOptionalString(skill.name) ||
      "Unnamed skill",
    skill_type:
      asOptionalString(record.skill_type) || asOptionalString(skill.skill_type),
    artifact_kind:
      asOptionalString(record.artifact_kind) ||
      asOptionalString(skill.artifact_kind),
    runtime_mode:
      asOptionalString(record.runtime_mode) ||
      asOptionalString(skill.runtime_mode),
    binding_mode:
      asOptionalString(record.binding_mode) ||
      asOptionalString(record.mode),
    enabled: typeof record.enabled === "boolean" ? record.enabled : true,
    priority:
      typeof record.priority === "number"
        ? record.priority
        : Number(record.priority || 0),
    source:
      asOptionalString(record.source) || asOptionalString(record.binding_source),
    auto_update_policy:
      asOptionalString(record.auto_update_policy) ||
      asOptionalString(record.autoUpdatePolicy),
    revision_pin_id:
      asOptionalString(record.revision_pin_id) ||
      asOptionalString(record.revisionPinId),
    access_level: (record.access_level || skill.access_level) as
      | SkillAccessLevel
      | undefined,
    department_name:
      asOptionalString(record.department_name) ||
      asOptionalString(skill.department_name),
    created_at:
      asOptionalString(record.created_at) || asOptionalString(record.createdAt),
    updated_at:
      asOptionalString(record.updated_at) || asOptionalString(record.updatedAt),
  };
};

const normalizeStoreSkill = (raw: unknown): StoreSkill => {
  const record = asRecord(raw);

  return {
    skill_id: String(record.skill_id || record.skillId || ""),
    skill_slug:
      asOptionalString(record.skill_slug) || asOptionalString(record.skillSlug) || "",
    display_name:
      asOptionalString(record.display_name) ||
      asOptionalString(record.displayName) ||
      "Unnamed skill",
    description: asOptionalString(record.description) || "",
    version: asOptionalString(record.version) || "1.0.0",
    access_level: (record.access_level || record.accessLevel || "private") as SkillAccessLevel,
    department_id:
      asOptionalString(record.department_id) || asOptionalString(record.departmentId),
    department_name:
      asOptionalString(record.department_name) || asOptionalString(record.departmentName),
    source_kind:
      asOptionalString(record.source_kind) || asOptionalString(record.sourceKind),
    artifact_kind:
      asOptionalString(record.artifact_kind) || asOptionalString(record.artifactKind),
    runtime_mode:
      asOptionalString(record.runtime_mode) || asOptionalString(record.runtimeMode),
    lifecycle_state:
      asOptionalString(record.lifecycle_state) || asOptionalString(record.lifecycleState),
    active_revision_id:
      asOptionalString(record.active_revision_id) || asOptionalString(record.activeRevisionId),
    can_edit: typeof record.can_edit === "boolean" ? record.can_edit : Boolean(record.canEdit),
    can_delete:
      typeof record.can_delete === "boolean" ? record.can_delete : Boolean(record.canDelete),
    can_publish_public:
      typeof record.can_publish_public === "boolean"
        ? record.can_publish_public
        : Boolean(record.canPublishPublic),
    skill_type:
      asOptionalString(record.skill_type) || asOptionalString(record.skillType) || undefined,
    storage_type:
      asOptionalString(record.storage_type) || asOptionalString(record.storageType) || undefined,
    storage_path:
      asOptionalString(record.storage_path) || asOptionalString(record.storagePath) || undefined,
    code: asOptionalString(record.code),
    config: asRecord(record.config),
    manifest: asRecord(record.manifest),
    is_active: typeof record.is_active === "boolean" ? record.is_active : undefined,
    execution_count:
      typeof record.execution_count === "number"
        ? record.execution_count
        : typeof record.executionCount === "number"
          ? record.executionCount
          : undefined,
    last_executed_at:
      asOptionalString(record.last_executed_at) || asOptionalString(record.lastExecutedAt) || undefined,
    average_execution_time:
      typeof record.average_execution_time === "number"
        ? record.average_execution_time
        : typeof record.averageExecutionTime === "number"
          ? record.averageExecutionTime
          : undefined,
    updated_at:
      asOptionalString(record.updated_at) || asOptionalString(record.updatedAt) || undefined,
    interface_definition: (record.interface_definition || record.interfaceDefinition || {
      inputs: {},
      outputs: {},
    }) as Skill["interface_definition"],
    dependencies: asStringArray(record.dependencies),
    created_at:
      asOptionalString(record.created_at) || asOptionalString(record.createdAt) || "",
    created_by:
      asOptionalString(record.created_by) || asOptionalString(record.createdBy) || undefined,
    skill_md_content:
      asOptionalString(record.skill_md_content) || asOptionalString(record.skillMdContent) || undefined,
    homepage: asOptionalString(record.homepage) || undefined,
    metadata: asRecord(record.metadata),
    skill_metadata:
      Object.keys(asRecord(record.skill_metadata)).length > 0
        ? asRecord(record.skill_metadata)
        : Object.keys(asRecord(record.skillMetadata)).length > 0
          ? asRecord(record.skillMetadata)
          : undefined,
    gating_status:
      Object.keys(asRecord(record.gating_status)).length > 0
        ? asRecord(record.gating_status) as Skill["gating_status"]
        : Object.keys(asRecord(record.gatingStatus)).length > 0
          ? asRecord(record.gatingStatus) as Skill["gating_status"]
          : undefined,
    is_installed:
      typeof record.is_installed === "boolean"
        ? record.is_installed
        : Boolean(record.isInstalled),
    installed_skill_id:
      asOptionalString(record.installed_skill_id) || asOptionalString(record.installedSkillId),
    installed_skill_slug:
      asOptionalString(record.installed_skill_slug) || asOptionalString(record.installedSkillSlug),
    installed_binding_count:
      typeof record.installed_binding_count === "number"
        ? record.installed_binding_count
        : typeof record.installedBindingCount === "number"
          ? record.installedBindingCount
          : 0,
  };
};

export const skillsApi = {
  async getCandidates(
    params?: ListSkillCandidatesRequest,
  ): Promise<SkillCandidate[]> {
    const response = await apiClient.get<unknown[]>("/skills/candidates", {
      params,
    });
    return response.data.map((item) => normalizeSkillCandidate(item));
  },

  async promoteCandidate(
    candidateId: string,
    data?: { auto_bind_source_agent?: boolean },
  ): Promise<SkillCandidate> {
    const response = await apiClient.post(
      `/skills/candidates/${candidateId}/promote`,
      data || {},
    );
    return normalizeSkillCandidate(response.data);
  },

  async mergeCandidate(
    candidateId: string,
    data: { targetSkillId: string; auto_bind_source_agent?: boolean },
  ): Promise<SkillCandidate> {
    const response = await apiClient.post(
      `/skills/candidates/${candidateId}/merge`,
      data,
    );
    return normalizeSkillCandidate(response.data);
  },

  async rejectCandidate(
    candidateId: string,
    data?: { note?: string },
  ): Promise<SkillCandidate> {
    const response = await apiClient.post(
      `/skills/candidates/${candidateId}/reject`,
      data || {},
    );
    return normalizeSkillCandidate(response.data);
  },

  async deleteCandidate(candidateId: string): Promise<void> {
    await apiClient.delete(`/skills/candidates/${candidateId}`);
  },

  async getBindings(
    params?: ListSkillBindingsRequest,
  ): Promise<SkillBinding[]> {
    const response = await apiClient.get<unknown[]>("/skills/bindings", {
      params,
    });
    return response.data.map((item) => normalizeSkillBinding(item));
  },

  async getAgentBindings(agentId: string): Promise<AgentSkillBindingConfig> {
    const response = await apiClient.get<AgentSkillBindingConfig>(
      `/skills/bindings/agents/${agentId}`,
    );
    return {
      owner_id: response.data.owner_id || agentId,
      owner_type: "agent",
      bindings: (response.data.bindings || []).map((binding, index) => ({
        skill_id: binding.skill_id,
        binding_mode: binding.binding_mode || "doc",
        enabled:
          typeof binding.enabled === "boolean" ? binding.enabled : true,
        priority:
          typeof binding.priority === "number" ? binding.priority : index,
        source: binding.source || "manual",
        auto_update_policy:
          binding.auto_update_policy || "follow_active",
        revision_pin_id: binding.revision_pin_id || null,
      })),
      available_skills: response.data.available_skills || [],
    };
  },

  async updateAgentBindings(
    agentId: string,
    bindings: AgentSkillBindingDraft[],
  ): Promise<void> {
    await apiClient.put(`/skills/bindings/agents/${agentId}`, {
      bindings,
    });
  },

  async getStore(): Promise<StoreSkill[]> {
    const response = await apiClient.get<StoreSkill[]>("/skills/store");
    return response.data.map((item) => normalizeStoreSkill(item));
  },

  async installSkill(skillId: string): Promise<SkillInstallResult> {
    const response = await apiClient.post<SkillInstallResult>(`/skills/${skillId}/install`);
    const record = asRecord(response.data);
    return {
      installed_skill_id:
        asOptionalString(record.installed_skill_id) ||
        asOptionalString(record.installedSkillId) ||
        "",
      installed_skill_slug:
        asOptionalString(record.installed_skill_slug) ||
        asOptionalString(record.installedSkillSlug) ||
        "",
      canonical_skill_id:
        asOptionalString(record.canonical_skill_id) ||
        asOptionalString(record.canonicalSkillId) ||
        skillId,
      source: asOptionalString(record.source) || "curated_install",
    };
  },

  async uninstallSkill(skillId: string): Promise<void> {
    await apiClient.delete(`/skills/${skillId}/install`);
  },

  async listPage({
    limit = 24,
    offset = 0,
    includeCode = false,
    query,
    sourceKind,
  }: ListSkillsRequest = {}): Promise<PaginatedSkillsResponse> {
    const normalizedQuery = query?.trim();
    const response = await apiClient.get<Skill[]>(
      normalizedQuery ? "/skills/search" : "/skills",
      {
        params: normalizedQuery
          ? {
              query: normalizedQuery,
              limit,
              offset,
              include_code: includeCode,
              source_kind: sourceKind,
            }
          : {
              limit,
              offset,
              include_code: includeCode,
              source_kind: sourceKind,
            },
      },
    );

    const totalHeader = Number(response.headers["x-total-count"]);
    const hasMoreHeader = response.headers["x-has-more"];
    const total = Number.isFinite(totalHeader) ? totalHeader : response.data.length;
    const hasMore =
      typeof hasMoreHeader === "string"
        ? hasMoreHeader === "true"
        : offset + response.data.length < total;

    return {
      items: response.data,
      total,
      limit,
      offset,
      hasMore,
    };
  },

  /**
   * Get all skills
   */
  async getAll(limit = 100, offset = 0, includeCode = false): Promise<Skill[]> {
    const response = await apiClient.get<Skill[]>("/skills", {
      params: { limit, offset, include_code: includeCode },
    });
    return response.data;
  },

  /**
   * Get skill by ID
   */
  async getById(skillId: string, includeCode = true): Promise<Skill> {
    const response = await apiClient.get<Skill>(`/skills/${skillId}`, {
      params: { include_code: includeCode },
    });
    return response.data;
  },

  /**
   * Search skills
   */
  async search(
    query: string,
    limit = 100,
    offset = 0,
    includeCode = false,
  ): Promise<Skill[]> {
    const response = await apiClient.get<Skill[]>("/skills/search", {
      params: { query, limit, offset, include_code: includeCode },
    });
    return response.data;
  },

  /**
   * Create new skill
   */
  async create(data: CreateSkillRequest): Promise<Skill> {
    // Always use multipart/form-data for consistency
    const formData = new FormData();
    formData.append("display_name", data.display_name);
    if (data.skill_slug) formData.append("skill_slug", data.skill_slug);
    if (typeof data.description === "string" && data.description.trim()) {
      formData.append("description", data.description.trim());
    }
    if (data.skill_type) formData.append("skill_type", data.skill_type);
    if (data.version) formData.append("version", data.version);
    if (data.access_level) formData.append("access_level", data.access_level);
    if (data.department_id)
      formData.append("department_id", data.department_id);
    if (data.package_file) formData.append("package_file", data.package_file);
    if (data.code) formData.append("code", data.code);
    if (data.config) formData.append("config", JSON.stringify(data.config));
    if (data.dependencies && data.dependencies.length > 0) {
      formData.append("dependencies", JSON.stringify(data.dependencies));
    }

    const response = await apiClient.post<Skill>("/skills", formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    });
    return response.data;
  },

  /**
   * Update skill
   */
  async update(skillId: string, data: UpdateSkillRequest): Promise<Skill> {
    const response = await apiClient.put<Skill>(`/skills/${skillId}`, data);
    return response.data;
  },

  /**
   * Delete skill
   */
  async delete(skillId: string): Promise<void> {
    await apiClient.delete(`/skills/${skillId}`);
  },

  /**
   * Get skill templates
   */
  async getTemplates(category?: string): Promise<any[]> {
    const response = await apiClient.get("/skills/templates", {
      params: category ? { category } : undefined,
    });
    return response.data;
  },

  /**
   * Create skill from template
   */
  async createFromTemplate(
    templateId: string,
    displayName: string,
    description?: string,
    skillSlug?: string,
    accessLevel?: SkillAccessLevel,
    departmentId?: string,
  ): Promise<Skill> {
    const response = await apiClient.post("/skills/from-template", {
      template_id: templateId,
      display_name: displayName,
      description,
      skill_slug: skillSlug,
      access_level: accessLevel,
      department_id: departmentId,
    });
    return response.data;
  },

  async getShareTargets(): Promise<SkillShareTargetsResponse> {
    const response = await apiClient.get<SkillShareTargetsResponse>(
      "/skills/share-targets",
    );
    return response.data;
  },

  /**
   * Test skill execution
   * For langchain_tool: Pass structured inputs
   * For agent_skill: Pass natural_language_input and required agent_id
   */
  async testSkill(skillId: string, params: SkillTestRequest): Promise<any> {
    const response = await apiClient.post(`/skills/${skillId}/test`, params);
    return response.data;
  },

  /**
   * Test agent_skill execution with streaming SSE events.
   */
  async testSkillStream(
    skillId: string,
    params: SkillTestRequest,
    onChunk: (chunk: SkillTestStreamChunk) => void,
    onError?: (error: string) => void,
    onComplete?: () => void,
    signal?: AbortSignal,
  ): Promise<void> {
    try {
      const token = getAuthToken();

      const url = `${apiClient.defaults.baseURL}/skills/${skillId}/test?stream=true`;
      const response = await fetch(url, {
        method: "POST",
        headers: {
          Accept: "text/event-stream",
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(params),
        signal,
      });

      if (!response.ok) {
        const errorText = await response.text();
        let errorMessage = "Failed to test skill";

        try {
          const errorData = JSON.parse(errorText);
          errorMessage = errorData.message || errorData.detail || errorMessage;
        } catch {
          errorMessage = errorText || errorMessage;
        }

        if (onError) onError(errorMessage);
        throw new Error(errorMessage);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        const error = "No response body";
        if (onError) onError(error);
        throw new Error(error);
      }

      try {
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            if (onComplete) onComplete();
            break;
          }

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) {
              continue;
            }
            try {
              const data = JSON.parse(line.slice(6));
              onChunk(data);
            } catch (e) {
              console.error("Failed to parse skill SSE data:", line, e);
            }
          }
        }
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") {
          return;
        }
        const errorMessage =
          error instanceof Error ? error.message : "Unknown error";
        if (onError) onError(errorMessage);
        throw error;
      } finally {
        reader.releaseLock();
      }
    } catch (error: any) {
      if (error?.name === "AbortError") {
        return;
      }
      const errorMessage = error?.message || "Failed to test skill";
      if (onError) onError(errorMessage);
      throw error;
    }
  },

  /**
   * Activate skill
   */
  async activateSkill(skillId: string): Promise<void> {
    await apiClient.post(`/skills/${skillId}/activate`);
  },

  /**
   * Deactivate skill
   */
  async deactivateSkill(skillId: string): Promise<void> {
    await apiClient.post(`/skills/${skillId}/deactivate`);
  },

  /**
   * Get skills library overview statistics
   */
  async getOverviewStats(): Promise<SkillOverviewStats> {
    const response = await apiClient.get<SkillOverviewStats>(
      "/skills/stats/overview",
    );
    return response.data;
  },

  /**
   * Get skill execution statistics
   */
  async getStats(skillId: string): Promise<any> {
    const response = await apiClient.get(`/skills/${skillId}/stats`);
    return response.data;
  },

  /**
   * Validate skill code
   */
  async validateCode(code: string): Promise<any> {
    const response = await apiClient.post("/skills/validate", { code });
    return response.data;
  },

  /**
   * Download package template
   */
  async downloadPackageTemplate(): Promise<Blob> {
    const response = await apiClient.get("/skills/templates/package-example", {
      responseType: "blob",
    });
    return response.data;
  },

  /**
   * List environment variable keys for current user
   */
  async listEnvVars(): Promise<string[]> {
    const response = await apiClient.get<string[]>("/skills/env-vars");
    return response.data;
  },

  /**
   * Set environment variable for current user
   */
  async setEnvVar(key: string, value: string): Promise<{ message: string }> {
    const response = await apiClient.post<{ message: string }>(
      "/skills/env-vars",
      {
        key,
        value,
      },
    );
    return response.data;
  },

  /**
   * Delete environment variable for current user
   */
  async deleteEnvVar(key: string): Promise<void> {
    await apiClient.delete(`/skills/env-vars/${key}`);
  },

  /**
   * Get file list for agent_skill package
   */
  async getFiles(skillId: string): Promise<{
    skill_id: string;
    skill_slug: string;
    display_name: string;
    skill_type: string;
    files: FileTreeItem[];
    package_status: SkillPackageStatus;
  }> {
    const response = await apiClient.get(`/skills/${skillId}/files`);
    return response.data;
  },

  /**
   * Get content of a specific file in agent_skill package
   */
  async getFileContent(
    skillId: string,
    filePath: string,
  ): Promise<{
    skill_id: string;
    file_path: string;
    file_name: string;
    content: string;
    size: number;
    extension: string;
    package_status: SkillPackageStatus;
  }> {
    const response = await apiClient.get(
      `/skills/${skillId}/files/${filePath}`,
    );
    return response.data;
  },

  /**
   * Update file content in agent_skill package (TODO: Backend implementation needed)
   */
  async updateFileContent(
    skillId: string,
    filePath: string,
    content: string,
  ): Promise<void> {
    await apiClient.put(`/skills/${skillId}/files/${filePath}`, { content });
  },

  /**
   * Re-upload package for agent_skill (TODO: Backend implementation needed)
   */
  async updatePackage(skillId: string, formData: FormData): Promise<void> {
    await apiClient.put(`/skills/${skillId}/package`, formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    });
  },
};

export interface FileTreeItem {
  name: string;
  path: string;
  type: "file" | "directory";
  file_type?: "python" | "text" | "config" | "script" | "other";
  size?: number;
  children?: FileTreeItem[];
}
