import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Upload as UploadIcon } from 'lucide-react';
import { DocumentCard } from '@/components/knowledge/DocumentCard';
import { UploadZone } from '@/components/knowledge/UploadZone';
import { DocumentViewer } from '@/components/knowledge/DocumentViewer';
import { SearchBar } from '@/components/knowledge/SearchBar';
import type { Document } from '@/types/document';

export const Knowledge: React.FC = () => {
  const { t } = useTranslation();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [showUploadZone, setShowUploadZone] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState<Document | null>(null);
  const [isViewerOpen, setIsViewerOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [accessFilter, setAccessFilter] = useState('all');

  // Mock data for demonstration
  useEffect(() => {
    const mockDocuments: Document[] = [
      {
        id: '1',
        name: 'Q4 Sales Report.pdf',
        type: 'pdf',
        size: 2457600,
        status: 'completed',
        uploadedAt: new Date(Date.now() - 86400000).toISOString(),
        processedAt: new Date(Date.now() - 86000000).toISOString(),
        owner: 'John Doe',
        accessLevel: 'internal',
        tags: ['sales', 'report', 'Q4'],
        description: 'Quarterly sales analysis and projections',
      },
      {
        id: '2',
        name: 'Product Roadmap 2026.docx',
        type: 'docx',
        size: 1048576,
        status: 'completed',
        uploadedAt: new Date(Date.now() - 172800000).toISOString(),
        processedAt: new Date(Date.now() - 172400000).toISOString(),
        owner: 'Jane Smith',
        accessLevel: 'confidential',
        tags: ['roadmap', 'product', 'strategy'],
        description: 'Strategic product development plan',
      },
      {
        id: '3',
        name: 'Team Photo.jpg',
        type: 'image',
        size: 3145728,
        status: 'completed',
        uploadedAt: new Date(Date.now() - 259200000).toISOString(),
        processedAt: new Date(Date.now() - 258800000).toISOString(),
        owner: 'Admin',
        accessLevel: 'public',
        tags: ['team', 'photo'],
      },
      {
        id: '4',
        name: 'Training Video.mp4',
        type: 'video',
        size: 52428800,
        status: 'processing',
        uploadedAt: new Date(Date.now() - 3600000).toISOString(),
        owner: 'Training Dept',
        accessLevel: 'internal',
        processingProgress: 45,
        tags: ['training', 'onboarding'],
      },
    ];
    setDocuments(mockDocuments);
  }, []);

  const handleUpload = (files: File[]) => {
    // Simulate file upload
    const newDocuments: Document[] = files.map((file, index) => ({
      id: String(Date.now() + index),
      name: file.name,
      type: file.type.includes('pdf') ? 'pdf' : 
            file.type.includes('word') ? 'docx' :
            file.type.includes('image') ? 'image' :
            file.type.includes('audio') ? 'audio' :
            file.type.includes('video') ? 'video' : 'txt',
      size: file.size,
      status: 'uploading',
      uploadedAt: new Date().toISOString(),
      owner: 'Current User',
      accessLevel: 'internal',
      uploadProgress: 0,
    }));

    setDocuments((prev) => [...newDocuments, ...prev]);
    setShowUploadZone(false);

    // Simulate upload progress
    newDocuments.forEach((doc, index) => {
      let progress = 0;
      const uploadInterval = setInterval(() => {
        progress += 10;
        if (progress <= 100) {
          setDocuments((prev) =>
            prev.map((d) =>
              d.id === doc.id ? { ...d, uploadProgress: progress } : d
            )
          );
        }
        if (progress === 100) {
          clearInterval(uploadInterval);
          // Start processing
          setDocuments((prev) =>
            prev.map((d) =>
              d.id === doc.id ? { ...d, status: 'processing', processingProgress: 0 } : d
            )
          );
          
          // Simulate processing
          let procProgress = 0;
          const procInterval = setInterval(() => {
            procProgress += 15;
            if (procProgress <= 100) {
              setDocuments((prev) =>
                prev.map((d) =>
                  d.id === doc.id ? { ...d, processingProgress: procProgress } : d
                )
              );
            }
            if (procProgress >= 100) {
              clearInterval(procInterval);
              setDocuments((prev) =>
                prev.map((d) =>
                  d.id === doc.id
                    ? { ...d, status: 'completed', processedAt: new Date().toISOString() }
                    : d
                )
              );
            }
          }, 500);
        }
      }, 300);
    });
  };

  const handleView = (document: Document) => {
    setSelectedDocument(document);
    setIsViewerOpen(true);
  };

  const handleDownload = (document: Document) => {
    console.log('Downloading:', document.name);
    // Implement download logic
  };

  const handleDelete = (document: Document) => {
    if (confirm(`Are you sure you want to delete ${document.name}?`)) {
      setDocuments((prev) => prev.filter((d) => d.id !== document.id));
    }
  };

  // Filter documents
  const filteredDocuments = documents.filter((doc) => {
    const matchesSearch = doc.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         doc.tags?.some(tag => tag.toLowerCase().includes(searchQuery.toLowerCase()));
    const matchesType = typeFilter === 'all' || doc.type === typeFilter;
    const matchesAccess = accessFilter === 'all' || doc.accessLevel === accessFilter;
    return matchesSearch && matchesType && matchesAccess;
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold text-gray-800 dark:text-white">
          {t('nav.knowledge')}
        </h1>
        <button
          onClick={() => setShowUploadZone(!showUploadZone)}
          className="flex items-center gap-2 px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors font-medium"
        >
          <UploadIcon className="w-5 h-5" />
          Upload Documents
        </button>
      </div>

      {/* Upload Zone */}
      {showUploadZone && (
        <div className="mb-6">
          <UploadZone onUpload={handleUpload} />
        </div>
      )}

      {/* Search and Filters */}
      <SearchBar
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        typeFilter={typeFilter}
        onTypeFilterChange={setTypeFilter}
        accessFilter={accessFilter}
        onAccessFilterChange={setAccessFilter}
      />

      {/* Document Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {filteredDocuments.length === 0 ? (
          <div className="col-span-full text-center py-12">
            <p className="text-gray-500 dark:text-gray-400">
              {documents.length === 0
                ? 'No documents yet. Upload your first document to get started.'
                : 'No documents match your search criteria.'}
            </p>
          </div>
        ) : (
          filteredDocuments.map((document) => (
            <DocumentCard
              key={document.id}
              document={document}
              onView={handleView}
              onDownload={handleDownload}
              onDelete={handleDelete}
            />
          ))
        )}
      </div>

      {/* Document Viewer Modal */}
      <DocumentViewer
        document={selectedDocument}
        isOpen={isViewerOpen}
        onClose={() => {
          setIsViewerOpen(false);
          setSelectedDocument(null);
        }}
      />
    </div>
  );
};
