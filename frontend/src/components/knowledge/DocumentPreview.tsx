import React, { useState, useEffect, useRef } from 'react';
import { Loader2, Download } from 'lucide-react';
import { knowledgeApi } from '@/api/knowledge';
import type { Document } from '@/types/document';

interface DocumentPreviewProps {
  document: Document;
  onDownload?: (document: Document) => void;
}

const MAX_TEXT_SIZE = 50 * 1024; // 50KB

export const DocumentPreview: React.FC<DocumentPreviewProps> = ({ document, onDownload }) => {
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [textContent, setTextContent] = useState<string | null>(null);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [isTruncated, setIsTruncated] = useState(false);
  const blobUrlRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const loadPreview = async () => {
      setIsLoading(true);
      setError(null);
      setTextContent(null);
      setBlobUrl(null);
      setIsTruncated(false);

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
        const blob = await knowledgeApi.download(document.id);

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
  }, [document.id, document.type, document.fileReference, document.status]);

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
  if (document.type === 'txt' && textContent !== null) {
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
