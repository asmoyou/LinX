"""Unit tests for JWT authentication module.

Tests cover token generation, validation, expiration, refresh, and blacklist functionality.

References:
- Requirements 14: User-Based Access Control
- Requirements 15: API and Integration Layer
- Design Section 8.1: Authentication
"""

import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from jose import jwt

from access_control.jwt_auth import (
    TokenData,
    TokenPair,
    JWTAuthenticationError,
    JWTTokenExpiredError,
    JWTTokenInvalidError,
    create_access_token,
    create_refresh_token,
    create_token_pair,
    decode_token,
    verify_token,
    refresh_access_token,
    blacklist_token,
    is_token_blacklisted,
    clear_blacklist,
    get_token_expiration,
    get_token_remaining_time,
    get_jwt_config,
)


@pytest.fixture
def sample_user():
    """Fixture providing sample user data."""
    return {
        "user_id": uuid.uuid4(),
        "username": "test_user",
        "role": "user",
    }


@pytest.fixture(autouse=True)
def clear_blacklist_before_test():
    """Clear token blacklist before each test."""
    clear_blacklist()
    yield
    clear_blacklist()


class TestJWTConfig:
    """Tests for JWT configuration."""
    
    def test_get_jwt_config(self):
        """Test getting JWT configuration."""
        config = get_jwt_config()
        
        assert "secret_key" in config
        assert "algorithm" in config
        assert "access_token_expire_hours" in config
        assert "refresh_token_expire_days" in config
        assert config["algorithm"] == "HS256"


class TestTokenGeneration:
    """Tests for JWT token generation."""
    
    def test_create_access_token(self, sample_user):
        """Test creating an access token."""
        token = create_access_token(
            user_id=sample_user["user_id"],
            username=sample_user["username"],
            role=sample_user["role"]
        )
        
        assert isinstance(token, str)
        assert len(token) > 0
        
        # Decode to verify contents
        config = get_jwt_config()
        payload = jwt.decode(token, config["secret_key"], algorithms=[config["algorithm"]])
        
        assert payload["user_id"] == str(sample_user["user_id"])
        assert payload["username"] == sample_user["username"]
        assert payload["role"] == sample_user["role"]
        assert payload["token_type"] == "access"
        assert "exp" in payload
        assert "iat" in payload
        assert "jti" in payload
    
    def test_create_access_token_with_custom_expiration(self, sample_user):
        """Test creating an access token with custom expiration."""
        custom_expiration = timedelta(hours=1)
        token = create_access_token(
            user_id=sample_user["user_id"],
            username=sample_user["username"],
            role=sample_user["role"],
            expires_delta=custom_expiration
        )
        
        config = get_jwt_config()
        payload = jwt.decode(token, config["secret_key"], algorithms=[config["algorithm"]])
        
        exp_time = datetime.fromtimestamp(payload["exp"])
        iat_time = datetime.fromtimestamp(payload["iat"])
        
        # Check expiration is approximately 1 hour from issued time
        time_diff = exp_time - iat_time
        assert 3590 <= time_diff.total_seconds() <= 3610  # Allow 10 second tolerance
    
    def test_create_refresh_token(self, sample_user):
        """Test creating a refresh token."""
        token = create_refresh_token(
            user_id=sample_user["user_id"],
            username=sample_user["username"],
            role=sample_user["role"]
        )
        
        assert isinstance(token, str)
        assert len(token) > 0
        
        # Decode to verify contents
        config = get_jwt_config()
        payload = jwt.decode(token, config["secret_key"], algorithms=[config["algorithm"]])
        
        assert payload["user_id"] == str(sample_user["user_id"])
        assert payload["username"] == sample_user["username"]
        assert payload["role"] == sample_user["role"]
        assert payload["token_type"] == "refresh"
        assert "exp" in payload
        assert "iat" in payload
        assert "jti" in payload
    
    def test_create_token_pair(self, sample_user):
        """Test creating both access and refresh tokens."""
        token_pair = create_token_pair(
            user_id=sample_user["user_id"],
            username=sample_user["username"],
            role=sample_user["role"]
        )
        
        assert isinstance(token_pair, TokenPair)
        assert token_pair.token_type == "bearer"
        assert len(token_pair.access_token) > 0
        assert len(token_pair.refresh_token) > 0
        assert token_pair.expires_in > 0
        
        # Verify both tokens are valid
        config = get_jwt_config()
        access_payload = jwt.decode(
            token_pair.access_token,
            config["secret_key"],
            algorithms=[config["algorithm"]]
        )
        refresh_payload = jwt.decode(
            token_pair.refresh_token,
            config["secret_key"],
            algorithms=[config["algorithm"]]
        )
        
        assert access_payload["token_type"] == "access"
        assert refresh_payload["token_type"] == "refresh"


