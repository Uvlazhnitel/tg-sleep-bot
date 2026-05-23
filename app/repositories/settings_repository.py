import json

from app.core.database import get_connection, initialize_database
from app.models.settings import QuietHours, UserSettingsRecord, UserSettingsUpdateRequest
from app.repositories.memory_repository import utc_now_iso


DEFAULT_FEATURE_FLAGS = {
    "reminders": False,
    "calendar": False,
    "health_data": False,
    "timezone_travel": True,
    "voice_mode": False,
}


class SettingsRepository:
    def __init__(self, database_path: str, default_timezone: str) -> None:
        self.database_path = database_path
        self.default_timezone = default_timezone
        initialize_database(self.database_path)

    def get_settings(self, user_id: str) -> UserSettingsRecord:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM user_settings WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if row is None:
                now = utc_now_iso()
                connection.execute(
                    """
                    INSERT INTO user_settings (
                        user_id, timezone, reminders_enabled, calendar_enabled,
                        health_data_enabled, voice_mode, private_mode_default,
                        proactive_insights_enabled, feature_flags_json,
                        notification_quiet_hours_json, goal_timezone_override,
                        goal_timezone_override_until, updated_at
                    )
                    VALUES (?, ?, 0, 0, 0, 0, 0, 1, ?, ?, NULL, NULL, ?)
                    """,
                    (
                        user_id,
                        self.default_timezone,
                        json.dumps(DEFAULT_FEATURE_FLAGS, sort_keys=True),
                        QuietHours().model_dump_json(),
                        now,
                    ),
                )
                connection.commit()
                row = connection.execute(
                    "SELECT * FROM user_settings WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
        assert row is not None
        return self._row_to_settings(row)

    def update_settings(
        self,
        user_id: str,
        patch: UserSettingsUpdateRequest,
    ) -> UserSettingsRecord:
        current = self.get_settings(user_id)
        feature_flags = (
            patch.feature_flags if patch.feature_flags is not None else current.feature_flags
        )
        quiet_hours = (
            patch.notification_quiet_hours
            if patch.notification_quiet_hours is not None
            else current.notification_quiet_hours
        )
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                UPDATE user_settings
                SET timezone = ?, reminders_enabled = ?, calendar_enabled = ?,
                    health_data_enabled = ?, voice_mode = ?, private_mode_default = ?,
                    proactive_insights_enabled = ?, feature_flags_json = ?,
                    notification_quiet_hours_json = ?, goal_timezone_override = ?,
                    goal_timezone_override_until = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (
                    patch.timezone if patch.timezone is not None else current.timezone,
                    int(patch.reminders_enabled if patch.reminders_enabled is not None else current.reminders_enabled),
                    int(patch.calendar_enabled if patch.calendar_enabled is not None else current.calendar_enabled),
                    int(patch.health_data_enabled if patch.health_data_enabled is not None else current.health_data_enabled),
                    int(patch.voice_mode if patch.voice_mode is not None else current.voice_mode),
                    int(patch.private_mode_default if patch.private_mode_default is not None else current.private_mode_default),
                    int(
                        patch.proactive_insights_enabled
                        if patch.proactive_insights_enabled is not None
                        else current.proactive_insights_enabled
                    ),
                    json.dumps(feature_flags, sort_keys=True),
                    quiet_hours.model_dump_json(),
                    patch.goal_timezone_override
                    if patch.goal_timezone_override is not None
                    else current.goal_timezone_override,
                    patch.goal_timezone_override_until
                    if patch.goal_timezone_override_until is not None
                    else current.goal_timezone_override_until,
                    utc_now_iso(),
                    user_id,
                ),
            )
            connection.commit()
        return self.get_settings(user_id)

    @staticmethod
    def _row_to_settings(row) -> UserSettingsRecord:
        return UserSettingsRecord(
            user_id=row["user_id"],
            timezone=row["timezone"],
            reminders_enabled=bool(row["reminders_enabled"]),
            calendar_enabled=bool(row["calendar_enabled"]),
            health_data_enabled=bool(row["health_data_enabled"]),
            voice_mode=bool(row["voice_mode"]),
            private_mode_default=bool(row["private_mode_default"]),
            proactive_insights_enabled=bool(row["proactive_insights_enabled"]),
            feature_flags=json.loads(row["feature_flags_json"]),
            notification_quiet_hours=QuietHours.model_validate_json(
                row["notification_quiet_hours_json"]
            ),
            goal_timezone_override=row["goal_timezone_override"],
            goal_timezone_override_until=row["goal_timezone_override_until"],
            updated_at=row["updated_at"],
        )
