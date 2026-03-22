from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mtls_demo.protocol import AgentRecord, AgentRegistration, CommandRecord, CommandResultUpdate, EnqueueCommandRequest


class StateStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def init_db(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    agent_id TEXT PRIMARY KEY,
                    display_name TEXT,
                    capabilities_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_seen TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS commands (
                    command_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    command TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    timeout_seconds INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    leased_at TEXT,
                    completed_at TEXT,
                    exit_code INTEGER,
                    stdout TEXT NOT NULL DEFAULT '',
                    stderr TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(agent_id) REFERENCES agents(agent_id)
                );
                """
            )
            connection.commit()

    def register_agent(self, registration: AgentRegistration) -> AgentRecord:
        now = utc_now()
        existing = self.get_agent(registration.agent_id)
        created_at = existing.created_at if existing else now
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agents (
                    agent_id,
                    display_name,
                    capabilities_json,
                    metadata_json,
                    status,
                    created_at,
                    updated_at,
                    last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    capabilities_json = excluded.capabilities_json,
                    metadata_json = excluded.metadata_json,
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    last_seen = excluded.last_seen
                """,
                (
                    registration.agent_id,
                    registration.display_name,
                    json.dumps(registration.capabilities),
                    json.dumps(registration.metadata),
                    "online",
                    created_at,
                    now,
                    now,
                ),
            )
            connection.commit()
        agent = self.get_agent(registration.agent_id)
        if agent is None:
            raise RuntimeError("Failed to store agent registration")
        return agent

    def get_agent(self, agent_id: str) -> AgentRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM agents WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()
        return self._agent_from_row(row) if row else None

    def mark_agent_seen(self, agent_id: str) -> AgentRecord | None:
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE agents SET status = ?, updated_at = ?, last_seen = ? WHERE agent_id = ?",
                ("online", now, now, agent_id),
            )
            connection.commit()
        return self.get_agent(agent_id)

    def list_agents(self) -> list[AgentRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM agents ORDER BY updated_at DESC, agent_id ASC"
            ).fetchall()
        return [self._agent_from_row(row) for row in rows]

    def prune_stale_agents(self, stale_after_seconds: int) -> list[str]:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)
        pruned: list[str] = []
        with self._connect() as connection:
            rows = connection.execute("SELECT agent_id, last_seen FROM agents").fetchall()
            for row in rows:
                last_seen = datetime.fromisoformat(row["last_seen"])
                if last_seen < cutoff:
                    pruned.append(row["agent_id"])
            if pruned:
                placeholders = ", ".join("?" for _ in pruned)
                connection.execute(
                    f"DELETE FROM agents WHERE agent_id IN ({placeholders})",
                    pruned,
                )
                connection.commit()
        return pruned

    def enqueue_command(self, request: EnqueueCommandRequest) -> CommandRecord:
        now = utc_now()
        command_id = str(uuid.uuid4())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO commands (
                    command_id,
                    agent_id,
                    command,
                    requested_by,
                    timeout_seconds,
                    status,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    command_id,
                    request.agent_id,
                    request.command,
                    request.requested_by,
                    request.timeout_seconds,
                    "queued",
                    now,
                ),
            )
            connection.commit()
        command = self.get_command(command_id)
        if command is None:
            raise RuntimeError("Failed to store command")
        return command

    def get_command(self, command_id: str) -> CommandRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM commands WHERE command_id = ?",
                (command_id,),
            ).fetchone()
        return self._command_from_row(row) if row else None

    def lease_next_command(self, agent_id: str) -> CommandRecord | None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT *
                FROM commands
                WHERE agent_id = ? AND status = 'queued'
                ORDER BY created_at ASC, command_id ASC
                LIMIT 1
                """,
                (agent_id,),
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            leased_at = utc_now()
            updated = connection.execute(
                "UPDATE commands SET status = ?, leased_at = ? WHERE command_id = ? AND status = 'queued'",
                ("in_progress", leased_at, row["command_id"]),
            )
            if updated.rowcount != 1:
                connection.rollback()
                return None
            connection.commit()
        finally:
            connection.close()
        return self.get_command(row["command_id"])

    def complete_command(self, command_id: str, result: CommandResultUpdate) -> CommandRecord:
        status = "completed" if result.exit_code == 0 else "failed"
        completed_at = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE commands
                SET status = ?, completed_at = ?, exit_code = ?, stdout = ?, stderr = ?
                WHERE command_id = ?
                """,
                (
                    status,
                    completed_at,
                    result.exit_code,
                    result.stdout,
                    result.stderr,
                    command_id,
                ),
            )
            connection.commit()
        command = self.get_command(command_id)
        if command is None:
            raise RuntimeError("Failed to update command result")
        return command

    def list_commands(self, agent_id: str | None = None, limit: int = 100) -> list[CommandRecord]:
        with self._connect() as connection:
            if agent_id:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM commands
                    WHERE agent_id = ?
                    ORDER BY created_at DESC, command_id DESC
                    LIMIT ?
                    """,
                    (agent_id, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM commands
                    ORDER BY created_at DESC, command_id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [self._command_from_row(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _agent_from_row(row: sqlite3.Row) -> AgentRecord:
        return AgentRecord(
            agent_id=row["agent_id"],
            display_name=row["display_name"],
            capabilities=json.loads(row["capabilities_json"]),
            metadata=json.loads(row["metadata_json"]),
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_seen=row["last_seen"],
        )

    @staticmethod
    def _command_from_row(row: sqlite3.Row) -> CommandRecord:
        return CommandRecord(
            command_id=row["command_id"],
            agent_id=row["agent_id"],
            command=row["command"],
            requested_by=row["requested_by"],
            timeout_seconds=row["timeout_seconds"],
            status=row["status"],
            created_at=row["created_at"],
            leased_at=row["leased_at"],
            completed_at=row["completed_at"],
            exit_code=row["exit_code"],
            stdout=row["stdout"],
            stderr=row["stderr"],
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
