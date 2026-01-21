"""File validation and malware scanning for document uploads.

References:
- Requirements 16: Document Processing
- Design Section 14.1: Processing Workflow
"""

import hashlib
import logging
import magic
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class SupportedFileType(Enum):
    """Supported file types for document processing."""
    
    # Documents
    PDF = "application/pdf"
    DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    DOC = "application/msword"
    TXT = "text/plain"
    MD = "text/markdown"
    HTML = "text/html"
    
    # Images
    PNG = "image/png"
    JPG = "image/jpeg"
    GIF = "image/gif"
    BMP = "image/bmp"
    
    # Audio
    MP3 = "audio/mpeg"
    WAV = "audio/wav"
    M4A = "audio/mp4"
    FLAC = "audio/flac"
    
    # Video
    MP4 = "video/mp4"
    AVI = "video/x-msvideo"
    MOV = "video/quicktime"
    MKV = "video/x-matroska"


@dataclass
class FileValidationResult:
    """Result of file validation."""
    
    is_valid: bool
    file_type: Optional[SupportedFileType]
    mime_type: str
    file_size: int
    content_hash: str
    error_message: Optional[str] = None
    is_malware: bool = False


class FileValidator:
    """Validates uploaded files for type, size, and malware."""
    
    def __init__(
        self,
        max_file_size: int = 100 * 1024 * 1024,  # 100MB default
        enable_malware_scan: bool = False,
    ):
        """Initialize file validator.
        
        Args:
            max_file_size: Maximum allowed file size in bytes
            enable_malware_scan: Whether to enable malware scanning (requires ClamAV)
        """
        self.max_file_size = max_file_size
        self.enable_malware_scan = enable_malware_scan
        self.magic = magic.Magic(mime=True)
        
        # Map MIME types to supported file types
        self.mime_type_map = {ft.value: ft for ft in SupportedFileType}
        
        logger.info(
            "FileValidator initialized",
            extra={
                "max_file_size": max_file_size,
                "enable_malware_scan": enable_malware_scan,
            }
        )
    
    def validate_file(self, file_path: Path) -> FileValidationResult:
        """Validate a file for upload.
        
        Args:
            file_path: Path to the file to validate
            
        Returns:
            FileValidationResult with validation details
        """
        try:
            # Check file exists
            if not file_path.exists():
                return FileValidationResult(
                    is_valid=False,
                    file_type=None,
                    mime_type="",
                    file_size=0,
                    content_hash="",
                    error_message="File does not exist",
                )
            
            # Check file size
            file_size = file_path.stat().st_size
            if file_size > self.max_file_size:
                return FileValidationResult(
                    is_valid=False,
                    file_type=None,
                    mime_type="",
                    file_size=file_size,
                    content_hash="",
                    error_message=f"File size {file_size} exceeds maximum {self.max_file_size}",
                )
            
            # Detect MIME type
            mime_type = self.magic.from_file(str(file_path))
            
            # Check if file type is supported
            file_type = self.mime_type_map.get(mime_type)
            if file_type is None:
                # Try to match by extension for text files
                if file_path.suffix.lower() in ['.txt', '.md', '.markdown']:
                    file_type = SupportedFileType.TXT if file_path.suffix == '.txt' else SupportedFileType.MD
                    mime_type = file_type.value
                else:
                    return FileValidationResult(
                        is_valid=False,
                        file_type=None,
                        mime_type=mime_type,
                        file_size=file_size,
                        content_hash="",
                        error_message=f"Unsupported file type: {mime_type}",
                    )
            
            # Calculate content hash
            content_hash = self._calculate_hash(file_path)
            
            # Malware scan (if enabled)
            is_malware = False
            if self.enable_malware_scan:
                is_malware = self._scan_malware(file_path)
                if is_malware:
                    return FileValidationResult(
                        is_valid=False,
                        file_type=file_type,
                        mime_type=mime_type,
                        file_size=file_size,
                        content_hash=content_hash,
                        error_message="Malware detected in file",
                        is_malware=True,
                    )
            
            return FileValidationResult(
                is_valid=True,
                file_type=file_type,
                mime_type=mime_type,
                file_size=file_size,
                content_hash=content_hash,
            )
            
        except Exception as e:
            logger.error(f"Error validating file: {e}", exc_info=True)
            return FileValidationResult(
                is_valid=False,
                file_type=None,
                mime_type="",
                file_size=0,
                content_hash="",
                error_message=f"Validation error: {str(e)}",
            )
    
    def _calculate_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file content.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Hexadecimal hash string
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def _scan_malware(self, file_path: Path) -> bool:
        """Scan file for malware using ClamAV.
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if malware detected, False otherwise
        """
        try:
            import clamd
            cd = clamd.ClamdUnixSocket()
            result = cd.scan(str(file_path))
            
            if result:
                for filename, (status, virus_name) in result.items():
                    if status == "FOUND":
                        logger.warning(
                            f"Malware detected: {virus_name}",
                            extra={"file": str(file_path), "virus": virus_name}
                        )
                        return True
            return False
            
        except Exception as e:
            logger.warning(f"Malware scan failed: {e}")
            # Don't block upload if scan fails
            return False


# Singleton instance
_file_validator: Optional[FileValidator] = None


def get_file_validator(
    max_file_size: int = 100 * 1024 * 1024,
    enable_malware_scan: bool = False,
) -> FileValidator:
    """Get or create the file validator singleton.
    
    Args:
        max_file_size: Maximum allowed file size in bytes
        enable_malware_scan: Whether to enable malware scanning
        
    Returns:
        FileValidator instance
    """
    global _file_validator
    if _file_validator is None:
        _file_validator = FileValidator(
            max_file_size=max_file_size,
            enable_malware_scan=enable_malware_scan,
        )
    return _file_validator
