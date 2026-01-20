# API Gateway

FastAPI-based API Gateway for the Digital Workforce Management Platform.

## Overview

The API Gateway serves as the entry point for all client requests, providing:
- RESTful API endpoints for all platform operations
- JWT-based authentication
- Rate limiting
- Request logging with correlation IDs
- WebSocket support for real-time updates
- OpenAPI/Swagger documentation

## Architecture

```
api_gateway/
├── main.py                 # FastAPI application and configuration
├── errors.py               # Error handling and structured responses
├── websocket.py            # WebSocket endpoint for real-time updates
├── middleware/             # Custom middleware
│   ├── auth.py            # JWT authentication middleware
│   ├── rate_limit.py      # Rate limiting middleware
│   └── logging.py         # Request logging middleware
├── routers/                # API route handlers
│   ├── auth.py            # Authentication endpoints
│   ├── users.py           # User management endpoints
│   ├── agents.py          # Agent management endpoints
│   ├── tasks.py           # Task management endpoints
│   └── knowledge.py       # Knowledge base endpoints
├── test_api_gateway.py    # Comprehensive test suite
└── README.md              # This file
```

## Features

### Authentication & Authorization
- JWT token-based authentication
- Token refresh mechanism
- Role-based access control (RBAC)
- Attribute-based access control (ABAC)
- Token blacklisting for logout

### Middleware
- **JWT Authentication**: Validates tokens and adds user info to request state
- **Rate Limiting**: Prevents API abuse with sliding window algorithm
- **Request Logging**: Logs all requests with correlation IDs and timing

### API Endpoints

#### Authentication (`/api/v1/auth`)
- `POST /login` - User login
- `POST /register` - User registration
- `POST /refresh` - Refresh access token
- `POST /logout` - User logout

#### Users (`/api/v1/users`)
- `GET /me` - Get current user profile
- `PUT /me` - Update current user profile
- `GET /{user_id}/quotas` - Get user resource quotas (admin/manager only)

#### Agents (`/api/v1/agents`)
- `POST /` - Create new agent
- `GET /` - List user's agents
- `GET /{agent_id}` - Get agent details
- `PUT /{agent_id}` - Update agent configuration
- `DELETE /{agent_id}` - Delete agent

#### Tasks (`/api/v1/tasks`)
- `POST /` - Submit new goal/task
- `GET /` - List user's tasks
- `GET /{task_id}` - Get task details
- `DELETE /{task_id}` - Cancel/delete task

#### Knowledge (`/api/v1/knowledge`)
- `POST /` - Upload knowledge document
- `GET /` - List accessible knowledge items
- `GET /{knowledge_id}` - Get knowledge item details
- `PUT /{knowledge_id}` - Update knowledge item
- `DELETE /{knowledge_id}` - Delete knowledge item

#### WebSocket (`/api/v1/ws`)
- `/tasks` - Real-time task status updates

### Error Handling
All errors return structured JSON responses:
```json
{
  "error": "error_code",
  "message": "Human-readable error message",
  "details": {
    "additional": "context"
  }
}
```

## Configuration

Configuration is loaded from `backend/config.yaml`:

```yaml
api:
  host: "0.0.0.0"
  port: 8000
  cors:
    origins:
      - "http://localhost:3000"
      - "http://localhost:5173"
    allow_credentials: true
    allow_methods: ["*"]
    allow_headers: ["*"]
  jwt:
    secret_key: "${JWT_SECRET}"
    algorithm: "HS256"
    expiration_hours: 24
    refresh_expiration_days: 7
  rate_limit:
    requests_per_minute: 60
```

## Running the API Gateway

### Development
```bash
cd backend
uvicorn api_gateway.main:app --reload --host 0.0.0.0 --port 8000
```

### Production
```bash
cd backend
gunicorn api_gateway.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

## Testing

Run the test suite:
```bash
cd backend
pytest api_gateway/test_api_gateway.py -v
```

Run with coverage:
```bash
pytest api_gateway/test_api_gateway.py --cov=api_gateway --cov-report=html
```

## API Documentation

Once the server is running, access the interactive API documentation:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## Implementation Status

### Completed (Section 2.1)
- ✅ FastAPI application with CORS configuration
- ✅ JWT authentication middleware
- ✅ Rate limiting middleware
- ✅ Request logging middleware
- ✅ Authentication endpoints (login, logout, refresh)
- ✅ User endpoints (profile, quotas)
- ✅ Agent endpoints (CRUD operations)
- ✅ Task endpoints (CRUD operations)
- ✅ Knowledge endpoints (CRUD operations)
- ✅ WebSocket endpoint for real-time updates
- ✅ OpenAPI/Swagger documentation
- ✅ Error handling with structured responses

### Pending Integration
The following endpoints are implemented but return 501 (Not Implemented) until integrated with:
- Database layer (PostgreSQL)
- Task Manager component
- Agent Framework component
- Object Storage (MinIO)
- Document Processor component

## Security

### Authentication
- JWT tokens with configurable expiration
- Refresh tokens for extended sessions
- Token blacklisting for logout
- Secure password hashing (bcrypt)

### Rate Limiting
- Sliding window algorithm
- Per-user and per-IP limits
- Configurable limits
- Retry-After headers

### CORS
- Configurable allowed origins
- Credentials support
- Preflight request handling

## Monitoring

### Request Logging
All requests are logged with:
- Correlation ID for request tracking
- HTTP method and path
- User information (if authenticated)
- Response status code
- Request duration
- Client IP and User-Agent

### Metrics
- Request count by endpoint
- Response time percentiles
- Error rates
- Active WebSocket connections

## References

- Requirements 15: API and Integration Layer
- Design Section 12: API Gateway
- Tasks 2.1.1 - 2.1.12: API Gateway Implementation
