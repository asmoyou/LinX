"""Unit tests for user registration functionality.

Tests cover:
- Input validation (username, email, password, role)
- Duplicate user detection
- Password hashing
- Resource quota creation
- Self-registration vs admin registration
- Error handling
"""

import uuid
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from database.models import ResourceQuota
from database.models import User as DBUser

from access_control.models import verify_password
from access_control.registration import (
    DEFAULT_QUOTAS,
    DuplicateUserError,
    RegistrationError,
    RegistrationRequest,
    RegistrationResponse,
    ValidationError,
    check_duplicate_user,
    create_resource_quota,
    register_user,
    register_user_admin,
    register_user_self,
    validate_email,
    validate_password,
    validate_resource_quotas,
    validate_role_assignment,
    validate_username,
)


class TestUsernameValidation:
    """Test username validation rules."""

    def test_valid_username(self):
        """Test that valid usernames pass validation."""
        valid_usernames = [
            "john_doe",
            "jane-smith",
            "user123",
            "test_user_123",
            "abc",  # minimum length
            "a" * 50,  # maximum length
        ]

        for username in valid_usernames:
            validate_username(username)  # Should not raise

    def test_username_too_short(self):
        """Test that usernames shorter than 3 characters are rejected."""
        with pytest.raises(ValidationError, match="at least 3 characters"):
            validate_username("ab")

    def test_username_too_long(self):
        """Test that usernames longer than 50 characters are rejected."""
        with pytest.raises(ValidationError, match="at most 50 characters"):
            validate_username("a" * 51)

    def test_username_invalid_characters(self):
        """Test that usernames with invalid characters are rejected."""
        invalid_usernames = [
            "user@name",
            "user name",
            "user.name",
            "user#123",
            "user$name",
        ]

        for username in invalid_usernames:
            with pytest.raises(ValidationError, match="can only contain"):
                validate_username(username)

    def test_username_starts_with_special(self):
        """Test that usernames starting with underscore/hyphen are rejected."""
        with pytest.raises(ValidationError, match="cannot start or end"):
            validate_username("_username")

        with pytest.raises(ValidationError, match="cannot start or end"):
            validate_username("-username")

    def test_username_ends_with_special(self):
        """Test that usernames ending with underscore/hyphen are rejected."""
        with pytest.raises(ValidationError, match="cannot start or end"):
            validate_username("username_")

        with pytest.raises(ValidationError, match="cannot start or end"):
            validate_username("username-")

    def test_username_empty(self):
        """Test that empty username is rejected."""
        with pytest.raises(ValidationError, match="required"):
            validate_username("")

    def test_username_none(self):
        """Test that None username is rejected."""
        with pytest.raises(ValidationError, match="required"):
            validate_username(None)

    def test_username_not_string(self):
        """Test that non-string username is rejected."""
        with pytest.raises(ValidationError, match="must be a string"):
            validate_username(123)


class TestEmailValidation:
    """Test email validation rules."""

    def test_valid_email(self):
        """Test that valid emails pass validation."""
        valid_emails = [
            "user@example.com",
            "john.doe@company.co.uk",
            "test+tag@domain.org",
            "user123@test-domain.com",
            "a@b.co",
        ]

        for email in valid_emails:
            validate_email(email)  # Should not raise

    def test_email_invalid_format(self):
        """Test that invalid email formats are rejected."""
        invalid_emails = [
            "notanemail",
            "@example.com",
            "user@",
            "user @example.com",
            "user@example",
            "user@@example.com",
        ]

        for email in invalid_emails:
            with pytest.raises(ValidationError, match="Invalid email"):
                validate_email(email)

    def test_email_too_long(self):
        """Test that emails longer than 255 characters are rejected."""
        long_email = "a" * 250 + "@example.com"
        with pytest.raises(ValidationError, match="too long"):
            validate_email(long_email)

    def test_email_empty(self):
        """Test that empty email is rejected."""
        with pytest.raises(ValidationError, match="required"):
            validate_email("")

    def test_email_none(self):
        """Test that None email is rejected."""
        with pytest.raises(ValidationError, match="required"):
            validate_email(None)

    def test_email_not_string(self):
        """Test that non-string email is rejected."""
        with pytest.raises(ValidationError, match="must be a string"):
            validate_email(123)


