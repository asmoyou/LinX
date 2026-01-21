import apiClient from './client';
import type { Document } from '../types/document';

export interface UploadDocumentRequest {
  file: File;
  description?: string;
  tags?: string[];
  access_level?: 'public' | 'internal' | 'confidential' | 'restricted';
}

export interface SearchKnowledgeRequest {
  query: string;
  limit?: number;
  filters?: {
    type?: string[];
    access_level?: string[];
    tags?: string[];
  };
}

export interface UpdateDocumentRequest {
  description?: string;
  tags?: string[];
  access_level?: 'public' | 'internal' | 'confidential' | 'restricted';
}

/**
 * Knowledge Base API
 */
export const knowledgeApi = {
  /**
   * Get all documents
   */
  getAll: async (): Promise<Document[]> => {
    const response = await apiClient.get<Document[]>('/knowledge');
    return response.data;
  },

  /**
   * Get document by ID
   */
  getById: async (documentId: string): Promise<Document> => {
    const response = await apiClient.get<Document>(`/knowledge/${documentId}`);
    return response.data;
  },

  /**
   * Upload document
   */
  upload: async (data: UploadDocumentRequest): Promise<Document> => {
    const formData = new FormData();
    formData.append('file', data.file);
    if (data.description) formData.append('description', data.description);
    if (data.tags) formData.append('tags', JSON.stringify(data.tags));
    if (data.access_level) formData.append('access_level', data.access_level);

    const response = await apiClient.post<Document>('/knowledge', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  /**
   * Upload multiple documents
   */
  uploadMultiple: async (files: File[]): Promise<Document[]> => {
    const formData = new FormData();
    files.forEach((file) => {
      formData.append('files', file);
    });

    const response = await apiClient.post<Document[]>('/knowledge/batch', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  /**
   * Update document metadata
   */
  update: async (documentId: string, data: UpdateDocumentRequest): Promise<Document> => {
    const response = await apiClient.put<Document>(`/knowledge/${documentId}`, data);
    return response.data;
  },

  /**
   * Delete document
   */
  delete: async (documentId: string): Promise<void> => {
    await apiClient.delete(`/knowledge/${documentId}`);
  },

  /**
   * Search knowledge base
   */
  search: async (data: SearchKnowledgeRequest): Promise<Document[]> => {
    const response = await apiClient.post<Document[]>('/knowledge/search', data);
    return response.data;
  },

  /**
   * Get document processing status
   */
  getProcessingStatus: async (documentId: string): Promise<any> => {
    const response = await apiClient.get(`/knowledge/${documentId}/status`);
    return response.data;
  },

  /**
   * Download document
   */
  download: async (documentId: string): Promise<Blob> => {
    const response = await apiClient.get(`/knowledge/${documentId}/download`, {
      responseType: 'blob',
    });
    return response.data;
  },

  /**
   * Get document preview
   */
  getPreview: async (documentId: string): Promise<string> => {
    const response = await apiClient.get<{ preview_url: string }>(
      `/knowledge/${documentId}/preview`
    );
    return response.data.preview_url;
  },
};
