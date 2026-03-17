"""Package handler for Agent Skills.

Handles skill package upload, extraction, and validation.

References:
- Requirements: Agent Skills Redesign
- Design: Package Handler component
"""

import io
import logging
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PackageInfo:
    """Information about uploaded package."""

    skill_md_path: Path
    additional_files: List[Path]
    total_size: int
    format: str  # 'zip' or 'tar.gz'


class PackageHandler:
    """Handle skill package upload and extraction."""

    def __init__(self, minio_client=None):
        """Initialize package handler.

        Args:
            minio_client: MinIO client for storage (optional)
        """
        self.minio_client = minio_client
        self.max_size = 50 * 1024 * 1024  # 50MB

    @staticmethod
    def _get_temp_root() -> str:
        """Return a guaranteed-existing temp root for package extraction."""
        temp_root = Path(tempfile.gettempdir())
        temp_root.mkdir(parents=True, exist_ok=True)
        return str(temp_root)

    def extract_package(self, file_data: bytes) -> PackageInfo:
        """Extract and validate package.

        Args:
            file_data: Package file bytes

        Returns:
            Package information

        Raises:
            ValueError: If package format is invalid
        """
        # Check size
        if len(file_data) > self.max_size:
            raise ValueError(f"Package too large: {len(file_data)} bytes (max {self.max_size})")

        # Detect format
        package_format = self._detect_format(file_data)

        # Create persistent temporary directory (caller must clean up)
        import tempfile

        temp_dir = tempfile.mkdtemp(
            prefix="skill_package_",
            dir=self._get_temp_root(),
        )
        temp_path = Path(temp_dir)

        try:
            if package_format == "zip":
                self._extract_zip(file_data, temp_path)
            elif package_format == "tar.gz":
                self._extract_tar(file_data, temp_path)
            else:
                raise ValueError(f"Unsupported package format: {package_format}")

            # Find SKILL.md
            skill_md_path = self._find_skill_md(temp_path)
            if not skill_md_path:
                raise ValueError("SKILL.md not found in package")

            # Collect additional files
            additional_files = self._collect_files(temp_path, skill_md_path)

            # Calculate total size
            total_size = len(file_data)

            logger.info(
                f"Extracted package: format={package_format}, "
                f"files={len(additional_files) + 1}, size={total_size}, "
                f"temp_dir={temp_dir}"
            )

            return PackageInfo(
                skill_md_path=skill_md_path,
                additional_files=additional_files,
                total_size=total_size,
                format=package_format,
            )
        except Exception as e:
            # Clean up on error
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

    def _detect_format(self, file_data: bytes) -> str:
        """Detect package format.

        Args:
            file_data: Package file bytes

        Returns:
            Format string ('zip' or 'tar.gz')

        Raises:
            ValueError: If format cannot be detected
        """
        # Check ZIP magic number
        if file_data[:4] == b"PK\x03\x04":
            return "zip"

        # Check tar.gz magic number
        if file_data[:2] == b"\x1f\x8b":
            return "tar.gz"

        raise ValueError("Unknown package format (not ZIP or tar.gz)")

    def _extract_zip(self, file_data: bytes, dest_path: Path):
        """Extract ZIP archive.

        Args:
            file_data: ZIP file bytes
            dest_path: Destination directory

        Raises:
            ValueError: If extraction fails
        """
        try:
            with zipfile.ZipFile(io.BytesIO(file_data)) as zf:
                # Check for path traversal
                for name in zf.namelist():
                    if name.startswith("/") or ".." in name:
                        raise ValueError(f"Invalid file path in archive: {name}")

                # Extract all files
                zf.extractall(dest_path)

        except zipfile.BadZipFile as e:
            raise ValueError(f"Invalid ZIP file: {e}")
        except Exception as e:
            raise ValueError(f"Failed to extract ZIP: {e}")

    def _extract_tar(self, file_data: bytes, dest_path: Path):
        """Extract tar.gz archive.

        Args:
            file_data: tar.gz file bytes
            dest_path: Destination directory

        Raises:
            ValueError: If extraction fails
        """
        try:
            with tarfile.open(fileobj=io.BytesIO(file_data), mode="r:gz") as tf:
                # Check for path traversal
                for member in tf.getmembers():
                    if member.name.startswith("/") or ".." in member.name:
                        raise ValueError(f"Invalid file path in archive: {member.name}")

                # Extract all files
                tf.extractall(dest_path)

        except tarfile.TarError as e:
            raise ValueError(f"Invalid tar.gz file: {e}")
        except Exception as e:
            raise ValueError(f"Failed to extract tar.gz: {e}")

    def _find_skill_md(self, base_path: Path) -> Optional[Path]:
        """Find SKILL.md in extracted package.

        Searches in root and one level deep.

        Args:
            base_path: Base directory to search

        Returns:
            Path to SKILL.md or None if not found
        """
        # Check root
        skill_md = base_path / "SKILL.md"
        if skill_md.exists():
            return skill_md

        # Check one level deep
        for item in base_path.iterdir():
            if item.is_dir():
                skill_md = item / "SKILL.md"
                if skill_md.exists():
                    return skill_md

        return None

    def _collect_files(self, base_path: Path, skill_md_path: Path) -> List[Path]:
        """Collect additional files in package.

        Args:
            base_path: Base directory
            skill_md_path: Path to SKILL.md

        Returns:
            List of additional file paths
        """
        additional_files = []

        # Get package root (directory containing SKILL.md)
        package_root = skill_md_path.parent

        # Collect all files in package root
        for item in package_root.rglob("*"):
            if item.is_file() and item != skill_md_path:
                additional_files.append(item)

        return additional_files

    def validate_package(self, package_info: PackageInfo) -> List[str]:
        """Validate package contents.

        Args:
            package_info: Package information

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check size
        if package_info.total_size > self.max_size:
            errors.append(
                f"Package too large: {package_info.total_size} bytes " f"(max {self.max_size})"
            )

        # Check for malicious files
        all_files = [package_info.skill_md_path] + package_info.additional_files
        for file_path in all_files:
            # Check for executable files (basic check)
            if file_path.suffix in [".exe", ".sh", ".bat", ".cmd"]:
                errors.append(f"Executable file not allowed: {file_path.name}")

            # Check for hidden files (starting with .)
            # Allow common development and system files
            allowed_hidden = {
                ".gitignore",
                ".gitkeep",
                ".DS_Store",  # macOS system file
                ".env.example",  # Example environment file
                ".editorconfig",  # Editor configuration
                ".prettierrc",  # Prettier configuration
                ".eslintrc",  # ESLint configuration
            }
            if file_path.name.startswith(".") and file_path.name not in allowed_hidden:
                errors.append(f"Hidden file not allowed: {file_path.name}")

        return errors

    async def upload_package(self, file_data: bytes, skill_name: str, version: str) -> str:
        """Upload package to MinIO.

        Args:
            file_data: Package file bytes
            skill_name: Skill name
            version: Skill version

        Returns:
            MinIO storage path

        Raises:
            ValueError: If package is invalid or upload fails
        """
        if not self.minio_client:
            raise ValueError("MinIO client not configured")

        # Validate size
        if len(file_data) > self.max_size:
            raise ValueError(f"Package too large: {len(file_data)} bytes (max {self.max_size})")

        # Generate storage path (object key)
        storage_path = f"skills/{skill_name}/{version}/package.zip"

        try:
            # Upload to MinIO using upload_file method
            logger.info(f"Uploading package to MinIO: {storage_path} ({len(file_data)} bytes)")

            # Use MinIO client's upload_file method
            # Use artifacts bucket for skill packages (no file type restrictions)
            bucket_name, object_key = self.minio_client.upload_file(
                bucket_type="artifacts",  # Use artifacts bucket for skill packages
                file_data=io.BytesIO(file_data),
                filename=f"{skill_name}-{version}.zip",
                user_id="system",  # System upload
                task_id=None,
                agent_id=None,
                content_type="application/zip",
                metadata={
                    "skill_name": skill_name,
                    "version": version,
                    "package_type": "agent_skill",
                },
            )

            logger.info(f"Package uploaded successfully to {bucket_name}/{object_key}")

            # Return the object key (storage path)
            return object_key

        except Exception as e:
            logger.error(f"Failed to upload package to MinIO: {e}")
            raise ValueError(f"Failed to upload package: {e}")