class TestTokenDecoding:
    """Tests for JWT token decoding and validation."""
    
    def test_decode_valid_token(self, sample_user):
        """Test decoding a valid token."""
        token = create_access_token(
            user_id=sample_user["user_id"],
            username=sample_user["username"],
            role=sample_user["role"]
        )
        
        token_data = decode_token(token)
        
        assert isinstance(token_data, TokenData)
        assert token_data.user_id == str(sample_user["user_id"])
        assert token_data.username == sample_user["username"]
        assert token_data.role == sample_user["role"]
        assert token_data.token_type == "access"
        assert token_data.exp is not None
        assert token_data.iat is not None
        assert token_data.jti is not None
    
    def test_decode_expired_token(self, sample_user):
        """Test decoding an expired token."""
        # Create token that expires immediately
        token = create_access_token(
            user_id=sample_user["user_id"],
            username=sample_user["username"],
            role=sample_user["role"],
            expires_delta=timedelta(seconds=-1)  # Already expired
        )
        
        with pytest.raises(JWTTokenExpiredError) as exc_info:
            decode_token(token)
        
        assert "expired" in str(exc_info.value).lower()
    
    def test_decode_invalid_token(self):
        """Test decoding an invalid token."""
        invalid_token = "invalid.token.string"
        
        with pytest.raises(JWTTokenInvalidError):
            decode_token(invalid_token)
    
    def test_decode_token_with_wrong_secret(self, sample_user):
        """Test decoding a token with wrong secret key."""
        # Create token with different secret
        wrong_secret = "wrong-secret-key"
        payload = {
            "user_id": str(sample_user["user_id"]),
            "username": sample_user["username"],
            "role": sample_user["role"],
            "token_type": "access",
            "exp": datetime.utcnow() + timedelta(hours=1),
        }
        token = jwt.encode(payload, wrong_secret, algorithm="HS256")
        
        with pytest.raises(JWTTokenInvalidError):
            decode_token(token)
    
    def test_verify_token_correct_type(self, sample_user):
        """Test verifying token with correct type."""
        access_token = create_access_token(
            user_id=sample_user["user_id"],
            username=sample_user["username"],
            role=sample_user["role"]
        )
        
        token_data = verify_token(access_token, expected_type="access")
        assert token_data.token_type == "access"
    
    def test_verify_token_wrong_type(self, sample_user):
        """Test verifying token with wrong type."""
        access_token = create_access_token(
            user_id=sample_user["user_id"],
            username=sample_user["username"],
            role=sample_user["role"]
        )
        
        with pytest.raises(JWTTokenInvalidError) as exc_info:
            verify_token(access_token, expected_type="refresh")
        
        assert "Invalid token type" in str(exc_info.value)


