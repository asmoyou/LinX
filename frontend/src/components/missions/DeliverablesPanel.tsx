import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { createPortal } from 'react-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  X,
  Download,
  Folder,
  FolderOpen,
  FileText,
  ChevronRight,
  ChevronDown,
  Loader2,
  File,
  Star,
} from 'lucide-react';
import { missionsApi } from '@/api/missions';
import type { MissionDeliverable } from '@/types/mission';
import type { WorkspaceFile } from '@/api/missions';
import { FileCodePreview } from '@/components/common/FileCodePreview';

interface DeliverablesPanelProps {
  missionId: string;
  isOpen: boolean;
  onClose: () => void;
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
const DELIVERABLES_POLL_INTERVAL_MS = 10_000;

interface FileEntry {
  path: string;
  name: string;
  size: number;
  source: 'deliverable' | 'workspace';
  isTarget: boolean;
  deliverable?: MissionDeliverable;
}

interface FileTreeNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  source: 'deliverable' | 'workspace';
  size?: number;
  isTarget?: boolean;
  deliverable?: MissionDeliverable;
  children?: FileTreeNode[];
}

const TEXT_EXTENSIONS = new Set([
  'txt',
  'md',
  'markdown',
  'json',
  'yaml',
  'yml',
  'toml',
  'ini',
  'py',
  'js',
  'ts',
  'tsx',
  'jsx',
  'css',
  'scss',
  'html',
  'xml',
  'sh',
  'bash',
  'sql',
  'log',
  'csv',
  'env',
  'conf',
  'config',
]);

const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg']);

