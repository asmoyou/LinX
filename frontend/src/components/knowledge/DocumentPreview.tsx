import React, { useState, useEffect, useRef } from 'react';
import { Loader2, Download } from 'lucide-react';
import { renderAsync } from 'docx-preview';
import { knowledgeApi } from '@/api/knowledge';
import type { Document } from '@/types/document';

interface DocumentPreviewProps {
  document: Document;
  onDownload?: (document: Document) => void;
}

const MAX_TEXT_SIZE = 50 * 1024; // 50KB
const DOCX_ZIP_MAGIC = [0x50, 0x4b, 0x03, 0x04];

const isDocxZipBuffer = (buffer: ArrayBuffer): boolean => {
  const bytes = new Uint8Array(buffer);
  if (bytes.length < DOCX_ZIP_MAGIC.length) {
    return false;
  }
  return DOCX_ZIP_MAGIC.every((magicByte, index) => bytes[index] === magicByte);
};

const mergeChunksToText = (
  chunks: Array<{ content?: string }>
): { text: string; truncated: boolean } => {
  const mergedText = (chunks || [])
    .map((chunk) => (chunk.content || '').trim())
    .filter(Boolean)
    .join('\n\n')
    .trim();

  if (!mergedText) {
    return { text: '', truncated: false };
  }

  if (mergedText.length > MAX_TEXT_SIZE) {
    return { text: mergedText.slice(0, MAX_TEXT_SIZE), truncated: true };
  }

  return { text: mergedText, truncated: false };
};

