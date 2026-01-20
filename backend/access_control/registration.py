"""User registration functionality with role assignment and validation.

This module provides user registration capabilities including:
- Input validation (email format, password strength, username format)
- Password hashing using bcrypt
- Role assignment (default or admin-specified)
- Resource quota creation for new users
- Duplicate username/email checking
- Comprehensive error handling

References:
- Requirements 14: User-Based Access Control
- Design Section 8.1: Authentication
- Task 2.2.7: Add user registration with role assignment
"""

import logging
import re
import uuid
from typing import Dict, Any, Optional
from dataclasses import dataclass

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database.models import User as DBUser, ResourceQuota
from .models import UserModel, hash_password
from .rbac import Role, validate_role

logger = logging.getLogger(__name__)


# Validation constants
MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 50
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
EMAIL_PATTERN = re.compile(
    r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
)

# Default resource quotas for new users
DEFAULT_QUOTAS = {
    "max_agents": 10,
    "max_storage_gb": 100,
    "max_cpu_cores": 10,
    "max_memory_gb": 20,
}


class RegistrationError(Exception):
    """Base exception for registration errors."""
    pass


class ValidationError(RegistrationError):
    """Raised when input validation fails."""
    pass


class DuplicateUserError(RegistrationError):
    """Raised when username or email already exists."""
    pass


@dataclass
class RegistrationRequest:
    """User registration request data.
    
    Attributes:
        username: Unique username (3-50 chars, alphanumeric, underscore, hyphen)
        email: Valid email address
        password: Plain text password (8-128 chars, will be hashed)
        role: User role (default: "user")
        attributes: Optional ABAC attributes
        resource_quotas: Optional custom resource quotas (admin only)
    """
    username: str
    email: str
    password: str
    role: str = "user"
    attributes: Optional[Dict[str, Any]] = None
    resource_quotas: Optional[Dict[str, int]] = None


@dataclass
class RegistrationResponse:
    """User registration response data.
    
    Attributes:
        user_id: UUID of created user
        username: Username
        email: Email address
        role: Assigned role
        attributes: ABAC attributes
        resource_quotas: Resource quota limits
        created_at: Creation timestamp (ISO format)
    """
    user_id: str
    username: str
    email: str
    role: str
    attributes: Optional[Dict[str, Any]]
    resource_quotas: Dict[str, int]
    created_at: str


def validate_username(username: str) -> None:
    """Validate username format and length.
    
    Args:
        username: Username to validate
        
    Raises:
        ValidationError: If username is invalid
        
    Rules:
        - Length: 3-50 characters
        - Characters: alphanumeric, underscore, hyphen only
        - Cannot start or end with hyphen or underscore
    """
    if not username:
        raise ValidationError("Username is required")
    
    if not isinstance(username, str):
        raise ValidationError("Username must be a string")
    
    if len(username) < MIN_USERNAME_LENGTH:
        raise ValidationError(
            f"Username must be at least {MIN_USERNAME_LENGTH} characters long"
        )
    
    if len(username) > MAX_USERNAME_LENGTH:
        raise ValidationError(
            f"Username must be at most {MAX_USERNAME_LENGTH} characters long"
        )
    
    if not USERNAME_PATTERN.match(username):
        raise ValidationError(
            "Username can only contain letters, numbers, underscores, and hyphens"
        )
    
    if username[0] in ('_', '-') or username[-1] in ('_', '-'):
        raise ValidationError(
            "Username cannot start or end with underscore or hyphen"
        )
    
    logger.debug(f"Username validation passed: {username}")


def validate_email(email: str) -> None:
    """Validate email format.
    
    Args:
        email: Email address to validate
        
    Raises:
        ValidationError: If email is invalid
        
    Rules:
        - Must match standard email format
        - Must contain @ and domain
        - Domain must have valid TLD
    """
    if not email:
        raise ValidationError("Email is required")
    
    if not isinstance(email, str):
        raise ValidationError("Email must be a string")
    
    if len(email) > 255:
        raise ValidationError("Email address is too long (max 255 characters)")
    
    if not EMAIL_PATTERN.match(email):
        raise ValidationError("Invalid email format")
    
    logger.debug(f"Email validation passed: {email}")


def validate_password(password: str) -> None:
    """Validate password strength.
    
    Args:
        password: Plain text password to validate
        
    Raises:
        ValidationError: If password is invalid
        
    Rules:
        - Length: 8-128 characters
        - Must contain at least one uppercase letter
        - Must contain at least one lowercase letter
        - Must contain at least one digit
        - Must contain at least one special character
    """
    if not password:
        raise ValidationError("Password is required")
    
    if not isinstance(password, str):
        raise ValidationError("Password must be a string")
    
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long"
        )
    
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValidationError(
            f"Password must be at most {MAX_PASSWORD_LENGTH} characters long"
        )
    
    # Check for required character types
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password)
    
    missing_requirements = []
    if not has_upper:
        missing_requirements.append("uppercase letter")
    if not has_lower:
        missing_requirements.append("lowercase letter")
    if not has_digit:
        missing_requirements.append("digit")
    if not has_special:
        missing_requirements.append("special character (!@#$%^&*()_+-=[]{}|;:,.<>?)")
    
    if missing_requirements:
        raise ValidationError(
            f"Password must contain at least one: {', '.join(missing_requirements)}"
        )
    
    logger.debug("Password validation passed")


