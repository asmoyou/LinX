# Dynamic Skill System Design

## Overview

This document describes the redesigned skill system inspired by Claude Code's flexible agent skills concept. The new system allows dynamic skill creation, code-based implementation, and seamless integration with LangChain agents.

## Current Problems

1. **Rigid Form-Based Creation**: Current UI uses fixed form fields (name, description, interface definition)
2. **No Executable Code**: Skills are just metadata without actual implementation
3. **Not LangChain Compatible**: Doesn't integrate with LangChain's `@tool` decorator pattern
4. **Static Interface**: Cannot adapt to different skill types dynamically

## Claude Code Agent Skills Concept

Claude Code's agent skills are:
- **Code-First**: Skills are defined by actual Python code with `@tool` decorator
- **Self-Describing**: Docstrings serve as descriptions and parameter documentation
- **Type-Safe**: Uses Python type hints for parameter validation
- **Composable**: Skills can call other skills or external APIs
- **Dynamic**: Can be created, tested, and modified on-the-fly

## New Architecture

### 1. Skill Types

```python
class SkillType(Enum):
    """Types of skills supported by the platform."""
    
    PYTHON_FUNCTION = "python_function"      # Pure Python function with @tool
    API_WRAPPER = "api_wrapper"              # Wraps external API calls
    DATABASE_QUERY = "database_query"        # SQL/NoSQL query templates
    WEB_SCRAPER = "web_scraper"             # Web scraping with selectors
    DATA_PROCESSOR = "data_processor"        # Data transformation pipelines
    CUSTOM = "custom"                        # User-defined custom logic
```

### 2. Skill Definition Format

#### Python Function Skill (Primary)

```python
from langchain_core.tools import tool
from typing import Dict, List, Optional

@tool
def web_search(query: str, max_results: int = 10) -> str:
    """Search the internet for information.
    
    Args:
        query: The search query string
        max_results: Maximum number of results to return (default: 10)
        
    Returns:
        Formatted search results with titles, URLs, and snippets
    """
    # Implementation code here
    results = tavily_client.search(query=query, max_results=max_results)
    return format_results(results)
```

#### API Wrapper Skill

```yaml
type: api_wrapper
name: weather_api
description: Get current weather for a location
endpoint: https://api.openweathermap.org/data/2.5/weather
method: GET
parameters:
  - name: q
    type: string
    description: City name
    required: true
  - name: units
    type: string
    description: Temperature units (metric/imperial)
    default: metric
headers:
  Authorization: "Bearer ${WEATHER_API_KEY}"
response_format: json
```

#### Database Query Skill

```yaml
type: database_query
name: get_user_stats
description: Get user statistics from database
database: postgresql
query: |
  SELECT 
    user_id,
    COUNT(*) as task_count,
    AVG(completion_time) as avg_time
  FROM tasks
  WHERE user_id = :user_id
    AND created_at >= :start_date
  GROUP BY user_id
parameters:
  - name: user_id
    type: uuid
    required: true
  - name: start_date
    type: date
    required: true
```

### 3. Database Schema Updates

```python
class Skill(Base):
    """Enhanced skills table with code storage."""
    
    __tablename__ = "skills"
    
    skill_id = Column(UUID, primary_key=True, default=uuid.uuid4)
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False)
    
    # Skill type and implementation
    skill_type = Column(String(50), nullable=False, default="python_function")
    code = Column(Text, nullable=True)  # Python code for function skills
    config = Column(JSONB, nullable=True)  # YAML config for API/DB skills
    
    # Auto-extracted from code/config
    interface_definition = Column(JSONB, nullable=False)
    dependencies = Column(JSONB, nullable=True)
    
    # Metadata
    version = Column(String(50), nullable=False, default="1.0.0")
    is_active = Column(Boolean, nullable=False, default=True)
    is_system = Column(Boolean, nullable=False, default=False)  # Built-in skills
    
    # Execution stats
    execution_count = Column(Integer, nullable=False, default=0)
    last_executed_at = Column(DateTime(timezone=True), nullable=True)
    average_execution_time = Column(Float, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Owner (for custom skills)
    created_by = Column(UUID, ForeignKey("users.user_id"), nullable=True)
```

### 4. Skill Execution Engine

