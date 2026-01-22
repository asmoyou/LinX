# Design Document: LinX (灵枢) Intelligent Collaboration Platform

## 1. Overview

### 1.1 Purpose

This document specifies the technical design for LinX (灵枢) - an enterprise intelligent collaboration system for managing and coordinating AI agents and future robotic workers. The platform establishes a digital company structure enabling autonomous goal completion through hierarchical task management, collaborative agent coordination, and comprehensive knowledge management.

### 1.2 Design Principles

1. **Privacy-First Architecture**: All sensitive data processing occurs on-premise with local LLM deployment
2. **Scalable Modularity**: Components are loosely coupled and horizontally scalable
3. **Agent Autonomy**: Agents operate independently within defined boundaries with minimal human intervention
4. **Future-Ready**: Architecture supports seamless integration of robotic agents alongside digital agents
5. **Enterprise-Grade Security**: Multi-layered security with encryption, isolation, and comprehensive access control

### 1.3 Technology Stack

- **Agent Framework**: LangChain for agent orchestration and tool integration
- **Primary Database**: PostgreSQL for operational data (agents, tasks, users, permissions)
- **Vector Database**: Milvus for semantic search and memory embeddings
- **Object Storage**: MinIO for documents, audio, video, and agent artifacts
- **Message Bus**: Redis/RabbitMQ for inter-agent communication
- **LLM Providers**: Ollama (primary), vLLM (high-performance), with optional cloud fallback
- **Containerization**: Docker for agent isolation and deployment
- **Code Execution**: gVisor for secure sandboxed code execution, Firecracker for microVM isolation
- **Orchestration**: Docker Compose (development), Kubernetes (production)
- **API Layer**: FastAPI for RESTful services and WebSocket support


## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         API Gateway Layer                        │
│                    (FastAPI + WebSocket)                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
┌───────▼────────┐  ┌────────▼────────┐  ┌───────▼────────┐
│  Task Manager  │  │ Agent Framework │  │ Access Control │
│   Component    │  │   (LangChain)   │  │     System     │
└───────┬────────┘  └────────┬────────┘  └───────┬────────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
┌───────▼────────┐  ┌────────▼────────┐  ┌───────▼────────┐
│ Memory System  │  │  Knowledge Base │  │  Skill Library │
│  (Multi-Tier)  │  │   & Document    │  │                │
│                │  │    Processor    │  │                │
└───────┬────────┘  └────────┬────────┘  └────────────────┘
        │                    │
        └────────────────────┼────────────────────┐
                             │                    │
        ┌────────────────────┼────────────────────┼────────┐
        │                    │                    │        │
┌───────▼────────┐  ┌────────▼────────┐  ┌───────▼──────┐ │
│   PostgreSQL   │  │     Milvus      │  │    MinIO     │ │
│   (Primary)    │  │    (Vector)     │  │   (Object)   │ │
└────────────────┘  └─────────────────┘  └──────────────┘ │
                                                           │
┌──────────────────────────────────────────────────────────▼──┐
│              Message Bus (Redis/RabbitMQ)                   │
└─────────────────────────────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
┌───────▼────────┐  ┌────────▼────────┐  ┌───────▼────────┐
│  Agent Pool    │  │  Agent Pool    │  │  Agent Pool    │
│  (Container 1) │  │  (Container 2) │  │  (Container N) │
└────────────────┘  └─────────────────┘  └────────────────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  LLM Providers  │
                    │ (Ollama/vLLM)   │
                    └─────────────────┘
```

### 2.2 Component Responsibilities


#### API Gateway
- Authenticates users via JWT tokens
- Routes requests to appropriate backend services
- Provides RESTful endpoints for all platform operations
- Manages WebSocket connections for real-time task flow updates
- Implements rate limiting and request logging
- Serves OpenAPI/Swagger documentation

#### Task Manager
- Accepts and validates high-level goals from users
- Generates clarifying questions when goals are ambiguous
- Decomposes goals into hierarchical task structures
- Assigns tasks to agents based on capability matching
- Coordinates multi-agent collaboration through shared context
- Aggregates results from completed sub-tasks
- Handles task reassignment on agent failure

#### Agent Framework (LangChain)
- Manages agent lifecycle (creation, initialization, termination)
- Provides agent registry with capability metadata
- Assigns skills from Skill Library based on task requirements
- Executes agent logic with access to tools and memory
- Returns structured results to Task Manager
- Supports multiple agent types with different capability profiles

#### Access Control System
- Authenticates user accounts
- Loads and enforces permission policies (RBAC/ABAC)
- Associates agents with owning users
- Filters Knowledge Base results based on user permissions
- Enforces memory access controls (Agent Memory, Company Memory, User Context)
- Supports extensible permission policy framework

#### Memory System (Multi-Tier)
- Provisions Agent Memory for individual agents
- Manages Company Memory for collaborative context
- Maintains User Context within Company Memory for cross-agent information sharing
- Stores and retrieves embeddings via Milvus Vector Database
- Performs semantic similarity search for relevant memories
- Enforces data isolation between Agent Memory instances
- Ranks results by relevance and recency

#### Knowledge Base & Document Processor
- Stores enterprise documents, policies, and domain knowledge
- Extracts text from PDF, DOCX, TXT, MD files
- Performs OCR on images with text
- Transcribes audio and video files using local speech recognition
- Chunks large documents for efficient embedding generation
- Indexes knowledge for efficient retrieval
- Stores extracted content in Milvus with metadata

#### Skill Library
- Stores reusable agent capabilities as discrete modules
- Validates skill interfaces and dependencies
- Provides skills to agents on demand
- Supports custom skill development

#### Message Bus
- Delivers inter-agent messages reliably
- Supports publish-subscribe for broadcasting
- Supports point-to-point for direct communication
- Queues messages for unavailable agents
- Enforces access control on messaging
- Logs all messages for audit

#### Virtualization System
- Creates isolated Docker containers for each agent
- Enforces resource limits (CPU, memory, network)
- Prevents access to resources outside container
- Cleans up resources on agent termination
- Detects and terminates unresponsive agents

#### LLM Providers
- Routes requests to local Ollama instances by default
- Supports vLLM for high-performance scenarios
- Provides optional cloud fallback (OpenAI, Anthropic)
- Prevents external data transmission in private mode
- Implements retry logic with fallback
- Supports multiple models for different tasks


## 3. Data Architecture

### 3.1 Database Design

#### PostgreSQL Schema (Primary Database)

**users**
- user_id (UUID, PK)
- username (VARCHAR, UNIQUE)
- email (VARCHAR, UNIQUE)
- password_hash (VARCHAR)
- role (VARCHAR) - for RBAC
- attributes (JSONB) - for ABAC
- created_at (TIMESTAMP)
- updated_at (TIMESTAMP)

**agents**
- agent_id (UUID, PK)
- name (VARCHAR)
- agent_type (VARCHAR) - template type
- owner_user_id (UUID, FK → users)
- capabilities (JSONB) - list of skills
- status (VARCHAR) - active, idle, terminated
- container_id (VARCHAR)
- created_at (TIMESTAMP)
- updated_at (TIMESTAMP)

**tasks**
- task_id (UUID, PK)
- goal_text (TEXT)
- parent_task_id (UUID, FK → tasks, nullable)
- assigned_agent_id (UUID, FK → agents, nullable)
- status (VARCHAR) - pending, in_progress, completed, failed
- priority (INTEGER)
- dependencies (JSONB) - array of task_ids
- result (JSONB)
- created_by_user_id (UUID, FK → users)
- created_at (TIMESTAMP)
- completed_at (TIMESTAMP)

**skills**
- skill_id (UUID, PK)
- name (VARCHAR, UNIQUE)
- description (TEXT)
- interface_definition (JSONB)
- dependencies (JSONB)
- version (VARCHAR)
- created_at (TIMESTAMP)

**permissions**
- permission_id (UUID, PK)
- user_id (UUID, FK → users)
- resource_type (VARCHAR) - knowledge, memory, agent
- resource_id (UUID)
- access_level (VARCHAR) - read, write, admin
- created_at (TIMESTAMP)

**knowledge_items**
- knowledge_id (UUID, PK)
- title (VARCHAR)
- content_type (VARCHAR) - document, policy, domain_knowledge
- file_reference (VARCHAR) - MinIO object key
- owner_user_id (UUID, FK → users)
- access_level (VARCHAR) - private, team, public
- metadata (JSONB)
- created_at (TIMESTAMP)
- updated_at (TIMESTAMP)

**agent_templates**
- template_id (UUID, PK)
- name (VARCHAR, UNIQUE)
- description (TEXT)
- default_skills (JSONB) - array of skill_ids
- default_config (JSONB)
- version (INTEGER)
- created_at (TIMESTAMP)

**resource_quotas**
- quota_id (UUID, PK)
- user_id (UUID, FK → users)
- max_agents (INTEGER)
- max_storage_gb (INTEGER)
- max_cpu_cores (INTEGER)
- max_memory_gb (INTEGER)
- current_agents (INTEGER)
- current_storage_gb (DECIMAL)

**audit_logs**
- log_id (UUID, PK)
- user_id (UUID, FK → users, nullable)
- agent_id (UUID, FK → agents, nullable)
- action (VARCHAR)
- resource_type (VARCHAR)
- resource_id (UUID)
- details (JSONB)
- timestamp (TIMESTAMP)


#### Milvus Collections (Vector Database)

**agent_memories**
- id (INT64, PK, auto-increment)
- agent_id (VARCHAR)
- embedding (FLOAT_VECTOR, dim=768 or 1024)
- content (VARCHAR)
- timestamp (INT64)
- metadata (JSON) - {task_id, importance, tags}
- Indexes: IVF_FLAT or HNSW for similarity search
- Partitions: By agent_id for efficient filtering

**company_memories**
- id (INT64, PK, auto-increment)
- user_id (VARCHAR) - for User Context filtering
- embedding (FLOAT_VECTOR, dim=768 or 1024)
- content (VARCHAR)
- memory_type (VARCHAR) - user_context, task_context, general
- timestamp (INT64)
- metadata (JSON) - {task_id, shared_with, tags}
- Indexes: IVF_FLAT or HNSW
- Partitions: By user_id and memory_type

**knowledge_embeddings**
- id (INT64, PK, auto-increment)
- knowledge_id (VARCHAR) - references PostgreSQL knowledge_items
- chunk_index (INT32)
- embedding (FLOAT_VECTOR, dim=768 or 1024)
- content (VARCHAR)
- owner_user_id (VARCHAR)
- access_level (VARCHAR)
- metadata (JSON) - {document_title, page_number, section}
- Indexes: IVF_FLAT or HNSW
- Partitions: By access_level for permission filtering

#### MinIO Bucket Structure

**documents/** - User-uploaded documents
- {user_id}/{task_id}/{filename}
- Versioning enabled

**audio/** - Audio files and transcriptions
- {user_id}/{task_id}/{filename}
- Metadata includes transcription status

**video/** - Video files and extracted audio
- {user_id}/{task_id}/{filename}
- Metadata includes processing status

**images/** - Image files
- {user_id}/{task_id}/{filename}
- Metadata includes OCR status

**agent-artifacts/** - Agent-generated outputs
- {agent_id}/{task_id}/{artifact_name}
- Temporary files cleaned after task completion

**backups/** - System backups
- {backup_type}/{timestamp}/

### 3.2 Data Flow Patterns

#### Goal Submission Flow
1. User submits goal via API Gateway
2. API Gateway authenticates user and creates task record in PostgreSQL
3. Task Manager receives goal and analyzes requirements
4. If clarification needed, Task Manager returns questions to user
5. Once clarified, Task Manager decomposes into sub-tasks (PostgreSQL)
6. Task Manager assigns tasks to agents based on capability matching
7. Agents execute tasks with access to Memory System and Knowledge Base
8. Results aggregated and stored in PostgreSQL task.result
9. Final result delivered to user via API Gateway

#### Memory Storage Flow
1. Agent processes information during task execution
2. Agent determines if information is user-specific or task-specific
3. Agent generates embedding using local LLM
4. Memory System stores embedding in appropriate Milvus collection
5. Metadata stored in PostgreSQL for indexing
6. User Context memories tagged for cross-agent access

#### Knowledge Ingestion Flow
1. User uploads document via API Gateway
2. File stored in MinIO with unique key
3. Document Processor extracts text/metadata
4. Large documents chunked for embedding generation
5. Embeddings generated using local LLM
6. Embeddings stored in Milvus knowledge_embeddings collection
7. Metadata stored in PostgreSQL knowledge_items table
8. Access permissions applied based on user role


## 4. Agent Framework Design

### 4.1 Agent Architecture

Each agent is a LangChain-based autonomous entity with:
- **Identity**: Unique agent_id, name, and owner_user_id
- **Capabilities**: Set of skills from Skill Library
- **Memory**: Access to Agent Memory (private) and Company Memory (shared)
- **Tools**: LangChain tools for interacting with external systems
- **Execution Environment**: Isolated Docker container

### 4.2 Agent Types and Templates

**Data Analyst Agent**
- Skills: data_processing, statistical_analysis, visualization, sql_query
- Tools: pandas, matplotlib, database_connector
- Use Case: Analyze datasets, generate reports, create visualizations

**Content Writer Agent**
- Skills: writing, editing, summarization, translation
- Tools: grammar_checker, style_analyzer, plagiarism_detector
- Use Case: Create articles, edit documents, summarize content

**Code Assistant Agent**
- Skills: code_generation, debugging, code_review, testing
- Tools: code_executor, linter, test_runner, git_interface
- Use Case: Write code, debug issues, review pull requests

**Research Assistant Agent**
- Skills: information_gathering, web_search, summarization, citation
- Tools: web_scraper, search_engine, document_analyzer
- Use Case: Gather information, research topics, compile reports

**Custom Agent**
- Skills: User-defined skill combinations
- Tools: Configurable based on requirements
- Use Case: Specialized tasks requiring unique capability combinations

### 4.3 Agent Lifecycle

**Creation Phase**
1. User selects template or custom configuration
2. Agent Framework validates skill requirements
3. PostgreSQL agent record created with status='initializing'
4. Virtualization System provisions Docker container
5. Agent Memory provisioned in Milvus
6. Skills loaded from Skill Library
7. Agent status updated to 'active'

**Execution Phase**
1. Task Manager assigns task to agent
2. Agent retrieves task details from PostgreSQL
3. Agent queries Memory System for relevant context
4. Agent queries Knowledge Base for domain information
5. Agent executes task using LangChain reasoning loop
6. Agent stores intermediate results in Agent Memory
7. Agent returns final result to Task Manager

**Termination Phase**
1. Administrator initiates agent retirement
2. Agent completes current task or gracefully interrupts
3. Agent Memory archived to cold storage (MinIO)
4. Container terminated and resources released
5. PostgreSQL agent status updated to 'terminated'
6. Audit log entry created

### 4.4 Skill System

Skills are modular capabilities that can be attached to agents. Each skill defines:
- **Interface**: Input/output schema
- **Implementation**: Python function or LangChain tool
- **Dependencies**: Required libraries or external services
- **Permissions**: Required access levels

Example Skill Definition:
```python
{
  "skill_id": "uuid",
  "name": "sql_query",
  "description": "Execute SQL queries against databases",
  "interface": {
    "input": {"query": "string", "database": "string"},
    "output": {"results": "array", "row_count": "integer"}
  },
  "implementation": "skills.database.sql_query",
  "dependencies": ["psycopg2", "sqlalchemy"],
  "required_permissions": ["database.read"]
}
```


## 5. Code Execution Environment and Security Isolation

### 5.1 Multi-Layer Isolation Architecture

The platform implements a defense-in-depth approach for code execution with multiple isolation layers:

```
┌─────────────────────────────────────────────────────────────┐
│                    Host Operating System                     │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Kubernetes / Docker Host                  │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │         Agent Container (Docker)                 │  │  │
│  │  │  ┌───────────────────────────────────────────┐  │  │  │
│  │  │  │    Code Execution Sandbox                 │  │  │  │
│  │  │  │    (gVisor or Firecracker microVM)        │  │  │  │
│  │  │  │  ┌─────────────────────────────────────┐ │  │  │  │
│  │  │  │  │  User-Generated Code Execution      │ │  │  │  │
│  │  │  │  │  - Python interpreter               │ │  │  │  │
│  │  │  │  │  - JavaScript runtime               │ │  │  │  │
│  │  │  │  │  - Code generation & execution      │ │  │  │  │
│  │  │  │  └─────────────────────────────────────┘ │  │  │  │
│  │  │  │                                           │  │  │  │
│  │  │  │  Resource Limits:                        │  │  │  │
│  │  │  │  - CPU: 0.5 cores                        │  │  │  │
│  │  │  │  - Memory: 512MB                         │  │  │  │
│  │  │  │  - Execution timeout: 30s                │  │  │  │
│  │  │  │  - Network: Restricted                   │  │  │  │
│  │  │  └───────────────────────────────────────────┘  │  │  │
│  │  │                                                  │  │  │
│  │  │  Agent Runtime Environment:                     │  │  │
│  │  │  - LangChain agent logic                        │  │  │
│  │  │  - Skill execution                              │  │  │
│  │  │  - Memory access                                │  │  │
│  │  │  - API communication                            │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Code Execution Sandbox Technologies

