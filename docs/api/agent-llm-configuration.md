# Agent LLM Configuration API

Updated agent management API to support dynamic LLM provider and model configuration.

## Overview

Agents can now be configured with specific LLM providers and models, allowing fine-grained control over which AI models power each agent. This aligns with the updated LLM provider management system that supports multiple providers (Ollama, OpenAI, Anthropic, vLLM, etc.).

## API Changes

### Agent Model Fields

New fields added to agent configuration:

```typescript
{
  // LLM Configuration
  provider?: string;        // LLM provider name (ollama, openai, etc.)
  model?: string;          // Model name (llama3.2:latest, gpt-4, etc.)
  systemPrompt?: string;   // Custom system prompt
  temperature?: number;    // Sampling temperature (0.0-2.0)
  maxTokens?: number;      // Maximum tokens (1-8000)
  topP?: number;          // Top-p sampling (0.0-1.0)
  
  // Access Control
  accessLevel?: string;           // private, team, public
  allowedKnowledge?: string[];    // Knowledge base IDs
  allowedMemory?: string[];       // Memory collection IDs
}
```

### New Endpoint: Get Available Providers

**GET** `/api/agents/available-providers`

Returns available LLM providers and their models for agent configuration.

**Response:**
```json
{
  "providers": {
    "ollama": ["llama3.2:latest", "mistral:latest", "codellama:latest"],
    "openai": ["gpt-4", "gpt-3.5-turbo"],
    "anthropic": ["claude-3-opus", "claude-3-sonnet"]
  }
}
```

**Usage:**
- Populate provider/model dropdowns in agent configuration UI
- Validate provider/model selections
- Show only enabled and healthy providers

### Updated Endpoints

#### Create Agent

**POST** `/api/agents`

Now accepts LLM configuration in request body:

```json
{
  "name": "Research Agent",
  "type": "researcher",
  "skills": ["search", "analyze"],
  "provider": "ollama",
  "model": "llama3.2:latest",
  "systemPrompt": "You are a research assistant...",
  "temperature": 0.7,
  "maxTokens": 2000,
  "topP": 0.9,
  "accessLevel": "private",
  "allowedKnowledge": ["kb-123"],
  "allowedMemory": ["mem-456"]
}
```

#### Update Agent

**PUT** `/api/agents/{agent_id}`

Can update LLM configuration:

```json
{
  "provider": "openai",
  "model": "gpt-4",
  "temperature": 0.5,
  "maxTokens": 3000
}
```

#### Get Agent / List Agents

**GET** `/api/agents/{agent_id}`  
**GET** `/api/agents`

Now returns LLM configuration in response:

```json
{
  "id": "agent-123",
  "name": "Research Agent",
  "provider": "ollama",
  "model": "llama3.2:latest",
  "systemPrompt": "You are a research assistant...",
  "temperature": 0.7,
  "maxTokens": 2000,
  "topP": 0.9,
  "accessLevel": "private",
  "allowedKnowledge": ["kb-123"],
  "allowedMemory": ["mem-456"]
}
```

## Database Schema

New columns added to `agents` table:

```sql
-- LLM Configuration
llm_provider VARCHAR(100)      -- Provider name
llm_model VARCHAR(255)         -- Model name
system_prompt TEXT             -- Custom system prompt
temperature FLOAT DEFAULT 0.7  -- Sampling temperature
max_tokens INTEGER DEFAULT 2000 -- Maximum tokens
top_p FLOAT DEFAULT 0.9        -- Top-p sampling

-- Access Control
access_level VARCHAR(50) DEFAULT 'private'
allowed_knowledge JSONB        -- Knowledge base IDs
allowed_memory JSONB           -- Memory collection IDs
```

## Migration

Run the database migration to add new fields:

```bash
cd backend
alembic upgrade head
```

Migration file: `alembic/versions/add_llm_config_to_agents.py`

## Integration with LLM Router

Agents now use their configured provider and model when executing tasks:

```python
# Agent test endpoint uses agent's LLM configuration
system_prompt = agent.system_prompt or f"You are {agent.name}..."
model = agent.llm_model or "llama3.2:latest"
provider = agent.llm_provider  # Can be None (auto-select)
temperature = agent.temperature or 0.7
max_tokens = agent.max_tokens or 2000

# Generate response using agent's configuration
async for chunk in llm_router.generate_stream(
    messages=messages,
    model=model,
    provider=provider,
    temperature=temperature,
    max_tokens=max_tokens,
):
    yield chunk
```

## Frontend Integration

### Agent Configuration Form

```typescript
// 1. Fetch available providers on component mount
const { data: providers } = await fetch('/api/agents/available-providers');

// 2. Populate provider dropdown
<Select value={provider} onChange={setProvider}>
  {Object.keys(providers.providers).map(p => (
    <Option key={p} value={p}>{p}</Option>
  ))}
</Select>

// 3. Populate model dropdown based on selected provider
<Select value={model} onChange={setModel}>
  {providers.providers[provider]?.map(m => (
    <Option key={m} value={m}>{m}</Option>
  ))}
</Select>

// 4. Submit agent configuration
await fetch('/api/agents', {
  method: 'POST',
  body: JSON.stringify({
    name,
    type,
    provider,
    model,
    temperature,
    maxTokens,
    systemPrompt,
  })
});
```

## Benefits

1. **Flexibility**: Each agent can use different LLM providers/models
2. **Cost Control**: Use cheaper models for simple tasks, expensive models for complex ones
3. **Performance**: Match model capabilities to agent requirements
4. **Privacy**: Keep sensitive agents on local providers (Ollama)
5. **Fallback**: Configure cloud providers as fallback for critical agents

## Examples

### Local Research Agent

```json
{
  "name": "Local Research Agent",
  "provider": "ollama",
  "model": "llama3.2:latest",
  "temperature": 0.7
}
```

### Cloud-Powered Code Agent

```json
{
  "name": "Code Assistant",
  "provider": "openai",
  "model": "gpt-4",
  "temperature": 0.3,
  "maxTokens": 4000
}
```

### Auto-Select Provider

```json
{
  "name": "General Agent",
  "model": "llama3.2:latest",
  "provider": null  // Let router choose best available provider
}
```

## References

- [LLM Provider Management API](./llm-provider-management.md)
- [Agent Framework Design](../architecture/agent-framework.md)
- Backend Implementation: `backend/agent_framework/agent_registry.py`
- API Routes: `backend/api_gateway/routers/agents.py`
- Database Models: `backend/database/models.py`
