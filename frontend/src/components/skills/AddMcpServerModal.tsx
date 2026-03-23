import { useState } from "react";
import {
  Braces,
  Globe,
  Loader2,
  Plus,
  Terminal,
  X,
  Zap,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { LayoutModal } from "@/components/LayoutModal";
import type { CreateMcpServerRequest } from "@/api/mcpServers";
import { mcpServersApi } from "@/api/mcpServers";

interface AddMcpServerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: () => void;
}

type InputMode = "form" | "json";

const transportOptions = [
  {
    value: "stdio" as const,
    icon: Terminal,
    label: "stdio",
    desc: "Run a local command (e.g. npx, python)",
  },
  {
    value: "sse" as const,
    icon: Zap,
    label: "SSE",
    desc: "Connect to a remote server via SSE",
  },
  {
    value: "streamable_http" as const,
    icon: Globe,
    label: "Streamable HTTP",
    desc: "Connect via the newer HTTP transport",
  },
];

const JSON_PLACEHOLDER = `{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest"]
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "your-token"
      }
    }
  }
}`;

/**
 * Parse standard MCP config JSON into CreateMcpServerRequest[].
 *
 * Accepts three formats:
 * 1. `{ mcpServers: { name: { command, args, env } } }`  — official multi-server format
 * 2. `{ name: { command, args, env } }`                   — shorthand without wrapper
 * 3. `{ command, args, env }`                             — single server (name required separately)
 */
function parseMcpJson(
  raw: string,
): { servers: { name: string; req: CreateMcpServerRequest }[]; error?: string } {
  let parsed: any;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { servers: [], error: "Invalid JSON" };
  }

  if (typeof parsed !== "object" || parsed === null) {
    return { servers: [], error: "JSON must be an object" };
  }

  // Unwrap `mcpServers` wrapper if present
  let entries: Record<string, any> = parsed.mcpServers ?? parsed;

  // Single-server shorthand: { command: "npx", args: [...] }
  if (typeof entries.command === "string") {
    return {
      servers: [
        {
          name: "",
          req: buildReqFromEntry(entries),
        },
      ],
    };
  }

  const servers: { name: string; req: CreateMcpServerRequest }[] = [];
  for (const [serverName, cfg] of Object.entries(entries)) {
    if (typeof cfg !== "object" || cfg === null) continue;
    servers.push({
      name: serverName,
      req: buildReqFromEntry(cfg, serverName),
    });
  }

  if (servers.length === 0) {
    return { servers: [], error: "No server entries found in JSON" };
  }

  return { servers };
}

function buildReqFromEntry(entry: any, name?: string): CreateMcpServerRequest {
  const hasCommand = typeof entry.command === "string";
  const hasUrl = typeof entry.url === "string";

  let transportType: CreateMcpServerRequest["transport_type"] = "stdio";
  if (!hasCommand && hasUrl) {
    transportType = entry.transport_type === "streamable_http" ? "streamable_http" : "sse";
  }

  return {
    name: name || "",
    transport_type: transportType,
    command: hasCommand ? entry.command : undefined,
    args: Array.isArray(entry.args) ? entry.args : undefined,
    url: hasUrl ? entry.url : undefined,
    env_vars: entry.env && typeof entry.env === "object" ? entry.env : undefined,
    headers: entry.headers && typeof entry.headers === "object" ? entry.headers : undefined,
  };
}

