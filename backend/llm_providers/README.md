# LLM Provider Integration

This module provides a unified interface for interacting with various LLM providers including local providers (Ollama, vLLM) and optional cloud providers (OpenAI, Anthropic).

## Features

- **Unified Interface**: Single API for all LLM providers
- **Automatic Provider Selection**: Task-based model selection
- **Fallback Logic**: Automatic fallback to cloud providers when local providers fail
- **Retry Mechanism**: Exponential backoff retry logic
- **Request/Response Logging**: Comprehensive logging for debugging and monitoring
- **Token Usage Tracking**: Track token consumption across providers
- **Prompt Templates**: Reusable templates for common tasks
- **Health Monitoring**: Provider health checks

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      LLM Router                          │
│  - Provider selection                                    │
│  - Fallback logic                                        │
│  - Retry mechanism                                       │
│  - Token tracking                                        │
└────────────┬────────────────────────────────────────────┘
             │
    ┌────────┼────────┬────────────┬──────────────┐
    │        │        │            │              │
┌───▼───┐ ┌─▼────┐ ┌─▼──────┐ ┌──▼────────┐ ┌──▼─────────┐
│Ollama │ │ vLLM │ │ OpenAI │ │ Anthropic │ │   Future   │
│(Local)│ │(Local)│ │(Cloud) │ │  (Cloud)  │ │  Providers │
└───────┘ └──────┘ └────────┘ └───────────┘ └────────────┘
```

## Components

### Base Provider (`base.py`)

Abstract base class that all providers must implement:

- `generate()`: Text completion
- `generate_embedding()`: Embedding generation
- `list_models()`: List available models
- `health_check()`: Provider health status

### Ollama Provider (`ollama_provider.py`)

Local LLM provider using Ollama:

- **Default provider** for development and small-scale deployments
- Easy setup and model management
- Supports multiple models concurrently
- Models: llama3, mistral, codellama, nomic-embed-text

### vLLM Provider (`vllm_provider.py`)

High-performance local LLM provider:

- Optimized for production scale
- PagedAttention for efficient memory usage
- Higher throughput and lower latency
- GPU acceleration support

### OpenAI Provider (`openai_provider.py`)

Optional cloud provider:

- GPT-4, GPT-3.5-turbo support
- Chat and completion APIs
- Embedding generation
- **Only for non-sensitive data**

### Anthropic Provider (`anthropic_provider.py`)

Optional cloud provider:

- Claude 3 models support
- High-quality reasoning
- **Only for non-sensitive data**
- Note: No embedding support

### LLM Router (`router.py`)

Intelligent request routing:

- Automatic provider selection based on task type
- Fallback to cloud providers when local fails
- Retry logic with exponential backoff
- Request/response logging
- Token usage tracking

### Prompt Templates (`prompts.py`)

Reusable prompt templates:

- Agent system prompts
- Task decomposition
- Clarification questions
- Code generation
- Summarization
- Data analysis
- Translation
- Knowledge base queries
- Result aggregation

## Configuration

### Example Configuration

```yaml
# config.yaml
llm_providers:
  # Provider configurations
  providers:
    ollama:
      base_url: "http://localhost:11434"
      timeout: 60
    
    vllm:
      base_url: "http://localhost:8000"
      timeout: 120
      api_key: null  # Optional
    
    openai:  # Optional
      api_key: "${OPENAI_API_KEY}"
      base_url: "https://api.openai.com/v1"
      timeout: 60
      organization: null  # Optional
    
    anthropic:  # Optional
      api_key: "${ANTHROPIC_API_KEY}"
      base_url: "https://api.anthropic.com"
      timeout: 60
      api_version: "2023-06-01"
  
  # Task-specific model mapping
  model_mapping:
    chat:
      ollama: "llama3"
      vllm: "llama3"
      openai: "gpt-3.5-turbo"
      anthropic: "claude-3-haiku-20240307"
    
    code_generation:
      ollama: "codellama"
      vllm: "codellama"
      openai: "gpt-4"
      anthropic: "claude-3-sonnet-20240229"
    
    embedding:
      ollama: "nomic-embed-text"
      vllm: "nomic-embed-text"
      openai: "text-embedding-ada-002"
    
    summarization:
      ollama: "llama3:8b"
      vllm: "llama3:8b"
      openai: "gpt-3.5-turbo"
      anthropic: "claude-3-haiku-20240307"
    
    reasoning:
      ollama: "llama3:70b"
      vllm: "llama3:70b"
      openai: "gpt-4"
      anthropic: "claude-3-opus-20240229"
  
  # Router configuration
  fallback_enabled: false  # Enable cloud fallback
  max_retries: 3
  retry_delay: 1  # seconds
