import pytest

from src.core.security import (
    create_access_token,
    create_refresh_token,
    decode_jwt_token,
    generate_secure_token,
    get_password_hash,
    validate_password_complexity,
    verify_password,
)


def test_password_complexity_valid():
    """Verify that a compliant strong password passes validation."""
    validate_password_complexity("StrongPass123!")


@pytest.mark.parametrize(
    "invalid_password,expected_error",
    [
        ("Short1!", "Password must be at least 8 characters long."),
        ("nouppercase123!", "Password must contain at least one uppercase letter."),
        ("NOLOWERCASE123!", "Password must contain at least one lowercase letter."),
        ("NoDigitsSpecial!", "Password must contain at least one digit."),
        ("NoSpecialChar123", "Password must contain at least one special character."),
    ],
)
def test_password_complexity_invalid(invalid_password: str, expected_error: str):
    """Verify that non-compliant passwords trigger appropriate validation errors."""
    with pytest.raises(ValueError, match=expected_error):
        validate_password_complexity(invalid_password)


def test_password_hashing():
    """Verify password hashing and verification logic."""
    raw_password = "ComplexPassword99#"
    hashed = get_password_hash(raw_password)

    assert hashed != raw_password
    assert verify_password(raw_password, hashed) is True
    assert verify_password("WrongPassword1!", hashed) is False


def test_jwt_tokens():
    """Verify JWT access and refresh token creation and payload structure."""
    user_id = 42

    # Test access token
    access_token = create_access_token(subject=user_id)
    payload = decode_jwt_token(access_token)
    assert payload["sub"] == str(user_id)
    assert payload["type"] == "access"

    # Test refresh token
    refresh_token, _ = create_refresh_token(subject=user_id)
    refresh_payload = decode_jwt_token(refresh_token)
    assert refresh_payload["sub"] == str(user_id)
    assert refresh_payload["type"] == "refresh"
    assert "jti" in refresh_payload


def test_secure_token_generation():
    """Verify generation of cryptographically secure random tokens."""
    token_1 = generate_secure_token()
    token_2 = generate_secure_token()

    assert len(token_1) >= 32
    assert len(token_2) >= 32
    assert token_1 != token_2