def validate_role_assignment(role: str, is_admin: bool = False) -> None:
    """Validate role assignment.
    
    Args:
        role: Role to assign
        is_admin: Whether the requester is an admin
        
    Raises:
        ValidationError: If role is invalid or unauthorized
        
    Rules:
        - Role must be valid (admin, manager, user, viewer)
        - Only admins can assign admin or manager roles
        - Self-registration defaults to "user" role
    """
    if not role:
        raise ValidationError("Role is required")
    
    if not isinstance(role, str):
        raise ValidationError("Role must be a string")
    
    # Validate role exists
    if not validate_role(role):
        raise ValidationError(
            f"Invalid role '{role}'. Must be one of: admin, manager, user, viewer"
        )
    
    # Check authorization for privileged roles
    if role in ("admin", "manager") and not is_admin:
        raise ValidationError(
            f"Only administrators can assign '{role}' role. "
            "Self-registration defaults to 'user' role."
        )
    
    logger.debug(f"Role validation passed: {role}")


def validate_resource_quotas(quotas: Optional[Dict[str, int]]) -> Dict[str, int]:
    """Validate and normalize resource quotas.
    
    Args:
        quotas: Custom resource quotas or None for defaults
        
    Returns:
        Validated resource quotas dictionary
        
    Raises:
        ValidationError: If quotas are invalid
    """
    if quotas is None:
        return DEFAULT_QUOTAS.copy()
    
    if not isinstance(quotas, dict):
        raise ValidationError("Resource quotas must be a dictionary")
    
    # Start with defaults and override with provided values
    validated_quotas = DEFAULT_QUOTAS.copy()
    
    valid_quota_keys = set(DEFAULT_QUOTAS.keys())
    
    for key, value in quotas.items():
        if key not in valid_quota_keys:
            raise ValidationError(
                f"Invalid quota key '{key}'. "
                f"Valid keys: {', '.join(valid_quota_keys)}"
            )
        
        if not isinstance(value, int):
            raise ValidationError(f"Quota value for '{key}' must be an integer")
        
        if value < 0:
            raise ValidationError(f"Quota value for '{key}' must be non-negative")
        
        validated_quotas[key] = value
    
    logger.debug(f"Resource quotas validated: {validated_quotas}")
    return validated_quotas


def check_duplicate_user(session: Session, username: str, email: str) -> None:
    """Check if username or email already exists.
    
    Args:
        session: SQLAlchemy database session
        username: Username to check
        email: Email to check
        
    Raises:
        DuplicateUserError: If username or email already exists
    """
    existing_user = session.query(DBUser).filter(
        (DBUser.username == username) | (DBUser.email == email)
    ).first()
    
    if existing_user:
        if existing_user.username == username:
            raise DuplicateUserError(f"Username '{username}' already exists")
        else:
            raise DuplicateUserError(f"Email '{email}' already exists")
    
    logger.debug(f"No duplicate user found for username={username}, email={email}")


def create_resource_quota(
    session: Session,
    user_id: uuid.UUID,
    quotas: Dict[str, int]
) -> ResourceQuota:
    """Create resource quota entry for new user.
    
    Args:
        session: SQLAlchemy database session
        user_id: User ID
        quotas: Resource quota limits
        
    Returns:
        Created ResourceQuota instance
    """
    quota = ResourceQuota(
        user_id=user_id,
        max_agents=quotas["max_agents"],
        max_storage_gb=quotas["max_storage_gb"],
        max_cpu_cores=quotas["max_cpu_cores"],
        max_memory_gb=quotas["max_memory_gb"],
        current_agents=0,
        current_storage_gb=0.0,
    )
    
    session.add(quota)
    
    logger.info(
        "Resource quota created",
        extra={
            "user_id": str(user_id),
            "max_agents": quotas["max_agents"],
            "max_storage_gb": quotas["max_storage_gb"],
        }
    )
    
    return quota