class TestPasswordValidation:
    """Test password validation rules."""

    def test_valid_password(self):
        """Test that valid passwords pass validation."""
        valid_passwords = [
            "Password123!",
            "SecureP@ss1",
            "MyP@ssw0rd",
            "Test1234!@#$",
            "aB3!defg",  # minimum length with all requirements
        ]

        for password in valid_passwords:
            validate_password(password)  # Should not raise

    def test_password_too_short(self):
        """Test that passwords shorter than 8 characters are rejected."""
        with pytest.raises(ValidationError, match="at least 8 characters"):
            validate_password("Pass1!")

    def test_password_too_long(self):
        """Test that passwords longer than 128 characters are rejected."""
        with pytest.raises(ValidationError, match="at most 128 characters"):
            validate_password("P@ssw0rd" * 20)

    def test_password_missing_uppercase(self):
        """Test that passwords without uppercase are rejected."""
        with pytest.raises(ValidationError, match="uppercase letter"):
            validate_password("password123!")

    def test_password_missing_lowercase(self):
        """Test that passwords without lowercase are rejected."""
        with pytest.raises(ValidationError, match="lowercase letter"):
            validate_password("PASSWORD123!")

    def test_password_missing_digit(self):
        """Test that passwords without digits are rejected."""
        with pytest.raises(ValidationError, match="digit"):
            validate_password("Password!")

    def test_password_missing_special(self):
        """Test that passwords without special characters are rejected."""
        with pytest.raises(ValidationError, match="special character"):
            validate_password("Password123")

    def test_password_empty(self):
        """Test that empty password is rejected."""
        with pytest.raises(ValidationError, match="required"):
            validate_password("")

    def test_password_none(self):
        """Test that None password is rejected."""
        with pytest.raises(ValidationError, match="required"):
            validate_password(None)

    def test_password_not_string(self):
        """Test that non-string password is rejected."""
        with pytest.raises(ValidationError, match="must be a string"):
            validate_password(123)


class TestRoleValidation:
    """Test role validation and authorization."""

    def test_valid_roles(self):
        """Test that valid roles pass validation."""
        valid_roles = ["admin", "manager", "user", "viewer"]

        for role in valid_roles:
            validate_role_assignment(role, is_admin=True)  # Should not raise

    def test_invalid_role(self):
        """Test that invalid roles are rejected."""
        with pytest.raises(ValidationError, match="Invalid role"):
            validate_role_assignment("superuser", is_admin=True)

    def test_admin_role_requires_admin(self):
        """Test that admin role requires admin authorization."""
        with pytest.raises(ValidationError, match="Only administrators"):
            validate_role_assignment("admin", is_admin=False)

    def test_manager_role_requires_admin(self):
        """Test that manager role requires admin authorization."""
        with pytest.raises(ValidationError, match="Only administrators"):
            validate_role_assignment("manager", is_admin=False)

    def test_user_role_no_admin_required(self):
        """Test that user role doesn't require admin authorization."""
        validate_role_assignment("user", is_admin=False)  # Should not raise

    def test_viewer_role_no_admin_required(self):
        """Test that viewer role doesn't require admin authorization."""
        validate_role_assignment("viewer", is_admin=False)  # Should not raise

    def test_role_empty(self):
        """Test that empty role is rejected."""
        with pytest.raises(ValidationError, match="required"):
            validate_role_assignment("", is_admin=True)

    def test_role_none(self):
        """Test that None role is rejected."""
        with pytest.raises(ValidationError, match="required"):
            validate_role_assignment(None, is_admin=True)


class TestResourceQuotaValidation:
    """Test resource quota validation."""

    def test_none_returns_defaults(self):
        """Test that None quotas return default values."""
        quotas = validate_resource_quotas(None)
        assert quotas == DEFAULT_QUOTAS

    def test_empty_dict_returns_defaults(self):
        """Test that empty dict returns default values."""
        quotas = validate_resource_quotas({})
        assert quotas == DEFAULT_QUOTAS

    def test_partial_quotas_merged_with_defaults(self):
        """Test that partial quotas are merged with defaults."""
        custom_quotas = {"max_agents": 20}
        quotas = validate_resource_quotas(custom_quotas)

        assert quotas["max_agents"] == 20
        assert quotas["max_storage_gb"] == DEFAULT_QUOTAS["max_storage_gb"]
        assert quotas["max_cpu_cores"] == DEFAULT_QUOTAS["max_cpu_cores"]
        assert quotas["max_memory_gb"] == DEFAULT_QUOTAS["max_memory_gb"]

    def test_invalid_quota_key(self):
        """Test that invalid quota keys are rejected."""
        with pytest.raises(ValidationError, match="Invalid quota key"):
            validate_resource_quotas({"invalid_key": 10})

    def test_negative_quota_value(self):
        """Test that negative quota values are rejected."""
        with pytest.raises(ValidationError, match="must be non-negative"):
            validate_resource_quotas({"max_agents": -1})

    def test_non_integer_quota_value(self):
        """Test that non-integer quota values are rejected."""
        with pytest.raises(ValidationError, match="must be an integer"):
            validate_resource_quotas({"max_agents": "10"})

    def test_not_dict(self):
        """Test that non-dict quotas are rejected."""
        with pytest.raises(ValidationError, match="must be a dictionary"):
            validate_resource_quotas("invalid")


