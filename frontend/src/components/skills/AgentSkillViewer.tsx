/**
 * Agent Skill Viewer Component
 * Displays agent_skill package files with a file tree on the left and content on the right
 * Similar to Manus interface
 * Supports both view and edit modes
 */

import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  X,
  File,
  Folder,
  FolderOpen,
  ChevronRight,
  ChevronDown,
  Loader2,
  Edit2,
  Save,
  Upload,
  AlertTriangle,
} from "lucide-react";
import {
  skillsApi,
  type FileTreeItem,
  type Skill,
  type SkillAccessLevel,
  type SkillShareTargetsResponse,
  type SkillPackageStatus,
} from "@/api/skills";
import { LayoutModal } from "@/components/LayoutModal";
import { ModalPanel } from "@/components/ModalPanel";
import { FileCodePreview } from "@/components/common/FileCodePreview";
import toast from "react-hot-toast";

interface AgentSkillViewerProps {
  isOpen: boolean;
  onClose: () => void;
  skill: Skill;
  mode?: "view" | "edit";
  onUpdate?: () => void | Promise<void>;
}

interface ApiErrorLike {
  response?: {
    data?: {
      detail?: string;
      message?: string;
    };
  };
  message?: string;
}

function getApiErrorMessage(error: unknown, fallback: string): string {
  if (typeof error === "object" && error !== null) {
    const typedError = error as ApiErrorLike;
    return (
      typedError.response?.data?.detail ||
      typedError.response?.data?.message ||
      typedError.message ||
      fallback
    );
  }
  return fallback;
}

function findFileByName(
  items: FileTreeItem[],
  name: string,
): FileTreeItem | null {
  for (const item of items) {
    if (item.type === "file" && item.name === name) {
      return item;
    }
    if (item.type === "directory" && item.children) {
      const found = findFileByName(item.children, name);
      if (found) return found;
    }
  }
  return null;
}

