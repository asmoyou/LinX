# Configuration Guide

This document describes the configuration structure for the Digital Workforce Platform.

## Configuration Files

- **config.yaml**: Main configuration file (development defaults included)
- **config.yaml.example**: Template configuration with all available options and documentation
- **.env**: Environment variables for sensitive data (not tracked in git)

## Quick Start

1. **For Development**: The included `config.yaml` has sensible defaults for local development.

2. **For Production**: 
   ```bash
   cp config.yaml.example config.yaml
   # Edit config.yaml with your production values
   # Set sensitive values via environment variables
   ```

3. **Environment Variables**: Create a `.env` file for sensitive data:
   ```bash
   cp .env.example .env
   # Edit .env with your secrets
   ```

## Configuration Sections

### 1. Platform Settings
Basic platform identification and environment configuration.

```yaml
platform:
  name: "Digital Workforce Platform"
  version: "1.0.0"
  environment: "development"  # development, staging, production
  debug: true
```

### 2. API Gateway
API server configuration including CORS, rate limiting, and JWT authentication.

**Key Settings**:
- `api.host`: Bind address (use "0.0.0.0" for all interfaces)
- `api.port`: HTTP port (default: 8000)
- `api.jwt.secret_key`: **REQUIRED** - Set via `${JWT_SECRET}` environment variable
- `api.cors.origins`: Allowed frontend origins

### 3. Database Configuration

#### PostgreSQL (Primary Database)
Stores operational data: users, agents, tasks, permissions.

**Key Settings**:
- `database.postgres.password`: **REQUIRED** - Set via `${POSTGRES_PASSWORD}`
- `database.postgres.pool_size`: Connection pool size (default: 20)

#### Milvus (Vector Database)
Stores embeddings for semantic search.

**Key Settings**:
- `database.milvus.index_type`: Index algorithm (IVF_FLAT, HNSW, etc.)
- `database.milvus.metric_type`: Distance metric (L2, IP, COSINE)
- `database.milvus.enable_partitioning`: Enable data partitioning for performance

#### Redis (Message Bus & Cache)
Handles inter-agent communication and caching.

**Key Settings**:
- `database.redis.password`: Optional password
- `database.redis.max_connections`: Connection pool size

### 4. Object Storage (MinIO)
Stores documents, audio, video, images, and agent artifacts.

**Key Settings**:
- `storage.minio.access_key`: **REQUIRED** - Set via `${MINIO_ACCESS_KEY}`
- `storage.minio.secret_key`: **REQUIRED** - Set via `${MINIO_SECRET_KEY}`
- `storage.minio.max_file_size_mb`: Maximum upload size
- `storage.minio.allowed_*_types`: Whitelist of allowed file extensions

### 5. LLM Providers
Configure local and cloud LLM providers.

**Providers**:
- **Ollama** (Primary - Local): Default for privacy-first deployment
- **vLLM** (High-Performance - Local): For production scale
- **OpenAI** (Optional - Cloud): Requires API key
- **Anthropic** (Optional - Cloud): Requires API key

**Key Settings**:
- `llm.default_provider`: Which provider to use by default
- `llm.providers.ollama.models.*`: Model selection for different tasks
- `llm.providers.*.enabled`: Enable/disable specific providers

**Model Types**:
- `chat`: General conversation and reasoning
- `code`: Code generation and analysis
- `embedding`: Text embedding for semantic search
- `summarization`: Text summarization
- `translation`: Language translation

### 6. Agent Framework
Agent pool management and resource allocation.

**Key Settings**:
- `agents.pool.min_size`: Minimum number of pre-warmed agents
- `agents.pool.max_size`: Maximum concurrent agents
- `agents.resources.default_*`: Default resource limits per agent
- `agents.templates`: Pre-configured agent types

**Agent Templates**:
- `data_analyst`: Data processing and visualization
- `content_writer`: Writing and editing
- `code_assistant`: Code generation and debugging
- `research_assistant`: Information gathering and research

### 7. Code Execution Sandbox
Secure code execution environment configuration.

**Sandbox Types** (Auto-detected by platform):
- **gVisor**: Linux only, high security
- **Firecracker**: Linux with KVM, very high security
- **Docker Enhanced**: Cross-platform fallback

**Key Settings**:
- `code_execution.sandbox_mode`: "auto" for automatic detection
- `code_execution.resources.*`: Resource limits for code execution
- `code_execution.security.enable_network`: Allow network access (default: false)

### 8. Security
Encryption, authentication, and access control settings.

**Key Settings**:
- `security.encryption.at_rest`: Encrypt data at rest
- `security.encryption.in_transit`: Enforce TLS/SSL
- `security.data_classification.enabled`: Auto-classify sensitive data
- `security.container_isolation.*`: Container security policies
- `security.authentication.*`: Password and session policies

### 9. Resource Quotas
Per-user resource limits.

**Key Settings**:
- `quotas.default.*`: Default limits for regular users
- `quotas.admin.*`: Limits for admin users
- `quotas.enforcement.enabled`: Enable quota enforcement

