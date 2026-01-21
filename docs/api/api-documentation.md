# API Documentation

This document provides comprehensive documentation for the LinX (灵枢) REST API.

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Endpoints](#endpoints)
4. [WebSocket API](#websocket-api)
5. [Error Handling](#error-handling)
6. [Rate Limiting](#rate-limiting)
7. [Examples](#examples)

## Overview

**Base URL**: `https://api.your-domain.com/api/v1`

**API Version**: v1

**Content Type**: `application/json`

**OpenAPI Specification**: Available at `/api/v1/docs` (Swagger UI)

## Authentication

### JWT Authentication

The API uses JWT (JSON Web Tokens) for authentication.

#### Login

```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "user@example.com",
  "password": "your_password"
}
```

**Response**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

#### Using the Token

Include the access token in the Authorization header:

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

#### Refresh Token

```http
POST /api/v1/auth/refresh
Content-Type: application/json

{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

#### Logout

```http
POST /api/v1/auth/logout
Authorization: Bearer {access_token}
```

## Endpoints

### Users

#### Get Current User

```http
GET /api/v1/users/me
Authorization: Bearer {access_token}
```

**Response**:
```json
{
  "id": "user-123",
  "username": "john.doe",
  "email": "john@example.com",
  "role": "user",
  "created_at": "2024-01-01T00:00:00Z"
}
```

#### Update Current User

```http
PUT /api/v1/users/me
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "email": "newemail@example.com",
  "display_name": "John Doe"
}
```

#### Get User Quotas

```http
GET /api/v1/users/{user_id}/quotas
Authorization: Bearer {access_token}
```

**Response**:
```json
{
  "max_agents": 10,
  "current_agents": 5,
  "max_storage_gb": 100,
  "current_storage_gb": 45.2,
  "max_cpu_cores": 8,
  "current_cpu_cores": 3.5
}
```

### Agents

#### List Agents

```http
GET /api/v1/agents
Authorization: Bearer {access_token}
```

**Query Parameters**:
- `status`: Filter by status (active, idle, terminated)
- `type`: Filter by agent type
- `limit`: Number of results (default: 50)
- `offset`: Pagination offset

**Response**:
```json
{
  "agents": [
    {
      "id": "agent-123",
      "name": "Data Analyst 1",
      "type": "data_analyst",
      "status": "active",
      "skills": ["data_processing", "sql_query"],
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-02T00:00:00Z"
    }
  ],
  "total": 5,
  "limit": 50,
  "offset": 0
}
```

#### Get Agent

```http
GET /api/v1/agents/{agent_id}
Authorization: Bearer {access_token}
```

#### Create Agent

```http
POST /api/v1/agents
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "name": "My Data Analyst",
  "type": "data_analyst",
  "description": "Analyzes sales data",
  "skills": ["data_processing", "sql_query"],
  "config": {
    "cpu_limit": 2,
    "memory_limit_mb": 2048
  }
}
```

**Response**:
```json
{
  "id": "agent-456",
  "name": "My Data Analyst",
  "type": "data_analyst",
  "status": "idle",
  "skills": ["data_processing", "sql_query"],
  "created_at": "2024-01-03T00:00:00Z"
}
```

#### Update Agent

```http
PUT /api/v1/agents/{agent_id}
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "name": "Updated Name",
  "description": "Updated description"
}
```

#### Delete Agent

```http
DELETE /api/v1/agents/{agent_id}
Authorization: Bearer {access_token}
```

#### Get Agent Templates

```http
GET /api/v1/agents/templates
Authorization: Bearer {access_token}
```

**Response**:
```json
{
  "templates": [
    {
      "id": "data_analyst",
      "name": "Data Analyst",
      "description": "Analyzes and processes data",
      "skills": ["data_processing", "sql_query", "data_visualization"],
      "default_config": {
        "cpu_limit": 2,
        "memory_limit_mb": 2048
      }
    }
  ]
}
```

### Tasks

#### List Tasks

```http
GET /api/v1/tasks
Authorization: Bearer {access_token}
```

**Query Parameters**:
- `status`: Filter by status (pending, in_progress, completed, failed)
- `agent_id`: Filter by agent
- `limit`: Number of results
- `offset`: Pagination offset

#### Get Task

```http
GET /api/v1/tasks/{task_id}
Authorization: Bearer {access_token}
```

**Response**:
```json
{
  "id": "task-123",
  "goal": "Analyze Q4 sales data",
  "status": "completed",
  "agent_id": "agent-123",
  "created_at": "2024-01-01T00:00:00Z",
  "completed_at": "2024-01-01T01:00:00Z",
  "result": {
    "summary": "Q4 sales increased by 15%",
    "details": {...}
  }
}
```

#### Create Task

```http
POST /api/v1/tasks
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "goal": "Analyze Q4 sales data and create a report",
  "priority": "high",
  "deadline": "2024-01-10T00:00:00Z"
}
```

**Response**:
```json
{
  "id": "task-456",
  "goal": "Analyze Q4 sales data and create a report",
  "status": "pending",
  "created_at": "2024-01-03T00:00:00Z"
}
```

#### Get Task Tree

```http
GET /api/v1/tasks/{task_id}/tree
Authorization: Bearer {access_token}
```

**Response**:
```json
{
  "task_id": "task-123",
  "goal": "Analyze Q4 sales data",
  "subtasks": [
    {
      "task_id": "task-124",
      "description": "Extract sales data from database",
      "status": "completed",
      "agent_id": "agent-123"
    },
    {
      "task_id": "task-125",
      "description": "Analyze trends",
      "status": "in_progress",
      "agent_id": "agent-124"
    }
  ]
}
```

#### Submit Clarification

```http
POST /api/v1/tasks/{task_id}/clarify
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "answers": {
    "question_1": "Q4 2023",
    "question_2": "All regions"
  }
}
```

#### Delete Task

```http
DELETE /api/v1/tasks/{task_id}
Authorization: Bearer {access_token}
```

### Knowledge Base

#### List Documents

```http
GET /api/v1/knowledge
Authorization: Bearer {access_token}
```

**Query Parameters**:
- `type`: Filter by document type
- `tags`: Filter by tags (comma-separated)
- `limit`: Number of results
- `offset`: Pagination offset

#### Get Document

```http
GET /api/v1/knowledge/{document_id}
Authorization: Bearer {access_token}
```

#### Upload Document

```http
POST /api/v1/knowledge
Authorization: Bearer {access_token}
Content-Type: multipart/form-data

