"""Durable mission status and event history storage."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List


class MissionRepository:
    def __init__(self, database_path: str) -> None:
        self.database_path = Path(database_path).expanduser()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def create_mission(
        self,
        mission_id: str,
        route_id: str,
        route_version: int,
        state: str,
        checkpoint_total: int,
    ) -> None:
        now = _utc_now()
        with self._connection() as connection:
            connection.execute(
                '''
                INSERT INTO missions (
                    mission_id, route_id, route_version, state, checkpoint_index,
                    checkpoint_total, checkpoint_id, retry_count, progress, detail,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, 0, ?, '', 0, 0.0, '', ?, ?)
                ''',
                (mission_id, route_id, route_version, state, checkpoint_total, now, now),
            )

    def update_status(
        self,
        mission_id: str,
        *,
        state: str,
        checkpoint_index: int,
        checkpoint_total: int,
        checkpoint_id: str,
        retry_count: int,
        progress: float,
        detail: str,
    ) -> None:
        with self._connection() as connection:
            cursor = connection.execute(
                '''
                UPDATE missions
                SET state = ?, checkpoint_index = ?, checkpoint_total = ?, checkpoint_id = ?,
                    retry_count = ?, progress = ?, detail = ?, updated_at = ?
                WHERE mission_id = ?
                ''',
                (
                    state,
                    checkpoint_index,
                    checkpoint_total,
                    checkpoint_id,
                    retry_count,
                    progress,
                    detail,
                    _utc_now(),
                    mission_id,
                ),
            )
        if cursor.rowcount != 1:
            raise KeyError(f'mission {mission_id!r} was not found')

    def append_event(
        self,
        mission_id: str,
        *,
        previous_state: str,
        state: str,
        checkpoint_id: str,
        code: str,
        detail: str,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                '''
                INSERT INTO mission_events (
                    mission_id, previous_state, state, checkpoint_id, code, detail, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''',
                (mission_id, previous_state, state, checkpoint_id, code, detail, _utc_now()),
            )

    def get_mission(self, mission_id: str) -> dict:
        with self._connection() as connection:
            row = connection.execute(
                'SELECT * FROM missions WHERE mission_id = ?', (mission_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f'mission {mission_id!r} was not found')
        return dict(row)

    def list_events(self, mission_id: str) -> List[dict]:
        with self._connection() as connection:
            rows = connection.execute(
                'SELECT * FROM mission_events WHERE mission_id = ? ORDER BY event_id', (mission_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def record_checkin(
        self,
        mission_id: str,
        *,
        checkpoint_id: str,
        attempt: int,
        method: str,
        outcome: str,
        success: bool,
        marker_type: str,
        marker_id: str,
        confirmation_count: int,
        evidence_path: str,
        detail: str,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                '''
                INSERT INTO checkpoint_checkins (
                    mission_id, checkpoint_id, attempt, method, outcome, success,
                    marker_type, marker_id, confirmation_count, evidence_path, detail, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    mission_id,
                    checkpoint_id,
                    attempt,
                    method,
                    outcome,
                    int(success),
                    marker_type,
                    marker_id,
                    confirmation_count,
                    evidence_path,
                    detail,
                    _utc_now(),
                ),
            )

    def list_checkins(self, mission_id: str) -> List[dict]:
        with self._connection() as connection:
            rows = connection.execute(
                '''
                SELECT * FROM checkpoint_checkins
                WHERE mission_id = ?
                ORDER BY checkin_id
                ''',
                (mission_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                '''
                CREATE TABLE IF NOT EXISTS missions (
                    mission_id TEXT PRIMARY KEY,
                    route_id TEXT NOT NULL,
                    route_version INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    checkpoint_index INTEGER NOT NULL,
                    checkpoint_total INTEGER NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    retry_count INTEGER NOT NULL,
                    progress REAL NOT NULL,
                    detail TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                '''
            )
            connection.execute(
                '''
                CREATE TABLE IF NOT EXISTS checkpoint_checkins (
                    checkin_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mission_id TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    method TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    marker_type TEXT NOT NULL,
                    marker_id TEXT NOT NULL,
                    confirmation_count INTEGER NOT NULL,
                    evidence_path TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (mission_id) REFERENCES missions(mission_id)
                )
                '''
            )
            connection.execute(
                '''
                CREATE TABLE IF NOT EXISTS mission_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mission_id TEXT NOT NULL,
                    previous_state TEXT NOT NULL,
                    state TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    code TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (mission_id) REFERENCES missions(mission_id)
                )
                '''
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(str(self.database_path))
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
