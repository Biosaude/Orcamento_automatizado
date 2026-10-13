import pytest
from pydantic import ValidationError

from backend.app.core.config import Settings


def test_settings_read_environment_and_mask_secrets(monkeypatch):
    monkeypatch.setenv("BIOSAUDE_ENVIRONMENT", "test")
    monkeypatch.setenv("BIOSAUDE_OPENAI_API_KEY", "synthetic-test-secret")
    settings = Settings(_env_file=None)
    assert settings.environment == "test"
    assert settings.openai_api_key.get_secret_value() == "synthetic-test-secret"
    assert "synthetic-test-secret" not in repr(settings)
    assert "synthetic-test-secret" not in settings.model_dump_json()


def test_settings_load_local_dotenv_without_connecting(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("BIOSAUDE_ENVIRONMENT=test\n", encoding="utf-8")
    assert Settings(_env_file=dotenv).environment == "test"


def test_invalid_environment_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="unknown")
