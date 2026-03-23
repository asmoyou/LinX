import { useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  Globe,
  Loader2,
  Pencil,
  Play,
  Plug,
  RefreshCw,
  Terminal,
  Trash2,
  Unplug,
  Wrench,
  Zap,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { McpServer, McpServerTool } from "@/api/mcpServers";
import { mcpServersApi } from "@/api/mcpServers";

interface McpServerCardProps {
  server: McpServer;
  onSync: (serverId: string) => Promise<void>;
  onConnect: (serverId: string) => Promise<void>;
  onDisconnect: (serverId: string) => Promise<void>;
  onDelete: (serverId: string) => Promise<void>;
  onEdit: (server: McpServer) => void;
  onTestTool?: (skillId: string) => void;
}

const transportIcons: Record<string, typeof Terminal> = {
  stdio: Terminal,
  sse: Zap,
  streamable_http: Globe,
};

const transportLabels: Record<string, string> = {
  stdio: "stdio",
  sse: "SSE",
  streamable_http: "HTTP",
};

const statusConfig: Record<
  string,
  { dot: string; label: string; bg: string }
> = {
  connected: {
    dot: "bg-emerald-500",
    label: "Connected",
    bg: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  },
  disconnected: {
    dot: "bg-zinc-400",
    label: "Disconnected",
    bg: "bg-zinc-500/10 text-zinc-600 dark:text-zinc-400",
  },
  error: {
    dot: "bg-rose-500",
    label: "Error",
    bg: "bg-rose-500/10 text-rose-700 dark:text-rose-300",
  },
  syncing: {
    dot: "bg-amber-500 animate-pulse",
    label: "Syncing",
    bg: "bg-amber-500/10 text-amber-700 dark:text-amber-300",
  },
};

export default function McpServerCard({
  server,
  onSync,
  onConnect,
  onDisconnect,
  onDelete,
  onEdit,
  onTestTool,
}: McpServerCardProps) {
  const { t } = useTranslation();
  const [isSyncing, setIsSyncing] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [showTools, setShowTools] = useState(false);
  const [tools, setTools] = useState<McpServerTool[]>([]);
  const [isLoadingTools, setIsLoadingTools] = useState(false);

  const TransportIcon = transportIcons[server.transport_type] || Globe;
  const status = statusConfig[server.status] || statusConfig.disconnected;

  const handleSync = async () => {
    setIsSyncing(true);
    try {
      await onSync(server.server_id);
    } finally {
      setIsSyncing(false);
    }
  };

  const handleConnect = async () => {
    setIsConnecting(true);
    try {
      await onConnect(server.server_id);
    } finally {
      setIsConnecting(false);
    }
  };

  const handleToggleTools = async () => {
    if (showTools) {
      setShowTools(false);
      return;
    }
    setIsLoadingTools(true);
    try {
      const result = await mcpServersApi.getTools(server.server_id);
      setTools(result);
    } catch {
      setTools([]);
    } finally {
      setIsLoadingTools(false);
      setShowTools(true);
    }
  };

  return (
    <div className="glass-panel group relative rounded-2xl border border-border/40 p-5 shadow-sm transition-shadow hover:shadow-md">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/10">
            <Plug className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">
              {server.name}
            </h3>
            {server.description && (
              <p className="mt-0.5 text-xs text-muted-foreground line-clamp-1">
                {server.description}
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
          <button
            onClick={() => onEdit(server)}
            className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600 dark:hover:bg-zinc-800"
            title={t("skills.mcpEdit", "Edit")}
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => void onDelete(server.server_id)}
            className="rounded-lg p-1.5 text-zinc-400 hover:bg-rose-500/10 hover:text-rose-600"
            title={t("skills.mcpDelete", "Delete")}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Status + transport badges */}
      <div className="mt-4 flex items-center gap-2">
        <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${status.bg}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${status.dot}`} />
          {status.label}
        </span>
        <span className="inline-flex items-center gap-1 rounded-full bg-zinc-100 px-2.5 py-1 text-xs font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
          <TransportIcon className="h-3 w-3" />
          {transportLabels[server.transport_type] || server.transport_type}
        </span>
      </div>

      {/* Stats */}
      <div className="mt-4 grid grid-cols-2 gap-3">
        <div>
          <div className="text-xs text-muted-foreground">
            {t("skills.mcpToolCount", "Tools")}
          </div>
          <div className="mt-0.5 flex items-center gap-1 text-sm font-semibold text-foreground">
            <Wrench className="h-3.5 w-3.5 text-muted-foreground" />
            {server.tool_count}
          </div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">
            {t("skills.mcpLastSync", "Last Sync")}
          </div>
          <div className="mt-0.5 text-sm text-foreground">
            {server.last_sync_at
              ? new Date(server.last_sync_at).toLocaleDateString()
              : "—"}
          </div>
        </div>
      </div>

      {/* Error message */}
      {server.error_message && (
        <div className="mt-3 rounded-lg bg-rose-500/10 px-3 py-2 text-xs text-rose-700 dark:text-rose-300 break-words">
          {server.error_message}
        </div>
      )}

      {/* Action buttons */}
      <div className="mt-4 flex gap-2">
        <button
          onClick={handleSync}
          disabled={isSyncing}
          className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-border/50 bg-white px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-muted/50 disabled:opacity-50 dark:bg-zinc-900 dark:hover:bg-zinc-800"
        >
          {isSyncing ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5" />
          )}
          {t("skills.mcpSync", "Sync Tools")}
        </button>
        {server.status !== "connected" ? (
          <button
            onClick={handleConnect}
            disabled={isConnecting}
            className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-emerald-500 px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-emerald-600 disabled:opacity-50"
          >
            {isConnecting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Plug className="h-3.5 w-3.5" />
            )}
            {t("skills.mcpConnect", "Connect")}
          </button>
        ) : (
          <button
            onClick={() => void onDisconnect(server.server_id)}
            className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-rose-200 bg-white px-3 py-2 text-xs font-medium text-rose-600 transition-colors hover:bg-rose-50 dark:border-rose-500/30 dark:bg-zinc-900 dark:text-rose-400 dark:hover:bg-rose-500/10"
          >
            <Unplug className="h-3.5 w-3.5" />
            {t("skills.mcpDisconnect", "Disconnect")}
          </button>
        )}
      </div>

      {/* Expand: View tools */}
      {server.tool_count > 0 && (
        <div className="mt-3 border-t border-border/30 pt-3">
          <button
            onClick={() => void handleToggleTools()}
            className="flex w-full items-center justify-between text-xs font-medium text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
          >
            <span>{t("skills.mcpViewTools", "View Tools")} ({server.tool_count})</span>
            {showTools ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>

          {showTools && (
            <div className="mt-2 max-h-52 space-y-1.5 overflow-y-auto">
              {isLoadingTools ? (
                <div className="flex justify-center py-3">
                  <Loader2 className="h-4 w-4 animate-spin text-zinc-400" />
                </div>
              ) : tools.length === 0 ? (
                <p className="py-2 text-center text-xs text-zinc-400">
                  {t("skills.mcpNoToolsFound", "No tools found")}
                </p>
              ) : (
                tools.map((tool) => (
                  <div
                    key={tool.skill_id}
                    className="flex items-center justify-between rounded-lg border border-border/30 bg-zinc-50 px-3 py-2 dark:bg-zinc-800/50"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-xs font-medium text-foreground">
                        {tool.display_name}
                      </div>
                      {tool.description && (
                        <div className="mt-0.5 truncate text-[11px] text-zinc-400">
                          {tool.description}
                        </div>
                      )}
                    </div>
                    {onTestTool && (
                      <button
                        onClick={() => onTestTool(tool.skill_id)}
                        className="ml-2 shrink-0 rounded-lg p-1.5 text-zinc-400 hover:bg-emerald-500/10 hover:text-emerald-600"
                        title={t("skills.mcpTestTool", "Test")}
                      >
                        <Play className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
