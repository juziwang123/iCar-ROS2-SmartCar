"""SQLite-backed, versioned storage for validated patrol routes."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional

from .route_schema import RouteDefinition, parse_route, route_to_mapping


class RouteNotFoundError(KeyError):
    """Raised when a route ID/version is not present in the repository."""


class RouteRepository:
    def __init__(self, database_path: str) -> None:
        self.database_path = Path(database_path).expanduser()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def save(self, route: RouteDefinition, *, replace: bool = False) -> None:
        """Persist a validated route; versions are immutable unless replaced explicitly."""
        statement = (
            'INSERT OR REPLACE INTO routes '
            '(route_id, version, map_id, name, loop, definition_json, updated_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)'
            if replace else
            'INSERT INTO routes '
            '(route_id, version, map_id, name, loop, definition_json, updated_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)'
        )
        with self._connection() as connection:
            connection.execute(
                statement,
                (
                    route.route_id,
                    route.version,
                    route.map_id,
                    route.name,
                    int(route.loop),
                    json.dumps(route_to_mapping(route), ensure_ascii=False, sort_keys=True),
                    _utc_now(),
                ),
            )

    def load(self, route_id: str, version: Optional[int] = None) -> RouteDefinition:
        query = (
            'SELECT definition_json FROM routes WHERE route_id = ? ORDER BY version DESC LIMIT 1'
            if version is None else
            'SELECT definition_json FROM routes WHERE route_id = ? AND version = ?'
        )
        arguments = (route_id,) if version is None else (route_id, version)
        with self._connection() as connection:
            row = connection.execute(query, arguments).fetchone()
        if row is None:
            suffix = 'latest' if version is None else f'version {version}'
            raise RouteNotFoundError(f'route {route_id!r} ({suffix}) was not found')
        return parse_route(json.loads(row['definition_json']))

    def list_routes(self, map_id: Optional[str] = None) -> List[dict]:
        query = (
            'SELECT route_id, version, map_id, name, loop, updated_at FROM routes '
            'ORDER BY route_id, version DESC'
        )
        arguments = ()
        if map_id is not None:
            query = (
                'SELECT route_id, version, map_id, name, loop, updated_at FROM routes '
                'WHERE map_id = ? ORDER BY route_id, version DESC'
            )
            arguments = (map_id,)
        with self._connection() as connection:
            rows = connection.execute(query, arguments).fetchall()
        return [dict(row) for row in rows]

    def delete(self, route_id: str, version: Optional[int] = None) -> int:
        query = 'DELETE FROM routes WHERE route_id = ?'
        arguments = (route_id,)
        if version is not None:
            query += ' AND version = ?'
            arguments = (route_id, version)
        with self._connection() as connection:
            cursor = connection.execute(query, arguments)
        return int(cursor.rowcount)

    def import_yaml(self, route_file: str, *, replace: bool = True) -> RouteDefinition:
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError('PyYAML is required to import route YAML files') from exc
        data = yaml.safe_load(Path(route_file).read_text(encoding='utf-8'))
        route = parse_route(data or {})
        self.save(route, replace=replace)
        return route

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                '''
                CREATE TABLE IF NOT EXISTS routes (
                    route_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    map_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    loop INTEGER NOT NULL,
                    definition_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (route_id, version)
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
