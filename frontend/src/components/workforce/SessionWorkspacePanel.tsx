import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  ChevronDown,
  ChevronRight,
  Download,
  File,
  FileText,
  Folder,
  FolderOpen,
  Loader2,
  RefreshCw,
  Star,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { agentsApi } from '@/api';
import type { AgentSessionWorkspaceFile } from '@/api/agents';
import { FileCodePreview } from '@/components/common/FileCodePreview';

interface SessionWorkspacePanelProps {
  agentId: string;
  sessionId?: string | null;
  conversationId?: string | null;
  isOpen: boolean;
  onClose: () => void;
  focusPath?: string | null;
  displayMode?: 'portal' | 'embedded';
  zIndexClassName?: string;
}

type PreviewKind =
  | 'empty'
  | 'loading'
  | 'text'
  | 'image'
  | 'pdf'
  | 'binary'
  | 'unsupported'
  | 'error';
type MarkdownViewMode = 'source' | 'preview';
type WorkspaceSection = 'output' | 'all';

interface WorkspaceEntry extends AgentSessionWorkspaceFile {
  isOutput: boolean;
  scopeLabel: string;
}

interface FileTreeNode {
  name: string;
  path: string;
  treePath: string;
  type: 'file' | 'directory';
  size?: number;
  isOutput?: boolean;
  scopeLabel?: string;
  retentionClass?: string;
  children?: FileTreeNode[];
}

const POLL_INTERVAL_MS = 8000;
const TEXT_PREVIEW_MAX_CHARS = 120000;
const TEXT_EXTENSIONS = new Set([
  'txt',
  'md',
  'markdown',
  'json',
  'csv',
  'yaml',
  'yml',
  'xml',
  'html',
  'htm',
  'py',
  'js',
  'ts',
  'tsx',
  'jsx',
  'css',
  'scss',
  'sql',
  'log',
  'toml',
  'ini',
  'env',
  'sh',
]);
const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg']);

