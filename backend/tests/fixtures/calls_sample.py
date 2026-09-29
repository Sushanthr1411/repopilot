"""Call-extraction fixture for parser testing."""


def authenticate(username: str, password: str) -> bool:
    """Check credentials."""
    return True


def save_user(user: dict) -> None:
    """Persist a user."""
    pass


def log_event(event: str) -> None:
    pass


class UserService:
    """Manages user lifecycle."""

    def create_user(self, name: str) -> dict:
        """Create and persist a new user."""
        ok = authenticate(name, "default")
        user = {"name": name, "active": ok}
        save_user(user)
        self.notify(user)
        return user

    def notify(self, user: dict) -> None:
        """Send a notification."""
        log_event("user_created")

    def delete_user(self, user: dict) -> None:
        log_event("user_deleted")
        self.notify(user)