file: <binary>
tags: ["sales", "report"]
access_level: "internal"
```

**Response**:
```json
{
  "id": "doc-123",
  "filename": "sales_report.pdf",
  "size_bytes": 1048576,
  "type": "pdf",
  "status": "processing",
  "uploaded_at": "2024-01-03T00:00:00Z"
}
```

#### Search Documents

```http
POST /api/v1/knowledge/search
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "query": "sales trends 2023",
  "limit": 10,
  "filters": {
    "type": ["pdf", "docx"],
    "tags": ["sales"]
  }
}
```

**Response**:
```json
{
  "results": [
    {
      "document_id": "doc-123",
      "filename": "sales_report.pdf",
      "relevance_score": 0.95,
      "snippet": "...sales trends in 2023 showed..."
    }
  ],
  "total": 5
}
```

#### Update Document

```http
PUT /api/v1/knowledge/{document_id}
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "tags": ["sales", "2023", "report"],
  "access_level": "confidential"
}
```

#### Delete Document

```http
DELETE /api/v1/knowledge/{document_id}
Authorization: Bearer {access_token}
```

### Memory

#### Get Agent Memory

```http
GET /api/v1/memory/agent/{agent_id}
Authorization: Bearer {access_token}
```

**Query Parameters**:
- `limit`: Number of results
- `offset`: Pagination offset

#### Get Company Memory

```http
GET /api/v1/memory/company
Authorization: Bearer {access_token}
```

#### Get User Context

```http
GET /api/v1/memory/user-context
Authorization: Bearer {access_token}
```

#### Share Memory

```http
POST /api/v1/memory/share
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "memory_id": "mem-123",
  "target_agent_ids": ["agent-456", "agent-789"],
  "note": "Relevant for your current task"
}
```

### Skills

#### List Skills

```http
GET /api/v1/skills
Authorization: Bearer {access_token}
```

#### Get Skill

```http
GET /api/v1/skills/{skill_id}
Authorization: Bearer {access_token}
```

#### Create Skill

```http
POST /api/v1/skills
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "name": "custom_analysis",
  "description": "Custom data analysis skill",
  "code": "def execute(data): ...",
  "dependencies": ["pandas", "numpy"]
}
```

## WebSocket API

### Connection

```javascript
const ws = new WebSocket('wss://api.your-domain.com/api/v1/ws');

