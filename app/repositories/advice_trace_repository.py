import json
import uuid

from app.core.database import get_connection
from app.models.memory_control import AdviceTraceRecord
from app.repositories.memory_repository import utc_now_iso


class AdviceTraceRepository:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path

    def create_trace(
        self,
        user_id: str,
        session_id: str,
        user_message: str,
        assistant_reply: str,
        source_memory_ids: list[str],
        knowledge_card_ids: list[str],
        safety_category: str,
    ) -> AdviceTraceRecord:
        trace_id = str(uuid.uuid4())
        created_at = utc_now_iso()
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO advice_traces (
                    id, user_id, session_id, user_message, assistant_reply,
                    source_memory_ids_json, knowledge_card_ids_json, safety_category, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace_id,
                    user_id,
                    session_id,
                    user_message,
                    assistant_reply,
                    json.dumps(source_memory_ids),
                    json.dumps(knowledge_card_ids),
                    safety_category,
                    created_at,
                ),
            )
            connection.commit()
        return self.get_latest_trace(user_id, session_id)

    def get_latest_trace(
        self,
        user_id: str,
        session_id: str,
    ) -> AdviceTraceRecord | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT * FROM advice_traces
                WHERE user_id = ? AND session_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id, session_id),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_trace(row)

    @staticmethod
    def _row_to_trace(row) -> AdviceTraceRecord:
        return AdviceTraceRecord(
            id=row["id"],
            user_id=row["user_id"],
            session_id=row["session_id"],
            user_message=row["user_message"],
            assistant_reply=row["assistant_reply"],
            source_memory_ids=json.loads(row["source_memory_ids_json"]),
            knowledge_card_ids=json.loads(row["knowledge_card_ids_json"]),
            safety_category=row["safety_category"],
            created_at=row["created_at"],
        )
