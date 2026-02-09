import apiClient from './client';
import type { Document } from '../types/document';

export interface KnowledgeListResponse {
  items: Document[];
  total: number;
  page: number;
  pageSize: number;
}

export interface UploadDocumentRequest {
  file: File;
  title?: string;
  description?: string;
  tags?: string[];
  access_level?: string;
  department_id?: string;
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

export interface SearchKnowledgeResponse {
  results: Array<{
    document_id: string;
    document_title?: string;
    content: string;
    similarity_score: number;
    chunk_index: number;
    keywords?: string[];
    summary?: string;
    search_method?: string;
  }>;
  query: string;
  total: number;
}

export interface KnowledgeChunk {
  chunk_id: string;
  chunk_index: number;
  content: string;
  keywords?: string[];
  questions?: string[];
  summary?: string;
  token_count?: number;
}

export interface KnowledgeChunksResponse {
  chunks: KnowledgeChunk[];
  total: number;
}

export interface UpdateDocumentRequest {
  title?: string;
  description?: string;
  tags?: string[];
  access_level?: string;
  department_id?: string;
}

export interface ProcessingStatusResponse {
  job_id?: string;
  status: string;
  error_message?: string;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
  chunk_count?: number;
  token_count?: number;
  processed_at?: string;
}

export interface KBConfigResponse {
  chunking: {
    strategy?: string;
    chunk_token_num?: number;
    overlap_percent?: number;
    delimiters?: string;
  };
  parsing: {
    method?: string;
    vision_model?: string;
    vision_provider?: string;
  };
  enrichment: {
    enabled?: boolean;
    provider?: string;
    model?: string;
    keywords_topn?: number;
    questions_topn?: number;
    generate_summary?: boolean;
    temperature?: number;
    batch_size?: number;
  };
  embedding: {
    provider?: string;
    model?: string;
    dimension?: number;
  };
  search: {
    enable_semantic?: boolean;
    enable_fulltext?: boolean;
    combine_results?: boolean;
    semantic_weight?: number;
    fulltext_weight?: number;
    fusion_method?: string;
    rrf_k?: number;
    rerank_enabled?: boolean;
    rerank_provider?: string;
    rerank_model?: string;
    rerank_top_k?: number;
  };
}

export interface KBConfigUpdateRequest {
  chunking?: Partial<KBConfigResponse['chunking']>;
  parsing?: Partial<KBConfigResponse['parsing']>;
  enrichment?: Partial<KBConfigResponse['enrichment']>;
  embedding?: Partial<KBConfigResponse['embedding']>;
  search?: Partial<KBConfigResponse['search']>;
}

/**
 * Knowledge Base API
 */
export const knowledgeApi = {
  /**
   * Get all documents (paginated)
   */
  getAll: async (params?: {
    page?: number;
    page_size?: number;
    type?: string;
    access_level?: string;
    search?: string;
    department_id?: string;
  }): Promise<KnowledgeListResponse> => {
    const response = await apiClient.get<KnowledgeListResponse>('/knowledge', { params });
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
    if (data.title) formData.append('title', data.title);
    if (data.description) formData.append('description', data.description);
    if (data.tags) formData.append('tags', JSON.stringify(data.tags));
    if (data.access_level) formData.append('access_level', data.access_level);
    if (data.department_id) formData.append('department_id', data.department_id);

    const response = await apiClient.post<Document>('/knowledge', formData, {
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
   * Search knowledge base (semantic)
   */
  search: async (data: SearchKnowledgeRequest): Promise<SearchKnowledgeResponse> => {
    const response = await apiClient.post<SearchKnowledgeResponse>('/knowledge/search', data);
    return response.data;
  },

  /**
   * Get document processing status
   */
  getProcessingStatus: async (documentId: string): Promise<ProcessingStatusResponse> => {
    const response = await apiClient.get<ProcessingStatusResponse>(
      `/knowledge/${documentId}/status`
    );
    return response.data;
  },

  /**
   * Download document — returns blob and server-provided filename
   */
  download: async (documentId: string): Promise<{ blob: Blob; filename?: string }> => {
    const response = await apiClient.get(`/knowledge/${documentId}/download`, {
      responseType: 'blob',
    });

    // Extract filename from Content-Disposition header
    const disposition = response.headers['content-disposition'] as string | undefined;
    let filename: string | undefined;
    if (disposition) {
      // RFC 5987: filename*=UTF-8''encoded_name
      const utf8Match = disposition.match(/filename\*=UTF-8''(.+)/i);
      if (utf8Match) {
        filename = decodeURIComponent(utf8Match[1]);
      } else {
        // Fallback: filename="name"
        const basicMatch = disposition.match(/filename="?([^";\n]+)"?/i);
        if (basicMatch) {
          filename = basicMatch[1].trim();
        }
      }
    }

    return { blob: response.data, filename };
  },

  /**
   * Get document chunks (paginated)
   */
  getChunks: async (
    documentId: string,
    page: number = 1,
    pageSize: number = 20
  ): Promise<KnowledgeChunksResponse> => {
    const response = await apiClient.get<KnowledgeChunksResponse>(
      `/knowledge/${documentId}/chunks`,
      { params: { page, page_size: pageSize } }
    );
    return response.data;
  },

  /**
   * Reprocess a failed or completed document
   */
  reprocess: async (documentId: string): Promise<Document> => {
    const response = await apiClient.post<Document>(`/knowledge/${documentId}/reprocess`);
    return response.data;
  },

  /**
   * Get knowledge base pipeline configuration
   */
  getConfig: async (): Promise<KBConfigResponse> => {
    const response = await apiClient.get<KBConfigResponse>('/knowledge/config');
    return response.data;
  },

  /**
   * Update knowledge base pipeline configuration
   */
  updateConfig: async (data: KBConfigUpdateRequest): Promise<KBConfigResponse> => {
    const response = await apiClient.put<KBConfigResponse>('/knowledge/config', data);
    return response.data;
  },
};