class TestTokenRefresh:
    """Tests for token refresh functionality."""
    
    def test_refresh_access_token(self, sample_user):
        """Test refreshing an access token using refresh token."""
        # Create refresh token
        refresh_token = create_refresh_token(
            user_id=sample_user["user_id"],
            username=sample_user["username"],
            role=sample_user["role"]
        )
        
        # Get new access token
        new_access_token = refresh_access_token(refresh_token)
        
        assert isinstance(new_access_token, str)
        assert len(new_access_token) > 0
        
        # Verify new access token
        token_data = decode_token(new_access_token)
        assert token_data.user_id == str(sample_user["user_id"])
        assert token_data.username == sample_user["username"]
        assert token_data.role == sample_user["role"]
        assert token_data.token_type == "access"
    
    def test_refresh_with_access_token_fails(self, sample_user):
        """Test that refreshing with access token fails."""
        # Create access token (not refresh token)
        access_token = create_access_token(
            user_id=sample_user["user_id"],
            username=sample_user["username"],
            role=sample_user["role"]
        )
        
        with pytest.raises(JWTTokenInvalidError) as exc_info:
            refresh_access_token(access_token)
        
        assert "Invalid token type" in str(exc_info.value)
    
    def test_refresh_with_expired_token_fails(self, sample_user):
        """Test that refreshing with expired token fails."""
        # Create expired refresh token
        expired_refresh_token = create_refresh_token(
            user_id=sample_user["user_id"],
            username=sample_user["username"],
            role=sample_user["role"],
            expires_delta=timedelta(seconds=-1)
        )
        
        with pytest.raises(JWTTokenExpiredError):
            refresh_access_token(expired_refresh_token)


class TestTokenBlacklist:
    """Tests for token blacklist functionality."""
    
    def test_blacklist_token(self, sample_user):
        """Test adding a token to blacklist."""
        token = create_access_token(
            user_id=sample_user["user_id"],
            username=sample_user["username"],
            role=sample_user["role"]
        )
        
        # Token should be valid before blacklisting
        token_data = decode_token(token)
        assert token_data is not None
        
        # Blacklist the token
        blacklist_token(token)
        
        # Token should now be invalid
        with pytest.raises(JWTTokenInvalidError) as exc_info:
            decode_token(token)
        
        assert "revoked" in str(exc_info.value).lower()
    
    def test_is_token_blacklisted(self, sample_user):
        """Test checking if token is blacklisted."""
        token = create_access_token(
            user_id=sample_user["user_id"],
            username=sample_user["username"],
            role=sample_user["role"]
        )
        
        # Token should not be blacklisted initially
        assert not is_token_blacklisted(token)
        
        # Blacklist the token
        blacklist_token(token)
        
        # Token should now be blacklisted
        assert is_token_blacklisted(token)
    
    def test_blacklist_expired_token(self, sample_user):
        """Test blacklisting an already expired token."""
        expired_token = create_access_token(
            user_id=sample_user["user_id"],
            username=sample_user["username"],
            role=sample_user["role"],
            expires_delta=timedelta(seconds=-1)
        )
        
        # Should not raise error when blacklisting expired token
        blacklist_token(expired_token)
        
        # Token should still be invalid (due to expiration)
        with pytest.raises(JWTTokenExpiredError):
            decode_token(expired_token)
    
    def test_clear_blacklist(self, sample_user):
        """Test clearing the token blacklist."""
        token = create_access_token(
            user_id=sample_user["user_id"],
            username=sample_user["username"],
            role=sample_user["role"]
        )
        
        # Blacklist the token
        blacklist_token(token)
        assert is_token_blacklisted(token)
        
        # Clear blacklist
        clear_blacklist()
        
        # Token should no longer be blacklisted
        assert not is_token_blacklisted(token)
        
        # Token should be valid again
        token_data = decode_token(token)
        assert token_data is not None


