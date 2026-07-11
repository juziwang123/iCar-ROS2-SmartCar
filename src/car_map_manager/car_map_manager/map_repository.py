"""Safe map metadata storage and static route-to-map validation."""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


_MAP_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')


class MapRepositoryError(ValueError):
    """Raised when managed map data is malformed or outside the managed root."""


class MapNotFoundError(KeyError):
    """Raised when a requested managed map does not exist."""


class MapRepository:
    def __init__(self, maps_root: str) -> None:
        self.maps_root = Path(maps_root).expanduser().resolve()
        self.maps_root.mkdir(parents=True, exist_ok=True)

    def create_map_id(self, name: str) -> str:
        normalized = re.sub(r'[^A-Za-z0-9_-]+', '_', name.strip()).strip('_-')
        if not normalized:
            normalized = 'map'
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        # A timestamp alone can collide when an operator saves the same named
        # map twice in one second.  Keep IDs human-readable while making the
        # suffix independent of the wall-clock resolution.
        digest = uuid.uuid4().hex[:8]
        return f'{normalized[:40]}_{timestamp}_{digest}'

    def prepare_save_location(self, map_id: str) -> Path:
        directory = self._map_directory(map_id)
        if directory.exists():
            raise MapRepositoryError(f'map_id already exists: {map_id}')
        directory.mkdir(parents=True)
        return directory / 'map'

    def register_saved_map(self, map_id: str, name: str, map_base_path: str) -> Dict[str, Any]:
        """Write a manifest after Nav2 has produced ``map.yaml`` and its image."""
        directory = self._map_directory(map_id)
        base_path = Path(map_base_path).resolve()
        if base_path.parent != directory:
            raise MapRepositoryError('map_base_path must stay inside the managed map directory')
        yaml_path = base_path.with_suffix('.yaml')
        if not yaml_path.is_file():
            raise MapRepositoryError(f'map saver did not create {yaml_path.name}')

        metadata = self._load_yaml_metadata(yaml_path)
        image_value = metadata.get('image')
        if not isinstance(image_value, str) or not image_value.strip():
            raise MapRepositoryError('saved map YAML has no image field')
        image_path = (yaml_path.parent / image_value).resolve()
        self._require_within_root(image_path)
        if image_path.parent != directory:
            raise MapRepositoryError('saved map image must stay in its map directory')
        if not image_path.is_file():
            raise MapRepositoryError(f'saved map image does not exist: {image_value}')
        width, height, _ = _read_pgm(image_path)

        manifest = {
            'map_id': map_id,
            'name': _nonempty_string(name, 'name'),
            'created_at': datetime.now(timezone.utc).isoformat(),
            'yaml_file': yaml_path.name,
            'image_file': image_path.name,
            'resolution': _positive_float(metadata.get('resolution'), 'resolution'),
            'origin': _origin(metadata.get('origin')),
            'occupied_thresh': _probability(metadata.get('occupied_thresh'), 'occupied_thresh'),
            'free_thresh': _probability(metadata.get('free_thresh'), 'free_thresh'),
            'width': width,
            'height': height,
            'sha256': {
                'yaml': _sha256(yaml_path),
                'image': _sha256(image_path),
            },
        }
        manifest_path = directory / 'manifest.json'
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8'
        )
        return manifest

    def list_maps(self) -> List[Dict[str, Any]]:
        maps: List[Dict[str, Any]] = []
        for manifest_path in sorted(self.maps_root.glob('*/manifest.json')):
            try:
                maps.append(self._load_manifest(manifest_path.parent.name))
            except (MapNotFoundError, MapRepositoryError):
                continue
        return sorted(maps, key=lambda item: item.get('created_at', ''), reverse=True)

    def get_map(self, map_id: str) -> Dict[str, Any]:
        return self._load_manifest(map_id)

    def validate_route(self, route) -> Dict[str, Any]:
        """Check each route checkpoint against the saved occupancy grid.

        This is static validation only. Runtime path feasibility remains Nav2's
        responsibility once localization and dynamic obstacles are available.
        """
        manifest = self.get_map(route.map_id)
        image_path = self._managed_map_file(route.map_id, manifest['image_file'], 'image_file')
        if not image_path.is_file():
            raise MapRepositoryError('managed map image no longer exists')
        width, height, pixels = _read_pgm(image_path)
        if width != int(manifest['width']) or height != int(manifest['height']):
            raise MapRepositoryError('map image dimensions no longer match manifest')

        errors: List[Dict[str, Any]] = []
        resolution = float(manifest['resolution'])
        origin_x, origin_y, origin_yaw = manifest['origin']
        occupied_limit = int(round(255.0 * (1.0 - float(manifest['occupied_thresh']))))
        for checkpoint in route.checkpoints:
            local_x, local_y = _inverse_origin_rotation(
                checkpoint.pose.x - origin_x,
                checkpoint.pose.y - origin_y,
                origin_yaw,
            )
            column = int(math.floor(local_x / resolution))
            row_from_bottom = int(math.floor(local_y / resolution))
            row = height - 1 - row_from_bottom
            if column < 0 or column >= width or row < 0 or row >= height:
                errors.append({
                    'checkpoint_id': checkpoint.checkpoint_id,
                    'code': 'OUTSIDE_MAP',
                    'message': 'checkpoint is outside the saved map bounds',
                })
                continue
            pixel = pixels[row * width + column]
            if pixel == 205:
                errors.append({
                    'checkpoint_id': checkpoint.checkpoint_id,
                    'code': 'UNKNOWN_CELL',
                    'message': 'checkpoint is in an unknown map cell',
                })
            elif pixel <= occupied_limit:
                errors.append({
                    'checkpoint_id': checkpoint.checkpoint_id,
                    'code': 'OCCUPIED_CELL',
                    'message': 'checkpoint is in an occupied map cell',
                })

        return {
            'valid': not errors,
            'map_id': route.map_id,
            'static_validation': True,
            'runtime_path_validation_required': True,
            'errors': errors,
        }

    def _load_manifest(self, map_id: str) -> Dict[str, Any]:
        directory = self._map_directory(map_id)
        manifest_path = directory / 'manifest.json'
        if not manifest_path.is_file():
            raise MapNotFoundError(f'map {map_id!r} was not found')
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise MapRepositoryError(f'could not read manifest for {map_id!r}') from exc
        if not isinstance(manifest, dict) or manifest.get('map_id') != map_id:
            raise MapRepositoryError(f'invalid manifest for {map_id!r}')
        # Manifests are persisted data and should be treated as untrusted on
        # reload.  Normalizing them here prevents a corrupted file from
        # becoming a path traversal or a division-by-zero during validation.
        normalized = dict(manifest)
        normalized['yaml_file'] = _filename(normalized.get('yaml_file'), 'yaml_file')
        normalized['image_file'] = _filename(normalized.get('image_file'), 'image_file')
        normalized['resolution'] = _positive_float(normalized.get('resolution'), 'resolution')
        normalized['origin'] = _origin(normalized.get('origin'))
        normalized['occupied_thresh'] = _probability(
            normalized.get('occupied_thresh'), 'occupied_thresh'
        )
        normalized['free_thresh'] = _probability(normalized.get('free_thresh'), 'free_thresh')
        normalized['width'] = _positive_integer(normalized.get('width'), 'width')
        normalized['height'] = _positive_integer(normalized.get('height'), 'height')
        self._managed_map_file(map_id, normalized['yaml_file'], 'yaml_file')
        self._managed_map_file(map_id, normalized['image_file'], 'image_file')
        return normalized

    def _map_directory(self, map_id: str) -> Path:
        if not isinstance(map_id, str) or not _MAP_ID.fullmatch(map_id):
            raise MapRepositoryError('map_id must contain only letters, digits, underscore, and hyphen')
        directory = (self.maps_root / map_id).resolve()
        self._require_within_root(directory)
        return directory

    def _require_within_root(self, path: Path) -> None:
        try:
            path.relative_to(self.maps_root)
        except ValueError as exc:
            raise MapRepositoryError('path must stay inside maps_root') from exc

    def _managed_map_file(self, map_id: str, filename: str, field: str) -> Path:
        directory = self._map_directory(map_id)
        path = (directory / _filename(filename, field)).resolve()
        if path.parent != directory:
            raise MapRepositoryError(f'{field} must stay in its map directory')
        return path

    @staticmethod
    def _load_yaml_metadata(yaml_path: Path) -> Dict[str, Any]:
        try:
            import yaml
        except ImportError as exc:
            raise MapRepositoryError('PyYAML is required to register saved maps') from exc
        try:
            data = yaml.safe_load(yaml_path.read_text(encoding='utf-8'))
        except (OSError, yaml.YAMLError) as exc:
            raise MapRepositoryError(f'could not parse {yaml_path.name}') from exc
        if not isinstance(data, dict):
            raise MapRepositoryError('map YAML must be an object')
        return data


