# Flexible Skill Architecture - Claude Code Style

## Overview

This document describes a highly flexible skill system inspired by Claude Code, supporting both simple LangChain tools and complex multi-file skill packages.

## Problem with Current Design

Current design only supports single-file Python functions with `@tool` decorator. This is too limited for:
- Complex skills requiring multiple files
- Skills with their own dependencies
- Skills needing configuration files
- Skills with data files or resources
- Skills that are entire mini-projects

## Claude Code Approach

Claude Code skills are:
1. **Project-Based**: Can be entire code projects with multiple files
2. **Self-Contained**: Have their own `requirements.txt`, config files, data
3. **Documented**: Include README.md explaining usage
4. **Flexible**: Can be simple functions or complex systems

## New Architecture

### Skill Types Hierarchy

```
Skill Types:
├── Simple Tool (LangChain @tool)
│   └── Single Python function
│       Example: calculator, simple API call
│
├── Code Module
│   └── Multiple Python files, single entry point
│       Example: data processor with helpers
│
└── Skill Package (Full Project)
    └── Complete project with dependencies, config, docs
        Example: web scraper with browser automation,
                 ML model with training pipeline,
                 Complex API integration
```

### Storage Structure

```
MinIO: skills-storage/
├── {skill_id}/
│   ├── skill.yaml              # Skill metadata and manifest
│   ├── README.md               # Documentation
│   ├── requirements.txt        # Python dependencies
│   ├── config.yaml             # Configuration template
│   ├── src/                    # Source code
│   │   ├── __init__.py
│   │   ├── main.py            # Entry point
│   │   ├── utils.py
│   │   └── ...
│   ├── data/                   # Data files
│   │   └── ...
│   ├── tests/                  # Tests
│   │   └── ...
│   └── .env.example           # Environment variables template
```

### Skill Manifest (skill.yaml)

```yaml
# Skill metadata
name: web_scraper_advanced
version: 1.0.0
type: skill_package  # simple_tool | code_module | skill_package
description: Advanced web scraper with JavaScript rendering

# Entry point
entry_point: src/main.py
function: scrape_website  # Function to call

# Interface definition
interface:
  inputs:
    - name: url
      type: string
      required: true
      description: URL to scrape
    - name: selectors
      type: dict
      required: false
      description: CSS selectors for data extraction
    - name: render_js
      type: boolean
      default: false
      description: Whether to render JavaScript
  outputs:
    - name: data
      type: dict
      description: Extracted data
    - name: metadata
      type: dict
      description: Scraping metadata

# Dependencies
dependencies:
  python: ">=3.11"
  packages:
    - requests>=2.31.0
    - beautifulsoup4>=4.12.0
    - selenium>=4.15.0  # For JS rendering
    - lxml>=4.9.0

# Configuration
config:
  timeout: 30
  max_retries: 3
  user_agent: "Mozilla/5.0..."

# Resources
resources:
  cpu: 0.5
  memory: 512Mi
  timeout: 60s

# Environment variables needed
env_vars:
  - PROXY_URL  # Optional
  - CHROME_DRIVER_PATH  # For Selenium

# Tags for discovery
tags:
  - web
  - scraping
  - data-extraction

# Author info
author:
  name: User Name
  email: user@example.com
created_at: 2026-01-24T00:00:00Z
```

### Database Schema Update

```python
class Skill(Base):
    """Skills table - now supports packages."""
    
    __tablename__ = "skills"
    
    skill_id = Column(UUID, primary_key=True, default=uuid.uuid4)
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False)
    
    # Skill type
    skill_type = Column(String(50), nullable=False, index=True)
    # simple_tool | code_module | skill_package
    
    # Storage location
    storage_type = Column(String(50), nullable=False, default="inline")
    # inline (code field) | minio (package in MinIO)
    
    storage_path = Column(String(500), nullable=True)
    # MinIO path: skills-storage/{skill_id}/
    
    # For simple tools (backward compatible)
    code = Column(Text, nullable=True)
    
    # Manifest (parsed from skill.yaml)
    manifest = Column(JSONB, nullable=True)
    
    # Auto-extracted interface
    interface_definition = Column(JSONB, nullable=False)
    
    # Dependencies (from requirements.txt or manifest)
    dependencies = Column(JSONB, nullable=True)
    
    # Metadata
    version = Column(String(50), nullable=False, default="1.0.0")
    is_active = Column(Boolean, nullable=False, default=True)
    is_system = Column(Boolean, nullable=False, default=False)
    
    # Execution stats
    execution_count = Column(Integer, nullable=False, default=0)
    last_executed_at = Column(DateTime(timezone=True), nullable=True)
    average_execution_time = Column(Float, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(UUID, ForeignKey("users.user_id"), nullable=True)
```

## Skill Creation Workflows

### Workflow 1: Simple Tool (LangChain @tool)

