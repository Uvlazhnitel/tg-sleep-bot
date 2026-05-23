import json
import uuid
from datetime import UTC, datetime, timedelta

from app.core.database import get_connection, initialize_database
from app.models.insight import (
    InsightCreateRequest,
    InsightPreferenceRecord,
    InsightPreferenceUpdateRequest,
    InsightRecord,
    InsightUpdateRequest,
)
from app.repositories.memory_repository import normalize_text, utc_now_iso


class InsightRepository:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        initialize_database(self.database_path)

    def list_insights(
        self,
        user_id: str,
        *,
        include_archived: bool = False,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[InsightRecord]:
        query = "SELECT * FROM insights WHERE user_id = ?"
        params: list[object] = [user_id]
        if status is not None:
            query += " AND status = ?"
            params.append(status)
        elif not include_archived:
            query += " AND status != 'archived'"
        query += " ORDER BY updated_at DESC, created_at DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with get_connection(self.database_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_insight(row) for row in rows]

    def get_insight(self, insight_id: str, user_id: str) -> InsightRecord | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM insights WHERE id = ? AND user_id = ?",
                (insight_id, user_id),
            ).fetchone()
        return None if row is None else self._row_to_insight(row)

    def create_insight(self, user_id: str, request: InsightCreateRequest) -> InsightRecord:
        insight_id = str(uuid.uuid4())
        now = utc_now_iso()
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO insights (
                    id, user_id, title, summary, evidence_json, confidence,
                    suggested_experiment, related_memory_ids_json,
                    related_message_ids_json, related_knowledge_card_ids_json,
                    status, created_at, updated_at, last_shown_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    insight_id,
                    user_id,
                    request.title,
                    request.summary,
                    json.dumps(request.evidence),
                    request.confidence,
                    request.suggested_experiment,
                    json.dumps(request.related_memory_ids),
                    json.dumps(request.related_message_ids),
                    json.dumps(request.related_knowledge_card_ids),
                    request.status,
                    now,
                    now,
                    request.last_shown_at,
                ),
            )
            connection.commit()
        return self.get_insight(insight_id, user_id)

    def update_insight(
        self,
        insight_id: str,
        user_id: str,
        request: InsightUpdateRequest,
    ) -> InsightRecord:
        current = self.get_insight(insight_id, user_id)
        assert current is not None
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                UPDATE insights
                SET title = ?, summary = ?, evidence_json = ?, confidence = ?,
                    suggested_experiment = ?, related_memory_ids_json = ?,
                    related_message_ids_json = ?, related_knowledge_card_ids_json = ?,
                    status = ?, updated_at = ?, last_shown_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (
                    request.title if request.title is not None else current.title,
                    request.summary if request.summary is not None else current.summary,
                    json.dumps(request.evidence if request.evidence is not None else current.evidence),
                    request.confidence if request.confidence is not None else current.confidence,
                    (
                        request.suggested_experiment
                        if request.suggested_experiment is not None
                        else current.suggested_experiment
                    ),
                    json.dumps(
                        request.related_memory_ids
                        if request.related_memory_ids is not None
                        else current.related_memory_ids
                    ),
                    json.dumps(
                        request.related_message_ids
                        if request.related_message_ids is not None
                        else current.related_message_ids
                    ),
                    json.dumps(
                        request.related_knowledge_card_ids
                        if request.related_knowledge_card_ids is not None
                        else current.related_knowledge_card_ids
                    ),
                    request.status if request.status is not None else current.status,
                    utc_now_iso(),
                    request.last_shown_at if request.last_shown_at is not None else current.last_shown_at,
                    insight_id,
                    user_id,
                ),
            )
            connection.commit()
        refreshed = self.get_insight(insight_id, user_id)
        assert refreshed is not None
        return refreshed

    def find_duplicate_insight(
        self,
        user_id: str,
        title: str,
        summary: str,
    ) -> InsightRecord | None:
        target_title = normalize_text(title)
        target_summary = normalize_text(summary)
        for insight in self.list_insights(user_id, include_archived=True):
            if normalize_text(insight.title) == target_title:
                return insight
            if normalize_text(insight.summary) == target_summary:
                return insight
        return None

    def get_latest_shown_active_insight(self, user_id: str) -> InsightRecord | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT * FROM insights
                WHERE user_id = ? AND status = 'active' AND last_shown_at IS NOT NULL
                ORDER BY last_shown_at DESC, updated_at DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        return None if row is None else self._row_to_insight(row)

    def get_recent_insights_since(self, user_id: str, since_iso: str | None) -> list[InsightRecord]:
        if since_iso is None:
            return self.list_insights(user_id, include_archived=True)
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT * FROM insights
                WHERE user_id = ? AND created_at >= ?
                ORDER BY created_at DESC
                """,
                (user_id, since_iso),
            ).fetchall()
        return [self._row_to_insight(row) for row in rows]

    def get_preferences(self, user_id: str) -> InsightPreferenceRecord:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM insight_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if row is None:
                now = utc_now_iso()
                connection.execute(
                    """
                    INSERT INTO insight_preferences (
                        user_id, proactive_insights_enabled, proactive_insight_frequency,
                        last_proactive_insight_at, insight_min_evidence_threshold, updated_at
                    )
                    VALUES (?, 1, 'weekly', NULL, 5, ?)
                    """,
                    (user_id, now),
                )
                connection.commit()
                row = connection.execute(
                    "SELECT * FROM insight_preferences WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
        assert row is not None
        return self._row_to_preferences(row)

    def update_preferences(
        self,
        user_id: str,
        request: InsightPreferenceUpdateRequest,
    ) -> InsightPreferenceRecord:
        current = self.get_preferences(user_id)
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                UPDATE insight_preferences
                SET proactive_insights_enabled = ?, proactive_insight_frequency = ?,
                    last_proactive_insight_at = ?, insight_min_evidence_threshold = ?,
                    updated_at = ?
                WHERE user_id = ?
                """,
                (
                    int(
                        request.proactive_insights_enabled
                        if request.proactive_insights_enabled is not None
                        else current.proactive_insights_enabled
                    ),
                    (
                        request.proactive_insight_frequency
                        if request.proactive_insight_frequency is not None
                        else current.proactive_insight_frequency
                    ),
                    (
                        request.last_proactive_insight_at
                        if request.last_proactive_insight_at is not None
                        else current.last_proactive_insight_at
                    ),
                    (
                        request.insight_min_evidence_threshold
                        if request.insight_min_evidence_threshold is not None
                        else current.insight_min_evidence_threshold
                    ),
                    utc_now_iso(),
                    user_id,
                ),
            )
            connection.commit()
        return self.get_preferences(user_id)

    @staticmethod
    def is_older_than_week(timestamp: str | None) -> bool:
        if timestamp is None:
            return True
        created = datetime.fromisoformat(timestamp)
        return datetime.now(UTC) - created >= timedelta(days=7)

    @staticmethod
    def _row_to_insight(row) -> InsightRecord:
        return InsightRecord(
            id=row["id"],
            user_id=row["user_id"],
            title=row["title"],
            summary=row["summary"],
            evidence=json.loads(row["evidence_json"]),
            confidence=row["confidence"],
            suggested_experiment=row["suggested_experiment"],
            related_memory_ids=json.loads(row["related_memory_ids_json"]),
            related_message_ids=json.loads(row["related_message_ids_json"]),
            related_knowledge_card_ids=json.loads(row["related_knowledge_card_ids_json"]),
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_shown_at=row["last_shown_at"],
        )

    @staticmethod
    def _row_to_preferences(row) -> InsightPreferenceRecord:
        return InsightPreferenceRecord(
            user_id=row["user_id"],
            proactive_insights_enabled=bool(row["proactive_insights_enabled"]),
            proactive_insight_frequency=row["proactive_insight_frequency"],
            last_proactive_insight_at=row["last_proactive_insight_at"],
            insight_min_evidence_threshold=row["insight_min_evidence_threshold"],
            updated_at=row["updated_at"],
        )
