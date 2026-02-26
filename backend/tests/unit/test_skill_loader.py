"""Tests for SkillLoader.

Tests cover:
- Code block extraction from markdown
- Language detection and normalization
- Executable code identification
- SkillPackage creation and querying
"""

import pytest
from uuid import uuid4

from skill_library.skill_loader import SkillCode, SkillLoader, SkillPackage, get_skill_loader


class TestSkillCode:
    """Test SkillCode dataclass."""
    
    def test_language_normalization(self):
        """Test language name normalization."""
        # Python variants
        code1 = SkillCode(language='py', code='print("hello")')
        assert code1.language == 'python'
        
        code2 = SkillCode(language='Python', code='print("hello")')
        assert code2.language == 'python'
        
        # JavaScript variants
        code3 = SkillCode(language='js', code='console.log("hello")')
        assert code3.language == 'javascript'
        
        # Bash variants
        code4 = SkillCode(language='sh', code='echo hello')
        assert code4.language == 'bash'
        
        code5 = SkillCode(language='shell', code='echo hello')
        assert code5.language == 'bash'
    
    def test_default_values(self):
        """Test default values."""
        code = SkillCode(language='python', code='print("test")')
        assert code.filename is None
        assert code.description is None
        assert code.is_executable is True


class TestSkillPackage:
    """Test SkillPackage dataclass."""
    
    def test_get_code_by_language(self):
        """Test filtering code by language."""
        skill_id = uuid4()
        package = SkillPackage(
            skill_id=skill_id,
            skill_name='test_skill',
            code_blocks=[
                SkillCode(language='python', code='print("hello")'),
                SkillCode(language='python', code='print("world")'),
                SkillCode(language='bash', code='echo hello'),
            ]
        )
        
        python_codes = package.get_code_by_language('python')
        assert len(python_codes) == 2
        assert all(c.language == 'python' for c in python_codes)
        
        bash_codes = package.get_code_by_language('bash')
        assert len(bash_codes) == 1
        assert bash_codes[0].language == 'bash'
        
        js_codes = package.get_code_by_language('javascript')
        assert len(js_codes) == 0
    
    def test_get_executable_code(self):
        """Test getting first executable code."""
        skill_id = uuid4()
        package = SkillPackage(
            skill_id=skill_id,
            skill_name='test_skill',
            code_blocks=[
                SkillCode(language='python', code='# Example', is_executable=False),
                SkillCode(language='python', code='print("hello")', is_executable=True),
                SkillCode(language='python', code='print("world")', is_executable=True),
            ]
        )
        
        code = package.get_executable_code('python')
        assert code == 'print("hello")'
    
    def test_get_all_executable_code(self):
        """Test getting all executable code concatenated."""
        skill_id = uuid4()
        package = SkillPackage(
            skill_id=skill_id,
            skill_name='test_skill',
            code_blocks=[
                SkillCode(language='python', code='# Example', is_executable=False),
                SkillCode(language='python', code='print("hello")', is_executable=True),
                SkillCode(language='python', code='print("world")', is_executable=True),
            ]
        )
        
        code = package.get_all_executable_code('python')
        assert 'print("hello")' in code
        assert 'print("world")' in code
        assert '# Example' not in code