**Cross-Platform Compatibility Strategy**:

The platform implements a tiered sandbox approach with automatic fallback based on platform capabilities:

```
Priority 1: gVisor (Linux + Kubernetes)
    ↓ (if unavailable)
Priority 2: Firecracker (Linux with KVM)
    ↓ (if unavailable)
Priority 3: Docker + Enhanced Security (All platforms)
```

#### Option 1: gVisor (Linux Only - Recommended for Kubernetes)

**Platform Requirements**:
- **Supported**: Linux (kernel 4.14+)
- **Not Supported**: macOS, Windows
- **Automatic Detection**: Platform checks gVisor availability at startup

**Architecture**:
- User-space kernel that intercepts system calls
- Runs inside Docker container as additional isolation layer
- Provides strong isolation without full VM overhead

**Implementation**:
```yaml
# Kubernetes RuntimeClass for gVisor
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: gvisor
handler: runsc

# Agent Pod with gVisor
apiVersion: v1
kind: Pod
metadata:
  name: agent-code-executor
spec:
  runtimeClassName: gvisor
  containers:
  - name: code-sandbox
    image: agent-code-executor:latest
    securityContext:
      runAsNonRoot: true
      runAsUser: 1000
      allowPrivilegeEscalation: false
      capabilities:
        drop: ["ALL"]
      readOnlyRootFilesystem: true
```

**Security Features**:
- System call filtering and interception
- Limited access to host kernel
- Network namespace isolation
- Filesystem isolation with read-only root
- Resource limits enforced at sandbox level

**Performance**:
- Overhead: ~10-15% compared to native
- Startup time: ~100-200ms
- Suitable for short-lived code execution tasks

**Availability Check**:
```python
def is_gvisor_available() -> bool:
    """Check if gVisor is available on the system"""
    try:
        # Check if runsc binary exists
        result = subprocess.run(['which', 'runsc'], 
                              capture_output=True, 
                              timeout=1)
        if result.returncode != 0:
            return False
        
        # Check if Docker supports gVisor runtime
        result = subprocess.run(['docker', 'info', '--format', '{{.Runtimes}}'],
                              capture_output=True,
                              timeout=2)
        return 'runsc' in result.stdout.decode()
    except Exception:
        return False
```

#### Option 2: Firecracker microVMs (Linux with KVM - High Security)

**Platform Requirements**:
- **Supported**: Linux with KVM support
- **Not Supported**: macOS, Windows, Linux without KVM
- **Automatic Detection**: Platform checks KVM availability

**Architecture**:
- Lightweight microVM using KVM
- Each code execution runs in isolated VM
- Minimal guest kernel (4.5MB)

**Implementation**:
```python
# Firecracker VM configuration for code execution
{
  "boot-source": {
    "kernel_image_path": "/var/firecracker/vmlinux",
    "boot_args": "console=ttyS0 reboot=k panic=1"
  },
  "drives": [{
    "drive_id": "rootfs",
    "path_on_host": "/var/firecracker/rootfs.ext4",
    "is_root_device": true,
    "is_read_only": true
  }],
  "machine-config": {
    "vcpu_count": 1,
    "mem_size_mib": 512,
    "ht_enabled": false
  },
  "network-interfaces": [{
    "iface_id": "eth0",
    "guest_mac": "AA:FC:00:00:00:01",
    "host_dev_name": "tap0"
  }]
}
```

**Security Features**:
- Hardware-level isolation via KVM
- Minimal attack surface (minimal guest kernel)
- No shared kernel with host
- Strong memory isolation
- Secure boot support

**Performance**:
- Overhead: ~20-30% compared to native
- Startup time: ~125ms (cold start)
- Suitable for sensitive code execution

**Availability Check**:
```python
def is_firecracker_available() -> bool:
    """Check if Firecracker is available on the system"""
    try:
        # Check if KVM is available
        if not os.path.exists('/dev/kvm'):
            return False
        
        # Check if firecracker binary exists
        result = subprocess.run(['which', 'firecracker'],
                              capture_output=True,
                              timeout=1)
        return result.returncode == 0
    except Exception:
        return False
```

#### Option 3: Docker + Enhanced Security (Cross-Platform Fallback)

**Platform Requirements**:
- **Supported**: Linux, macOS, Windows
- **Use Case**: Development environments, non-Linux production, fallback mode

**Architecture**:
- Standard Docker container with enhanced security profiles
- Seccomp for system call filtering (Linux)
- AppArmor/SELinux for mandatory access control (Linux)
- Resource limits enforced by Docker
- Network isolation via Docker networks

**Implementation**:
```json
// Seccomp profile for code execution (Linux)
{
  "defaultAction": "SCMP_ACT_ERRNO",
  "architectures": ["SCMP_ARCH_X86_64", "SCMP_ARCH_AARCH64"],
  "syscalls": [
    {
      "names": ["read", "write", "open", "close", "stat", "fstat",
                "mmap", "munmap", "brk", "rt_sigaction", "exit_group",
                "access", "execve", "getpid", "getuid", "getgid"],
      "action": "SCMP_ACT_ALLOW"
    }
  ]
}
```

```yaml
# Docker Compose configuration with enhanced security
version: '3.8'
services:
  code-executor:
    image: agent-code-executor:latest
    security_opt:
      - no-new-privileges:true
      - seccomp=./seccomp-profile.json  # Linux only
      - apparmor=docker-default          # Linux only
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETUID
      - SETGID
    read_only: true
    tmpfs:
      - /tmp:size=50M,mode=1777
      - /output:size=10M,mode=1777
    networks:
      - isolated-network
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 256M
```

**Security Features**:
- System call whitelist (only safe syscalls allowed) - Linux only
- Dropped capabilities (CAP_NET_RAW, CAP_SYS_ADMIN, etc.)
- Read-only root filesystem
- No new privileges flag
- Network isolation via Docker networks
- Resource limits enforced by Docker (all platforms)

**Performance**:
- Overhead: ~5% compared to native
- Startup time: ~50ms
- Suitable for development and cross-platform deployment

**Platform-Specific Behavior**:
- **Linux**: Full security features (Seccomp, AppArmor, capabilities)
- **macOS**: Docker Desktop VM isolation + resource limits
- **Windows**: Hyper-V or WSL2 isolation + resource limits

### 5.3 Automatic Sandbox Selection

**Sandbox Selection Logic**:

```python
from enum import Enum
import platform
import logging

class SandboxType(Enum):
    GVISOR = "gvisor"
    FIRECRACKER = "firecracker"
    DOCKER_ENHANCED = "docker_enhanced"

class SandboxSelector:
    """Automatically select best available sandbox technology"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._detected_sandbox = None
    
    def detect_best_sandbox(self) -> SandboxType:
        """
        Detect and return the best available sandbox technology
        
        Priority:
        1. gVisor (if Linux + Kubernetes + gVisor available)
        2. Firecracker (if Linux + KVM available)
        3. Docker Enhanced (fallback for all platforms)
        """
        if self._detected_sandbox:
            return self._detected_sandbox
        
        system = platform.system()
        
        # Check gVisor (Linux only)
        if system == "Linux":
            if self._is_gvisor_available():
                self.logger.info("Using gVisor sandbox (highest security)")
                self._detected_sandbox = SandboxType.GVISOR
                return self._detected_sandbox
            
            # Check Firecracker (Linux with KVM)
            if self._is_firecracker_available():
                self.logger.info("Using Firecracker sandbox (high security)")
                self._detected_sandbox = SandboxType.FIRECRACKER
                return self._detected_sandbox
        
        # Fallback to Docker Enhanced (all platforms)
        self.logger.info(
            f"Using Docker Enhanced sandbox on {system} "
            f"(gVisor/Firecracker not available)"
        )
        self._detected_sandbox = SandboxType.DOCKER_ENHANCED
        return self._detected_sandbox
    
    def _is_gvisor_available(self) -> bool:
        """Check if gVisor is available"""
        try:
            result = subprocess.run(
                ['docker', 'info', '--format', '{{.Runtimes}}'],
                capture_output=True,
                timeout=2,
                text=True
            )
            return 'runsc' in result.stdout
        except Exception as e:
            self.logger.debug(f"gVisor check failed: {e}")
            return False
    
    def _is_firecracker_available(self) -> bool:
        """Check if Firecracker is available"""
        try:
            # Check KVM
            if not os.path.exists('/dev/kvm'):
                return False
            
            # Check firecracker binary
            result = subprocess.run(
                ['which', 'firecracker'],
                capture_output=True,
                timeout=1
            )
            return result.returncode == 0
        except Exception as e:
            self.logger.debug(f"Firecracker check failed: {e}")
            return False
    
    def get_sandbox_config(self, sandbox_type: SandboxType) -> dict:
        """Get configuration for specified sandbox type"""
        configs = {
            SandboxType.GVISOR: {
                "runtime": "runsc",
                "security_level": "high",
                "overhead": "10-15%",
                "startup_time_ms": 150,
                "platform": "linux"
            },
            SandboxType.FIRECRACKER: {
                "runtime": "firecracker",
                "security_level": "very_high",
                "overhead": "20-30%",
                "startup_time_ms": 125,
                "platform": "linux"
            },
            SandboxType.DOCKER_ENHANCED: {
                "runtime": "docker",
                "security_level": "medium",
                "overhead": "5%",
                "startup_time_ms": 50,
                "platform": "all"
            }
        }
        return configs[sandbox_type]

# Global sandbox selector
sandbox_selector = SandboxSelector()
```

**Configuration File Support**:

```yaml
# config.yaml - Sandbox configuration
code_execution:
  # Sandbox selection mode
  sandbox_mode: "auto"  # auto, gvisor, firecracker, docker
  
  # Fallback behavior
  fallback_enabled: true
  fallback_to_docker: true
  
  # Platform-specific overrides
  platform_overrides:
    linux:
      preferred: "gvisor"
      fallback: ["firecracker", "docker"]
    darwin:  # macOS
      preferred: "docker"
      fallback: []
    windows:
      preferred: "docker"
      fallback: []
  
  # Security warnings
  warn_on_fallback: true
  require_minimum_security: "medium"  # low, medium, high, very_high
```

### 5.4 Code Execution Workflow

**Dynamic Code Generation and Execution**:

```python
class CodeExecutionSandbox:
    """Secure sandbox for executing agent-generated code"""
    
    def __init__(self, sandbox_type="auto"):
        # Auto-detect best sandbox if not specified
        if sandbox_type == "auto":
            self.sandbox_type = sandbox_selector.detect_best_sandbox()
        else:
            self.sandbox_type = SandboxType(sandbox_type)
        
        self.config = sandbox_selector.get_sandbox_config(self.sandbox_type)
        self.timeout = 30  # seconds
        self.max_memory = 512 * 1024 * 1024  # 512MB
        self.max_cpu_time = 10  # seconds
        
        logging.info(
            f"CodeExecutionSandbox initialized with {self.sandbox_type.value} "
            f"(security: {self.config['security_level']})"
        )
    
    async def execute_code(self, code: str, language: str, 
                          context: dict) -> ExecutionResult:
        """
        Execute user-generated code in isolated sandbox
        
        Args:
            code: Source code to execute
            language: Programming language (python, javascript, etc.)
            context: Execution context and input data
        
        Returns:
            ExecutionResult with output, errors, and resource usage
        """
        # 1. Validate code (static analysis)
        validation_result = await self.validate_code(code, language)
        if not validation_result.safe:
            raise SecurityException(validation_result.issues)
        
        # 2. Create isolated sandbox environment
        sandbox_id = await self.create_sandbox(self.sandbox_type)
        
        try:
            # 3. Inject code and context into sandbox
            await self.inject_code(sandbox_id, code, context)
            
            # 4. Execute with resource limits and timeout
            result = await self.run_with_limits(
                sandbox_id,
                timeout=self.timeout,
                max_memory=self.max_memory,
                max_cpu_time=self.max_cpu_time
            )
            
            # 5. Collect output and metrics
            output = await self.collect_output(sandbox_id)
            metrics = await self.collect_metrics(sandbox_id)
            
            return ExecutionResult(
                success=True,
                output=output,
                metrics=metrics,
                sandbox_id=sandbox_id
            )
            
        except TimeoutException:
            await self.kill_sandbox(sandbox_id)
            raise ExecutionTimeoutException()
            
        except MemoryException:
            await self.kill_sandbox(sandbox_id)
            raise ExecutionMemoryException()
            
        finally:
            # 6. Cleanup sandbox
            await self.destroy_sandbox(sandbox_id)
    
    async def validate_code(self, code: str, language: str) -> ValidationResult:
        """Static analysis to detect dangerous patterns"""
        dangerous_patterns = [
            r'import\s+os',  # OS access
            r'import\s+subprocess',  # Process execution
            r'import\s+socket',  # Network access
            r'eval\s*\(',  # Dynamic evaluation
            r'exec\s*\(',  # Dynamic execution
            r'__import__',  # Dynamic imports
            r'open\s*\(',  # File access
        ]
        
        issues = []
        for pattern in dangerous_patterns:
            if re.search(pattern, code):
                issues.append(f"Dangerous pattern detected: {pattern}")
        
        return ValidationResult(
            safe=len(issues) == 0,
            issues=issues
        )
```