export const DocumentPreview: React.FC<DocumentPreviewProps> = ({ document, onDownload }) => {
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [textContent, setTextContent] = useState<string | null>(null);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [docxArrayBuffer, setDocxArrayBuffer] = useState<ArrayBuffer | null>(null);
  const [isTruncated, setIsTruncated] = useState(false);
  const blobUrlRef = useRef<string | null>(null);
  const docxContainerRef = useRef<HTMLDivElement | null>(null);

  const loadDocxTextFallback = React.useCallback(async () => {
    const chunkResp = await knowledgeApi.getChunks(document.id, 1, 20);
    return mergeChunksToText(chunkResp.chunks || []);
  }, [document.id]);

  useEffect(() => {
    let cancelled = false;

    const loadPreview = async () => {
      setIsLoading(true);
      setError(null);
      setTextContent(null);
      setBlobUrl(null);
      setDocxArrayBuffer(null);
      setIsTruncated(false);

      // DOCX preview: prefer full fidelity render; fallback to extracted text.
      if (document.type === 'docx') {
        if (document.status === 'processing' || document.status === 'uploading') {
          setError('Document is still being processed...');
          setIsLoading(false);
          return;
        }
        if (document.status === 'failed') {
          setError(document.errorMessage || document.error || 'Processing failed');
          setIsLoading(false);
          return;
        }

        try {
          if (document.fileReference && document.fileReference.startsWith('minio:')) {
            try {
              const { blob } = await knowledgeApi.download(document.id);
              if (cancelled) return;
              const buffer = await blob.arrayBuffer();
              if (cancelled) return;

              // Only DOCX (zip container) is rendered by docx-preview.
              if (isDocxZipBuffer(buffer)) {
                setDocxArrayBuffer(buffer);
                return;
              }
            } catch {
              // Ignore and fallback to chunk text.
            }
          }

          const { text, truncated } = await loadDocxTextFallback();
          if (cancelled) return;

          if (!text) {
            setError('No extracted text available for preview');
          } else {
            setTextContent(text);
            setIsTruncated(truncated);
          }
        } catch {
          if (!cancelled) {
            setError('Failed to load preview');
          }
        } finally {
          if (!cancelled) {
            setIsLoading(false);
          }
        }
        return;
      }

      // Guard: skip download when file is not available
      if (!document.fileReference || !document.fileReference.startsWith('minio:')) {
        if (document.status === 'processing' || document.status === 'uploading') {
          setError('Document is still being processed...');
        } else if (document.status === 'failed') {
          setError(document.errorMessage || document.error || 'Processing failed');
        } else {
          setError('File not available for preview');
        }
        setIsLoading(false);
        return;
      }

      try {
        const { blob } = await knowledgeApi.download(document.id);

        if (cancelled) return;

        const isTextType = ['txt', 'md'].includes(document.type);

        if (isTextType) {
          const text = await blob.text();
          if (cancelled) return;
          if (text.length > MAX_TEXT_SIZE) {
            setTextContent(text.slice(0, MAX_TEXT_SIZE));
            setIsTruncated(true);
          } else {
            setTextContent(text);
          }
        } else {
          const url = URL.createObjectURL(blob);
          if (cancelled) {
            URL.revokeObjectURL(url);
            return;
          }
          blobUrlRef.current = url;
          setBlobUrl(url);
        }
      } catch {
        if (!cancelled) {
          setError('Failed to load preview');
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    loadPreview();

    return () => {
      cancelled = true;
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current);
        blobUrlRef.current = null;
      }
    };
  }, [
    document.id,
    document.type,
    document.fileReference,
    document.status,
    document.error,
    document.errorMessage,
    loadDocxTextFallback,
  ]);

  useEffect(() => {
    if (document.type !== 'docx' || !docxArrayBuffer || !docxContainerRef.current) {
      return;
    }

    let cancelled = false;
    const container = docxContainerRef.current;

    const renderDocxPreview = async () => {
      container.innerHTML = '';

      try {
        await renderAsync(docxArrayBuffer, container);
      } catch {
        if (cancelled) return;

        setDocxArrayBuffer(null);
        try {
          const { text, truncated } = await loadDocxTextFallback();
          if (cancelled) return;

          if (!text) {
            setError('No extracted text available for preview');
          } else {
            setError(null);
            setTextContent(text);
            setIsTruncated(truncated);
          }
        } catch {
          if (!cancelled) {
            setError('Failed to render Word preview');
          }
        }
      }
    };

    void renderDocxPreview();

    return () => {
      cancelled = true;
      container.innerHTML = '';
    };
  }, [document.type, docxArrayBuffer, loadDocxTextFallback]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="w-8 h-8 text-indigo-500 animate-spin" />
        <span className="ml-3 text-gray-500 dark:text-gray-400">Loading preview...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] text-center">
        <p className="text-gray-600 dark:text-gray-400 mb-4">{error}</p>
        {onDownload && (
          <button
            onClick={() => onDownload(document)}
            className="px-4 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition-colors"
          >
            <Download className="w-4 h-4 inline mr-2" />
            Download to View
          </button>
        )}
      </div>
    );
  }

  // Markdown
  if (document.type === 'md' && textContent !== null) {
    return (
      <div className="min-h-[400px]">
        <div className="prose prose-sm dark:prose-invert max-w-none p-4 bg-white/5 rounded-lg overflow-auto max-h-[600px]">
          <pre className="whitespace-pre-wrap text-sm text-gray-800 dark:text-gray-200 font-mono">
            {textContent}
          </pre>
        </div>
        {isTruncated && (
          <div className="mt-3 text-center">
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">
              Content truncated (file too large for preview)
            </p>
            {onDownload && (
              <button
                onClick={() => onDownload(document)}
                className="text-sm text-indigo-500 hover:text-indigo-600"
              >
                Download full file
              </button>
            )}
          </div>
        )}
      </div>
    );
  }

  // Plain text
  if ((document.type === 'txt' || document.type === 'docx') && textContent !== null) {
    return (
      <div className="min-h-[400px]">
        <pre className="whitespace-pre-wrap text-sm text-gray-800 dark:text-gray-200 p-4 bg-white/5 rounded-lg overflow-auto max-h-[600px] font-mono">
          {textContent}
        </pre>
        {isTruncated && (
          <div className="mt-3 text-center">
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">
              Content truncated (file too large for preview)
            </p>
            {onDownload && (
              <button
                onClick={() => onDownload(document)}
                className="text-sm text-indigo-500 hover:text-indigo-600"
              >
                Download full file
              </button>
            )}
          </div>
        )}
      </div>
    );
  }

  // DOCX rich preview
  if (document.type === 'docx' && docxArrayBuffer) {
    return (
      <div className="min-h-[400px]">
        <div
          ref={docxContainerRef}
          className="w-full max-h-[700px] overflow-auto rounded-lg border border-gray-200 dark:border-gray-700 bg-white p-4 [&_.docx-wrapper]:bg-transparent [&_.docx]:mx-auto"
        />
      </div>
    );
  }

  // PDF
  if (document.type === 'pdf' && blobUrl) {
    return (
      <div className="min-h-[400px]">
        <iframe
          src={blobUrl}
          className="w-full h-[600px] rounded-lg border border-gray-200 dark:border-gray-700"
          title={document.name}
        />
      </div>
    );
  }

  // Image
  if (document.type === 'image' && blobUrl) {
    return (
      <div className="min-h-[400px] flex items-center justify-center">
        <img
          src={blobUrl}
          alt={document.name}
          className="max-w-full max-h-[600px] object-contain rounded-lg"
        />
      </div>
    );
  }

  // Audio
  if (document.type === 'audio' && blobUrl) {
    return (
      <div className="min-h-[200px] flex items-center justify-center">
        <audio controls src={blobUrl} className="w-full max-w-lg" />
      </div>
    );
  }

  // Video
  if (document.type === 'video' && blobUrl) {
    return (
      <div className="min-h-[400px] flex items-center justify-center">
        <video
          controls
          src={blobUrl}
          className="max-w-full max-h-[600px] rounded-lg"
        />
      </div>
    );
  }

  // Fallback (docx, etc.)
  return (
    <div className="flex flex-col items-center justify-center min-h-[400px] text-center">
      <p className="text-gray-600 dark:text-gray-400 mb-4">
        Preview not available for {document.type.toUpperCase()} files
      </p>
      {onDownload && (
        <button
          onClick={() => onDownload(document)}
          className="px-4 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition-colors"
        >
          <Download className="w-4 h-4 inline mr-2" />
          Download to View
        </button>
      )}
    </div>
  );
};
