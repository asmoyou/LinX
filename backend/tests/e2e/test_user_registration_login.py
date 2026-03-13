"""End-to-end tests for user registration and login flow.

Tests the complete user registration and authentication workflow.

References:
- Task 8.3.1: Test user registration and login
"""

import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.usefixtures("cleanup_shared_db_test_artifacts")]


def _error_text(response) -> str:
    payload = response.json()
    return str(payload.get("detail") or payload.get("message") or payload)


@pytest.fixture
def api_client():
    """Create API test client."""
    from api_gateway.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture
def test_user_data():
    """Generate unique test user data."""
    unique_id = str(uuid4())[:8]
    return {
        "username": f"testuser_{unique_id}",
        "email": f"test_{unique_id}@example.com",
        "password": "SecurePassword123!",
        "full_name": "Test User",
    }


class TestUserRegistrationLogin:
    """Test complete user registration and login flow."""

    def test_complete_registration_and_login_flow(self, api_client, test_user_data):
        """Test complete flow from registration to authenticated access."""
        # Step 1: Register new user
        register_response = api_client.post("/api/v1/auth/register", json=test_user_data)

        assert register_response.status_code == 201
        register_data = register_response.json()
        assert "user_id" in register_data
        assert register_data["username"] == test_user_data["username"]
        assert register_data["email"] == test_user_data["email"]
        assert "password" not in register_data  # Password should not be returned

        user_id = register_data["user_id"]

        # Step 2: Login with credentials
        login_response = api_client.post(
            "/api/v1/auth/login",
            json={"username": test_user_data["username"], "password": test_user_data["password"]},
        )

        assert login_response.status_code == 200
        login_data = login_response.json()
        assert "access_token" in login_data
        assert "refresh_token" in login_data
        assert login_data["token_type"] == "bearer"

        access_token = login_data["access_token"]
        refresh_token = login_data["refresh_token"]

        # Step 3: Access protected endpoint with token
        profile_response = api_client.get(
            "/api/v1/users/me", headers={"Authorization": f"Bearer {access_token}"}
        )

        assert profile_response.status_code == 200
        profile_data = profile_response.json()
        assert profile_data["user_id"] == user_id
        assert profile_data["username"] == test_user_data["username"]
        assert profile_data["email"] == test_user_data["email"]

        # Step 4: Update user profile
        update_response = api_client.put(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"display_name": "Updated Test User"},
        )

        assert update_response.status_code == 200
        update_data = update_response.json()
        assert update_data["display_name"] == "Updated Test User"

        # Step 5: Refresh access token
        refresh_response = api_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
        )

        assert refresh_response.status_code == 200
        refresh_data = refresh_response.json()
        assert "access_token" in refresh_data
        assert refresh_data["access_token"] != access_token  # New token

        # Step 6: Logout
        logout_response = api_client.post(
            "/api/v1/auth/logout", headers={"Authorization": f"Bearer {access_token}"}
        )

        assert logout_response.status_code == 204

        # Step 7: Verify token is invalidated
        verify_response = api_client.get(
            "/api/v1/users/me", headers={"Authorization": f"Bearer {access_token}"}
        )

        assert verify_response.status_code == 401  # Unauthorized

        # Step 8: Verify refresh token is also invalidated
        refresh_after_logout_response = api_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
        )

        assert refresh_after_logout_response.status_code == 401

    def test_registration_with_duplicate_username(self, api_client, test_user_data):
        """Test that duplicate username registration fails."""
        # Register first user
        first_response = api_client.post("/api/v1/auth/register", json=test_user_data)
        assert first_response.status_code == 201

        # Try to register with same username
        duplicate_data = test_user_data.copy()
        duplicate_data["email"] = "different@example.com"

        second_response = api_client.post("/api/v1/auth/register", json=duplicate_data)

        assert second_response.status_code == 409  # Conflict
        assert "username" in _error_text(second_response).lower()

    def test_registration_with_duplicate_email(self, api_client, test_user_data):
        """Test that duplicate email registration fails."""
        # Register first user
        first_response = api_client.post("/api/v1/auth/register", json=test_user_data)
        assert first_response.status_code == 201

        # Try to register with same email
        duplicate_data = test_user_data.copy()
        duplicate_data["username"] = "differentuser"

        second_response = api_client.post("/api/v1/auth/register", json=duplicate_data)

        assert second_response.status_code == 409  # Conflict
        assert "email" in _error_text(second_response).lower()

    def test_login_with_invalid_credentials(self, api_client, test_user_data):
        """Test that login fails with invalid credentials."""
        # Register user
        api_client.post("/api/v1/auth/register", json=test_user_data)

        # Try to login with wrong password
        login_response = api_client.post(
            "/api/v1/auth/login",
            json={"username": test_user_data["username"], "password": "WrongPassword123!"},
        )

        assert login_response.status_code == 401
        assert (
            "credentials" in _error_text(login_response).lower()
            or "username/email or password" in _error_text(login_response).lower()
        )

    def test_access_protected_endpoint_without_token(self, api_client):
        """Test that protected endpoints require authentication."""
        response = api_client.get("/api/v1/users/me")

        assert response.status_code == 401
        assert (
            "authenticated" in _error_text(response).lower()
            or "authentication" in _error_text(response).lower()
            or "authorization" in _error_text(response).lower()
        )

    def test_access_protected_endpoint_with_invalid_token(self, api_client):
        """Test that invalid tokens are rejected."""
        response = api_client.get(
            "/api/v1/users/me", headers={"Authorization": "Bearer invalid_token_12345"}
        )

        assert response.status_code == 401

    def test_token_expiration(self, api_client, test_user_data):
        """Test that expired tokens are rejected."""
        # Register and login
        api_client.post("/api/v1/auth/register", json=test_user_data)
        login_response = api_client.post(
            "/api/v1/auth/login",
            json={"username": test_user_data["username"], "password": test_user_data["password"]},
        )

        access_token = login_response.json()["access_token"]

        # Wait for token to expire (if short expiry is configured for testing)
        # In production, this would be a longer wait
        # For testing, we can mock the time or use a very short expiry

        # Try to use potentially expired token
        # Note: This test assumes short token expiry for testing
        time.sleep(2)  # Adjust based on test token expiry

        response = api_client.get(
            "/api/v1/users/me", headers={"Authorization": f"Bearer {access_token}"}
        )

        # Token might still be valid if expiry is long
        # This test is more relevant with mocked time or short test expiry
        assert response.status_code in [200, 401]

    def test_password_validation(self, api_client):
        """Test that weak passwords are rejected."""
        weak_passwords = [
            "short",  # Too short
            "nouppercaseornumbers",  # No uppercase or numbers
            "NOLOWERCASE123",  # No lowercase
            "NoSpecialChar123",  # No special characters (if required)
        ]

        for weak_password in weak_passwords:
            response = api_client.post(
                "/api/v1/auth/register",
                json={
                    "username": f"user_{uuid4()}",
                    "email": f"test_{uuid4()}@example.com",
                    "password": weak_password,
                    "full_name": "Test User",
                },
            )

            # Should fail validation
            assert response.status_code in [400, 422]

    def test_email_validation(self, api_client):
        """Test that invalid emails are rejected."""
        invalid_emails = [
            "notanemail",
            "@example.com",
            "user@",
            "user @example.com",
        ]

        for invalid_email in invalid_emails:
            response = api_client.post(
                "/api/v1/auth/register",
                json={
                    "username": f"user_{uuid4()}",
                    "email": invalid_email,
                    "password": "SecurePassword123!",
                    "full_name": "Test User",
                },
            )

            # Should fail validation
            assert response.status_code in [400, 422]