**Execution Flow**:

1. **Code Generation Phase**:
   - Agent uses LLM to generate code for specific task
   - Code stored temporarily in Agent Memory
   - Code reviewed by validation system

2. **Validation Phase**:
   - Static analysis for dangerous patterns
   - Syntax checking
   - Dependency verification
   - Security policy compliance check

3. **Sandbox Creation Phase**:
   - Provision isolated execution environment (gVisor/Firecracker)
   - Apply resource limits (CPU, memory, network)
   - Mount read-only filesystem with required libraries
   - Configure network restrictions

4. **Execution Phase**:
   - Inject code into sandbox
   - Execute with timeout and resource monitoring
   - Capture stdout, stderr, and return values
   - Monitor resource usage in real-time

5. **Result Collection Phase**:
   - Collect execution output
   - Gather performance metrics
   - Log execution for audit
   - Store results in Agent Memory

6. **Cleanup Phase**:
   - Terminate sandbox environment
   - Release resources
   - Archive execution logs
   - Update task status

### 5.5 Runtime Security Policies

**Network Restrictions**:
```yaml
# Network policy for code execution sandbox
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: code-sandbox-netpol
spec:
  podSelector:
    matchLabels:
      role: code-executor
  policyTypes:
  - Ingress
  - Egress
  egress:
  # Allow DNS
  - to:
    - namespaceSelector:
        matchLabels:
          name: kube-system
    ports:
    - protocol: UDP
      port: 53
  # Allow internal API access only
  - to:
    - podSelector:
        matchLabels:
          role: api-gateway
    ports:
    - protocol: TCP
      port: 8000
  # Block all other egress
  ingress: []  # No ingress allowed
```

**Resource Quotas**:
```python
SANDBOX_RESOURCE_LIMITS = {
    "cpu": {
        "default": "0.5",  # 0.5 CPU cores
        "max": "2.0",      # Maximum 2 cores for complex tasks
    },
    "memory": {
        "default": "512Mi",  # 512MB
        "max": "2Gi",        # Maximum 2GB
    },
    "execution_time": {
        "default": 30,   # 30 seconds
        "max": 300,      # 5 minutes for complex tasks
    },
    "disk_io": {
        "read_bps": "10Mi",   # 10MB/s read
        "write_bps": "5Mi",   # 5MB/s write
    },
    "network": {
        "bandwidth": "1Mi",   # 1MB/s
        "connections": 5,     # Max 5 concurrent connections
    }
}
```

**Filesystem Restrictions**:
```python
SANDBOX_FILESYSTEM_CONFIG = {
    "root": {
        "path": "/sandbox",
        "readonly": True,
        "size": "100Mi"
    },
    "tmp": {
        "path": "/tmp",
        "readonly": False,
        "size": "50Mi",
        "cleanup_on_exit": True
    },
    "output": {
        "path": "/output",
        "readonly": False,
        "size": "10Mi"
    },
    "blocked_paths": [
        "/proc",
        "/sys",
        "/dev",
        "/host",
        "/var/run/docker.sock"
    ]
}
```

### 5.6 Skill Generation and Dynamic Programming

**On-the-Fly Skill Creation**:

```python
class DynamicSkillGenerator:
    """Generate and execute skills dynamically based on task requirements"""
    
    async def generate_skill(self, task_description: str, 
                            examples: List[str]) -> Skill:
        """
        Generate a new skill from task description
        
        Args:
            task_description: Natural language description of required skill
            examples: Example inputs/outputs for the skill
        
        Returns:
            Executable Skill object
        """
        # 1. Use LLM to generate skill code
        prompt = f"""
        Generate a Python function to accomplish this task:
        {task_description}
        
        Examples:
        {examples}
        
        Requirements:
        - Function must be pure (no side effects)
        - No external network access
        - No file system access
        - Use only standard library
        - Include type hints
        - Include docstring
        """
        
        generated_code = await self.llm.generate(prompt)
        
        # 2. Validate generated code
        validation = await self.code_validator.validate(generated_code)
        if not validation.safe:
            # Retry with safety constraints
            generated_code = await self.regenerate_safe_code(
                task_description, validation.issues
            )
        
        # 3. Test in sandbox
        test_results = await self.test_skill_in_sandbox(
            generated_code, examples
        )
        
        if not test_results.passed:
            raise SkillGenerationException(
                f"Generated skill failed tests: {test_results.errors}"
            )
        
        # 4. Create skill object
        skill = Skill(
            name=self.generate_skill_name(task_description),
            code=generated_code,
            interface=self.extract_interface(generated_code),
            validation_status="tested",
            created_at=datetime.now()
        )
        
        # 5. Store in Skill Library for reuse
        await self.skill_library.store(skill)
        
        return skill
    
    async def execute_dynamic_skill(self, skill: Skill, 
                                   input_data: dict) -> Any:
        """Execute dynamically generated skill in sandbox"""
        
        sandbox = CodeExecutionSandbox(sandbox_type="gvisor")
        
        # Wrap skill code with input/output handling
        execution_code = f"""
import json

{skill.code}

# Load input
with open('/input/data.json', 'r') as f:
    input_data = json.load(f)

# Execute skill
result = {skill.entry_point}(**input_data)

# Save output
with open('/output/result.json', 'w') as f:
    json.dump(result, f)
"""
        
        result = await sandbox.execute_code(
            code=execution_code,
            language="python",
            context={"input": input_data}
        )
        
        return result.output
```

**Skill Caching and Reuse**:
- Generated skills stored in Skill Library
- Semantic search to find similar existing skills
- Version control for skill evolution
- Performance metrics tracked for optimization

### 5.7 Security Monitoring and Incident Response

**Real-Time Monitoring**:
```python
class SandboxMonitor:
    """Monitor sandbox execution for security violations"""
    
    async def monitor_execution(self, sandbox_id: str):
        """Real-time monitoring of sandbox behavior"""
        
        monitors = [
            self.monitor_system_calls(sandbox_id),
            self.monitor_network_activity(sandbox_id),
            self.monitor_resource_usage(sandbox_id),
            self.monitor_file_access(sandbox_id)
        ]
        
        async for event in self.aggregate_events(monitors):
            if event.severity == "critical":
                # Immediate termination
                await self.kill_sandbox(sandbox_id)
                await self.alert_security_team(event)
                
            elif event.severity == "high":
                # Log and alert
                await self.log_security_event(event)
                await self.alert_security_team(event)
                
            elif event.severity == "medium":
                # Log for analysis
                await self.log_security_event(event)
```

**Incident Response**:
1. **Detection**: Real-time monitoring detects anomaly
2. **Containment**: Sandbox immediately terminated
3. **Analysis**: Execution logs analyzed for root cause
4. **Remediation**: Security policies updated
5. **Recovery**: Agent restarted with enhanced restrictions

### 5.8 Performance Optimization

**Sandbox Pool Management**:
```python
class SandboxPool:
    """Pre-warmed sandbox pool for fast execution"""
    
    def __init__(self, pool_size=10):
        self.pool_size = pool_size
        self.available_sandboxes = asyncio.Queue()
        self.active_sandboxes = {}
    
    async def initialize_pool(self):
        """Pre-create sandboxes for fast allocation"""
        for _ in range(self.pool_size):
            sandbox = await self.create_sandbox()
            await self.available_sandboxes.put(sandbox)
    
    async def acquire_sandbox(self) -> str:
        """Get sandbox from pool or create new one"""
        try:
            sandbox_id = await asyncio.wait_for(
                self.available_sandboxes.get(),
                timeout=1.0
            )
            return sandbox_id
        except asyncio.TimeoutError:
            # Pool exhausted, create new sandbox
            return await self.create_sandbox()
    
    async def release_sandbox(self, sandbox_id: str):
        """Return sandbox to pool or destroy if pool full"""
        if self.available_sandboxes.qsize() < self.pool_size:
            await self.reset_sandbox(sandbox_id)
            await self.available_sandboxes.put(sandbox_id)
        else:
            await self.destroy_sandbox(sandbox_id)
```

**Caching Strategies**:
- Compiled code caching for repeated executions
- Dependency pre-loading in sandbox images
- Result caching for deterministic functions
- Warm sandbox pool for common languages


## 6. Memory System Design

### 6.1 Memory Hierarchy

**Agent Memory (Private)**
- Scope: Single agent instance
- Purpose: Store agent-specific context, learned patterns, task history
- Access: Only the owning agent
- Storage: Milvus agent_memories collection
- Retention: Archived on agent termination

**Company Memory (Shared)**
- Scope: All agents within permission boundaries
- Purpose: Enable collaboration, share insights, store organizational knowledge
- Access: All authorized agents based on user permissions
- Storage: Milvus company_memories collection
- Retention: Persistent with configurable archival policies

**User Context (Within Company Memory)**
- Scope: All agents owned by a specific user
- Purpose: Share user preferences, context, and information across user's agents
- Access: Agents owned by the same user
- Storage: Milvus company_memories collection with user_id filtering
- Retention: Persistent, tied to user account lifecycle

**Knowledge Base (Enterprise)**
- Scope: Platform-wide with access control
- Purpose: Store enterprise documents, policies, domain knowledge
- Access: Based on user permissions and document access levels
- Storage: Milvus knowledge_embeddings collection + MinIO for files
- Retention: Persistent with version control

### 6.2 Memory Operations

**Storage Operation**
1. Agent generates memory content (text)
2. Memory System determines memory type (agent/company/user_context)
3. Local LLM generates embedding vector
4. Embedding stored in appropriate Milvus collection with metadata
5. Reference stored in PostgreSQL for indexing

**Retrieval Operation**
1. Agent submits query (text)
2. Local LLM generates query embedding
3. Milvus performs vector similarity search with metadata filtering
4. Results ranked by similarity score and recency
5. Top-k results returned to agent with source metadata

**Sharing Operation**
1. User marks information as "share with all my agents"
2. Memory System stores in company_memories with memory_type='user_context'
3. user_id metadata enables filtering for user's agents
4. All user's agents can retrieve via semantic search

### 6.3 Embedding Strategy

**Model Selection**
- Primary: Local Ollama model (e.g., nomic-embed-text, mxbai-embed-large)
- Dimension: 768 or 1024 based on model
- Consistency: Same model for storage and retrieval

**Chunking Strategy**
- Documents: 512-token chunks with 50-token overlap
- Memories: Single embedding per memory item
- Large context: Hierarchical embeddings (summary + details)

**Index Configuration**
- Small datasets (<1M vectors): FLAT index for exact search
- Medium datasets (1M-10M): IVF_FLAT with nlist=1024
- Large datasets (>10M): HNSW with M=16, efConstruction=200


## 7. Task Management Design

### 7.1 Task Decomposition Algorithm

**Input**: High-level goal from user
**Output**: Hierarchical task tree with agent assignments

**Algorithm Steps**:
1. **Goal Analysis**: LLM analyzes goal to identify required capabilities
2. **Clarification**: If ambiguous, generate questions for user
3. **Decomposition**: Break goal into sub-goals using LLM reasoning
4. **Capability Mapping**: Match sub-goals to required skills
5. **Agent Assignment**: Select agents with matching capabilities
6. **Dependency Resolution**: Identify task dependencies and execution order
7. **Task Creation**: Store task tree in PostgreSQL with relationships

**Example Decomposition**:
```
Goal: "Analyze Q4 sales data and create a presentation"
├─ Task 1: Extract sales data from database [Data Analyst]
├─ Task 2: Perform statistical analysis [Data Analyst]
│  └─ Depends on: Task 1
├─ Task 3: Create visualizations [Data Analyst]
│  └─ Depends on: Task 2
├─ Task 4: Write presentation content [Content Writer]
│  └─ Depends on: Task 2, Task 3
└─ Task 5: Format and finalize presentation [Content Writer]
   └─ Depends on: Task 4
```

### 7.2 Task Execution Flow

**Sequential Execution**
- Tasks with dependencies execute in order
- Parent task waits for all child tasks to complete
- Results passed to dependent tasks via Company Memory

**Parallel Execution**
- Independent tasks execute concurrently
- Task Manager distributes across available agents
- Load balancing based on agent availability and resource usage

**Collaborative Execution**
- Multiple agents work on related tasks
- Shared context stored in Company Memory
- Inter-agent communication via Message Bus

### 7.3 Result Aggregation

**Aggregation Strategies**:
- **Concatenation**: Combine text outputs sequentially
- **Summarization**: LLM summarizes multiple outputs
- **Structured Merge**: Combine JSON/data structures
- **Voting**: Select best result from multiple attempts

**Aggregation Process**:
1. Task Manager collects results from completed sub-tasks
2. Determines aggregation strategy based on task type
3. Applies aggregation logic (may use LLM)
4. Stores aggregated result in parent task record
5. Triggers dependent tasks or returns to user

### 7.4 Error Handling and Recovery

**Failure Detection**
- Agent timeout (configurable per task type)
- Explicit error return from agent
- Container crash detected by Virtualization System

**Recovery Strategies**
- **Retry**: Attempt same task with same agent (max 3 attempts)
- **Reassign**: Assign task to different agent with same capabilities
- **Escalate**: Request user intervention for ambiguous failures
- **Partial Success**: Accept partial results if some sub-tasks succeed

**Failure Logging**
- All failures logged to audit_logs table
- Error details stored in task.result JSONB
- Alerts sent to administrators for critical failures


## 8. Security and Access Control Design

### 8.1 Authentication

**JWT-Based Authentication**
- Users authenticate with username/password
- API Gateway issues JWT token with claims: user_id, role, permissions
- Token expiration: 24 hours (configurable)
- Refresh token mechanism for extended sessions
- Token stored securely in HTTP-only cookies or Authorization header

### 8.2 Authorization Models

**Role-Based Access Control (RBAC)**
- Predefined roles: admin, manager, user, viewer
- Roles mapped to permission sets
- Users assigned one or more roles
- Permissions checked at API Gateway and component level

**Attribute-Based Access Control (ABAC)**
- Fine-grained permissions based on user attributes
- Attributes: department, clearance_level, project_membership
- Policies defined as rules: "user.department == resource.department"
- Evaluated dynamically at access time

### 8.3 Data Access Control

**Knowledge Base Access**
- Documents have access_level: private, team, public
- Private: Only owner can access
- Team: Users with matching department attribute
- Public: All authenticated users
- Milvus queries filtered by user permissions

**Memory Access**
- Agent Memory: Only owning agent
- Company Memory: All agents, filtered by user permissions
- User Context: Agents owned by same user
- Access enforced at Memory System component level

**Agent Access**
- Users can only view/control agents they own
- Admins can view all agents
- Managers can view agents in their department
- Agent registry queries filtered by user_id

### 8.4 Data Protection

**Encryption at Rest**
- PostgreSQL: Transparent Data Encryption (TDE) or disk encryption
- Milvus: Data files encrypted at filesystem level
- MinIO: Server-side encryption (SSE) enabled
- Encryption keys managed via key management service