```python
class SkillExecutionEngine:
    """Execute skills with proper sandboxing and error handling."""
    
    def __init__(self):
        self.sandbox_selector = SandboxSelector()
        self.llm_router = get_llm_router()
        
    async def execute_skill(
        self,
        skill: Skill,
        inputs: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ExecutionResult:
        """Execute a skill with given inputs.
        
        Args:
            skill: Skill object from database
            inputs: Input parameters
            context: Optional execution context (agent_id, task_id, etc.)
            
        Returns:
            ExecutionResult with output or error
        """
        if skill.skill_type == SkillType.PYTHON_FUNCTION:
            return await self._execute_python_skill(skill, inputs, context)
        elif skill.skill_type == SkillType.API_WRAPPER:
            return await self._execute_api_skill(skill, inputs)
        elif skill.skill_type == SkillType.DATABASE_QUERY:
            return await self._execute_db_skill(skill, inputs)
        else:
            raise ValueError(f"Unsupported skill type: {skill.skill_type}")
    
    async def _execute_python_skill(
        self,
        skill: Skill,
        inputs: Dict[str, Any],
        context: Optional[Dict[str, Any]]
    ) -> ExecutionResult:
        """Execute Python function skill in sandbox."""
        
        # Create LangChain tool from code
        tool = self._create_langchain_tool(skill.code, skill.name)
        
        # Execute in sandbox
        sandbox = self.sandbox_selector.get_sandbox()
        result = await sandbox.execute_tool(tool, inputs, context)
        
        # Update execution stats
        await self._update_execution_stats(skill.skill_id, result.execution_time)
        
        return result
    
    def _create_langchain_tool(self, code: str, name: str) -> Tool:
        """Dynamically create LangChain tool from Python code.
        
        This uses exec() to load the @tool decorated function.
        Security is handled by sandbox execution.
        """
        namespace = {
            'tool': tool,
            '__name__': f'skill_{name}',
        }
        
        # Execute code to define the function
        exec(code, namespace)
        
        # Find the tool function
        for obj in namespace.values():
            if isinstance(obj, Tool):
                return obj
        
        raise ValueError(f"No @tool decorated function found in skill: {name}")
```

### 5. Frontend: Code Editor Interface

Replace the rigid form with a flexible code editor:

```typescript
// Skill creation modes
type SkillCreationMode = 
  | 'code-editor'      // Write Python code with @tool
  | 'api-builder'      // Visual API wrapper builder
  | 'query-builder'    // SQL query builder
  | 'template'         // Start from template

interface SkillEditorProps {
  mode: SkillCreationMode;
  initialCode?: string;
  onSave: (skill: SkillDefinition) => void;
}

// Code editor with syntax highlighting
<CodeEditor
  language="python"
  value={code}
  onChange={setCode}
  theme="vs-dark"
  options={{
    minimap: { enabled: false },
    fontSize: 14,
    lineNumbers: 'on',
    automaticLayout: true,
  }}
  placeholder={`from langchain_core.tools import tool

@tool
def my_skill(param: str) -> str:
    """Skill description here.
    
    Args:
        param: Parameter description
        
    Returns:
        Result description
    """
    # Your implementation here
    return result
`}
/>
```

### 6. Skill Templates Library

Provide pre-built templates for common patterns:

```python
SKILL_TEMPLATES = {
    "web_search": {
        "name": "Web Search",
        "description": "Search the internet using Tavily API",
        "code": """
from langchain_core.tools import tool
from tavily import TavilyClient
import os

tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

@tool
def web_search(query: str, max_results: int = 10) -> str:
    \"\"\"Search the internet for information.
    
    Args:
        query: The search query string
        max_results: Maximum number of results to return
        
    Returns:
        Formatted search results
    \"\"\"
    response = tavily_client.search(
        query=query,
        max_results=max_results,
        search_depth="basic"
    )
    
    results = []
    for r in response.get("results", []):
        results.append(f"**{r['title']}**\\nURL: {r['url']}\\n{r['content']}\\n")
    
    return "\\n---\\n".join(results) if results else "No results found"
""",
        "dependencies": ["tavily-python"],
    },
    
    "api_call": {
        "name": "HTTP API Call",
        "description": "Make HTTP requests to external APIs",
        "code": """
from langchain_core.tools import tool
import requests
from typing import Dict, Any, Optional

@tool
def api_call(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[Dict[str, Any]] = None
) -> str:
    \"\"\"Make HTTP API requests.
    
    Args:
        url: The API endpoint URL
        method: HTTP method (GET, POST, PUT, DELETE)
        headers: Optional request headers
        body: Optional request body (for POST/PUT)
        
    Returns:
        API response as JSON string
    \"\"\"
    response = requests.request(
        method=method.upper(),
        url=url,
        headers=headers or {},
        json=body
    )
    response.raise_for_status()
    return response.text
""",
        "dependencies": ["requests"],
    },
    
    "data_analysis": {
        "name": "Data Analysis",
        "description": "Analyze data using pandas",
        "code": """
from langchain_core.tools import tool
import pandas as pd
from typing import List, Dict, Any

@tool
def analyze_data(data: List[Dict[str, Any]], operation: str) -> str:
    \"\"\"Analyze data using pandas operations.
    
    Args:
        data: List of dictionaries representing rows
        operation: Operation to perform (describe, sum, mean, etc.)
        
    Returns:
        Analysis results as formatted string
    \"\"\"
    df = pd.DataFrame(data)
    
    if operation == "describe":
        return df.describe().to_string()
    elif operation == "sum":
        return df.sum().to_string()
    elif operation == "mean":
        return df.mean().to_string()
    else:
        return f"Unknown operation: {operation}"
""",
        "dependencies": ["pandas"],
    },
}
```

### 7. Skill Testing Interface

Allow users to test skills before deploying:

