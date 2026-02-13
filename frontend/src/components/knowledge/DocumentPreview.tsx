import React, { useState, useEffect, useRef } from "react";
import { Loader2, Download } from "lucide-react";
import { renderAsync } from "docx-preview";
import { AgGridReact } from "ag-grid-react";
import { ModuleRegistry, AllCommunityModule, type ColDef } from "ag-grid-community";
import * as XLSX from "xlsx";
import { knowledgeApi } from "@/api/knowledge";
import type { Document } from "@/types/document";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-quartz.css";

ModuleRegistry.registerModules([AllCommunityModule]);

interface DocumentPreviewProps {
  document: Document;
  onDownload?: (document: Document) => void;
}

const MAX_TEXT_SIZE = 50 * 1024; // 50KB
const EXCEL_MAX_PREVIEW_ROWS = 200;
const EXCEL_MAX_PREVIEW_COLS = 40;
const DOCX_ZIP_MAGIC = [0x50, 0x4b, 0x03, 0x04];

interface ExcelSheetPreview {
  name: string;
  columns: Array<{
    field: string;
    headerName: string;
  }>;
  rows: Array<Record<string, string | number>>;
  dataRowCount: number;
  colCount: number;
  truncatedRows: boolean;
  truncatedCols: boolean;
}

const isDocxZipBuffer = (buffer: ArrayBuffer): boolean => {
  const bytes = new Uint8Array(buffer);
  if (bytes.length < DOCX_ZIP_MAGIC.length) {
    return false;
  }
  return DOCX_ZIP_MAGIC.every((magicByte, index) => bytes[index] === magicByte);
};

const mergeChunksToText = (
  chunks: Array<{ content?: string }>,
): { text: string; truncated: boolean } => {
  const mergedText = (chunks || [])
    .map((chunk) => (chunk.content || "").trim())
    .filter(Boolean)
    .join("\n\n")
    .trim();

  if (!mergedText) {
    return { text: "", truncated: false };
  }

  if (mergedText.length > MAX_TEXT_SIZE) {
    return { text: mergedText.slice(0, MAX_TEXT_SIZE), truncated: true };
  }

  return { text: mergedText, truncated: false };
};

const buildExcelSheetPreview = (
  name: string,
  rawRows: unknown[][],
): ExcelSheetPreview => {
  const rows = rawRows.map((row) =>
    Array.isArray(row) ? row.map((cell) => String(cell ?? "").trim()) : [],
  );
  const [headerRow = [], ...dataRows] = rows;
  const dataRowCount = dataRows.length;
  const colCount = rawRows.reduce((max, row) => Math.max(max, row.length), 0);
  const visibleColCount = Math.max(Math.min(colCount, EXCEL_MAX_PREVIEW_COLS), 1);
  const truncatedRows = dataRowCount > EXCEL_MAX_PREVIEW_ROWS;
  const truncatedCols = colCount > EXCEL_MAX_PREVIEW_COLS;

  const columns = Array.from({ length: visibleColCount }, (_, idx) => ({
    field: `c${idx + 1}`,
    headerName: (headerRow[idx] || `C${idx + 1}`).trim(),
  }));

  const previewRows = dataRows.slice(0, EXCEL_MAX_PREVIEW_ROWS).map((row, rowIdx) => {
    const rowData: Record<string, string | number> = { __row: rowIdx + 1 };
    columns.forEach((column, colIdx) => {
      rowData[column.field] = row[colIdx] || "";
    });
    return rowData;
  });

  return {
    name,
    columns,
    rows: previewRows,
    dataRowCount,
    colCount,
    truncatedRows,
    truncatedCols,
  };
};

const parseExcelPreviewFromWorkbook = (buffer: ArrayBuffer): ExcelSheetPreview[] => {
  const workbook = XLSX.read(buffer, {
    type: "array",
    dense: true,
    cellText: true,
  });

  return workbook.SheetNames.map((sheetName) => {
    const worksheet = workbook.Sheets[sheetName];
    if (!worksheet) {
      return buildExcelSheetPreview(sheetName, []);
    }

    const rows = XLSX.utils.sheet_to_json(worksheet, {
      header: 1,
      raw: false,
      defval: "",
      blankrows: false,
    }) as unknown[][];

    return buildExcelSheetPreview(sheetName, rows);
  });
};

