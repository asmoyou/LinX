# Access Control System

The Access Control System implements authentication and authorization for the Digital Workforce Platform using Role-Based Access Control (RBAC) and Attribute-Based Access Control (ABAC) models.

## References

- **Requirements 14**: User-Based Access Control
- **Design Section 8**: Access Control System
- **Design Section 3.1**: PostgreSQL Schema (users table)

## Features

- **Secure Password Hashing**: Uses bcrypt for password hashing with automatic salt generation
- **User Management**: Create, retrieve, and authenticate users
- **JWT Authentication**: Token-based authentication with access and refresh tokens
- **RBAC Support**: Role-based access control with predefined roles (admin, manager, user, viewer)
- **ABAC Support**: Attribute-based access control for fine-grained permissions
- **Permission Checking**: Middleware and decorators for endpoint protection
- **Password Verification**: Secure password verification with timing-attack resistance

## Components

### 1. User Management (`models.py`)

Password hashing and user model operations.

The module uses `passlib` with bcrypt for secure password hashing:

```python
from access_control.models import hash_password, verify_password

# Hash a password
hashed = hash_password("my_secure_password")

# Verify a password
is_valid = verify_password("my_secure_password", hashed)
```

**Security Features:**
- Automatic salt generation (different hash for same password)
- Adaptive hashing (configurable work factor)
- Timing-attack resistant verification
- Industry-standard bcrypt algorithm

### UserModel

The `UserModel` class provides a high-level interface for user management:

```python
from database.connection import get_db_session
from access_control.models import UserModel

# Create a new user
with get_db_session() as session:
    user = UserModel.create(
        session=session,
        username="john_doe",
        email="john@example.com",
        password="secure_password",
        role="user",
        attributes={"department": "engineering"}
    )
    session.commit()

# Authenticate a user
with get_db_session() as session:
    user = UserModel.authenticate(session, "john_doe", "secure_password")
    if user:
        print(f"Authenticated: {user.username}")

# Retrieve a user
with get_db_session() as session:
    user = UserModel.get_by_username(session, "john_doe")
    if user:
        print(f"Found user: {user.email}")

# Change password
with get_db_session() as session:
    user = UserModel.get_by_username(session, "john_doe")
    user.set_password("new_secure_password")
    session.commit()
```

## User Model Fields

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | UUID | Unique user identifier (auto-generated) |
| `username` | String | Unique username (indexed) |
| `email` | String | Unique email address (indexed) |
| `password_hash` | String | Bcrypt hashed password |
| `role` | String | User role for RBAC (default: "user") |
| `attributes` | JSONB | Flexible attributes for ABAC |
| `created_at` | Timestamp | User creation timestamp |
| `updated_at` | Timestamp | Last update timestamp |

## RBAC Roles

The system supports the following predefined roles:

- **admin**: Full system access
- **manager**: Manage users and agents
- **user**: Standard user access (default)
- **viewer**: Read-only access

## ABAC Attributes

Users can have flexible JSONB attributes for fine-grained access control:

```python
attributes = {
    "department": "engineering",
    "clearance_level": "high",
    "location": "headquarters",
    "projects": ["project_a", "project_b"]
}
```

## Usage Examples

### Creating Users with Different Roles

```python
from database.connection import get_db_session
from access_control.models import UserModel

with get_db_session() as session:
    # Create admin user
    admin = UserModel.create(
        session=session,
        username="admin",
        email="admin@company.com",
        password="admin_password",
        role="admin"
    )
    
    # Create regular user with attributes
    user = UserModel.create(
        session=session,
        username="engineer",
        email="engineer@company.com",
        password="user_password",
        role="user",
        attributes={
            "department": "engineering",
            "clearance_level": "standard"
        }
    )
    
    session.commit()
```

### Authentication Flow

```python
from database.connection import get_db_session
from access_control.models import UserModel

def login(username: str, password: str):
    with get_db_session() as session:
        user = UserModel.authenticate(session, username, password)
        
        if user:
            # Generate JWT token (implemented in separate module)
            return {
                "success": True,
                "user_id": str(user.user_id),
                "username": user.username,
                "role": user.role
            }
        else:
            return {"success": False, "error": "Invalid credentials"}
```

### Password Reset

```python
from database.connection import get_db_session
from access_control.models import UserModel

def reset_password(username: str, old_password: str, new_password: str):
    with get_db_session() as session:
        # Authenticate with old password
        user = UserModel.authenticate(session, username, old_password)
        
        if user:
            # Set new password
            user.set_password(new_password)
            session.commit()
            return {"success": True}
        else:
            return {"success": False, "error": "Invalid credentials"}
```

## Testing

Run the unit tests:

```bash
cd backend
pytest access_control/test_models.py -v
```

Run with coverage:

```bash
pytest access_control/test_models.py --cov=access_control --cov-report=term
```