```typescript
interface SkillTestProps {
  skill: Skill;
  onTest: (inputs: Record<string, any>) => Promise<TestResult>;
}

function SkillTester({ skill, onTest }: SkillTestProps) {
  const [inputs, setInputs] = useState<Record<string, any>>({});
  const [result, setResult] = useState<TestResult | null>(null);
  const [loading, setLoading] = useState(false);
  
  const handleTest = async () => {
    setLoading(true);
    try {
      const testResult = await onTest(inputs);
      setResult(testResult);
    } catch (error) {
      setResult({
        success: false,
        error: error.message,
      });
    } finally {
      setLoading(false);
    }
  };
  
  return (
    <div className="skill-tester">
      <h3>Test Skill</h3>
      
      {/* Dynamic input fields based on skill interface */}
      {skill.interface_definition.inputs.map(input => (
        <InputField
          key={input.name}
          name={input.name}
          type={input.type}
          required={input.required}
          value={inputs[input.name]}
          onChange={(value) => setInputs({...inputs, [input.name]: value})}
        />
      ))}
      
      <button onClick={handleTest} disabled={loading}>
        {loading ? 'Testing...' : 'Run Test'}
      </button>
      
      {result && (
        <div className={`result ${result.success ? 'success' : 'error'}`}>
          <h4>Result:</h4>
          <pre>{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}
```

### 8. Agent-Skill Integration

Agents dynamically load skills as LangChain tools:

```python
class BaseAgent:
    """LangChain-based agent with dynamic skill loading."""
    
    def __init__(self, agent_id: UUID, capabilities: List[str]):
        self.agent_id = agent_id
        self.capabilities = capabilities
        self.tools = []
        self.llm = None
        
    async def initialize(self):
        """Initialize agent with skills and LLM."""
        
        # Load LLM
        self.llm = await self._get_llm()
        
        # Load skills as LangChain tools
        self.tools = await self._load_skills()
        
        # Create LangChain agent
        self.agent = create_react_agent(
            model=self.llm,
            tools=self.tools,
            prompt=self._get_system_prompt()
        )
    
    async def _load_skills(self) -> List[Tool]:
        """Load agent's skills as LangChain tools."""
        tools = []
        
        skill_registry = get_skill_registry()
        execution_engine = get_skill_execution_engine()
        
        for skill_name in self.capabilities:
            skill = skill_registry.get_skill_by_name(skill_name)
            if not skill or not skill.is_active:
                continue
            
            # Convert skill to LangChain tool
            tool = execution_engine.create_tool(skill, agent_id=self.agent_id)
            tools.append(tool)
        
        return tools
    
    async def execute_task(self, task: str) -> Dict[str, Any]:
        """Execute task using available skills."""
        
        result = await self.agent.ainvoke({
            "messages": [{"role": "user", "content": task}]
        })
        
        return {
            "status": "completed",
            "output": result["output"],
            "tools_used": result.get("intermediate_steps", []),
        }
```

## Implementation Plan

### Phase 1: Database Migration
1. Add new columns to skills table (skill_type, code, config, is_active, is_system, execution stats)
2. Migrate existing skills to new format
3. Create indexes for performance

### Phase 2: Backend - Skill Execution Engine
1. Implement SkillExecutionEngine with sandbox support
2. Add dynamic LangChain tool creation from code
3. Implement API wrapper and DB query executors
4. Add skill validation and testing endpoints

### Phase 3: Backend - API Updates
1. Update skill CRUD endpoints to support new fields
2. Add skill testing endpoint (POST /skills/{id}/test)
3. Add skill templates endpoint (GET /skills/templates)
4. Add skill execution stats endpoint

### Phase 4: Frontend - Code Editor
1. Replace rigid form with Monaco code editor
2. Add syntax highlighting for Python
3. Implement skill templates selector
4. Add skill testing interface

### Phase 5: Frontend - Skill Management
1. Update skill cards to show skill type and stats
2. Add code preview/edit functionality
3. Implement skill activation/deactivation
4. Add skill usage analytics

### Phase 6: Integration
1. Update agent creation to use new skill system
2. Test agent-skill integration end-to-end
3. Add skill marketplace (optional)
4. Documentation and examples

## Benefits

1. **Flexibility**: Users can create any type of skill with code
2. **LangChain Native**: Direct integration with LangChain tools
3. **Type-Safe**: Python type hints provide validation
4. **Testable**: Built-in testing before deployment
5. **Composable**: Skills can use other skills
6. **Observable**: Execution stats and monitoring
7. **Secure**: Sandboxed execution with resource limits

## Security Considerations

1. **Code Validation**: Static analysis before execution
2. **Sandbox Isolation**: All code runs in isolated containers
3. **Resource Limits**: CPU, memory, and time limits
4. **Permission System**: Skills require explicit permissions
5. **Audit Logging**: All skill executions are logged
6. **Code Review**: Optional approval workflow for custom skills

## References

- LangChain Tools: https://python.langchain.com/docs/modules/agents/tools/
- Claude Code Agent Skills concept
- Design Document Section 4.4: Skill System
- Design Document Section 5: Code Execution Environment
