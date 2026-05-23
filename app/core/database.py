import sqlite3
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    type TEXT NOT NULL,
    content TEXT NOT NULL,
    confidence REAL NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_used_at TEXT,
    evidence_count INTEGER NOT NULL DEFAULT 1,
    positive_count INTEGER NOT NULL DEFAULT 0,
    negative_count INTEGER NOT NULL DEFAULT 0,
    last_confirmed_at TEXT,
    related_memory_id TEXT,
    relation_type TEXT,
    is_archived INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_memories_user_archived
ON memories (user_id, is_archived);

CREATE INDEX IF NOT EXISTS idx_memories_user_type
ON memories (user_id, type);

CREATE TABLE IF NOT EXISTS advice_traces (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    user_message TEXT NOT NULL,
    assistant_reply TEXT NOT NULL,
    source_memory_ids_json TEXT NOT NULL,
    knowledge_card_ids_json TEXT NOT NULL,
    safety_category TEXT NOT NULL,
    is_private_mode INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_advice_traces_user_session_created
ON advice_traces (user_id, session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS memory_session_state (
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    memory_enabled INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, session_id)
);

CREATE TABLE IF NOT EXISTS pending_memory_confirmations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    memory_updates_json TEXT NOT NULL,
    prompt_text TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pending_memory_confirmations_user_session_created
ON pending_memory_confirmations (user_id, session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS insights (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    confidence TEXT NOT NULL,
    suggested_experiment TEXT NOT NULL,
    related_memory_ids_json TEXT NOT NULL,
    related_message_ids_json TEXT NOT NULL,
    related_knowledge_card_ids_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_shown_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_insights_user_status_updated
ON insights (user_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS insight_preferences (
    user_id TEXT PRIMARY KEY,
    proactive_insights_enabled INTEGER NOT NULL,
    proactive_insight_frequency TEXT NOT NULL,
    last_proactive_insight_at TEXT,
    insight_min_evidence_threshold INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
"""

MEMORY_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("evidence_count", "ALTER TABLE memories ADD COLUMN evidence_count INTEGER NOT NULL DEFAULT 1"),
    ("positive_count", "ALTER TABLE memories ADD COLUMN positive_count INTEGER NOT NULL DEFAULT 0"),
    ("negative_count", "ALTER TABLE memories ADD COLUMN negative_count INTEGER NOT NULL DEFAULT 0"),
    ("last_confirmed_at", "ALTER TABLE memories ADD COLUMN last_confirmed_at TEXT"),
    ("related_memory_id", "ALTER TABLE memories ADD COLUMN related_memory_id TEXT"),
    ("relation_type", "ALTER TABLE memories ADD COLUMN relation_type TEXT"),
)

ADVICE_TRACE_MIGRATIONS: tuple[tuple[str, str], ...] = (
    (
        "is_private_mode",
        "ALTER TABLE advice_traces ADD COLUMN is_private_mode INTEGER NOT NULL DEFAULT 0",
    ),
)


def get_connection(database_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(database_path: str) -> None:
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    with get_connection(database_path) as connection:
        connection.executescript(SCHEMA_SQL)
        memory_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(memories)").fetchall()
        }
        for column_name, statement in MEMORY_MIGRATIONS:
            if column_name not in memory_columns:
                connection.execute(statement)

        advice_trace_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(advice_traces)").fetchall()
        }
        for column_name, statement in ADVICE_TRACE_MIGRATIONS:
            if column_name not in advice_trace_columns:
                connection.execute(statement)
        connection.commit()