def _read_pgm(path: Path) -> Tuple[int, int, bytes]:
    data = path.read_bytes()
    position = 0

    def token() -> bytes:
        nonlocal position
        while position < len(data) and data[position] in b' \t\r\n':
            position += 1
        while position < len(data) and data[position] == ord('#'):
            while position < len(data) and data[position] not in b'\r\n':
                position += 1
            while position < len(data) and data[position] in b' \t\r\n':
                position += 1
        start = position
        while position < len(data) and data[position] not in b' \t\r\n':
            position += 1
        return data[start:position]

    magic = token()
    if magic not in {b'P2', b'P5'}:
        raise MapRepositoryError('only P2/P5 PGM map images are supported')
    try:
        width = int(token())
        height = int(token())
        maximum = int(token())
    except ValueError as exc:
        raise MapRepositoryError('invalid PGM header') from exc
    if width <= 0 or height <= 0 or maximum != 255:
        raise MapRepositoryError('only 8-bit PGM map images are supported')
    if magic == b'P2':
        values = []
        while True:
            item = token()
            if not item:
                break
            try:
                value = int(item)
            except ValueError as exc:
                raise MapRepositoryError('invalid P2 PGM pixel value') from exc
            if value < 0 or value > 255:
                raise MapRepositoryError('P2 PGM pixel value is outside 0..255')
            values.append(value)
        if len(values) != width * height:
            raise MapRepositoryError('P2 PGM pixel count does not match dimensions')
        return width, height, bytes(values)

    if position >= len(data) or data[position] not in b' \t\r\n':
        raise MapRepositoryError('P5 PGM header is missing a pixel separator')
    if data[position:position + 2] == b'\r\n':
        position += 2
    else:
        position += 1
    pixels = data[position:]
    if len(pixels) != width * height:
        raise MapRepositoryError('P5 PGM pixel count does not match dimensions')
    return width, height, pixels


