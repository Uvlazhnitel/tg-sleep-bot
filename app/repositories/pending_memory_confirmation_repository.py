import uuid

from app.core.database import get_connection
from app.models.memory_control import PendingMemoryConfirmationRecord
from app.repositories.memory_repository import utc_now_iso


class PendingMemoryConfirmationRepository:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path

    def create_pending_confirmation(
        self,
        user_id: str,
        session_id: str,
        memory_updates_json: str,
        prompt_text: str,
    ) -> PendingMemoryConfirmationRecord:
        self.delete_pending_confirmation(user_id, session_id)
        confirmation_id = str(uuid.uuid4())
        created_at = utc_now_iso()
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO pending_memory_confirmations (
                    id, user_id, session_id, memory_updates_json, prompt_text, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    confirmation_id,
                    user_id,
                    session_id,
                    memory_updates_json,
                    prompt_text,
                    created_at,
                ),
            )
            connection.commit()
        return self.get_pending_confirmation(user_id, session_id)

    def get_pending_confirmation(
        self,
        user_id: str,
        session_id: str,
    ) -> PendingMemoryConfirmationRecord | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT * FROM pending_memory_confirmations
                WHERE user_id = ? AND session_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id, session_id),
            ).fetchone()
        if row is None:
            return None
        return PendingMemoryConfirmationRecord(
            id=row["id"],
            user_id=row["user_id"],
            session_id=row["session_id"],
            memory_updates_json=row["memory_updates_json"],
            prompt_text=row["prompt_text"],
            created_at=row["created_at"],
        )

    def delete_pending_confirmation(self, user_id: str, session_id: str) -> None:
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                DELETE FROM pending_memory_confirmations
                WHERE user_id = ? AND session_id = ?
                """,
                (user_id, session_id),
            )
            connection.commit()
