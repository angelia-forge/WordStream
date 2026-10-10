import pytest
from pydantic import ValidationError

from app.config import AuthMode, Environment, Settings


def test_production_rejects_disabled_authentication() -> None:
    with pytest.raises(ValidationError, match="cannot be disabled"):
        Settings(environment=Environment.PRODUCTION, auth_mode=AuthMode.DISABLED)


def test_password_mode_requires_hash_and_secret() -> None:
    with pytest.raises(ValidationError, match="APP_PASSWORD_HASH"):
        Settings(auth_mode=AuthMode.PASSWORD)


def test_configuration_rejects_unknown_timezone() -> None:
    with pytest.raises(ValidationError, match="valid IANA timezone"):
        Settings(app_timezone="Mars/Olympus")
