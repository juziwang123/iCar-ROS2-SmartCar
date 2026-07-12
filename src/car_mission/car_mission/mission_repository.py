"""Durable mission status and event history storage."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List


TERMINAL_MISSION_STATES = frozenset({'COMPLETED', 'CANCELLED', 'FAILED'})


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

    def record_inspection(
        self,
        mission_id: str,
        *,
        checkpoint_id: str,
        task_id: str,
        task_type: str,
        target: str,
        success: bool,
        conclusion: str,
        confidence: float,
        needs_human_review: bool,
        evidence_paths: List[str],
        detail_json: str,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                '''
                INSERT INTO inspection_results (
                    mission_id, checkpoint_id, task_id, task_type, target, success,
                    conclusion, confidence, needs_human_review, evidence_paths_json,
                    detail_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    mission_id,
                    checkpoint_id,
                    task_id,
                    task_type,
                    target,
                    int(success),
                    conclusion,
                    confidence,
                    int(needs_human_review),
                    json.dumps(evidence_paths, ensure_ascii=False),
                    detail_json,
                    _utc_now(),
                ),
            )

    def list_inspections(self, mission_id: str) -> List[dict]:
        with self._connection() as connection:
            rows = connection.execute(
                '''
                SELECT * FROM inspection_results
                WHERE mission_id = ?
                ORDER BY inspection_id
                ''',
                (mission_id,),
            ).fetchall()
        results = []
        for row in rows:
            result = dict(row)
            result['success'] = bool(result.get('success'))
            result['needs_human_review'] = bool(result.get('needs_human_review'))
            try:
                result['evidence_paths'] = json.loads(result.pop('evidence_paths_json'))
            except (KeyError, TypeError, json.JSONDecodeError):
                result['evidence_paths'] = []
            results.append(result)
        return results

    def get_report(self, mission_id: str) -> dict:
        """Return a transport-safe mission report without exposing evidence content."""
        mission = self.get_mission(mission_id)
        checkins = self.list_checkins(mission_id)
        inspections = self.list_inspections(mission_id)
        conclusion_counts = {}
        for inspection in inspections:
            conclusion = inspection.get('conclusion', 'UNKNOWN')
            conclusion_counts[conclusion] = conclusion_counts.get(conclusion, 0) + 1
        return {
            'mission': mission,
            'summary': {
                'checkin_attempts': len(checkins),
                'checkin_successes': sum(1 for item in checkins if bool(item['success'])),
                'inspection_count': len(inspections),
                'inspection_successes': sum(1 for item in inspections if item['success']),
                'needs_human_review_count': sum(
                    1 for item in inspections if item['needs_human_review']
                ),
                'inspection_conclusions': conclusion_counts,
            },
            'checkins': checkins,
            'inspections': inspections,
            'events': self.list_events(mission_id),
        }

    def recover_incomplete_missions(self, reason: str = 'Mission manager restarted') -> List[dict]:
        """Safely park interrupted work; a process restart never resumes motion."""
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM missions WHERE state NOT IN ('COMPLETED', 'CANCELLED', 'FAILED')"
            ).fetchall()
            now = _utc_now()
            for row in rows:
                detail = f'{reason}; operator must choose retry-current or continue-next'
                connection.execute(
                    """UPDATE missions SET state = ?, detail = ?, updated_at = ? WHERE mission_id = ?""",
                    ('WAITING_OPERATOR', detail, now, row['mission_id']),
                )
                connection.execute(
                    '''INSERT INTO mission_events (
                        mission_id, previous_state, state, checkpoint_id, code, detail, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (
                        row['mission_id'], row['state'], 'WAITING_OPERATOR', row['checkpoint_id'],
                        'PROCESS_RESTART_RECOVERY', detail, now,
                    ),
                )
        return [dict(row) for row in rows]

    def list_recoverable_missions(self) -> List[dict]:
        """Return parked process-restart missions and safe explicit restart indexes."""
        with self._connection() as connection:
            rows = connection.execute(
                '''SELECT m.* FROM missions m WHERE m.state = 'WAITING_OPERATOR'
                   AND EXISTS (
                     SELECT 1 FROM mission_events e WHERE e.mission_id = m.mission_id
                     AND e.code = 'PROCESS_RESTART_RECOVERY'
                   ) ORDER BY m.updated_at DESC'''
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item['retry_current_checkpoint_index'] = item['checkpoint_index']
            item['continue_next_checkpoint_index'] = min(
                item['checkpoint_index'] + 1, item['checkpoint_total']
            )
            result.append(item)
        return result

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
                CREATE TABLE IF NOT EXISTS inspection_results (
                    inspection_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mission_id TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    target TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    conclusion TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    needs_human_review INTEGER NOT NULL,
                    evidence_paths_json TEXT NOT NULL,
                    detail_json TEXT NOT NULL,
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
