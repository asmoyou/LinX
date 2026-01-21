export type DocumentStatus = 'uploading' | 'processing' | 'completed' | 'failed';

export type DocumentType = 'pdf' | 'docx' | 'txt' | 'md' | 'image' | 'audio' | 'video';

export type Document = {
  id: string;
  name: string;
  type: DocumentType;
  size: number;
  status: DocumentStatus;
  uploadedAt: string;
  processedAt?: string;
  uploadProgress?: number;
  processingProgress?: number;
  owner: string;
  accessLevel: 'public' | 'internal' | 'confidential' | 'restricted';
  tags?: string[];
  description?: string;
  thumbnailUrl?: string;
  url?: string;
  error?: string;
};
