"""Dependency Manager for code execution.

This module manages dependencies for code execution in sandboxes:
- Detects required packages from code
- Caches installed packages
- Installs dependencies on-demand
- Supports multiple languages (Python, Node.js, etc.)

References:
- Design: .kiro/specs/code-execution-improvement/design.md
"""

import ast
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class DependencyInfo:
    """Information about a dependency."""
    
    name: str
    version: Optional[str] = None
    language: str = "python"
    install_command: Optional[str] = None
    
    def __hash__(self):
        return hash((self.name, self.version, self.language))
    
    def to_requirement(self) -> str:
        """Convert to requirement string (e.g., 'requests==2.28.0')."""
        if self.version:
            return f"{self.name}=={self.version}"
        return self.name


@dataclass
class DependencyCache:
    """Cache entry for installed dependencies."""
    
    dependencies: Set[DependencyInfo]
    installed_at: datetime
    cache_key: str
    image_tag: Optional[str] = None  # Docker image with dependencies
    
    def is_expired(self, ttl_hours: int = 24) -> bool:
        """Check if cache entry is expired."""
        return datetime.now() - self.installed_at > timedelta(hours=ttl_hours)


class DependencyDetector:
    """Detects dependencies from code."""

    PYTHON_IMPORT_PACKAGE_ALIASES = {
        "docx": "python-docx",
        "pptx": "python-pptx",
        "cv2": "opencv-python",
        "yaml": "pyyaml",
        "pil": "pillow",
        "fitz": "pymupdf",
        "jwt": "pyjwt",
        "dateutil": "python-dateutil",
    }
    
    def __init__(self):
        """Initialize dependency detector."""
        self.logger = logging.getLogger(__name__)
    
    def detect_python_dependencies(self, code: str) -> Set[DependencyInfo]:
        """Detect Python dependencies from code.
        
        Args:
            code: Python source code
            
        Returns:
            Set of detected dependencies
        """
        dependencies = set()
        
        try:
            tree = ast.parse(code)
            
            for node in ast.walk(tree):
                # Import statements: import module
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module_name = alias.name.split('.')[0]
                        if not self._is_stdlib_module(module_name):
                            dependency_name = self._normalize_python_dependency(module_name)
                            dependencies.add(DependencyInfo(
                                name=dependency_name,
                                language='python'
                            ))
                
                # From imports: from module import something
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        module_name = node.module.split('.')[0]
                        if not self._is_stdlib_module(module_name):
                            dependency_name = self._normalize_python_dependency(module_name)
                            dependencies.add(DependencyInfo(
                                name=dependency_name,
                                language='python'
                            ))
        
        except SyntaxError as e:
            self.logger.warning(f"Failed to parse Python code: {e}")
        
        return dependencies

    def _normalize_python_dependency(self, module_name: str) -> str:
        """Map python import module names to pip package names when needed."""
        normalized = str(module_name or "").strip()
        if not normalized:
            return normalized
        return self.PYTHON_IMPORT_PACKAGE_ALIASES.get(normalized.lower(), normalized)
    
    def detect_javascript_dependencies(self, code: str) -> Set[DependencyInfo]:
        """Detect JavaScript/Node.js dependencies from code.
        
        Args:
            code: JavaScript source code
            
        Returns:
            Set of detected dependencies
        """
        dependencies = set()
        
        # Match: import ... from 'package'
        import_pattern = r"import\s+.*?\s+from\s+['\"]([^'\"]+)['\"]"
        # Match: require('package')
        require_pattern = r"require\(['\"]([^'\"]+)['\"]\)"
        
        for pattern in [import_pattern, require_pattern]:
            for match in re.finditer(pattern, code):
                package = match.group(1)
                # Skip relative imports
                if not package.startswith('.') and not package.startswith('/'):
                    dependencies.add(DependencyInfo(
                        name=package,
                        language='javascript'
                    ))
        
        return dependencies
    
    def detect_dependencies(self, code: str, language: str) -> Set[DependencyInfo]:
        """Detect dependencies for any language.
        
        Args:
            code: Source code
            language: Programming language
            
        Returns:
            Set of detected dependencies
        """
        language = language.lower()
        
        if language in ['python', 'py']:
            return self.detect_python_dependencies(code)
        elif language in ['javascript', 'js', 'typescript', 'ts']:
            return self.detect_javascript_dependencies(code)
        else:
            self.logger.warning(f"Dependency detection not supported for: {language}")
            return set()
    
    def _is_stdlib_module(self, module_name: str) -> bool:
        """Check if module is part of Python standard library.
        
        Args:
            module_name: Module name
            
        Returns:
            True if stdlib module
        """
        # Common stdlib modules (not exhaustive)
        stdlib_modules = {
            'os', 'sys', 'json', 'time', 'datetime', 'math', 'random',
            're', 'collections', 'itertools', 'functools', 'pathlib',
            'typing', 'dataclasses', 'enum', 'abc', 'io', 'logging',
            'unittest', 'asyncio', 'threading', 'multiprocessing',
            'subprocess', 'argparse', 'configparser', 'csv', 'xml',
            'html', 'http', 'urllib', 'email', 'base64', 'hashlib',
            'hmac', 'secrets', 'uuid', 'pickle', 'shelve', 'sqlite3',
            'gzip', 'zipfile', 'tarfile', 'tempfile', 'shutil', 'glob',
            'fnmatch', 'linecache', 'traceback', 'warnings', 'contextlib',
            'weakref', 'copy', 'pprint', 'textwrap', 'string', 'struct',
            'codecs', 'locale', 'gettext', 'decimal', 'fractions',
            'statistics', 'heapq', 'bisect', 'array', 'queue', 'socket',
            'ssl', 'select', 'selectors', 'signal', 'mmap', 'ctypes',
        }
        
        return module_name in stdlib_modules


