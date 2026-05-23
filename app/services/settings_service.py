from datetime import UTC, datetime

from app.models.insight import InsightPreferenceUpdateRequest
from app.models.settings import FeatureName, UserSettingsRecord, UserSettingsUpdateRequest
from app.repositories.insight_repository import InsightRepository
from app.repositories.settings_repository import DEFAULT_FEATURE_FLAGS, SettingsRepository


class SettingsService:
    def __init__(
        self,
        repository: SettingsRepository,
        insight_repository: InsightRepository,
        user_id: str,
    ) -> None:
        self.repository = repository
        self.insight_repository = insight_repository
        self.user_id = user_id

    def get_user_settings(self) -> UserSettingsRecord:
        settings = self.repository.get_settings(self.user_id)
        insight_preferences = self.insight_repository.get_preferences(self.user_id)
        if settings.proactive_insights_enabled != insight_preferences.proactive_insights_enabled:
            settings = self.repository.update_settings(
                self.user_id,
                UserSettingsUpdateRequest(
                    proactive_insights_enabled=insight_preferences.proactive_insights_enabled
                ),
            )
        return settings

    def update_user_settings(self, patch: UserSettingsUpdateRequest) -> UserSettingsRecord:
        settings = self.repository.update_settings(self.user_id, patch)
        if patch.proactive_insights_enabled is not None:
            self.insight_repository.update_preferences(
                self.user_id,
                InsightPreferenceUpdateRequest(
                    proactive_insights_enabled=patch.proactive_insights_enabled
                ),
            )
        return self.get_user_settings()

    def enable_feature(self, feature_name: FeatureName) -> UserSettingsRecord:
        settings = self.get_user_settings()
        flags = dict(settings.feature_flags)
        flags[feature_name] = True
        patch = {"feature_flags": flags}
        if feature_name == "reminders":
            patch["reminders_enabled"] = True
        elif feature_name == "calendar":
            patch["calendar_enabled"] = True
        elif feature_name == "health_data":
            patch["health_data_enabled"] = True
        elif feature_name == "voice_mode":
            patch["voice_mode"] = True
        return self.update_user_settings(UserSettingsUpdateRequest(**patch))

    def disable_feature(self, feature_name: FeatureName) -> UserSettingsRecord:
        settings = self.get_user_settings()
        flags = dict(settings.feature_flags)
        flags[feature_name] = False
        patch = {"feature_flags": flags}
        if feature_name == "reminders":
            patch["reminders_enabled"] = False
        elif feature_name == "calendar":
            patch["calendar_enabled"] = False
        elif feature_name == "health_data":
            patch["health_data_enabled"] = False
        elif feature_name == "voice_mode":
            patch["voice_mode"] = False
        return self.update_user_settings(UserSettingsUpdateRequest(**patch))

    def list_enabled_features(self) -> list[FeatureName]:
        settings = self.get_user_settings()
        enabled = [
            feature
            for feature, value in settings.feature_flags.items()
            if value
        ]
        return sorted(enabled)  # type: ignore[return-value]

    def get_effective_timezone(self) -> str:
        settings = self.get_user_settings()
        if (
            settings.goal_timezone_override
            and settings.goal_timezone_override_until
            and datetime.fromisoformat(settings.goal_timezone_override_until)
            > datetime.now(UTC)
        ):
            return settings.goal_timezone_override
        return settings.timezone

    def apply_private_mode_default(self, session_has_explicit_state: bool) -> bool:
        if session_has_explicit_state:
            return False
        return self.get_user_settings().private_mode_default

    def ensure_feature_defaults(self) -> UserSettingsRecord:
        settings = self.get_user_settings()
        merged_flags = dict(DEFAULT_FEATURE_FLAGS)
        merged_flags.update(settings.feature_flags)
        if merged_flags != settings.feature_flags:
            return self.update_user_settings(UserSettingsUpdateRequest(feature_flags=merged_flags))
        return settings
