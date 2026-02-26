"""Skill Loader - Extracts and loads executable code from skills.

This module provides functionality to:
1. Parse SKILL.md files and extract code blocks
2. Load code from skill packages stored in MinIO
3. Provide code to agents for direct execution

References:
- Design: .kiro/specs/code-execution-improvement/design.md
- Requirements: .kiro/specs/code-execution-improvement/requirements.md
"""

import logging
import re
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class SkillCode:
    """Represents extracted code from a skill."""
    
    language: str
    code: str
    filename: Optional[str] = None
    description: Optional[str] = None
    is_executable: bool = True
    
    def __post_init__(self):
        """Validate and normalize language."""
        # Normalize language names
        lang_map = {
            'py': 'python',
            'js': 'javascript',
            'ts': 'typescript',
            'sh': 'bash',
            'shell': 'bash',
        }
        self.language = lang_map.get(self.language.lower(), self.language.lower())


@dataclass
class SkillPackage:
    """Represents a complete skill package with all code."""
    
    skill_id: UUID
    skill_name: str
    skill_md_content: Optional[str] = None
    code_blocks: List[SkillCode] = field(default_factory=list)
    package_files: Dict[str, str] = field(default_factory=dict)
    manifest: Optional[dict] = None
    
    def get_code_by_language(self, language: str) -> List[SkillCode]:
        """Get all code blocks for a specific language.
        
        Args:
            language: Programming language (python, javascript, bash, etc.)
            
        Returns:
            List of SkillCode objects for the language
        """
        language = language.lower()
        return [code for code in self.code_blocks if code.language == language]
    
    def get_executable_code(self, language: str) -> Optional[str]:
        """Get the first executable code block for a language.
        
        Args:
            language: Programming language
            
        Returns:
            Code string or None if not found
        """
        codes = self.get_code_by_language(language)
        executable = [c for c in codes if c.is_executable]
        return executable[0].code if executable else None
    
    def get_all_executable_code(self, language: str) -> str:
        """Get all executable code blocks concatenated.
        
        Args:
            language: Programming language
            
        Returns:
            Concatenated code string
        """
        codes = self.get_code_by_language(language)
        executable = [c.code for c in codes if c.is_executable]
        return '\n\n'.join(executable)


