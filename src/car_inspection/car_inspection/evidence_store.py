"""Managed, integrity-tagged evidence files for completed check-ins."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


_IDENTIFIER = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$')
_EXTENSION = re.compile(r'^[a-z0-9]{1,12}$')


class EvidenceStoreError(ValueError):
    """An evidence write did not satisfy managed-storage restrictions."""


class EvidenceStore:
    def __init__(self, root: str) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def store_bytes(
        self,
        *,
        mission_id: str,
        checkpoint_id: str,
        kind: str,
        content: bytes,
        extension: str,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        mission = _identifier(mission_id, 'mission_id')
        checkpoint = _identifier(checkpoint_id, 'checkpoint_id')
        file_kind = _identifier(kind, 'kind')
        if not isinstance(content, bytes) or not content:
            raise EvidenceStoreError('content must be non-empty bytes')
        suffix = extension.strip().lower().lstrip('.') if isinstance(extension, str) else ''
        if not _EXTENSION.fullmatch(suffix):
            raise EvidenceStoreError('extension must contain only lower-case letters and digits')

        directory = (self.root / mission / checkpoint).resolve()
        self._require_within_root(directory)
        directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
        basename = f'{file_kind}_{timestamp}_{uuid.uuid4().hex[:8]}'
        data_path = directory / f'{basename}.{suffix}'
        digest = hashlib.sha256(content).hexdigest()
        data_path.write_bytes(content)
        record = {
            'mission_id': mission,
            'checkpoint_id': checkpoint,
            'kind': file_kind,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'filename': data_path.name,
            'sha256': digest,
            'size_bytes': len(content),
            'metadata': metadata,
        }
        metadata_path = directory / f'{basename}.json'
        metadata_path.write_text(
            json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2), encoding='utf-8'
        )
        return {
            **record,
            'path': str(data_path),
            'metadata_path': str(metadata_path),
        }

    def _require_within_root(self, path: Path) -> None:
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise EvidenceStoreError('evidence path must remain inside evidence root') from exc


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise EvidenceStoreError(f'{field} must contain only letters, digits, underscore, and hyphen')
    return value