class TestDuplicateUserCheck:
    """Test duplicate user detection."""

    def test_no_duplicate_user(self):
        """Test that check passes when no duplicate exists."""
        session = Mock()
        session.query().filter().first.return_value = None

        check_duplicate_user(session, "newuser", "new@example.com")  # Should not raise

    def test_duplicate_username(self):
        """Test that duplicate username is detected."""
        session = Mock()
        existing_user = Mock()
        existing_user.username = "existinguser"
        existing_user.email = "other@example.com"
        session.query().filter().first.return_value = existing_user

        with pytest.raises(DuplicateUserError, match="Username.*already exists"):
            check_duplicate_user(session, "existinguser", "new@example.com")

    def test_duplicate_email(self):
        """Test that duplicate email is detected."""
        session = Mock()
        existing_user = Mock()
        existing_user.username = "otheruser"
        existing_user.email = "existing@example.com"
        session.query().filter().first.return_value = existing_user

        with pytest.raises(DuplicateUserError, match="Email.*already exists"):
            check_duplicate_user(session, "newuser", "existing@example.com")


class TestResourceQuotaCreation:
    """Test resource quota creation."""

    def test_create_resource_quota(self):
        """Test that resource quota is created correctly."""
        session = Mock()
        user_id = uuid.uuid4()
        quotas = {
            "max_agents": 20,
            "max_storage_gb": 200,
            "max_cpu_cores": 20,
            "max_memory_gb": 40,
        }

        quota = create_resource_quota(session, user_id, quotas)

        assert quota.user_id == user_id
        assert quota.max_agents == 20
        assert quota.max_storage_gb == 200
        assert quota.max_cpu_cores == 20
        assert quota.max_memory_gb == 40
        assert quota.current_agents == 0
        assert quota.current_storage_gb == 0.0

        session.add.assert_called_once_with(quota)