class SkillLoader:
    """Loads and extracts code from skills."""
    
    def __init__(self):
        """Initialize skill loader."""
        self.logger = logging.getLogger(__name__)
        self.logger.info("SkillLoader initialized")
    
    def load_skill(
        self,
        skill_id: UUID,
        skill_name: str,
        skill_md_content: Optional[str] = None,
        storage_path: Optional[str] = None,
        manifest: Optional[dict] = None,
        package_files: Optional[Dict[str, str]] = None,
    ) -> SkillPackage:
        """Load a skill and extract all code.
        
        Args:
            skill_id: Skill UUID
            skill_name: Skill name
            skill_md_content: SKILL.md content
            storage_path: MinIO storage path for package skills
            manifest: Parsed manifest for package skills
            package_files: Optional pre-loaded package files (preferred if available)
            
        Returns:
            SkillPackage with extracted code
        """
        package = SkillPackage(
            skill_id=skill_id,
            skill_name=skill_name,
            skill_md_content=skill_md_content,
            manifest=manifest,
        )
        
        # Extract code blocks from SKILL.md
        if skill_md_content:
            package.code_blocks = self._extract_code_blocks(skill_md_content)
            self.logger.info(
                f"Extracted {len(package.code_blocks)} code blocks from SKILL.md",
                extra={
                    'skill_id': str(skill_id),
                    'skill_name': skill_name,
                }
            )
        
        # Use pre-loaded package files when available to avoid repeated MinIO downloads.
        if package_files is not None:
            package.package_files = dict(package_files)
            self.logger.info(
                f"Loaded {len(package.package_files)} files from preloaded package files",
                extra={
                    'skill_id': str(skill_id),
                    'skill_name': skill_name,
                }
            )
        # Fallback: load package files from MinIO when storage path is available.
        elif storage_path:
            package.package_files = self._load_package_files(storage_path)
            self.logger.info(
                f"Loaded {len(package.package_files)} files from package",
                extra={
                    'skill_id': str(skill_id),
                    'storage_path': storage_path,
                }
            )
        
        return package
    
    def _extract_code_blocks(self, markdown_content: str) -> List[SkillCode]:
        """Extract code blocks from markdown content.
        
        Supports both fenced code blocks (```) and indented code blocks.
        
        Args:
            markdown_content: Markdown content with code blocks
            
        Returns:
            List of SkillCode objects
        """
        code_blocks = []
        
        # Pattern for fenced code blocks with language
        # Matches: ```python\ncode\n``` or ```python filename.py\ncode\n```
        # The filename must not contain newlines and should be a valid filename pattern
        fenced_pattern = r'```(\w+)(?:\s+([^\n]+?\.[\w]+))?\s*\n(.*?)\n```'
        
        for match in re.finditer(fenced_pattern, markdown_content, re.DOTALL):
            language = match.group(1)
            filename = match.group(2).strip() if match.group(2) else None
            code = match.group(3)
            
            # Skip empty code blocks
            if not code or not code.strip():
                continue
            
            # Extract description from preceding text (if any)
            start_pos = match.start()
            preceding_text = markdown_content[max(0, start_pos - 200):start_pos]
            description = self._extract_description(preceding_text)
            
            # Determine if code is executable (not just examples)
            is_executable = self._is_executable_code(code, language)
            
            code_blocks.append(SkillCode(
                language=language,
                code=code,
                filename=filename,
                description=description,
                is_executable=is_executable,
            ))
        
        return code_blocks
    
    def _extract_description(self, preceding_text: str) -> Optional[str]:
        """Extract description from text preceding a code block.
        
        Args:
            preceding_text: Text before the code block
            
        Returns:
            Description string or None
        """
        # Look for the last paragraph or heading before the code block
        lines = preceding_text.strip().split('\n')
        
        # Get the last non-empty line
        for line in reversed(lines):
            line = line.strip()
            if line and not line.startswith('```'):
                # Remove markdown formatting
                line = re.sub(r'[#*_`]', '', line)
                return line.strip()
        
        return None
    
    def _is_executable_code(self, code: str, language: str) -> bool:
        """Determine if code block is executable (not just an example).
        
        Args:
            code: Code content
            language: Programming language
            
        Returns:
            True if code appears to be executable
        """
        # Code blocks with certain patterns are likely examples, not executable
        example_indicators = [
            '# Example:',
            '# Example usage:',
            '// Example:',
            '// Example usage:',
            'Example:',
            'Usage:',
            '...',  # Ellipsis indicating incomplete code
        ]
        
        code_lower = code.lower()
        for indicator in example_indicators:
            if indicator.lower() in code_lower:
                return False
        
        # Very short code blocks are likely examples
        lines = code.strip().split('\n')
        if len(lines) < 2:
            return False
        
        # Code with imports and function definitions is likely executable
        if language in ['python', 'py']:
            # Has function or class definition
            if 'def ' in code or 'class ' in code:
                return True
            # Has imports
            if 'import ' in code or 'from ' in code:
                if '__name__' in code:
                    return True
        
        elif language in ['javascript', 'js', 'typescript', 'ts']:
            if 'import ' in code or 'require(' in code:
                if 'function ' in code or 'const ' in code or 'export ' in code:
                    return True
        
        elif language in ['bash', 'sh', 'shell']:
            # Bash code with shebang or multiple commands is executable
            if code.strip().startswith('#!'):
                return True
            if 'function ' in code:
                return True
            # Multiple lines of bash commands (not just one-liners)
            if len(lines) >= 3:
                return True
        
        # Default to executable if it looks substantial
        return len(lines) >= 5
    
    def _load_package_files(self, storage_path: str) -> Dict[str, str]:
        """Load files from MinIO package storage.
        
        Args:
            storage_path: MinIO storage path
            
        Returns:
            Dictionary mapping filename to content
        """
        package_files: Dict[str, str] = {}
        tmp_path: Optional[Path] = None
        file_stream = None

        try:
            from object_storage.minio_client import get_minio_client

            minio_client = get_minio_client()
            bucket_name = minio_client.buckets.get("artifacts", "agent-artifacts")
            object_key = storage_path
            if object_key.startswith(f"{bucket_name}/"):
                object_key = object_key[len(bucket_name) + 1:]

            file_stream, _ = minio_client.download_file(bucket_name, object_key)

            with tempfile.NamedTemporaryFile(delete=False, suffix=".skillpkg") as tmp_file:
                tmp_file.write(file_stream.read())
                tmp_file.flush()
                tmp_path = Path(tmp_file.name)

            with tempfile.TemporaryDirectory() as extract_dir:
                extract_path = Path(extract_dir)

                try:
                    with zipfile.ZipFile(tmp_path, "r") as zip_ref:
                        zip_ref.extractall(extract_path)
                except zipfile.BadZipFile:
                    with tarfile.open(tmp_path, "r:gz") as tar_ref:
                        tar_ref.extractall(extract_path)

                relevant_extensions = {".py", ".yaml", ".yml", ".json", ".txt", ".md"}
                for file_path in extract_path.rglob("*"):
                    if not file_path.is_file():
                        continue
                    if file_path.suffix.lower() not in relevant_extensions:
                        continue

                    relative_path = file_path.relative_to(extract_path)
                    if (
                        "__pycache__" in relative_path.parts
                        or any(part.startswith("__") for part in relative_path.parts)
                        or any(part.startswith(".") for part in relative_path.parts)
                        or file_path.name.startswith(".")
                    ):
                        continue

                    try:
                        content = file_path.read_text(encoding="utf-8")
                    except UnicodeDecodeError:
                        content = file_path.read_text(encoding="utf-8", errors="replace")

                    package_files[str(relative_path)] = content

        except Exception as e:
            self.logger.warning(
                "Failed to load package files from MinIO",
                extra={"storage_path": storage_path, "error": str(e)},
            )
        finally:
            try:
                if file_stream is not None:
                    file_stream.close()
            except Exception:
                pass
            if tmp_path:
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass

        return package_files
    
    def get_code_by_language(
        self,
        skill_package: SkillPackage,
        language: str,
    ) -> List[SkillCode]:
        """Get all code blocks for a specific language.
        
        Args:
            skill_package: SkillPackage to search
            language: Programming language
            
        Returns:
            List of SkillCode objects
        """
        return skill_package.get_code_by_language(language)


# Singleton instance
_skill_loader: Optional[SkillLoader] = None


def get_skill_loader() -> SkillLoader:
    """Get or create the skill loader singleton.
    
    Returns:
        SkillLoader instance
    """
    global _skill_loader
    if _skill_loader is None:
        _skill_loader = SkillLoader()
    return _skill_loader
