"""Integration tests for Document upload → Processing → Indexing flow.

Tests the complete document processing pipeline.

References:
- Task 8.2.5: Test Document upload → Processing → Indexing flow
"""

import pytest
from uuid import uuid4
from unittest.mock import Mock, patch, AsyncMock
import io


@pytest.fixture
def mock_minio_client():
    """Mock MinIO client."""
    with patch('object_storage.minio_client.get_minio_client') as mock:
        client = Mock()
        client.upload_file = Mock(return_value=('documents', 'test/file.pdf'))
        client.download_file = Mock(return_value=(io.BytesIO(b'PDF content'), {}))
        mock.return_value = client
        yield client


@pytest.fixture
def mock_processing_queue():
    """Mock processing queue."""
    with patch('knowledge_base.processing_queue.ProcessingQueue') as mock:
        queue = Mock()
        queue.enqueue = AsyncMock(return_value=str(uuid4()))
        queue.get_status = AsyncMock(return_value={'status': 'processing'})
        mock.return_value = queue
        yield queue


@pytest.fixture
def mock_knowledge_indexer():
    """Mock knowledge indexer."""
    with patch('knowledge_base.knowledge_indexer.KnowledgeIndexer') as mock:
        indexer = Mock()
        indexer.index_document = AsyncMock(return_value=True)
        mock.return_value = indexer
        yield indexer


class TestDocumentFlowIntegration:
    """Test Document upload → Processing → Indexing flow."""
    
    @pytest.mark.asyncio
    async def test_complete_document_upload_flow(
        self, mock_minio_client, mock_processing_queue, mock_knowledge_indexer
    ):
        """Test complete flow from upload to indexing."""
        from knowledge_base.document_upload import DocumentUpload
        
        upload = DocumentUpload()
        user_id = uuid4()
        
        # Upload document
        file_data = io.BytesIO(b'Test PDF content')
        result = await upload.upload_document(
            user_id=user_id,
            filename='test_document.pdf',
            file_data=file_data,
            title='Test Document',
            content_type='document'
        )
        
        assert 'knowledge_id' in result
        assert result['status'] == 'processing'
        
        # Verify file was uploaded to MinIO
        mock_minio_client.upload_file.assert_called_once()
        
        # Verify processing was queued
        mock_processing_queue.enqueue.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_document_processing_extracts_text(self):
        """Test that document processing extracts text content."""
        from knowledge_base.document_processor_worker import DocumentProcessorWorker
        from knowledge_base.text_extractors import PDFExtractor
        
        with patch.object(PDFExtractor, 'extract_text') as mock_extract:
            mock_extract.return_value = "Extracted text from PDF"
            
            worker = DocumentProcessorWorker()
            knowledge_id = uuid4()
            
            # Process document
            result = await worker.process_document(
                knowledge_id=knowledge_id,
                file_path='test/file.pdf',
                content_type='application/pdf'
            )
            
            assert result['success'] is True
            assert 'text' in result
            assert len(result['text']) > 0
            
            # Verify text extraction was called
            mock_extract.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_document_chunking_creates_segments(self):
        """Test that documents are chunked for indexing."""
        from knowledge_base.document_chunker import get_document_chunker
        
        chunker = get_document_chunker()
        
        # Long document text
        text = "This is a test document. " * 100
        
        # Chunk document
        chunks = chunker.chunk_text(
            text=text,
            chunk_size=200,
            overlap=50
        )
        
        assert len(chunks) > 1
        assert all(len(chunk) <= 250 for chunk in chunks)  # chunk_size + overlap
        
        # Verify overlap between chunks
        for i in range(len(chunks) - 1):
            assert chunks[i][-20:] in chunks[i + 1][:70]  # Some overlap exists
    
    @pytest.mark.asyncio
    async def test_document_indexing_creates_embeddings(self, mock_knowledge_indexer):
        """Test that document indexing creates vector embeddings."""
        from knowledge_base.knowledge_indexer import KnowledgeIndexer
        from memory_system.embedding_service import EmbeddingService
        
        with patch.object(EmbeddingService, 'generate_embedding') as mock_embed:
            mock_embed.return_value = [0.1] * 384  # Mock embedding vector
            
            indexer = KnowledgeIndexer()
            knowledge_id = uuid4()
            
            # Index document chunks
            chunks = [
                "First chunk of text",
                "Second chunk of text",
                "Third chunk of text"
            ]
            
            result = await indexer.index_chunks(
                knowledge_id=knowledge_id,
                chunks=chunks
            )
            
            assert result['success'] is True
            assert result['indexed_count'] == len(chunks)
            
            # Verify embeddings were generated for each chunk
            assert mock_embed.call_count == len(chunks)
    
    @pytest.mark.asyncio
    async def test_document_metadata_stored_in_database(self):
        """Test that document metadata is stored in database."""
        from knowledge_base.document_upload import DocumentUpload
        from database.models import KnowledgeItem
        
        with patch('database.connection.get_db_session') as mock_session:
            session = Mock()
            mock_session.return_value.__enter__.return_value = session
            
            upload = DocumentUpload()
            user_id = uuid4()
            
            # Upload document
            file_data = io.BytesIO(b'Test content')
            result = await upload.upload_document(
                user_id=user_id,
                filename='test.pdf',
                file_data=file_data,
                title='Test Document',
                content_type='document'
            )
            
            # Verify database record was created
            session.add.assert_called_once()
            added_item = session.add.call_args[0][0]
            assert isinstance(added_item, KnowledgeItem)
            assert added_item.title == 'Test Document'
            assert added_item.owner_user_id == user_id
            
            session.commit.assert_called()
    
    @pytest.mark.asyncio
    async def test_document_search_after_indexing(self, mock_knowledge_indexer):
        """Test that indexed documents are searchable."""
        from knowledge_base.knowledge_search import KnowledgeSearch
        
        search = KnowledgeSearch()
        
        # Mock vector search results
        with patch('memory_system.milvus_connection.MilvusConnection.search') as mock_search:
            mock_search.return_value = [
                {
                    'id': str(uuid4()),
                    'distance': 0.15,
                    'entity': {
                        'knowledge_id': str(uuid4()),
                        'chunk_text': 'Relevant document content'
                    }
                }
            ]
            
            # Search for documents
            results = await search.search(
                query="test document",
                user_id=uuid4(),
                limit=5
            )
            
            assert len(results) > 0
            assert results[0]['relevance_score'] > 0.8
            
            # Verify vector search was performed
            mock_search.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_document_processing_handles_errors(self, mock_processing_queue):
        """Test that document processing handles errors gracefully."""
        from knowledge_base.document_processor_worker import DocumentProcessorWorker
        
        worker = DocumentProcessorWorker()
        knowledge_id = uuid4()
        
        # Simulate processing error
        with patch('knowledge_base.text_extractors.PDFExtractor.extract_text') as mock_extract:
            mock_extract.side_effect = Exception("Corrupted PDF")
            
            result = await worker.process_document(
                knowledge_id=knowledge_id,
                file_path='corrupted.pdf',
                content_type='application/pdf'
            )
            
            assert result['success'] is False
            assert 'error' in result
            
            # Verify error status was updated
            mock_processing_queue.update_status.assert_called_with(
                knowledge_id=knowledge_id,
                status='failed',
                error=mock.ANY
            )
