import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Download, Eye, FileText, Folder, RefreshCw, X } from 'lucide-react';
import { agentsApi } from '@/api';
import type { AgentSessionWorkspaceFile } from '@/api/agents';

interface SessionWorkspacePanelProps {
  agentId: string;
  sessionId: string | null;
  isOpen: boolean;
  onClose: () => void;
}

type PreviewKind = 'empty' | 'loading' | 'text' | 'image' | 'pdf' | 'unsupported' | 'error';

const POLL_INTERVAL_MS = 8000;
const TEXT_PREVIEW_MAX_CHARS = 120000;
const TEXT_EXTENSIONS = new Set([
  '.txt',
  '.md',
  '.markdown',
  '.json',
  '.csv',
  '.yaml',
  '.yml',
  '.xml',
  '.html',
  '.htm',
  '.py',
  '.js',
  '.ts',
  '.tsx',
  '.jsx',
  '.css',
  '.scss',
  '.sql',
  '.log',
]);
const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg']);

function formatFileSize(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function getExtension(fileName: string): string {
  const dotIndex = fileName.lastIndexOf('.');
  if (dotIndex < 0) return '';
  return fileName.slice(dotIndex).toLowerCase();
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

export const SessionWorkspacePanel: React.FC<SessionWorkspacePanelProps> = ({
  agentId,
  sessionId,
  isOpen,
  onClose,
}) => {
  const [files, setFiles] = useState<AgentSessionWorkspaceFile[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [previewKind, setPreviewKind] = useState<PreviewKind>('empty');
  const [previewText, setPreviewText] = useState('');
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewMime, setPreviewMime] = useState('');
  const [previewMessage, setPreviewMessage] = useState('');
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);

  const previewUrlRef = useRef<string | null>(null);

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
  }, [cleanupPreviewUrl]);

  const loadFiles = useCallback(
    async (showLoading: boolean) => {
      if (!sessionId || !isOpen) return;
      if (showLoading) {
        setIsLoading(true);
      }
      try {
        const list = await agentsApi.getSessionWorkspaceFiles(agentId, sessionId, '', true);
        setFiles(list);
        setError(null);
      } catch (e) {
        const message = e instanceof Error ? e.message : 'Failed to load workspace files';
        setError(message);
      } finally {
        if (showLoading) {
          setIsLoading(false);
        }
      }
    },
    [agentId, isOpen, sessionId]
  );

  useEffect(() => {
    if (!isOpen || !sessionId) {
      setFiles([]);
      setSelectedPath(null);
      setError(null);
      resetPreview();
      return;
    }

    void loadFiles(true);
    const timer = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return;
      void loadFiles(false);
    }, POLL_INTERVAL_MS);

    return () => {
      window.clearInterval(timer);
    };
  }, [isOpen, loadFiles, resetPreview, sessionId]);

  useEffect(() => {
    return () => {
      cleanupPreviewUrl();
    };
  }, [cleanupPreviewUrl]);

  useEffect(() => {
    if (!files.length) {
      setSelectedPath(null);
      resetPreview();
      return;
    }

    const fileEntries = files.filter((file) => !file.is_dir);
    if (fileEntries.length === 0) {
      setSelectedPath(null);
      resetPreview();
      return;
    }

    if (!selectedPath || !fileEntries.some((file) => file.path === selectedPath)) {
      setSelectedPath(fileEntries[0].path);
    }
  }, [files, resetPreview, selectedPath]);

  const selectedFile = useMemo(
    () =>
      selectedPath
        ? files.find((item) => item.path === selectedPath && !item.is_dir) || null
        : null,
    [files, selectedPath]
  );

  const loadPreview = useCallback(
    async (file: AgentSessionWorkspaceFile) => {
      if (!sessionId) return;
      setIsPreviewLoading(true);
      setPreviewKind('loading');
      setPreviewText('');
      setPreviewMessage('');
      setPreviewMime('');
      cleanupPreviewUrl();

      try {
        const blob = await agentsApi.downloadSessionWorkspaceFile(agentId, sessionId, file.path);
        const mimeType = blob.type || 'application/octet-stream';
        const ext = getExtension(file.name);
        setPreviewMime(mimeType);

        if (TEXT_EXTENSIONS.has(ext) || file.previewable_inline) {
          const text = await blob.text();
          const truncated = text.length > TEXT_PREVIEW_MAX_CHARS;
          setPreviewText(truncated ? text.slice(0, TEXT_PREVIEW_MAX_CHARS) : text);
          setPreviewMessage(
            truncated
              ? `Preview truncated to ${TEXT_PREVIEW_MAX_CHARS.toLocaleString()} chars. Use download for full content.`
              : ''
          );
          setPreviewKind('text');
          return;
        }

        if (IMAGE_EXTENSIONS.has(ext)) {
          const objectUrl = window.URL.createObjectURL(blob);
          previewUrlRef.current = objectUrl;
          setPreviewUrl(objectUrl);
          setPreviewKind('image');
          return;
        }

        if (ext === '.pdf' || mimeType.includes('pdf')) {
          const objectUrl = window.URL.createObjectURL(blob);
          previewUrlRef.current = objectUrl;
          setPreviewUrl(objectUrl);
          setPreviewKind('pdf');
          return;
        }

        setPreviewKind('unsupported');
        setPreviewMessage('Preview is not supported for this file type. Use download.');
      } catch (e) {
        const message = e instanceof Error ? e.message : 'Failed to preview file';
        setPreviewKind('error');
        setPreviewMessage(message);
      } finally {
        setIsPreviewLoading(false);
      }
    },
    [agentId, cleanupPreviewUrl, sessionId]
  );

  useEffect(() => {
    if (!selectedFile) return;
    void loadPreview(selectedFile);
  }, [loadPreview, selectedFile]);

  const handleDownload = useCallback(
    async (file: AgentSessionWorkspaceFile) => {
      if (!sessionId) return;
      setIsDownloading(true);
      try {
        const blob = await agentsApi.downloadSessionWorkspaceFile(agentId, sessionId, file.path);
        downloadBlob(blob, file.name);
      } finally {
        setIsDownloading(false);
      }
    },
    [agentId, sessionId]
  );

  if (!isOpen) return null;

  return (
    <div className="w-[360px] border-l border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/40 flex flex-col min-h-0">
      <div className="px-3 py-2 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-zinc-800 dark:text-zinc-100">Workspace Files</h3>
          <p className="text-[11px] text-zinc-500 dark:text-zinc-400">
            {files.filter((item) => !item.is_dir).length} file(s), {files.length} item(s)
          </p>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => void loadFiles(true)}
            className="p-1.5 rounded-md hover:bg-zinc-200 dark:hover:bg-zinc-800 text-zinc-600 dark:text-zinc-300"
            title="Refresh files"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-md hover:bg-zinc-200 dark:hover:bg-zinc-800 text-zinc-600 dark:text-zinc-300"
            title="Close workspace panel"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="flex-1 min-h-0 flex flex-col">
        <div className="h-[42%] overflow-y-auto border-b border-zinc-200 dark:border-zinc-800">
          {error ? (
            <div className="p-3 text-xs text-red-600 dark:text-red-400">{error}</div>
          ) : files.length === 0 ? (
            <div className="p-3 text-xs text-zinc-500 dark:text-zinc-400">
              No files in workspace yet.
            </div>
          ) : (
            <div className="p-2 space-y-1">
              {files.map((file) => {
                const selected = !file.is_dir && file.path === selectedPath;
                const depth = Math.max(file.path.split('/').filter(Boolean).length - 1, 0);
                return (
                  <button
                    key={file.path}
                    type="button"
                    onClick={() => {
                      if (!file.is_dir) {
                        setSelectedPath(file.path);
                      }
                    }}
                    aria-disabled={file.is_dir}
                    className={`w-full text-left px-2 py-2 rounded-md border transition-colors ${
                      selected
                        ? 'border-emerald-300 bg-emerald-50 dark:border-emerald-700 dark:bg-emerald-900/20'
                        : file.is_dir
                          ? 'border-transparent bg-transparent'
                          : 'border-transparent hover:border-zinc-200 dark:hover:border-zinc-700 hover:bg-white/80 dark:hover:bg-zinc-800/80'
                    }`}
                    style={{ paddingLeft: `${8 + depth * 12}px` }}
                  >
                    <div className="flex items-start gap-2">
                      {file.is_dir ? (
                        <Folder className="w-4 h-4 mt-0.5 text-zinc-500 dark:text-zinc-400" />
                      ) : (
                        <FileText className="w-4 h-4 mt-0.5 text-zinc-500 dark:text-zinc-400" />
                      )}
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-medium text-zinc-800 dark:text-zinc-200 truncate">
                          {file.name}
                        </p>
                        <p className="text-[11px] text-zinc-500 dark:text-zinc-400 truncate">
                          {file.path}
                        </p>
                        {!file.is_dir && (
                          <p className="text-[11px] text-zinc-400 dark:text-zinc-500">
                            {formatFileSize(file.size)}
                          </p>
                        )}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div className="flex-1 min-h-0 flex flex-col">
          <div className="px-3 py-2 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between gap-2">
            <div className="min-w-0">
              <p className="text-xs font-medium text-zinc-700 dark:text-zinc-200 truncate">
                {selectedFile?.name || 'No file selected'}
              </p>
              {previewMime && (
                <p className="text-[11px] text-zinc-500 dark:text-zinc-400 truncate">{previewMime}</p>
              )}
            </div>
            {selectedFile && (
              <button
                type="button"
                onClick={() => void handleDownload(selectedFile)}
                disabled={isDownloading}
                className="inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-md bg-emerald-500 text-white hover:bg-emerald-600 disabled:opacity-60"
              >
                <Download className="w-3.5 h-3.5" />
                Download
              </button>
            )}
          </div>

          <div className="flex-1 min-h-0 overflow-auto p-3 bg-white dark:bg-zinc-900">
            {(previewKind === 'loading' || isPreviewLoading) && (
              <div className="h-full flex items-center justify-center text-xs text-zinc-500 dark:text-zinc-400">
                <Eye className="w-4 h-4 mr-1.5 animate-pulse" />
                Loading preview...
              </div>
            )}

            {previewKind === 'text' && (
              <div className="space-y-2">
                {previewMessage && (
                  <p className="text-[11px] text-amber-600 dark:text-amber-400">{previewMessage}</p>
                )}
                <pre className="text-[11px] leading-relaxed whitespace-pre-wrap break-words text-zinc-800 dark:text-zinc-200">
                  {previewText}
                </pre>
              </div>
            )}

            {previewKind === 'image' && previewUrl && (
              <div className="h-full flex items-center justify-center">
                <img src={previewUrl} alt={selectedFile?.name || 'preview'} className="max-w-full max-h-full object-contain" />
              </div>
            )}

            {previewKind === 'pdf' && previewUrl && (
              <iframe title={selectedFile?.name || 'pdf-preview'} src={previewUrl} className="w-full h-full border-0" />
            )}

            {previewKind === 'unsupported' && (
              <div className="h-full flex items-center justify-center text-xs text-zinc-500 dark:text-zinc-400 text-center">
                {previewMessage}
              </div>
            )}

            {previewKind === 'error' && (
              <div className="h-full flex items-center justify-center text-xs text-red-600 dark:text-red-400 text-center">
                {previewMessage || 'Failed to load preview.'}
              </div>
            )}

            {previewKind === 'empty' && (
              <div className="h-full flex items-center justify-center text-xs text-zinc-500 dark:text-zinc-400">
                Select a file to preview.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
