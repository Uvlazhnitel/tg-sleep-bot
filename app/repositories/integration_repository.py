import json
import uuid

from app.core.database import get_connection, initialize_database
from app.models.integration import HealthSleepSummary, IntegrationConnectionRecord
from app.repositories.memory_repository import utc_now_iso


class IntegrationRepository:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        initialize_database(self.database_path)

    def list_connections(self, user_id: str, kind: str | None = None) -> list[IntegrationConnectionRecord]:
        query = "SELECT * FROM integration_connections WHERE user_id = ?"
        params: list[object] = [user_id]
        if kind is not None:
            query += " AND kind = ?"
            params.append(kind)
        query += " ORDER BY updated_at DESC"
        with get_connection(self.database_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_connection(row) for row in rows]

    def get_active_connection(self, user_id: str, kind: str) -> IntegrationConnectionRecord | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT * FROM integration_connections
                WHERE user_id = ? AND kind = ? AND status = 'connected'
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (user_id, kind),
            ).fetchone()
        return None if row is None else self._row_to_connection(row)

    def connect(
        self,
        user_id: str,
        kind: str,
        provider_name: str,
        metadata: dict[str, str] | None = None,
    ) -> IntegrationConnectionRecord:
        existing = self.get_active_connection(user_id, kind)
        if existing is not None and existing.provider_name == provider_name:
            return existing
        connection_id = str(uuid.uuid4())
        now = utc_now_iso()
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO integration_connections (
                    id, user_id, kind, provider_name, status,
                    metadata_json, created_at, updated_at, disconnected_at
                )
                VALUES (?, ?, ?, ?, 'connected', ?, ?, ?, NULL)
                """,
                (
                    connection_id,
                    user_id,
                    kind,
                    provider_name,
                    json.dumps(metadata or {}),
                    now,
                    now,
                ),
            )
            connection.commit()
        active = self.get_active_connection(user_id, kind)
        assert active is not None
        return active

    def disconnect(self, user_id: str, kind: str) -> IntegrationConnectionRecord | None:
        existing = self.get_active_connection(user_id, kind)
        if existing is None:
            return None
        now = utc_now_iso()
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                UPDATE integration_connections
                SET status = 'disconnected', updated_at = ?, disconnected_at = ?
                WHERE id = ?
                """,
                (now, now, existing.id),
            )
            connection.commit()
        return self.list_connections(user_id, kind)[0]

    def save_health_summary(self, user_id: str, summary: HealthSleepSummary) -> HealthSleepSummary:
        summary_id = str(uuid.uuid4())
        created_at = utc_now_iso()
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO health_sleep_summaries (
                    id, user_id, provider_name, sleep_start, sleep_end, wake_time,
                    sleep_duration_minutes, interruptions, resting_heart_rate,
                    sleep_score, device_derived, raw_summary_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary_id,
                    user_id,
                    summary.provider_name,
                    summary.sleep_start,
                    summary.sleep_end,
                    summary.wake_time,
                    summary.sleep_duration_minutes,
                    summary.interruptions,
                    summary.resting_heart_rate,
                    summary.sleep_score,
                    int(summary.device_derived),
                    json.dumps(summary.raw_summary),
                    created_at,
                ),
            )
            connection.commit()
        return HealthSleepSummary(
            id=summary_id,
            user_id=user_id,
            provider_name=summary.provider_name,
            sleep_start=summary.sleep_start,
            sleep_end=summary.sleep_end,
            wake_time=summary.wake_time,
            sleep_duration_minutes=summary.sleep_duration_minutes,
            interruptions=summary.interruptions,
            resting_heart_rate=summary.resting_heart_rate,
            sleep_score=summary.sleep_score,
            device_derived=summary.device_derived,
            raw_summary=summary.raw_summary,
            created_at=created_at,
        )

    def list_health_summaries(self, user_id: str, provider_name: str | None = None) -> list[HealthSleepSummary]:
        query = "SELECT * FROM health_sleep_summaries WHERE user_id = ?"
        params: list[object] = [user_id]
        if provider_name is not None:
            query += " AND provider_name = ?"
            params.append(provider_name)
        query += " ORDER BY created_at DESC"
        with get_connection(self.database_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_health_summary(row) for row in rows]

    def delete_health_data(self, user_id: str, provider_name: str | None = None) -> int:
        query = "DELETE FROM health_sleep_summaries WHERE user_id = ?"
        params: list[object] = [user_id]
        if provider_name is not None:
            query += " AND provider_name = ?"
            params.append(provider_name)
        with get_connection(self.database_path) as connection:
            cursor = connection.execute(query, params)
            connection.commit()
        return cursor.rowcount

    @staticmethod
    def _row_to_connection(row) -> IntegrationConnectionRecord:
        return IntegrationConnectionRecord(
            id=row["id"],
            user_id=row["user_id"],
            kind=row["kind"],
            provider_name=row["provider_name"],
            status=row["status"],
            metadata=json.loads(row["metadata_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            disconnected_at=row["disconnected_at"],
        )

    @staticmethod
    def _row_to_health_summary(row) -> HealthSleepSummary:
        return HealthSleepSummary(
            id=row["id"],
            user_id=row["user_id"],
            provider_name=row["provider_name"],
            sleep_start=row["sleep_start"],
            sleep_end=row["sleep_end"],
            wake_time=row["wake_time"],
            sleep_duration_minutes=row["sleep_duration_minutes"],
            interruptions=row["interruptions"],
            resting_heart_rate=row["resting_heart_rate"],
            sleep_score=row["sleep_score"],
            device_derived=bool(row["device_derived"]),
            raw_summary=json.loads(row["raw_summary_json"]),
            created_at=row["created_at"],
        )