def register_user(
    session: Session,
    request: RegistrationRequest,
    is_admin: bool = False
) -> RegistrationResponse:
    """Register a new user with validation and resource quota creation.
    
    This is the main registration function that:
    1. Validates all input fields
    2. Checks for duplicate username/email
    3. Hashes the password
    4. Creates the user record
    5. Creates default resource quotas
    6. Returns user information (without password hash)
    
    Args:
        session: SQLAlchemy database session
        request: Registration request data
        is_admin: Whether the requester is an admin (for role assignment)
        
    Returns:
        RegistrationResponse with created user information
        
    Raises:
        ValidationError: If input validation fails
        DuplicateUserError: If username or email already exists
        RegistrationError: If registration fails for other reasons
        
    Example:
        >>> from database.connection import get_db_session
        >>> from access_control.registration import register_user, RegistrationRequest
        >>> 
        >>> request = RegistrationRequest(
        ...     username="john_doe",
        ...     email="john@example.com",
        ...     password="SecurePass123!",
        ...     role="user"
        ... )
        >>> 
        >>> with get_db_session() as session:
        ...     response = register_user(session, request)
        ...     session.commit()
        ...     print(f"User created: {response.username}")
    """
    try:
        # Validate input fields
        validate_username(request.username)
        validate_email(request.email)
        validate_password(request.password)
        validate_role_assignment(request.role, is_admin)
        
        # Validate and normalize resource quotas
        quotas = validate_resource_quotas(request.resource_quotas)
        
        # Check for duplicates
        check_duplicate_user(session, request.username, request.email)
        
        # Create user with hashed password
        user_model = UserModel.create(
            session=session,
            username=request.username,
            email=request.email,
            password=request.password,
            role=request.role,
            attributes=request.attributes,
        )
        
        # Create resource quota
        create_resource_quota(session, user_model.user_id, quotas)
        
        # Flush to ensure all database operations complete
        session.flush()
        
        logger.info(
            "User registered successfully",
            extra={
                "user_id": str(user_model.user_id),
                "username": request.username,
                "email": request.email,
                "role": request.role,
            }
        )
        
        # Return response (without password hash)
        return RegistrationResponse(
            user_id=str(user_model.user_id),
            username=user_model.username,
            email=user_model.email,
            role=user_model.role,
            attributes=user_model.attributes,
            resource_quotas=quotas,
            created_at=user_model.created_at.isoformat(),
        )
        
    except (ValidationError, DuplicateUserError):
        # Re-raise validation and duplicate errors as-is
        raise
    
    except IntegrityError as e:
        # Handle database integrity errors
        session.rollback()
        logger.error(
            "Database integrity error during registration",
            extra={"error": str(e), "username": request.username}
        )
        raise RegistrationError(
            "Registration failed due to database constraint violation"
        ) from e
    
    except Exception as e:
        # Handle unexpected errors
        session.rollback()
        logger.error(
            "Unexpected error during registration",
            extra={"error": str(e), "username": request.username},
            exc_info=True
        )
        raise RegistrationError(
            f"Registration failed: {str(e)}"
        ) from e


def register_user_self(
    session: Session,
    username: str,
    email: str,
    password: str,
    attributes: Optional[Dict[str, Any]] = None
) -> RegistrationResponse:
    """Self-registration with default "user" role.
    
    This is a convenience function for self-registration that always
    assigns the "user" role and default resource quotas.
    
    Args:
        session: SQLAlchemy database session
        username: Unique username
        email: Email address
        password: Plain text password
        attributes: Optional ABAC attributes
        
    Returns:
        RegistrationResponse with created user information
        
    Raises:
        ValidationError: If input validation fails
        DuplicateUserError: If username or email already exists
        RegistrationError: If registration fails
        
    Example:
        >>> from database.connection import get_db_session
        >>> from access_control.registration import register_user_self
        >>> 
        >>> with get_db_session() as session:
        ...     response = register_user_self(
        ...         session,
        ...         username="jane_doe",
        ...         email="jane@example.com",
        ...         password="SecurePass456!"
        ...     )
        ...     session.commit()
    """
    request = RegistrationRequest(
        username=username,
        email=email,
        password=password,
        role="user",  # Always "user" for self-registration
        attributes=attributes,
        resource_quotas=None,  # Use defaults
    )
    
    return register_user(session, request, is_admin=False)


def register_user_admin(
    session: Session,
    username: str,
    email: str,
    password: str,
    role: str,
    attributes: Optional[Dict[str, Any]] = None,
    resource_quotas: Optional[Dict[str, int]] = None
) -> RegistrationResponse:
    """Admin registration with custom role and quotas.
    
    This function allows administrators to create users with any role
    and custom resource quotas.
    
    Args:
        session: SQLAlchemy database session
        username: Unique username
        email: Email address
        password: Plain text password
        role: User role (admin, manager, user, viewer)
        attributes: Optional ABAC attributes
        resource_quotas: Optional custom resource quotas
        
    Returns:
        RegistrationResponse with created user information
        
    Raises:
        ValidationError: If input validation fails
        DuplicateUserError: If username or email already exists
        RegistrationError: If registration fails
        
    Example:
        >>> from database.connection import get_db_session
        >>> from access_control.registration import register_user_admin
        >>> 
        >>> with get_db_session() as session:
        ...     response = register_user_admin(
        ...         session,
        ...         username="admin_user",
        ...         email="admin@example.com",
        ...         password="AdminPass789!",
        ...         role="admin",
        ...         resource_quotas={"max_agents": 50, "max_storage_gb": 500}
        ...     )
        ...     session.commit()
    """
    request = RegistrationRequest(
        username=username,
        email=email,
        password=password,
        role=role,
        attributes=attributes,
        resource_quotas=resource_quotas,
    )
    
    return register_user(session, request, is_admin=True)