class TestTokenUtilities:
    """Tests for token utility functions."""
    
    def test_get_token_expiration(self, sample_user):
        """Test getting token expiration time."""
        token = create_access_token(
            user_id=sample_user["user_id"],
            username=sample_user["username"],
            role=sample_user["role"]
        )
        
        expiration = get_token_expiration(token)
        
        assert isinstance(expiration, datetime)
        assert expiration > datetime.utcnow()
    
    def test_get_token_expiration_invalid_token(self):
        """Test getting expiration of invalid token."""
        invalid_token = "invalid.token.string"
        
        expiration = get_token_expiration(invalid_token)
        assert expiration is None
    
    def test_get_token_remaining_time(self, sample_user):
        """Test getting remaining time until token expiration."""
        token = create_access_token(
            user_id=sample_user["user_id"],
            username=sample_user["username"],
            role=sample_user["role"],
            expires_delta=timedelta(hours=1)
        )
        
        remaining = get_token_remaining_time(token)
        
        assert isinstance(remaining, timedelta)
        assert remaining.total_seconds() > 0
        assert remaining.total_seconds() <= 3600  # Less than or equal to 1 hour
    
    def test_get_token_remaining_time_expired(self, sample_user):
        """Test getting remaining time of expired token."""
        expired_token = create_access_token(
            user_id=sample_user["user_id"],
            username=sample_user["username"],
            role=sample_user["role"],
            expires_delta=timedelta(seconds=-1)
        )
        
        remaining = get_token_remaining_time(expired_token)
        assert remaining is None
    
    def test_get_token_remaining_time_invalid_token(self):
        """Test getting remaining time of invalid token."""
        invalid_token = "invalid.token.string"
        
        remaining = get_token_remaining_time(invalid_token)
        assert remaining is None


class TestTokenDataModel:
    """Tests for TokenData Pydantic model."""
    
    def test_token_data_creation(self):
        """Test creating TokenData instance."""
        token_data = TokenData(
            user_id="123e4567-e89b-12d3-a456-426614174000",
            username="test_user",
            role="admin",
            token_type="access"
        )
        
        assert token_data.user_id == "123e4567-e89b-12d3-a456-426614174000"
        assert token_data.username == "test_user"
        assert token_data.role == "admin"
        assert token_data.token_type == "access"
    
    def test_token_data_default_type(self):
        """Test TokenData default token type."""
        token_data = TokenData(
            user_id="123e4567-e89b-12d3-a456-426614174000",
            username="test_user",
            role="user"
        )
        
        assert token_data.token_type == "access"


class TestTokenPairModel:
    """Tests for TokenPair Pydantic model."""
    
    def test_token_pair_creation(self):
        """Test creating TokenPair instance."""
        token_pair = TokenPair(
            access_token="access.token.here",
            refresh_token="refresh.token.here",
            expires_in=86400
        )
        
        assert token_pair.access_token == "access.token.here"
        assert token_pair.refresh_token == "refresh.token.here"
        assert token_pair.token_type == "bearer"
        assert token_pair.expires_in == 86400


class TestEdgeCases:
    """Tests for edge cases and error conditions."""
    
    def test_token_with_special_characters_in_username(self):
        """Test token generation with special characters in username."""
        user_id = uuid.uuid4()
        username = "user@example.com"
        role = "user"
        
        token = create_access_token(user_id, username, role)
        token_data = decode_token(token)
        
        assert token_data.username == username
    
    def test_token_with_different_roles(self):
        """Test token generation with different roles."""
        user_id = uuid.uuid4()
        username = "test_user"
        
        roles = ["admin", "manager", "user", "viewer"]
        
        for role in roles:
            token = create_access_token(user_id, username, role)
            token_data = decode_token(token)
            assert token_data.role == role
    
    def test_multiple_tokens_for_same_user(self, sample_user):
        """Test creating multiple tokens for the same user."""
        token1 = create_access_token(
            user_id=sample_user["user_id"],
            username=sample_user["username"],
            role=sample_user["role"]
        )
        token2 = create_access_token(
            user_id=sample_user["user_id"],
            username=sample_user["username"],
            role=sample_user["role"]
        )
        
        # Tokens should be different (different jti)
        assert token1 != token2
        
        # Both should be valid
        data1 = decode_token(token1)
        data2 = decode_token(token2)
        
        assert data1.user_id == data2.user_id
        assert data1.username == data2.username
        assert data1.jti != data2.jti