const AgentSkillViewer: React.FC<AgentSkillViewerProps> = ({
  isOpen,
  onClose,
  skill,
  mode = "view",
  onUpdate,
}) => {
  const { t } = useTranslation();
  const skillId = skill.skill_id;
  const [files, setFiles] = useState<FileTreeItem[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>("");
  const [editedContent, setEditedContent] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [contentLoading, setContentLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(
    new Set(),
  );
  const [isEditing, setIsEditing] = useState(mode === "edit");
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [displayName, setDisplayName] = useState(skill.display_name);
  const [accessLevel, setAccessLevel] = useState<SkillAccessLevel>(skill.access_level);
  const [departmentId, setDepartmentId] = useState(skill.department_id || "");
  const [shareTargets, setShareTargets] = useState<SkillShareTargetsResponse | null>(null);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [packageStatus, setPackageStatus] = useState<SkillPackageStatus | null>(
    null,
  );
  const isReadOnly = mode === "view";
  const resolvedDepartmentId =
    accessLevel === "team"
      ? departmentId || shareTargets?.default_department_id || ""
      : "";
  const initialDepartmentId =
    skill.access_level === "team" ? skill.department_id || "" : "";
  const settingsDirty =
    displayName.trim() !== skill.display_name ||
    accessLevel !== skill.access_level ||
    resolvedDepartmentId !== initialDepartmentId;

  const handleFileSelect = useCallback(
    async (filePath: string) => {
      setSelectedFile(filePath);
      setContentLoading(true);
      setError(null);

      try {
        const data = await skillsApi.getFileContent(skillId, filePath);
        setPackageStatus(data.package_status);
        setFileContent(data.content);
        setEditedContent(data.content);
      } catch (error: unknown) {
        console.error("Failed to load file content:", error);
        setError(getApiErrorMessage(error, "Failed to load file content"));
        setFileContent("");
        setEditedContent("");
      } finally {
        setContentLoading(false);
      }
    },
    [skillId],
  );

  const loadFiles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await skillsApi.getFiles(skillId);
      setFiles(data.files);
      setPackageStatus(data.package_status);

      // Auto-select SKILL.md if it exists
      const skillMd = findFileByName(data.files, "SKILL.md");
      if (skillMd) {
        void handleFileSelect(skillMd.path);
      }
    } catch (error: unknown) {
      console.error("Failed to load files:", error);
      setError(getApiErrorMessage(error, "Failed to load files"));
    } finally {
      setLoading(false);
    }
  }, [handleFileSelect, skillId]);

  // Load file list when modal opens
  useEffect(() => {
    if (isOpen && skillId) {
      void loadFiles();
    }
  }, [isOpen, skillId, loadFiles]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    setIsEditing(mode === "edit");
    setShowUploadDialog(false);
    setUploadFile(null);
    setIsDragging(false);
    setDisplayName(skill.display_name);
    setAccessLevel(skill.access_level);
    setDepartmentId(skill.department_id || "");

    if (mode !== "edit") {
      setShareTargets(null);
      return;
    }

    void skillsApi
      .getShareTargets()
      .then((data) => setShareTargets(data))
      .catch((error: unknown) => {
        console.error("Failed to load skill share targets:", error);
        setShareTargets(null);
      });
  }, [
    isOpen,
    mode,
    skill.skill_id,
    skill.access_level,
    skill.department_id,
    skill.department_name,
    skill.display_name,
  ]);

  const handleSaveSettings = async () => {
    if (isReadOnly || !displayName.trim()) {
      return;
    }

    if (accessLevel === "team" && !resolvedDepartmentId) {
      toast.error(
        t("skills.departmentRequired", {
          defaultValue: "Department is required for team visibility",
        }),
      );
      return;
    }

    setSettingsSaving(true);
    try {
      const updatedSkill = await skillsApi.update(skillId, {
        display_name: displayName.trim(),
        access_level: accessLevel,
        department_id: accessLevel === "team" ? resolvedDepartmentId : null,
      });
      setDisplayName(updatedSkill.display_name);
      setAccessLevel(updatedSkill.access_level);
      setDepartmentId(updatedSkill.department_id || "");
      toast.success(
        t("skills.settingsSaved", {
          defaultValue: "Settings saved successfully",
        }),
      );
      if (onUpdate) {
        await onUpdate();
      }
    } catch (error: unknown) {
      console.error("Failed to save skill settings:", error);
      toast.error(
        getApiErrorMessage(
          error,
          t("skills.failedToSaveSettings", {
            defaultValue: "Failed to save settings",
          }),
        ),
      );
    } finally {
      setSettingsSaving(false);
    }
  };

  const handleSaveFile = async () => {
    if (!selectedFile) return;

    setSaving(true);
    try {
      // TODO: Implement file save API
      await skillsApi.updateFileContent(skillId, selectedFile, editedContent);
      setFileContent(editedContent);
      toast.success(t("skills.fileSaved"));
      if (onUpdate) onUpdate();
    } catch (error: unknown) {
      console.error("Failed to save file:", error);
      toast.error(getApiErrorMessage(error, t("skills.failedToSaveFile")));
    } finally {
      setSaving(false);
    }
  };

  const handleUploadPackage = async () => {
    if (!uploadFile) return;

    setSaving(true);
    try {
      const formData = new FormData();
      formData.append("package_file", uploadFile);

      await skillsApi.updatePackage(skillId, formData);
      toast.success(t("skills.packageUpdated"));
      setShowUploadDialog(false);
      setUploadFile(null);
      await loadFiles();
      if (onUpdate) onUpdate();
    } catch (error: unknown) {
      console.error("Failed to upload package:", error);
      toast.error(getApiErrorMessage(error, t("skills.failedToUploadPackage")));
    } finally {
      setSaving(false);
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
      const validTypes = [".zip", ".tar.gz"];
      const isValid = validTypes.some((type) =>
        file.name.toLowerCase().endsWith(type),
      );

      if (!isValid) {
        toast.error(t("skills.invalidFileType"));
        return;
      }

      setUploadFile(file);
    }
  };

  const toggleFolder = (path: string) => {
    const newExpanded = new Set(expandedFolders);
    if (newExpanded.has(path)) {
      newExpanded.delete(path);
    } else {
      newExpanded.add(path);
    }
    setExpandedFolders(newExpanded);
  };

  const renderFileTree = (items: FileTreeItem[], level = 0) => {
    return items.map((item) => {
      const isExpanded = expandedFolders.has(item.path);
      const isSelected = selectedFile === item.path;

      if (item.type === "directory") {
        return (
          <div key={item.path}>
            <div
              className={`flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-muted/50 transition-colors ${
                level > 0 ? `ml-${level * 4}` : ""
              }`}
              style={{ paddingLeft: `${level * 16 + 12}px` }}
              onClick={() => toggleFolder(item.path)}
            >
              {isExpanded ? (
                <ChevronDown className="w-4 h-4 text-muted-foreground" />
              ) : (
                <ChevronRight className="w-4 h-4 text-muted-foreground" />
              )}
              {isExpanded ? (
                <FolderOpen className="w-4 h-4 text-blue-400" />
              ) : (
                <Folder className="w-4 h-4 text-blue-400" />
              )}
              <span className="text-sm text-foreground">{item.name}</span>
            </div>
            {isExpanded && item.children && (
              <div>{renderFileTree(item.children, level + 1)}</div>
            )}
          </div>
        );
      }

      return (
        <div
          key={item.path}
          className={`flex items-center gap-2 px-3 py-2 cursor-pointer transition-colors ${
            isSelected
              ? "bg-primary/20 text-primary"
              : "hover:bg-muted/50 text-foreground"
          }`}
          style={{ paddingLeft: `${level * 16 + 28}px` }}
          onClick={() => handleFileSelect(item.path)}
        >
          <File className="w-4 h-4" />
          <span className="text-sm">{item.name}</span>
          {item.size !== undefined && (
            <span className="text-xs text-muted-foreground ml-auto">
              {formatFileSize(item.size)}
            </span>
          )}
        </div>
      );
    });
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  if (!isOpen) return null;

  return (
    <LayoutModal
      isOpen={isOpen}
      onClose={onClose}
      closeOnBackdropClick={false}
      closeOnEscape={true}
      backdropClassName="bg-black/50 backdrop-blur-sm"
    >
      <ModalPanel className="w-full max-w-[95vw] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between mb-4 pb-4 border-b border-border">
          <div>
            <h2 className="text-xl font-semibold text-foreground">
              {displayName}
            </h2>
            <p className="text-sm text-muted-foreground mt-1">
              {isEditing
                ? t("skills.editAgentSkill")
                : t("skills.viewAgentSkill")}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {mode === "edit" && (
              <>
                <button
                  onClick={() => setShowUploadDialog(true)}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-muted hover:bg-muted/80 text-foreground transition-colors"
                >
                  <Upload className="w-4 h-4" />
                  {t("skills.reuploadPackage")}
                </button>
                <button
                  onClick={() => setIsEditing(!isEditing)}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground transition-colors"
                >
                  <Edit2 className="w-4 h-4" />
                  {isEditing ? t("skills.viewMode") : t("skills.editMode")}
                </button>
              </>
            )}
            <button
              onClick={onClose}
              className="p-2 rounded-lg hover:bg-muted/50 transition-colors"
            >
              <X className="w-5 h-5 text-muted-foreground" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex flex-col gap-4">
          {packageStatus?.package_missing && (
            <div className="rounded-xl border border-amber-300/60 bg-amber-50/80 px-4 py-3 text-sm text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-100">
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <div className="space-y-1">
                  <p className="font-medium">
                    {t("skills.packageMissingTitle")}
                  </p>
                  <p className="text-amber-800 dark:text-amber-200">
                    {packageStatus.message || t("skills.packageMissingBody")}
                  </p>
                  {mode === "edit" && (
                    <p className="text-amber-800/90 dark:text-amber-200/90">
                      {t("skills.packageMissingEditHint")}
                    </p>
                  )}
                </div>
              </div>
            </div>
          )}

          <div className="flex flex-col gap-4">
            <div className="flex h-[calc(100vh-var(--app-header-height,4rem)-9rem)] min-h-[30rem] gap-4">
              {/* Left Sidebar - File Tree */}
              <div className="min-h-0 w-80 border border-border rounded-xl overflow-hidden bg-muted/20 flex flex-col">
                <div className="p-3 border-b border-border bg-muted/30">
                  <h3 className="text-sm font-medium text-foreground">
                    {t("skills.files")}
                  </h3>
                </div>
                <div className="flex-1 overflow-y-auto">
                  {loading ? (
                    <div className="flex items-center justify-center py-8">
                      <Loader2 className="w-6 h-6 animate-spin text-primary" />
                    </div>
                  ) : error ? (
                    <div className="p-4 text-sm text-destructive">{error}</div>
                  ) : (
                    <div className="py-2">{renderFileTree(files)}</div>
                  )}
                </div>
              </div>

              {/* Right Content Area */}
              <div className="min-h-0 flex-1 border border-border rounded-xl overflow-hidden flex flex-col bg-background">
                {selectedFile ? (
                  <>
                    {/* File Header */}
                    <div className="px-4 py-3 border-b border-border bg-muted/20 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <File className="w-4 h-4 text-muted-foreground" />
                        <span className="text-sm font-medium text-foreground">
                          {selectedFile}
                        </span>
                      </div>
                      {isEditing && selectedFile && (
                        <button
                          onClick={handleSaveFile}
                          disabled={saving || editedContent === fileContent}
                          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {saving ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <Save className="w-4 h-4" />
                          )}
                          {t("skills.save")}
                        </button>
                      )}
                    </div>

                    {/* File Content */}
                    <div className="flex-1 min-h-0 overflow-hidden">
                      {contentLoading ? (
                        <div className="flex items-center justify-center h-full">
                          <Loader2 className="w-8 h-8 animate-spin text-primary" />
                        </div>
                      ) : isEditing ? (
                        <textarea
                          value={editedContent}
                          onChange={(e) => setEditedContent(e.target.value)}
                          className="h-full w-full overflow-auto p-6 bg-transparent text-foreground font-mono text-sm resize-none focus:outline-none"
                          style={{ tabSize: 2 }}
                        />
                      ) : (
                        <FileCodePreview
                          filename={selectedFile}
                          content={fileContent}
                        />
                      )}
                    </div>
                  </>
                ) : (
                  <div className="flex items-center justify-center h-full text-muted-foreground">
                    <div className="text-center">
                      <File className="w-16 h-16 mx-auto mb-4 opacity-50" />
                      <p className="text-sm">{t("skills.selectFileToView")}</p>
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="shrink-0 rounded-xl border border-border bg-muted/10 p-4">
              <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                <div className="space-y-1">
                  <h3 className="text-sm font-semibold text-foreground">
                    {t("skills.visibility", { defaultValue: "Visibility" })}
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    {t("skills.editSkillDesc")}
                  </p>
                </div>
                <p className="text-xs font-mono text-muted-foreground">
                  {skill.skill_slug}
                </p>
              </div>

              <div className="grid gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(15rem,0.9fr)]">
                <div className="space-y-2">
                  <label className="block text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    {t("skills.skillName")}
                  </label>
                  <input
                    type="text"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    disabled={isReadOnly || settingsSaving}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 disabled:cursor-not-allowed disabled:opacity-70"
                  />
                </div>

                <div className="space-y-2">
                  <label className="block text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    {t("skills.visibility", { defaultValue: "Visibility" })}
                  </label>
                  <select
                    value={accessLevel}
                    onChange={(e) => {
                      const nextAccessLevel = e.target.value as SkillAccessLevel;
                      setAccessLevel(nextAccessLevel);
                      if (nextAccessLevel === "team") {
                        setDepartmentId(
                          departmentId || shareTargets?.default_department_id || "",
                        );
                      } else {
                        setDepartmentId("");
                      }
                    }}
                    disabled={isReadOnly || settingsSaving}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 disabled:cursor-not-allowed disabled:opacity-70"
                  >
                    <option value="private">
                      {t("skills.private", { defaultValue: "Private" })}
                    </option>
                    <option value="team">
                      {t("skills.team", { defaultValue: "Team" })}
                    </option>
                    {shareTargets?.can_publish_public && (
                      <option value="public">
                        {t("skills.public", { defaultValue: "Public" })}
                      </option>
                    )}
                  </select>
                </div>
              </div>

              {accessLevel === "team" && (
                <div className="mt-4 max-w-md space-y-2">
                  <label className="block text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    {t("skills.department", { defaultValue: "Department" })}
                  </label>
                  <select
                    value={resolvedDepartmentId}
                    onChange={(e) => setDepartmentId(e.target.value)}
                    disabled={isReadOnly || settingsSaving}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 disabled:cursor-not-allowed disabled:opacity-70"
                  >
                    {(shareTargets?.allowed_department_targets || []).map((target) => (
                      <option key={target.department_id} value={target.department_id}>
                        {target.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {!isReadOnly && (
                <div className="mt-4 flex justify-end">
                  <button
                    onClick={handleSaveSettings}
                    disabled={
                      settingsSaving ||
                      !settingsDirty ||
                      !displayName.trim() ||
                      (accessLevel === "team" && !resolvedDepartmentId)
                    }
                    className="flex min-w-32 items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {settingsSaving ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Save className="h-4 w-4" />
                    )}
                    {t("skills.save", { defaultValue: "Save" })}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Upload Dialog */}
        {showUploadDialog && (
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-10">
            <div className="bg-background border border-border rounded-xl p-6 max-w-lg w-full mx-4">
              <h3 className="text-lg font-semibold text-foreground mb-4">
                {t("skills.reuploadPackage")}
              </h3>
              <p className="text-sm text-muted-foreground mb-6">
                {t("skills.reuploadWarning")}
              </p>

              {/* Drag and Drop Upload Area */}
              <div
                className={`border-2 border-dashed rounded-xl p-8 text-center transition-all duration-300 ${
                  isDragging
                    ? "border-primary bg-primary/10 scale-[1.02]"
                    : "border-border hover:border-primary hover:bg-primary/5"
                }`}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                <input
                  type="file"
                  accept=".zip,.tar.gz"
                  onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                  className="hidden"
                  id="package-reupload"
                />
                <label
                  htmlFor="package-reupload"
                  className="cursor-pointer block"
                >
                  {uploadFile ? (
                    <div className="space-y-3">
                      <div className="w-16 h-16 rounded-full bg-green-500/10 flex items-center justify-center mx-auto">
                        <Upload className="w-8 h-8 text-green-500" />
                      </div>
                      <div>
                        <p className="text-foreground font-semibold mb-1">
                          {uploadFile.name}
                        </p>
                        <p className="text-sm text-muted-foreground">
                          {(uploadFile.size / 1024 / 1024).toFixed(2)} MB
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.preventDefault();
                          setUploadFile(null);
                        }}
                        className="mt-3 px-4 py-2 text-sm text-primary hover:text-primary/80 transition-colors font-medium rounded-lg hover:bg-primary/10"
                      >
                        {t("skills.reselect")}
                      </button>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <div
                        className={`w-16 h-16 rounded-full flex items-center justify-center mx-auto transition-colors ${
                          isDragging ? "bg-primary/20" : "bg-muted"
                        }`}
                      >
                        <Upload
                          className={`w-8 h-8 transition-colors ${
                            isDragging
                              ? "text-primary"
                              : "text-muted-foreground"
                          }`}
                        />
                      </div>
                      <div>
                        <p className="text-foreground font-semibold mb-1">
                          {t("skills.dragDropOrClick")}
                        </p>
                        <p className="text-sm text-muted-foreground">
                          {t("skills.supportedFormats")}: ZIP, TAR.GZ
                        </p>
                      </div>
                    </div>
                  )}
                </label>
              </div>

              <div className="flex gap-2 justify-end mt-6">
                <button
                  onClick={() => {
                    setShowUploadDialog(false);
                    setUploadFile(null);
                    setIsDragging(false);
                  }}
                  className="px-4 py-2 rounded-lg bg-muted hover:bg-muted/80 text-foreground transition-colors"
                >
                  {t("common.cancel")}
                </button>
                <button
                  onClick={handleUploadPackage}
                  disabled={!uploadFile || saving}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {saving ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Upload className="w-4 h-4" />
                  )}
                  {t("skills.upload")}
                </button>
              </div>
            </div>
          </div>
        )}
      </ModalPanel>
    </LayoutModal>
  );
};

export default AgentSkillViewer;