## Security Considerations

1. **Password Storage**: Passwords are never stored in plain text. Only bcrypt hashes are stored.

2. **Salt Generation**: Each password hash uses a unique random salt, preventing rainbow table attacks.

3. **Timing Attacks**: Password verification uses constant-time comparison to prevent timing attacks.

4. **Password Complexity**: The application layer should enforce password complexity requirements (minimum length, character types, etc.).

5. **Rate Limiting**: Authentication endpoints should implement rate limiting to prevent brute-force attacks.

6. **Audit Logging**: All authentication attempts should be logged for security monitoring.

## Future Enhancements

- ~~JWT token generation and validation (Task 2.2.2)~~ ✅ **Completed**
- ~~RBAC role definitions (Task 2.2.3)~~ ✅ **Completed**
- RBAC permission checking (Task 2.2.4)
- ABAC attribute evaluation engine (Task 2.2.5)
- Permission policy loader (Task 2.2.6)
- User registration API (Task 2.2.7)
- Audit logging for access control decisions (Task 2.2.11)

## Dependencies

- `passlib[bcrypt]`: Password hashing library
- `bcrypt`: Bcrypt algorithm implementation
- `sqlalchemy`: ORM for database operations
- `database.models`: Database model definitions

## Related Modules

- `database`: Database connection and models
- `api_gateway`: API endpoints for authentication
- `shared.logging`: Structured logging for audit trails


---

## JWT Authentication Module

### Overview

The JWT Authentication module (`jwt_auth.py`) provides JSON Web Token functionality for secure, stateless authentication.

**References:**
- **Requirements 15**: API and Integration Layer
- **Design Section 8.1**: Authentication (JWT-Based Authentication)

### Features

- **Access Token Generation**: Short-lived tokens (default 24 hours)
- **Refresh Token Generation**: Long-lived tokens (default 7 days)
- **Token Validation**: Decode and verify JWT tokens
- **Token Refresh**: Generate new access tokens without re-authentication
- **Token Blacklist**: Revoke tokens before expiration (logout support)
- **Configurable Expiration**: Customize token lifetimes via configuration
- **Token Utilities**: Helper functions for token management

### Configuration

JWT settings are configured in `backend/config.yaml`:

```yaml
api:
  jwt:
    secret_key: "${JWT_SECRET}"  # Set via environment variable
    algorithm: "HS256"
    expiration_hours: 24
    refresh_expiration_days: 7
```

**Environment Variables:**

```bash
# Required for production
JWT_SECRET=your-secret-key-here-change-in-production

# Optional overrides
JWT_EXPIRATION_HOURS=24
JWT_REFRESH_EXPIRATION_DAYS=7
```

⚠️ **Security Warning**: Never commit the JWT secret key to version control!

### Token Structure

JWT tokens contain the following claims:

| Claim | Type | Description |
|-------|------|-------------|
| `user_id` | String (UUID) | User's unique identifier |
| `username` | String | User's username |
| `role` | String | User's role for RBAC |
| `token_type` | String | "access" or "refresh" |
| `exp` | Integer | Expiration timestamp (Unix) |
| `iat` | Integer | Issued at timestamp (Unix) |
| `jti` | String (UUID) | JWT ID for blacklist support |

### Usage Examples

#### Creating Token Pairs

```python
from access_control import create_token_pair
import uuid

# Create both access and refresh tokens
user_id = uuid.uuid4()
tokens = create_token_pair(
    user_id=user_id,
    username="john_doe",
    role="user"
)

print(f"Access Token: {tokens.access_token}")
print(f"Refresh Token: {tokens.refresh_token}")
print(f"Token Type: {tokens.token_type}")  # "bearer"
print(f"Expires in: {tokens.expires_in} seconds")
```

#### Validating Tokens

```python
from access_control import decode_token, JWTTokenExpiredError, JWTTokenInvalidError

try:
    # Decode and validate token
    token_data = decode_token(access_token)
    
    print(f"User ID: {token_data.user_id}")
    print(f"Username: {token_data.username}")
    print(f"Role: {token_data.role}")
    print(f"Token Type: {token_data.token_type}")
    
except JWTTokenExpiredError:
    print("Token has expired, please login again")
    
except JWTTokenInvalidError as e:
    print(f"Invalid token: {e}")
```

#### Refreshing Access Tokens

```python
from access_control import refresh_access_token

try:
    # Generate new access token using refresh token
    new_access_token = refresh_access_token(refresh_token)
    print(f"New access token: {new_access_token}")
    
except JWTTokenExpiredError:
    print("Refresh token expired, please login again")
    
except JWTTokenInvalidError:
    print("Invalid refresh token")
```

#### Token Blacklist (Logout)

```python
from access_control import blacklist_token, is_token_blacklisted

# Logout: blacklist the token
blacklist_token(access_token)

# Check if token is blacklisted
if is_token_blacklisted(access_token):
    print("Token has been revoked")
```

