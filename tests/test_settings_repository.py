from app.models.settings import UserSettingsUpdateRequest
from app.repositories.settings_repository import SettingsRepository


def test_settings_defaults_and_updates(tmp_path):
    repository = SettingsRepository(str(tmp_path / "settings.db"), "UTC")
    settings = repository.get_settings("default_user")

    assert settings.timezone == "UTC"
    assert settings.proactive_insights_enabled is True
    assert settings.feature_flags["reminders"] is False

    updated = repository.update_settings(
        "default_user",
        UserSettingsUpdateRequest(timezone="Europe/Riga", reminders_enabled=True),
    )

    assert updated.timezone == "Europe/Riga"
    assert updated.reminders_enabled is True