function normalizePath(path: string): string {
  return path.replace(/^\/workspace\//, '').replace(/^\/+/, '');
}

function getExtension(filename: string): string {
  const ext = filename.split('.').pop();
  return ext ? ext.toLowerCase() : '';
}

function isMarkdownExtension(ext: string): boolean {
  return ext === 'md' || ext === 'markdown';
}

function buildDeliverablesSignature(items: MissionDeliverable[]): string {
  return items
    .map((item) => {
      const normalizedPath = normalizePath(item.filename || item.path);
      return `${normalizedPath}|${item.path}|${item.size}|${item.is_target ? 1 : 0}`;
    })
    .sort()
    .join('\n');
}

function buildWorkspaceFilesSignature(items: WorkspaceFile[]): string {
  return items
    .filter((item) => !item.is_dir)
    .map((item) => {
      const normalizedPath = normalizePath(item.path || item.name);
      return `${normalizedPath}|${item.size}|${item.is_dir ? 1 : 0}`;
    })
    .sort()
    .join('\n');
}

function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
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

function buildFileTree(entries: FileEntry[]): FileTreeNode[] {
  const root: FileTreeNode[] = [];

  const ensureDirectory = (container: FileTreeNode[], name: string, path: string): FileTreeNode => {
    const existing = container.find((node) => node.type === 'directory' && node.path === path);
    if (existing) return existing;
    const created: FileTreeNode = {
      name,
      path,
      type: 'directory',
      source: 'deliverable',
      children: [],
    };
    container.push(created);
    return created;
  };

  entries.forEach((entry) => {
    const parts = entry.path.split('/').filter(Boolean);
    if (parts.length === 0) return;

    let currentLevel = root;
    let currentPath = '';
    for (let i = 0; i < parts.length; i += 1) {
      const part = parts[i];
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      const isLeaf = i === parts.length - 1;

      if (isLeaf) {
        currentLevel.push({
          name: part,
          path: entry.path,
          type: 'file',
          source: entry.source,
          size: entry.size,
          isTarget: entry.isTarget,
          deliverable: entry.deliverable,
        });
      } else {
        const directory = ensureDirectory(currentLevel, part, currentPath);
        directory.source = entry.source;
        currentLevel = directory.children || [];
        directory.children = currentLevel;
      }
    }
  });

  return sortTree(root);
}

function findNodeByPath(nodes: FileTreeNode[], path: string): FileTreeNode | null {
  for (const node of nodes) {
    if (node.path === path) return node;
    if (node.type === 'directory' && node.children) {
      const found = findNodeByPath(node.children, path);
      if (found) return found;
    }
  }
  return null;
}

function findFirstFile(nodes: FileTreeNode[]): FileTreeNode | null {
  for (const node of nodes) {
    if (node.type === 'file') return node;
    if (node.children) {
      const found = findFirstFile(node.children);
      if (found) return found;
    }
  }
  return null;
}

export const DeliverablesPanel: React.FC<DeliverablesPanelProps> = ({
  missionId,
  isOpen,
  onClose,
}) => {
  const { t } = useTranslation();
  const [deliverables, setDeliverables] = useState<MissionDeliverable[]>([]);
  const [workspaceFiles, setWorkspaceFiles] = useState<WorkspaceFile[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [previewKind, setPreviewKind] = useState<PreviewKind>('empty');
  const [previewText, setPreviewText] = useState('');
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewMime, setPreviewMime] = useState('');
  const [previewMessage, setPreviewMessage] = useState('');
  const [markdownViewMode, setMarkdownViewMode] = useState<MarkdownViewMode>('source');
  const deliverablesSignatureRef = useRef('');
  const workspaceFilesSignatureRef = useRef('');
  const lastPreviewKeyRef = useRef('');

  useEffect(() => {
    return () => {
      if (previewUrl) {
        window.URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  const resetPreview = useCallback(() => {
    if (previewUrl) {
      window.URL.revokeObjectURL(previewUrl);
    }
    setPreviewUrl(null);
    setPreviewText('');
    setPreviewMime('');
    setPreviewMessage('');
    setPreviewKind('empty');
    setMarkdownViewMode('source');
  }, [previewUrl]);

  const loadPanelFiles = useCallback(
    async (showLoading: boolean) => {
      if (showLoading) {
        setIsLoading(true);
        setLoadError(null);
      }

      const [deliverablesResult, workspaceResult] = await Promise.allSettled([
        missionsApi.getDeliverables(missionId),
        missionsApi.getWorkspaceFiles(missionId, '', true),
      ]);

      if (deliverablesResult.status === 'fulfilled') {
        const nextDeliverables = Array.isArray(deliverablesResult.value)
          ? deliverablesResult.value
          : [];
        const nextSignature = buildDeliverablesSignature(nextDeliverables);
        if (nextSignature !== deliverablesSignatureRef.current) {
          deliverablesSignatureRef.current = nextSignature;
          setDeliverables(nextDeliverables);
        }
      } else if (showLoading) {
        deliverablesSignatureRef.current = '';
        setDeliverables([]);
      }

      if (workspaceResult.status === 'fulfilled') {
        const files = Array.isArray(workspaceResult.value) ? workspaceResult.value : [];
        const filteredFiles = files.filter((file) => !file.is_dir);
        const nextSignature = buildWorkspaceFilesSignature(filteredFiles);
        if (nextSignature !== workspaceFilesSignatureRef.current) {
          workspaceFilesSignatureRef.current = nextSignature;
          setWorkspaceFiles(filteredFiles);
        }
      } else if (showLoading) {
        workspaceFilesSignatureRef.current = '';
        setWorkspaceFiles([]);
      }

      if (
        deliverablesResult.status === 'rejected' &&
        workspaceResult.status === 'rejected'
      ) {
        setLoadError(t('missions.deliverablesLoadFailed'));
      } else {
        setLoadError(null);
      }

      if (showLoading) {
        setIsLoading(false);
      }
    },
    [missionId, t]
  );

  useEffect(() => {
    if (!isOpen) return;

    queueMicrotask(() => {
      deliverablesSignatureRef.current = '';
      workspaceFilesSignatureRef.current = '';
      lastPreviewKeyRef.current = '';
      setExpandedFolders(new Set());
      setSelectedPath(null);
      resetPreview();
    });

    const initialLoadTimer = window.setTimeout(() => {
      void loadPanelFiles(true);
    }, 0);
    const interval = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return;
      void loadPanelFiles(false);
    }, DELIVERABLES_POLL_INTERVAL_MS);

    return () => {
      window.clearTimeout(initialLoadTimer);
      window.clearInterval(interval);
    };
  }, [isOpen, loadPanelFiles, resetPreview]);

  const fileEntries = useMemo<FileEntry[]>(() => {
    const entryByPath = new Map<string, FileEntry>();

    workspaceFiles.forEach((item) => {
      const normalized = normalizePath(item.path || item.name);
      entryByPath.set(normalized, {
        path: normalized,
        name: normalized.split('/').pop() || item.name,
        size: item.size,
        source: 'workspace',
        isTarget: false,
      });
    });

    deliverables.forEach((item) => {
      const normalized = normalizePath(item.filename || item.path);
      const existing = entryByPath.get(normalized);
      if (existing) {
        entryByPath.set(normalized, {
          ...existing,
          isTarget: existing.isTarget || Boolean(item.is_target),
          deliverable: item,
        });
        return;
      }

      entryByPath.set(normalized, {
        path: normalized,
        name: item.filename ? item.filename.split('/').pop() || item.filename : item.path,
        size: item.size,
        source: 'deliverable',
        isTarget: Boolean(item.is_target),
        deliverable: item,
      });
    });

    return Array.from(entryByPath.values()).sort((a, b) => a.path.localeCompare(b.path));
  }, [deliverables, workspaceFiles]);

  const fileTree = useMemo(() => buildFileTree(fileEntries), [fileEntries]);
  const selectedNode = useMemo(
    () => (selectedPath ? findNodeByPath(fileTree, selectedPath) : null),
    [fileTree, selectedPath]
  );

  useEffect(() => {
    if (!isOpen || fileTree.length === 0) return;
    if (selectedPath && selectedNode?.type === 'file') return;

    const firstFile = findFirstFile(fileTree);
    if (!firstFile) return;

    const folders = firstFile.path
      .split('/')
      .slice(0, -1)
      .reduce<string[]>((acc, part, index) => {
        const parent = index === 0 ? part : `${acc[index - 1]}/${part}`;
        acc.push(parent);
        return acc;
      }, []);
    queueMicrotask(() => {
      setSelectedPath(firstFile.path);
      setMarkdownViewMode('source');
      setExpandedFolders(new Set(folders));
    });
  }, [fileTree, isOpen, selectedNode, selectedPath]);

  const handleSelectPath = useCallback((path: string) => {
    setSelectedPath(path);
    setMarkdownViewMode('source');
  }, []);

  const toggleFolder = (path: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  };

  const loadPreview = useCallback(
    async (node: FileTreeNode) => {
      resetPreview();
      setPreviewKind('loading');
      try {
        let blob: Blob;
        if (node.source === 'workspace') {
          blob = await missionsApi.downloadWorkspaceFile(missionId, node.path);
        } else if (node.deliverable) {
          blob = await missionsApi.downloadDeliverable(missionId, node.deliverable.path);
        } else {
          setPreviewKind('unsupported');
          setPreviewMessage(
            t('missions.deliverableUnavailable', 'The file is temporarily unavailable.')
          );
          return;
        }

        const ext = getExtension(node.name);
        const mime = blob.type || 'application/octet-stream';
        setPreviewMime(mime);

        if (IMAGE_EXTENSIONS.has(ext)) {
          const objectUrl = window.URL.createObjectURL(blob);
          setPreviewUrl(objectUrl);
          setPreviewKind('image');
          return;
        }

        if (ext === 'pdf' || mime === 'application/pdf') {
          const objectUrl = window.URL.createObjectURL(blob);
          setPreviewUrl(objectUrl);
          setPreviewKind('pdf');
          return;
        }

        if (TEXT_EXTENSIONS.has(ext) || mime.startsWith('text/') || mime.includes('json')) {
          let content = await blob.text();
          if (ext === 'json' || mime.includes('json')) {
            try {
              content = JSON.stringify(JSON.parse(content), null, 2);
            } catch {
              // Keep original text if parsing fails.
            }
          }
          setPreviewText(content);
          setPreviewKind('text');
          return;
        }

        setPreviewKind('binary');
        setPreviewMessage(
          t(
            'missions.binaryPreviewUnavailable',
            'Binary file preview is not supported. Please download the file.'
          )
        );
      } catch (error) {
        setPreviewKind('error');
        setPreviewMessage(
          error instanceof Error
            ? error.message
            : t('missions.deliverablesLoadFailed')
        );
      }
    },
    [missionId, resetPreview, t]
  );

  useEffect(() => {
    if (!selectedNode || selectedNode.type !== 'file') return;
    const previewKey = `${selectedNode.path}|${selectedNode.source}|${selectedNode.size || 0}|${
      selectedNode.deliverable?.path || ''
    }`;
    if (previewKey === lastPreviewKeyRef.current) return;
    lastPreviewKeyRef.current = previewKey;

    queueMicrotask(() => {
      void loadPreview(selectedNode);
    });
  }, [loadPreview, selectedNode]);

  const selectedExtension = selectedNode?.type === 'file' ? getExtension(selectedNode.name) : '';
  const isMarkdownSelected = isMarkdownExtension(selectedExtension);
  const showMarkdownToggle = previewKind === 'text' && isMarkdownSelected;

  const handleDownloadNode = async (node: FileTreeNode) => {
    if (node.type !== 'file') return;

    try {
      const blob =
        node.source === 'workspace'
          ? await missionsApi.downloadWorkspaceFile(missionId, node.path)
          : node.deliverable
            ? await missionsApi.downloadDeliverable(missionId, node.deliverable.path)
            : null;
      if (!blob) return;

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = node.name;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch {
      // error handled by api client toast
    }
  };

  const renderTree = (nodes: FileTreeNode[], level = 0): React.ReactNode =>
    nodes.map((node) => {
      if (node.type === 'directory') {
        const isExpanded = expandedFolders.has(node.path);
        return (
          <div key={node.path}>
            <button
              type="button"
              onClick={() => toggleFolder(node.path)}
              className="w-full flex items-center gap-1.5 py-1.5 px-2 text-left hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-md transition-colors"
              style={{ paddingLeft: `${level * 16 + 8}px` }}
            >
              {isExpanded ? (
                <ChevronDown className="w-3.5 h-3.5 text-zinc-500" />
              ) : (
                <ChevronRight className="w-3.5 h-3.5 text-zinc-500" />
              )}
              {isExpanded ? (
                <FolderOpen className="w-4 h-4 text-cyan-500" />
              ) : (
                <Folder className="w-4 h-4 text-cyan-500" />
              )}
              <span className="text-xs text-zinc-700 dark:text-zinc-200 truncate">
                {node.name}
              </span>
            </button>
            {isExpanded && node.children && <div>{renderTree(node.children, level + 1)}</div>}
          </div>
        );
      }

      const isSelected = selectedPath === node.path;
      return (
        <button
          key={node.path}
          type="button"
          onClick={() => handleSelectPath(node.path)}
          className={`w-full flex items-center gap-1.5 py-1.5 px-2 text-left rounded-md transition-colors ${
            isSelected
              ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300'
              : 'hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-700 dark:text-zinc-200'
          }`}
          style={{ paddingLeft: `${level * 16 + 28}px` }}
        >
          <File className="w-3.5 h-3.5 flex-shrink-0" />
          <span className="text-xs truncate flex-1">{node.name}</span>
          {node.isTarget && (
            <Star className="w-3 h-3 text-amber-500 flex-shrink-0" />
          )}
          <span className="text-[10px] text-zinc-400 flex-shrink-0">
            {formatFileSize(node.size || 0)}
          </span>
        </button>
      );
    });

  if (!isOpen) return null;

  const panel = (
    <div
      className="fixed right-0 z-[60] glass-panel border-l border-zinc-200 dark:border-zinc-700 pointer-events-auto flex flex-col animate-in slide-in-from-right duration-300 shadow-2xl"
      style={{
        top: 'var(--app-header-height, 4rem)',
        height: 'calc(100vh - var(--app-header-height, 4rem))',
        width: 'min(75vw, 960px)',
      }}
    >
      <div className="flex items-center justify-between p-4 border-b border-zinc-200 dark:border-zinc-700">
        <div className="flex items-center gap-2 min-w-0">
          <Folder className="w-4 h-4 text-emerald-500" />
          <h3 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200 truncate">
            {t('missions.deliverables')}
          </h3>
          <span className="text-xs text-zinc-400">({fileEntries.length})</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-1 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors"
        >
          <X className="w-4 h-4 text-zinc-500" />
        </button>
      </div>

      <div className="flex-1 min-h-0">
        {isLoading ? (
          <div className="flex items-center justify-center h-full text-zinc-400 text-sm">
            <Loader2 className="w-4 h-4 animate-spin mr-2" />
            {t('missions.loading')}
          </div>
        ) : loadError ? (
          <div className="flex items-center justify-center h-full text-sm text-red-500 px-4 text-center">
            {loadError}
          </div>
        ) : fileTree.length === 0 ? (
          <div className="flex items-center justify-center h-full text-zinc-400 text-sm px-4 text-center">
            {t('missions.noDeliverablesYet')}
          </div>
        ) : (
          <div className="h-full min-h-0 flex overflow-hidden">
            <div className="w-[300px] shrink-0 border-r border-zinc-200 dark:border-zinc-700 overflow-y-auto p-2 custom-scrollbar">
              {renderTree(fileTree)}
            </div>

            <div className="flex-1 min-w-0 min-h-0 overflow-hidden flex flex-col">
              <div className="shrink-0 px-4 py-3 border-b border-zinc-200 dark:border-zinc-700 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-xs font-medium text-zinc-700 dark:text-zinc-200 truncate">
                    {selectedNode?.path || t('missions.selectFileToView', 'Select a file to preview')}
                  </p>
                  {selectedNode?.type === 'file' && (
                    <p className="text-[11px] text-zinc-400 mt-0.5">
                      {formatFileSize(selectedNode.size || 0)}
                      {previewMime ? ` • ${previewMime}` : ''}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {showMarkdownToggle && (
                    <div className="inline-flex items-center rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-100/60 dark:bg-zinc-800/70 p-0.5">
                      <button
                        type="button"
                        onClick={() => setMarkdownViewMode('source')}
                        className={`px-2.5 py-1 text-xs rounded-md transition-colors ${
                          markdownViewMode === 'source'
                            ? 'bg-emerald-600 text-white'
                            : 'text-zinc-600 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700'
                        }`}
                      >
                        {t('missions.markdownSource', 'Source')}
                      </button>
                      <button
                        type="button"
                        onClick={() => setMarkdownViewMode('preview')}
                        className={`px-2.5 py-1 text-xs rounded-md transition-colors ${
                          markdownViewMode === 'preview'
                            ? 'bg-emerald-600 text-white'
                            : 'text-zinc-600 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700'
                        }`}
                      >
                        {t('missions.markdownPreview', 'Preview')}
                      </button>
                    </div>
                  )}
                  {selectedNode?.type === 'file' && (
                    <button
                      type="button"
                      onClick={() => handleDownloadNode(selectedNode)}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 text-zinc-700 dark:text-zinc-200 transition-colors"
                    >
                      <Download className="w-3.5 h-3.5" />
                      {t('missions.download')}
                    </button>
                  )}
                </div>
              </div>

              <div
                className="flex-1 min-h-0 overflow-auto bg-zinc-950/95 custom-scrollbar"
                onWheelCapture={(event) => event.stopPropagation()}
              >
                {previewKind === 'loading' && (
                  <div className="h-full flex items-center justify-center text-zinc-300 text-sm">
                    <Loader2 className="w-4 h-4 animate-spin mr-2" />
                    {t('missions.loading')}
                  </div>
                )}

                {previewKind === 'text' &&
                  (isMarkdownSelected && markdownViewMode === 'preview' ? (
                    <div className="p-6 text-sm leading-7 text-zinc-200">
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
                                <code className="px-1 py-0.5 rounded bg-zinc-800 text-zinc-100">
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
                              className="text-cyan-300 hover:text-cyan-200 underline"
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
                    <FileCodePreview
                      filename={selectedNode?.name || 'file.txt'}
                      content={previewText}
                    />
                  ))}

                {previewKind === 'image' && previewUrl && (
                  <div className="h-full flex items-center justify-center p-4">
                    <img src={previewUrl} alt={selectedNode?.name || 'preview'} className="max-h-full max-w-full object-contain" />
                  </div>
                )}

                {previewKind === 'pdf' && previewUrl && (
                  <iframe title={selectedNode?.name || 'pdf-preview'} src={previewUrl} className="w-full h-full border-0" />
                )}

                {(previewKind === 'binary' || previewKind === 'unsupported') && (
                  <div className="h-full flex items-center justify-center p-6">
                    <div className="text-center max-w-md">
                      <FileText className="w-10 h-10 text-zinc-400 mx-auto mb-3" />
                      <p className="text-sm text-zinc-200 mb-2">
                        {previewMessage}
                      </p>
                      {selectedNode?.type === 'file' && (
                        <button
                          type="button"
                          onClick={() => handleDownloadNode(selectedNode)}
                          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-xs bg-emerald-600 hover:bg-emerald-700 text-white transition-colors"
                        >
                          <Download className="w-3.5 h-3.5" />
                          {t('missions.download')}
                        </button>
                      )}
                    </div>
                  </div>
                )}

                {previewKind === 'error' && (
                  <div className="h-full flex items-center justify-center p-6">
                    <div className="text-center max-w-md">
                      <p className="text-sm text-red-300">{previewMessage}</p>
                    </div>
                  </div>
                )}

                {previewKind === 'empty' && (
                  <div className="h-full flex items-center justify-center text-zinc-400 text-sm">
                    {t('missions.selectFileToView', 'Select a file to preview')}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );

  if (typeof document === 'undefined') {
    return panel;
  }
  return createPortal(panel, document.body);
};