#### Token Utilities

```python
from access_control import get_token_expiration, get_token_remaining_time

# Get expiration datetime
expiration = get_token_expiration(access_token)
print(f"Token expires at: {expiration}")

# Get remaining time
remaining = get_token_remaining_time(access_token)
if remaining:
    print(f"Token valid for: {remaining.total_seconds()} seconds")
else:
    print("Token has expired")
```

### Complete Authentication Flow

```python
from database.connection import get_db_session
from access_control import UserModel, create_token_pair, decode_token, blacklist_token

# 1. User Login
def login(username: str, password: str):
    with get_db_session() as session:
        # Authenticate user
        user = UserModel.authenticate(session, username, password)
        
        if not user:
            return {"success": False, "error": "Invalid credentials"}
        
        # Generate tokens
        tokens = create_token_pair(
            user_id=user.user_id,
            username=user.username,
            role=user.role
        )
        
        return {
            "success": True,
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "token_type": tokens.token_type,
            "expires_in": tokens.expires_in
        }

# 2. Protected Endpoint
def get_user_profile(access_token: str):
    try:
        # Validate token
        token_data = decode_token(access_token)
        
        # Fetch user data
        with get_db_session() as session:
            user = UserModel.get_by_id(session, uuid.UUID(token_data.user_id))
            return user.to_dict()
            
    except JWTTokenExpiredError:
        return {"error": "Token expired"}
    except JWTTokenInvalidError:
        return {"error": "Invalid token"}

# 3. User Logout
def logout(access_token: str):
    blacklist_token(access_token)
    return {"success": True, "message": "Logged out successfully"}
```

### FastAPI Integration

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthCredentials
from access_control import decode_token, JWTTokenExpiredError, JWTTokenInvalidError, TokenData

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthCredentials = Depends(security)
) -> TokenData:
    """Dependency to get current authenticated user from JWT token."""
    try:
        token_data = decode_token(credentials.credentials)
        return token_data
    except JWTTokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTTokenInvalidError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

# Use in endpoints
@app.get("/api/v1/users/me")
async def get_current_user_profile(
    current_user: TokenData = Depends(get_current_user)
):
    return {
        "user_id": current_user.user_id,
        "username": current_user.username,
        "role": current_user.role
    }

@app.post("/api/v1/auth/logout")
async def logout(
    current_user: TokenData = Depends(get_current_user),
    credentials: HTTPAuthCredentials = Depends(security)
):
    blacklist_token(credentials.credentials)
    return {"message": "Successfully logged out"}
```

### Exception Handling

The module provides specific exception types:

```python
from access_control import (
    JWTAuthenticationError,      # Base exception
    JWTTokenExpiredError,         # Token expired
    JWTTokenInvalidError,         # Token invalid/malformed
)

try:
    token_data = decode_token(token)
except JWTTokenExpiredError:
    # Handle expired token - prompt for re-authentication or refresh
    pass
except JWTTokenInvalidError as e:
    # Handle invalid token - log security event
    pass
except JWTAuthenticationError as e:
    # Handle any JWT authentication error
    pass
```

### Testing

Run JWT authentication tests:

```bash
cd backend

# Run all JWT tests
pytest access_control/test_jwt_auth.py -v

# Run with coverage
pytest access_control/test_jwt_auth.py --cov=access_control.jwt_auth --cov-report=term

# Run specific test class
pytest access_control/test_jwt_auth.py::TestTokenGeneration -v
```

**Test Coverage:**
- ✅ Token generation (access and refresh)
- ✅ Token validation and decoding
- ✅ Token expiration handling
- ✅ Token refresh mechanism
- ✅ Token blacklist functionality
- ✅ Token utilities (expiration, remaining time)
- ✅ Edge cases and error conditions
- ✅ 29 tests with 98% code coverage

### Security Features

#### Token Security
- **HS256 Algorithm**: Industry-standard HMAC with SHA-256
- **Secret Key**: Configurable via environment variables
- **Token Expiration**: Automatic expiration enforcement
- **Token Blacklist**: Revoke tokens before expiration
- **JWT ID (jti)**: Unique identifier for each token
- **Separate Token Types**: Access and refresh tokens with different lifetimes

#### Best Practices
1. **Store tokens securely**: Use HTTP-only cookies or secure storage
2. **Use HTTPS**: Always transmit tokens over encrypted connections
3. **Rotate secrets**: Periodically rotate JWT secret keys
4. **Short-lived access tokens**: Keep access token expiration short
5. **Refresh token rotation**: Consider rotating refresh tokens on use
6. **Monitor blacklist**: Track blacklisted tokens for security analysis

### Production Considerations

#### Token Blacklist with Redis

The current implementation uses in-memory storage for the token blacklist. For production, use Redis:

```python
import redis
from datetime import timedelta