**Encryption in Transit**
- All API communication over HTTPS/TLS 1.3
- Internal component communication over TLS
- Message Bus connections encrypted
- Database connections use SSL/TLS

**Data Classification**
- Automatic classification based on content analysis
- Levels: public, internal, confidential, restricted
- Classified data routed to local LLM only
- Audit logs track all classified data access

### 8.5 Container Isolation

**Security Boundaries**
- Each agent runs in isolated Docker container
- Containers use minimal base images (Alpine Linux)
- No privileged containers
- Read-only root filesystem where possible
- Dropped capabilities (CAP_NET_RAW, CAP_SYS_ADMIN, etc.)

**Resource Limits**
- CPU: Configurable per agent (default 1 core)
- Memory: Configurable per agent (default 2GB)
- Network: Rate limiting and firewall rules
- Disk I/O: Quota enforcement

**Network Isolation**
- Agents communicate only via Message Bus
- No direct container-to-container networking
- Outbound internet access blocked by default
- Whitelist for approved external services


## 9. LLM Integration Design

### 9.1 Provider Architecture

**Local Deployment (Primary)**
- **Ollama**: Default for development and small-scale deployments
  - Easy setup and model management
  - Supports multiple models concurrently
  - Models: llama3, mistral, codellama, nomic-embed-text
- **vLLM**: High-performance for production scale
  - Optimized inference with PagedAttention
  - Higher throughput and lower latency
  - GPU acceleration support

**Cloud Fallback (Optional)**
- OpenAI API for GPT-4/GPT-3.5
- Anthropic API for Claude models
- Only used when explicitly configured and for non-sensitive data
- Automatic fallback disabled by default for privacy

### 9.2 Model Selection Strategy

**Task-Specific Models**
- **Chat/Reasoning**: llama3:70b or mistral:7b
- **Code Generation**: codellama:13b or deepseek-coder
- **Embeddings**: nomic-embed-text or mxbai-embed-large
- **Summarization**: llama3:8b (faster, sufficient quality)
- **Translation**: aya:8b or llama3:70b

**Model Routing Logic**
1. Task Manager identifies task type
2. Selects appropriate model from configuration
3. Routes request to LLM Provider
4. LLM Provider selects available instance (load balancing)
5. Returns result to requesting component

### 9.3 Prompt Engineering

**System Prompts**
- Agent role definition and capabilities
- Task context and objectives
- Available tools and their usage
- Output format requirements
- Safety and ethical guidelines

**Few-Shot Examples**
- Task-specific examples stored in Knowledge Base
- Retrieved based on task similarity
- Injected into prompt for better performance

**Prompt Templates**
```python
AGENT_SYSTEM_PROMPT = """
You are a {agent_type} agent with the following capabilities: {skills}.
Your task is: {task_description}
You have access to these tools: {tools}
Always provide structured output in JSON format.
Prioritize accuracy and cite sources when using knowledge base information.
"""

TASK_DECOMPOSITION_PROMPT = """
Given the following goal: {goal}
Break it down into a hierarchical task structure.
For each task, identify:
1. Task description
2. Required skills
3. Dependencies on other tasks
4. Expected output format
Output as JSON with task tree structure.
"""
```

### 9.4 Context Management

**Context Window Optimization**
- Prioritize recent and relevant information
- Summarize older context to save tokens
- Use embeddings to retrieve only relevant memories
- Implement sliding window for long conversations

**Token Budget Allocation**
- System prompt: 20%
- Task context: 30%
- Retrieved memories: 25%
- Retrieved knowledge: 20%
- Output buffer: 5%


## 10. Scalability and Performance Design

### 10.1 Horizontal Scaling Strategy

**Component Scaling**
- **API Gateway**: Multiple instances behind load balancer (Nginx/HAProxy)
- **Task Manager**: Stateless, multiple instances with distributed locking (Redis)
- **Agent Pool**: Dynamic scaling based on task queue depth
- **LLM Providers**: Multiple Ollama/vLLM instances with load balancing
- **Databases**: Read replicas for PostgreSQL, Milvus cluster for high volume

**Scaling Triggers**
- Task queue depth > 50: Scale up agents
- API request rate > 1000 req/s: Scale up API Gateway
- CPU utilization > 70%: Scale up compute resources
- Memory utilization > 80%: Scale up memory or optimize

### 10.2 Performance Optimization

**Database Optimization**
- PostgreSQL connection pooling (PgBouncer)
- Indexed columns: user_id, agent_id, task_id, status, created_at
- Partitioning: tasks table by created_at (monthly partitions)
- Materialized views for complex queries

**Vector Search Optimization**
- Milvus index tuning based on data volume
- Partition pruning by user_id or timestamp
- Query result caching for common searches
- Batch embedding generation for bulk operations

**Caching Strategy**
- Redis cache for frequently accessed data
  - User permissions (TTL: 5 minutes)
  - Agent metadata (TTL: 10 minutes)
  - Knowledge Base results (TTL: 1 hour)
- Cache invalidation on data updates

**Async Processing**
- Task decomposition: Async with callback
- Document processing: Background job queue
- Embedding generation: Batch processing
- Result aggregation: Async with progress tracking

### 10.3 Resource Management

**Agent Pool Management**
- Minimum pool size: 10 agents
- Maximum pool size: 100 agents (configurable)
- Idle timeout: 5 minutes
- Warm pool: Pre-initialized agents for common types

**Container Orchestration**
- Kubernetes for production (HPA for auto-scaling)
- Docker Compose for development
- Resource requests and limits defined per agent type
- Pod affinity for co-locating related agents

**Database Connection Management**
- PostgreSQL: Max 100 connections, pooled via PgBouncer
- Milvus: Connection pooling with max 50 connections
- Redis: Connection pooling with max 20 connections
- Graceful connection handling with retries


## 11. Monitoring and Observability Design

### 11.1 Metrics Collection

**System Metrics**
- CPU, memory, disk, network utilization per component
- Container resource usage per agent
- Database connection pool statistics
- Message Bus queue depths and throughput

**Application Metrics**
- Task completion rate and duration
- Agent execution success/failure rate
- API request rate and latency (p50, p95, p99)
- LLM inference latency and token usage
- Memory System query latency
- Knowledge Base retrieval accuracy

**Business Metrics**
- Active users and agents
- Tasks created/completed per day
- Goal completion rate
- User satisfaction scores (if feedback collected)

**Metrics Stack**
- Prometheus for metrics collection
- Grafana for visualization
- Node Exporter for system metrics
- Custom exporters for application metrics

### 11.2 Logging Strategy

**Log Levels**
- ERROR: System failures, agent crashes, security violations
- WARN: Degraded performance, retry attempts, quota warnings
- INFO: Task lifecycle events, agent actions, API requests
- DEBUG: Detailed execution traces (development only)

**Structured Logging**
- JSON format for machine parsing
- Standard fields: timestamp, level, component, user_id, agent_id, task_id
- Correlation IDs for tracing requests across components

**Log Aggregation**
- Centralized logging with ELK stack (Elasticsearch, Logstash, Kibana)
- Or Loki + Grafana for lighter footprint
- Log retention: 30 days hot, 90 days cold, 1 year archive

**Audit Logging**
- All data access logged to audit_logs table
- Immutable audit trail
- Fields: user, action, resource, timestamp, result
- Compliance reporting capabilities

### 11.3 Alerting

**Alert Conditions**
- System: CPU > 90%, Memory > 95%, Disk > 85%
- Application: Error rate > 5%, Task failure rate > 10%
- Security: Failed auth attempts > 10/min, unauthorized access
- Business: Task queue depth > 100, Agent pool exhausted

**Alert Channels**
- Email for non-urgent alerts
- Slack/Teams for urgent alerts
- PagerDuty for critical incidents
- Dashboard notifications for operators

**Alert Routing**
- Critical: On-call engineer
- High: Team lead
- Medium: Team channel
- Low: Daily digest

### 11.4 Distributed Tracing

**Trace Implementation**
- OpenTelemetry for instrumentation
- Jaeger for trace storage and visualization
- Trace context propagation across components
- Sampling: 100% for errors, 10% for success

**Trace Spans**
- API request → Task Manager → Agent execution → LLM call
- Memory retrieval → Vector search → Result ranking
- Document upload → Processing → Embedding → Storage


## 12. API Design

### 12.1 RESTful Endpoints

**Authentication**
- POST /api/v1/auth/login - Authenticate user, return JWT
- POST /api/v1/auth/logout - Invalidate JWT
- POST /api/v1/auth/refresh - Refresh JWT token

**Users**
- GET /api/v1/users/me - Get current user profile
- PUT /api/v1/users/me - Update user profile
- GET /api/v1/users/{user_id}/quotas - Get resource quotas

**Agents**
- POST /api/v1/agents - Create new agent
- GET /api/v1/agents - List user's agents
- GET /api/v1/agents/{agent_id} - Get agent details
- PUT /api/v1/agents/{agent_id} - Update agent configuration
- DELETE /api/v1/agents/{agent_id} - Terminate agent
- GET /api/v1/agents/templates - List available templates

**Tasks**
- POST /api/v1/tasks - Submit new goal/task
- GET /api/v1/tasks - List user's tasks
- GET /api/v1/tasks/{task_id} - Get task details and status
- GET /api/v1/tasks/{task_id}/tree - Get hierarchical task structure
- POST /api/v1/tasks/{task_id}/clarify - Provide clarification answers
- DELETE /api/v1/tasks/{task_id} - Cancel task

**Knowledge Base**
- POST /api/v1/knowledge - Upload document
- GET /api/v1/knowledge - List knowledge items
- GET /api/v1/knowledge/{knowledge_id} - Get knowledge item
- PUT /api/v1/knowledge/{knowledge_id} - Update knowledge item
- DELETE /api/v1/knowledge/{knowledge_id} - Delete knowledge item
- POST /api/v1/knowledge/search - Search knowledge base

**Skills**
- GET /api/v1/skills - List available skills
- GET /api/v1/skills/{skill_id} - Get skill details
- POST /api/v1/skills - Create custom skill (admin only)

**Monitoring**
- GET /api/v1/metrics/system - Get system metrics
- GET /api/v1/metrics/agents - Get agent performance metrics
- GET /api/v1/metrics/tasks - Get task statistics

### 12.2 WebSocket Endpoints

**Real-Time Task Updates**
- WS /api/v1/ws/tasks/{task_id} - Subscribe to task status updates
- Messages: task_started, task_progress, task_completed, task_failed

**Real-Time Agent Status**
- WS /api/v1/ws/agents/{agent_id} - Subscribe to agent status updates
- Messages: agent_active, agent_idle, agent_error

**Task Flow Visualization**
- WS /api/v1/ws/tasks/{task_id}/flow - Real-time task flow updates
- Messages: task_created, agent_assigned, task_in_progress, task_completed

### 12.3 API Response Format

**Success Response**
```json
{
  "status": "success",
  "data": {
    // Response data
  },
  "metadata": {
    "timestamp": "2026-01-19T10:30:00Z",
    "request_id": "uuid"
  }
}
```

**Error Response**
```json
{
  "status": "error",
  "error": {
    "code": "INVALID_INPUT",
    "message": "Task description cannot be empty",
    "details": {
      "field": "description",
      "constraint": "required"
    }
  },
  "metadata": {
    "timestamp": "2026-01-19T10:30:00Z",
    "request_id": "uuid"
  }
}
```

### 12.4 Rate Limiting

**Limits by Endpoint**
- Authentication: 10 requests/minute per IP
- Task submission: 100 requests/hour per user
- Knowledge upload: 50 requests/hour per user
- General API: 1000 requests/hour per user
- WebSocket: 10 concurrent connections per user

**Rate Limit Headers**
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 950
X-RateLimit-Reset: 1642598400
```


## 13. Deployment Architecture

### 13.1 On-Premise Deployment

**Infrastructure Requirements**
- **Compute**: 32 CPU cores, 128GB RAM minimum
- **Storage**: 1TB SSD for databases, 5TB HDD for object storage
- **Network**: 10Gbps internal, 1Gbps external
- **GPU**: Optional, 2x NVIDIA A100 for vLLM acceleration

**Component Distribution**
```
Server 1 (Control Plane):
- API Gateway (2 instances)
- Task Manager (2 instances)
- PostgreSQL (primary)
- Redis (Message Bus)

Server 2 (Data Plane):
- Milvus (standalone or cluster)
- MinIO (distributed mode)
- PostgreSQL (read replica)

Server 3-N (Compute Plane):
- Agent containers (dynamic scaling)
- Ollama/vLLM instances
- Document Processor workers
```

**Network Architecture**
```
                    ┌─────────────┐
                    │ Load Balancer│
                    │   (Nginx)    │
                    └──────┬───────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
┌───────▼────────┐ ┌───────▼────────┐ ┌──────▼─────────┐
│  API Gateway   │ │  API Gateway   │ │   WebSocket    │
│   Instance 1   │ │   Instance 2   │ │     Server     │
└───────┬────────┘ └───────┬────────┘ └──────┬─────────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                    ┌──────▼───────┐
                    │ Internal LAN │
                    └──────┬───────┘
        ┌──────────────────┼──────────────────┐
        │                  │                  │
┌───────▼────────┐ ┌───────▼────────┐ ┌──────▼─────────┐
│   PostgreSQL   │ │     Milvus     │ │     MinIO      │
└────────────────┘ └────────────────┘ └────────────────┘
```

### 13.2 Docker Compose Configuration

**docker-compose.yml Structure**
```yaml
services:
  api-gateway:
    image: linx-platform/api-gateway:latest
    ports: ["8000:8000"]
    environment:
      - DATABASE_URL=postgresql://...
      - REDIS_URL=redis://...
    depends_on: [postgres, redis]
  
  task-manager:
    image: linx-platform/task-manager:latest
    environment:
      - DATABASE_URL=postgresql://...
      - MILVUS_HOST=milvus
    depends_on: [postgres, milvus]
  
  postgres:
    image: postgres:16
    volumes: ["postgres-data:/var/lib/postgresql/data"]
    environment:
      - POSTGRES_PASSWORD=${DB_PASSWORD}
  
  milvus:
    image: milvusdb/milvus:latest
    volumes: ["milvus-data:/var/lib/milvus"]
    environment:
      - ETCD_ENDPOINTS=etcd:2379
  
  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    volumes: ["minio-data:/data"]
  
  ollama:
    image: ollama/ollama:latest
    volumes: ["ollama-models:/root/.ollama"]
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
  
  redis:
    image: redis:7-alpine
    volumes: ["redis-data:/data"]
```

### 13.3 Kubernetes Deployment

**Namespace Structure**
- linx-platform-core: API Gateway, Task Manager
- linx-platform-data: Databases, storage
- linx-platform-agents: Agent containers
- linx-platform-llm: LLM providers

**Key Kubernetes Resources**
- Deployments: API Gateway, Task Manager, Document Processor
- StatefulSets: PostgreSQL, Milvus, Redis
- DaemonSets: Node monitoring agents
- Jobs: Database migrations, initial setup
- CronJobs: Cleanup tasks, backup jobs
- Services: Internal service discovery
- Ingress: External access with TLS termination
- ConfigMaps: Application configuration
- Secrets: Credentials and API keys
- PersistentVolumeClaims: Database and storage volumes

**Auto-Scaling Configuration**
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: agent-pool-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: agent-pool
  minReplicas: 10
  maxReplicas: 100
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Pods
    pods:
      metric:
        name: task_queue_depth
      target:
        type: AverageValue
        averageValue: "5"
```

