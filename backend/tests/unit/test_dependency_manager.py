"""Tests for dependency management system.

Tests cover:
- Dependency detection from code
- Cache management
- Install script generation
- Integration with code execution
"""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from virtualization.dependency_manager import (
    DependencyCache,
    DependencyDetector,
    DependencyInfo,
    DependencyManager,
)


class TestDependencyInfo:
    """Test DependencyInfo dataclass."""

    def test_create_dependency_info(self):
        """Test creating dependency info."""
        dep = DependencyInfo(name="requests", version="2.28.0", language="python")

        assert dep.name == "requests"
        assert dep.version == "2.28.0"
        assert dep.language == "python"

    def test_to_requirement_with_version(self):
        """Test converting to requirement string with version."""
        dep = DependencyInfo(name="requests", version="2.28.0", language="python")

        assert dep.to_requirement() == "requests==2.28.0"

    def test_to_requirement_without_version(self):
        """Test converting to requirement string without version."""
        dep = DependencyInfo(name="requests", language="python")

        assert dep.to_requirement() == "requests"

    def test_dependency_hashable(self):
        """Test that dependencies can be used in sets."""
        dep1 = DependencyInfo(name="requests", version="2.28.0", language="python")
        dep2 = DependencyInfo(name="requests", version="2.28.0", language="python")
        dep3 = DependencyInfo(name="flask", version="2.0.0", language="python")

        deps = {dep1, dep2, dep3}
        assert len(deps) == 2  # dep1 and dep2 are the same


class TestDependencyCache:
    """Test DependencyCache dataclass."""

    def test_cache_not_expired(self):
        """Test cache entry not expired."""
        deps = {DependencyInfo(name="requests", language="python")}
        cache = DependencyCache(
            dependencies=deps,
            installed_at=datetime.now(),
            cache_key="abc123",
        )

        assert not cache.is_expired(ttl_hours=24)

    def test_cache_expired(self):
        """Test cache entry expired."""
        deps = {DependencyInfo(name="requests", language="python")}
        cache = DependencyCache(
            dependencies=deps,
            installed_at=datetime.now() - timedelta(hours=25),
            cache_key="abc123",
        )

        assert cache.is_expired(ttl_hours=24)


class TestDependencyDetector:
    """Test dependency detection from code."""

    def setup_method(self):
        """Set up test fixtures."""
        self.detector = DependencyDetector()

    def test_detect_python_import(self):
        """Test detecting Python import statements."""
        code = """
import requests
import json
"""
        deps = self.detector.detect_python_dependencies(code)

        # json is stdlib, should be filtered out
        assert len(deps) == 1
        assert any(dep.name == "requests" for dep in deps)

    def test_detect_python_from_import(self):
        """Test detecting Python from-import statements."""
        code = """
from flask import Flask
from datetime import datetime
"""
        deps = self.detector.detect_python_dependencies(code)

        # datetime is stdlib, should be filtered out
        assert len(deps) == 1
        assert any(dep.name == "flask" for dep in deps)

    def test_detect_python_submodule_import(self):
        """Test detecting submodule imports."""
        code = """
from requests.auth import HTTPBasicAuth
import numpy.random
"""
        deps = self.detector.detect_python_dependencies(code)

        assert len(deps) == 2
        assert any(dep.name == "requests" for dep in deps)
        assert any(dep.name == "numpy" for dep in deps)

    def test_detect_python_stdlib_filtered(self):
        """Test that stdlib modules are filtered out."""
        code = """
import os
import sys
import json
import datetime
import asyncio
"""
        deps = self.detector.detect_python_dependencies(code)

        # All are stdlib, should be empty
        assert len(deps) == 0

    def test_detect_python_syntax_error(self):
        """Test handling syntax errors gracefully."""
        code = """
import requests
def broken(
"""
        deps = self.detector.detect_python_dependencies(code)

        # Should return empty set, not crash
        assert len(deps) == 0

    def test_detect_javascript_import(self):
        """Test detecting JavaScript import statements."""
        code = """
import express from 'express';
import { Router } from 'express';
import axios from 'axios';
"""
        deps = self.detector.detect_javascript_dependencies(code)

        assert len(deps) == 2
        assert any(dep.name == "express" for dep in deps)
        assert any(dep.name == "axios" for dep in deps)

    def test_detect_javascript_require(self):
        """Test detecting JavaScript require statements."""
        code = """
const express = require('express');
const axios = require('axios');
"""
        deps = self.detector.detect_javascript_dependencies(code)

        assert len(deps) == 2
        assert any(dep.name == "express" for dep in deps)
        assert any(dep.name == "axios" for dep in deps)

    def test_detect_javascript_relative_imports_filtered(self):
        """Test that relative imports are filtered out."""
        code = """
import express from 'express';
import utils from './utils';
import config from '../config';
"""
        deps = self.detector.detect_javascript_dependencies(code)

        # Only express should be detected
        assert len(deps) == 1
        assert any(dep.name == "express" for dep in deps)

    def test_detect_dependencies_python(self):
        """Test generic detect_dependencies for Python."""
        code = "import requests"
        deps = self.detector.detect_dependencies(code, "python")

        assert len(deps) == 1
        assert any(dep.name == "requests" for dep in deps)

    def test_detect_dependencies_javascript(self):
        """Test generic detect_dependencies for JavaScript."""
        code = "import express from 'express';"
        deps = self.detector.detect_dependencies(code, "javascript")

        assert len(deps) == 1
        assert any(dep.name == "express" for dep in deps)

    def test_detect_dependencies_unsupported_language(self):
        """Test detecting dependencies for unsupported language."""
        code = "some code"
        deps = self.detector.detect_dependencies(code, "ruby")

        # Should return empty set
        assert len(deps) == 0


