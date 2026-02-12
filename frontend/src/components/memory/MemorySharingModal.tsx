import React, { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { X, Share2, Users, Check, Loader2 } from "lucide-react";
import { ModalPanel } from "@/components/ModalPanel";
import { agentsApi } from "@/api/agents";
import type { Memory } from "@/types/memory";

interface ShareTarget {
  id: string;
  name: string;
  type: "agent" | "user";
}

interface MemorySharingModalProps {
  memory: Memory | null;
  isOpen: boolean;
  onClose: () => void;
  onShare: (
    memoryId: string,
    payload: { agentIds: string[]; userIds: string[] },
  ) => Promise<void> | void;
}

export const MemorySharingModal: React.FC<MemorySharingModalProps> = ({
  memory,
  isOpen,
  onClose,
  onShare,
}) => {
  const { t } = useTranslation();
  const [selectedUsers, setSelectedUsers] = useState<string[]>([]);
  const [initialSelectedUsers, setInitialSelectedUsers] = useState<string[]>(
    [],
  );
  const [availableTargets, setAvailableTargets] = useState<ShareTarget[]>([]);
  const [isLoadingTargets, setIsLoadingTargets] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!isOpen || !memory) return;
    const initial = (memory.sharedWith || []).map((id) => String(id));
    setSelectedUsers(initial);
    setInitialSelectedUsers(initial);
  }, [isOpen, memory]);

  // Fetch real agents when modal opens
  useEffect(() => {
    if (!isOpen) return;

    const fetchTargets = async () => {
      setIsLoadingTargets(true);
      try {
        const agents = await agentsApi.getAll();
        const agentTargets: ShareTarget[] = agents.map((agent) => ({
          id: String(agent.agentId || agent.id),
          name: agent.name,
          type: "agent" as const,
        }));

        const sharedIds = (memory?.sharedWith || []).map((id) => String(id));
        const sharedNames = (memory?.sharedWithNames || []).map((name) =>
          String(name),
        );
        const sharedNameMap = new Map(
          sharedIds.map((id, index) => [id, sharedNames[index] || id]),
        );
        const knownAgentIds = new Set(agentTargets.map((target) => target.id));
        const missingTargets: ShareTarget[] = sharedIds
          .filter((id) => !knownAgentIds.has(id))
          .map((id) => ({
            id,
            name: sharedNameMap.get(id) || id,
            type: "user" as const,
          }));

        setAvailableTargets([...agentTargets, ...missingTargets]);
      } catch {
        setAvailableTargets([]);
      } finally {
        setIsLoadingTargets(false);
      }
    };

    fetchTargets();
  }, [isOpen, memory]);

  if (!isOpen || !memory) return null;

  const handleToggleUser = (userId: string) => {
    setSelectedUsers((prev) =>
      prev.includes(userId)
        ? prev.filter((id) => id !== userId)
        : [...prev, userId],
    );
  };

  const handleShare = async () => {
    const selectedTypeMap = new Map(
      availableTargets.map((target) => [target.id, target.type]),
    );
    const agentIds = selectedUsers.filter(
      (id) => selectedTypeMap.get(id) === "agent",
    );
    const userIds = selectedUsers.filter(
      (id) => selectedTypeMap.get(id) === "user",
    );

    setIsSubmitting(true);
    try {
      await onShare(memory.id, { agentIds, userIds });
      onClose();
    } finally {
      setIsSubmitting(false);
    }
  };

  const selectedSet = new Set(selectedUsers);
  const initialSet = new Set(initialSelectedUsers);
  const hasChanges =
    selectedSet.size !== initialSet.size ||
    Array.from(selectedSet).some((id) => !initialSet.has(id));
  const targetNameMap = new Map(
    availableTargets.map((target) => [target.id, target.name]),
  );
  const selectedTargetNames = selectedUsers.map(
    (targetId) => targetNameMap.get(targetId) || targetId,
  );
  const currentSharedNames =
    memory.sharedWithNames && memory.sharedWithNames.length > 0
      ? memory.sharedWithNames
      : memory.sharedWith || [];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md"
      style={{ marginLeft: "var(--sidebar-width, 0px)" }}
    >
      <ModalPanel className="w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Share2 className="w-6 h-6 text-indigo-500" />
            <h2 className="text-2xl font-bold text-gray-800 dark:text-white">
              {t("memory.share.title")}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/20 rounded-lg transition-colors"
          >
            <X className="w-6 h-6 text-gray-700 dark:text-gray-300" />
          </button>
        </div>

        {/* Memory Preview */}
        <div className="mb-6 p-4 bg-white/10 rounded-lg">
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
            {t("memory.share.sharing")}
          </p>
          <p className="text-gray-800 dark:text-white line-clamp-2">
            {memory.summary || memory.content}
          </p>
          <p className="text-xs text-indigo-500 mt-2">
            {t("memory.share.defaultVisibility")}
          </p>
          <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
            {t("memory.share.extraShareHint")}
          </p>
          <p className="text-xs text-gray-600 dark:text-gray-400 mt-2">
            {t("memory.share.currentSharedWith")}:{" "}
            {currentSharedNames.length > 0
              ? currentSharedNames.join(", ")
              : t("memory.share.notShared")}
          </p>
        </div>

        {/* Share With */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-3">
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
              <Users className="w-4 h-4" />
              {t("memory.share.shareWithExternal")} ({selectedUsers.length}{" "}
              {t("memory.share.selected")})
            </label>
            <button
              onClick={() => setSelectedUsers([])}
              className="text-xs text-indigo-500 hover:text-indigo-400 transition-colors"
            >
              {t("memory.share.clearSelection")}
            </button>
          </div>
          {selectedTargetNames.length > 0 && (
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
              {t("memory.share.selectedNames")}:{" "}
              {selectedTargetNames.join(", ")}
            </p>
          )}
          {isLoadingTargets ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
            </div>
          ) : availableTargets.length === 0 ? (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              {t("memory.share.noTargets")}
            </div>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {availableTargets.map((target) => (
                <button
                  key={target.id}
                  onClick={() => handleToggleUser(target.id)}
                  className={`w-full flex items-center justify-between p-3 rounded-lg transition-colors ${
                    selectedUsers.includes(target.id)
                      ? "bg-indigo-500/20 border-2 border-indigo-500"
                      : "bg-white/10 border-2 border-transparent hover:bg-white/20"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-10 h-10 rounded-full flex items-center justify-center ${
                        target.type === "agent"
                          ? "bg-blue-500/20"
                          : "bg-purple-500/20"
                      }`}
                    >
                      <span className="text-sm font-medium">
                        {target.name.charAt(0)}
                      </span>
                    </div>
                    <div className="text-left">
                      <p className="text-sm font-medium text-gray-800 dark:text-white">
                        {target.name}
                      </p>
                      <p className="text-xs text-gray-600 dark:text-gray-400 capitalize">
                        {target.type}
                      </p>
                    </div>
                  </div>
                  {selectedUsers.includes(target.id) && (
                    <Check className="w-5 h-5 text-indigo-500" />
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-3">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-3 bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-white rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors font-medium"
          >
            {t("memory.share.cancel")}
          </button>
          <button
            onClick={handleShare}
            disabled={!hasChanges || isSubmitting}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSubmitting ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <Share2 className="w-5 h-5" />
            )}
            {t("memory.share.applyChanges")}
          </button>
        </div>
      </ModalPanel>
    </div>
  );
};