### 13.4 Hybrid Deployment

**On-Premise Components** (Required)
- All data storage (PostgreSQL, Milvus, MinIO)
- All LLM providers (Ollama/vLLM)
- Agent execution environment
- Core platform services

**Optional Cloud Components**
- Monitoring and alerting (Grafana Cloud)
- Log aggregation (Elasticsearch Cloud)
- Backup storage (S3-compatible)
- Development/staging environments

**Data Flow Restrictions**
- No sensitive data transmitted to cloud
- Only metrics and logs (sanitized) sent to cloud monitoring
- Backups encrypted before cloud upload
- Cloud components cannot access on-premise data directly

### 13.5 Cross-Platform Deployment Considerations

**Development Environments**:

| Platform | Sandbox | Docker | Kubernetes | Notes |
|----------|---------|--------|------------|-------|
| Linux | gVisor/Firecracker/Docker | ✓ | ✓ | Full feature support |
| macOS | Docker Enhanced | ✓ | ✗ | Docker Desktop required |
| Windows | Docker Enhanced | ✓ | ✗ | Docker Desktop or WSL2 |

**Production Environments**:

| Platform | Recommended Sandbox | Deployment Method | Security Level |
|----------|-------------------|-------------------|----------------|
| Linux (Kubernetes) | gVisor | Kubernetes + gVisor RuntimeClass | High |
| Linux (Bare Metal) | Firecracker | Docker Compose + Firecracker | Very High |
| Linux (Standard) | Docker Enhanced | Docker Compose | Medium |
| macOS (Dev Only) | Docker Enhanced | Docker Compose | Medium |
| Windows (Dev Only) | Docker Enhanced | Docker Compose | Medium |

**Platform-Specific Setup**:

**Linux (Production)**:
```bash
# Install gVisor
curl -fsSL https://gvisor.dev/archive.key | sudo gpg --dearmor -o /usr/share/keyrings/gvisor-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main" | sudo tee /etc/apt/sources.list.d/gvisor.list
sudo apt-get update && sudo apt-get install -y runsc

# Configure Docker to use gVisor
sudo runsc install
sudo systemctl restart docker

# Verify
docker run --runtime=runsc hello-world
```

**macOS (Development)**:
```bash
# Install Docker Desktop
brew install --cask docker

# Start Docker Desktop
open -a Docker

# Platform will automatically use Docker Enhanced sandbox
# No additional configuration needed
```

**Windows (Development)**:
```powershell
# Install Docker Desktop with WSL2 backend
# Download from https://www.docker.com/products/docker-desktop

# Or use Chocolatey
choco install docker-desktop

# Platform will automatically use Docker Enhanced sandbox
# No additional configuration needed
```

**Automatic Platform Detection**:

The platform automatically detects the host OS and selects the appropriate sandbox:

```python
# Platform detection in startup
import platform

def initialize_platform():
    system = platform.system()
    
    if system == "Linux":
        print("✓ Linux detected - checking for gVisor/Firecracker")
        sandbox = sandbox_selector.detect_best_sandbox()
        print(f"✓ Using {sandbox.value} sandbox")
    
    elif system == "Darwin":  # macOS
        print("✓ macOS detected - using Docker Enhanced sandbox")
        print("⚠ Note: gVisor not available on macOS")
        sandbox = SandboxType.DOCKER_ENHANCED
    
    elif system == "Windows":
        print("✓ Windows detected - using Docker Enhanced sandbox")
        print("⚠ Note: gVisor not available on Windows")
        sandbox = SandboxType.DOCKER_ENHANCED
    
    else:
        raise PlatformNotSupportedException(f"Unsupported platform: {system}")
    
    return sandbox
```

**Security Recommendations by Platform**:

- **Linux Production**: Use gVisor or Firecracker for maximum security
- **Linux Development**: Docker Enhanced is acceptable for development
- **macOS Development**: Docker Enhanced only, not recommended for production
- **Windows Development**: Docker Enhanced only, not recommended for production

**Migration Path**:

1. **Development on macOS/Windows** → Docker Enhanced
2. **Staging on Linux** → Docker Enhanced (test compatibility)
3. **Production on Linux** → gVisor (deploy with enhanced security)


## 14. Document Processing Pipeline

### 14.1 Processing Workflow

**Upload Phase**
1. User uploads file via API Gateway
2. File validated (type, size, malware scan)
3. File stored in MinIO with unique key
4. Processing job queued in Redis
5. Upload confirmation returned to user

**Extraction Phase**
1. Document Processor worker picks up job
2. File retrieved from MinIO
3. Text extraction based on file type:
   - PDF: PyPDF2 or pdfplumber
   - DOCX: python-docx
   - TXT/MD: Direct read
   - Images: Tesseract OCR
   - Audio: Whisper (local) for transcription
   - Video: Extract audio → Whisper transcription
4. Metadata extraction (title, author, dates, etc.)
5. Text cleaning and normalization

**Chunking Phase**
1. Large documents split into chunks (512 tokens)
2. Overlap of 50 tokens between chunks
3. Chunk metadata: document_id, chunk_index, page_number
4. Hierarchical chunking for structured documents

**Embedding Phase**
1. Batch chunks for efficient processing
2. Generate embeddings using local LLM (Ollama)
3. Store embeddings in Milvus knowledge_embeddings collection
4. Store metadata in PostgreSQL knowledge_items table

**Indexing Phase**
1. Update Milvus index for new embeddings
2. Create full-text search index in PostgreSQL
3. Update knowledge base statistics
4. Notify requesting user of completion

### 14.2 Supported File Types

**Documents**
- PDF: Text extraction, OCR for scanned PDFs
- DOCX: Text, tables, images
- TXT: Plain text
- MD: Markdown with formatting preservation
- HTML: Text extraction, link preservation

**Audio**
- MP3, WAV, M4A, FLAC
- Transcription via Whisper (local deployment)
- Speaker diarization (optional)
- Timestamp alignment

**Video**
- MP4, AVI, MOV, MKV
- Audio extraction → transcription
- Frame extraction for visual analysis (future)
- Subtitle extraction if available

**Images**
- PNG, JPG, GIF, BMP
- OCR for text extraction
- Image description via vision model (future)
- Metadata extraction (EXIF)

### 14.3 Processing Optimization

**Parallel Processing**
- Multiple worker processes for concurrent jobs
- GPU acceleration for Whisper transcription
- Batch embedding generation

**Caching**
- Duplicate detection via content hash
- Reuse embeddings for identical content
- Cache OCR results

**Quality Control**
- Confidence scores for OCR results
- Transcription accuracy estimation
- Manual review queue for low-confidence results


## 15. Inter-Agent Communication

### 15.1 Message Bus Architecture

**Technology Choice: Redis Pub/Sub + Streams**
- Pub/Sub for broadcast messages
- Streams for reliable point-to-point messaging
- Persistence for message durability
- Consumer groups for load balancing

**Message Types**
- **Direct Message**: Agent A → Agent B
- **Broadcast**: Agent A → All agents in task
- **Request-Response**: Agent A requests info from Agent B
- **Event Notification**: Agent A notifies completion/status

### 15.2 Message Format

**Standard Message Structure**
```json
{
  "message_id": "uuid",
  "from_agent_id": "uuid",
  "to_agent_id": "uuid or null for broadcast",
  "task_id": "uuid",
  "message_type": "direct|broadcast|request|response|event",
  "payload": {
    "content": "message content",
    "data": {}
  },
  "timestamp": "2026-01-19T10:30:00Z",
  "correlation_id": "uuid for request-response pairing"
}
```

### 15.3 Communication Patterns

**Collaboration Pattern**
1. Agent A completes sub-task, stores result in Company Memory
2. Agent A broadcasts completion event to task channel
3. Agent B receives event, retrieves result from Company Memory
4. Agent B proceeds with dependent sub-task

**Request-Response Pattern**
1. Agent A needs information from Agent B
2. Agent A sends request message with correlation_id
3. Agent B processes request, sends response with same correlation_id
4. Agent A receives response, continues execution

**Coordination Pattern**
1. Task Manager broadcasts task assignments to agent channel
2. Agents subscribe to their assigned task channels
3. Agents report progress via event messages
4. Task Manager aggregates progress for user visibility

### 15.4 Access Control

**Message Authorization**
- Agents can only send messages within their assigned tasks
- Agents can only subscribe to channels they have permission for
- Message Bus validates sender identity via agent_id
- Audit log records all inter-agent messages


## 16. Configuration Management

### 16.1 Configuration Structure

**Configuration File: config.yaml**
```yaml
platform:
  name: "LinX Platform"
  version: "1.0.0"
  environment: "production"  # development, staging, production

api:
  host: "0.0.0.0"
  port: 8000
  cors_origins: ["https://workforce.company.com"]
  rate_limit:
    enabled: true
    requests_per_hour: 1000
  jwt:
    secret_key: "${JWT_SECRET}"
    expiration_hours: 24

database:
  postgres:
    host: "postgres"
    port: 5432
    database: "linx_platform"
    username: "platform_user"
    password: "${POSTGRES_PASSWORD}"
    pool_size: 20
    max_overflow: 10
  
  milvus:
    host: "milvus"
    port: 19530
    collection_prefix: "workforce_"
    index_type: "IVF_FLAT"
    metric_type: "L2"
    nlist: 1024
  
  redis:
    host: "redis"
    port: 6379
    password: "${REDIS_PASSWORD}"
    db: 0

storage:
  minio:
    endpoint: "minio:9000"
    access_key: "${MINIO_ACCESS_KEY}"
    secret_key: "${MINIO_SECRET_KEY}"
    secure: false
    buckets:
      documents: "documents"
      audio: "audio"
      video: "video"
      images: "images"
      artifacts: "agent-artifacts"

llm:
  default_provider: "ollama"
  providers:
    ollama:
      enabled: true
      host: "ollama"
      port: 11434
      models:
        chat: "llama3:70b"
        code: "codellama:13b"
        embedding: "nomic-embed-text"
        summarization: "llama3:8b"
    
    vllm:
      enabled: false
      host: "vllm"
      port: 8000
      models:
        chat: "meta-llama/Llama-3-70b"
    
    openai:
      enabled: false
      api_key: "${OPENAI_API_KEY}"
      models:
        chat: "gpt-4"
        embedding: "text-embedding-3-large"

agents:
  pool:
    min_size: 10
    max_size: 100
    idle_timeout_minutes: 5
  
  resources:
    default_cpu_cores: 1
    default_memory_gb: 2
    max_cpu_cores: 4
    max_memory_gb: 8
  
  templates:
    - name: "data_analyst"
      skills: ["data_processing", "statistical_analysis", "visualization"]
    - name: "content_writer"
      skills: ["writing", "editing", "summarization"]
    - name: "code_assistant"
      skills: ["code_generation", "debugging", "code_review"]
    - name: "research_assistant"
      skills: ["information_gathering", "web_search", "summarization"]

security:
  encryption:
    at_rest: true
    in_transit: true
  
  data_classification:
    enabled: true
    auto_classify: true
    levels: ["public", "internal", "confidential", "restricted"]
  
  container_isolation:
    drop_capabilities: ["NET_RAW", "SYS_ADMIN"]
    read_only_root: true
    no_new_privileges: true

monitoring:
  prometheus:
    enabled: true
    port: 9090
  
  logging:
    level: "INFO"  # DEBUG, INFO, WARN, ERROR
    format: "json"
    output: "stdout"
  
  tracing:
    enabled: true
    jaeger_endpoint: "jaeger:14268"
    sample_rate: 0.1

quotas:
  default:
    max_agents: 10
    max_storage_gb: 100
    max_cpu_cores: 10
    max_memory_gb: 20
```

### 16.2 Environment Variables

**Required Variables**
- JWT_SECRET: Secret key for JWT signing
- POSTGRES_PASSWORD: PostgreSQL password
- REDIS_PASSWORD: Redis password
- MINIO_ACCESS_KEY: MinIO access key
- MINIO_SECRET_KEY: MinIO secret key

**Optional Variables**
- OPENAI_API_KEY: OpenAI API key (if enabled)
- ANTHROPIC_API_KEY: Anthropic API key (if enabled)
- SMTP_PASSWORD: Email server password (for alerts)

### 16.3 Configuration Management

**Hot Reload Support**
- API rate limits
- Agent pool size
- Logging level
- Monitoring settings

**Restart Required**
- Database connections
- LLM provider changes
- Security settings
- Core platform settings

**Configuration Validation**
- Schema validation on startup
- Required field checks
- Type validation
- Range validation for numeric values


## 17. Future Robot Integration

### 17.1 Architecture Extension

**Robot Agent Interface**
```python
class RobotAgent(BaseAgent):
    """Extension of BaseAgent for physical robots"""
    
    def __init__(self, agent_id, capabilities, physical_location):
        super().__init__(agent_id, capabilities)
        self.physical_location = physical_location
        self.sensor_data = {}
        self.actuator_status = {}
    
    def execute_physical_task(self, task):
        """Execute task in physical world"""
        pass
    
    def update_sensor_data(self, sensor_readings):
        """Update internal state from sensors"""
        pass
    
    def get_physical_state(self):
        """Return current physical state"""
        pass
```

**Physical World State Storage**
- Extend Memory System to store sensor data
- Store robot location, orientation, battery level
- Store environmental conditions
- Store task execution history with physical outcomes

### 17.2 Task Type Extensions

**Physical Task Types**
- **Manipulation**: Pick, place, assemble objects
- **Navigation**: Move to location, patrol area
- **Inspection**: Visual inspection, sensor readings
- **Delivery**: Transport items between locations
- **Maintenance**: Perform routine maintenance tasks

**Hybrid Tasks**
- Digital agent analyzes data, robot agent executes physical action
- Robot agent collects data, digital agent processes and reports
- Coordinated tasks requiring both digital and physical capabilities

### 17.3 Integration Points

**Robot Control System Interface**
- ROS (Robot Operating System) integration
- MQTT for real-time command/telemetry
- REST API for high-level task assignment
- WebSocket for status streaming

**Safety and Compliance**
- Emergency stop mechanisms
- Collision avoidance
- Safety zone enforcement
- Compliance with robotics safety standards

**Monitoring Extensions**
- Robot health metrics (battery, temperature, errors)
- Task execution video recording
- Physical world state visualization
- Incident reporting and analysis


## 18. User Interface Design

### 18.1 Design System and Visual Style

**Design Philosophy**:
- **Modern Glassmorphism**: Inspired by Apple's design language with frosted glass panels
- **Minimalist Aesthetics**: Clean, spacious layouts with purposeful use of whitespace
- **Smooth Animations**: Fluid transitions and micro-interactions for enhanced UX
- **Dark Mode First**: Native dark mode support with system preference detection
- **Responsive Design**: Mobile-first approach with adaptive layouts

**Reference Implementation**: The UI design follows the style established in `examples-of-reference/linx-workforce-web/`