### 10. Monitoring & Observability
Metrics, logging, and tracing configuration.

**Components**:
- **Prometheus**: Metrics collection
- **Logging**: Structured JSON logging
- **Tracing**: Distributed tracing with Jaeger
- **Health Checks**: Component health monitoring

**Key Settings**:
- `monitoring.logging.level`: Log level (DEBUG, INFO, WARNING, ERROR)
- `monitoring.logging.format`: "json" or "text"
- `monitoring.tracing.sample_rate`: Percentage of requests to trace

### 11. Alerting
Alert configuration for system, application, and security events.

**Channels**:
- Email (SMTP)
- Slack
- Microsoft Teams
- PagerDuty (critical alerts)

**Key Settings**:
- `alerting.enabled`: Enable/disable alerting
- `alerting.channels.*`: Configure alert channels
- `alerting.rules.*`: Alert thresholds
- `alerting.routing.*`: Route alerts by severity

### 12. Task Management
Task decomposition, execution, and retry configuration.

**Key Settings**:
- `task_management.decomposition.max_depth`: Maximum task tree depth
- `task_management.execution.enable_parallel`: Enable parallel execution
- `task_management.retry.max_attempts`: Maximum retry attempts
- `task_management.aggregation.default_strategy`: Result aggregation method

### 13. Memory System
Multi-tiered memory configuration.

**Memory Types**:
- **Agent Memory**: Private to each agent
- **Company Memory**: Shared across agents
- **User Context**: Shared across user's agents

**Key Settings**:
- `memory.types.*.retention_days`: How long to keep memories
- `memory.embedding.dimension`: Embedding vector dimension (must match model)
- `memory.retrieval.top_k`: Number of results to retrieve
- `memory.retrieval.similarity_threshold`: Minimum similarity score

### 14. Knowledge Base
Document processing and search configuration.

**Key Settings**:
- `knowledge_base.processing.chunk_size_tokens`: Document chunk size
- `knowledge_base.processing.ocr.enabled`: Enable OCR for images
- `knowledge_base.processing.transcription.enabled`: Enable audio transcription
- `knowledge_base.search.enable_semantic`: Enable vector search
- `knowledge_base.search.enable_fulltext`: Enable full-text search

### 15. Message Bus
Inter-agent communication configuration.

**Key Settings**:
- `message_bus.enable_pubsub`: Enable publish-subscribe
- `message_bus.enable_streams`: Enable Redis Streams
- `message_bus.retention.*`: Message retention policies
- `message_bus.audit_messages`: Log all messages

### 16. Deployment
Deployment mode and backup configuration.

**Modes**:
- `docker-compose`: Development and small deployments
- `kubernetes`: Production scale
- `standalone`: Single-server deployment

**Key Settings**:
- `deployment.mode`: Deployment mode
- `deployment.backup.enabled`: Enable automated backups
- `deployment.backup.schedule`: Cron schedule for backups

### 17. Feature Flags
Enable/disable platform features.

**Key Settings**:
- `features.enable_task_flow_visualization`: Real-time task visualization
- `features.enable_websocket`: WebSocket support for real-time updates
- `features.enable_dynamic_skill_generation`: Generate skills on-the-fly
- `features.enable_robot_integration`: Future robot support

### 18. Development Settings
Development-specific configuration.

**Key Settings**:
- `development.debug_mode`: Enable debug mode
- `development.hot_reload`: Enable hot reload
- `development.mock_llm_responses`: Mock LLM for testing
- `development.load_sample_data`: Load sample data on startup

## Environment Variables

Sensitive configuration should be set via environment variables:

### Required Variables

```bash
# JWT Secret (generate with: openssl rand -hex 32)
JWT_SECRET=your-secret-key-here

# PostgreSQL Password
POSTGRES_PASSWORD=your-postgres-password

# MinIO Credentials
MINIO_ACCESS_KEY=your-minio-access-key
MINIO_SECRET_KEY=your-minio-secret-key
```

### Optional Variables

```bash
# Redis Password (if authentication enabled)
REDIS_PASSWORD=your-redis-password

# Milvus Password (if authentication enabled)
MILVUS_PASSWORD=your-milvus-password

# Cloud LLM Providers (if enabled)
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key

# Email Alerts (if enabled)
SMTP_USER=your-smtp-username
SMTP_PASSWORD=your-smtp-password

# Slack Alerts (if enabled)
SLACK_WEBHOOK_URL=your-slack-webhook-url

# Microsoft Teams Alerts (if enabled)
TEAMS_WEBHOOK_URL=your-teams-webhook-url

# PagerDuty Alerts (if enabled)
PAGERDUTY_INTEGRATION_KEY=your-pagerduty-key
```

## Configuration Validation

The platform validates configuration on startup:

1. **Required Fields**: Checks all required fields are present
2. **Type Validation**: Ensures correct data types
3. **Range Validation**: Validates numeric ranges
4. **Dependency Checks**: Ensures dependent settings are consistent