**Use Case**: Simple, single-function skills like calculator, API call

```python
# User provides just the code
from langchain_core.tools import tool

@tool
def calculator(expression: str) -> str:
    """Calculate mathematical expressions."""
    return str(eval(expression))
```

**Storage**: Inline in `code` field

### Workflow 2: Code Module

**Use Case**: Multi-file Python module with helpers

```
User uploads:
├── main.py          # Entry point with @tool function
├── utils.py         # Helper functions
└── config.py        # Configuration
```

**Storage**: MinIO as zip, extracted to `skills-storage/{skill_id}/`

### Workflow 3: Skill Package (Full Project)

**Use Case**: Complex skills like ML models, web scrapers, API integrations

```
User uploads entire project:
├── skill.yaml           # Manifest
├── README.md            # Documentation
├── requirements.txt     # Dependencies
├── src/
│   ├── __init__.py
│   ├── main.py         # Entry point
│   ├── scraper.py
│   └── parser.py
├── data/
│   └── selectors.json
├── tests/
│   └── test_scraper.py
└── .env.example
```

**Storage**: MinIO as structured project

## Skill Execution Engine

### Dynamic Loading

```python
class SkillExecutionEngine:
    """Execute skills of any complexity."""
    
    async def execute_skill(
        self,
        skill: Skill,
        inputs: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ExecutionResult:
        """Execute skill based on its type."""
        
        if skill.storage_type == "inline":
            # Simple tool - execute directly
            return await self._execute_inline_skill(skill, inputs)
        
        elif skill.storage_type == "minio":
            # Package - load from MinIO and execute
            return await self._execute_package_skill(skill, inputs, context)
    
    async def _execute_package_skill(
        self,
        skill: Skill,
        inputs: Dict[str, Any],
        context: Optional[Dict[str, Any]]
    ) -> ExecutionResult:
        """Execute a skill package from MinIO."""
        
        # 1. Download package from MinIO
        package_path = await self._download_skill_package(skill.skill_id)
        
        # 2. Create isolated environment
        venv_path = await self._create_skill_venv(
            skill.skill_id,
            skill.dependencies
        )
        
        # 3. Load manifest
        manifest = self._load_manifest(package_path)
        
        # 4. Prepare execution context
        exec_context = {
            "skill_id": skill.skill_id,
            "package_path": package_path,
            "venv_path": venv_path,
            "config": manifest.get("config", {}),
            "env_vars": self._prepare_env_vars(manifest),
        }
        
        # 5. Execute in sandbox
        result = await self._execute_in_sandbox(
            entry_point=manifest["entry_point"],
            function=manifest["function"],
            inputs=inputs,
            context=exec_context,
            timeout=manifest.get("resources", {}).get("timeout", 60),
        )
        
        return result
    
    async def _download_skill_package(self, skill_id: UUID) -> str:
        """Download skill package from MinIO to local cache."""
        cache_dir = f"/tmp/skills/{skill_id}"
        
        if os.path.exists(cache_dir):
            return cache_dir  # Already cached
        
        # Download from MinIO
        minio_client = get_minio_client()
        minio_client.download_directory(
            bucket="skills-storage",
            prefix=f"{skill_id}/",
            local_path=cache_dir
        )
        
        return cache_dir
    
    async def _create_skill_venv(
        self,
        skill_id: UUID,
        dependencies: List[str]
    ) -> str:
        """Create isolated virtual environment for skill."""
        venv_path = f"/tmp/skills/{skill_id}/.venv"
        
        if os.path.exists(venv_path):
            return venv_path  # Already created
        
        # Create venv
        subprocess.run([
            "python", "-m", "venv", venv_path
        ], check=True)
        
        # Install dependencies
        pip_path = f"{venv_path}/bin/pip"
        subprocess.run([
            pip_path, "install", *dependencies
        ], check=True)
        
        return venv_path
```

## Frontend: Flexible Upload Interface

### UI Modes

```typescript
type SkillCreationMode = 
  | 'simple-tool'      // Single function with code editor
  | 'code-module'      // Multiple files upload
  | 'skill-package'    // Full project upload with manifest
  | 'from-template'    // Start from template

interface SkillUploadProps {
  mode: SkillCreationMode;
}
```

### Simple Tool Mode

```tsx
<CodeEditor
  language="python"
  value={code}
  onChange={setCode}
  placeholder={`from langchain_core.tools import tool

@tool
def my_skill(param: str) -> str:
    """Skill description."""
    return result
`}
/>
```

### Code Module Mode

```tsx
<FileUploader
  accept=".py"
  multiple={true}
  onUpload={handleFilesUpload}
  instructions="Upload Python files. Mark one as entry point."
/>

<FileList files={files}>
  {files.map(file => (
    <FileItem 
      file={file}
      isEntryPoint={file.name === entryPoint}
      onSetEntryPoint={() => setEntryPoint(file.name)}
    />
  ))}
</FileList>
```