**Color Palette**:
```css
/* Light Mode */
--bg-primary: #fbfbfd;
--bg-secondary: rgba(255, 255, 255, 0.72);
--border-subtle: rgba(0, 0, 0, 0.08);
--text-primary: #1d1d1f;
--text-secondary: #86868b;
--accent: #10b981;  /* Emerald green */

/* Dark Mode */
--bg-primary: #000000;
--bg-secondary: rgba(28, 28, 30, 0.7);
--border-subtle: rgba(255, 255, 255, 0.1);
--text-primary: #f5f5f7;
--text-secondary: #a1a1a6;
```

**Typography**:
- **Primary Font**: Inter (sans-serif) - for UI text
- **Monospace Font**: JetBrains Mono - for code and technical data
- **Font Smoothing**: -webkit-font-smoothing: antialiased
- **Font Features**: "cv11", "ss01" for enhanced readability

**Glass Panel Effect**:
```css
.glass-panel {
  background: var(--bg-secondary);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border: 1px solid var(--border-subtle);
  box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.04);
  border-radius: 24px-40px; /* Varies by component */
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}
```

### 18.2 Layout Structure

**Application Shell**:
```
┌─────────────────────────────────────────────────────────┐
│  Sidebar (64px collapsed, 256px expanded)               │
│  ┌─────────┐  ┌──────────────────────────────────────┐ │
│  │  Logo   │  │         Header Bar                    │ │
│  │         │  │  [Menu] [Status] [Theme] [Lang] [🔔] │ │
│  ├─────────┤  ├──────────────────────────────────────┤ │
│  │  Nav    │  │                                       │ │
│  │  Items  │  │         Main Content Area            │ │
│  │         │  │         (Scrollable)                 │ │
│  │         │  │                                       │ │
│  │         │  │                                       │ │
│  ├─────────┤  │                                       │ │
│  │ Profile │  │                                       │ │
│  └─────────┘  └──────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Sidebar Navigation**:
- Collapsible sidebar (toggle between 64px and 256px)
- Icon-only mode when collapsed
- Active state with emerald accent color
- Smooth expand/collapse animation (500ms)
- Navigation items:
  - Dashboard (LayoutDashboard icon)
  - Workforce (Users icon)
  - Tasks (Target icon)
  - Knowledge (Database icon)
  - Memory (BrainCircuit icon)

**Header Bar**:
- Height: 64px
- Glass panel effect with subtle border
- Left: Menu toggle button
- Center: System status indicator
- Right: Theme switcher, Language selector, Notifications

### 18.3 Dashboard Components

**Overview Cards (4-column grid)**:
```tsx
<StatCard>
  - Icon with colored background (emerald/blue/purple/orange)
  - Large value display (3xl font)
  - Title (uppercase, small, tracking-widest)
  - Subtitle (monospace, tiny)
  - Trend indicator (+12.5% badge)
  - Hover effect: translate-y-[-2px]
</StatCard>
```

**Metrics**:
1. **Active Agents**: Count of working agents
2. **Goals Completed**: Completed vs total goals
3. **Throughput**: Completed tasks / total tasks
4. **Compute Load**: CPU usage percentage

**Task Distribution Chart**:
- Area chart with gradient fill
- Emerald color scheme (#10b981)
- 7-day view (Mon-Sun)
- Smooth curves (monotone interpolation)
- Hover tooltips with glass effect
- Grid lines with subtle opacity

**Recent Events Timeline**:
- Vertical list with timestamps
- Time ago format (2m, 15m, 1h, 3h)
- Event descriptions
- Hover effect: text color changes to emerald

### 18.4 Workforce Management

**Agent Grid (3-column responsive)**:
```tsx
<AgentCard>
  - Glass panel with rounded-[32px]
  - Avatar (80x80, rounded-[24px])
  - Status indicator (dot with icon)
    - Working: Emerald with Zap icon
    - Idle: Gray
    - Offline: Red
  - Agent name (2xl, bold)
  - Agent type badge (Shield icon + uppercase text)
  - Description (2 lines, line-clamp)
  - Skills (pill badges, uppercase, tiny)
  - Footer: Memory usage + View logs link
  - Hover: translate-y-[-4px]
</AgentCard>
```

**Search and Filter Bar**:
- Glass panel with rounded-2xl
- Search input with icon
- Filter button
- Responsive layout

**Add Agent Modal**:
- Full-screen overlay with backdrop blur
- Centered modal (max-w-2xl)
- Rounded-[40px] glass panel
- Template grid (2 columns)
- Template cards:
  - Avatar (grayscale → color on hover)
  - Type name
  - Description (2 lines)
  - Skills preview (first 3)
  - Click to create

### 18.5 Task Manager

**Goal Input**:
```tsx
<GoalInput>
  - Large glass panel (rounded-[32px])
  - Sparkles icon (emerald)
  - Text input (xl font, medium weight)
  - Submit button (emerald, rounded-[24px])
  - Loading state with spinner
  - Focus ring (emerald/10)
</GoalInput>
```

**Goal Cards**:
```tsx
<GoalCard>
  - Glass panel (rounded-[40px])
  - Header section:
    - Goal description (2xl, bold)
    - Goal ID (tiny, uppercase, monospace)
    - Status badge (completed/in-progress)
  - Task list:
    - Vertical timeline with connecting lines
    - Status icons (CheckCircle/Loader/Clock/AlertCircle)
    - Task cards (rounded-[24px])
      - Task description
      - Progress bar (emerald)
      - Agent avatar + name
      - Result badge (if completed)
    - Hover: background color change
</GoalCard>
```

**Task Flow Visualization** (Requirement 13):
```tsx
<TaskFlowVisualization>
  - Interactive graph/tree view
  - Real-time WebSocket updates
  - Node types:
    - Goal node (large, emerald)
    - Task nodes (medium, status-colored)
    - Sub-task nodes (small)
  - Connections:
    - Dependency arrows
    - Animated flow indicators
  - Node details:
    - Task description
    - Assigned agent avatar
    - Status indicator
    - Progress percentage
    - Estimated completion time
  - Controls:
    - Zoom in/out
    - Pan
    - Filter by status
    - Filter by agent
    - Auto-layout toggle
  - Legend:
    - Status colors
    - Icon meanings
</TaskFlowVisualization>
```

### 18.6 Knowledge Base

**Document Library**:
```tsx
<DocumentGrid>
  - Grid layout (3-4 columns)
  - Document cards:
    - File type icon
    - Document title
    - Preview thumbnail (if available)
    - Last modified date
    - Access level badge
    - Processing status indicator
    - Hover: scale and shadow effect
</DocumentGrid>
```

**Upload Interface**:
- Drag-and-drop zone
- File picker button
- Upload progress indicators
- Processing status (extraction → embedding → indexing)
- Success/error notifications

**Document Viewer**:
- Full-screen modal
- Document preview
- Metadata panel
- Access control settings
- Download button
- Delete button (with confirmation)

### 18.7 Memory System

**Memory Browser**:
```tsx
<MemoryList>
  - Tabbed interface:
    - Agent Memory
    - Company Memory
    - User Context
  - Memory cards:
    - Content preview
    - Memory type badge
    - Timestamp
    - Tags (pill badges)
    - Relevance score (if search result)
  - Search bar with semantic search
  - Filter by type, date, tags
</MemoryList>
```

### 18.8 Settings Page

**LLM Provider Management**:
```tsx
<SettingsPage>
  - Header section:
    - Settings icon with gradient background
    - Title: "LLM Settings"
    - Subtitle: "Manage your AI model providers and configurations"
    - Refresh button
    - Add Provider button (admin only)
  
  - Configuration Summary (3-column grid):
    - Default Provider card
      - Cpu icon
      - Provider name (capitalized)
    - Active Providers card
      - CheckCircle2 icon
      - Count: "X / Y"
    - Fallback Status card
      - Zap icon
      - "Enabled" or "Disabled"
  
  - Providers List:
    - Provider cards (one per provider):
      - Provider icon (emoji: 🦙 Ollama, ⚡ vLLM, 🤖 OpenAI, 🧠 Anthropic)
      - Provider name (capitalized, large, bold)
      - Health status indicator:
        - Healthy: CheckCircle2 icon (emerald)
        - Unhealthy: XCircle icon (red)
      - Border color based on health status
      - Available models section:
        - Model count display
        - Model badges (pill style, monospace font)
        - "No models available" message if empty
      - Action buttons (admin only):
        - Edit button (Pencil icon)
        - Delete button (Trash icon)
      - Test button (if healthy and has models):
        - Zap icon
        - "Test" / "Testing..." states
        - Disabled during test
  
  - Test Prompt Input:
    - Glass panel with rounded corners
    - Input field for custom test prompt
    - Default: "Hello, how are you?"
    - Hint text: "This prompt will be used when testing providers"
</SettingsPage>
```

**Add/Edit Provider Modal**:
```tsx
<ProviderModal>
  - Modal header:
    - Title: "Add Provider" / "Edit Provider"
    - Close button
  
  - Form fields:
    1. Provider Name (required):
       - Text input
       - Placeholder: "e.g., my-ollama-server"
       - Validation: alphanumeric, hyphens, underscores
    
    2. Protocol Type (required):
       - Select dropdown
       - Options:
         * Ollama (default)
         * OpenAI Compatible
       - Icon indicator for each protocol
    
    3. Base URL (required):
       - Text input
       - Placeholder: "http://localhost:11434" (Ollama) or "https://api.openai.com/v1" (OpenAI)
       - Validation: valid URL format
    
    4. API Key (optional, required for OpenAI Compatible):
       - Password input with show/hide toggle
       - Placeholder: "sk-..."
       - Only shown for OpenAI Compatible protocol
    
    5. Timeout (optional):
       - Number input
       - Default: 30 seconds
       - Range: 5-300 seconds
    
    6. Max Retries (optional):
       - Number input
       - Default: 3
       - Range: 0-10
  
  - Actions:
    - Test Connection button:
      - Validates configuration
      - Fetches available models
      - Shows success/error message
    - Cancel button
    - Save button (disabled until valid)
</ProviderModal>
```

**Provider Configuration Storage**:
```yaml
# config.yaml
llm:
  providers:
    ollama-local:
      protocol: ollama
      base_url: http://localhost:11434
      timeout: 30
      max_retries: 3
      enabled: true
    
    openai-compatible:
      protocol: openai_compatible
      base_url: https://api.openai.com/v1
      api_key: ${OPENAI_API_KEY}  # From environment variable
      timeout: 60
      max_retries: 3
      enabled: true
  
  default_provider: ollama-local
  fallback_enabled: true
  fallback_order:
    - ollama-local
    - openai-compatible