export default function AddMcpServerModal({
  isOpen,
  onClose,
  onCreated,
}: AddMcpServerModalProps) {
  const { t } = useTranslation();
  const [inputMode, setInputMode] = useState<InputMode>("json");

  // Form mode state
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [transportType, setTransportType] =
    useState<CreateMcpServerRequest["transport_type"]>("stdio");
  const [command, setCommand] = useState("");
  const [argsText, setArgsText] = useState("");
  const [url, setUrl] = useState("");
  const [envPairs, setEnvPairs] = useState<{ key: string; value: string }[]>([]);
  const [headerPairs, setHeaderPairs] = useState<{ key: string; value: string }[]>([]);

  // JSON mode state
  const [jsonText, setJsonText] = useState("");

  // Shared state
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  if (!isOpen) return null;

  const resetForm = () => {
    setName("");
    setDescription("");
    setTransportType("stdio");
    setCommand("");
    setArgsText("");
    setUrl("");
    setEnvPairs([]);
    setHeaderPairs([]);
    setJsonText("");
    setError(null);
    setSuccessMsg(null);
  };

  const handleClose = () => {
    resetForm();
    onClose();
  };

  // --- Form mode helpers ---

  const pairsToRecord = (
    pairs: { key: string; value: string }[],
  ): Record<string, string> | undefined => {
    const filtered = pairs.filter((p) => p.key.trim());
    if (filtered.length === 0) return undefined;
    const record: Record<string, string> = {};
    for (const p of filtered) record[p.key.trim()] = p.value;
    return record;
  };

  const buildFormRequest = (): CreateMcpServerRequest => ({
    name: name.trim(),
    description: description.trim() || undefined,
    transport_type: transportType,
    command: transportType === "stdio" ? command.trim() || undefined : undefined,
    args:
      transportType === "stdio" && argsText.trim()
        ? argsText.split(/\s+/).map((s) => s.trim()).filter(Boolean)
        : undefined,
    url: transportType !== "stdio" ? url.trim() || undefined : undefined,
    env_vars: transportType === "stdio" ? pairsToRecord(envPairs) : undefined,
    headers: transportType !== "stdio" ? pairsToRecord(headerPairs) : undefined,
  });

  // --- Save logic ---

  const createAndSync = async (req: CreateMcpServerRequest) => {
    const server = await mcpServersApi.create(req);
    try {
      await mcpServersApi.testConnection(server.server_id);
      await mcpServersApi.syncTools(server.server_id);
    } catch {
      // Non-fatal
    }
    return server;
  };

  const handleSaveForm = async () => {
    if (!name.trim()) {
      setError(t("skills.mcpNameRequired", "Name is required"));
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      await createAndSync(buildFormRequest());
      resetForm();
      onCreated();
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || "Failed to create MCP server");
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveJson = async () => {
    if (!jsonText.trim()) {
      setError(t("skills.mcpJsonRequired", "Please paste MCP server JSON"));
      return;
    }
    const { servers, error: parseError } = parseMcpJson(jsonText.trim());
    if (parseError) {
      setError(parseError);
      return;
    }
    if (servers.length === 0) {
      setError("No servers found in JSON");
      return;
    }
    // Validate all servers have names
    for (const s of servers) {
      if (!s.name && !s.req.name) {
        setError("Each server entry must have a name");
        return;
      }
      if (!s.req.name) s.req.name = s.name;
    }

    setIsSaving(true);
    setError(null);
    const results: string[] = [];
    const errors: string[] = [];
    try {
      for (const s of servers) {
        try {
          await createAndSync(s.req);
          results.push(s.req.name);
        } catch (e: any) {
          errors.push(`${s.req.name}: ${e?.response?.data?.detail || e?.message || "failed"}`);
        }
      }
      if (results.length > 0) {
        onCreated();
      }
      if (errors.length > 0) {
        setError(errors.join("\n"));
        setSuccessMsg(
          results.length > 0
            ? t("skills.mcpJsonPartialSuccess", {
                count: results.length,
                defaultValue: `${results.length} server(s) created successfully.`,
              })
            : null,
        );
      } else {
        resetForm();
        onClose();
      }
    } finally {
      setIsSaving(false);
    }
  };

  const handleSave = () => {
    void (inputMode === "json" ? handleSaveJson() : handleSaveForm());
  };

  // --- Key-value pair helpers ---

  const addPair = (
    setter: React.Dispatch<React.SetStateAction<{ key: string; value: string }[]>>,
  ) => {
    setter((prev) => [...prev, { key: "", value: "" }]);
  };

  const updatePair = (
    setter: React.Dispatch<React.SetStateAction<{ key: string; value: string }[]>>,
    idx: number,
    field: "key" | "value",
    val: string,
  ) => {
    setter((prev) => prev.map((p, i) => (i === idx ? { ...p, [field]: val } : p)));
  };

  const removePair = (
    setter: React.Dispatch<React.SetStateAction<{ key: string; value: string }[]>>,
    idx: number,
  ) => {
    setter((prev) => prev.filter((_, i) => i !== idx));
  };

  return (
    <LayoutModal
      isOpen={isOpen}
      onClose={handleClose}
      closeOnBackdropClick={false}
      closeOnEscape={true}
    >
      <div className="w-full max-w-2xl max-h-[calc(100vh-var(--app-header-height,4rem)-3rem)] overflow-y-auto modal-panel rounded-[24px] shadow-2xl p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-2xl font-bold text-zinc-800 dark:text-white">
            {t("skills.mcpAddServer", "Add MCP Server")}
          </h2>
          <button
            onClick={handleClose}
            className="p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors"
          >
            <X className="w-6 h-6 text-zinc-700 dark:text-zinc-300" />
          </button>
        </div>

        {/* Input mode toggle */}
        <div className="mb-5 inline-flex rounded-xl border border-zinc-200 bg-zinc-50 p-1 dark:border-zinc-700 dark:bg-zinc-800/50">
          <button
            type="button"
            onClick={() => setInputMode("json")}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors ${
              inputMode === "json"
                ? "bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white"
                : "text-zinc-500 hover:text-zinc-700 dark:text-zinc-400"
            }`}
          >
            <Braces className="h-3.5 w-3.5" />
            {t("skills.mcpJsonImport", "JSON Import")}
          </button>
          <button
            type="button"
            onClick={() => setInputMode("form")}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors ${
              inputMode === "form"
                ? "bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white"
                : "text-zinc-500 hover:text-zinc-700 dark:text-zinc-400"
            }`}
          >
            <Terminal className="h-3.5 w-3.5" />
            {t("skills.mcpManualForm", "Manual")}
          </button>
        </div>

        {/* === JSON Import Mode === */}
        {inputMode === "json" && (
          <div className="space-y-4">
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              {t(
                "skills.mcpJsonHint",
                "Paste the standard MCP server JSON config. Supports the official format used by Claude Desktop / Cursor / etc.",
              )}
            </p>
            <textarea
              value={jsonText}
              onChange={(e) => {
                setJsonText(e.target.value);
                setError(null);
              }}
              placeholder={JSON_PLACEHOLDER}
              rows={14}
              className="w-full rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 font-mono text-sm text-zinc-800 outline-none transition-colors focus:border-emerald-500 dark:border-zinc-700 dark:bg-zinc-800/50 dark:text-zinc-200"
            />
          </div>
        )}

        {/* === Manual Form Mode === */}
        {inputMode === "form" && (
          <div className="space-y-4">
            {/* Name */}
            <div>
              <label className="mb-1 block text-xs font-medium text-zinc-700 dark:text-zinc-300">
                {t("skills.mcpName", "Name")} *
              </label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. filesystem-server"
                className="w-full rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-sm outline-none focus:border-emerald-500 dark:border-zinc-700 dark:bg-zinc-800/50 dark:text-zinc-200"
              />
            </div>

            {/* Description */}
            <div>
              <label className="mb-1 block text-xs font-medium text-zinc-700 dark:text-zinc-300">
                {t("skills.mcpDescription", "Description")}
              </label>
              <input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optional description"
                className="w-full rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-sm outline-none focus:border-emerald-500 dark:border-zinc-700 dark:bg-zinc-800/50 dark:text-zinc-200"
              />
            </div>

            {/* Transport type */}
            <div>
              <label className="mb-2 block text-xs font-medium text-zinc-700 dark:text-zinc-300">
                {t("skills.mcpTransport", "Transport")}
              </label>
              <div className="grid grid-cols-3 gap-2">
                {transportOptions.map((opt) => {
                  const Icon = opt.icon;
                  const active = transportType === opt.value;
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => {
                        setTransportType(opt.value);
                        if (opt.value === "stdio") {
                          setUrl("");
                          setHeaderPairs([]);
                        } else {
                          setCommand("");
                          setArgsText("");
                          setEnvPairs([]);
                        }
                      }}
                      className={`flex flex-col items-center gap-1 rounded-xl border px-3 py-3 text-xs transition-colors ${
                        active
                          ? "border-emerald-500 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                          : "border-zinc-200 text-zinc-500 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800"
                      }`}
                    >
                      <Icon className="h-4 w-4" />
                      <span className="font-medium">{opt.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* stdio fields */}
            {transportType === "stdio" && (
              <>
                <div>
                  <label className="mb-1 block text-xs font-medium text-zinc-700 dark:text-zinc-300">
                    {t("skills.mcpCommand", "Command")} *
                  </label>
                  <input
                    value={command}
                    onChange={(e) => setCommand(e.target.value)}
                    placeholder="e.g. npx, python, node"
                    className="w-full rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-sm font-mono outline-none focus:border-emerald-500 dark:border-zinc-700 dark:bg-zinc-800/50 dark:text-zinc-200"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-zinc-700 dark:text-zinc-300">
                    {t("skills.mcpArgs", "Arguments")}
                  </label>
                  <input
                    value={argsText}
                    onChange={(e) => setArgsText(e.target.value)}
                    placeholder="e.g. -y @modelcontextprotocol/server-filesystem /tmp"
                    className="w-full rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-sm font-mono outline-none focus:border-emerald-500 dark:border-zinc-700 dark:bg-zinc-800/50 dark:text-zinc-200"
                  />
                  <p className="mt-1 text-xs text-zinc-400">
                    {t("skills.mcpArgsHint", "Space-separated arguments")}
                  </p>
                </div>

                {/* Env vars */}
                <div>
                  <div className="mb-1 flex items-center justify-between">
                    <label className="text-xs font-medium text-zinc-700 dark:text-zinc-300">
                      {t("skills.mcpEnvVars", "Environment Variables")}
                    </label>
                    <button
                      type="button"
                      onClick={() => addPair(setEnvPairs)}
                      className="text-xs text-emerald-600 hover:underline"
                    >
                      <Plus className="mr-0.5 inline h-3 w-3" />
                      {t("skills.mcpAddVar", "Add")}
                    </button>
                  </div>
                  {envPairs.map((pair, idx) => (
                    <div key={idx} className="mb-1.5 flex gap-2">
                      <input
                        value={pair.key}
                        onChange={(e) => updatePair(setEnvPairs, idx, "key", e.target.value)}
                        placeholder="KEY"
                        className="w-1/3 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs font-mono outline-none focus:border-emerald-500 dark:border-zinc-700 dark:bg-zinc-800/50"
                      />
                      <input
                        value={pair.value}
                        onChange={(e) => updatePair(setEnvPairs, idx, "value", e.target.value)}
                        placeholder="value"
                        className="flex-1 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs font-mono outline-none focus:border-emerald-500 dark:border-zinc-700 dark:bg-zinc-800/50"
                      />
                      <button
                        onClick={() => removePair(setEnvPairs, idx)}
                        className="rounded-lg p-2 text-zinc-400 hover:bg-rose-500/10 hover:text-rose-600"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                  ))}
                </div>
              </>
            )}

            {/* SSE / Streamable HTTP fields */}
            {transportType !== "stdio" && (
              <>
                <div>
                  <label className="mb-1 block text-xs font-medium text-zinc-700 dark:text-zinc-300">
                    URL *
                  </label>
                  <input
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder={
                      transportType === "sse"
                        ? "http://localhost:8080/sse"
                        : "http://localhost:8080/mcp"
                    }
                    className="w-full rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-sm font-mono outline-none focus:border-emerald-500 dark:border-zinc-700 dark:bg-zinc-800/50 dark:text-zinc-200"
                  />
                </div>

                {/* Headers */}
                <div>
                  <div className="mb-1 flex items-center justify-between">
                    <label className="text-xs font-medium text-zinc-700 dark:text-zinc-300">
                      {t("skills.mcpHeaders", "Headers")}
                    </label>
                    <button
                      type="button"
                      onClick={() => addPair(setHeaderPairs)}
                      className="text-xs text-emerald-600 hover:underline"
                    >
                      <Plus className="mr-0.5 inline h-3 w-3" />
                      {t("skills.mcpAddHeader", "Add")}
                    </button>
                  </div>
                  {headerPairs.map((pair, idx) => (
                    <div key={idx} className="mb-1.5 flex gap-2">
                      <input
                        value={pair.key}
                        onChange={(e) => updatePair(setHeaderPairs, idx, "key", e.target.value)}
                        placeholder="Header-Name"
                        className="w-1/3 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs font-mono outline-none focus:border-emerald-500 dark:border-zinc-700 dark:bg-zinc-800/50"
                      />
                      <input
                        value={pair.value}
                        onChange={(e) => updatePair(setHeaderPairs, idx, "value", e.target.value)}
                        placeholder="value"
                        className="flex-1 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs font-mono outline-none focus:border-emerald-500 dark:border-zinc-700 dark:bg-zinc-800/50"
                      />
                      <button
                        onClick={() => removePair(setHeaderPairs, idx)}
                        className="rounded-lg p-2 text-zinc-400 hover:bg-rose-500/10 hover:text-rose-600"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        {/* Error / Success */}
        {error && (
          <div className="mt-4 rounded-xl bg-rose-500/10 px-4 py-2.5 text-sm text-rose-700 dark:text-rose-300 whitespace-pre-wrap">
            {error}
          </div>
        )}
        {successMsg && (
          <div className="mt-4 rounded-xl bg-emerald-500/10 px-4 py-2.5 text-sm text-emerald-700 dark:text-emerald-300">
            {successMsg}
          </div>
        )}

        {/* Footer */}
        <div className="mt-6 flex justify-end gap-2 border-t border-zinc-100 pt-4 dark:border-zinc-800">
          <button
            onClick={handleClose}
            className="rounded-xl border border-zinc-200 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            {t("common.cancel", "Cancel")}
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-500 px-5 py-2 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
          >
            {isSaving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {inputMode === "json"
              ? t("skills.mcpImportAndConnect", "Import & Connect")
              : t("skills.mcpSaveAndConnect", "Save & Connect")}
          </button>
        </div>
      </div>
    </LayoutModal>
  );
}