# Redis client
redis_client = redis.Redis(host='localhost', port=6379, db=0)

def blacklist_token_redis(token: str):
    """Blacklist token using Redis with TTL."""
    token_data = decode_token(token)
    
    if token_data.jti and token_data.exp:
        # Calculate TTL (time until token expires)
        ttl = token_data.exp - int(datetime.utcnow().timestamp())
        
        if ttl > 0:
            # Store in Redis with TTL
            redis_client.setex(
                f"blacklist:{token_data.jti}",
                timedelta(seconds=ttl),
                "1"
            )

def is_token_blacklisted_redis(token: str) -> bool:
    """Check if token is blacklisted in Redis."""
    try:
        config = get_jwt_config()
        payload = jwt.decode(token, config["secret_key"], algorithms=[config["algorithm"]])
        token_id = payload.get("jti")
        
        if token_id:
            return redis_client.exists(f"blacklist:{token_id}") > 0
        return False
    except:
        return False
```

#### Rate Limiting

Implement rate limiting for authentication endpoints:

```python
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/v1/auth/login")
@limiter.limit("5/minute")  # 5 attempts per minute
async def login(request: Request, credentials: LoginCredentials):
    # Login logic
    pass
```

#### Token Rotation

Implement refresh token rotation for enhanced security:

```python
def refresh_with_rotation(refresh_token: str) -> TokenPair:
    """Refresh access token and rotate refresh token."""
    # Verify refresh token
    token_data = verify_token(refresh_token, expected_type="refresh")
    
    # Blacklist old refresh token
    blacklist_token(refresh_token)
    
    # Create new token pair
    return create_token_pair(
        user_id=uuid.UUID(token_data.user_id),
        username=token_data.username,
        role=token_data.role
    )
```

### API Endpoints

Typical JWT authentication endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/auth/login` | POST | Authenticate and get tokens |
| `/api/v1/auth/logout` | POST | Blacklist token (logout) |
| `/api/v1/auth/refresh` | POST | Refresh access token |
| `/api/v1/users/me` | GET | Get current user profile |

### Dependencies

- `python-jose[cryptography]`: JWT encoding/decoding
- `pydantic`: Data validation and models
- `shared.config`: Configuration management

### Related Documentation

