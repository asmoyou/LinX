import React, { useCallback, useEffect, useMemo, useState } from 'react';
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
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { missionsApi } from '@/api/missions';
import type { MissionDeliverable } from '@/types/mission';
import type { WorkspaceFile } from '@/api/missions';

interface DeliverablesPanelProps {
  missionId: string;
  isOpen: boolean;
  onClose: () => void;
}

type PreviewKind =
  | 'empty'
  | 'loading'
  | 'text'
  | 'markdown'
  | 'image'
  | 'pdf'
  | 'binary'
  | 'unsupported'
  | 'error';

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

function getLanguageFromExtension(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase();
  const languageMap: Record<string, string> = {
    py: 'python',
    js: 'javascript',
    ts: 'typescript',
    jsx: 'jsx',
    tsx: 'tsx',
    json: 'json',
    yaml: 'yaml',
    yml: 'yaml',
    md: 'markdown',
    txt: 'text',
    sh: 'bash',
    bash: 'bash',
    css: 'css',
    html: 'html',
    xml: 'xml',
    sql: 'sql',
  };
  return languageMap[ext || ''] || 'text';
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
  }, [previewUrl]);

  useEffect(() => {
    if (!isOpen) return;

    queueMicrotask(() => {
      setIsLoading(true);
      setLoadError(null);
      setExpandedFolders(new Set());
      setSelectedPath(null);
      resetPreview();
    });

    Promise.allSettled([
      missionsApi.getDeliverables(missionId),
      missionsApi.getWorkspaceFiles(missionId),
    ])
      .then(([deliverablesResult, workspaceResult]) => {
        if (deliverablesResult.status === 'fulfilled') {
          setDeliverables(Array.isArray(deliverablesResult.value) ? deliverablesResult.value : []);
        } else {
          setDeliverables([]);
        }

        if (workspaceResult.status === 'fulfilled') {
          const files = Array.isArray(workspaceResult.value) ? workspaceResult.value : [];
          setWorkspaceFiles(files.filter((file) => !file.is_dir));
        } else {
          setWorkspaceFiles([]);
        }

        if (
          deliverablesResult.status === 'rejected' &&
          workspaceResult.status === 'rejected'
        ) {
          setLoadError(t('missions.deliverablesLoadFailed'));
        }
      })
      .finally(() => setIsLoading(false));
  }, [isOpen, missionId, resetPreview, t]);

  const fileEntries = useMemo<FileEntry[]>(() => {
    if (deliverables.length > 0) {
      return deliverables.map((item) => ({
        path: normalizePath(item.filename || item.path),
        name: item.filename ? item.filename.split('/').pop() || item.filename : item.path,
        size: item.size,
        source: 'deliverable',
        isTarget: Boolean(item.is_target),
        deliverable: item,
      }));
    }

    return workspaceFiles.map((item) => {
      const normalized = normalizePath(item.path || item.name);
      return {
        path: normalized,
        name: normalized.split('/').pop() || item.name,
        size: item.size,
        source: 'workspace',
        isTarget: false,
      };
    });
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
      setExpandedFolders(new Set(folders));
    });
  }, [fileTree, isOpen, selectedNode, selectedPath]);

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
      if (node.source !== 'deliverable' || !node.deliverable) {
        setPreviewKind('unsupported');
        setPreviewMessage(
          t(
            'missions.workspacePreviewUnavailable',
            'Running workspace files do not support direct preview yet.'
          )
        );
        return;
      }

      setPreviewKind('loading');
      try {
        const blob = await missionsApi.downloadDeliverable(missionId, node.deliverable.path);
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
          if (ext === 'md' || ext === 'markdown') {
            setPreviewKind('markdown');
            return;
          }
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
    queueMicrotask(() => {
      void loadPreview(selectedNode);
    });
  }, [loadPreview, selectedNode]);

  const handleDownload = async (deliverable: MissionDeliverable) => {
    try {
      const blob = await missionsApi.downloadDeliverable(missionId, deliverable.path);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = deliverable.filename.split('/').pop() || deliverable.filename;
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
          onClick={() => setSelectedPath(node.path)}
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
                {selectedNode?.deliverable && (
                  <button
                    type="button"
                    onClick={() => handleDownload(selectedNode.deliverable!)}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 text-zinc-700 dark:text-zinc-200 transition-colors"
                  >
                    <Download className="w-3.5 h-3.5" />
                    {t('missions.download')}
                  </button>
                )}
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

                {previewKind === 'text' && (
                  <SyntaxHighlighter
                    language={getLanguageFromExtension(selectedNode?.name || '')}
                    style={vscDarkPlus}
                    customStyle={{
                      margin: 0,
                      padding: '1.5rem',
                      background: 'transparent',
                      fontSize: '0.875rem',
                      lineHeight: '1.5',
                    }}
                    showLineNumbers
                  >
                    {previewText}
                  </SyntaxHighlighter>
                )}

                {previewKind === 'markdown' && (
                  <div className="p-6 text-sm leading-7 text-zinc-200">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        code({ className, children, ...props }) {
                          const match = /language-(\w+)/.exec(className || '');
                          const language = match?.[1] || 'text';
                          const value = String(children).replace(/\n$/, '');
                          if (!className) {
                            return (
                              <code className="px-1 py-0.5 rounded bg-zinc-800 text-zinc-100" {...props}>
                                {children}
                              </code>
                            );
                          }
                          return (
                            <SyntaxHighlighter
                              language={language}
                              style={vscDarkPlus}
                              customStyle={{
                                margin: '0.75rem 0',
                                padding: '1rem',
                                borderRadius: '0.5rem',
                                background: '#0f172a',
                                fontSize: '0.8rem',
                                lineHeight: '1.5',
                              }}
                              showLineNumbers
                            >
                              {value}
                            </SyntaxHighlighter>
                          );
                        },
                        p({ children }) {
                          return <p className="mb-4 text-zinc-200">{children}</p>;
                        },
                        h1({ children }) {
                          return <h1 className="mb-4 mt-2 text-2xl font-bold text-zinc-100">{children}</h1>;
                        },
                        h2({ children }) {
                          return <h2 className="mb-3 mt-6 text-xl font-semibold text-zinc-100">{children}</h2>;
                        },
                        h3({ children }) {
                          return <h3 className="mb-2 mt-5 text-lg font-semibold text-zinc-100">{children}</h3>;
                        },
                        ul({ children }) {
                          return <ul className="mb-4 ml-5 list-disc">{children}</ul>;
                        },
                        ol({ children }) {
                          return <ol className="mb-4 ml-5 list-decimal">{children}</ol>;
                        },
                        li({ children }) {
                          return <li className="mb-1">{children}</li>;
                        },
                        blockquote({ children }) {
                          return (
                            <blockquote className="my-4 border-l-4 border-zinc-600 pl-3 text-zinc-300">
                              {children}
                            </blockquote>
                          );
                        },
                        a({ href, children }) {
                          return (
                            <a
                              href={href}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-cyan-300 hover:text-cyan-200 underline"
                            >
                              {children}
                            </a>
                          );
                        },
                      }}
                    >
                      {previewText}
                    </ReactMarkdown>
                  </div>
                )}

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
                      {selectedNode?.deliverable && (
                        <button
                          type="button"
                          onClick={() => handleDownload(selectedNode.deliverable!)}
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