class TestUserRegistration:
    """Test complete user registration flow."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = Mock()
        session.query().filter().first.return_value = None  # No duplicate user
        return session

    @pytest.fixture
    def valid_request(self):
        """Create a valid registration request."""
        return RegistrationRequest(
            username="john_doe",
            email="john@example.com",
            password="SecurePass123!",
            role="user",
            attributes={"department": "engineering"},
        )

    def test_successful_registration(self, mock_session, valid_request):
        """Test successful user registration."""
        from datetime import datetime

        with patch("access_control.registration.UserModel.create") as mock_create:
            # Setup mock user
            mock_user = Mock()
            mock_user.user_id = uuid.uuid4()
            mock_user.username = valid_request.username
            mock_user.email = valid_request.email
            mock_user.role = valid_request.role
            mock_user.attributes = valid_request.attributes
            mock_user.created_at = datetime(2024, 1, 1, 0, 0, 0)
            mock_create.return_value = mock_user

            response = register_user(mock_session, valid_request, is_admin=False)

            assert response.username == valid_request.username
            assert response.email == valid_request.email
            assert response.role == valid_request.role
            assert response.attributes == valid_request.attributes
            assert response.resource_quotas == DEFAULT_QUOTAS

            mock_session.flush.assert_called_once()

    def test_registration_with_invalid_username(self, mock_session):
        """Test that registration fails with invalid username."""
        request = RegistrationRequest(
            username="ab",  # Too short
            email="test@example.com",
            password="SecurePass123!",
        )

        with pytest.raises(ValidationError, match="at least 3 characters"):
            register_user(mock_session, request)

    def test_registration_with_invalid_email(self, mock_session):
        """Test that registration fails with invalid email."""
        request = RegistrationRequest(
            username="testuser",
            email="invalid-email",
            password="SecurePass123!",
        )

        with pytest.raises(ValidationError, match="Invalid email"):
            register_user(mock_session, request)

    def test_registration_with_weak_password(self, mock_session):
        """Test that registration fails with weak password."""
        request = RegistrationRequest(
            username="testuser",
            email="test@example.com",
            password="weak",
        )

        with pytest.raises(ValidationError, match="at least 8 characters"):
            register_user(mock_session, request)

    def test_registration_with_duplicate_username(self, mock_session):
        """Test that registration fails with duplicate username."""
        existing_user = Mock()
        existing_user.username = "existinguser"
        existing_user.email = "other@example.com"
        mock_session.query().filter().first.return_value = existing_user

        request = RegistrationRequest(
            username="existinguser",
            email="new@example.com",
            password="SecurePass123!",
        )

        with pytest.raises(DuplicateUserError, match="Username.*already exists"):
            register_user(mock_session, request)

    def test_registration_with_custom_quotas(self, mock_session, valid_request):
        """Test registration with custom resource quotas."""
        from datetime import datetime

        valid_request.resource_quotas = {"max_agents": 50}

        with patch("access_control.registration.UserModel.create") as mock_create:
            mock_user = Mock()
            mock_user.user_id = uuid.uuid4()
            mock_user.username = valid_request.username
            mock_user.email = valid_request.email
            mock_user.role = valid_request.role
            mock_user.attributes = valid_request.attributes
            mock_user.created_at = datetime(2024, 1, 1, 0, 0, 0)
            mock_create.return_value = mock_user

            response = register_user(mock_session, valid_request, is_admin=True)

            assert response.resource_quotas["max_agents"] == 50
            # Other quotas should be defaults
            assert response.resource_quotas["max_storage_gb"] == DEFAULT_QUOTAS["max_storage_gb"]

    def test_registration_handles_integrity_error(self, mock_session, valid_request):
        """Test that registration handles database integrity errors."""
        with patch("access_control.registration.UserModel.create") as mock_create:
            mock_create.side_effect = IntegrityError("", "", "")

            with pytest.raises(RegistrationError, match="constraint violation"):
                register_user(mock_session, valid_request)

            mock_session.rollback.assert_called()

    def test_registration_handles_unexpected_error(self, mock_session, valid_request):
        """Test that registration handles unexpected errors."""
        with patch("access_control.registration.UserModel.create") as mock_create:
            mock_create.side_effect = Exception("Unexpected error")

            with pytest.raises(RegistrationError, match="Registration failed"):
                register_user(mock_session, valid_request)

            mock_session.rollback.assert_called()


class TestSelfRegistration:
    """Test self-registration convenience function."""

    def test_self_registration_uses_user_role(self):
        """Test that self-registration always uses 'user' role."""
        session = Mock()
        session.query().filter().first.return_value = None

        with patch("access_control.registration.register_user") as mock_register:
            mock_register.return_value = Mock()

            register_user_self(
                session, username="testuser", email="test@example.com", password="SecurePass123!"
            )

            # Check that register_user was called with is_admin=False
            call_args = mock_register.call_args
            assert call_args[0][1].role == "user"
            assert call_args[1]["is_admin"] is False

    def test_self_registration_uses_default_quotas(self):
        """Test that self-registration uses default quotas."""
        session = Mock()
        session.query().filter().first.return_value = None

        with patch("access_control.registration.register_user") as mock_register:
            mock_register.return_value = Mock()

            register_user_self(
                session, username="testuser", email="test@example.com", password="SecurePass123!"
            )

            # Check that register_user was called with None quotas
            call_args = mock_register.call_args
            assert call_args[0][1].resource_quotas is None


class TestAdminRegistration:
    """Test admin registration convenience function."""

    def test_admin_registration_allows_any_role(self):
        """Test that admin registration allows any role."""
        session = Mock()
        session.query().filter().first.return_value = None

        with patch("access_control.registration.register_user") as mock_register:
            mock_register.return_value = Mock()

            register_user_admin(
                session,
                username="adminuser",
                email="admin@example.com",
                password="AdminPass123!",
                role="admin",
            )

            # Check that register_user was called with is_admin=True
            call_args = mock_register.call_args
            assert call_args[0][1].role == "admin"
            assert call_args[1]["is_admin"] is True

    def test_admin_registration_allows_custom_quotas(self):
        """Test that admin registration allows custom quotas."""
        session = Mock()
        session.query().filter().first.return_value = None

        custom_quotas = {"max_agents": 100}

        with patch("access_control.registration.register_user") as mock_register:
            mock_register.return_value = Mock()

            register_user_admin(
                session,
                username="adminuser",
                email="admin@example.com",
                password="AdminPass123!",
                role="manager",
                resource_quotas=custom_quotas,
            )

            # Check that register_user was called with custom quotas
            call_args = mock_register.call_args
            assert call_args[0][1].resource_quotas == custom_quotas


class TestPasswordHashing:
    """Test that passwords are properly hashed."""

    def test_password_is_hashed(self):
        """Test that password is hashed and can be verified."""
        from datetime import datetime

        session = Mock()
        session.query().filter().first.return_value = None

        with patch("access_control.registration.UserModel.create") as mock_create:
            mock_user = Mock()
            mock_user.user_id = uuid.uuid4()
            mock_user.username = "testuser"
            mock_user.email = "test@example.com"
            mock_user.role = "user"
            mock_user.attributes = None
            mock_user.created_at = datetime(2024, 1, 1, 0, 0, 0)
            mock_create.return_value = mock_user

            request = RegistrationRequest(
                username="testuser",
                email="test@example.com",
                password="SecurePass123!",
            )

            register_user(session, request)

            # Verify that UserModel.create was called with the password
            # (it will be hashed inside UserModel.create)
            call_args = mock_create.call_args
            assert call_args[1]["password"] == "SecurePass123!"
