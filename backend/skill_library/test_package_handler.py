"""Unit tests for package handler.

References:
- Requirements: Agent Skills Redesign
- Design: Package Handler component
"""

import io
import zipfile
import tarfile
import pytest
from pathlib import Path

from skill_library.package_handler import PackageHandler, PackageInfo


class TestPackageHandler:
    """Test package handler."""

    def create_test_zip(self, include_skill_md: bool = True) -> bytes:
        """Create a test ZIP package.

        Args:
            include_skill_md: Whether to include SKILL.md

        Returns:
            ZIP file bytes
        """
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            if include_skill_md:
                zf.writestr('SKILL.md', '---\nname: test\ndescription: test\n---\n\n# Test')
            zf.writestr('README.md', '# Test Package')
            zf.writestr('requirements.txt', 'requests>=2.0.0')
        return buffer.getvalue()

    def create_test_tar_gz(self, include_skill_md: bool = True) -> bytes:
        """Create a test tar.gz package.

        Args:
            include_skill_md: Whether to include SKILL.md

        Returns:
            tar.gz file bytes
        """
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:gz') as tf:
            if include_skill_md:
                skill_md = tarfile.TarInfo('SKILL.md')
                skill_md_content = b'---\nname: test\ndescription: test\n---\n\n# Test'
                skill_md.size = len(skill_md_content)
                tf.addfile(skill_md, io.BytesIO(skill_md_content))
            
            readme = tarfile.TarInfo('README.md')
            readme_content = b'# Test Package'
            readme.size = len(readme_content)
            tf.addfile(readme, io.BytesIO(readme_content))
        return buffer.getvalue()

    def test_detect_zip_format(self):
        """Test detecting ZIP format."""
        handler = PackageHandler()
        zip_data = self.create_test_zip()
        
        format_type = handler._detect_format(zip_data)
        assert format_type == "zip"

    def test_detect_tar_gz_format(self):
        """Test detecting tar.gz format."""
        handler = PackageHandler()
        tar_data = self.create_test_tar_gz()
        
        format_type = handler._detect_format(tar_data)
        assert format_type == "tar.gz"

    def test_detect_invalid_format(self):
        """Test detecting invalid format."""
        handler = PackageHandler()
        invalid_data = b"not a valid archive"
        
        with pytest.raises(ValueError, match="Unknown package format"):
            handler._detect_format(invalid_data)

    def test_extract_zip_package(self):
        """Test extracting ZIP package."""
        handler = PackageHandler()
        zip_data = self.create_test_zip()
        
        package_info = handler.extract_package(zip_data)
        
        assert package_info.format == "zip"
        assert package_info.skill_md_path.name == "SKILL.md"
        assert len(package_info.additional_files) >= 1  # README.md, requirements.txt
        assert package_info.total_size == len(zip_data)

    def test_extract_tar_gz_package(self):
        """Test extracting tar.gz package."""
        handler = PackageHandler()
        tar_data = self.create_test_tar_gz()
        
        package_info = handler.extract_package(tar_data)
        
        assert package_info.format == "tar.gz"
        assert package_info.skill_md_path.name == "SKILL.md"
        assert len(package_info.additional_files) >= 1  # README.md
        assert package_info.total_size == len(tar_data)

    def test_extract_package_without_skill_md(self):
        """Test extracting package without SKILL.md."""
        handler = PackageHandler()
        zip_data = self.create_test_zip(include_skill_md=False)
        
        with pytest.raises(ValueError, match="SKILL.md not found"):
            handler.extract_package(zip_data)

    def test_extract_package_too_large(self):
        """Test extracting package that exceeds size limit."""
        handler = PackageHandler()
        
        # Create a large package (> 50MB)
        large_data = b"x" * (51 * 1024 * 1024)
        
        with pytest.raises(ValueError, match="Package too large"):
            handler.extract_package(large_data)

    def test_extract_zip_with_path_traversal(self):
        """Test extracting ZIP with path traversal attempt."""
        handler = PackageHandler()
        
        # Create ZIP with path traversal
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as zf:
            zf.writestr('../../../etc/passwd', 'malicious')
        
        with pytest.raises(ValueError, match="Invalid file path"):
            handler.extract_package(buffer.getvalue())

    def test_validate_package_valid(self):
        """Test validating valid package."""
        handler = PackageHandler()
        zip_data = self.create_test_zip()
        package_info = handler.extract_package(zip_data)
        
        errors = handler.validate_package(package_info)
        assert len(errors) == 0

    def test_validate_package_with_executable(self):
        """Test validating package with executable file."""
        handler = PackageHandler()
        
        # Create ZIP with executable
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as zf:
            zf.writestr('SKILL.md', '---\nname: test\ndescription: test\n---\n\n# Test')
            zf.writestr('malicious.exe', 'fake executable')
        
        package_info = handler.extract_package(buffer.getvalue())
        errors = handler.validate_package(package_info)
        
        assert len(errors) > 0
        assert any("Executable file not allowed" in err for err in errors)

    def test_validate_package_with_hidden_file(self):
        """Test validating package with hidden file."""
        handler = PackageHandler()
        
        # Create ZIP with hidden file
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as zf:
            zf.writestr('SKILL.md', '---\nname: test\ndescription: test\n---\n\n# Test')
            zf.writestr('.hidden', 'hidden file')
        
        package_info = handler.extract_package(buffer.getvalue())
        errors = handler.validate_package(package_info)
        
        assert len(errors) > 0
        assert any("Hidden file not allowed" in err for err in errors)

    def test_validate_package_gitignore_allowed(self):
        """Test that .gitignore is allowed."""
        handler = PackageHandler()
        
        # Create ZIP with .gitignore
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as zf:
            zf.writestr('SKILL.md', '---\nname: test\ndescription: test\n---\n\n# Test')
            zf.writestr('.gitignore', '*.pyc\n__pycache__/')
        
        package_info = handler.extract_package(buffer.getvalue())
        errors = handler.validate_package(package_info)
        
        # .gitignore should be allowed
        assert not any(".gitignore" in err for err in errors)

    @pytest.mark.asyncio
    async def test_upload_package_without_minio(self):
        """Test uploading package without MinIO client."""
        handler = PackageHandler(minio_client=None)
        zip_data = self.create_test_zip()
        
        with pytest.raises(ValueError, match="MinIO client not configured"):
            await handler.upload_package(zip_data, "test_skill", "1.0.0")

    @pytest.mark.asyncio
    async def test_upload_package_too_large(self):
        """Test uploading package that exceeds size limit."""
        handler = PackageHandler(minio_client="mock")
        
        # Create large data
        large_data = b"x" * (51 * 1024 * 1024)
        
        with pytest.raises(ValueError, match="Package too large"):
            await handler.upload_package(large_data, "test_skill", "1.0.0")

    @pytest.mark.asyncio
    async def test_upload_package_returns_path(self):
        """Test that upload returns storage path."""
        handler = PackageHandler(minio_client="mock")
        zip_data = self.create_test_zip()
        
        storage_path = await handler.upload_package(zip_data, "test_skill", "1.0.0")
        
        assert storage_path == "skills/test_skill/1.0.0/package.zip"

    def test_find_skill_md_in_root(self):
        """Test finding SKILL.md in root directory."""
        handler = PackageHandler()
        
        # Create ZIP with SKILL.md in root
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as zf:
            zf.writestr('SKILL.md', '---\nname: test\ndescription: test\n---\n\n# Test')
        
        package_info = handler.extract_package(buffer.getvalue())
        assert package_info.skill_md_path.name == "SKILL.md"

    def test_find_skill_md_in_subdirectory(self):
        """Test finding SKILL.md in subdirectory."""
        handler = PackageHandler()
        
        # Create ZIP with SKILL.md in subdirectory
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as zf:
            zf.writestr('my-skill/SKILL.md', '---\nname: test\ndescription: test\n---\n\n# Test')
            zf.writestr('my-skill/README.md', '# Test')
        
        package_info = handler.extract_package(buffer.getvalue())
        assert package_info.skill_md_path.name == "SKILL.md"
        assert len(package_info.additional_files) >= 1  # README.md

    def test_collect_additional_files(self):
        """Test collecting additional files from package."""
        handler = PackageHandler()
        
        # Create ZIP with multiple files
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as zf:
            zf.writestr('SKILL.md', '---\nname: test\ndescription: test\n---\n\n# Test')
            zf.writestr('README.md', '# Test')
            zf.writestr('requirements.txt', 'requests>=2.0.0')
            zf.writestr('config.yaml', 'key: value')
        
        package_info = handler.extract_package(buffer.getvalue())
        
        # Should have 3 additional files (README, requirements, config)
        assert len(package_info.additional_files) == 3
        
        # SKILL.md should not be in additional files
        file_names = [f.name for f in package_info.additional_files]
        assert 'SKILL.md' not in file_names
        assert 'README.md' in file_names
        assert 'requirements.txt' in file_names
        assert 'config.yaml' in file_names