def _inverse_origin_rotation(x: float, y: float, yaw: float) -> Tuple[float, float]:
    cosine = math.cos(yaw)
    sine = math.sin(yaw)
    return cosine * x + sine * y, -sine * x + cosine * y


def _origin(value: Any) -> List[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise MapRepositoryError('origin must contain exactly three numbers')
    return [_finite_float(item, 'origin') for item in value]


def _finite_float(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise MapRepositoryError(f'{field} must be a finite number')
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise MapRepositoryError(f'{field} must be a finite number') from exc
    if not math.isfinite(result):
        raise MapRepositoryError(f'{field} must be a finite number')
    return result


def _probability(value: Any, field: str) -> float:
    result = _finite_float(value, field)
    if result < 0.0 or result > 1.0:
        raise MapRepositoryError(f'{field} must be between zero and one')
    return result


def _positive_float(value: Any, field: str) -> float:
    result = _finite_float(value, field)
    if result <= 0.0:
        raise MapRepositoryError(f'{field} must be greater than zero')
    return result


def _positive_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MapRepositoryError(f'{field} must be a positive integer')
    return value


def _filename(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MapRepositoryError(f'{field} must be a non-empty filename')
    filename = value.strip()
    if filename in {'.', '..'} or '/' in filename or '\\' in filename:
        raise MapRepositoryError(f'{field} must be a filename without a path')
    return filename


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MapRepositoryError(f'{field} must be a non-empty string')
    return value.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()
