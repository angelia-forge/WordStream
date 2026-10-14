import pytest
from pydantic import ValidationError

from app.config import AuthMode, Environment, Settings


def test_production_rejects_disabled_authentication() -> None:
    with pytest.raises(ValidationError, match="cannot be disabled"):
        Settings(
            _env_file=None,
            environment=Environment.PRODUCTION,
            auth_mode=AuthMode.DISABLED,
        )


def test_password_mode_requires_password_and_secret() -> None:
    with pytest.raises(ValidationError, match="APP_PASSWORD"):
        Settings(
            _env_file=None,
            auth_mode=AuthMode.PASSWORD,
            app_password=None,
            secret_key=None,
        )


def test_production_requires_password_and_secret() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY and APP_PASSWORD"):
        Settings(
            _env_file=None,
            environment=Environment.PRODUCTION,
            auth_mode=AuthMode.PASSWORD,
            app_password=None,
            secret_key=None,
        )


@pytest.mark.parametrize(
    ("password", "secret_key"),
    [
        ("", "a" * 32),
        ("   ", "a" * 32),
        ("valid-password", ""),
        ("valid-password", "\t"),
    ],
)
def test_password_mode_rejects_blank_credentials(
    password: str,
    secret_key: str,
) -> None:
    with pytest.raises(ValidationError, match="APP_PASSWORD"):
        Settings(
            _env_file=None,
            auth_mode=AuthMode.PASSWORD,
            app_password=password,
            secret_key=secret_key,
        )


def test_password_mode_requires_long_session_secret() -> None:
    with pytest.raises(ValidationError, match="at least 32 characters"):
        Settings(
            _env_file=None,
            auth_mode=AuthMode.PASSWORD,
            app_password="valid-password",
            secret_key="too-short",
        )


def test_password_mode_accepts_nonblank_credentials() -> None:
    settings = Settings(
        _env_file=None,
        auth_mode=AuthMode.PASSWORD,
        app_password="valid-password",
        secret_key="a" * 32,
    )

    assert settings.auth_mode is AuthMode.PASSWORD


def test_configuration_rejects_unknown_timezone() -> None:
    with pytest.raises(ValidationError, match="valid IANA timezone"):
        Settings(_env_file=None, app_timezone="Mars/Olympus")
