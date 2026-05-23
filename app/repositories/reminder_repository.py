import uuid

from app.core.database import get_connection, initialize_database
from app.models.reminder import ReminderCreateRequest, ReminderRecord, ReminderUpdateRequest
from app.repositories.memory_repository import utc_now_iso


class ReminderRepository:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        initialize_database(self.database_path)

    def list_reminders(self, user_id: str, active_only: bool = False) -> list[ReminderRecord]:
        query = "SELECT * FROM reminders WHERE user_id = ?"
        params: list[object] = [user_id]
        if active_only:
            query += " AND active = 1"
        query += " ORDER BY scheduled_time ASC, created_at DESC"
        with get_connection(self.database_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_reminder(row) for row in rows]

    def get_reminder(self, reminder_id: str, user_id: str) -> ReminderRecord | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM reminders WHERE id = ? AND user_id = ?",
                (reminder_id, user_id),
            ).fetchone()
        return None if row is None else self._row_to_reminder(row)

    def create_reminder(self, user_id: str, request: ReminderCreateRequest) -> ReminderRecord:
        reminder_id = str(uuid.uuid4())
        now = utc_now_iso()
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO reminders (
                    id, user_id, type, title, message, scheduled_time, timezone,
                    recurrence_rule, active, source, last_sent_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    reminder_id,
                    user_id,
                    request.type,
                    request.title,
                    request.message,
                    request.scheduled_time,
                    request.timezone,
                    request.recurrence_rule,
                    int(request.active),
                    request.source,
                    now,
                    now,
                ),
            )
            connection.commit()
        reminder = self.get_reminder(reminder_id, user_id)
        assert reminder is not None
        return reminder

    def update_reminder(
        self,
        reminder_id: str,
        user_id: str,
        patch: ReminderUpdateRequest,
    ) -> ReminderRecord:
        current = self.get_reminder(reminder_id, user_id)
        assert current is not None
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                UPDATE reminders
                SET title = ?, message = ?, scheduled_time = ?, timezone = ?,
                    recurrence_rule = ?, active = ?, last_sent_at = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (
                    patch.title if patch.title is not None else current.title,
                    patch.message if patch.message is not None else current.message,
                    patch.scheduled_time if patch.scheduled_time is not None else current.scheduled_time,
                    patch.timezone if patch.timezone is not None else current.timezone,
                    patch.recurrence_rule if patch.recurrence_rule is not None else current.recurrence_rule,
                    int(patch.active if patch.active is not None else current.active),
                    patch.last_sent_at if patch.last_sent_at is not None else current.last_sent_at,
                    utc_now_iso(),
                    reminder_id,
                    user_id,
                ),
            )
            connection.commit()
        refreshed = self.get_reminder(reminder_id, user_id)
        assert refreshed is not None
        return refreshed

    def delete_reminder(self, reminder_id: str, user_id: str) -> ReminderRecord | None:
        reminder = self.get_reminder(reminder_id, user_id)
        if reminder is None:
            return None
        return self.update_reminder(reminder_id, user_id, ReminderUpdateRequest(active=False))

    @staticmethod
    def _row_to_reminder(row) -> ReminderRecord:
        return ReminderRecord(
            id=row["id"],
            user_id=row["user_id"],
            type=row["type"],
            title=row["title"],
            message=row["message"],
            scheduled_time=row["scheduled_time"],
            timezone=row["timezone"],
            recurrence_rule=row["recurrence_rule"],
            active=bool(row["active"]),
            source=row["source"],
            last_sent_at=row["last_sent_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
