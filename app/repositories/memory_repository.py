import re
import uuid
from datetime import UTC, datetime

from app.core.database import get_connection, initialize_database
from app.core.exceptions import MemoryNotFoundError
from app.models.memory import MemoryRecord, MemoryType


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def tokenize(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9:]+", value.lower()))


class MemoryRepository:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        initialize_database(self.database_path)

    def list_memories(
        self, user_id: str, include_archived: bool = False
    ) -> list[MemoryRecord]:
        query = """
        SELECT * FROM memories
        WHERE user_id = ?
        """
        params: list[str | int] = [user_id]
        if not include_archived:
            query += " AND is_archived = 0"
        query += " ORDER BY updated_at DESC, created_at DESC"

        with get_connection(self.database_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def get_memory(self, memory_id: str, user_id: str) -> MemoryRecord:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM memories WHERE id = ? AND user_id = ?",
                (memory_id, user_id),
            ).fetchone()
        if row is None:
            raise MemoryNotFoundError(f"Memory '{memory_id}' was not found.")
        return self._row_to_memory(row)

    def create_memory(
        self,
        user_id: str,
        memory_type: MemoryType,
        content: str,
        confidence: float,
        source: str,
    ) -> MemoryRecord:
        now = utc_now_iso()
        memory_id = str(uuid.uuid4())
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO memories (
                    id, user_id, type, content, confidence, source,
                    created_at, updated_at, last_used_at, is_archived
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    memory_id,
                    user_id,
                    memory_type,
                    content,
                    confidence,
                    source,
                    now,
                    now,
                    None,
                ),
            )
            connection.commit()
        return self.get_memory(memory_id, user_id)

    def update_memory(
        self,
        memory_id: str,
        user_id: str,
        *,
        content: str | None = None,
        confidence: float | None = None,
        source: str | None = None,
        is_archived: bool | None = None,
        last_used_at: str | None = None,
    ) -> MemoryRecord:
        current = self.get_memory(memory_id, user_id)
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                UPDATE memories
                SET content = ?, confidence = ?, source = ?, updated_at = ?,
                    last_used_at = ?, is_archived = ?
                WHERE id = ? AND user_id = ?
                """,
                (
                    content if content is not None else current.content,
                    confidence if confidence is not None else current.confidence,
                    source if source is not None else current.source,
                    utc_now_iso(),
                    last_used_at if last_used_at is not None else current.last_used_at,
                    int(is_archived if is_archived is not None else current.is_archived),
                    memory_id,
                    user_id,
                ),
            )
            connection.commit()
        return self.get_memory(memory_id, user_id)

    def archive_memory(self, memory_id: str, user_id: str) -> MemoryRecord:
        return self.update_memory(memory_id, user_id, is_archived=True)

    def find_similar_memory(
        self, user_id: str, memory_type: MemoryType, content: str
    ) -> MemoryRecord | None:
        target = normalize_text(content)
        target_tokens = tokenize(content)
        candidates = [
            memory
            for memory in self.list_memories(user_id, include_archived=False)
            if memory.type == memory_type
        ]
        best_match: MemoryRecord | None = None
        best_score = 0.0

        for candidate in candidates:
            normalized = normalize_text(candidate.content)
            if normalized == target:
                return candidate
            candidate_tokens = tokenize(candidate.content)
            if not target_tokens or not candidate_tokens:
                continue
            overlap = len(target_tokens & candidate_tokens) / max(
                len(target_tokens), len(candidate_tokens)
            )
            if overlap > best_score:
                best_score = overlap
                best_match = candidate

        if best_score >= 0.75:
            return best_match
        return None

    def get_relevant_memories(self, user_id: str, message: str) -> list[MemoryRecord]:
        memories = self.list_memories(user_id, include_archived=False)
        if len(memories) < 30:
            return memories

        message_tokens = tokenize(message)

        def score(memory: MemoryRecord) -> tuple[int, str, str]:
            content_tokens = tokenize(memory.content)
            overlap = len(message_tokens & content_tokens)
            return (overlap, memory.last_used_at or "", memory.updated_at)

        ranked = sorted(memories, key=score, reverse=True)
        return ranked[:20]

    def touch_memories(self, user_id: str, memory_ids: list[str]) -> None:
        if not memory_ids:
            return
        now = utc_now_iso()
        with get_connection(self.database_path) as connection:
            connection.executemany(
                """
                UPDATE memories
                SET last_used_at = ?, updated_at = updated_at
                WHERE id = ? AND user_id = ?
                """,
                [(now, memory_id, user_id) for memory_id in memory_ids],
            )
            connection.commit()

    @staticmethod
    def _row_to_memory(row) -> MemoryRecord:
        return MemoryRecord(
            id=row["id"],
            user_id=row["user_id"],
            type=row["type"],
            content=row["content"],
            confidence=row["confidence"],
            source=row["source"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_used_at=row["last_used_at"],
            is_archived=bool(row["is_archived"]),
        )
