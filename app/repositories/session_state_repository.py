from app.core.database import get_connection
from app.models.memory_control import MemorySessionStateRecord
from app.repositories.memory_repository import utc_now_iso


class SessionStateRepository:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path

    def get_state(self, user_id: str, session_id: str) -> MemorySessionStateRecord | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT * FROM memory_session_state
                WHERE user_id = ? AND session_id = ?
                """,
                (user_id, session_id),
            ).fetchone()
        if row is None:
            return None
        return MemorySessionStateRecord(
            user_id=row["user_id"],
            session_id=row["session_id"],
            memory_enabled=bool(row["memory_enabled"]),
            updated_at=row["updated_at"],
        )

    def set_memory_enabled(
        self,
        user_id: str,
        session_id: str,
        memory_enabled: bool,
    ) -> MemorySessionStateRecord:
        now = utc_now_iso()
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO memory_session_state (user_id, session_id, memory_enabled, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, session_id)
                DO UPDATE SET memory_enabled = excluded.memory_enabled, updated_at = excluded.updated_at
                """,
                (user_id, session_id, int(memory_enabled), now),
            )
            connection.commit()
        return self.get_state(user_id, session_id)
