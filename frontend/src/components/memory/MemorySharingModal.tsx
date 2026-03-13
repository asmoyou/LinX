import React, { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  CalendarClock,
  Info,
  Loader2,
  Plus,
  Search,
  Send,
  Share2,
  Shield,
  X,
} from "lucide-react";
import { LayoutModal } from "@/components/LayoutModal";
import { ModalPanel } from "@/components/ModalPanel";
import { adminUsersApi, type AdminUser } from "@/api/adminUsers";
import type { Memory } from "@/types/memory";

type VisibilityScope =
  | "explicit"
  | "department"
  | "department_tree"
  | "account"
  | "private"
  | "public";

const VALID_SCOPES: VisibilityScope[] = [
  "private",
  "explicit",
  "department",
  "department_tree",
  "account",
  "public",
];

const parseUserIds = (raw: string): string[] => {
  const items = raw
    .split(/[\n,，]/g)
    .map((value) => value.trim())
    .filter(Boolean);
  return Array.from(new Set(items));
};

const toDateTimeLocal = (isoValue?: string): string => {
  if (!isoValue) return "";
  const date = new Date(isoValue);
  if (Number.isNaN(date.getTime())) return "";
  const offsetMs = date.getTimezoneOffset() * 60 * 1000;
  const local = new Date(date.getTime() - offsetMs);
  return local.toISOString().slice(0, 16);
};

const toIsoDateTime = (dateTimeLocal?: string): string | undefined => {
  if (!dateTimeLocal) return undefined;
  const date = new Date(dateTimeLocal);
  if (Number.isNaN(date.getTime())) return undefined;
  return date.toISOString();
};

const defaultScopeByType = (): VisibilityScope => "private";

const resolveInitialScope = (memory: Memory): VisibilityScope => {
  const metadata = memory.metadata || {};
  const visibility = String(metadata.visibility || "").trim().toLowerCase();

  if (memory.type === "user_memory") {
    if (visibility === "private" || visibility === "explicit") {
      return visibility as VisibilityScope;
    }
    return "private";
  }

  if (VALID_SCOPES.includes(visibility as VisibilityScope)) {
    return visibility as VisibilityScope;
  }
  return defaultScopeByType();
};

const scopeOptionsByType = (
  type: Memory["type"],
): Array<{ value: VisibilityScope; labelKey: string; descKey: string }> => {
  if (type === "user_memory") {
    return [
      {
        value: "private",
        labelKey: "memory.share.scope.private",
        descKey: "memory.share.scopeDesc.privateUser",
      },
      {
        value: "explicit",
        labelKey: "memory.share.scope.explicit",
        descKey: "memory.share.scopeDesc.explicitException",
      },
    ];
  }
  return [
    {
      value: "private",
      labelKey: "memory.share.scope.private",
      descKey: "memory.share.scopeDesc.private",
    },
    {
      value: "department",
      labelKey: "memory.share.scope.department",
      descKey: "memory.share.scopeDesc.department",
    },
    {
      value: "department_tree",
      labelKey: "memory.share.scope.departmentTree",
      descKey: "memory.share.scopeDesc.departmentTree",
    },
    {
      value: "account",
      labelKey: "memory.share.scope.account",
      descKey: "memory.share.scopeDesc.account",
    },
    {
      value: "public",
      labelKey: "memory.share.scope.public",
      descKey: "memory.share.scopeDesc.public",
    },
    {
      value: "explicit",
      labelKey: "memory.share.scope.explicit",
      descKey: "memory.share.scopeDesc.explicit",
    },
  ];
};

interface MemorySharingPayload {
  mode: "share" | "publish";
  scope: VisibilityScope;
  userIds: string[];
  expiresAt?: string;
  reason?: string;
}

interface MemorySharingModalProps {
  memory: Memory | null;
  isOpen: boolean;
  onClose: () => void;
  onShare: (memoryId: string, payload: MemorySharingPayload) => Promise<void> | void;
}

const getUserLabel = (user: AdminUser): string =>
  String(user.displayName || "").trim() ||
  String(user.username || "").trim() ||
  String(user.email || "").trim() ||
  String(user.id);

