# System Architecture

This document describes the architecture of LinX (灵枢) intelligent collaboration platform.

## Table of Contents

1. [Overview](#overview)
2. [Architecture Principles](#architecture-principles)
3. [System Components](#system-components)
4. [Data Flow](#data-flow)
5. [Technology Stack](#technology-stack)
6. [Deployment Architecture](#deployment-architecture)
7. [Security Architecture](#security-architecture)
8. [Scalability](#scalability)

## Overview

LinX (灵枢) is a microservices-based system for managing AI agents and automating complex tasks through intelligent task decomposition and agent collaboration.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend                             │
│                    (React + TypeScript)                      │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTPS/WebSocket
┌────────────────────────┴────────────────────────────────────┐
│                      API Gateway                             │
│              (FastAPI + Authentication)                      │
└─────┬──────────┬──────────┬──────────┬──────────┬──────────┘
      │          │          │          │          │
      ▼          ▼          ▼          ▼          ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│  Task    │ │  Agent   │ │Knowledge │ │  Memory  │ │  Access  │
│ Manager  │ │Framework │ │   Base   │ │  System  │ │ Control  │
└────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
     │            │            │            │            │
     └────────────┴────────────┴────────────┴────────────┘
                              │
     ┌────────────────────────┴────────────────────────┐
     │                                                  │
     ▼                  ▼              ▼               ▼
┌──────────┐      ┌──────────┐  ┌──────────┐    ┌──────────┐
│PostgreSQL│      │  Redis   │  │  MinIO   │    │  Milvus  │
│(Metadata)│      │(Message) │  │(Storage) │    │(Vectors) │
└──────────┘      └──────────┘  └──────────┘    └──────────┘
```

## Architecture Principles

### 1. Microservices

**Benefits**:
- Independent deployment
- Technology flexibility
- Fault isolation
- Scalability

**Services**:
- API Gateway
- Task Manager
- Agent Framework
- Knowledge Base
- Memory System
- Access Control

### 2. Event-Driven

**Message Bus** (Redis):
- Pub/Sub for broadcasts
- Streams for point-to-point
- Asynchronous communication
- Loose coupling

### 3. Data-Centric

**Multiple Data Stores**:
- PostgreSQL: Operational data
- Milvus: Vector embeddings
- MinIO: Object storage
- Redis: Caching and messaging

### 4. Security by Design

**Layers**:
- Authentication (JWT)
- Authorization (RBAC/ABAC)
- Encryption (at rest and in transit)
- Isolation (containers, sandboxes)
- Audit logging

## System Components

### Frontend

**Technology**: React 19 + TypeScript + Vite

**Features**:
- Glassmorphism UI design
- Real-time updates (WebSocket)
- Responsive layout
- Internationalization (i18n)
- PWA support

**Components**:
- Dashboard
- Workforce Management
- Task Manager
- Knowledge Base
- Memory Browser

### API Gateway

**Technology**: FastAPI + Python 3.11

**Responsibilities**:
- Request routing
- Authentication/Authorization
- Rate limiting
- Request logging
- Error handling
- WebSocket management

**Endpoints**:
- `/api/v1/auth/*` - Authentication
- `/api/v1/users/*` - User management
- `/api/v1/agents/*` - Agent management
- `/api/v1/tasks/*` - Task management
- `/api/v1/knowledge/*` - Knowledge base
- `/api/v1/memory/*` - Memory system
- `/ws` - WebSocket

### Task Manager

**Technology**: Python + LangChain

**Responsibilities**:
- Goal analysis
- Task decomposition
- Agent assignment
- Dependency resolution
- Progress tracking
- Result aggregation

**Workflow**:
1. Receive goal from user
2. Analyze and clarify (if needed)
3. Decompose into sub-tasks
4. Map capabilities to agents
5. Execute tasks (sequential/parallel)
6. Aggregate results
7. Return to user

### Agent Framework

**Technology**: LangChain + Python

**Components**:
- BaseAgent: Core agent class
- AgentRegistry: Agent management
- AgentTemplate: Pre-configured types
- AgentExecutor: Task execution
- AgentTools: Skill integration

**Agent Types**:
- Data Analyst
- Content Writer
- Code Assistant
- Research Assistant
- Custom agents

### Knowledge Base

**Technology**: Python + Tesseract + Whisper

**Pipeline**:
1. **Upload**: File validation
2. **Process**: Text extraction/OCR/Transcription
3. **Chunk**: Split into 512-token chunks
4. **Embed**: Generate vector embeddings
5. **Index**: Store in Milvus
6. **Search**: Semantic similarity search

**Supported Formats**:
- Documents: PDF, DOCX, TXT, MD
- Images: PNG, JPG (OCR)
- Audio: MP3, WAV (transcription)
- Video: MP4, AVI (audio extraction)

### Memory System

**Technology**: Milvus + Python

**Reset-Era Architecture**:

1. **User Memory**:
   - Long-term user facts and profile projections
   - Built from session-ledger extraction
   - Retrieved for personalization

2. **Skill Learning**:
   - Agent-owned successful paths and reusable execution methods
   - Reviewed before publication
   - Retrieved as runtime skills, not as generic memory

3. **Knowledge Base**:
   - Shared documents and reference knowledge
   - Retrieved independently from user memory

**Operations**:
- Store memory
- Retrieve by similarity
- Share between agents
- Archive old memories

### Access Control

**Technology**: Python + JWT + PostgreSQL

**Components**:
- Authentication (JWT)
- RBAC (Role-Based Access Control)
- ABAC (Attribute-Based Access Control)
- Permission filtering
- Audit logging

**Roles**:
- Admin: Full access
- Manager: User/agent management
- User: Create agents/tasks
- Viewer: Read-only

### Virtualization

**Technology**: Docker + gVisor + Firecracker

**Sandbox Selection**:
1. gVisor (Linux, highest security)
2. Firecracker (Linux with KVM)
3. Docker Enhanced (all platforms)

**Features**:
- Container isolation
- Resource limits
- Network restrictions
- Code execution sandbox
- Security monitoring

## Data Flow

### Task Submission Flow

```
User → API Gateway → Task Manager
                         ↓
                    Goal Analysis
                         ↓
                  Task Decomposition
                         ↓
                   Agent Assignment
                         ↓
              ┌──────────┴──────────┐
              ▼                     ▼
         Agent 1                Agent 2
              ↓                     ↓
         Execute                Execute
              ↓                     ↓
              └──────────┬──────────┘
                         ▼
                  Result Aggregation
                         ↓
                    API Gateway
                         ↓
                       User
```

### Document Processing Flow

```
User → API Gateway → Knowledge Base
                         ↓
                   File Validation
                         ↓
                   Text Extraction
                         ↓
                      Chunking
                         ↓
                   Embedding (LLM)
                         ↓
                   Indexing (Milvus)
                         ↓
                    API Gateway
                         ↓
                       User
```

### Memory Storage Flow

```
Agent → Memory System
           ↓
      Classify Product
           ↓
    ┌──────┴──────┐
    ▼             ▼
User Memory   Skill Learning
    ↓             ↓
Generate      Generate
Embedding     Embedding
    ↓             ↓
Store in      Store in
Milvus        Milvus
(partition)   (partition)
```

## Technology Stack

### Backend

- **Language**: Python 3.11+
- **Framework**: FastAPI
- **Agent Framework**: LangChain
- **ORM**: SQLAlchemy
- **Migrations**: Alembic
- **Async**: asyncio, asyncpg

### Frontend

- **Framework**: React 19
- **Language**: TypeScript
- **Build Tool**: Vite
- **Styling**: TailwindCSS
- **State**: Zustand
- **Routing**: React Router
- **Charts**: Recharts
- **Flow**: React Flow

### Databases

- **PostgreSQL 16**: Operational data
- **Milvus 2.3**: Vector embeddings
- **Redis 7**: Message bus, caching
- **MinIO**: Object storage

### LLM Providers

- **Ollama**: Primary (local)
- **vLLM**: High-performance (local)
- **OpenAI**: Optional (cloud)
- **Anthropic**: Optional (cloud)

### Infrastructure

- **Containers**: Docker
- **Orchestration**: Kubernetes
- **Sandbox**: gVisor, Firecracker
- **Monitoring**: Prometheus, Grafana
- **Logging**: Loki, ELK
- **CI/CD**: GitHub Actions

## Deployment Architecture

### Development

```
Developer Machine
├── Backend (uvicorn --reload)
├── Frontend (npm run dev)
└── Infrastructure (docker-compose)
    ├── PostgreSQL
    ├── Redis
    ├── MinIO
    ├── Milvus
    └── Ollama
```

### Staging/Production (Docker Compose)

```
Single Server
├── Nginx (Reverse Proxy)
├── API Gateway (Docker)
├── Task Manager (Docker)
├── Document Processor (Docker)
├── Frontend (Docker)
└── Infrastructure (Docker)
    ├── PostgreSQL
    ├── Redis
    ├── MinIO
    └── Milvus
```

### Production (Kubernetes)

```
Kubernetes Cluster
├── Ingress (NGINX)
├── Frontend (Deployment, HPA)
├── API Gateway (Deployment, HPA)
├── Task Manager (Deployment, HPA)
├── Document Processor (Deployment, HPA)
└── Data Layer (StatefulSets)
    ├── PostgreSQL
    ├── Redis
    ├── MinIO
    └── Milvus
```

## Security Architecture

### Defense in Depth

**Layers**:
1. **Network**: Firewall, segmentation
2. **Application**: Authentication, authorization
3. **Data**: Encryption at rest and in transit
4. **Container**: Isolation, resource limits
5. **Sandbox**: gVisor, Firecracker
6. **Monitoring**: Audit logs, alerts

### Authentication Flow

```
User → Login → API Gateway
                   ↓
              Verify Credentials
                   ↓
              Generate JWT
                   ↓
              Return Token
                   ↓
User stores token
                   ↓
Subsequent requests include token
                   ↓
API Gateway validates token
                   ↓
Check permissions (RBAC/ABAC)
                   ↓
Allow/Deny request
```

### Data Encryption

**At Rest**:
- PostgreSQL: TDE or disk encryption
- Milvus: File encryption
- MinIO: Server-side encryption (SSE)

**In Transit**:
- TLS 1.2+ for all connections
- Certificate-based authentication
- Strong cipher suites

## Scalability

### Horizontal Scaling

**Stateless Services** (can scale freely):
- API Gateway
- Task Manager
- Document Processor
- Frontend

**Stateful Services** (require coordination):
- PostgreSQL (read replicas)
- Redis (cluster mode)
- Milvus (distributed mode)
- MinIO (distributed mode)

### Vertical Scaling

**Resource Limits**:
```yaml
resources:
  requests:
    cpu: 1
    memory: 2Gi
  limits:
    cpu: 4
    memory: 8Gi
```

### Auto-Scaling

**Kubernetes HPA**:
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-gateway-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-gateway
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

### Performance Targets

- **API Response Time**: <200ms (p95)
- **Task Decomposition**: <5s
- **Document Processing**: <30s per document
- **Vector Search**: <100ms
- **Concurrent Agents**: 100+
- **Throughput**: 1000+ tasks/hour

## Future Enhancements

### Planned Features

1. **Robot Integration**:
   - ROS integration
   - Physical task execution
   - Sensor data processing

2. **Advanced Analytics**:
   - Agent performance metrics
   - Cost optimization
   - Predictive analytics

3. **Multi-Tenancy**:
   - Tenant isolation
   - Resource quotas per tenant
   - Tenant-specific branding

4. **Federation**:
   - Multi-cluster deployment
   - Cross-cluster agent collaboration
   - Distributed task execution

## References

- [API Documentation](../api/api-documentation.md)
- [Deployment Guide](../deployment/kubernetes-deployment.md)
- [Security Best Practices](../deployment/security-best-practices.md)
- [Developer Guide](../developer/developer-guide.md)
