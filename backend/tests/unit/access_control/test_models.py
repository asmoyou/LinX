"""Unit tests for User model with password hashing.

Tests password hashing, verification, and user management functionality.

References:
- Requirements 14: User-Based Access Control
- Design Section 3.1: PostgreSQL Schema (users table)
"""

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from access_control.models import (
    UserModel,
    hash_password,
    verify_password,
)
from database.models import Base
from database.models import User as DBUser


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    # Use SQLite in-memory database for tests
    # Note: SQLite doesn't support PostgreSQL-specific JSONB/ARRAY types,
    # so adapt those columns to JSON for unit tests.
    from sqlalchemy import JSON, ARRAY
    from sqlalchemy.dialects.postgresql import JSONB

    engine = create_engine("sqlite:///:memory:")

    # Replace PostgreSQL-specific types with JSON for SQLite compatibility.
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
            elif isinstance(column.type, ARRAY):
                column.type = JSON()

    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()
    engine.dispose()


class TestPasswordHashing:
    """Test password hashing and verification functions."""

    def test_hash_password_returns_string(self):
        """Test that hash_password returns a string."""
        password = "test_password_123"
        hashed = hash_password(password)

        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_hash_password_different_for_same_input(self):
        """Test that hashing the same password twice produces different hashes (salt)."""
        password = "test_password_123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # Hashes should be different due to random salt
        assert hash1 != hash2

    def test_verify_password_correct_password(self):
        """Test that verify_password returns True for correct password."""
        password = "correct_password"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect_password(self):
        """Test that verify_password returns False for incorrect password."""
        password = "correct_password"
        wrong_password = "wrong_password"
        hashed = hash_password(password)

        assert verify_password(wrong_password, hashed) is False

    def test_verify_password_empty_password(self):
        """Test password verification with empty password."""
        password = ""
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True
        assert verify_password("not_empty", hashed) is False

    def test_verify_password_special_characters(self):
        """Test password hashing with special characters."""
        password = "p@ssw0rd!#$%^&*()"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_unicode_characters(self):
        """Test password hashing with unicode characters."""
        password = "密码测试🔒"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True


class TestUserModelCreation:
    """Test UserModel creation and basic properties."""

    def test_create_user_success(self, db_session: Session):
        """Test creating a new user successfully."""
        user = UserModel.create(
            session=db_session,
            username="testuser",
            email="test@example.com",
            password="secure_password",
            role="user",
        )

        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.role == "user"
        assert isinstance(user.user_id, uuid.UUID)
        assert isinstance(user.created_at, datetime)
        assert isinstance(user.updated_at, datetime)

    def test_create_user_with_attributes(self, db_session: Session):
        """Test creating user with ABAC attributes."""
        attributes = {
            "department": "engineering",
            "clearance_level": "high",
            "location": "headquarters",
        }

        user = UserModel.create(
            session=db_session,
            username="testuser",
            email="test@example.com",
            password="password",
            role="user",
            attributes=attributes,
        )

        assert user.attributes == attributes

    def test_create_user_duplicate_username(self, db_session: Session):
        """Test that creating user with duplicate username raises error."""
        UserModel.create(
            session=db_session,
            username="duplicate",
            email="first@example.com",
            password="password",
        )

        with pytest.raises(ValueError, match="Username 'duplicate' already exists"):
            UserModel.create(
                session=db_session,
                username="duplicate",
                email="second@example.com",
                password="password",
            )

    def test_create_user_duplicate_email(self, db_session: Session):
        """Test that creating user with duplicate email raises error."""
        UserModel.create(
            session=db_session,
            username="user1",
            email="duplicate@example.com",
            password="password",
        )

        with pytest.raises(ValueError, match="Email 'duplicate@example.com' already exists"):
            UserModel.create(
                session=db_session,
                username="user2",
                email="duplicate@example.com",
                password="password",
            )

    def test_create_user_default_role(self, db_session: Session):
        """Test that default role is 'user'."""
        user = UserModel.create(
            session=db_session,
            username="testuser",
            email="test@example.com",
            password="password",
        )

        assert user.role == "user"

    def test_create_user_custom_role(self, db_session: Session):
        """Test creating user with custom role."""
        user = UserModel.create(
            session=db_session,
            username="admin",
            email="admin@example.com",
            password="password",
            role="admin",
        )

        assert user.role == "admin"


class TestUserModelPasswordVerification:
    """Test password verification functionality."""

    def test_verify_password_correct(self, db_session: Session):
        """Test verifying correct password."""
        user = UserModel.create(
            session=db_session,
            username="testuser",
            email="test@example.com",
            password="correct_password",
        )

        assert user.verify_password("correct_password") is True

    def test_verify_password_incorrect(self, db_session: Session):
        """Test verifying incorrect password."""
        user = UserModel.create(
            session=db_session,
            username="testuser",
            email="test@example.com",
            password="correct_password",
        )

        assert user.verify_password("wrong_password") is False

    def test_set_password(self, db_session: Session):
        """Test changing user password."""
        user = UserModel.create(
            session=db_session,
            username="testuser",
            email="test@example.com",
            password="old_password",
        )

        # Verify old password works
        assert user.verify_password("old_password") is True

        # Change password
        user.set_password("new_password")
        db_session.commit()

        # Verify new password works and old doesn't
        assert user.verify_password("new_password") is True
        assert user.verify_password("old_password") is False