const getUserLabelById = (userId: string, userById: Map<string, AdminUser>): string => {
  const matched = userById.get(userId);
  return matched ? getUserLabel(matched) : userId;
};

const getUserSearchText = (user: AdminUser): string => {
  return [
    user.id,
    user.username,
    user.displayName,
    user.email,
    user.departmentName,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
};

export const MemorySharingModal: React.FC<MemorySharingModalProps> = ({
  memory,
  isOpen,
  onClose,
  onShare,
}) => {
  const { t } = useTranslation();
  const [scope, setScope] = useState<VisibilityScope>("account");
  const [selectedUserIds, setSelectedUserIds] = useState<string[]>([]);
  const [userSearch, setUserSearch] = useState("");
  const [manualUserInput, setManualUserInput] = useState("");
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [isLoadingUsers, setIsLoadingUsers] = useState(false);
  const [usersLoadError, setUsersLoadError] = useState("");
  const [expiresAtLocal, setExpiresAtLocal] = useState("");
  const [reason, setReason] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string>("");

  const mode: "share" | "publish" =
    memory?.type === "skill_proposal" ? "publish" : "share";

  const scopeOptions = useMemo(
    () => scopeOptionsByType(memory?.type || "user_memory"),
    [memory?.type],
  );

  useEffect(() => {
    if (!isOpen || !memory) return;

    let cancelled = false;

    setSubmitError("");
    setScope(resolveInitialScope(memory));
    setSelectedUserIds(
      Array.from(new Set((memory.sharedWith || []).map((id) => String(id)))),
    );
    setUserSearch("");
    setManualUserInput("");
    setExpiresAtLocal(toDateTimeLocal(String(memory.metadata?.expires_at || "")));
    setReason(String(memory.metadata?.share_reason || ""));
    setUsersLoadError("");
    setIsLoadingUsers(true);

    const loadUsers = async () => {
      try {
        const pageSize = 100;
        const maxPages = 20;
        let page = 1;
        let total = Number.POSITIVE_INFINITY;
        let allUsers: AdminUser[] = [];

        while (page <= maxPages && allUsers.length < total) {
          const result = await adminUsersApi.list({
            page,
            page_size: pageSize,
            status: "active",
          });

          const pageUsers = result.users || [];
          allUsers = allUsers.concat(pageUsers);
          total = Number.isFinite(result.total) ? Number(result.total) : allUsers.length;

          if (pageUsers.length < pageSize) {
            break;
          }
          page += 1;
        }

        if (cancelled) return;
        const dedupedUsers = Array.from(
          new Map(allUsers.map((user) => [String(user.id), user])).values(),
        );
        const enabledUsers = dedupedUsers.filter((user) => !user.isDisabled);
        setUsers(enabledUsers);
      } catch {
        if (cancelled) return;
        setUsers([]);
        setUsersLoadError(t("memory.share.userLoadError"));
      } finally {
        if (!cancelled) {
          setIsLoadingUsers(false);
        }
      }
    };

    void loadUsers();
    return () => {
      cancelled = true;
    };
  }, [isOpen, memory, t]);

  const userById = useMemo(() => {
    const map = new Map<string, AdminUser>();
    for (const user of users) {
      map.set(String(user.id), user);
    }
    return map;
  }, [users]);

  const filteredUsers = useMemo(() => {
    const keyword = userSearch.trim().toLowerCase();
    if (!keyword) {
      return users;
    }
    return users.filter((user) => getUserSearchText(user).includes(keyword));
  }, [users, userSearch]);

  const initialSnapshot = useMemo(() => {
    if (!memory) return "";
    return JSON.stringify({
      scope: resolveInitialScope(memory),
      userIds: (memory.sharedWith || []).map((id) => String(id)),
      expiresAt: toDateTimeLocal(String(memory.metadata?.expires_at || "")),
      reason: String(memory.metadata?.share_reason || ""),
    });
  }, [memory]);

  const currentSnapshot = useMemo(
    () =>
      JSON.stringify({
        scope,
        userIds: selectedUserIds,
        expiresAt: expiresAtLocal,
        reason: reason.trim(),
      }),
    [scope, selectedUserIds, expiresAtLocal, reason],
  );

  const hasChanges = initialSnapshot !== currentSnapshot;

  if (!isOpen || !memory) return null;

  const actionTitle =
    mode === "publish" ? t("memory.share.publishTitle") : t("memory.share.title");
  const actionButtonText =
    mode === "publish"
      ? t("memory.share.applyPublish")
      : t("memory.share.applyChanges");
  const scopeHintKey =
    mode === "publish" ? "memory.share.publishHint" : "memory.share.shareHint";

  const toggleUser = (userId: string) => {
    setSelectedUserIds((current) => {
      if (current.includes(userId)) {
        return current.filter((id) => id !== userId);
      }
      return [...current, userId];
    });
  };

  const removeSelectedUser = (userId: string) => {
    setSelectedUserIds((current) => current.filter((id) => id !== userId));
  };

  const handleAddManualUsers = () => {
    const parsed = parseUserIds(manualUserInput);
    if (parsed.length === 0) return;

    setSelectedUserIds((current) => {
      return Array.from(new Set([...current, ...parsed]));
    });
    setManualUserInput("");
  };

  const handleSubmit = async () => {
    setSubmitError("");
    if (scope === "explicit" && selectedUserIds.length === 0) {
      setSubmitError(t("memory.share.explicitNeedsUsers"));
      return;
    }
    if (selectedUserIds.length > 0 && !reason.trim()) {
      setSubmitError(t("memory.share.reasonRequired"));
      return;
    }

    setIsSubmitting(true);
    try {
      await onShare(memory.id, {
        mode,
        scope,
        userIds: selectedUserIds,
        expiresAt: toIsoDateTime(expiresAtLocal),
        reason: reason.trim() || undefined,
      });
      onClose();
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <LayoutModal
      isOpen={isOpen}
      onClose={onClose}
      closeOnBackdropClick={false}
      closeOnEscape={true}
    >
      <ModalPanel className="w-full max-w-2xl max-h-[calc(100vh-var(--app-header-height,4rem)-3rem)] overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Share2 className="w-6 h-6 text-indigo-500" />
            <h2 className="text-2xl font-bold text-gray-800 dark:text-white">
              {actionTitle}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/20 rounded-lg transition-colors"
          >
            <X className="w-6 h-6 text-gray-700 dark:text-gray-300" />
          </button>
        </div>

        <div className="mb-5 p-4 bg-white/10 rounded-lg space-y-2">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {t("memory.share.workingOn")}
          </p>
          <p className="text-gray-800 dark:text-white line-clamp-2">
            {memory.summary || memory.content}
          </p>
          <p className="text-xs text-indigo-500 flex items-center gap-1">
            <Info className="w-3.5 h-3.5" />
            {t(scopeHintKey)}
          </p>
        </div>

        <div className="mb-5">
          <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
            <Shield className="w-4 h-4" />
            {t("memory.share.scopeLabel")}
          </label>
          <div className="space-y-2">
            {scopeOptions.map((option) => (
              <label
                key={option.value}
                className={`block rounded-lg border p-3 cursor-pointer transition-colors ${
                  scope === option.value
                    ? "border-indigo-500 bg-indigo-500/10"
                    : "border-gray-300 dark:border-gray-600 bg-white/10 hover:bg-white/20"
                }`}
              >
                <div className="flex items-start gap-3">
                  <input
                    type="radio"
                    name="memory_scope"
                    className="mt-1"
                    checked={scope === option.value}
                    onChange={() => setScope(option.value)}
                  />
                  <div>
                    <p className="text-sm font-medium text-gray-800 dark:text-white">
                      {t(option.labelKey)}
                    </p>
                    <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                      {t(option.descKey)}
                    </p>
                  </div>
                </div>
              </label>
            ))}
          </div>
        </div>

        <div className="mb-5 space-y-3">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            {t("memory.share.explicitUsers")}
          </label>
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-3 text-gray-500" />
            <input
              type="text"
              value={userSearch}
              onChange={(event) => setUserSearch(event.target.value)}
              placeholder={t("memory.share.userSearchPlaceholder")}
              className="w-full pl-9 pr-3 py-2 bg-white/10 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-800 dark:text-white placeholder-gray-500"
            />
          </div>
          <div className="max-h-52 overflow-y-auto rounded-lg border border-gray-300 dark:border-gray-600 bg-white/5">
            {isLoadingUsers ? (
              <div className="px-3 py-4 text-sm text-gray-500 dark:text-gray-400 flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                {t("common.loading")}
              </div>
            ) : filteredUsers.length === 0 ? (
              <div className="px-3 py-4 text-sm text-gray-500 dark:text-gray-400">
                {usersLoadError || t("memory.share.noUsersFound")}
              </div>
            ) : (
              filteredUsers.map((user) => {
                const userId = String(user.id);
                const checked = selectedUserIds.includes(userId);
                return (
                  <label
                    key={userId}
                    className="flex items-start gap-3 px-3 py-2 border-b border-gray-200/50 dark:border-gray-700/50 last:border-b-0 cursor-pointer hover:bg-white/10"
                  >
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={checked}
                      onChange={() => toggleUser(userId)}
                    />
                    <div className="min-w-0">
                      <p className="text-sm text-gray-800 dark:text-white truncate">
                        {getUserLabel(user)}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                        {user.username} · {user.email}
                      </p>
                    </div>
                  </label>
                );
              })
            )}
          </div>
          <div className="flex items-center justify-between">
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {t("memory.share.explicitUsersHint", { count: selectedUserIds.length })}
            </p>
            {selectedUserIds.length > 0 && (
              <button
                type="button"
                onClick={() => setSelectedUserIds([])}
                className="text-xs text-indigo-500 hover:text-indigo-600"
              >
                {t("memory.share.clearSelection")}
              </button>
            )}
          </div>
          {selectedUserIds.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {selectedUserIds.map((userId) => (
                <span
                  key={userId}
                  className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 text-xs max-w-full"
                >
                  <span className="truncate max-w-[220px]">
                    {getUserLabelById(userId, userById)}
                  </span>
                  <button
                    type="button"
                    onClick={() => removeSelectedUser(userId)}
                    className="hover:text-indigo-900 dark:hover:text-indigo-200"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
          )}
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={manualUserInput}
              onChange={(event) => setManualUserInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  handleAddManualUsers();
                }
              }}
              placeholder={t("memory.share.explicitUsersPlaceholder")}
              className="flex-1 px-3 py-2 bg-white/10 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-800 dark:text-white placeholder-gray-500"
            />
            <button
              type="button"
              onClick={handleAddManualUsers}
              className="inline-flex items-center gap-1 px-3 py-2 rounded-lg bg-indigo-500 text-white hover:bg-indigo-600 transition-colors"
            >
              <Plus className="w-4 h-4" />
              {t("memory.share.addUser")}
            </button>
          </div>
          {usersLoadError && (
            <p className="text-xs text-amber-600 dark:text-amber-400">
              {usersLoadError}
            </p>
          )}
        </div>

        <div className="mb-5 grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {t("memory.share.expiresAt")}
            </label>
            <div className="relative">
              <CalendarClock className="w-4 h-4 absolute left-3 top-3 text-gray-500" />
              <input
                type="datetime-local"
                value={expiresAtLocal}
                onChange={(event) => setExpiresAtLocal(event.target.value)}
                className="w-full pl-9 pr-3 py-2 bg-white/10 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-800 dark:text-white"
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {t("memory.share.reason")}
            </label>
            <input
              type="text"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder={t("memory.share.reasonPlaceholder")}
              className="w-full px-3 py-2 bg-white/10 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-800 dark:text-white placeholder-gray-500"
            />
          </div>
        </div>

        {submitError && (
          <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/40 text-sm text-red-600 dark:text-red-400">
            {submitError}
          </div>
        )}

        <div className="flex items-center gap-3">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-3 bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-white rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors font-medium"
          >
            {t("memory.share.cancel")}
          </button>
          <button
            onClick={handleSubmit}
            disabled={!hasChanges || isSubmitting}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSubmitting ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <Send className="w-5 h-5" />
            )}
            {actionButtonText}
          </button>
        </div>
      </ModalPanel>
    </LayoutModal>
  );
};