function formatFileSize(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function getExtension(fileName: string): string {
  const dotIndex = fileName.lastIndexOf('.');
  if (dotIndex < 0) return '';
  return fileName.slice(dotIndex + 1).toLowerCase();
}

function isMarkdownFile(fileName: string): boolean {
  const extension = getExtension(fileName);
  return extension === 'md' || extension === 'markdown';
}

function downloadBlob(blob: Blob, fileName: string): void {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  window.URL.revokeObjectURL(url);
}

function splitPathSegments(path: string): string[] {
  return path.split('/').filter(Boolean);
}

function normalizeSessionWorkspacePath(path: string): string {
  const raw = String(path || '').trim().replace(/\\/g, '/').replace(/^\/+/, '');
  if (!raw) return '';
  if (raw.startsWith('workspace/')) {
    return raw.slice('workspace/'.length);
  }
  return raw;
}

function isOutputPath(path: string): boolean {
  const normalized = normalizeSessionWorkspacePath(path);
  return normalized === 'output' || normalized.startsWith('output/');
}

function inferScopeLabel(path: string): string {
  const normalized = normalizeSessionWorkspacePath(path);
  if (!normalized) return 'workspace';
  const [firstSegment] = splitPathSegments(normalized);
  if (!firstSegment) return 'workspace';
  if (firstSegment === '.linx_runtime') return 'runtime';
  return firstSegment;
}

function getRetentionLabel(retentionClass?: string): string {
  switch (retentionClass) {
    case 'ephemeral':
      return 'ephemeral';
    case 'rebuildable':
      return 'rebuildable';
    case 'stateful_runtime':
      return 'runtime';
    default:
      return 'durable';
  }
}

function getRetentionHint(retentionClass?: string): string | null {
  switch (retentionClass) {
    case 'ephemeral':
      return 'This file is treated as temporary and can be removed automatically before snapshots.';
    case 'rebuildable':
      return 'This file is a rebuildable input copy and can be removed automatically after aging.';
    case 'stateful_runtime':
      return 'This file belongs to preserved runtime dependencies.';
    default:
      return null;
  }
}

function sortTree(nodes: FileTreeNode[]): FileTreeNode[] {
  const sorted = [...nodes].sort((a, b) => {
    if (a.type !== b.type) {
      return a.type === 'directory' ? -1 : 1;
    }
    return a.name.localeCompare(b.name);
  });

  return sorted.map((node) =>
    node.type === 'directory' && node.children
      ? { ...node, children: sortTree(node.children) }
      : node
  );
}

function buildFileTree(entries: WorkspaceEntry[]): FileTreeNode[] {
  const root: FileTreeNode[] = [];

  const ensureDirectory = (
    container: FileTreeNode[],
    name: string,
    treePath: string
  ): FileTreeNode => {
    const existing = container.find(
      (node) => node.type === 'directory' && node.treePath === treePath
    );
    if (existing) return existing;

    const created: FileTreeNode = {
      name,
      path: treePath,
      treePath,
      type: 'directory',
      children: [],
    };
    container.push(created);
    return created;
  };

  const sortedEntries = [...entries].sort((a, b) => a.path.localeCompare(b.path));

  sortedEntries.forEach((entry) => {
    const parts = splitPathSegments(entry.path);
    if (parts.length === 0) return;

    let currentLevel = root;
    let currentTreePath = '';

    for (let index = 0; index < parts.length; index += 1) {
      const part = parts[index];
      currentTreePath = currentTreePath ? `${currentTreePath}/${part}` : part;
      const isLeaf = index === parts.length - 1;

      if (isLeaf && !entry.is_dir) {
        const exists = currentLevel.some(
          (node) => node.type === 'file' && node.path === entry.path
        );
        if (!exists) {
          currentLevel.push({
            name: entry.name || part,
            path: entry.path,
            treePath: currentTreePath,
            type: 'file',
            size: entry.size,
            isOutput: entry.isOutput,
            scopeLabel: entry.scopeLabel,
            retentionClass: entry.retentionClass,
          });
        }
      } else {
        const directory = ensureDirectory(currentLevel, part, currentTreePath);
        currentLevel = directory.children || [];
        directory.children = currentLevel;
      }
    }
  });

  return sortTree(root);
}

function findFirstFileNode(nodes: FileTreeNode[]): FileTreeNode | null {
  for (const node of nodes) {
    if (node.type === 'file') return node;
    if (node.children) {
      const found = findFirstFileNode(node.children);
      if (found) return found;
    }
  }
  return null;
}

function findFileNodeByPath(nodes: FileTreeNode[], path: string): FileTreeNode | null {
  for (const node of nodes) {
    if (node.type === 'file' && node.path === path) return node;
    if (node.type === 'directory' && node.children) {
      const found = findFileNodeByPath(node.children, path);
      if (found) return found;
    }
  }
  return null;
}

function collectAncestorFolders(treePath: string): string[] {
  const parts = splitPathSegments(treePath);
  const ancestors: string[] = [];

  parts.slice(0, -1).forEach((part, index) => {
    const parentPath = index === 0 ? part : `${ancestors[index - 1]}/${part}`;
    ancestors.push(parentPath);
  });

  return ancestors;
}

function buildFilesSignature(entries: AgentSessionWorkspaceFile[]): string {
  return entries
    .map(
      (entry) =>
        `${entry.path}|${entry.size}|${entry.modified_at || ''}|${entry.is_dir ? 'd' : 'f'}|${entry.retentionClass || ''}`
    )
    .sort()
    .join(';');
}

export const SessionWorkspacePanel: React.FC<SessionWorkspacePanelProps> = ({
  agentId,
  sessionId = null,
  conversationId = null,
  isOpen,
  onClose,
  focusPath = null,
  displayMode = 'portal',
  zIndexClassName = 'z-[60]',
}) => {
  const { t } = useTranslation();
  const [files, setFiles] = useState<AgentSessionWorkspaceFile[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<WorkspaceSection>('output');
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [previewKind, setPreviewKind] = useState<PreviewKind>('empty');
  const [previewText, setPreviewText] = useState('');
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewMime, setPreviewMime] = useState('');
  const [previewMessage, setPreviewMessage] = useState('');
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [markdownViewMode, setMarkdownViewMode] = useState<MarkdownViewMode>('preview');

  const previewUrlRef = useRef<string | null>(null);
  const runtimeKeyRef = useRef('');
  const previewRequestIdRef = useRef(0);
  const lastFilesSignatureRef = useRef('');

  const runtimeKey = conversationId
    ? `conversation:${conversationId}`
    : sessionId
      ? `session:${sessionId}`
      : '';

  const cleanupPreviewUrl = useCallback(() => {
    if (previewUrlRef.current) {
      window.URL.revokeObjectURL(previewUrlRef.current);
      previewUrlRef.current = null;
    }
    setPreviewUrl(null);
  }, []);

  const resetPreview = useCallback(() => {
    cleanupPreviewUrl();
    setPreviewKind('empty');
    setPreviewText('');
    setPreviewMime('');
    setPreviewMessage('');
    setIsPreviewLoading(false);
    setMarkdownViewMode('preview');
  }, [cleanupPreviewUrl]);

  const loadFiles = useCallback(
    async (showLoading: boolean) => {
      if (!runtimeKey || !isOpen) return;
      const requestRuntimeKey = runtimeKey;
      if (showLoading) {
        setIsLoading(true);
      }
      try {
        const list = conversationId
          ? await agentsApi.getConversationWorkspaceFiles(agentId, conversationId, '', true, {
              suppressErrorToast: true,
            })
          : await agentsApi.getSessionWorkspaceFiles(agentId, sessionId!, '', true, {
              suppressErrorToast: true,
            });

        if (runtimeKeyRef.current !== requestRuntimeKey) {
          return;
        }

        const nextSignature = buildFilesSignature(list);
        if (nextSignature !== lastFilesSignatureRef.current) {
          lastFilesSignatureRef.current = nextSignature;
          setFiles(list);
        }
        setError(null);
      } catch (loadError) {
        if (runtimeKeyRef.current !== requestRuntimeKey) {
          return;
        }
        const message =
          loadError instanceof Error
            ? loadError.message
            : t('agent.workspaceLoadFailed', 'Failed to load workspace files');
        setError(message);
      } finally {
        if (showLoading && runtimeKeyRef.current === requestRuntimeKey) {
          setIsLoading(false);
        }
      }
    },
    [agentId, conversationId, isOpen, runtimeKey, sessionId, t]
  );

  useEffect(() => {
    runtimeKeyRef.current = runtimeKey;
  }, [runtimeKey]);

  useEffect(() => {
    previewRequestIdRef.current += 1;
    lastFilesSignatureRef.current = '';

    if (!isOpen || !runtimeKey) {
      setFiles([]);
      setSelectedPath(null);
      setExpandedFolders(new Set());
      setActiveSection('output');
      setError(null);
      resetPreview();
      return;
    }

    setFiles([]);
    setSelectedPath(null);
    setExpandedFolders(new Set());
    setActiveSection('output');
    setError(null);
    resetPreview();
    void loadFiles(true);

    const timer = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return;
      void loadFiles(false);
    }, POLL_INTERVAL_MS);

    return () => {
      window.clearInterval(timer);
    };
  }, [isOpen, loadFiles, resetPreview, runtimeKey]);

  useEffect(() => {
    return () => {
      cleanupPreviewUrl();
    };
  }, [cleanupPreviewUrl]);

  const allEntries = useMemo<WorkspaceEntry[]>(
    () =>
      files
        .filter((file) => !file.is_dir)
        .map((file) => ({
          ...file,
          isOutput: isOutputPath(file.path),
          scopeLabel: inferScopeLabel(file.path),
        })),
    [files]
  );

  const outputEntries = useMemo(
    () => allEntries.filter((file) => file.isOutput),
    [allEntries]
  );

  useEffect(() => {
    if (activeSection === 'output' && outputEntries.length === 0 && allEntries.length > 0) {
      setActiveSection('all');
    }
  }, [activeSection, allEntries.length, outputEntries.length]);

  const fileEntries = useMemo(
    () => (activeSection === 'output' && outputEntries.length > 0 ? outputEntries : allEntries),
    [activeSection, allEntries, outputEntries]
  );
  const fileTree = useMemo(() => buildFileTree(fileEntries), [fileEntries]);

  const expandAncestors = useCallback((treePath: string) => {
    const ancestors = collectAncestorFolders(treePath);
    if (ancestors.length === 0) return;
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      let changed = false;
      ancestors.forEach((folderPath) => {
        if (!next.has(folderPath)) {
          next.add(folderPath);
          changed = true;
        }
      });
      return changed ? next : prev;
    });
  }, []);

  useEffect(() => {
    if (fileEntries.length === 0) {
      setSelectedPath(null);
      setExpandedFolders(new Set());
      resetPreview();
      return;
    }

    if (selectedPath && fileEntries.some((file) => file.path === selectedPath)) {
      const currentNode = findFileNodeByPath(fileTree, selectedPath);
      if (currentNode) {
        expandAncestors(currentNode.treePath);
      }
      return;
    }

    const firstFileNode = findFirstFileNode(fileTree);
    if (!firstFileNode) {
      setSelectedPath(null);
      setExpandedFolders(new Set());
      resetPreview();
      return;
    }

    setSelectedPath(firstFileNode.path);
    expandAncestors(firstFileNode.treePath);
  }, [expandAncestors, fileEntries, fileTree, resetPreview, selectedPath]);

  useEffect(() => {
    if (!focusPath) return;
    const normalizedFocusPath = normalizeSessionWorkspacePath(focusPath);
    if (!normalizedFocusPath) return;

    const targetEntry = allEntries.find((entry) => entry.path === normalizedFocusPath);
    if (!targetEntry) return;

    setActiveSection(targetEntry.isOutput ? 'output' : 'all');
    setSelectedPath(normalizedFocusPath);

    const targetNode = findFileNodeByPath(
      targetEntry.isOutput ? buildFileTree(outputEntries) : buildFileTree(allEntries),
      normalizedFocusPath
    );
    if (targetNode) {
      expandAncestors(targetNode.treePath);
    }
  }, [allEntries, expandAncestors, focusPath, outputEntries]);

  const selectedFile = useMemo(
    () => allEntries.find((item) => item.path === selectedPath) || null,
    [allEntries, selectedPath]
  );

  const loadPreview = useCallback(
    async (file: WorkspaceEntry) => {
      if (!runtimeKey) return;
      const requestId = ++previewRequestIdRef.current;
      const requestRuntimeKey = runtimeKeyRef.current;

      setIsPreviewLoading(true);
      setPreviewKind('loading');
      setPreviewText('');
      setPreviewMessage('');
      setPreviewMime('');
      cleanupPreviewUrl();

      try {
        const blob = conversationId
          ? await agentsApi.downloadConversationWorkspaceFile(agentId, conversationId, file.path, {
              suppressErrorToast: true,
            })
          : await agentsApi.downloadSessionWorkspaceFile(agentId, sessionId!, file.path, {
              suppressErrorToast: true,
            });

        if (
          previewRequestIdRef.current !== requestId ||
          runtimeKeyRef.current !== requestRuntimeKey
        ) {
          return;
        }

        const mimeType = blob.type || 'application/octet-stream';
        const ext = getExtension(file.name);
        setPreviewMime(mimeType);

        if (
          TEXT_EXTENSIONS.has(ext) ||
          file.previewable_inline ||
          mimeType.startsWith('text/') ||
          mimeType.includes('json') ||
          mimeType.includes('xml')
        ) {
          const textContent = await blob.text();
          if (
            previewRequestIdRef.current !== requestId ||
            runtimeKeyRef.current !== requestRuntimeKey
          ) {
            return;
          }
          const truncated = textContent.length > TEXT_PREVIEW_MAX_CHARS;
          setPreviewText(
            truncated ? textContent.slice(0, TEXT_PREVIEW_MAX_CHARS) : textContent
          );
          setPreviewMessage(
            truncated
              ? t(
                  'agent.workspacePreviewTruncated',
                  'Preview truncated. Download the file to view the full content.'
                )
              : ''
          );
          setPreviewKind('text');
          setMarkdownViewMode(isMarkdownFile(file.name) ? 'preview' : 'source');
          return;
        }

        if (IMAGE_EXTENSIONS.has(ext) || mimeType.startsWith('image/')) {
          const objectUrl = window.URL.createObjectURL(blob);
          previewUrlRef.current = objectUrl;
          setPreviewUrl(objectUrl);
          setPreviewKind('image');
          return;
        }

        if (ext === 'pdf' || mimeType.includes('pdf')) {
          const objectUrl = window.URL.createObjectURL(blob);
          previewUrlRef.current = objectUrl;
          setPreviewUrl(objectUrl);
          setPreviewKind('pdf');
          return;
        }

        setPreviewKind('binary');
        setPreviewMessage(
          t(
            'agent.workspacePreviewBinary',
            'This file cannot be previewed inline. Download it to inspect the content.'
          )
        );
      } catch (previewError) {
        if (
          previewRequestIdRef.current !== requestId ||
          runtimeKeyRef.current !== requestRuntimeKey
        ) {
          return;
        }
        const message =
          previewError instanceof Error
            ? previewError.message
            : t('agent.workspacePreviewFailed', 'Failed to load file preview');
        setPreviewKind('error');
        setPreviewMessage(message);
      } finally {
        if (
          previewRequestIdRef.current === requestId &&
          runtimeKeyRef.current === requestRuntimeKey
        ) {
          setIsPreviewLoading(false);
        }
      }
    },
    [agentId, cleanupPreviewUrl, conversationId, runtimeKey, sessionId, t]
  );

  useEffect(() => {
    if (!selectedFile) {
      resetPreview();
      return;
    }
    void loadPreview(selectedFile);
  }, [
    loadPreview,
    resetPreview,
    runtimeKey,
    selectedFile?.modified_at,
    selectedFile?.path,
    selectedFile?.size,
  ]);

  const handleRefresh = useCallback(() => {
    lastFilesSignatureRef.current = '';
    void loadFiles(true);
    if (selectedFile) {
      void loadPreview(selectedFile);
    }
  }, [loadFiles, loadPreview, selectedFile]);

  const handleDownload = useCallback(
    async (file: WorkspaceEntry) => {
      if (!runtimeKey) return;
      setIsDownloading(true);
      try {
        const blob = conversationId
          ? await agentsApi.downloadConversationWorkspaceFile(agentId, conversationId, file.path)
          : await agentsApi.downloadSessionWorkspaceFile(agentId, sessionId!, file.path);
        downloadBlob(blob, file.name);
      } finally {
        setIsDownloading(false);
      }
    },
    [agentId, conversationId, runtimeKey, sessionId]
  );

  const toggleFolder = useCallback((path: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  }, []);

  const handleSelectNode = useCallback(
    (node: FileTreeNode) => {
      if (node.type !== 'file') return;
      setSelectedPath(node.path);
      expandAncestors(node.treePath);
      if (node.path === selectedPath) {
        const target = allEntries.find((entry) => entry.path === node.path);
        if (target) {
          void loadPreview(target);
        }
      }
    },
    [allEntries, expandAncestors, loadPreview, selectedPath]
  );

  const renderTree = useCallback(
    (nodes: FileTreeNode[], level = 0): React.ReactNode =>
      nodes.map((node) => {
        if (node.type === 'directory') {
          const isExpanded = expandedFolders.has(node.treePath);
          return (
            <div key={`dir:${node.treePath}`}>
              <button
                type="button"
                onClick={() => toggleFolder(node.treePath)}
                className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-zinc-100 dark:hover:bg-zinc-800"
                style={{ paddingLeft: `${level * 16 + 8}px` }}
              >
                {isExpanded ? (
                  <ChevronDown className="h-3.5 w-3.5 text-zinc-500" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5 text-zinc-500" />
                )}
                {isExpanded ? (
                  <FolderOpen className="h-4 w-4 text-cyan-500" />
                ) : (
                  <Folder className="h-4 w-4 text-cyan-500" />
                )}
                <span className="truncate text-xs text-zinc-700 dark:text-zinc-200">
                  {node.name}
                </span>
              </button>
              {isExpanded && node.children && <div>{renderTree(node.children, level + 1)}</div>}
            </div>
          );
        }

        const isSelected = node.path === selectedPath;
        return (
          <button
            key={`file:${node.path}`}
            type="button"
            onClick={() => handleSelectNode(node)}
            className={`flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left transition-colors ${
              isSelected
                ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300'
                : 'text-zinc-700 hover:bg-zinc-100 dark:text-zinc-200 dark:hover:bg-zinc-800'
            }`}
            style={{ paddingLeft: `${level * 16 + 28}px` }}
          >
            <File className="h-3.5 w-3.5 shrink-0" />
            <span className="min-w-0 flex-1 truncate text-xs">{node.name}</span>
            {activeSection === 'all' && node.isOutput && (
              <Star className="h-3 w-3 shrink-0 text-amber-500" />
            )}
            {node.retentionClass && (
              <span className="shrink-0 rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] uppercase tracking-wide text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                {getRetentionLabel(node.retentionClass)}
              </span>
            )}
            <span className="shrink-0 rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] uppercase tracking-wide text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
              {node.scopeLabel}
            </span>
            <span className="shrink-0 text-[10px] text-zinc-400">
              {formatFileSize(node.size || 0)}
            </span>
          </button>
        );
      }),
    [activeSection, expandedFolders, handleSelectNode, selectedPath, toggleFolder]
  );

  if (!isOpen) return null;

  const fileCount = allEntries.length;
  const itemCount = files.length;
  const showMarkdownToggle = selectedFile ? isMarkdownFile(selectedFile.name) : false;
  const sectionHint =
    activeSection === 'output'
      ? t(
          'agent.workspaceOutputHint',
          'Focus on files under /output first. Switch to all files when you need the full workspace.'
        )
      : t(
          'agent.workspaceAllFilesHint',
          'Browse the full workspace, including output, input, and runtime directories.'
        );

  const panel = (
    <div
      className={
        displayMode === 'embedded'
          ? 'flex h-full min-h-0 w-full flex-col border-l border-zinc-200 bg-white/95 shadow-2xl backdrop-blur dark:border-zinc-700 dark:bg-zinc-950/95'
          : `fixed right-0 ${zIndexClassName} flex flex-col border-l border-zinc-200 bg-white/95 shadow-2xl backdrop-blur dark:border-zinc-700 dark:bg-zinc-950/95`
      }
      style={
        displayMode === 'embedded'
          ? undefined
          : {
              top: 'var(--app-header-height, 4rem)',
              height: 'calc(100vh - var(--app-header-height, 4rem))',
              width: 'min(88vw, 1240px)',
            }
      }
    >
      <div className="flex items-center justify-between border-b border-zinc-200 px-5 py-4 dark:border-zinc-700">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Folder className="h-4 w-4 text-emerald-500" />
            <h3 className="truncate text-sm font-semibold text-zinc-800 dark:text-zinc-100">
              {t('agent.workspace', 'Workspace')}
            </h3>
            <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] text-zinc-500 dark:bg-zinc-800 dark:text-zinc-300">
              {activeSection === 'output' ? outputEntries.length : allEntries.length}
            </span>
          </div>
          <p className="mt-1 text-[11px] text-zinc-500 dark:text-zinc-400">
            {t('agent.workspaceSummary', '{{fileCount}} files, {{itemCount}} items', {
              fileCount,
              itemCount,
            })}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={handleRefresh}
            className="rounded-lg p-2 text-zinc-600 transition-colors hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
            title={t('common.refresh', 'Refresh')}
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-zinc-600 transition-colors hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
            title={t('common.close', 'Close')}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="space-y-2 border-b border-zinc-200 px-5 py-3 dark:border-zinc-700">
        <div className="inline-flex items-center rounded-lg border border-zinc-200 bg-zinc-100/70 p-0.5 dark:border-zinc-700 dark:bg-zinc-800/70">
          <button
            type="button"
            onClick={() => setActiveSection('output')}
            className={`rounded-md px-3 py-1 text-xs transition-colors ${
              activeSection === 'output'
                ? 'bg-emerald-600 text-white'
                : 'text-zinc-600 hover:bg-zinc-200 dark:text-zinc-300 dark:hover:bg-zinc-700'
            }`}
          >
            {t('agent.workspaceOutputFiles', 'Output files')} ({outputEntries.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveSection('all')}
            className={`rounded-md px-3 py-1 text-xs transition-colors ${
              activeSection === 'all'
                ? 'bg-emerald-600 text-white'
                : 'text-zinc-600 hover:bg-zinc-200 dark:text-zinc-300 dark:hover:bg-zinc-700'
            }`}
          >
            {t('agent.workspaceAllFiles', 'All files')} ({allEntries.length})
          </button>
        </div>
        <p className="text-[11px] text-zinc-500 dark:text-zinc-400">{sectionHint}</p>
      </div>

      <div className="min-h-0 flex-1">
        {isLoading && files.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-zinc-500 dark:text-zinc-400">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            {t('common.loading', 'Loading...')}
          </div>
        ) : error ? (
          <div className="flex h-full items-center justify-center px-6 text-center text-sm text-red-600 dark:text-red-400">
            {error}
          </div>
        ) : fileTree.length === 0 ? (
          <div className="flex h-full items-center justify-center px-6 text-center text-sm text-zinc-500 dark:text-zinc-400">
            {activeSection === 'output'
              ? t('agent.workspaceNoOutputFiles', 'No output files yet.')
              : t('agent.workspaceNoFiles', 'No workspace files yet.')}
          </div>
        ) : (
          <div className="flex h-full min-h-0 overflow-hidden">
            <div className="w-[320px] shrink-0 overflow-y-auto border-r border-zinc-200 p-2 dark:border-zinc-700">
              {renderTree(fileTree)}
            </div>

            <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
              <div className="flex items-center justify-between gap-3 border-b border-zinc-200 px-5 py-3 dark:border-zinc-700">
                <div className="min-w-0">
                  <p className="truncate text-xs font-medium text-zinc-700 dark:text-zinc-200">
                    {selectedFile?.path ||
                      t('agent.workspaceSelectFile', 'Select a file to preview')}
                  </p>
                  {selectedFile && (
                    <p className="mt-0.5 text-[11px] text-zinc-400">
                      {formatFileSize(selectedFile.size || 0)}
                      {previewMime ? ` • ${previewMime}` : ''}
                    </p>
                  )}
                  {selectedFile && getRetentionHint(selectedFile.retentionClass) && (
                    <p className="mt-1 text-[11px] text-amber-500 dark:text-amber-300">
                      {getRetentionHint(selectedFile.retentionClass)}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {showMarkdownToggle && previewKind === 'text' && (
                    <div className="inline-flex items-center rounded-lg border border-zinc-200 bg-zinc-100/60 p-0.5 dark:border-zinc-700 dark:bg-zinc-800/70">
                      <button
                        type="button"
                        onClick={() => setMarkdownViewMode('preview')}
                        className={`rounded-md px-2.5 py-1 text-xs transition-colors ${
                          markdownViewMode === 'preview'
                            ? 'bg-emerald-600 text-white'
                            : 'text-zinc-600 hover:bg-zinc-200 dark:text-zinc-300 dark:hover:bg-zinc-700'
                        }`}
                      >
                        {t('agent.workspaceMarkdownPreview', 'Preview')}
                      </button>
                      <button
                        type="button"
                        onClick={() => setMarkdownViewMode('source')}
                        className={`rounded-md px-2.5 py-1 text-xs transition-colors ${
                          markdownViewMode === 'source'
                            ? 'bg-emerald-600 text-white'
                            : 'text-zinc-600 hover:bg-zinc-200 dark:text-zinc-300 dark:hover:bg-zinc-700'
                        }`}
                      >
                        {t('agent.workspaceMarkdownSource', 'Source')}
                      </button>
                    </div>
                  )}
                  {selectedFile && (
                    <button
                      type="button"
                      onClick={() => void handleDownload(selectedFile)}
                      disabled={isDownloading}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-emerald-600 disabled:opacity-60"
                    >
                      <Download className="h-3.5 w-3.5" />
                      {t('common.download', 'Download')}
                    </button>
                  )}
                </div>
              </div>

              <div
                className="min-h-0 flex-1 overflow-auto bg-zinc-950/95"
                onWheelCapture={(event) => event.stopPropagation()}
              >
                {(previewKind === 'loading' || isPreviewLoading) && (
                  <div className="flex h-full items-center justify-center text-sm text-zinc-300">
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    {t('agent.workspaceLoadingPreview', 'Loading preview...')}
                  </div>
                )}

                {previewKind === 'text' &&
                  (showMarkdownToggle && markdownViewMode === 'preview' ? (
                    <div className="p-6 text-sm leading-7 text-zinc-200">
                      {previewMessage && (
                        <p className="mb-4 text-[11px] text-amber-300">{previewMessage}</p>
                      )}
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          p: ({ children }) => <p className="mb-4">{children}</p>,
                          h1: ({ children }) => (
                            <h1 className="mb-4 mt-2 text-2xl font-bold text-zinc-100">{children}</h1>
                          ),
                          h2: ({ children }) => (
                            <h2 className="mb-3 mt-6 text-xl font-semibold text-zinc-100">{children}</h2>
                          ),
                          h3: ({ children }) => (
                            <h3 className="mb-2 mt-5 text-lg font-semibold text-zinc-100">{children}</h3>
                          ),
                          ul: ({ children }) => <ul className="mb-4 ml-5 list-disc">{children}</ul>,
                          ol: ({ children }) => <ol className="mb-4 ml-5 list-decimal">{children}</ol>,
                          li: ({ children }) => <li className="mb-1">{children}</li>,
                          code: ({ children, className }) => {
                            const isBlockCode = Boolean(className);
                            if (!isBlockCode) {
                              return (
                                <code className="rounded bg-zinc-800 px-1 py-0.5 text-zinc-100">
                                  {children}
                                </code>
                              );
                            }
                            return (
                              <pre className="my-3 overflow-x-auto rounded-lg bg-zinc-900 p-3 text-zinc-100">
                                <code className={className}>{children}</code>
                              </pre>
                            );
                          },
                          blockquote: ({ children }) => (
                            <blockquote className="my-4 border-l-4 border-zinc-600 pl-3 text-zinc-300">
                              {children}
                            </blockquote>
                          ),
                          a: ({ href, children }) => (
                            <a
                              href={href}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-cyan-300 underline hover:text-cyan-200"
                            >
                              {children}
                            </a>
                          ),
                        }}
                      >
                        {previewText}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    <div className="h-full">
                      {previewMessage && (
                        <div className="border-b border-zinc-800 px-4 py-2 text-[11px] text-amber-300">
                          {previewMessage}
                        </div>
                      )}
                      <FileCodePreview
                        filename={selectedFile?.name || 'file.txt'}
                        content={previewText}
                      />
                    </div>
                  ))}

                {previewKind === 'image' && previewUrl && (
                  <div className="flex h-full items-center justify-center p-4">
                    <img
                      src={previewUrl}
                      alt={selectedFile?.name || 'preview'}
                      className="max-h-full max-w-full object-contain"
                    />
                  </div>
                )}

                {previewKind === 'pdf' && previewUrl && (
                  <iframe
                    title={selectedFile?.name || 'pdf-preview'}
                    src={previewUrl}
                    className="h-full w-full border-0"
                  />
                )}

                {(previewKind === 'binary' || previewKind === 'unsupported') && (
                  <div className="flex h-full items-center justify-center p-6">
                    <div className="max-w-md text-center">
                      <FileText className="mx-auto mb-3 h-10 w-10 text-zinc-400" />
                      <p className="text-sm text-zinc-200">{previewMessage}</p>
                    </div>
                  </div>
                )}

                {previewKind === 'error' && (
                  <div className="flex h-full items-center justify-center p-6">
                    <div className="max-w-md text-center">
                      <p className="text-sm text-red-300">
                        {previewMessage ||
                          t('agent.workspacePreviewFailed', 'Failed to load file preview')}
                      </p>
                    </div>
                  </div>
                )}

                {previewKind === 'empty' && (
                  <div className="flex h-full items-center justify-center text-sm text-zinc-400">
                    {t('agent.workspaceSelectFile', 'Select a file to preview')}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );

  if (displayMode === 'embedded' || typeof document === 'undefined') {
    return panel;
  }

  return createPortal(panel, document.body);
};