const parseExcelPreviewFromExtractedText = (text: string): ExcelSheetPreview[] => {
  const normalized = (text || "").replace(/\r\n/g, "\n").trim();
  if (!normalized) return [];

  const sheetHeaderRegex = /\[Sheet:\s*(.+?)\]\s*\n/g;
  const headers = Array.from(normalized.matchAll(sheetHeaderRegex));

  const parseRows = (body: string): string[][] =>
    body
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => line.split("\t").map((cell) => cell.trim()));

  if (!headers.length) {
    return [buildExcelSheetPreview("Sheet 1", parseRows(normalized))];
  }

  const sheets: ExcelSheetPreview[] = [];
  for (let i = 0; i < headers.length; i += 1) {
    const current = headers[i];
    const next = headers[i + 1];
    const start = (current.index ?? 0) + current[0].length;
    const end = next?.index ?? normalized.length;
    const name = (current[1] || `Sheet ${i + 1}`).trim();
    const body = normalized.slice(start, end).trim();
    sheets.push(buildExcelSheetPreview(name, parseRows(body)));
  }

  return sheets;
};

export const DocumentPreview: React.FC<DocumentPreviewProps> = ({
  document,
  onDownload,
}) => {
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [textContent, setTextContent] = useState<string | null>(null);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [docxArrayBuffer, setDocxArrayBuffer] = useState<ArrayBuffer | null>(
    null,
  );
  const [excelSheets, setExcelSheets] = useState<ExcelSheetPreview[] | null>(
    null,
  );
  const [activeExcelSheet, setActiveExcelSheet] = useState(0);
  const [isTruncated, setIsTruncated] = useState(false);
  const blobUrlRef = useRef<string | null>(null);
  const docxContainerRef = useRef<HTMLDivElement | null>(null);

  const loadChunkTextFallback = React.useCallback(
    async (pageSize: number = 20) => {
      const chunkResp = await knowledgeApi.getChunks(document.id, 1, pageSize);
      return mergeChunksToText(chunkResp.chunks || []);
    },
    [document.id],
  );

  useEffect(() => {
    let cancelled = false;

    const loadPreview = async () => {
      setIsLoading(true);
      setError(null);
      setTextContent(null);
      setBlobUrl(null);
      setDocxArrayBuffer(null);
      setExcelSheets(null);
      setActiveExcelSheet(0);
      setIsTruncated(false);

      // Excel preview: use SheetJS for workbook parsing, fallback to extracted chunk text.
      if (document.type === "excel") {
        if (
          document.status === "processing" ||
          document.status === "uploading"
        ) {
          setError("Document is still being processed...");
          setIsLoading(false);
          return;
        }
        if (document.status === "failed") {
          setError(
            document.errorMessage || document.error || "Processing failed",
          );
          setIsLoading(false);
          return;
        }

        try {
          if (
            document.fileReference &&
            document.fileReference.startsWith("minio:")
          ) {
            try {
              const { blob } = await knowledgeApi.download(document.id);
              if (cancelled) return;

              const buffer = await blob.arrayBuffer();
              if (cancelled) return;

              const workbookSheets = parseExcelPreviewFromWorkbook(buffer);
              if (workbookSheets.length > 0) {
                setExcelSheets(workbookSheets);
                setIsTruncated(
                  workbookSheets.some(
                    (sheet) => sheet.truncatedRows || sheet.truncatedCols,
                  ),
                );
                setIsLoading(false);
                return;
              }
            } catch {
              // Ignore parse/download failures and fallback to extracted text.
            }
          }

          const { text, truncated } = await loadChunkTextFallback(50);
          if (cancelled) return;

          if (!text) {
            setError("No extracted worksheet content available for preview");
          } else {
            const sheets = parseExcelPreviewFromExtractedText(text);
            if (sheets.length > 0) {
              setExcelSheets(sheets);
              setIsTruncated(
                truncated ||
                  sheets.some(
                    (sheet) => sheet.truncatedRows || sheet.truncatedCols,
                  ),
              );
            } else {
              setTextContent(text);
              setIsTruncated(truncated);
            }
          }
        } catch {
          if (!cancelled) {
            setError("Failed to load preview");
          }
        } finally {
          if (!cancelled) {
            setIsLoading(false);
          }
        }
        return;
      }

      // DOCX preview: prefer full fidelity render; fallback to extracted text.
      if (document.type === "docx") {
        if (
          document.status === "processing" ||
          document.status === "uploading"
        ) {
          setError("Document is still being processed...");
          setIsLoading(false);
          return;
        }
        if (document.status === "failed") {
          setError(
            document.errorMessage || document.error || "Processing failed",
          );
          setIsLoading(false);
          return;
        }

        try {
          if (
            document.fileReference &&
            document.fileReference.startsWith("minio:")
          ) {
            try {
              const { blob } = await knowledgeApi.download(document.id, {
                convert_to: "docx",
              });
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

          const { text, truncated } = await loadChunkTextFallback();
          if (cancelled) return;

          if (!text) {
            setError("No extracted text available for preview");
          } else {
            setTextContent(text);
            setIsTruncated(truncated);
          }
        } catch {
          if (!cancelled) {
            setError("Failed to load preview");
          }
        } finally {
          if (!cancelled) {
            setIsLoading(false);
          }
        }
        return;
      }

      // Guard: skip download when file is not available
      if (
        !document.fileReference ||
        !document.fileReference.startsWith("minio:")
      ) {
        if (
          document.status === "processing" ||
          document.status === "uploading"
        ) {
          setError("Document is still being processed...");
        } else if (document.status === "failed") {
          setError(
            document.errorMessage || document.error || "Processing failed",
          );
        } else {
          setError("File not available for preview");
        }
        setIsLoading(false);
        return;
      }

      try {
        const { blob } = await knowledgeApi.download(document.id);

        if (cancelled) return;

        const isTextType = ["txt", "md"].includes(document.type);

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
          setError("Failed to load preview");
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
    loadChunkTextFallback,
  ]);

  useEffect(() => {
    if (
      document.type !== "docx" ||
      !docxArrayBuffer ||
      !docxContainerRef.current
    ) {
      return;
    }

    let cancelled = false;
    const container = docxContainerRef.current;

    const renderDocxPreview = async () => {
      container.innerHTML = "";

      try {
        await renderAsync(docxArrayBuffer, container);
      } catch {
        if (cancelled) return;

        setDocxArrayBuffer(null);
        try {
          const { text, truncated } = await loadChunkTextFallback();
          if (cancelled) return;

          if (!text) {
            setError("No extracted text available for preview");
          } else {
            setError(null);
            setTextContent(text);
            setIsTruncated(truncated);
          }
        } catch {
          if (!cancelled) {
            setError("Failed to render Word preview");
          }
        }
      }
    };

    void renderDocxPreview();

    return () => {
      cancelled = true;
      container.innerHTML = "";
    };
  }, [document.type, docxArrayBuffer, loadChunkTextFallback]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="w-8 h-8 text-indigo-500 animate-spin" />
        <span className="ml-3 text-gray-500 dark:text-gray-400">
          Loading preview...
        </span>
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
  if (document.type === "md" && textContent !== null) {
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
  if (
    (document.type === "txt" || document.type === "docx") &&
    textContent !== null
  ) {
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

  // Excel preview (SheetJS + AG Grid)
  if (document.type === "excel" && excelSheets && excelSheets.length > 0) {
    const activeSheet =
      excelSheets[Math.min(activeExcelSheet, excelSheets.length - 1)];
    const columnDefs: ColDef[] = [
      {
        field: "__row",
        headerName: "#",
        pinned: "left",
        width: 72,
        maxWidth: 90,
        sortable: false,
        filter: false,
        suppressMovable: true,
      },
      ...activeSheet.columns.map((column) => ({
        field: column.field,
        headerName: column.headerName,
      })),
    ];

    return (
      <div className="min-h-[400px] space-y-3">
        <div className="flex flex-wrap gap-2">
          {excelSheets.map((sheet, idx) => (
            <button
              key={`${sheet.name}-${idx}`}
              onClick={() => setActiveExcelSheet(idx)}
              className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
                idx === activeExcelSheet
                  ? "bg-emerald-500 text-white border-emerald-500"
                  : "bg-white/5 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:bg-white/10"
              }`}
            >
              {sheet.name}
            </button>
          ))}
        </div>

        <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white/5 p-2">
          <div className="ag-theme-quartz w-full h-[640px]">
            <AgGridReact
              rowData={activeSheet.rows}
              columnDefs={columnDefs}
              defaultColDef={{
                resizable: true,
                sortable: true,
                filter: true,
                minWidth: 120,
              }}
              animateRows
              pagination={activeSheet.dataRowCount > 50}
              paginationPageSize={50}
              suppressCellFocus
            />
          </div>
        </div>

        {(isTruncated || activeSheet.truncatedRows || activeSheet.truncatedCols) && (
          <div className="text-sm text-gray-500 dark:text-gray-400">
            Preview is truncated for performance.
            {activeSheet.truncatedRows && ` Rows: showing first ${EXCEL_MAX_PREVIEW_ROWS}.`}
            {activeSheet.truncatedCols && ` Columns: showing first ${EXCEL_MAX_PREVIEW_COLS}.`}
          </div>
        )}
      </div>
    );
  }

  // Excel plain-text fallback
  if (document.type === "excel" && textContent !== null) {
    return (
      <div className="min-h-[400px]">
        <pre className="whitespace-pre-wrap text-sm text-gray-800 dark:text-gray-200 p-4 bg-white/5 rounded-lg overflow-auto max-h-[650px] font-mono">
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
  if (document.type === "docx" && docxArrayBuffer) {
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
  if (document.type === "pdf" && blobUrl) {
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
  if (document.type === "image" && blobUrl) {
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
  if (document.type === "audio" && blobUrl) {
    return (
      <div className="min-h-[200px] flex items-center justify-center">
        <audio controls src={blobUrl} className="w-full max-w-lg" />
      </div>
    );
  }

  // Video
  if (document.type === "video" && blobUrl) {
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
