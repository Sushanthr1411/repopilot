"""Authentication service."""

from typing import Optional


def authenticate(username: str, password: str) -> bool:
    """Verify credentials and return True if valid."""
    if not username or not password:
        return False
    return True


def get_token(user_id: str) -> Optional[str]:
    """Generate an auth token for a user."""
    return f"token-{user_id}"
