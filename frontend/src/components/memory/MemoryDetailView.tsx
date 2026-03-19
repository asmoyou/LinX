import React, { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Clock, Tag, Trash2, User, X } from "lucide-react";
import { LayoutModal } from "@/components/LayoutModal";
import { ModalPanel } from "@/components/ModalPanel";
import type { MemoryFact, MemoryRecord } from "@/types/memory";

const parseFacts = (memory: MemoryRecord): MemoryFact[] => {
  const raw = memory.metadata?.facts;
  if (!Array.isArray(raw)) {
    return [];
  }

  return raw
    .filter((entry): entry is MemoryFact => {
      return (
        !!entry &&
        typeof entry === "object" &&
        typeof (entry as MemoryFact).key === "string" &&
        typeof (entry as MemoryFact).value === "string" &&
        Boolean((entry as MemoryFact).key.trim()) &&
        Boolean((entry as MemoryFact).value.trim())
      );
    })
    .map((entry) => ({
      ...entry,
      key: entry.key.trim(),
      value: entry.value.trim(),
    }));
};

const formatTimestamp = (value?: string | null): string => {
  if (!value) {
    return "—";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
};

interface MemoryDetailViewProps {
  memory: MemoryRecord | null;
  isOpen: boolean;
  onClose: () => void;
  onDelete?: (memory: MemoryRecord) => void;
}

export const MemoryDetailView: React.FC<MemoryDetailViewProps> = ({
  memory,
  isOpen,
  onClose,
  onDelete,
}) => {
  const { t } = useTranslation();
  const facts = useMemo(() => (memory ? parseFacts(memory) : []), [memory]);

  if (!isOpen || !memory) {
    return null;
  }

  const metadataEntries = Object.entries(memory.metadata || {}).filter(
    ([key, value]) =>
      key !== "facts" &&
      value !== null &&
      value !== undefined &&
      !(typeof value === "string" && value.trim() === ""),
  );

  return (
    <LayoutModal
      isOpen={isOpen}
      onClose={onClose}
      closeOnBackdropClick={false}
      closeOnEscape={true}
    >
      <ModalPanel className="w-full max-w-4xl max-h-[calc(100vh-var(--app-header-height,4rem)-3rem)] overflow-y-auto">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div className="space-y-3">
            <div className="inline-flex items-center gap-2 rounded-full bg-emerald-500/10 px-3 py-1 text-sm text-emerald-700 dark:text-emerald-300">
              <User className="h-4 w-4" />
              <span>
                {memory.userName
                  ? t("memory.card.userMemoryOwner", {
                      defaultValue: "{{name}} 的记忆",
                      name: memory.userName,
                    })
                  : t("memory.tabs.userMemory", { defaultValue: "用户记忆" })}
              </span>
            </div>
            <div>
              <h2 className="text-2xl font-bold text-zinc-800 dark:text-white">
                {memory.summary ||
                  t("memory.detail.title", { defaultValue: "Memory detail" })}
              </h2>
              <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-zinc-500 dark:text-zinc-400">
                <span className="inline-flex items-center gap-1">
                  <Clock className="h-4 w-4" />
                  {formatTimestamp(memory.updatedAt || memory.createdAt)}
                </span>
                {memory.tags.length > 0 && (
                  <span className="inline-flex items-center gap-1">
                    <Tag className="h-4 w-4" />
                    {memory.tags.length}
                  </span>
                )}
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-white"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-6">
          <section className="rounded-2xl border border-zinc-200/70 bg-white/70 p-5 dark:border-zinc-700 dark:bg-zinc-900/50">
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              {t("memory.detail.content", { defaultValue: "Content" })}
            </h3>
            <div className="whitespace-pre-wrap text-sm leading-7 text-zinc-700 dark:text-zinc-200">
              {memory.content}
            </div>
          </section>

          {facts.length > 0 && (
            <section className="rounded-2xl border border-zinc-200/70 bg-white/70 p-5 dark:border-zinc-700 dark:bg-zinc-900/50">
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                {t("memory.detail.facts", { defaultValue: "Extracted facts" })}
              </h3>
              <div className="grid gap-3 md:grid-cols-2">
                {facts.map((fact) => (
                  <div
                    key={`${fact.key}-${fact.value}`}
                    className="rounded-xl border border-zinc-200/70 bg-zinc-50/80 p-3 dark:border-zinc-700 dark:bg-zinc-950/40"
                  >
                    <p className="font-mono text-xs text-indigo-600 dark:text-indigo-300">
                      {fact.key}
                    </p>
                    <p className="mt-1 text-sm text-zinc-700 dark:text-zinc-200">
                      {fact.value}
                    </p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {memory.tags.length > 0 && (
            <section className="rounded-2xl border border-zinc-200/70 bg-white/70 p-5 dark:border-zinc-700 dark:bg-zinc-900/50">
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                {t("memory.detail.tags", { defaultValue: "Tags" })}
              </h3>
              <div className="flex flex-wrap gap-2">
                {memory.tags.map((tag) => (
                  <span
                    key={tag}
                    className="rounded-full bg-zinc-500/10 px-3 py-1 text-xs text-zinc-700 dark:text-zinc-200"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </section>
          )}

          {metadataEntries.length > 0 && (
            <section className="rounded-2xl border border-zinc-200/70 bg-white/70 p-5 dark:border-zinc-700 dark:bg-zinc-900/50">
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                {t("memory.detail.metadata", { defaultValue: "Metadata" })}
              </h3>
              <dl className="grid gap-3 md:grid-cols-2">
                {metadataEntries.map(([key, value]) => (
                  <div
                    key={key}
                    className="rounded-xl border border-zinc-200/70 bg-zinc-50/80 p-3 dark:border-zinc-700 dark:bg-zinc-950/40"
                  >
                    <dt className="font-mono text-xs text-zinc-500 dark:text-zinc-400">
                      {key}
                    </dt>
                    <dd className="mt-1 break-all text-sm text-zinc-700 dark:text-zinc-200">
                      {typeof value === "string"
                        ? value
                        : JSON.stringify(value, null, 2)}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
          )}
        </div>

        <div className="mt-6 flex items-center justify-end gap-3 border-t border-zinc-200 pt-4 dark:border-zinc-700">
          {onDelete && (
            <button
              type="button"
              onClick={() => void onDelete(memory)}
              className="inline-flex items-center gap-2 rounded-lg border border-rose-200 px-4 py-2 text-sm text-rose-600 transition-colors hover:bg-rose-50 dark:border-rose-500/30 dark:text-rose-300 dark:hover:bg-rose-500/10"
            >
              <Trash2 className="h-4 w-4" />
              {t("memory.delete.title", { defaultValue: "Delete" })}
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-zinc-900 px-4 py-2 text-sm text-white transition-colors hover:bg-zinc-700 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
          >
            {t("common.close", { defaultValue: "Close" })}
          </button>
        </div>
      </ModalPanel>
    </LayoutModal>
  );
};
