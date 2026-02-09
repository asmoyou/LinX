"""ZIP archive extraction handler for Knowledge Base.

Extracts files from ZIP archives with validation, filtering, and safety checks.
"""

import io
import os
import zipfile
from dataclasses import dataclass, field
from typing import BinaryIO, List, Tuple

import logging

logger = logging.getLogger(__name__)

# Supported file extensions (matches knowledge router's EXT_TO_DOC_TYPE)
SUPPORTED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".txt", ".md",
    ".jpg", ".jpeg", ".png", ".gif",
    ".mp3", ".wav", ".mp4", ".avi",
}

# Files/directories to skip
SKIP_PATTERNS = {"__MACOSX", ".DS_Store", "Thumbs.db", ".git", "__pycache__"}

# Limits
MAX_FILES = 100
MAX_TOTAL_SIZE = 500 * 1024 * 1024  # 500MB
MAX_COMPRESSION_RATIO = 100  # zip bomb protection


@dataclass
class ExtractedFile:
    """A single file extracted from a ZIP archive."""

    filename: str
    data: io.BytesIO
    size: int


@dataclass
class ZipExtractionResult:
    """Result of extracting a ZIP archive."""

    extracted_files: List[ExtractedFile] = field(default_factory=list)
    skipped_files: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def _should_skip(name: str) -> bool:
    """Check if a file/path should be skipped."""
    parts = name.replace("\\", "/").split("/")
    for part in parts:
        if part in SKIP_PATTERNS or part.startswith("."):
            return True
    return False


def _deduplicate_filename(filename: str, existing: set) -> str:
    """Add numeric suffix to filename if it already exists."""
    if filename not in existing:
        return filename
    base, ext = os.path.splitext(filename)
    counter = 1
    while True:
        new_name = f"{base}_{counter}{ext}"
        if new_name not in existing:
            return new_name
        counter += 1


def extract_zip(zip_data: BinaryIO) -> ZipExtractionResult:
    """Extract files from a ZIP archive with validation and filtering.

    Args:
        zip_data: Binary stream of the ZIP file.

    Returns:
        ZipExtractionResult with extracted files, skipped files, and errors.
    """
    result = ZipExtractionResult()

    # Read ZIP data to check compressed size
    zip_data.seek(0, 2)
    compressed_size = zip_data.tell()
    zip_data.seek(0)

    if compressed_size == 0:
        result.errors.append("ZIP file is empty")
        return result

    try:
        zf = zipfile.ZipFile(zip_data, "r")
    except zipfile.BadZipFile:
        result.errors.append("Invalid or corrupted ZIP file")
        return result

    with zf:
        # Check for zip bomb: total uncompressed size vs compressed size
        total_uncompressed = sum(info.file_size for info in zf.infolist())
        if compressed_size > 0 and total_uncompressed / compressed_size > MAX_COMPRESSION_RATIO:
            result.errors.append(
                f"ZIP compression ratio too high ({total_uncompressed / compressed_size:.0f}:1). "
                f"Maximum allowed is {MAX_COMPRESSION_RATIO}:1."
            )
            return result

        if total_uncompressed > MAX_TOTAL_SIZE:
            result.errors.append(
                f"Total extracted size ({total_uncompressed / 1024 / 1024:.1f}MB) "
                f"exceeds limit ({MAX_TOTAL_SIZE / 1024 / 1024:.0f}MB)"
            )
            return result

        existing_names: set = set()
        total_extracted_size = 0

        for info in zf.infolist():
            # Skip directories
            if info.is_dir():
                continue

            original_path = info.filename

            # Skip hidden/system files
            if _should_skip(original_path):
                result.skipped_files.append(original_path)
                continue

            # Flatten: use only the basename
            basename = os.path.basename(original_path)
            if not basename:
                continue

            # Check extension
            ext = os.path.splitext(basename)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                result.skipped_files.append(f"{original_path} (unsupported: {ext})")
                continue

            # Check file count limit
            if len(result.extracted_files) >= MAX_FILES:
                result.errors.append(
                    f"Reached maximum file limit ({MAX_FILES}). "
                    f"Remaining files were skipped."
                )
                break

            # Deduplicate filename
            unique_name = _deduplicate_filename(basename, existing_names)
            existing_names.add(unique_name)

            # Extract file data
            try:
                file_data = zf.read(info.filename)
            except Exception as e:
                result.errors.append(f"Failed to extract {original_path}: {str(e)}")
                continue

            file_size = len(file_data)
            total_extracted_size += file_size

            if total_extracted_size > MAX_TOTAL_SIZE:
                result.errors.append(
                    f"Total extracted size exceeds limit ({MAX_TOTAL_SIZE / 1024 / 1024:.0f}MB). "
                    f"Remaining files were skipped."
                )
                break

            result.extracted_files.append(
                ExtractedFile(
                    filename=unique_name,
                    data=io.BytesIO(file_data),
                    size=file_size,
                )
            )

    logger.info(
        f"ZIP extraction complete: {len(result.extracted_files)} files extracted, "
        f"{len(result.skipped_files)} skipped, {len(result.errors)} errors"
    )
    return result