class DependencyManager:
    """Manages dependencies for code execution."""
    
    def __init__(
        self,
        cache_dir: str = "/tmp/linx_dependency_cache",
        cache_ttl_hours: int = 24,
    ):
        """Initialize dependency manager.
        
        Args:
            cache_dir: Directory for caching dependency information
            cache_ttl_hours: Cache time-to-live in hours
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl_hours = cache_ttl_hours
        
        self.detector = DependencyDetector()
        self.cache: Dict[str, DependencyCache] = {}
        
        self.logger = logging.getLogger(__name__)
        self.logger.info(
            f"DependencyManager initialized with cache_dir={cache_dir}, "
            f"ttl={cache_ttl_hours}h"
        )
        
        # Load existing cache
        self._load_cache()
    
    def get_dependencies(
        self,
        code: str,
        language: str,
        explicit_deps: Optional[List[str]] = None,
    ) -> Set[DependencyInfo]:
        """Get all dependencies for code.
        
        Args:
            code: Source code
            language: Programming language
            explicit_deps: Explicitly specified dependencies
            
        Returns:
            Set of all dependencies
        """
        # Detect from code
        detected = self.detector.detect_dependencies(code, language)
        
        # Add explicit dependencies
        if explicit_deps:
            for dep in explicit_deps:
                # Parse version if specified (e.g., "requests==2.28.0")
                if '==' in dep:
                    name, version = dep.split('==', 1)
                    detected.add(DependencyInfo(
                        name=name.strip(),
                        version=version.strip(),
                        language=language
                    ))
                else:
                    detected.add(DependencyInfo(
                        name=dep.strip(),
                        language=language
                    ))
        
        return detected
    
    def get_cache_key(self, dependencies: Set[DependencyInfo]) -> str:
        """Generate cache key for dependencies.
        
        Args:
            dependencies: Set of dependencies
            
        Returns:
            Cache key (hash)
        """
        # Sort for consistent hashing
        sorted_deps = sorted(
            [dep.to_requirement() for dep in dependencies]
        )
        content = json.dumps(sorted_deps, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def is_cached(self, dependencies: Set[DependencyInfo]) -> bool:
        """Check if dependencies are cached.
        
        Args:
            dependencies: Set of dependencies
            
        Returns:
            True if cached and not expired
        """
        cache_key = self.get_cache_key(dependencies)
        
        if cache_key in self.cache:
            cache_entry = self.cache[cache_key]
            if not cache_entry.is_expired(self.cache_ttl_hours):
                return True
            else:
                # Remove expired entry
                del self.cache[cache_key]
                self._save_cache()
        
        return False
    
    def get_cached_image(self, dependencies: Set[DependencyInfo]) -> Optional[str]:
        """Get cached Docker image tag for dependencies.
        
        Args:
            dependencies: Set of dependencies
            
        Returns:
            Docker image tag or None
        """
        cache_key = self.get_cache_key(dependencies)
        
        if cache_key in self.cache:
            cache_entry = self.cache[cache_key]
            if not cache_entry.is_expired(self.cache_ttl_hours):
                return cache_entry.image_tag
        
        return None

    def build_dependency_image_tag(
        self,
        dependencies: Set[DependencyInfo],
        language: str,
    ) -> str:
        """Build deterministic Docker image tag for a dependency set."""
        cache_key = self.get_cache_key(dependencies)
        normalized_language = (language or "python").strip().lower()
        return f"linx/code-exec-deps:{normalized_language}-{cache_key}"
    
    def cache_dependencies(
        self,
        dependencies: Set[DependencyInfo],
        image_tag: Optional[str] = None,
    ):
        """Cache installed dependencies.
        
        Args:
            dependencies: Set of installed dependencies
            image_tag: Docker image tag with dependencies
        """
        cache_key = self.get_cache_key(dependencies)
        
        self.cache[cache_key] = DependencyCache(
            dependencies=dependencies,
            installed_at=datetime.now(),
            cache_key=cache_key,
            image_tag=image_tag,
        )
        
        self._save_cache()
        
        self.logger.info(
            f"Cached {len(dependencies)} dependencies with key={cache_key}"
        )
    
    def generate_install_script(
        self,
        dependencies: Set[DependencyInfo],
        language: str,
    ) -> str:
        """Generate installation script for dependencies.
        
        Args:
            dependencies: Set of dependencies to install
            language: Programming language
            
        Returns:
            Shell script to install dependencies
        """
        language = language.lower()
        
        if language in ['python', 'py']:
            return self._generate_python_install_script(dependencies)
        elif language in ['javascript', 'js', 'typescript', 'ts']:
            return self._generate_node_install_script(dependencies)
        else:
            return ""
    
    def _generate_python_install_script(
        self,
        dependencies: Set[DependencyInfo],
    ) -> str:
        """Generate Python pip install script.
        
        Args:
            dependencies: Python dependencies
            
        Returns:
            Shell script
        """
        if not dependencies:
            return ""
        
        # Filter Python dependencies
        python_deps = [
            dep for dep in dependencies
            if dep.language in ['python', 'py']
        ]
        
        if not python_deps:
            return ""
        
        requirements = [dep.to_requirement() for dep in python_deps]
        requirements.sort()

        script = f"""#!/bin/bash