class TestDependencyManager:
    """Test dependency manager."""

    def setup_method(self):
        """Set up test fixtures."""
        # Use temporary directory for cache
        self.temp_dir = tempfile.mkdtemp()
        self.manager = DependencyManager(
            cache_dir=self.temp_dir,
            cache_ttl_hours=24,
        )

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_dependencies_from_code(self):
        """Test getting dependencies from code."""
        code = """
import requests
import flask
"""
        deps = self.manager.get_dependencies(code, "python")

        assert len(deps) == 2
        assert any(dep.name == "requests" for dep in deps)
        assert any(dep.name == "flask" for dep in deps)

    def test_get_dependencies_with_explicit(self):
        """Test getting dependencies with explicit list."""
        code = "import requests"
        explicit = ["flask==2.0.0", "numpy"]

        deps = self.manager.get_dependencies(code, "python", explicit_deps=explicit)

        assert len(deps) == 3
        assert any(dep.name == "requests" for dep in deps)
        assert any(dep.name == "flask" and dep.version == "2.0.0" for dep in deps)
        assert any(dep.name == "numpy" for dep in deps)

    def test_get_cache_key_consistent(self):
        """Test that cache key is consistent for same dependencies."""
        deps1 = {
            DependencyInfo(name="requests", version="2.28.0", language="python"),
            DependencyInfo(name="flask", version="2.0.0", language="python"),
        }
        deps2 = {
            DependencyInfo(name="flask", version="2.0.0", language="python"),
            DependencyInfo(name="requests", version="2.28.0", language="python"),
        }

        key1 = self.manager.get_cache_key(deps1)
        key2 = self.manager.get_cache_key(deps2)

        # Order shouldn't matter
        assert key1 == key2

    def test_get_cache_key_different(self):
        """Test that cache key is different for different dependencies."""
        deps1 = {DependencyInfo(name="requests", version="2.28.0", language="python")}
        deps2 = {DependencyInfo(name="flask", version="2.0.0", language="python")}

        key1 = self.manager.get_cache_key(deps1)
        key2 = self.manager.get_cache_key(deps2)

        assert key1 != key2

    def test_cache_dependencies(self):
        """Test caching dependencies."""
        deps = {DependencyInfo(name="requests", language="python")}

        self.manager.cache_dependencies(deps, image_tag="test:latest")

        cache_key = self.manager.get_cache_key(deps)
        assert cache_key in self.manager.cache
        assert self.manager.cache[cache_key].image_tag == "test:latest"

    def test_is_cached_true(self):
        """Test checking if dependencies are cached."""
        deps = {DependencyInfo(name="requests", language="python")}

        self.manager.cache_dependencies(deps)

        assert self.manager.is_cached(deps)

    def test_is_cached_false(self):
        """Test checking if dependencies are not cached."""
        deps = {DependencyInfo(name="requests", language="python")}

        assert not self.manager.is_cached(deps)

    def test_is_cached_expired(self):
        """Test that expired cache returns False."""
        deps = {DependencyInfo(name="requests", language="python")}

        # Cache with expired timestamp
        cache_key = self.manager.get_cache_key(deps)
        self.manager.cache[cache_key] = DependencyCache(
            dependencies=deps,
            installed_at=datetime.now() - timedelta(hours=25),
            cache_key=cache_key,
        )

        assert not self.manager.is_cached(deps)
        # Expired entry should be removed
        assert cache_key not in self.manager.cache

    def test_get_cached_image(self):
        """Test getting cached image tag."""
        deps = {DependencyInfo(name="requests", language="python")}

        self.manager.cache_dependencies(deps, image_tag="test:latest")

        image_tag = self.manager.get_cached_image(deps)
        assert image_tag == "test:latest"

    def test_get_cached_image_not_found(self):
        """Test getting cached image when not cached."""
        deps = {DependencyInfo(name="requests", language="python")}

        image_tag = self.manager.get_cached_image(deps)
        assert image_tag is None

    def test_build_dependency_image_tag(self):
        """Test deterministic dependency image tag generation."""
        deps = {DependencyInfo(name="requests", language="python")}

        image_tag = self.manager.build_dependency_image_tag(deps, "python")

        assert image_tag.startswith("linx/code-exec-deps:python-")
        assert len(image_tag.split("-", 1)[-1]) >= 8

    def test_generate_python_install_script(self):
        """Test generating Python install script."""
        deps = {
            DependencyInfo(name="requests", version="2.28.0", language="python"),
            DependencyInfo(name="flask", language="python"),
        }

        script = self.manager.generate_install_script(deps, "python")

        assert "pip install" in script
        assert "requests==2.28.0" in script
        assert "flask" in script
        assert "--no-cache-dir" not in script

    def test_generate_node_install_script(self):
        """Test generating Node.js install script."""
        deps = {
            DependencyInfo(name="express", version="4.18.0", language="javascript"),
            DependencyInfo(name="axios", language="javascript"),
        }

        script = self.manager.generate_install_script(deps, "javascript")

        assert "npm install" in script
        assert "express==4.18.0" in script
        assert "axios" in script

    def test_generate_install_script_empty(self):
        """Test generating install script with no dependencies."""
        deps = set()

        script = self.manager.generate_install_script(deps, "python")

        assert script == ""

    def test_generate_install_script_wrong_language(self):
        """Test generating install script filters by language."""
        deps = {
            DependencyInfo(name="requests", language="python"),
            DependencyInfo(name="express", language="javascript"),
        }

        script = self.manager.generate_install_script(deps, "python")

        assert "requests" in script
        assert "express" not in script

    def test_cache_persistence(self):
        """Test that cache is persisted to disk."""
        deps = {DependencyInfo(name="requests", language="python")}

        self.manager.cache_dependencies(deps, image_tag="test:latest")

        # Create new manager with same cache dir
        new_manager = DependencyManager(cache_dir=self.temp_dir)

        # Should load cache from disk
        assert new_manager.is_cached(deps)
        assert new_manager.get_cached_image(deps) == "test:latest"

    def test_clear_expired_cache(self):
        """Test clearing expired cache entries."""
        deps1 = {DependencyInfo(name="requests", language="python")}
        deps2 = {DependencyInfo(name="flask", language="python")}

        # Cache one with expired timestamp
        cache_key1 = self.manager.get_cache_key(deps1)
        self.manager.cache[cache_key1] = DependencyCache(
            dependencies=deps1,
            installed_at=datetime.now() - timedelta(hours=25),
            cache_key=cache_key1,
        )

        # Cache one with valid timestamp
        self.manager.cache_dependencies(deps2)

        # Clear expired
        self.manager.clear_expired_cache()

        # Only valid entry should remain
        assert not self.manager.is_cached(deps1)
        assert self.manager.is_cached(deps2)


