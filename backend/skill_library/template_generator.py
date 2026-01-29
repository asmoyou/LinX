"""
Agent Skill Template Generator.

Generates downloadable template packages for agent skills.
"""

import io
import zipfile
from pathlib import Path
from typing import BinaryIO


def generate_agent_skill_template() -> bytes:
    """
    Generate a ZIP package containing the agent skill template.
    
    Returns:
        bytes: ZIP file content
    """
    template_dir = Path(__file__).parent / "templates" / "agent_skill_template"
    
    # Create in-memory ZIP file
    buffer = io.BytesIO()
    
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add all files from template directory
        if template_dir.exists():
            for file_path in template_dir.rglob('*'):
                if file_path.is_file():
                    # Get relative path for archive
                    arcname = file_path.relative_to(template_dir)
                    zf.write(file_path, arcname)
        else:
            # Fallback: Create template inline if directory doesn't exist
            _create_inline_template(zf)
    
    buffer.seek(0)
    return buffer.read()


def _create_inline_template(zf: zipfile.ZipFile) -> None:
    """
    Create template files inline if template directory doesn't exist.
    
    Args:
        zf: ZipFile object to write to
    """
    # SKILL.md
    skill_md = """---
name: My Custom Skill
emoji: ⚡
version: 1.0.0
author: Your Name
homepage: https://github.com/yourusername/my-skill
description: Brief description of what this skill does
tags:
  - custom
  - example
gating:
  binaries:
    - curl
    - python3
  env_vars:
    - MY_API_KEY
metadata:
  category: general
  difficulty: beginner
---

# My Custom Skill

Describe what your skill does and how to use it.

## Usage Examples

### Example 1: Basic Usage

```bash
curl "https://api.example.com/endpoint?key=${MY_API_KEY}"
```

### Example 2: Using Python Script

```bash
python3 {baseDir}/scripts/helper.py --query "example"
```

### Example 3: Advanced Usage

```bash
curl -X POST "https://api.example.com/data" \\
  -H "Authorization: Bearer ${MY_API_KEY}" \\
  -d '{"query": "example"}'
```

## Natural Language Testing

Test with queries like:
- "Run my custom skill"
- "Execute the example command"

## Configuration

Required environment variables:
- `MY_API_KEY`: Your API key

Set it in your environment:

```bash
export MY_API_KEY=your_api_key_here
```

## Package Contents

- **SKILL.md**: This file - natural language instructions
- **scripts/**: Executable scripts (Python, Shell, etc.)
- **references/**: Reference documentation (optional)
- **requirements.txt**: Python dependencies (if using Python)

## Notes

Add any additional notes or documentation here.
"""
    zf.writestr('SKILL.md', skill_md)
    
    # README.md
    readme = """# My Custom Skill

A template for creating agent skills in LinX.

## Quick Start

1. Modify `SKILL.md` with your skill definition
2. Add executable scripts to `scripts/` directory
3. Update gating requirements as needed
4. Add usage examples and documentation
5. Zip the package and upload to LinX

## Package Structure

### Simple Script Mode (Recommended for most skills)

```
my-skill/
├── SKILL.md              # Main skill definition (required)
├── README.md             # Documentation (optional)
├── requirements.txt      # Python dependencies (if using Python)
├── scripts/              # Executable scripts
│   ├── helper.py
│   └── utils.py
└── references/           # Reference documentation (optional)
    └── api-docs.md
```

### Complete Package Mode (For complex skills)

```
my-skill/
├── SKILL.md              # Main skill definition (required)
├── README.md             # Documentation (optional)
├── pyproject.toml        # Python package configuration
├── src/                  # Complete Python package
│   └── my_skill/
│       ├── __init__.py
│       ├── main.py
│       └── utils.py
└── references/           # Reference documentation (optional)
    └── api-docs.md
```

### Mixed Mode (For multiple tool types)

```
my-skill/
├── SKILL.md              # Main skill definition (required)
├── README.md             # Documentation (optional)
├── requirements.txt      # Python dependencies
├── scripts/              # Simple scripts
│   └── quick_check.py
├── src/                  # Complex package
│   └── my_skill/
│       └── api.py
└── references/           # Reference documentation
    └── api-docs.md
```

## SKILL.md Format

The SKILL.md file uses:
- **YAML Frontmatter**: Metadata (name, version, gating, etc.)
- **Markdown Body**: Natural language instructions and examples

### Key Concepts

- **SKILL.md**: Instructions on HOW to use the tools
- **scripts/**: Executable code that agents call
- **{baseDir}**: Placeholder for skill package directory path

## Configuration

Use environment variables for configuration instead of config files:

```bash
export MY_API_KEY=your_key
export MY_API_URL=https://api.example.com
```

## Testing

Test your skill with natural language queries in the LinX UI.

## Documentation

- [LinX Documentation](https://docs.linx.ai)
- [AgentSkills.io Standard](https://agentskills.io)
- [Moltbot Skills Reference](https://github.com/moltbot/skills)
"""
    zf.writestr('README.md', readme)
    
    # Example Python script
    helper_script = """#!/usr/bin/env python3
\"\"\"
Example helper script for agent skill.

This script demonstrates how to create executable tools for agent skills.
\"\"\"

import os
import sys
import argparse


def main():
    \"\"\"Main entry point.\"\"\"
    parser = argparse.ArgumentParser(description="Example helper script")
    parser.add_argument("--query", "-q", required=True, help="Query to process")
    parser.add_argument("--format", "-f", default="text", 
                       choices=["text", "json"], help="Output format")
    
    args = parser.parse_args()
    
    # Get API key from environment
    api_key = os.environ.get('MY_API_KEY')
    if not api_key:
        print("Error: MY_API_KEY environment variable not set", file=sys.stderr)
        return 1
    
    # Process query
    print(f"Processing query: {args.query}")
    print(f"Format: {args.format}")
    
    # Your implementation here
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
"""
    zf.writestr('scripts/helper.py', helper_script)
    
    # requirements.txt
    requirements = """# Python dependencies
requests>=2.31.0
"""
    zf.writestr('requirements.txt', requirements)
    
    # references/.gitkeep
    gitkeep = """# This directory is for reference documentation
# Add API docs, guides, or other reference materials here
"""
    zf.writestr('references/.gitkeep', gitkeep)