```

**Provider Card States**:
- Healthy: `border-emerald-500/30 bg-emerald-500/5`
- Unhealthy: `border-red-500/30 bg-red-500/5`
- Hover: Subtle scale effect
- Test button: Emerald background, white text, spinner during testing

**Interactions**:
- Refresh button: Reloads all provider status
- Add Provider: Opens modal for new provider configuration
- Edit Provider: Opens modal with existing configuration
- Delete Provider: Shows confirmation dialog
- Test button: Sends test prompt to provider, shows toast with response
- Test Connection: Validates config and fetches models
- Real-time health status updates
- Error handling with user-friendly messages

### 18.9 Responsive Breakpoints

```css
/* Mobile First */
sm: 640px   /* Small tablets */
md: 768px   /* Tablets */
lg: 1024px  /* Laptops */
xl: 1280px  /* Desktops */
2xl: 1536px /* Large desktops */
```

**Mobile Adaptations**:
- Sidebar: Hidden by default, slide-in overlay
- Grid layouts: 1 column on mobile, 2 on tablet, 3+ on desktop
- Header: Compact with hamburger menu
- Cards: Full width with reduced padding
- Charts: Simplified with touch-friendly tooltips

### 18.10 Animations and Transitions

**Page Transitions**:
```css
.animate-in {
  animation: fadeIn 0.7s ease-out,
             slideInFromBottom 0.7s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideInFromBottom {
  from { transform: translateY(24px); }
  to { transform: translateY(0); }
}
```

**Hover Effects**:
- Cards: `translate-y-[-2px]` or `translate-y-[-4px]`
- Buttons: `active:scale-95`
- Icons: `scale-110` on active state
- Colors: Smooth transition to emerald accent

**Loading States**:
- Spinner: `animate-spin` (Loader2 icon)
- Skeleton screens for data loading
- Progress bars with smooth transitions
- Pulse animation for pending states

**Scan Line Effect** (Background):
```css
.scan-line {
  background: linear-gradient(
    to bottom,
    transparent,
    rgba(16, 185, 129, 0.02),
    transparent
  );
  background-size: 100% 200px;
  animation: scan 12s linear infinite;
  pointer-events: none;
}
```

### 18.10 Animations and Transitions

**Page Transitions**:
```css
.animate-in {
  animation: fadeIn 0.7s ease-out,
             slideInFromBottom 0.7s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideInFromBottom {
  from { transform: translateY(24px); }
  to { transform: translateY(0); }
}
```

**Hover Effects**:
- Cards: `translate-y-[-2px]` or `translate-y-[-4px]`
- Buttons: `active:scale-95`
- Icons: `scale-110` on active state
- Colors: Smooth transition to emerald accent

**Loading States**:
- Spinner: `animate-spin` (Loader2 icon)
- Skeleton screens for data loading
- Progress bars with smooth transitions
- Pulse animation for pending states

**Scan Line Effect** (Background):
```css
.scan-line {
  background: linear-gradient(
    to bottom,
    transparent,
    rgba(16, 185, 129, 0.02),
    transparent
  );
  background-size: 100% 200px;
  animation: scan 12s linear infinite;
  pointer-events: none;
}
```

### 18.11 Accessibility

**WCAG 2.1 AA Compliance**:
- Color contrast ratios: 4.5:1 for text, 3:1 for UI components
- Keyboard navigation: Full support with visible focus indicators
- Screen reader support: Semantic HTML and ARIA labels
- Focus management: Logical tab order
- Skip links: Skip to main content

**Keyboard Shortcuts**:
- `Cmd/Ctrl + K`: Global search
- `Cmd/Ctrl + B`: Toggle sidebar
- `Cmd/Ctrl + N`: New goal/agent (context-dependent)
- `Esc`: Close modals
- Arrow keys: Navigate lists and grids

### 18.12 Technology Stack

**Frontend Framework**:
- **React 19** with TypeScript
- **Vite** for build tooling and dev server
- **TailwindCSS** for utility-first styling
- **Lucide React** for icon system

**UI Components**:
- Custom components following glassmorphism design
- No heavy component library (lightweight approach)
- Recharts for data visualization
- React Flow (optional) for advanced task flow visualization

**State Management**:
- React hooks (useState, useEffect, useContext)
- Custom hooks for API integration
- WebSocket hooks for real-time updates

**Styling Approach**:
```tsx
// Utility classes with Tailwind
<div className="glass-panel rounded-[32px] p-8 hover:translate-y-[-2px] transition-all duration-300">
  
// Custom CSS variables for theming
:root {
  --bg-primary: #fbfbfd;
  --accent: #10b981;
}

// Dark mode with class strategy
<html className="dark">
```

**Real-Time Updates**:
- WebSocket connection for task status
- Automatic reconnection on disconnect
- Optimistic UI updates
- Toast notifications for events

**Internationalization**:
- Built-in i18n support (Chinese/English)
- Language switcher in header
- Translation files structure:
```typescript
export const translations = {
  zh: { /* Chinese translations */ },
  en: { /* English translations */ }
};
```

### 18.12 Component Examples

**Stat Card Component**:
```tsx
interface StatCardProps {
  title: string;
  value: string | number;
  subtitle: string;
  icon: LucideIcon;
  colorClass: string;
  trend?: string;
}

const StatCard: React.FC<StatCardProps> = ({
  title, value, subtitle, icon: Icon, colorClass, trend
}) => (
  <div className="glass-panel p-6 rounded-[24px] group hover:translate-y-[-2px] transition-all duration-300">
    <div className="flex justify-between items-start mb-4">
      <div className={`p-2.5 rounded-xl ${colorClass} bg-opacity-10`}>
        <Icon className="w-5 h-5" />
      </div>
      {trend && (
        <span className="text-[10px] font-bold text-emerald-600 bg-emerald-500/5 px-2 py-0.5 rounded-full">
          {trend}
        </span>
      )}
    </div>
    <h3 className="text-3xl font-bold tracking-tight mb-1">{value}</h3>
    <p className="text-zinc-500 text-xs font-medium uppercase tracking-wider">
      {title}
    </p>
    <p className="text-zinc-400 text-[10px] mt-2 font-mono">{subtitle}</p>
  </div>
);
```

**Agent Card Component**:
```tsx
interface AgentCardProps {
  agent: Agent;
  onViewLogs: (agentId: string) => void;
}

const AgentCard: React.FC<AgentCardProps> = ({ agent, onViewLogs }) => (
  <div className="glass-panel group relative rounded-[32px] overflow-hidden p-8 hover:translate-y-[-4px] transition-all duration-300">
    <div className="flex justify-between items-start mb-8">
      <div className="relative">
        <div className="w-20 h-20 rounded-[24px] overflow-hidden border-2 border-white dark:border-zinc-800 shadow-2xl">
          <img src={agent.avatar} alt={agent.name} className="w-full h-full object-cover" />
        </div>
        <StatusIndicator status={agent.status} />
      </div>
      <MoreMenu agentId={agent.id} />
    </div>
    
    <div className="space-y-4">
      <div>
        <h3 className="text-2xl font-bold tracking-tight mb-1">{agent.name}</h3>
        <TypeBadge type={agent.type} />
      </div>
      
      <p className="text-zinc-500 text-sm leading-relaxed line-clamp-2">
        {agent.description}
      </p>
      
      <SkillBadges skills={agent.skills} />
    </div>
    
    <AgentFooter agent={agent} onViewLogs={onViewLogs} />
  </div>
);
```

**Task Timeline Component**:
```tsx
interface TaskTimelineProps {
  tasks: Task[];
  agents: Agent[];
}

const TaskTimeline: React.FC<TaskTimelineProps> = ({ tasks, agents }) => (
  <div className="space-y-6">
    {tasks.map((task, idx) => {
      const agent = agents.find(a => a.id === task.assignedTo);
      const isLast = idx === tasks.length - 1;
      
      return (
        <div key={task.id} className="flex gap-6 items-start relative group">
          {!isLast && <TimelineConnector />}
          
          <StatusIcon status={task.status} />
          
          <div className="flex-1 bg-zinc-500/5 rounded-[24px] p-6 group-hover:bg-zinc-500/10 transition-colors">
            <TaskHeader task={task} />
            <ProgressBar progress={task.progress} />
            <TaskFooter task={task} agent={agent} />
          </div>
        </div>
      );
    })}
  </div>
);
```

### 18.13 Theme System

**Theme Toggle**:
```tsx
type Theme = 'light' | 'dark' | 'system';

const ThemeToggle: React.FC = () => {
  const [theme, setTheme] = useState<Theme>('system');
  
  useEffect(() => {
    const root = document.documentElement;
    const applyTheme = (t: 'light' | 'dark') => {
      if (t === 'dark') root.classList.add('dark');
      else root.classList.remove('dark');
    };
    
    if (theme === 'system') {
      const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches 
        ? 'dark' : 'light';
      applyTheme(systemTheme);
    } else {
      applyTheme(theme);
    }
  }, [theme]);
  
  return (
    <div className="flex items-center bg-zinc-500/5 rounded-full p-1">
      <ThemeButton icon={Sun} active={theme === 'light'} onClick={() => setTheme('light')} />
      <ThemeButton icon={Monitor} active={theme === 'system'} onClick={() => setTheme('system')} />
      <ThemeButton icon={Moon} active={theme === 'dark'} onClick={() => setTheme('dark')} />
    </div>
  );
};
```

### 18.14 Performance Optimizations

**Code Splitting**:
```tsx
// Lazy load heavy components
const TaskFlowVisualization = lazy(() => import('./components/TaskFlowVisualization'));
const KnowledgeBase = lazy(() => import('./components/KnowledgeBase'));

// Use Suspense for loading states
<Suspense fallback={<LoadingSpinner />}>
  <TaskFlowVisualization />
</Suspense>
```

**Virtual Scrolling**:
- For large agent lists (>100 items)
- For long task histories
- React Window or React Virtual for implementation

**Image Optimization**:
- Lazy loading for agent avatars
- WebP format with fallback
- Responsive images with srcset
- Placeholder blur effect during load

**Bundle Size**:
- Target: <200KB initial bundle (gzipped)
- Code splitting by route
- Tree shaking unused code
- Dynamic imports for heavy features


## 19. Testing Strategy

### 19.1 Unit Testing

**Component Tests**
- Task Manager: Goal parsing, task decomposition, agent assignment
- Agent Framework: Agent initialization, skill loading, task execution
- Memory System: Storage, retrieval, filtering, ranking
- Access Control: Permission evaluation, role checking
- Document Processor: Text extraction, chunking, embedding generation

**Test Framework**
- pytest for Python components
- Jest for TypeScript/JavaScript components
- Coverage target: 80% minimum

### 19.2 Integration Testing

**Component Integration**
- API Gateway → Task Manager → Agent Framework
- Agent → Memory System → Milvus
- Document Processor → MinIO → Knowledge Base
- Agent → Message Bus → Agent communication

**Database Integration**
- PostgreSQL CRUD operations
- Milvus vector search accuracy
- Redis pub/sub reliability
- MinIO file operations

**Test Environment**
- Docker Compose test environment
- Test data fixtures
- Database migrations tested
- Cleanup after tests

### 19.3 End-to-End Testing

**User Workflows**
- Complete goal submission → task execution → result delivery
- Agent creation → task assignment → execution
- Document upload → processing → knowledge retrieval
- Multi-agent collaboration on complex task

**Test Scenarios**
- Happy path: All components working
- Error scenarios: Agent failure, timeout, invalid input
- Load scenarios: Multiple concurrent tasks
- Security scenarios: Unauthorized access attempts

**Test Tools**
- Playwright or Cypress for UI testing
- Postman/Newman for API testing
- k6 or Locust for load testing

### 19.4 Performance Testing

**Load Testing**
- Concurrent user simulation (100, 500, 1000 users)
- Task submission rate testing
- Agent pool scaling validation
- Database query performance under load

**Stress Testing**
- Maximum agent capacity
- Database connection exhaustion
- Memory pressure scenarios
- Network bandwidth limits

**Benchmarks**
- API response time: p95 < 500ms
- Task decomposition: < 5 seconds
- Vector search: < 100ms for 1M vectors
- Document processing: < 30 seconds for 10-page PDF


## 20. Migration and Upgrade Strategy

### 20.1 Database Migrations

**Migration Tool**
- Alembic for PostgreSQL schema migrations
- Versioned migration scripts
- Rollback capability for failed migrations

**Migration Process**
1. Generate migration script from schema changes
2. Review and test in development environment
3. Backup production database
4. Apply migration with downtime window
5. Verify data integrity
6. Monitor for issues

**Zero-Downtime Migrations**
- Backward-compatible schema changes
- Blue-green deployment for application updates
- Database replication for read availability

### 20.2 Data Migration

**Milvus Collection Updates**
- Create new collection with updated schema
- Migrate data in batches
- Switch application to new collection
- Delete old collection after verification

**MinIO Bucket Reorganization**
- Copy objects to new structure
- Update references in PostgreSQL
- Verify all references updated
- Delete old objects

### 20.3 Version Compatibility

**API Versioning**
- URL-based versioning: /api/v1/, /api/v2/
- Maintain backward compatibility for 2 major versions
- Deprecation warnings in API responses
- Migration guides for breaking changes

**Agent Compatibility**
- Agent version stored in database
- Skill library versioning
- Graceful handling of version mismatches
- Automatic agent updates (optional)

### 20.4 Backup and Recovery

**Backup Strategy**
- PostgreSQL: Daily full backup, hourly incremental
- Milvus: Weekly full backup, daily incremental
- MinIO: Continuous replication to backup bucket
- Configuration: Version controlled in Git

**Recovery Procedures**
- Point-in-time recovery for PostgreSQL
- Collection restore for Milvus
- Object restore from backup bucket
- Disaster recovery runbook


## 21. Design Decisions and Rationale

### 21.1 Technology Choices

**LangChain for Agent Framework**
- **Decision**: Use LangChain as the agent orchestration framework
- **Rationale**: 
  - Mature ecosystem with extensive tool integrations
  - Built-in support for memory, chains, and agents
  - Active community and regular updates
  - Flexible enough for custom agent types
- **Alternatives Considered**: AutoGPT, CrewAI, custom framework
- **Trade-offs**: Some learning curve, but saves significant development time

**Milvus for Vector Database**
- **Decision**: Use Milvus for vector embeddings and similarity search
- **Rationale**:
  - Designed specifically for billion-scale vector search
  - Excellent performance with GPU acceleration
  - Supports distributed deployment for horizontal scaling
  - Rich indexing options (IVF_FLAT, HNSW, etc.)
  - Open-source with strong community
- **Alternatives Considered**: Pinecone (cloud-only), Weaviate, Qdrant
- **Trade-offs**: More complex setup than simpler alternatives, but necessary for scale

**PostgreSQL for Primary Database**
- **Decision**: Use PostgreSQL for operational data
- **Rationale**:
  - Proven reliability and ACID guarantees
  - Rich feature set (JSONB, full-text search, partitioning)
  - Excellent performance for transactional workloads
  - Strong ecosystem and tooling
- **Alternatives Considered**: MySQL, MongoDB
- **Trade-offs**: None significant for this use case

**MinIO for Object Storage**
- **Decision**: Use MinIO for file storage
- **Rationale**:
  - S3-compatible API (easy migration if needed)
  - Can be deployed on-premise
  - High performance and scalability
  - Built-in versioning and lifecycle management
- **Alternatives Considered**: Local filesystem, Ceph
- **Trade-offs**: Additional service to manage, but provides better scalability

**Ollama for Local LLM**
- **Decision**: Use Ollama as primary local LLM provider
- **Rationale**:
  - Extremely easy setup and model management
  - Good performance for development and small-scale
  - Supports wide range of models
  - Active development and community
- **Alternatives Considered**: vLLM (used for production), llama.cpp
- **Trade-offs**: Lower throughput than vLLM, but much easier to use

### 21.2 Architectural Decisions

**Multi-Tier Memory System**
- **Decision**: Separate Agent Memory, Company Memory, and User Context
- **Rationale**:
  - Enables both privacy and collaboration
  - User Context solves the "tell once, use everywhere" problem
  - Clear data ownership and access control
  - Supports future compliance requirements (data deletion, export)
- **Alternatives Considered**: Single shared memory, per-task memory only
- **Trade-offs**: More complex implementation, but essential for usability

**Container-Based Agent Isolation**
- **Decision**: Run each agent in isolated Docker container
- **Rationale**:
  - Security: Prevents agent code from affecting host or other agents
  - Resource control: Enforce CPU/memory limits per agent
  - Reliability: Agent crashes don't affect platform
  - Scalability: Easy to distribute across multiple hosts
- **Alternatives Considered**: Process isolation, VM isolation
- **Trade-offs**: Higher resource overhead than processes, but necessary for security

**Task Decomposition via LLM**
- **Decision**: Use LLM to decompose goals into task hierarchies
- **Rationale**:
  - Flexible: Handles diverse goal types without hardcoded rules
  - Intelligent: Can ask clarifying questions when needed
  - Maintainable: No complex rule engine to maintain
  - Extensible: Improves as LLMs improve
- **Alternatives Considered**: Rule-based decomposition, manual task creation
- **Trade-offs**: Less predictable than rules, but much more capable

**On-Premise First Design**
- **Decision**: Design for on-premise deployment with optional cloud components
- **Rationale**:
  - Data privacy: Sensitive enterprise data stays on-premise
  - Compliance: Meets regulatory requirements
  - Control: Full control over infrastructure and data
  - Cost: Predictable costs for large-scale usage
- **Alternatives Considered**: Cloud-first, hybrid-first
- **Trade-offs**: More complex deployment, but essential for enterprise adoption

### 21.3 Security Decisions

**JWT for Authentication**
- **Decision**: Use JWT tokens for API authentication
- **Rationale**:
  - Stateless: No server-side session storage needed
  - Scalable: Works well with multiple API Gateway instances
  - Standard: Well-understood and widely supported
  - Flexible: Can include custom claims for permissions
- **Alternatives Considered**: Session-based auth, OAuth2
- **Trade-offs**: Token revocation requires additional mechanism

**RBAC + ABAC Hybrid**
- **Decision**: Support both role-based and attribute-based access control
- **Rationale**:
  - RBAC: Simple for common cases (admin, user, viewer)
  - ABAC: Flexible for complex enterprise requirements
  - Hybrid: Best of both worlds
  - Extensible: Can add new attributes without code changes
- **Alternatives Considered**: RBAC only, ABAC only
- **Trade-offs**: More complex to configure, but necessary for enterprise

**Encryption at Rest and in Transit**
- **Decision**: Encrypt all data at rest and in transit
- **Rationale**:
  - Security: Protects against data breaches
  - Compliance: Required by many regulations
  - Best practice: Industry standard for enterprise systems
- **Alternatives Considered**: Encryption in transit only
- **Trade-offs**: Performance overhead, but minimal with modern hardware

### 21.4 Scalability Decisions

**Horizontal Scaling for All Components**
- **Decision**: Design all components to scale horizontally
- **Rationale**:
  - Cost-effective: Add commodity hardware as needed
  - Reliable: No single point of failure
  - Flexible: Scale different components independently
  - Cloud-ready: Easy to deploy to Kubernetes
- **Alternatives Considered**: Vertical scaling
- **Trade-offs**: More complex architecture, but necessary for scale

**Async Processing for Heavy Operations**
- **Decision**: Use job queues for document processing, embedding generation
- **Rationale**:
  - Responsiveness: API returns immediately
  - Reliability: Jobs can be retried on failure
  - Scalability: Workers can be scaled independently
  - Monitoring: Easy to track job status and performance
- **Alternatives Considered**: Synchronous processing
- **Trade-offs**: More complex, but necessary for good UX

**Caching Strategy**
- **Decision**: Cache frequently accessed data in Redis
- **Rationale**:
  - Performance: Reduce database load
  - Scalability: Handle more requests with same resources
  - Cost: Cheaper than scaling databases
- **Alternatives Considered**: No caching, application-level caching
- **Trade-offs**: Cache invalidation complexity, but worth it for performance

**Code Execution Sandbox Technology**
- **Decision**: Use gVisor for Kubernetes deployments, Firecracker for high-security scenarios, with automatic fallback to Docker Enhanced
- **Rationale**:
  - gVisor: Good balance of security and performance (~10-15% overhead) on Linux
  - Firecracker: Hardware-level isolation for sensitive code execution on Linux
  - Docker Enhanced: Cross-platform compatibility for development (macOS, Windows)
  - Automatic detection ensures platform compatibility
  - Enables safe dynamic code generation and execution
  - Protects host system from malicious or buggy agent code
- **Alternatives Considered**: Docker only, full VMs, WebAssembly sandboxes
- **Trade-offs**: Additional complexity and overhead, but essential for security when agents generate and execute code

**Cross-Platform Sandbox Strategy**
- **Decision**: Implement automatic sandbox selection with graceful fallback
- **Rationale**:
  - gVisor only works on Linux - need fallback for other platforms
  - Development teams may use macOS or Windows
  - Docker Enhanced provides acceptable security for development
  - Automatic detection prevents configuration errors
  - Enables "develop anywhere, deploy on Linux" workflow
  - Clear security level indicators for each platform
- **Alternatives Considered**: Linux-only deployment, manual configuration
- **Trade-offs**: More complex implementation, but essential for developer experience

**Dynamic Skill Generation**
- **Decision**: Allow agents to generate code on-the-fly for task-specific skills
- **Rationale**:
  - Flexibility: Agents can adapt to novel tasks without pre-defined skills
  - Efficiency: No need to pre-build skills for every possible scenario
  - Innovation: Agents can create optimized solutions for specific problems
  - Learning: Generated skills can be stored and reused
- **Alternatives Considered**: Fixed skill library only, manual skill creation
- **Trade-offs**: Security risks (mitigated by sandboxing), unpredictable behavior (mitigated by validation)


## 22. Implementation Phases

### Phase 1: Core Infrastructure (Weeks 1-4)
**Objectives**: Establish foundational infrastructure and data layer

**Deliverables**:
- PostgreSQL database with schema
- Milvus vector database setup
- MinIO object storage configuration
- Redis message bus setup
- Docker Compose development environment
- Basic API Gateway with authentication

**Success Criteria**:
- All databases operational and accessible
- API Gateway can authenticate users
- Docker Compose brings up all services

### Phase 2: Agent Framework (Weeks 5-8)
**Objectives**: Implement core agent functionality

**Deliverables**:
- LangChain agent implementation
- Agent lifecycle management (create, execute, terminate)
- Skill library with basic skills
- Agent templates (Data Analyst, Content Writer, Code Assistant, Research Assistant)
- Container-based agent isolation
- Agent registry and metadata management

**Success Criteria**:
- Can create agents from templates
- Agents can execute simple tasks
- Agents run in isolated containers
- Agent status tracked in database

### Phase 3: Memory System (Weeks 9-12)
**Objectives**: Implement multi-tier memory with semantic search

**Deliverables**:
- Agent Memory implementation
- Company Memory implementation
- User Context within Company Memory
- Embedding generation pipeline
- Vector similarity search
- Memory storage and retrieval APIs

**Success Criteria**:
- Agents can store and retrieve memories
- User Context shared across user's agents
- Semantic search returns relevant results
- Memory access control enforced

### Phase 4: Task Management (Weeks 13-16)
**Objectives**: Implement hierarchical task decomposition and execution

**Deliverables**:
- Task Manager component
- Goal analysis and clarification
- LLM-based task decomposition
- Agent assignment algorithm
- Task execution coordination
- Result aggregation
- Task status tracking and updates

**Success Criteria**:
- Can submit goals and get clarifying questions
- Goals decomposed into task hierarchies
- Tasks assigned to appropriate agents
- Results aggregated and returned to user

### Phase 5: Knowledge Base (Weeks 17-20)
**Objectives**: Implement document processing and knowledge management

**Deliverables**:
- Document upload API
- Document Processor for PDF, DOCX, TXT, MD
- OCR for images
- Audio transcription (Whisper)
- Video processing
- Knowledge Base search API
- Access control for knowledge items

**Success Criteria**:
- Can upload and process documents
- Text extracted and embedded
- Knowledge searchable by agents
- Access control enforced

### Phase 6: Inter-Agent Communication (Weeks 21-22)
**Objectives**: Enable agent collaboration

**Deliverables**:
- Message Bus implementation (Redis)
- Direct messaging between agents
- Broadcast messaging
- Request-response pattern
- Message access control
- Message audit logging

**Success Criteria**:
- Agents can send messages to each other
- Broadcast messages reach all agents in task
- Messages logged for audit

### Phase 7: User Interface (Weeks 23-26)
**Objectives**: Build web-based user interface

**Deliverables**:
- React frontend application
- Dashboard with task overview
- Task flow visualization (real-time)
- Agent management interface
- Knowledge Base interface
- Monitoring dashboard
- WebSocket integration for real-time updates

**Success Criteria**:
- Users can submit goals via UI
- Task flow visualized in real-time
- Can create and manage agents
- Can upload and search knowledge

### Phase 8: Monitoring and Operations (Weeks 27-28)
**Objectives**: Implement observability and operational tools

**Deliverables**:
- Prometheus metrics collection
- Grafana dashboards
- Structured logging (ELK or Loki)
- Distributed tracing (Jaeger)
- Alerting rules and channels
- Health check endpoints

**Success Criteria**:
- All components emit metrics
- Dashboards show system health
- Logs aggregated and searchable
- Alerts fire for critical issues

### Phase 9: Security Hardening (Weeks 29-30)
**Objectives**: Implement comprehensive security measures

**Deliverables**:
- Encryption at rest for all databases
- TLS for all internal communication
- RBAC and ABAC implementation
- Data classification system
- Security audit logging
- Penetration testing and fixes

**Success Criteria**:
- All data encrypted
- Access control enforced
- Security audit passed
- No critical vulnerabilities

### Phase 10: Production Deployment (Weeks 31-32)
**Objectives**: Deploy to production environment

**Deliverables**:
- Kubernetes deployment manifests
- Production configuration
- Backup and recovery procedures
- Disaster recovery plan
- Operations runbook
- User documentation

**Success Criteria**:
- Platform deployed to production
- All services healthy and monitored
- Backup procedures tested
- Documentation complete


## 23. Risk Analysis and Mitigation

### 23.1 Technical Risks

**Risk: LLM Hallucination in Task Decomposition**
- **Impact**: High - Incorrect task decomposition leads to wrong results
- **Probability**: Medium
- **Mitigation**:
  - Implement validation checks on decomposed tasks
  - Allow user review before execution
  - Use few-shot examples for better accuracy
  - Implement feedback loop to improve over time
  - Provide manual task editing capability

**Risk: Vector Search Accuracy**
- **Impact**: Medium - Poor search results reduce agent effectiveness
- **Probability**: Medium
- **Mitigation**:
  - Use high-quality embedding models
  - Implement hybrid search (vector + keyword)
  - Allow manual relevance feedback
  - Monitor search quality metrics
  - Regularly evaluate and tune index parameters

**Risk: Agent Container Escape**
- **Impact**: Critical - Security breach, data exposure
- **Probability**: Low
- **Mitigation**:
  - Use minimal base images
  - Drop unnecessary capabilities
  - Regular security updates
  - Security scanning of container images
  - Network isolation
  - Regular penetration testing

**Risk: Database Performance Degradation**
- **Impact**: High - System slowdown, poor user experience
- **Probability**: Medium
- **Mitigation**:
  - Implement connection pooling
  - Regular index optimization
  - Query performance monitoring
  - Database partitioning for large tables
  - Read replicas for scaling
  - Caching strategy

**Risk: LLM Provider Downtime**
- **Impact**: Critical - Platform unusable
- **Probability**: Low (local deployment)
- **Mitigation**:
  - Multiple Ollama instances for redundancy
  - Automatic failover between instances
  - Health checks and monitoring
  - Graceful degradation (queue tasks if LLM unavailable)
  - Optional cloud fallback for non-sensitive tasks

**Risk: Cross-Platform Sandbox Compatibility**
- **Impact**: Medium - Development environment issues, security inconsistencies
- **Probability**: Medium
- **Mitigation**:
  - Automatic sandbox detection and selection
  - Clear documentation of platform-specific limitations
  - Graceful fallback to Docker Enhanced on non-Linux platforms
  - Warning messages when using lower security sandbox
  - Comprehensive testing on all supported platforms
  - Enforce Linux deployment for production environments
  - CI/CD pipeline tests on multiple platforms

**Risk: Sandbox Escape or Code Injection**
- **Impact**: Critical - Malicious code execution, system compromise
- **Probability**: Low (with proper sandboxing)
- **Mitigation**:
  - Multi-layer isolation (Docker + gVisor/Firecracker)
  - Static code analysis before execution
  - Strict resource limits and timeouts
  - Network isolation and firewall rules
  - Real-time monitoring of sandbox behavior
  - Automatic termination on suspicious activity
  - Regular security audits and penetration testing
  - Code validation and sanitization
  - Graceful degradation (queue tasks if LLM unavailable)
  - Optional cloud fallback for non-sensitive tasks

### 23.2 Operational Risks

**Risk: Data Loss**
- **Impact**: Critical - Loss of knowledge, memories, tasks
- **Probability**: Low
- **Mitigation**:
  - Regular automated backups
  - Point-in-time recovery capability
  - Backup verification procedures
  - Disaster recovery plan
  - Geographic backup distribution

**Risk: Resource Exhaustion**
- **Impact**: High - System unavailable
- **Probability**: Medium
- **Mitigation**:
  - Resource quotas per user
  - Container resource limits
  - Auto-scaling for agent pool
  - Monitoring and alerting
  - Rate limiting on API

**Risk: Insufficient Documentation**
- **Impact**: Medium - Difficult to operate and maintain
- **Probability**: Medium
- **Mitigation**:
  - Comprehensive operations runbook
  - API documentation (OpenAPI)
  - Architecture documentation
  - Troubleshooting guides
  - Regular documentation reviews

### 23.3 Business Risks

**Risk: Poor User Adoption**
- **Impact**: High - Platform not used, project failure
- **Probability**: Medium
- **Mitigation**:
  - User-friendly interface
  - Comprehensive onboarding
  - Agent templates for quick start
  - Regular user feedback collection
  - Iterative improvements based on feedback

**Risk: Compliance Violations**
- **Impact**: Critical - Legal issues, fines
- **Probability**: Low
- **Mitigation**:
  - Data classification system
  - Comprehensive audit logging
  - Access control enforcement
  - Regular compliance audits
  - Privacy-by-design approach

**Risk: Vendor Lock-in**
- **Impact**: Medium - Difficult to migrate
- **Probability**: Low
- **Mitigation**:
  - Use open-source components
  - Standard APIs (S3-compatible, PostgreSQL)
  - Avoid proprietary features
  - Data export capabilities
  - Modular architecture


## 24. Success Metrics

### 24.1 Technical Metrics

**Performance**
- API response time: p95 < 500ms, p99 < 1000ms
- Task decomposition time: < 5 seconds for typical goals
- Vector search latency: < 100ms for 1M vectors
- Document processing: < 30 seconds for 10-page PDF
- Agent startup time: < 10 seconds

**Reliability**
- System uptime: > 99.9%
- Task success rate: > 95%
- Agent failure rate: < 5%
- Data loss incidents: 0

**Scalability**
- Support 100 concurrent agents
- Handle 1000 API requests/second
- Store 10M+ vector embeddings
- Process 1000 documents/day

### 24.2 Business Metrics

**Adoption**
- Active users: Target 100+ in first 3 months
- Agents created: Target 500+ in first 3 months
- Tasks completed: Target 5000+ in first 3 months
- Knowledge items: Target 1000+ in first 3 months

**Efficiency**
- Time saved per task: Target 50% vs manual
- Goal completion rate: > 80%
- User satisfaction score: > 4.0/5.0
- Return on investment: Positive within 12 months

**Engagement**
- Daily active users: > 50% of registered users
- Tasks per user per week: > 5
- Knowledge base usage: > 70% of tasks use knowledge
- Agent reuse rate: > 60% of agents used multiple times

### 24.3 Quality Metrics

**Accuracy**
- Task decomposition accuracy: > 90% (user validation)
- Knowledge retrieval relevance: > 85% (user feedback)
- Agent output quality: > 4.0/5.0 (user rating)

**Security**
- Security incidents: 0 critical, < 5 medium per quarter
- Unauthorized access attempts blocked: 100%
- Compliance audit pass rate: 100%

**Maintainability**
- Code coverage: > 80%
- Documentation completeness: > 90%
- Mean time to resolve issues: < 24 hours
- Technical debt ratio: < 5%


## 25. Glossary

**Agent**: An autonomous AI entity capable of executing tasks using LLM capabilities, running in an isolated container with specific skills and access to memory systems.

**Agent Framework**: The LangChain-based infrastructure that manages agent lifecycle, skill assignment, and task execution.

**Agent Memory**: Private memory storage specific to each agent instance, used for agent-specific context and learning.

**Company Memory**: Shared memory accessible to all authorized agents for collaboration and organizational knowledge sharing.

**User Context**: A specialized area within Company Memory that stores user-specific information accessible to all agents owned by that user, enabling cross-agent information sharing.

**Knowledge Base**: Centralized repository of enterprise documents, policies, and domain knowledge, searchable via semantic similarity.

**Vector Database**: Database system (Milvus) for storing and retrieving embeddings for semantic similarity search.

**Primary Database**: Relational database (PostgreSQL) for storing platform operational data including agents, tasks, users, and permissions.

**Object Storage**: Storage system (MinIO) for large files including documents, audio, video, and agent artifacts.

**Task Manager**: Component responsible for accepting goals, decomposing them into hierarchical task structures, and coordinating agent execution.

**Skill Library**: Repository of reusable capabilities that can be assigned to agents, defining tools and functions agents can use.

**LLM Provider**: Service providing large language model capabilities, primarily local (Ollama/vLLM) with optional cloud fallback.

**Message Bus**: Communication infrastructure (Redis) for inter-agent messaging supporting pub/sub and point-to-point patterns.

**Virtualization System**: Docker-based infrastructure for isolated agent execution environments with resource limits.

**Document Processor**: Component for extracting text and metadata from uploaded documents, including OCR and transcription.

**API Gateway**: Entry point for external systems and user interfaces, handling authentication, routing, and rate limiting.

**Access Control System**: Component managing user authentication and authorization using RBAC and ABAC models.

**Goal**: High-level objective provided by a user to the platform for autonomous completion.

**Task**: Decomposed unit of work assigned to specific agents, potentially with dependencies on other tasks.

**Result Aggregator**: Component that combines outputs from multiple agents into final deliverables.