class TestDependencyManagerIntegration:
    """Integration tests for dependency manager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = DependencyManager(cache_dir=self.temp_dir)

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_full_workflow_python(self):
        """Test full workflow for Python code."""
        code = """
import requests
import flask
from numpy import array
"""
        # 1. Get dependencies
        deps = self.manager.get_dependencies(code, "python")
        assert len(deps) == 3

        # 2. Check cache (should be empty)
        assert not self.manager.is_cached(deps)

        # 3. Generate install script
        script = self.manager.generate_install_script(deps, "python")
        assert "pip install" in script
        assert "requests" in script

        # 4. Cache dependencies
        self.manager.cache_dependencies(deps, image_tag="python:deps-abc123")

        # 5. Check cache (should be cached now)
        assert self.manager.is_cached(deps)
        assert self.manager.get_cached_image(deps) == "python:deps-abc123"

    def test_full_workflow_javascript(self):
        """Test full workflow for JavaScript code."""
        code = """
import express from 'express';
const axios = require('axios');
"""
        # 1. Get dependencies
        deps = self.manager.get_dependencies(code, "javascript")
        assert len(deps) == 2

        # 2. Generate install script
        script = self.manager.generate_install_script(deps, "javascript")
        assert "npm install" in script

        # 3. Cache and verify
        self.manager.cache_dependencies(deps)
        assert self.manager.is_cached(deps)
