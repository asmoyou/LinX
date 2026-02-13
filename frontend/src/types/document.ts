export type DocumentStatus =
  | "uploading"
  | "processing"
  | "completed"
  | "failed";

export type DocumentType =
  | "pdf"
  | "docx"
  | "excel"
  | "txt"
  | "md"
  | "image"
  | "audio"
  | "video";

export type Document = {
  id: string;
  name: string;
  type: DocumentType;
  size: number;
  status: DocumentStatus;
  uploadedAt: string;
  processedAt?: string;
  processingStartedAt?: string;
  processingCompletedAt?: string;
  previousProcessedAt?: string;
  uploadProgress?: number;
  processingProgress?: number;
  owner: string;
  accessLevel: "public" | "internal" | "confidential" | "restricted";
  tags?: string[];
  description?: string;
  thumbnailUrl?: string;
  url?: string;
  error?: string;
  fileReference?: string;
  departmentId?: string;
  collectionId?: string;
  chunkCount?: number;
  tokenCount?: number;
  errorMessage?: string;
};

export type Collection = {
  id: string;
  name: string;
  description?: string;
  itemCount: number;
  owner: string;
  accessLevel: "public" | "internal" | "confidential" | "restricted";
  departmentId?: string;
  createdAt: string;
  updatedAt: string;
};
