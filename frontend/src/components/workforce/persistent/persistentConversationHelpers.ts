import { mergeScheduleEvents, normalizeScheduleCreatedEvent } from "@/components/schedules/scheduleUtils";
import type { ConversationMessage } from "@/types/agent";
import type { ScheduleCreatedEvent } from "@/types/schedule";

const WORKSPACE_PATH_PATTERN = /\/workspace\/[^\s,)\]}>"'`，。；！？]+/gi;
const FILE_PATH_KV_PATTERN = /file_path=([^\s,)\]}>"'`]+)/gi;
const FILE_ACTION_PATH_PATTERN =
  /(?:wrote|appended to|edited)\s+([^\s,)\]}>"'`]+)/gi;
const RELATIVE_FILE_PATH_PATTERN =
  /(?:^|[\s"'`(（【])((?:\.\/)?[^\s"'`<>(){}[\]]+\.(?:md|markdown|txt|json|csv|ya?ml|pdf|docx?|xlsx?|pptx?|html?))(?=$|[\s"'`)\]}>，。；;!?])/gi;
const PERSISTENT_IGNORED_ARTIFACT_ROOTS = new Set([
  "input",
  "logs",
  "tasks",
  ".linx_runtime",
  ".linux_runtime",
  "pip_cache",
  "python_deps",
]);
const PERSISTENT_IGNORED_ARTIFACT_NAMES = new Set([
  ".venv",
  "node_modules",
  ".skills",
  "__pycache__",
  ".pytest_cache",
  ".mypy_cache",
]);

export type PersistentConversationPhase =
  | "thinking"
  | "using_tools"
  | "finalizing"
  | "recovering";

export type PersistentProcessKind =
  | "thinking"
  | "context"
  | "memory"
  | "knowledge"
  | "attachments"
  | "tool"
  | "finalizing"
  | "recovering";

export interface PersistentConversationArtifactItem {
  path: string;
  name: string;
}

export interface PersistentProcessDescriptor {
  phase: PersistentConversationPhase;
  kind: PersistentProcessKind;
  detail: string | null;
  accent: string | null;
}

export function normalizeWorkspaceFilePath(rawPath: string): string {
  let normalized = String(rawPath || "")
    .trim()
    .replace(/\\/g, "/");
  normalized = normalized.replace(/^[\s("'`[{（【]+/, "");
  normalized = normalized.replace(/[\s)"'`.,:;!?，。；！？}\]）】]+$/, "");
  if (!normalized) return "";
  if (/^(?:https?:|data:|file:)/i.test(normalized)) return "";

  const workspaceIndex = normalized.indexOf("/workspace/");
  if (workspaceIndex >= 0) {
    normalized = normalized.slice(workspaceIndex);
  }

  if (normalized.startsWith("workspace/")) {
    normalized = `/${normalized}`;
  }

  if (!normalized.startsWith("/workspace/")) {
    if (normalized.startsWith("./")) {
      normalized = normalized.slice(2);
    }
    if (normalized.startsWith("/")) return "";
    normalized = `/workspace/${normalized}`;
  }

  if (normalized.includes("..")) return "";
  return normalized.startsWith("/workspace/") ? normalized : "";
}

function extractWorkspacePathsFromText(text: string): string[] {
  const source = String(text || "");
  const unique = new Set<string>();
  const candidatePaths: string[] = [];

  const absoluteMatches = source.match(WORKSPACE_PATH_PATTERN) || [];
  candidatePaths.push(...absoluteMatches);

  for (const match of source.matchAll(FILE_PATH_KV_PATTERN)) {
    if (match[1]) {
      candidatePaths.push(match[1]);
    }
  }

  for (const match of source.matchAll(FILE_ACTION_PATH_PATTERN)) {
    if (match[1]) {
      candidatePaths.push(match[1]);
    }
  }

  for (const match of source.matchAll(RELATIVE_FILE_PATH_PATTERN)) {
    if (match[1]) {
      candidatePaths.push(match[1]);
    }
  }

  candidatePaths.forEach((rawPath) => {
    const normalized = normalizeWorkspaceFilePath(rawPath);
    if (!normalized || normalized.startsWith("/workspace/input/")) {
      return;
    }
    unique.add(normalized);
  });

  return [...unique];
}

function normalizeProcessText(value: unknown, maxChars = 140): string {
  const normalized = String(value || "")
    .replace(/\*\*/g, "")
    .replace(/`/g, "")
    .replace(/\s+/g, " ")
    .trim();

  if (normalized.length <= maxChars) {
    return normalized;
  }

  return `${normalized.slice(0, Math.max(0, maxChars - 1)).trimEnd()}…`;
}

function basename(path: string): string {
  return path.split("/").filter(Boolean).pop() || path;
}

function normalizeArtifactEntryPath(rawEntry: any): string {
  return normalizeWorkspaceFilePath(
    rawEntry?.path || rawEntry?.file_path || rawEntry?.filePath || "",
  );
}

function isDirectoryArtifactEntry(rawEntry: any): boolean {
  return Boolean(rawEntry?.is_directory || rawEntry?.is_dir);
}

function isOutputWorkspacePath(path: string): boolean {
  return path === "/workspace/output" || path.startsWith("/workspace/output/");
}

function isUserVisibleArtifactPath(path: string): boolean {
  const normalized = normalizeWorkspaceFilePath(path);
  if (!normalized) return false;

  const segments = normalized
    .replace(/^\/workspace\//, "")
    .split("/")
    .filter(Boolean);

  if (segments.length === 0) {
    return false;
  }

  const [firstSegment, ...restSegments] = segments;
  if (
    PERSISTENT_IGNORED_ARTIFACT_ROOTS.has(firstSegment) ||
    firstSegment.startsWith(".")
  ) {
    return false;
  }

  if (
    [firstSegment, ...restSegments].some(
      (segment) =>
        segment.startsWith(".") || PERSISTENT_IGNORED_ARTIFACT_NAMES.has(segment),
    )
  ) {
    return false;
  }

  return true;
}

function artifactDisplayName(path: string, name?: unknown): string {
  const explicitName = String(name || "").trim();
  if (explicitName) {
    return explicitName;
  }

  return path.split("/").filter(Boolean).pop() || path;
}

function addArtifactItem(
  target: Map<string, PersistentConversationArtifactItem>,
  path: string,
  name?: unknown,
): void {
  if (!isUserVisibleArtifactPath(path) || target.has(path)) {
    return;
  }

  target.set(path, {
    path,
    name: artifactDisplayName(path, name),
  });
}

function normalizeArtifactEntry(rawEntry: any): PersistentConversationArtifactItem | null {
  const path = normalizeArtifactEntryPath(rawEntry);
  if (!path || isDirectoryArtifactEntry(rawEntry) || !isUserVisibleArtifactPath(path)) {
    return null;
  }

  return {
    path,
    name: artifactDisplayName(path, rawEntry?.name),
  };
}

function selectPersistentDeliverableArtifacts(
  artifacts: unknown,
): PersistentConversationArtifactItem[] {
  const selected: PersistentConversationArtifactItem[] = [];
  for (const entry of Array.isArray(artifacts) ? artifacts : []) {
    const normalized = normalizeArtifactEntry(entry);
    if (!normalized) {
      continue;
    }
    selected.push(normalized);
  }
  return selected;
}

function selectPersistentExplicitlyReferencedArtifacts(
  artifacts: PersistentConversationArtifactItem[],
  ...texts: Array<string | null | undefined>
): PersistentConversationArtifactItem[] {
  const haystack = texts
    .map((text) => String(text || ""))
    .join("\n")
    .toLowerCase();

  if (!haystack.trim()) {
    return [];
  }

  const selected: PersistentConversationArtifactItem[] = [];
  const seenPaths = new Set<string>();
  const byName = new Map<string, PersistentConversationArtifactItem[]>();

  artifacts.forEach((artifact) => {
    const fileName = basename(artifact.path).toLowerCase();
    if (fileName) {
      byName.set(fileName, [...(byName.get(fileName) || []), artifact]);
    }

    const normalizedPath = artifact.path.replace(/^\/workspace\//, "").toLowerCase();
    if (
      haystack.includes(artifact.path.toLowerCase()) ||
      haystack.includes(`/workspace/${normalizedPath}`) ||
      haystack.includes(`workspace/${normalizedPath}`) ||
      haystack.includes(normalizedPath)
    ) {
      selected.push(artifact);
      seenPaths.add(artifact.path);
    }
  });

  byName.forEach((matches, fileName) => {
    if (matches.length !== 1 || !haystack.includes(fileName)) {
      return;
    }
    const artifact = matches[0];
    if (seenPaths.has(artifact.path)) {
      return;
    }
    selected.push(artifact);
    seenPaths.add(artifact.path);
  });

  return selected;
}

function collectArtifactPathsFromRound(rawRound: any): string[] {
  const explicitArtifacts = Array.isArray(rawRound?.artifacts)
    ? rawRound.artifacts
    : [];
  const explicitPaths = explicitArtifacts
    .map((item: any) => normalizeWorkspaceFilePath(item?.path || ""))
    .filter(Boolean);
  const inferredPaths = extractWorkspacePathsFromText(String(rawRound?.content || ""));

  return [...new Set([...explicitPaths, ...inferredPaths])];
}

function summarizeToolCallDetail(
  content: string,
): Pick<PersistentProcessDescriptor, "accent" | "detail"> {
  const normalized = normalizeProcessText(content, 220);
  const toolMatch = normalized.match(/(?:调用工具|calling tool)\s*:\s*([a-z0-9_.-]+)/i);
  const summaryMatch =
    normalized.match(/参数摘要[:：]\s*(.+)$/i) ||
    normalized.match(/arguments?[:：]\s*(.+)$/i);
  const toolName = toolMatch?.[1]?.trim() || null;
  const summary = summaryMatch?.[1]?.trim() || "";

  if (/^bash$/i.test(toolName || "")) {
    const command = summary.match(/command=([^,]+)(?:,|$)/i)?.[1]?.trim();
    return {
      accent: toolName,
      detail: normalizeProcessText(command || "正在执行命令", 88),
    };
  }

  if (/^(write_file|append_file|edit_file)$/i.test(toolName || "")) {
    const filePath = summary.match(/file_path=([^,\s]+)(?:,|$)/i)?.[1]?.trim();
    return {
      accent: toolName,
      detail: filePath
        ? basename(normalizeWorkspaceFilePath(filePath) || filePath)
        : normalizeProcessText(summary || "正在处理文件", 88),
    };
  }

  if (/^code_execution$/i.test(toolName || "")) {
    const workspacePath = summary.match(/workspace_paths=\[([^\]]+)\]/i)?.[1]?.trim();
    return {
      accent: toolName,
      detail: workspacePath
        ? normalizeProcessText(workspacePath, 88)
        : normalizeProcessText(summary || "正在执行代码", 88),
    };
  }

  return {
    accent: toolName,
    detail: normalizeProcessText(summary || normalized || "正在调用工具", 88),
  };
}

function deriveInfoProcessDescriptor(
  content: string,
): Pick<PersistentProcessDescriptor, "kind" | "detail" | "accent"> {
  const normalized = normalizeProcessText(content, 180);

  if (
    normalized.startsWith("[记忆检索]") ||
    normalized.startsWith("[记忆命中]")
  ) {
    const scopeMatch = normalized.match(/^\[记忆(?:检索|命中)\]\[([^\]]+)\]/);
    const detail = normalized.replace(/^\[[^\]]+\](?:\[[^\]]+\])?\s*/, "").trim();
    return {
      kind: "memory",
      detail: normalizeProcessText(detail || "正在抽取记忆", 88),
      accent: scopeMatch?.[1] || null,
    };
  }

  if (
    normalized.startsWith("[知识库检索]") ||
    normalized.startsWith("[知识命中") ||
    normalized.startsWith("[知识片段")
  ) {
    const detail = normalized.replace(/^\[[^\]]+\]\s*/, "").trim();
    return {
      kind: "knowledge",
      detail: normalizeProcessText(detail || "正在检索知识库", 88),
      accent: null,
    };
  }

  if (normalized.startsWith("[上下文构建]")) {
    return {
      kind: "context",
      detail: normalizeProcessText(
        normalized.replace(/^\[[^\]]+\]\s*/, "") || "正在整理上下文",
        88,
      ),
      accent: null,
    };
  }

  if (/^Copied\s+\d+\s+uploaded file/i.test(normalized)) {
    return {
      kind: "attachments",
      detail: normalizeProcessText(normalized, 88),
      accent: null,
    };
  }

  if (/^Failed to copy one uploaded file/i.test(normalized)) {
    return {
      kind: "attachments",
      detail: normalizeProcessText(normalized, 88),
      accent: null,
    };
  }

  if (/^Using model:/i.test(normalized)) {
    return {
      kind: "thinking",
      detail: normalizeProcessText(normalized.replace(/^Using model:\s*/i, ""), 88),
      accent: null,
    };
  }

  if (/^Available skills:/i.test(normalized)) {
    return {
      kind: "context",
      detail: normalizeProcessText(
        normalized.replace(/^Available skills:\s*/i, ""),
        88,
      ),
      accent: null,
    };
  }

  if (/^Initializing agent/i.test(normalized)) {
    return {
      kind: "thinking",
      detail: null,
      accent: null,
    };
  }

  if (/^Using cached agent/i.test(normalized)) {
    return {
      kind: "thinking",
      detail: "复用已初始化运行态",
      accent: null,
    };
  }

  if (/^Retrieving relevant memories/i.test(normalized)) {
    return {
      kind: "context",
      detail: "记忆与知识检索",
      accent: null,
    };
  }

  if (/^Generating response/i.test(normalized)) {
    return {
      kind: "finalizing",
      detail: "整理最终回答",
      accent: null,
    };
  }

  return {
    kind: "thinking",
    detail: normalizeProcessText(normalized, 88) || null,
    accent: null,
  };
}

export function mapChunkToPersistentPhase(chunk: {
  type?: string;
}): PersistentConversationPhase | null {
  switch (String(chunk?.type || "").trim()) {
    case "runtime":
    case "start":
    case "info":
    case "thinking":
      return "thinking";
    case "tool_call":
      return "using_tools";
    case "tool_result":
    case "round_stats":
    case "stats":
      return "finalizing";
    case "retry_attempt":
    case "error_feedback":
    case "tool_error":
      return "recovering";
    default:
      return null;
  }
}

export function derivePersistentArtifacts(
  message: Pick<ConversationMessage, "contentText" | "contentJson">,
): PersistentConversationArtifactItem[] {
  const byPath = new Map<string, PersistentConversationArtifactItem>();
  const contentText = String(message.contentText || "").trim();
  const currentArtifacts = selectPersistentDeliverableArtifacts(message.contentJson?.artifacts);
  const artifactDelta = selectPersistentDeliverableArtifacts(message.contentJson?.artifactDelta);
  const explicitlyReferencedArtifacts = selectPersistentExplicitlyReferencedArtifacts(
    currentArtifacts,
    contentText,
  );

  artifactDelta.forEach((item) => {
    addArtifactItem(byPath, item.path, item.name);
  });
  explicitlyReferencedArtifacts.forEach((item) => {
    addArtifactItem(byPath, item.path, item.name);
  });

  if (byPath.size === 0 && currentArtifacts.length === 0) {
    const rawRounds = Array.isArray(message.contentJson?.rounds)
      ? message.contentJson.rounds
      : [];
    rawRounds.forEach((rawRound: any) => {
      collectArtifactPathsFromRound(rawRound).forEach((path) => {
        addArtifactItem(byPath, path);
      });
    });

    extractWorkspacePathsFromText(contentText).forEach((path) => {
      addArtifactItem(byPath, path);
    });
  }

  if (byPath.size === 0 && !contentText) {
    const prioritizedFallbackArtifacts = currentArtifacts.filter((item) =>
      isOutputWorkspacePath(item.path),
    );
    const fallbackArtifacts =
      prioritizedFallbackArtifacts.length > 0
        ? prioritizedFallbackArtifacts
        : currentArtifacts.length <= 4
          ? currentArtifacts
          : [];

    fallbackArtifacts.forEach((item) => {
      addArtifactItem(byPath, item.path, item.name);
    });
  }

  return [...byPath.values()].sort((a, b) => {
    const outputPriority =
      Number(isOutputWorkspacePath(b.path)) - Number(isOutputWorkspacePath(a.path));
    return outputPriority || a.path.localeCompare(b.path);
  });
}

export function derivePersistentScheduleEvents(
  message: Pick<ConversationMessage, "contentJson">,
): ScheduleCreatedEvent[] {
  let mergedEvents: ScheduleCreatedEvent[] | undefined;

  const rawRounds = Array.isArray(message.contentJson?.rounds)
    ? message.contentJson.rounds
    : [];
  rawRounds.forEach((rawRound: any) => {
    mergedEvents = mergeScheduleEvents(mergedEvents, rawRound?.scheduleEvents);
  });

  mergedEvents = mergeScheduleEvents(mergedEvents, message.contentJson?.scheduleEvents);

  return mergedEvents || [];
}

export function shouldHideProcessLine(hasStreamingContentStarted: boolean): boolean {
  return hasStreamingContentStarted;
}

export function derivePersistentProcessDescriptor(chunk: {
  type?: string;
  content?: string;
}): PersistentProcessDescriptor | null {
  const phase = mapChunkToPersistentPhase(chunk);
  const type = String(chunk?.type || "").trim();
  const content = String(chunk?.content || "").trim();

  if (type === "tool_call") {
    const summary = summarizeToolCallDetail(content);
    return {
      phase: "using_tools",
      kind: "tool",
      detail: summary.detail,
      accent: summary.accent,
    };
  }

  if (type === "tool_result" || type === "stats" || type === "round_stats") {
    const detail = normalizeProcessText(
      content.replace(/^✅\s*\*?\*?执行结果\*?\*?[:：]?\s*/u, ""),
      88,
    );
    return {
      phase: "finalizing",
      kind: "finalizing",
      detail: detail || null,
      accent: null,
    };
  }

  if (type === "retry_attempt" || type === "error_feedback" || type === "tool_error") {
    return {
      phase: "recovering",
      kind: "recovering",
      detail: normalizeProcessText(content, 88) || null,
      accent: null,
    };
  }

  if (type === "info") {
    const infoDescriptor = deriveInfoProcessDescriptor(content);
    return {
      phase: infoDescriptor.kind === "finalizing" ? "finalizing" : phase || "thinking",
      kind: infoDescriptor.kind,
      detail: infoDescriptor.detail,
      accent: infoDescriptor.accent,
    };
  }

  if (type === "start" || type === "runtime" || type === "thinking") {
    return {
      phase: phase || "thinking",
      kind: "thinking",
      detail: normalizeProcessText(content, 88) || null,
      accent: null,
    };
  }

  return phase
    ? {
        phase,
        kind:
          phase === "finalizing"
            ? "finalizing"
            : phase === "recovering"
              ? "recovering"
              : "thinking",
        detail: normalizeProcessText(content, 88) || null,
        accent: null,
      }
    : null;
}

export function getPersistentFallbackAssistantText(
  message: Pick<ConversationMessage, "contentText" | "contentJson">,
  fallbackText = "Generated output",
): string {
  const contentText = String(message.contentText || "").trim();
  if (contentText) {
    return contentText;
  }

  if (
    derivePersistentArtifacts(message).length > 0 ||
    derivePersistentScheduleEvents(message).length > 0
  ) {
    return fallbackText;
  }

  return "";
}

export function mergePersistentScheduleEvents(
  currentEvents: ScheduleCreatedEvent[],
  rawEvent: unknown,
): ScheduleCreatedEvent[] {
  const normalized = normalizeScheduleCreatedEvent(rawEvent);
  if (!normalized) {
    return currentEvents;
  }
  return mergeScheduleEvents(currentEvents, [normalized]) || currentEvents;
}