**Example Validation Errors**:
```
ERROR: Missing required configuration: api.jwt.secret_key
ERROR: Invalid value for monitoring.logging.level: must be one of [DEBUG, INFO, WARNING, ERROR, CRITICAL]
ERROR: database.postgres.pool_size must be between 1 and 100
```

## Hot Reload Support

Some configuration changes can be applied without restart:

**Hot-Reloadable**:
- API rate limits
- Agent pool size
- Logging level
- Monitoring settings

**Requires Restart**:
- Database connections
- LLM provider changes
- Security settings
- Core platform settings

To reload configuration:
```bash
# Send SIGHUP signal to reload
kill -HUP <pid>

# Or use the API endpoint
curl -X POST http://localhost:8000/api/v1/admin/reload-config \
  -H "Authorization: Bearer $TOKEN"
```

## Configuration Best Practices

### Security

1. **Never commit secrets**: Use environment variables for sensitive data
2. **Use strong JWT secrets**: Generate with `openssl rand -hex 32`
3. **Enable encryption**: Set `security.encryption.at_rest` and `in_transit` to `true`
4. **Restrict CORS**: Only allow trusted origins in `api.cors.origins`
5. **Enable rate limiting**: Protect against abuse with `api.rate_limit.enabled`

### Performance

1. **Tune connection pools**: Adjust `database.postgres.pool_size` based on load
2. **Configure Milvus indexes**: Choose appropriate `index_type` for data volume
3. **Enable caching**: Use Redis for frequently accessed data
4. **Optimize agent pool**: Set `agents.pool.min_size` based on typical load
5. **Batch operations**: Use `memory.embedding.batch_size` for bulk operations

### Reliability

1. **Enable backups**: Set `deployment.backup.enabled` to `true`
2. **Configure retries**: Set appropriate `*.retry.max_attempts` values
3. **Set timeouts**: Configure reasonable timeout values
4. **Enable health checks**: Monitor component health with `monitoring.health.enabled`
5. **Configure alerting**: Set up alerts for critical issues

### Scalability

1. **Enable partitioning**: Use `database.milvus.enable_partitioning` for large datasets
2. **Configure autoscaling**: Set `deployment.kubernetes.enable_autoscaling` for K8s
3. **Optimize resource limits**: Balance `agents.resources.*` for your workload
4. **Use parallel execution**: Enable `task_management.execution.enable_parallel`
5. **Tune worker counts**: Adjust `api.workers` based on CPU cores

## Troubleshooting

### Configuration Not Loading

1. Check file path: Ensure `config.yaml` is in the correct location
2. Verify YAML syntax: Use a YAML validator
3. Check environment variables: Ensure all required variables are set
4. Review logs: Check startup logs for validation errors

### Performance Issues

1. Check connection pools: May need to increase pool sizes
2. Review resource limits: Agents may be resource-constrained
3. Check Milvus indexes: May need to rebuild or optimize indexes
4. Monitor metrics: Use Prometheus/Grafana to identify bottlenecks

### Security Warnings

1. Review security settings: Ensure encryption is enabled
2. Check container isolation: Verify security policies are applied
3. Audit access logs: Review `audit_logs` table for suspicious activity
4. Update secrets: Rotate JWT secrets and passwords regularly

## Example Configurations

### Minimal Development Setup

```yaml
platform:
  environment: "development"

api:
  port: 8000
  jwt:
    secret_key: "dev-secret"

database:
  postgres:
    host: "localhost"
    password: "dev_password"

llm:
  default_provider: "ollama"
  providers:
    ollama:
      enabled: true
      models:
        chat: "llama3:8b"  # Smaller model for dev
        embedding: "nomic-embed-text"
```

### Production Setup

```yaml
platform:
  environment: "production"
  debug: false

api:
  jwt:
    secret_key: "${JWT_SECRET}"
  rate_limit:
    enabled: true

security:
  encryption:
    at_rest: true
    in_transit: true
  data_classification:
    enabled: true

monitoring:
  prometheus:
    enabled: true
  logging:
    level: "WARNING"
  tracing:
    enabled: true

alerting:
  enabled: true
  channels:
    pagerduty:
      enabled: true

deployment:
  mode: "kubernetes"
  backup:
    enabled: true
```

### High-Performance Setup

```yaml
llm:
  default_provider: "vllm"
  providers:
    vllm:
      enabled: true
      gpu_memory_utilization: 0.9

agents:
  pool:
    min_size: 50
    max_size: 500

database:
  postgres:
    pool_size: 50
  milvus:
    index_type: "HNSW"
    enable_partitioning: true

task_management:
  execution:
    enable_parallel: true
    max_parallel_tasks: 50
```

## References

- [Requirements Document](../.kiro/specs/digital-workforce-platform/requirements.md)
- [Design Document](../.kiro/specs/digital-workforce-platform/design.md) - Section 16
- [Tasks Document](../.kiro/specs/digital-workforce-platform/tasks.md) - Task 1.1.3