- [User Model Documentation](#usermodel)
- [API Gateway Authentication](../api_gateway/README.md)
- [Security Best Practices](../../docs/security.md)

### Task Status

✅ **Task 2.2.2 Complete**: JWT token generation and validation implemented with:
- Access token generation with configurable expiration
- Refresh token generation with longer expiration
- Token validation and decoding
- Token refresh mechanism
- Token blacklist support for logout
- Comprehensive unit tests (29 tests, 98% coverage)
- Full documentation and usage examples


---

## RBAC (Role-Based Access Control) Module

### Overview

The RBAC module (`rbac.py`) provides role definitions and permission management for the Digital Workforce Platform.

**References:**
- **Requirements 14**: User-Based Access Control
- **Design Section 8**: Access Control System
- **Task 2.2.3**: Create RBAC role definitions

### Features

- **Four Standard Roles**: admin, manager, user, viewer
- **Role Hierarchy**: admin > manager > user > viewer
- **Permission Scopes**: Granular control with resource types and actions
- **Permission Inheritance**: Higher roles inherit lower role permissions
- **Flexible Permission Checking**: Support for wildcard scopes and MANAGE action
- **Comprehensive API**: Functions for role validation, permission checking, and role management

### Role Definitions

#### Viewer Role
**Description**: Read-only access to permitted resources

**Permissions**:
- View agents user has permission to see
- View tasks user has permission to see
- View knowledge base items user has permission to see
- View memory user has permission to see
- View own user profile

**Use Cases**: External stakeholders, auditors, read-only users

#### User Role
**Description**: Standard user access (create/manage own agents, tasks, knowledge)

**Permissions** (in addition to Viewer permissions):
- Create and manage own agents (create, read, update, delete, execute)
- Create and manage own tasks (create, read, update, delete, execute)
- Upload and manage own knowledge base items (create, read, update, delete)
- Access own agent memory (read, create)
- Manage own user profile (read, update)

**Use Cases**: Regular platform users, individual contributors

#### Manager Role
**Description**: Manage users and agents, view all data

**Permissions** (in addition to User permissions):
- Manage all agents (create, read, update, delete, execute)
- View and manage all tasks (create, read, update, delete)
- View all knowledge base items (read, update)
- View all memory (read)
- Manage users (read, create, update non-admin users)

**Use Cases**: Team leads, department managers, supervisors

#### Admin Role
**Description**: Full system access (all permissions)

**Permissions** (in addition to Manager permissions):
- Full control over all agents (MANAGE)
- Full control over all tasks (MANAGE)
- Full control over knowledge base (MANAGE)
- Full control over memory system (MANAGE)
- Full control over users (MANAGE)
- Full control over system configuration (MANAGE)

**Use Cases**: System administrators, platform operators

### Resource Types

The platform defines six resource types:

| Resource Type | Description |
|---------------|-------------|
| `agents` | AI agents and their configurations |
| `tasks` | Tasks and goals submitted to the platform |
| `knowledge` | Knowledge base items (documents, policies) |
| `memory` | Agent memory and company memory |
| `users` | User accounts and profiles |
| `system` | System configuration and settings |

### Actions

The platform defines six actions:

| Action | Description |
|--------|-------------|
| `create` | Create new resources |
| `read` | View/retrieve resources |
| `update` | Modify existing resources |
| `delete` | Remove resources |
| `execute` | Execute agents or tasks |
| `manage` | Full control (grants all actions) |

### Permission Scopes

Permissions can have optional scopes for fine-grained control:

| Scope | Description |
|-------|-------------|
| `None` | No scope restriction (applies to all) |
| `own` | Only user's own resources |
| `permitted` | Resources user has explicit permission for |
| `non-admin` | All resources except admin-owned |

### Usage Examples

#### Check User Permissions

```python
from access_control import Role, ResourceType, Action, check_permission

# Check if user can create agents
can_create = check_permission(Role.USER, ResourceType.AGENTS, Action.CREATE)
print(f"User can create agents: {can_create}")  # True

# Check if viewer can delete agents
can_delete = check_permission(Role.VIEWER, ResourceType.AGENTS, Action.DELETE)
print(f"Viewer can delete agents: {can_delete}")  # False

# Check if manager can read all tasks
can_read_all = check_permission(Role.MANAGER, ResourceType.TASKS, Action.READ)
print(f"Manager can read all tasks: {can_read_all}")  # True
```

#### Get Role Permissions

```python
from access_control import Role, get_role_permissions

# Get all permissions for a role (including inherited)
user_perms = get_role_permissions(Role.USER, include_inherited=True)
print(f"User has {len(user_perms)} total permissions")

# Get only direct permissions (not inherited)
user_direct = get_role_permissions(Role.USER, include_inherited=False)
print(f"User has {len(user_direct)} direct permissions")

# Print all permissions
for perm in user_perms:
    print(f"  - {perm}")
```

#### Validate Roles

```python
from access_control import validate_role, get_all_roles

# Validate role name
if validate_role("admin"):
    print("Valid role")

# Get all available roles
roles = get_all_roles()
print(f"Available roles: {[r.value for r in roles]}")
```

#### Check Role Hierarchy

```python
from access_control import Role, is_role_higher_or_equal, get_role_hierarchy

# Check if admin has higher privilege than user
if is_role_higher_or_equal(Role.ADMIN, Role.USER):
    print("Admin has higher or equal privilege than user")

# Get hierarchy levels
hierarchy = get_role_hierarchy()
for role, level in hierarchy.items():
    print(f"{role.value}: level {level}")
```

#### Get Role Summary

```python
from access_control import get_role_summary
import json

# Get comprehensive role summary
summary = get_role_summary()
print(json.dumps(summary, indent=2))

# Output:
# {
#   "viewer": {
#     "display_name": "Viewer",
#     "description": "Read-only access to permitted resources",
#     "inherits_from": null,
#     "direct_permissions": 5,
#     "total_permissions": 5,
#     "permissions": [...]
#   },
#   ...
# }
```

#### Working with Permission Objects

```python
from access_control import Permission, ResourceType, Action

# Create a permission
perm = Permission(
    resource_type=ResourceType.AGENTS,
    action=Action.CREATE,
    scope="own",
    description="Create own agents"
)

print(f"Permission: {perm}")  # agents:create:own
print(f"Resource: {perm.resource_type.value}")  # agents
print(f"Action: {perm.action.value}")  # create
print(f"Scope: {perm.scope}")  # own
```

#### Role-Based Access Control in API

```python
from fastapi import Depends, HTTPException, status
from access_control import (
    TokenData,
    Role,
    ResourceType,
    Action,
    check_permission,
    get_current_user  # From JWT auth examples
)

async def require_permission(
    resource_type: ResourceType,
    action: Action,
    scope: str = None
):
    """Dependency to check if current user has required permission."""
    async def permission_checker(
        current_user: TokenData = Depends(get_current_user)
    ):
        user_role = Role(current_user.role)
        
        if not check_permission(user_role, resource_type, action, scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions: {resource_type.value}:{action.value}"
            )
        
        return current_user
    
    return permission_checker

# Use in endpoints
@app.post("/api/v1/agents")
async def create_agent(
    agent_data: AgentCreate,
    current_user: TokenData = Depends(
        require_permission(ResourceType.AGENTS, Action.CREATE)
    )
):
    # Only users with agent creation permission can access this
    return {"message": "Agent created"}

@app.delete("/api/v1/agents/{agent_id}")
async def delete_agent(
    agent_id: str,
    current_user: TokenData = Depends(
        require_permission(ResourceType.AGENTS, Action.DELETE, "own")
    )
):
    # Check if user owns the agent
    # Implementation depends on agent ownership logic
    return {"message": "Agent deleted"}
```

#### Custom Permission Checking

```python
from access_control import Role, get_role_definition

def can_user_manage_other_user(user_role: Role, target_role: Role) -> bool:
    """Check if a user can manage another user based on roles."""
    role_def = get_role_definition(user_role)
    
    if not role_def:
        return False
    
    # Admin can manage anyone
    if user_role == Role.ADMIN:
        return True
    
    # Manager can manage non-admin users
    if user_role == Role.MANAGER and target_role != Role.ADMIN:
        return True
    
    return False

# Usage
if can_user_manage_other_user(Role.MANAGER, Role.USER):
    print("Manager can manage user")
```

### Permission Inheritance

Roles inherit permissions from lower-privilege roles:

```
Admin (inherits from Manager)
  └─ Manager (inherits from User)
      └─ User (inherits from Viewer)
          └─ Viewer (no inheritance)
```

**Example**:
- Viewer has 5 direct permissions
- User has 10 direct permissions + 5 inherited from Viewer = 15 total
- Manager has 8 direct permissions + 15 inherited from User = 23 total
- Admin has 6 direct permissions + 23 inherited from Manager = 29 total

### Special Permission Rules

#### Wildcard Scope
A permission with `scope=None` grants access to all scopes:
```python
# Permission: agents:read (no scope)
# Grants: agents:read:own, agents:read:all, agents:read:permitted, etc.
```

#### MANAGE Action
The `MANAGE` action grants all other actions:
```python
# Permission: agents:manage
# Grants: agents:create, agents:read, agents:update, agents:delete, agents:execute
```

### Testing

Run RBAC tests:

```bash
cd backend

# Run all RBAC tests
pytest access_control/test_rbac.py -v

# Run with coverage
pytest access_control/test_rbac.py --cov=access_control.rbac --cov-report=term

# Run specific test class
pytest access_control/test_rbac.py::TestPermissionChecking -v
```

**Test Coverage**:
- ✅ Permission creation and equality
- ✅ Role definition and inheritance
- ✅ Role validation
- ✅ Role hierarchy
- ✅ Permission checking for all roles
- ✅ Permission inheritance
- ✅ Wildcard scopes and MANAGE action
- ✅ Edge cases and error conditions
- ✅ 43 tests with 98% code coverage

### Security Considerations

1. **Principle of Least Privilege**: Assign users the minimum role required for their tasks

2. **Role Hierarchy**: Higher roles automatically inherit lower role permissions

3. **Scope Restrictions**: Use scopes to limit permissions to specific resources

4. **Permission Auditing**: Log all permission checks for security monitoring

5. **Role Assignment**: Only admins and managers should be able to assign roles

6. **Default Role**: New users should default to the "user" role

### Integration with Other Modules

#### With User Model
```python
from database.connection import get_db_session
from access_control import UserModel, Role, check_permission, ResourceType, Action

with get_db_session() as session:
    # Create user with specific role
    user = UserModel.create(
        session=session,
        username="john_doe",
        email="john@example.com",
        password="secure_password",
        role=Role.USER.value  # Assign user role
    )
    
    # Check user's permissions
    user_role = Role(user.role)
    can_create_agents = check_permission(
        user_role,
        ResourceType.AGENTS,
        Action.CREATE
    )
```

#### With JWT Authentication
```python
from access_control import create_token_pair, Role

# Include role in JWT token
tokens = create_token_pair(
    user_id=user.user_id,
    username=user.username,
    role=Role.USER.value  # Role included in token
)

# Token payload will contain:
# {
#   "user_id": "...",
#   "username": "john_doe",
#   "role": "user",  # Used for permission checking
#   ...
# }
```

### Configuration

RBAC roles and permissions are defined in code and do not require configuration. However, you can customize:

```python
# Custom permission checking logic
from access_control.rbac import ROLE_DEFINITIONS, Role, Permission

# Add custom permission to a role (not recommended in production)
custom_perm = Permission(ResourceType.AGENTS, Action.EXECUTE, "team")
ROLE_DEFINITIONS[Role.MANAGER].permissions.add(custom_perm)
```

**Note**: Modifying role definitions at runtime is not recommended. Instead, use ABAC (Attribute-Based Access Control) for dynamic permissions.

### Task Status

✅ **Task 2.2.3 Complete**: RBAC role definitions implemented with:
- Four standard roles (admin, manager, user, viewer)
- Role hierarchy with inheritance
- Six resource types (agents, tasks, knowledge, memory, users, system)
- Six actions (create, read, update, delete, execute, manage)
- Permission scopes for fine-grained control
- Comprehensive permission checking functions
- Role validation and management utilities
- Full documentation and usage examples
- 43 unit tests with 98% code coverage

## 5. ABAC Engine (`abac.py`)

✅ **COMPLETED** - Task 2.2.5

The ABAC (Attribute-Based Access Control) engine provides fine-grained access control based on user attributes, resource attributes, and environmental conditions.

### Key Features

- **Flexible Conditions**: Support for multiple comparison operators (==, !=, >, >=, <, <=, in, contains, etc.)
- **Logical Operators**: Combine conditions with AND, OR, NOT
- **Nested Conditions**: Support for complex nested condition groups
- **Policy Management**: Add, remove, enable/disable policies
- **Priority System**: Higher priority policies evaluated first
- **DENY Precedence**: DENY policies always override ALLOW policies
- **Default Deny**: No access granted unless explicitly allowed
- **Environmental Conditions**: Time-based and context-based access control

### Basic Usage

```python
from access_control.abac import (
    ABACPolicy,
    ABACEvaluationEngine,
    Condition,
    ConditionGroup,
    ConditionOperator,
    LogicalOperator,
    PolicyEffect,
)

# Create engine
engine = ABACEvaluationEngine()

# Define policy
policy = ABACPolicy(
    policy_id="eng-access",
    name="Engineering Access",
    description="Allow engineering to read internal resources",
    effect=PolicyEffect.ALLOW,
    resource_type="knowledge",
    actions=["read"],
    conditions=ConditionGroup(
        operator=LogicalOperator.AND,
        conditions=[
            Condition("user.department", ConditionOperator.EQUALS, "engineering"),
            Condition("resource.classification", ConditionOperator.EQUALS, "internal")
        ]
    ),
    priority=100
)

# Add policy
engine.add_policy(policy)

# Evaluate access
allowed = engine.evaluate(
    user_attributes={"department": "engineering"},
    resource_type="knowledge",
    resource_attributes={"classification": "internal"},
    action="read"
)
```

### Policy Helpers

Pre-built policy creation functions:

```python
from access_control.abac import (
    create_department_access_policy,
    create_clearance_level_policy,
    create_business_hours_policy,
)

# Department-based access
policy1 = create_department_access_policy(
    policy_id="dept-policy",
    department="engineering",
    resource_type="knowledge",
    actions=["read", "write"],
    priority=100
)

# Clearance level access
policy2 = create_clearance_level_policy(
    policy_id="clearance-policy",
    required_clearance=3,
    resource_type="knowledge",
    actions=["read"],
    priority=200
)

# Business hours restriction
policy3 = create_business_hours_policy(
    policy_id="hours-policy",
    resource_type="knowledge",
    actions=["read", "write"],
    start_hour=9,
    end_hour=17,
    priority=50
)
```

### Integration with User Attributes

ABAC uses the `User.attributes` JSONB field:

```python
from database.models import User

# User with attributes
user = User(
    username="john.doe",
    email="john@example.com",
    role="user",
    attributes={
        "department": "engineering",
        "clearance_level": 3,
        "projects": ["project-x", "project-y"],
        "location": "US"
    }
)

# Use in ABAC evaluation
allowed = engine.evaluate(
    user_attributes=user.attributes,
    resource_type="knowledge",
    resource_attributes={"classification": "internal"},
    action="read"
)
```

### Testing

- 35 comprehensive unit tests
- 91% code coverage on abac.py
- Tests cover all operators, logic, and scenarios
- See `test_abac.py` for examples

### Documentation

See `ABAC_IMPLEMENTATION_SUMMARY.md` for:
- Detailed implementation notes
- Usage examples
- Integration guide
- Performance considerations

---

## 6. Policy Loader (Task 2.2.6) ✅

### Overview

The Policy Loader provides database persistence and management for ABAC policies. It bridges the gap between PostgreSQL storage and the in-memory ABAC evaluation engine.

### Features

- **CRUD Operations**: Create, read, update, delete policies
- **Serialization**: Convert policies to/from database format
- **Engine Synchronization**: Automatically sync with ABAC engine
- **Startup Loading**: Load policies from database on application start
- **Policy Management**: Enable/disable policies without deletion

### Database Model

```python
class ABACPolicyModel(Base):
    """ABAC policies table."""
    __tablename__ = 'abac_policies'
    
    policy_id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=False)
    effect = Column(String(50), nullable=False, index=True)
    resource_type = Column(String(100), nullable=False, index=True)
    actions = Column(JSONB, nullable=False)
    conditions = Column(JSONB, nullable=False)
    priority = Column(Integer, nullable=False, default=0, index=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
```

### Usage

#### Creating a Policy

```python
from access_control import (
    PolicyLoader,
    ABACPolicy,
    PolicyEffect,
    ConditionGroup,
    Condition,
    ConditionOperator,
    LogicalOperator,
)

# Create policy
policy = ABACPolicy(
    policy_id="eng-internal-access",
    name="Engineering Internal Access",
    description="Allow engineering to access internal resources",
    effect=PolicyEffect.ALLOW,
    resource_type="knowledge",
    actions=["read"],
    conditions=ConditionGroup(
        operator=LogicalOperator.AND,
        conditions=[
            Condition("user.department", ConditionOperator.EQUALS, "engineering"),
            Condition("resource.classification", ConditionOperator.EQUALS, "internal")
        ]
    ),
    priority=100,
    enabled=True
)

# Store in database
loader = PolicyLoader()
loader.create_policy(policy)
```

#### Loading Policies on Startup

```python
from access_control import load_policies_on_startup

# In application startup code
count = load_policies_on_startup()
print(f"Loaded {count} ABAC policies")
```

#### Updating a Policy

```python
# Get existing policy
policy = loader.get_policy("eng-internal-access")

# Modify
policy.priority = 150
policy.description = "Updated description"

# Save changes (automatically updates ABAC engine)
loader.update_policy(policy)
```

#### Listing Policies

```python
# List all enabled policies for knowledge resources
policies = loader.list_policies(
    resource_type="knowledge",
    enabled_only=True
)

for policy in policies:
    print(f"{policy.name}: {policy.effect} (priority: {policy.priority})")
```

#### Managing Policy State

```python
# Disable a policy temporarily
loader.disable_policy("eng-internal-access")

# Re-enable later
loader.enable_policy("eng-internal-access")

# Delete permanently
loader.delete_policy("eng-internal-access")
```

#### Reloading Policies

```python
# Reload all policies from database (useful after external updates)
count = loader.reload_policies()
print(f"Reloaded {count} policies")
```

### Serialization Format

Policies are serialized to JSONB for database storage:

**Simple Condition**:
```json
{
  "type": "condition",
  "attribute": "user.department",
  "operator": "==",
  "value": "engineering"
}
```

**Nested Conditions**:
```json
{
  "operator": "OR",
  "conditions": [
    {
      "type": "group",
      "operator": "AND",
      "conditions": [
        {"type": "condition", "attribute": "user.department", "operator": "==", "value": "engineering"},
        {"type": "condition", "attribute": "user.clearance_level", "operator": ">=", "value": 3}
      ]
    },
    {"type": "condition", "attribute": "user.role", "operator": "==", "value": "admin"}
  ]
}
```

### API Reference

#### PolicyLoader Class

```python
class PolicyLoader:
    """ABAC policy loader and persistence manager."""
    
    def create_policy(self, policy: ABACPolicy) -> ABACPolicy
    def get_policy(self, policy_id: str) -> Optional[ABACPolicy]
    def list_policies(
        self,
        resource_type: Optional[str] = None,
        enabled_only: bool = False,
        effect: Optional[PolicyEffect] = None
    ) -> List[ABACPolicy]
    def update_policy(self, policy: ABACPolicy) -> ABACPolicy
    def delete_policy(self, policy_id: str) -> bool
    def load_policies_into_engine(self, clear_existing: bool = True) -> int
    def reload_policies(self) -> int
    def enable_policy(self, policy_id: str) -> bool
    def disable_policy(self, policy_id: str) -> bool
```

#### Global Functions

```python
def get_policy_loader() -> PolicyLoader
    """Get singleton PolicyLoader instance."""

def load_policies_on_startup() -> int
    """Load policies from database on application startup."""
```

### Error Handling

```python
from access_control import PolicySerializationError, PolicyNotFoundError

try:
    loader.create_policy(policy)
except IntegrityError:
    print("Policy ID already exists")
except PolicySerializationError as e:
    print(f"Failed to serialize policy: {e}")

try:
    loader.update_policy(policy)
except PolicyNotFoundError:
    print("Policy not found")
```

### Testing

- Comprehensive unit tests in `test_policy_loader.py`
- Integration tests in `test_policy_loader_integration.py`
- All tests passing ✅
- Tests cover:
  - Serialization/deserialization
  - Nested conditions
  - All operators
  - Roundtrip conversion
  - Policy evaluation

### Documentation

See `POLICY_LOADER_IMPLEMENTATION_SUMMARY.md` for:
- Detailed implementation notes
- Database schema
- Performance considerations
- Security considerations
- Future enhancements

### Next Steps

- ~~**Task 2.2.4**: Implement RBAC permission checking middleware~~ ✅ **Completed**
- ~~**Task 2.2.5**: Create ABAC attribute evaluation engine~~ ✅ **Completed**
- ~~**Task 2.2.6**: Implement permission policy loader~~ ✅ **Completed**
- **Task 2.2.7**: Add user registration with role assignment