class TestUserModelRetrieval:
    """Test user retrieval methods."""

    def test_get_by_id_exists(self, db_session: Session):
        """Test retrieving user by ID when user exists."""
        created_user = UserModel.create(
            session=db_session,
            username="testuser",
            email="test@example.com",
            password="password",
        )
        db_session.commit()

        retrieved_user = UserModel.get_by_id(db_session, created_user.user_id)

        assert retrieved_user is not None
        assert retrieved_user.user_id == created_user.user_id
        assert retrieved_user.username == "testuser"

    def test_get_by_id_not_exists(self, db_session: Session):
        """Test retrieving user by ID when user doesn't exist."""
        non_existent_id = uuid.uuid4()
        user = UserModel.get_by_id(db_session, non_existent_id)

        assert user is None

    def test_get_by_username_exists(self, db_session: Session):
        """Test retrieving user by username when user exists."""
        UserModel.create(
            session=db_session,
            username="testuser",
            email="test@example.com",
            password="password",
        )
        db_session.commit()

        user = UserModel.get_by_username(db_session, "testuser")

        assert user is not None
        assert user.username == "testuser"

    def test_get_by_username_not_exists(self, db_session: Session):
        """Test retrieving user by username when user doesn't exist."""
        user = UserModel.get_by_username(db_session, "nonexistent")

        assert user is None

    def test_get_by_email_exists(self, db_session: Session):
        """Test retrieving user by email when user exists."""
        UserModel.create(
            session=db_session,
            username="testuser",
            email="test@example.com",
            password="password",
        )
        db_session.commit()

        user = UserModel.get_by_email(db_session, "test@example.com")

        assert user is not None
        assert user.email == "test@example.com"

    def test_get_by_email_not_exists(self, db_session: Session):
        """Test retrieving user by email when user doesn't exist."""
        user = UserModel.get_by_email(db_session, "nonexistent@example.com")

        assert user is None


class TestUserModelAuthentication:
    """Test user authentication functionality."""

    def test_authenticate_success(self, db_session: Session):
        """Test successful authentication."""
        UserModel.create(
            session=db_session,
            username="testuser",
            email="test@example.com",
            password="correct_password",
        )
        db_session.commit()

        user = UserModel.authenticate(db_session, "testuser", "correct_password")

        assert user is not None
        assert user.username == "testuser"

    def test_authenticate_wrong_password(self, db_session: Session):
        """Test authentication with wrong password."""
        UserModel.create(
            session=db_session,
            username="testuser",
            email="test@example.com",
            password="correct_password",
        )
        db_session.commit()

        user = UserModel.authenticate(db_session, "testuser", "wrong_password")

        assert user is None

    def test_authenticate_nonexistent_user(self, db_session: Session):
        """Test authentication with nonexistent username."""
        user = UserModel.authenticate(db_session, "nonexistent", "password")

        assert user is None


class TestUserModelSerialization:
    """Test user serialization methods."""

    def test_to_dict_without_sensitive(self, db_session: Session):
        """Test converting user to dict without sensitive fields."""
        user = UserModel.create(
            session=db_session,
            username="testuser",
            email="test@example.com",
            password="password",
            role="admin",
            attributes={"department": "engineering"},
        )

        user_dict = user.to_dict(include_sensitive=False)

        assert user_dict["username"] == "testuser"
        assert user_dict["email"] == "test@example.com"
        assert user_dict["role"] == "admin"
        assert user_dict["attributes"] == {"department": "engineering"}
        assert "password_hash" not in user_dict
        assert "user_id" in user_dict
        assert "created_at" in user_dict
        assert "updated_at" in user_dict

    def test_to_dict_with_sensitive(self, db_session: Session):
        """Test converting user to dict with sensitive fields."""
        user = UserModel.create(
            session=db_session,
            username="testuser",
            email="test@example.com",
            password="password",
        )

        user_dict = user.to_dict(include_sensitive=True)

        assert "password_hash" in user_dict
        assert len(user_dict["password_hash"]) > 0

    def test_repr(self, db_session: Session):
        """Test string representation of UserModel."""
        user = UserModel.create(
            session=db_session,
            username="testuser",
            email="test@example.com",
            password="password",
            role="admin",
        )

        repr_str = repr(user)

        assert "UserModel" in repr_str
        assert "testuser" in repr_str
        assert "admin" in repr_str
        assert str(user.user_id) in repr_str


class TestUserModelEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_create_user_empty_attributes(self, db_session: Session):
        """Test creating user with empty attributes dict."""
        user = UserModel.create(
            session=db_session,
            username="testuser",
            email="test@example.com",
            password="password",
            attributes={},
        )

        assert user.attributes == {}

    def test_create_user_none_attributes(self, db_session: Session):
        """Test creating user with None attributes."""
        user = UserModel.create(
            session=db_session,
            username="testuser",
            email="test@example.com",
            password="password",
            attributes=None,
        )

        assert user.attributes is None

    def test_username_case_sensitive(self, db_session: Session):
        """Test that usernames are case-sensitive."""
        UserModel.create(
            session=db_session,
            username="TestUser",
            email="test1@example.com",
            password="password",
        )

        # Should be able to create user with different case
        user2 = UserModel.create(
            session=db_session,
            username="testuser",
            email="test2@example.com",
            password="password",
        )

        assert user2.username == "testuser"