class TestSkillLoader:
    """Test SkillLoader class."""
    
    def test_singleton(self):
        """Test singleton pattern."""
        loader1 = get_skill_loader()
        loader2 = get_skill_loader()
        assert loader1 is loader2
    
    def test_extract_fenced_code_blocks(self):
        """Test extracting fenced code blocks."""
        loader = SkillLoader()
        
        markdown = """
# Test Skill

This is a test skill.

```python
def hello():
    print("Hello, World!")
```

Some text here.

```bash
echo "Hello from bash"
```
"""
        
        code_blocks = loader._extract_code_blocks(markdown)
        
        assert len(code_blocks) == 2
        assert code_blocks[0].language == 'python'
        assert 'def hello()' in code_blocks[0].code
        assert code_blocks[1].language == 'bash'
        assert 'echo' in code_blocks[1].code
    
    def test_extract_code_with_filename(self):
        """Test extracting code blocks with filenames."""
        loader = SkillLoader()
        
        markdown = """
```python main.py
def main():
    print("Hello")
```
"""
        
        code_blocks = loader._extract_code_blocks(markdown)
        
        assert len(code_blocks) == 1
        assert code_blocks[0].filename == 'main.py'
        assert 'def main()' in code_blocks[0].code
    
    def test_is_executable_code_python(self):
        """Test identifying executable Python code."""
        loader = SkillLoader()
        
        # Executable code
        executable = """
import os

def main():
    print("Hello")
    
if __name__ == "__main__":
    main()
"""
        assert loader._is_executable_code(executable, 'python') is True
        
        # Example code (not executable)
        example = """
# Example:
print("hello")
"""
        assert loader._is_executable_code(example, 'python') is False
        
        # Too short
        short = "print('hi')"
        assert loader._is_executable_code(short, 'python') is False
    
    def test_is_executable_code_bash(self):
        """Test identifying executable Bash code."""
        loader = SkillLoader()
        
        # Executable code with shebang
        executable = """
#!/bin/bash
echo "Hello"
ls -la
"""
        assert loader._is_executable_code(executable, 'bash') is True
        
        # Executable code with function
        executable2 = """
function greet() {
    echo "Hello, $1"
}
greet "World"
"""
        assert loader._is_executable_code(executable2, 'bash') is True
    
    def test_load_skill_with_markdown(self):
        """Test loading skill with markdown content."""
        loader = SkillLoader()
        skill_id = uuid4()
        
        markdown = """
# Weather Skill

Get weather information.

```python
import requests

def get_weather(city):
    # API call here
    return {"temp": 72, "city": city}
```
"""
        
        package = loader.load_skill(
            skill_id=skill_id,
            skill_name='weather',
            skill_md_content=markdown,
        )
        
        assert package.skill_id == skill_id
        assert package.skill_name == 'weather'
        assert len(package.code_blocks) == 1
        assert package.code_blocks[0].language == 'python'
        assert 'get_weather' in package.code_blocks[0].code
    
    def test_load_skill_without_markdown(self):
        """Test loading skill without markdown content."""
        loader = SkillLoader()
        skill_id = uuid4()
        
        package = loader.load_skill(
            skill_id=skill_id,
            skill_name='test_skill',
            skill_md_content=None,
        )
        
        assert package.skill_id == skill_id
        assert package.skill_name == 'test_skill'
        assert len(package.code_blocks) == 0

    def test_load_skill_prefers_preloaded_package_files(self, monkeypatch):
        """Test preloaded package files are used instead of fetching from storage."""
        loader = SkillLoader()
        skill_id = uuid4()
        preloaded_files = {
            "weather-forcast/SKILL.md": "# Weather Skill",
            "weather-forcast/scripts/weather_helper.py": "print('ok')",
        }

        called = False

        def _unexpected_load(_: str):
            nonlocal called
            called = True
            return {}

        monkeypatch.setattr(loader, "_load_package_files", _unexpected_load)

        package = loader.load_skill(
            skill_id=skill_id,
            skill_name="weather-forcast",
            skill_md_content=None,
            storage_path="system/weather-forcast.zip",
            package_files=preloaded_files,
        )

        assert package.package_files == preloaded_files
        assert called is False

    def test_load_package_files_from_zip_preserves_structure(self, monkeypatch):
        """Test ZIP package loading keeps original top-level folder structure."""
        import io
        import zipfile

        loader = SkillLoader()
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_ref:
            zip_ref.writestr("weather-forcast/SKILL.md", "# Weather Skill")
            zip_ref.writestr(
                "weather-forcast/scripts/weather_helper.py",
                "print('hello weather')\n",
            )
            zip_ref.writestr("weather-forcast/requirements.txt", "requests==2.31.0\n")
            zip_ref.writestr("weather-forcast/.DS_Store", "ignored")

        payload = zip_buffer.getvalue()

        class _FakeMinioClient:
            buckets = {"artifacts": "agent-artifacts"}

            def download_file(self, bucket_name: str, object_key: str):
                return io.BytesIO(payload), {}

        import object_storage.minio_client as minio_client_module

        monkeypatch.setattr(minio_client_module, "get_minio_client", lambda: _FakeMinioClient())

        package_files = loader._load_package_files("system/weather-forcast-1.0.0.zip")

        assert "weather-forcast/SKILL.md" in package_files
        assert "weather-forcast/scripts/weather_helper.py" in package_files
        assert "weather-forcast/requirements.txt" in package_files
        assert "weather-forcast/.DS_Store" not in package_files
    
    def test_extract_description(self):
        """Test extracting description from preceding text."""
        loader = SkillLoader()
        
        # With heading
        text1 = "## Installation\n\nInstall the package:\n\n"
        desc1 = loader._extract_description(text1)
        assert desc1 == "Install the package:"
        
        # With paragraph
        text2 = "This is a description.\n\n"
        desc2 = loader._extract_description(text2)
        assert desc2 == "This is a description."
        
        # Empty
        text3 = "\n\n"
        desc3 = loader._extract_description(text3)
        assert desc3 is None
    
    def test_complex_markdown_extraction(self):
        """Test extracting from complex markdown."""
        loader = SkillLoader()
        
        markdown = """
# Complex Skill

## Overview

This skill does multiple things.

### Python Implementation

Here's the main code:

```python main.py
import sys

def main(inputs):
    print(f"Processing: {inputs}")
    return {"status": "success"}

if __name__ == "__main__":
    main(sys.argv[1:])
```

### Helper Script

```python utils.py
def helper():
    return "helper"
```

### Example Usage

```python
# Example:
result = main({"test": "data"})
```

### Bash Script

```bash run.sh
#!/bin/bash
python main.py "$@"
```
"""
        
        code_blocks = loader._extract_code_blocks(markdown)
        
        # Should extract 4 code blocks
        assert len(code_blocks) == 4
        
        # Check languages
        languages = [cb.language for cb in code_blocks]
        assert languages.count('python') == 3
        assert languages.count('bash') == 1
        
        # Check filenames
        assert code_blocks[0].filename == 'main.py'
        assert code_blocks[1].filename == 'utils.py'
        assert code_blocks[3].filename == 'run.sh'
        
        # Check executable status
        # First two Python blocks should be executable
        assert code_blocks[0].is_executable is True
        assert code_blocks[1].is_executable is True
        # Example block should not be executable
        assert code_blocks[2].is_executable is False
        # Bash script should be executable
        assert code_blocks[3].is_executable is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