// Authenticate
ws.send(JSON.stringify({
  type: 'auth',
  token: 'your_access_token'
}));
```

### Subscribe to Events

```javascript
// Subscribe to task updates
ws.send(JSON.stringify({
  type: 'subscribe',
  channel: 'tasks',
  filters: {
    user_id: 'user-123'
  }
}));

// Subscribe to agent updates
ws.send(JSON.stringify({
  type: 'subscribe',
  channel: 'agents',
  filters: {
    agent_id: 'agent-123'
  }
}));
```

### Receive Events

```javascript
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  switch(data.type) {
    case 'task_update':
      console.log('Task updated:', data.task);
      break;
    case 'agent_status':
      console.log('Agent status:', data.status);
      break;
    case 'system_metric':
      console.log('System metric:', data.metric);
      break;
  }
};
```

### Event Types

- `task_update`: Task status changed
- `agent_status`: Agent status changed
- `system_metric`: System metrics update
- `notification`: User notification

## Error Handling

### Error Response Format

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "Invalid request parameters",
    "details": {
      "field": "email",
      "reason": "Invalid email format"
    }
  }
}
```

### HTTP Status Codes

- `200 OK`: Success
- `201 Created`: Resource created
- `400 Bad Request`: Invalid request
- `401 Unauthorized`: Authentication required
- `403 Forbidden`: Insufficient permissions
- `404 Not Found`: Resource not found
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: Server error

### Error Codes

- `INVALID_REQUEST`: Invalid request parameters
- `AUTHENTICATION_FAILED`: Invalid credentials
- `UNAUTHORIZED`: Authentication required
- `FORBIDDEN`: Insufficient permissions
- `NOT_FOUND`: Resource not found
- `RATE_LIMIT_EXCEEDED`: Too many requests
- `QUOTA_EXCEEDED`: Resource quota exceeded
- `INTERNAL_ERROR`: Server error

## Rate Limiting

### Limits

- **Default**: 100 requests per minute
- **Authenticated**: 1000 requests per minute
- **Admin**: 10000 requests per minute

### Headers

Response includes rate limit headers:

```http
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 995
X-RateLimit-Reset: 1609459200
```

### Handling Rate Limits

When rate limit is exceeded (429 status):

```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded",
    "retry_after": 60
  }
}
```

Wait for `retry_after` seconds before retrying.

## Examples

### Python

```python
import requests

# Login
response = requests.post(
    'https://api.your-domain.com/api/v1/auth/login',
    json={
        'username': 'user@example.com',
        'password': 'password'
    }
)
token = response.json()['access_token']

# Create agent
headers = {'Authorization': f'Bearer {token}'}
response = requests.post(
    'https://api.your-domain.com/api/v1/agents',
    headers=headers,
    json={
        'name': 'My Agent',
        'type': 'data_analyst',
        'skills': ['data_processing']
    }
)
agent = response.json()

# Submit task
response = requests.post(
    'https://api.your-domain.com/api/v1/tasks',
    headers=headers,
    json={
        'goal': 'Analyze sales data'
    }
)
task = response.json()
```

### JavaScript

```javascript
// Login
const response = await fetch('https://api.your-domain.com/api/v1/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    username: 'user@example.com',
    password: 'password'
  })
});
const { access_token } = await response.json();

// Create agent
const agentResponse = await fetch('https://api.your-domain.com/api/v1/agents', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${access_token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    name: 'My Agent',
    type: 'data_analyst',
    skills: ['data_processing']
  })
});
const agent = await agentResponse.json();
```

### cURL

```bash
# Login
curl -X POST https://api.your-domain.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"user@example.com","password":"password"}'

# Create agent
curl -X POST https://api.your-domain.com/api/v1/agents \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"My Agent","type":"data_analyst","skills":["data_processing"]}'
```

## SDK Libraries

Official SDKs available:
- Python: `pip install linx-sdk`
- JavaScript/TypeScript: `npm install @linx/sdk`
- Go: `go get github.com/linx/sdk-go`

## Support

- **API Status**: https://status.your-domain.com
- **Documentation**: https://docs.your-domain.com
- **Support**: api-support@example.com
- **GitHub**: https://github.com/your-org/linx

## Changelog

See [API Changelog](./api-changelog.md) for version history and breaking changes.