```

## Usage

### Basic Usage

```python
from llm_providers import LLMRouter, TaskType
from shared.config import get_config

# Initialize router
config = get_config().get_section("llm_providers")
router = LLMRouter(config)

# Generate text
response = await router.generate(
    prompt="Explain quantum computing",
    task_type=TaskType.CHAT,
    temperature=0.7,
    max_tokens=500
)

print(response.content)
print(f"Tokens used: {response.tokens_used}")

# Generate embedding
embedding_response = await router.generate_embedding(
    text="This is a test document"
)

print(f"Embedding dimension: {len(embedding_response.embedding)}")

# Close connections
await router.close_all()
```

### Using Specific Provider

```python
from llm_providers import OllamaProvider

# Initialize provider
provider = OllamaProvider({
    "base_url": "http://localhost:11434",
    "timeout": 60
})

# Generate text
response = await provider.generate(
    prompt="Hello, world!",
    model="llama3",
    temperature=0.7
)

print(response.content)

await provider.close()
```

### Using Prompt Templates

```python
from llm_providers.prompts import (
    get_agent_prompt,
    get_task_decomposition_prompt,
    get_code_generation_prompt
)

# Agent system prompt
agent_prompt = get_agent_prompt(
    agent_type="Data Analyst",
    skills=["data_processing", "visualization"],
    task_description="Analyze Q4 sales data",
    tools=["pandas", "matplotlib"],
    context="Focus on regional trends"
)

# Task decomposition prompt
decomp_prompt = get_task_decomposition_prompt(
    goal="Create a comprehensive sales report",
    available_skills=["data_processing", "writing", "visualization"]
)

# Code generation prompt
code_prompt = get_code_generation_prompt(
    language="Python",
    task_description="Calculate moving average",
    requirements=[
        "Use pandas DataFrame",
        "Handle missing values",
        "Return Series object"
    ]
)
```

### Health Monitoring

```python
# Check all providers
health_status = await router.health_check_all()
print(health_status)
# {'ollama': True, 'vllm': False, 'openai': True}

# Get token usage
usage = router.get_token_usage()
print(usage)
# {'ollama': 15000, 'openai': 5000}

# List available models
models = await router.list_available_models()
print(models)
# {'ollama': ['llama3', 'mistral', 'codellama'], 'vllm': ['llama3']}
```

## Testing

### Run Unit Tests

```bash
cd backend
pytest llm_providers/test_llm_providers.py -v
```

### Run Integration Tests

Integration tests require Ollama running on localhost:11434:

```bash
# Start Ollama
ollama serve

# Pull a model
ollama pull llama3

# Run integration tests
pytest llm_providers/test_llm_providers.py -v -m integration
```

## Privacy and Security

### Data Classification

- **Sensitive Data**: Always routed to local providers (Ollama, vLLM)
- **Non-Sensitive Data**: Can use cloud providers if fallback enabled
- **Default Behavior**: Cloud fallback disabled for maximum privacy

### Best Practices

1. **Use Local Providers**: Default to Ollama/vLLM for all enterprise data
2. **Disable Cloud Fallback**: Set `fallback_enabled: false` in production
3. **Monitor Token Usage**: Track usage to detect anomalies
4. **Health Checks**: Regular health monitoring of all providers
5. **Secure API Keys**: Use environment variables for cloud provider keys
6. **Audit Logging**: All requests logged for compliance

## Performance Optimization

### Model Selection

- **Chat/Reasoning**: Use larger models (llama3:70b) for complex tasks
- **Code Generation**: Use specialized models (codellama)
- **Embeddings**: Use optimized embedding models (nomic-embed-text)
- **Summarization**: Use smaller models (llama3:8b) for speed

### Caching

- Cache embeddings for frequently accessed documents
- Cache model responses for deterministic queries
- Use Redis for distributed caching

### Load Balancing

- Deploy multiple Ollama/vLLM instances
- Use round-robin or least-loaded selection
- Monitor instance health and capacity

## Troubleshooting

### Ollama Connection Issues

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama
ollama serve

# Check logs
journalctl -u ollama -f
```

### vLLM Connection Issues

```bash
# Check if vLLM is running
curl http://localhost:8000/health

# Start vLLM
python -m vllm.entrypoints.openai.api_server \
    --model llama3 \
    --port 8000
```

### High Latency

- Check model size (smaller models = faster inference)
- Enable GPU acceleration for vLLM
- Reduce max_tokens parameter
- Use batch processing for multiple requests

### Out of Memory

- Reduce concurrent requests
- Use smaller models
- Increase system memory
- Enable model quantization

## References

- Requirements 5: Multi-Provider LLM Support
- Design Section 9: LLM Integration Design
- Design Section 9.2: Model Selection Strategy
- Design Section 9.3: Prompt Engineering