def get_template_info() -> dict:
    """
    Get information about available templates.
    
    Returns:
        dict: Template information
    """
    return {
        "name": "Agent Skill Template",
        "description": "Standard template for creating agent skills with SKILL.md format and executable code",
        "version": "2.0.0",
        "structure": {
            "simple_script": {
                "description": "Simple scripts mode (recommended for most skills)",
                "files": [
                    "SKILL.md (required)",
                    "scripts/ (executable scripts)",
                    "requirements.txt (optional)",
                    "references/ (optional)",
                    "README.md (optional)"
                ]
            },
            "complete_package": {
                "description": "Complete Python package mode (for complex skills)",
                "files": [
                    "SKILL.md (required)",
                    "src/ (Python package)",
                    "pyproject.toml (package config)",
                    "references/ (optional)",
                    "README.md (optional)"
                ]
            },
            "mixed": {
                "description": "Mixed mode (scripts + package)",
                "files": [
                    "SKILL.md (required)",
                    "scripts/ (simple scripts)",
                    "src/ (complex package)",
                    "requirements.txt (optional)",
                    "references/ (optional)",
                    "README.md (optional)"
                ]
            }
        },
        "key_concepts": {
            "skill_md": "Instructions on HOW to use the tools",
            "executable_code": "Tools that agents call (scripts/, src/)",
            "base_dir": "Use {baseDir} placeholder for skill package path"
        },
        "format": "AgentSkills.io standard",
        "documentation": "https://agentskills.io",
        "examples": [
            "Moltbot: openai-image-gen (simple script)",
            "Moltbot: local-places (complete package)",
            "Moltbot: bitwarden (mixed mode)"
        ]
    }
