"""User model with secure password hashing for Access Control System.

This module provides the User model with password hashing and verification
using bcrypt for secure authentication.

References:
- Requirements 14: User-Based Access Control
- Design Section 3.1: PostgreSQL Schema (users table)
- Design Section 8: Access Control System
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import bcrypt
from sqlalchemy.orm import Session

from database.models import User as DBUser

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    """Hash a plain text password using bcrypt.

    Args:
        password: Plain text password to hash

    Returns:
        Hashed password string

    Example:
        >>> hashed = hash_password("my_secure_password")
        >>> len(hashed) > 0
        True
    """
    # Convert password to bytes
    password_bytes = password.encode("utf-8")
    # Generate salt and hash password
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    # Return as string
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain text password against a hashed password.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Hashed password to compare against

    Returns:
        True if password matches, False otherwise

    Example:
        >>> hashed = hash_password("my_password")
        >>> verify_password("my_password", hashed)
        True
        >>> verify_password("wrong_password", hashed)
        False
    """
    # Convert to bytes
    password_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    # Verify password
    return bcrypt.checkpw(password_bytes, hashed_bytes)


class UserModel:
    """User model with password hashing and verification.

    This class provides a high-level interface for user management with
    secure password handling. It wraps the SQLAlchemy User model and adds
    password hashing functionality.

    Attributes:
        user_id: Unique user identifier (UUID)
        username: Unique username
        email: Unique email address
        role: User role for RBAC (admin, manager, user, viewer)
        attributes: JSONB attributes for ABAC
        created_at: Timestamp when user was created
        updated_at: Timestamp when user was last updated
    """

    def __init__(self, db_user: DBUser):
        """Initialize UserModel from database User object.

        Args:
            db_user: SQLAlchemy User model instance
        """
        self._db_user = db_user

    @property
    def user_id(self) -> uuid.UUID:
        """Get user ID."""
        return self._db_user.user_id

    @property
    def username(self) -> str:
        """Get username."""
        return self._db_user.username

    @property
    def email(self) -> str:
        """Get email."""
        return self._db_user.email

    @property
    def role(self) -> str:
        """Get user role."""
        return self._db_user.role

    @property
    def attributes(self) -> Optional[Dict[str, Any]]:
        """Get user attributes for ABAC."""
        return self._db_user.attributes

    @property
    def created_at(self) -> datetime:
        """Get creation timestamp."""
        return self._db_user.created_at

    @property
    def updated_at(self) -> datetime:
        """Get last update timestamp."""
        return self._db_user.updated_at

    def verify_password(self, password: str) -> bool:
        """Verify password against stored hash.

        Args:
            password: Plain text password to verify

        Returns:
            True if password matches, False otherwise
        """
        return verify_password(password, self._db_user.password_hash)

    def set_password(self, password: str) -> None:
        """Set new password (hashes automatically).

        Args:
            password: Plain text password to set
        """
        self._db_user.password_hash = hash_password(password)
        logger.info(
            "Password updated for user",
            extra={"user_id": str(self.user_id), "username": self.username},
        )

    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """Convert user to dictionary representation.

        Args:
            include_sensitive: If True, include sensitive fields (password_hash)

        Returns:
            Dictionary representation of user
        """
        data = {
            "user_id": str(self.user_id),
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "attributes": self.attributes,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

        if include_sensitive:
            data["password_hash"] = self._db_user.password_hash

        return data

    @classmethod
    def create(
        cls,
        session: Session,
        username: str,
        email: str,
        password: str,
        role: str = "user",
        attributes: Optional[Dict[str, Any]] = None,
    ) -> "UserModel":
        """Create a new user with hashed password.

        Args:
            session: SQLAlchemy database session
            username: Unique username
            email: Unique email address
            password: Plain text password (will be hashed)
            role: User role (default: "user")
            attributes: Optional ABAC attributes

        Returns:
            UserModel instance

        Raises:
            ValueError: If username or email already exists
        """
        # Check if username already exists
        existing_user = (
            session.query(DBUser)
            .filter((DBUser.username == username) | (DBUser.email == email))
            .first()
        )

        if existing_user:
            if existing_user.username == username:
                raise ValueError(f"Username '{username}' already exists")
            else:
                raise ValueError(f"Email '{email}' already exists")

        # Create new user with hashed password
        db_user = DBUser(
            username=username,
            email=email,
            password_hash=hash_password(password),
            role=role,
            attributes=attributes,
        )

        session.add(db_user)
        session.flush()  # Flush to get the user_id

        logger.info(
            "User created",
            extra={
                "user_id": str(db_user.user_id),
                "username": username,
                "role": role,
            },
        )

        return cls(db_user)

    @classmethod
    def get_by_id(cls, session: Session, user_id: uuid.UUID) -> Optional["UserModel"]:
        """Get user by ID.

        Args:
            session: SQLAlchemy database session
            user_id: User ID to look up

        Returns:
            UserModel instance if found, None otherwise
        """
        db_user = session.query(DBUser).filter(DBUser.user_id == user_id).first()
        return cls(db_user) if db_user else None

    @classmethod
    def get_by_username(cls, session: Session, username: str) -> Optional["UserModel"]:
        """Get user by username.

        Args:
            session: SQLAlchemy database session
            username: Username to look up

        Returns:
            UserModel instance if found, None otherwise
        """
        db_user = session.query(DBUser).filter(DBUser.username == username).first()
        return cls(db_user) if db_user else None

    @classmethod
    def get_by_email(cls, session: Session, email: str) -> Optional["UserModel"]:
        """Get user by email.

        Args:
            session: SQLAlchemy database session
            email: Email to look up

        Returns:
            UserModel instance if found, None otherwise
        """
        db_user = session.query(DBUser).filter(DBUser.email == email).first()
        return cls(db_user) if db_user else None

    @classmethod
    def authenticate(cls, session: Session, username: str, password: str) -> Optional["UserModel"]:
        """Authenticate user with username and password.

        Args:
            session: SQLAlchemy database session
            username: Username to authenticate
            password: Plain text password to verify

        Returns:
            UserModel instance if authentication successful, None otherwise
        """
        user = cls.get_by_username(session, username)

        if user and user.verify_password(password):
            logger.info(
                "User authenticated successfully",
                extra={"user_id": str(user.user_id), "username": username},
            )
            return user

        logger.warning(
            "Authentication failed", extra={"username": username, "reason": "invalid_credentials"}
        )
        return None

    def __repr__(self) -> str:
        """String representation of UserModel."""
        return (
            f"<UserModel(user_id={self.user_id}, username={self.username}, " f"role={self.role})>"
        )
