# Digital Workforce Management Platform - Project Structure

This document describes the directory structure of the Digital Workforce Management Platform.

## Overview

The project is organized into four main directories:
- **backend/** - Python backend services
- **frontend/** - React frontend application
- **infrastructure/** - Docker, Kubernetes, and deployment configurations
- **docs/** - Documentation files

## Directory Structure

```
digital-workforce-platform/
├── backend/                    # Python backend services
│   ├── api_gateway/           # FastAPI-based API Gateway
│   ├── task_manager/          # Hierarchical task management service
│   ├── agent_framework/       # LangChain-based agent implementation
│   ├── memory_system/         # Multi-tiered memory management
│   ├── knowledge_base/        # Knowledge Base and Document Processor
│   ├── access_control/        # Authentication and authorization
│   ├── llm_providers/         # LLM provider integrations (Ollama, vLLM, etc.)
│   ├── skill_library/         # Reusable agent capabilities
│   ├── virtualization/        # Container management for agents
│   ├── shared/                # Shared utilities, models, and common code
│   └── tests/                 # Backend tests (unit, integration, e2e)
│
├── frontend/                   # React frontend application
│   ├── src/                   # Source code
│   │   ├── api/              # API client and service layer
│   │   ├── components/       # Reusable React components
│   │   ├── pages/            # Page components (Dashboard, Workforce, Tasks, etc.)
│   │   ├── hooks/            # Custom React hooks
│   │   ├── types/            # TypeScript type definitions
│   │   ├── styles/           # Global styles and theme configuration
│   │   └── utils/            # Utility functions and helpers
│   └── public/               # Static assets (images, icons, etc.)
│
├── infrastructure/             # Deployment and infrastructure
│   ├── docker/               # Docker configurations and Dockerfiles
│   ├── kubernetes/           # Kubernetes manifests for production
│   ├── monitoring/           # Monitoring configurations (Prometheus, Grafana)
│   └── scripts/              # Deployment and setup scripts
│
└── docs/                       # Documentation
    ├── api/                   # API documentation
    ├── architecture/          # Architecture diagrams and documentation
    ├── deployment/            # Deployment and installation guides
    ├── developer/             # Developer documentation and contribution guide
    └── user-guide/            # User manual and guides
```

## Backend Services

### api_gateway/
FastAPI-based API Gateway that provides:
- RESTful API endpoints for all platform operations
- JWT authentication middleware
- Rate limiting and request logging
- WebSocket support for real-time updates
- OpenAPI/Swagger documentation

### task_manager/
Hierarchical task management service responsible for:
- Goal submission and validation
- Task decomposition using LLM
- Agent assignment based on capabilities
- Task execution coordination
- Result aggregation

### agent_framework/
LangChain-based agent implementation including:
- BaseAgent class and agent lifecycle management
- Agent templates (Data Analyst, Content Writer, Code Assistant, etc.)
- Skill assignment and execution
- Agent registry and capability matching

### memory_system/
Multi-tiered memory management:
- Agent Memory (private to each agent)
- Company Memory (shared across agents)
- User Context (shared across user's agents)
- Vector database integration (Milvus)
- Semantic similarity search

### knowledge_base/
Knowledge Base and Document Processor:
- Document upload and storage (MinIO)
- Text extraction (PDF, DOCX, TXT, MD)
- OCR for images
- Audio/video transcription
- Document chunking and embedding generation
- Knowledge indexing and retrieval

### access_control/
Authentication and authorization system:
- User authentication (JWT)
- Role-Based Access Control (RBAC)
- Attribute-Based Access Control (ABAC)
- Permission policy management
- Audit logging

### llm_providers/
LLM provider integrations:
- Ollama (primary local provider)
- vLLM (high-performance local provider)
- OpenAI (optional cloud fallback)
- Anthropic (optional cloud fallback)
- Provider routing and fallback logic
- Embedding generation service

### skill_library/
Reusable agent capabilities:
- Skill registration and validation
- Skill versioning
- Default skills (data_processing, sql_query, etc.)
- Skill execution wrapper
- Dynamic skill generation

### virtualization/
Container management for agent isolation:
- Docker container provisioning
- Resource limits enforcement (CPU, memory)
- Sandbox selection (gVisor, Firecracker, Docker Enhanced)
- Container health monitoring
- Cleanup and resource release

### shared/
Shared utilities and common code:
- Database models and schemas
- Configuration management
- Logging utilities
- Common exceptions
- Helper functions

### tests/
Backend testing:
- Unit tests for individual components
- Integration tests for service interactions
- End-to-end tests for complete workflows
- Performance and load tests
- Security tests

## Frontend Application

### src/api/
API client and service layer:
- HTTP client configuration
- API endpoint definitions
- WebSocket client for real-time updates
- Request/response interceptors
- Error handling

### src/components/
Reusable React components:
- Glass panel components (glassmorphism design)
- Agent cards
- Task cards
- Charts and visualizations
- Form components
- Navigation components

### src/pages/
Page components:
- Dashboard (metrics and overview)
- Workforce Management (agent management)
- Task Manager (goal submission and task flow)
- Knowledge Base (document management)
- Memory System (memory browsing)
- Settings

### src/hooks/
Custom React hooks:
- useAuth (authentication state)
- useWebSocket (real-time updates)
- useTheme (theme management)
- useApi (API calls with loading/error states)

### src/types/
TypeScript type definitions:
- API response types
- Component prop types
- State types
- Utility types

### src/styles/
Global styles and theme:
- TailwindCSS configuration
- Theme definitions (light/dark)
- Global CSS
- Animation definitions

### src/utils/
Utility functions:
- Date formatting
- Data transformations
- Validation helpers
- Constants

## Infrastructure

### docker/
Docker configurations:
- Dockerfiles for each service
- Docker Compose files (development, staging)
- .dockerignore files
- Build scripts

### kubernetes/
Kubernetes manifests:
- Deployment manifests
- Service definitions
- Ingress configuration
- ConfigMaps and Secrets
- PersistentVolumeClaims
- HorizontalPodAutoscaler
- RuntimeClass for gVisor

### monitoring/
Monitoring configurations:
- Prometheus configuration
- Grafana dashboards
- Alert rules
- Exporters configuration

### scripts/
Deployment and setup scripts:
- Installation scripts (Linux, macOS, Windows)
- Database migration scripts
- Backup and restore scripts
- Health check scripts

## Documentation

### api/
API documentation:
- OpenAPI/Swagger specifications
- Endpoint descriptions
- Request/response examples
- Authentication guide

### architecture/
Architecture documentation:
- System architecture diagrams
- Component interaction diagrams
- Data flow diagrams
- Security architecture

### deployment/
Deployment guides:
- Installation instructions
- Configuration guide
- Platform-specific setup (Linux, macOS, Windows)
- Troubleshooting guide

### developer/
Developer documentation:
- Development setup
- Coding standards
- Contribution guidelines
- Testing guidelines
- API development guide

### user-guide/
User manual:
- Getting started guide
- Feature documentation
- Best practices
- FAQ
- Troubleshooting

## Technology Stack

### Backend
- **Language**: Python 3.11+
- **Framework**: FastAPI
- **Agent Framework**: LangChain
- **Databases**: PostgreSQL (primary), Milvus (vector), Redis (message bus)
- **Object Storage**: MinIO
- **LLM Providers**: Ollama, vLLM, OpenAI, Anthropic

### Frontend
- **Framework**: React 19
- **Language**: TypeScript
- **Build Tool**: Vite
- **Styling**: TailwindCSS
- **Icons**: Lucide React
- **Charts**: Recharts
- **Flow Diagrams**: React Flow

### Infrastructure
- **Containerization**: Docker
- **Orchestration**: Kubernetes (production), Docker Compose (development)
- **Monitoring**: Prometheus, Grafana
- **Tracing**: Jaeger (OpenTelemetry)
- **Logging**: ELK Stack or Loki

## References

- **Requirements**: `.kiro/specs/digital-workforce-platform/requirements.md`
- **Design**: `.kiro/specs/digital-workforce-platform/design.md`
- **Tasks**: `.kiro/specs/digital-workforce-platform/tasks.md`

## Next Steps

1. Initialize Python backend project with Poetry/pip requirements (Task 1.1.2)
2. Create config.yaml structure (Task 1.1.3)
3. Set up database schemas (Tasks 1.2.x)
4. Initialize React frontend project (Task 6.1.1)
5. Create Docker configurations (Tasks 1.6.x)

---

**Note**: This structure follows the design specified in Requirements 20 and Design Section 16 of the Digital Workforce Management Platform specification.