set -e

echo "Installing Python dependencies..."

# Create requirements file
cat > /tmp/requirements.txt <<'EOF'
{chr(10).join(requirements)}
EOF

# Install with pip (pip -> pip3 -> python -m pip)
if command -v pip >/dev/null 2>&1; then
  pip install --disable-pip-version-check -r /tmp/requirements.txt
elif command -v pip3 >/dev/null 2>&1; then
  pip3 install --disable-pip-version-check -r /tmp/requirements.txt
elif command -v python3 >/dev/null 2>&1; then
  python3 -m pip install --disable-pip-version-check -r /tmp/requirements.txt
else
  python -m pip install --disable-pip-version-check -r /tmp/requirements.txt
fi

echo "Python dependencies installed successfully"
"""
        return script
    
    def _generate_node_install_script(
        self,
        dependencies: Set[DependencyInfo],
    ) -> str:
        """Generate Node.js npm install script.
        
        Args:
            dependencies: Node.js dependencies
            
        Returns:
            Shell script
        """
        if not dependencies:
            return ""
        
        # Filter JavaScript dependencies
        js_deps = [
            dep for dep in dependencies
            if dep.language in ['javascript', 'js', 'typescript', 'ts']
        ]
        
        if not js_deps:
            return ""
        
        packages = [dep.to_requirement() for dep in js_deps]
        
        script = f"""#!/bin/bash
set -e

echo "Installing Node.js dependencies..."

# Install with npm
npm install --no-save {' '.join(packages)}

echo "Node.js dependencies installed successfully"
"""
        return script
    
    def _load_cache(self):
        """Load cache from disk."""
        cache_file = self.cache_dir / "dependency_cache.json"
        
        if not cache_file.exists():
            return
        
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
            
            for cache_key, entry_data in data.items():
                # Reconstruct DependencyInfo objects
                dependencies = set()
                for dep_data in entry_data['dependencies']:
                    dependencies.add(DependencyInfo(
                        name=dep_data['name'],
                        version=dep_data.get('version'),
                        language=dep_data['language'],
                    ))
                
                self.cache[cache_key] = DependencyCache(
                    dependencies=dependencies,
                    installed_at=datetime.fromisoformat(entry_data['installed_at']),
                    cache_key=cache_key,
                    image_tag=entry_data.get('image_tag'),
                )
            
            self.logger.info(f"Loaded {len(self.cache)} cache entries")
        
        except Exception as e:
            self.logger.error(f"Failed to load cache: {e}")
    
    def _save_cache(self):
        """Save cache to disk."""
        cache_file = self.cache_dir / "dependency_cache.json"
        
        try:
            data = {}
            for cache_key, entry in self.cache.items():
                data[cache_key] = {
                    'dependencies': [
                        {
                            'name': dep.name,
                            'version': dep.version,
                            'language': dep.language,
                        }
                        for dep in entry.dependencies
                    ],
                    'installed_at': entry.installed_at.isoformat(),
                    'image_tag': entry.image_tag,
                }
            
            with open(cache_file, 'w') as f:
                json.dump(data, f, indent=2)
        
        except Exception as e:
            self.logger.error(f"Failed to save cache: {e}")
    
    def clear_expired_cache(self):
        """Remove expired cache entries."""
        expired_keys = [
            key for key, entry in self.cache.items()
            if entry.is_expired(self.cache_ttl_hours)
        ]
        
        for key in expired_keys:
            del self.cache[key]
        
        if expired_keys:
            self._save_cache()
            self.logger.info(f"Cleared {len(expired_keys)} expired cache entries")


# Singleton instance
_dependency_manager: Optional[DependencyManager] = None


def get_dependency_manager() -> DependencyManager:
    """Get or create the dependency manager singleton.
    
    Returns:
        DependencyManager instance
    """
    global _dependency_manager
    if _dependency_manager is None:
        _dependency_manager = DependencyManager()
    return _dependency_manager