### Skill Package Mode

```tsx
<ProjectUploader
  onUpload={handleProjectUpload}
  requiredFiles={['skill.yaml', 'README.md']}
  optionalFiles={['requirements.txt', '.env.example']}
>
  <DropZone>
    Drop entire project folder or zip file
  </DropZone>
  
  <ProjectStructure>
    <RequiredFile>skill.yaml</RequiredFile>
    <RequiredFile>README.md</RequiredFile>
    <OptionalFile>requirements.txt</OptionalFile>
    <OptionalFile>src/</OptionalFile>
    <OptionalFile>data/</OptionalFile>
  </ProjectStructure>
</ProjectUploader>
```

## Integration with LangChain Tools

### Compatibility Layer

```python
class SkillToToolAdapter:
    """Convert any skill to LangChain Tool."""
    
    def create_tool(self, skill: Skill) -> Tool:
        """Create LangChain tool from skill."""
        
        if skill.skill_type == "simple_tool":
            # Direct conversion
            return self._create_from_code(skill.code)
        
        else:
            # Wrap package execution as tool
            return self._create_wrapper_tool(skill)
    
    def _create_wrapper_tool(self, skill: Skill) -> Tool:
        """Create wrapper tool for complex skills."""
        
        @tool
        async def skill_wrapper(**kwargs) -> str:
            """Dynamically generated tool wrapper."""
            engine = get_skill_execution_engine()
            result = await engine.execute_skill(skill, kwargs)
            return result.output
        
        # Set metadata from skill
        skill_wrapper.name = skill.name
        skill_wrapper.description = skill.description
        skill_wrapper.args_schema = self._create_args_schema(
            skill.interface_definition
        )
        
        return skill_wrapper
```

## Examples

### Example 1: Simple Tool (Tavily Search)

```python
# Inline code
from langchain_core.tools import tool
from tavily import TavilyClient
import os

@tool
def web_search(query: str, max_results: int = 10) -> str:
    """Search the internet."""
    client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    results = client.search(query=query, max_results=max_results)
    return format_results(results)
```

**Storage**: Inline in database

### Example 2: Complex Skill (ML Model Inference)

```
Project Structure:
├── skill.yaml
├── README.md
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── main.py              # Entry point
│   ├── model_loader.py
│   ├── preprocessor.py
│   └── postprocessor.py
├── models/
│   └── model.pkl
└── config.yaml
```

```yaml
# skill.yaml
name: sentiment_analyzer
type: skill_package
entry_point: src/main.py
function: analyze_sentiment

interface:
  inputs:
    - name: text
      type: string
      required: true
  outputs:
    - name: sentiment
      type: string
    - name: confidence
      type: float

dependencies:
  packages:
    - torch>=2.0.0
    - transformers>=4.30.0
    - numpy>=1.24.0

resources:
  memory: 2Gi
  timeout: 30s
```

```python
# src/main.py
from langchain_core.tools import tool
from .model_loader import load_model
from .preprocessor import preprocess
from .postprocessor import postprocess

# Load model once at module level
model = load_model("models/model.pkl")

@tool
def analyze_sentiment(text: str) -> dict:
    """Analyze sentiment of text using ML model."""
    processed = preprocess(text)
    prediction = model.predict(processed)
    result = postprocess(prediction)
    return result
```

**Storage**: Full project in MinIO

## Benefits

1. **Maximum Flexibility**: Support any complexity level
2. **LangChain Compatible**: All skills work as LangChain tools
3. **Isolated Execution**: Each skill has its own environment
4. **Version Control**: Skills are versioned packages
5. **Reusable**: Share complex skills across agents
6. **Testable**: Skills include their own tests
7. **Documented**: README.md explains usage

## Migration Path

1. **Phase 1**: Support inline simple tools (current)
2. **Phase 2**: Add code module support (multi-file)
3. **Phase 3**: Add full package support (with manifest)
4. **Phase 4**: Add skill marketplace/sharing

## API Endpoints

```
POST   /api/v1/skills/upload-simple      # Upload inline code
POST   /api/v1/skills/upload-module      # Upload multiple files
POST   /api/v1/skills/upload-package     # Upload full project
GET    /api/v1/skills/{id}/download      # Download skill package
GET    /api/v1/skills/{id}/readme        # Get README
GET    /api/v1/skills/{id}/manifest      # Get manifest
POST   /api/v1/skills/{id}/test          # Test skill
```

## Summary

This architecture provides:
- **Simple**: Single function for basic skills
- **Flexible**: Full projects for complex skills
- **Compatible**: Works with LangChain tools
- **Scalable**: Isolated execution environments
- **Professional**: Proper packaging and documentation

It's the best of both worlds: simple when you need simple, powerful when you need power.
