# Product Overview

LinX is an enterprise-grade Digital Workforce Management Platform for managing and coordinating AI agents and future robotic workers. The platform establishes a digital company structure enabling autonomous goal completion through hierarchical task management, collaborative agent coordination, and comprehensive knowledge management.

## Core Capabilities

- **Intelligent Agent Management**: LangChain-based AI agent framework with multiple agent types and templates
- **Hierarchical Task Management**: Automatic decomposition of high-level goals into executable tasks with dependency tracking
- **Multi-Tiered Memory System**: Agent Memory (private), Company Memory (shared), and User Context for seamless collaboration
- **Enterprise Knowledge Base**: Centralized document processing (PDF, DOCX, audio, video) with OCR and transcription
- **Privacy-First Architecture**: Local LLM deployment with complete data privacy using Ollama/vLLM
- **Secure Code Execution**: Multi-layer sandbox isolation (gVisor, Firecracker, Docker)

## Key Features

- Multi-provider LLM support (Ollama primary, vLLM, optional cloud fallback)
- Real-time task visualization via WebSocket
- Vector search with Milvus for semantic similarity
- RBAC and ABAC access control
- Comprehensive monitoring with Prometheus metrics and structured logging
- Containerized deployment with Docker and Kubernetes support

## Architecture

The platform uses a microservices architecture with:
- FastAPI-based API Gateway
- PostgreSQL for operational data
- Milvus for vector embeddings
- Redis for message bus
- MinIO for object storage
- LangChain for agent framework
