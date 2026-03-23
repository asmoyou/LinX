import { useEffect, useState } from "react";
import {
  Globe,
  Loader2,
  Plus,
  Terminal,
  X,
  Zap,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { LayoutModal } from "@/components/LayoutModal";
import type { McpServer, UpdateMcpServerRequest } from "@/api/mcpServers";
import { mcpServersApi } from "@/api/mcpServers";

interface EditMcpServerModalProps {
  server: McpServer | null;
  onClose: () => void;
  onSaved: () => void;
}

const transportOptions = [
  { value: "stdio" as const, icon: Terminal, label: "stdio" },
  { value: "sse" as const, icon: Zap, label: "SSE" },
  { value: "streamable_http" as const, icon: Globe, label: "HTTP" },
];

export default function EditMcpServerModal({
  server,
  onClose,
  onSaved,
}: EditMcpServerModalProps) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [transportType, setTransportType] = useState<"stdio" | "sse" | "streamable_http">("stdio");
  const [command, setCommand] = useState("");
  const [argsText, setArgsText] = useState("");
  const [url, setUrl] = useState("");
  const [envPairs, setEnvPairs] = useState<{ key: string; value: string }[]>([]);
  const [headerPairs, setHeaderPairs] = useState<{ key: string; value: string }[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!server) return;
    setName(server.name);
    setDescription(server.description || "");
    setTransportType(server.transport_type);
    setCommand(server.command || "");
    setArgsText((server.args || []).join(" "));
    setUrl(server.url || "");
    setEnvPairs(
      Object.entries(server.env_vars || {}).map(([key, value]) => ({ key, value })),
    );
    setHeaderPairs(
      Object.entries(server.headers || {}).map(([key, value]) => ({ key, value })),
    );
    setError(null);
  }, [server]);

  if (!server) return null;

  const handleTransportChange = (t: "stdio" | "sse" | "streamable_http") => {
    setTransportType(t);
    if (t === "stdio") {
      setUrl("");
      setHeaderPairs([]);
    } else {
      setCommand("");
      setArgsText("");
      setEnvPairs([]);
    }
  };

  const pairsToRecord = (pairs: { key: string; value: string }[]): Record<string, string> | undefined => {
    const filtered = pairs.filter((p) => p.key.trim());
    if (filtered.length === 0) return undefined;
    const record: Record<string, string> = {};
    for (const p of filtered) record[p.key.trim()] = p.value;
    return record;
  };

  const handleSave = async () => {
    setIsSaving(true);
    setError(null);
    try {
      const data: UpdateMcpServerRequest = {
        name: name.trim(),
        description: description.trim() || undefined,
        transport_type: transportType,
        command: transportType === "stdio" ? command.trim() || undefined : undefined,
        args: transportType === "stdio" && argsText.trim()
          ? argsText.split(/\s+/).map((s) => s.trim()).filter(Boolean)
          : undefined,
        url: transportType !== "stdio" ? url.trim() || undefined : undefined,
        env_vars: transportType === "stdio" ? pairsToRecord(envPairs) : undefined,
        headers: transportType !== "stdio" ? pairsToRecord(headerPairs) : undefined,
      };
      await mcpServersApi.update(server.server_id, data);
      onSaved();
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || "Failed to update");
    } finally {
      setIsSaving(false);
    }
  };

  const addPair = (setter: React.Dispatch<React.SetStateAction<{ key: string; value: string }[]>>) => {
    setter((prev) => [...prev, { key: "", value: "" }]);
  };
  const updatePair = (setter: typeof setEnvPairs, idx: number, field: "key" | "value", val: string) => {
    setter((prev) => prev.map((p, i) => (i === idx ? { ...p, [field]: val } : p)));
  };
  const removePair = (setter: typeof setEnvPairs, idx: number) => {
    setter((prev) => prev.filter((_, i) => i !== idx));
  };

  const inputCls = "w-full rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-sm outline-none focus:border-emerald-500 dark:border-zinc-700 dark:bg-zinc-800/50 dark:text-zinc-200";
  const labelCls = "mb-1 block text-xs font-medium text-zinc-700 dark:text-zinc-300";
  const kvInputCls = "rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs font-mono outline-none focus:border-emerald-500 dark:border-zinc-700 dark:bg-zinc-800/50";

  return (
    <LayoutModal isOpen={true} onClose={onClose} closeOnBackdropClick={false} closeOnEscape={true}>
      <div className="w-full max-w-2xl max-h-[calc(100vh-var(--app-header-height,4rem)-3rem)] overflow-y-auto modal-panel rounded-[24px] shadow-2xl p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-2xl font-bold text-zinc-800 dark:text-white">
            {t("skills.mcpEditServer", "Edit MCP Server")}
          </h2>
          <button onClick={onClose} className="p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors">
            <X className="w-6 h-6 text-zinc-700 dark:text-zinc-300" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className={labelCls}>{t("skills.mcpName", "Name")} *</label>
            <input value={name} onChange={(e) => setName(e.target.value)} className={inputCls} />
          </div>
          <div>
            <label className={labelCls}>{t("skills.mcpDescription", "Description")}</label>
            <input value={description} onChange={(e) => setDescription(e.target.value)} className={inputCls} />
          </div>

          <div>
            <label className={labelCls}>{t("skills.mcpTransport", "Transport")}</label>
            <div className="grid grid-cols-3 gap-2">
              {transportOptions.map((opt) => {
                const Icon = opt.icon;
                const active = transportType === opt.value;
                return (
                  <button key={opt.value} type="button" onClick={() => handleTransportChange(opt.value)}
                    className={`flex flex-col items-center gap-1 rounded-xl border px-3 py-3 text-xs transition-colors ${
                      active ? "border-emerald-500 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                        : "border-zinc-200 text-zinc-500 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800"
                    }`}>
                    <Icon className="h-4 w-4" />
                    <span className="font-medium">{opt.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {transportType === "stdio" && (
            <>
              <div>
                <label className={labelCls}>{t("skills.mcpCommand", "Command")} *</label>
                <input value={command} onChange={(e) => setCommand(e.target.value)} placeholder="npx" className={`${inputCls} font-mono`} />
              </div>
              <div>
                <label className={labelCls}>{t("skills.mcpArgs", "Arguments")}</label>
                <input value={argsText} onChange={(e) => setArgsText(e.target.value)} placeholder="@playwright/mcp@latest" className={`${inputCls} font-mono`} />
              </div>
              <div>
                <div className="mb-1 flex items-center justify-between">
                  <label className={labelCls}>{t("skills.mcpEnvVars", "Environment Variables")}</label>
                  <button type="button" onClick={() => addPair(setEnvPairs)} className="text-xs text-emerald-600 hover:underline">
                    <Plus className="mr-0.5 inline h-3 w-3" />{t("skills.mcpAddVar", "Add")}
                  </button>
                </div>
                {envPairs.map((pair, idx) => (
                  <div key={idx} className="mb-1.5 flex gap-2">
                    <input value={pair.key} onChange={(e) => updatePair(setEnvPairs, idx, "key", e.target.value)} placeholder="KEY" className={`w-1/3 ${kvInputCls}`} />
                    <input value={pair.value} onChange={(e) => updatePair(setEnvPairs, idx, "value", e.target.value)} placeholder="value" className={`flex-1 ${kvInputCls}`} />
                    <button onClick={() => removePair(setEnvPairs, idx)} className="rounded-lg p-2 text-zinc-400 hover:bg-rose-500/10 hover:text-rose-600"><X className="h-3 w-3" /></button>
                  </div>
                ))}
              </div>
            </>
          )}

          {transportType !== "stdio" && (
            <>
              <div>
                <label className={labelCls}>URL *</label>
                <input value={url} onChange={(e) => setUrl(e.target.value)} className={`${inputCls} font-mono`} />
              </div>
              <div>
                <div className="mb-1 flex items-center justify-between">
                  <label className={labelCls}>{t("skills.mcpHeaders", "Headers")}</label>
                  <button type="button" onClick={() => addPair(setHeaderPairs)} className="text-xs text-emerald-600 hover:underline">
                    <Plus className="mr-0.5 inline h-3 w-3" />{t("skills.mcpAddHeader", "Add")}
                  </button>
                </div>
                {headerPairs.map((pair, idx) => (
                  <div key={idx} className="mb-1.5 flex gap-2">
                    <input value={pair.key} onChange={(e) => updatePair(setHeaderPairs, idx, "key", e.target.value)} placeholder="Header" className={`w-1/3 ${kvInputCls}`} />
                    <input value={pair.value} onChange={(e) => updatePair(setHeaderPairs, idx, "value", e.target.value)} placeholder="value" className={`flex-1 ${kvInputCls}`} />
                    <button onClick={() => removePair(setHeaderPairs, idx)} className="rounded-lg p-2 text-zinc-400 hover:bg-rose-500/10 hover:text-rose-600"><X className="h-3 w-3" /></button>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        {error && <div className="mt-4 rounded-xl bg-rose-500/10 px-4 py-2.5 text-sm text-rose-700 dark:text-rose-300">{error}</div>}

        <div className="mt-6 flex justify-end gap-2 border-t border-zinc-100 pt-4 dark:border-zinc-800">
          <button onClick={onClose} className="rounded-xl border border-zinc-200 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800">
            {t("common.cancel", "Cancel")}
          </button>
          <button onClick={() => void handleSave()} disabled={isSaving || !name.trim()}
            className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-500 px-5 py-2 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-50">
            {isSaving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {t("common.save", "Save")}
          </button>
        </div>
      </div>
    </LayoutModal>
  );
}
