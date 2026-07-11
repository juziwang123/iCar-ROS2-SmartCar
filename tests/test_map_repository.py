import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(ROOT / 'car_map_manager'))
sys.path.insert(0, str(ROOT / 'car_mission'))

from car_map_manager.map_repository import MapRepository, MapRepositoryError, _read_pgm
from car_mission.route_schema import parse_route


def _route(x, y):
    return parse_route({
        'schema_version': 1,
        'route_id': 'unit_route',
        'map_id': 'unit_map',
        'name': 'Unit route',
        'version': 1,
        'loop': False,
        'checkpoints': [{
            'checkpoint_id': 'CP-01',
            'sequence': 1,
            'name': 'Checkpoint',
            'type': 'transit',
            'pose': {'frame_id': 'map', 'x': x, 'y': y, 'yaw': 0.0},
            'arrival': {
                'position_tolerance_m': 0.3,
                'yaw_tolerance_rad': 0.35,
                'dwell_sec': 0.0,
            },
            'tasks': [],
            'failure_policy': {'navigation': 'retry_then_wait_operator'},
        }],
    })


class TestMapRepository(unittest.TestCase):
    def _make_repository(self, directory):
        root = Path(directory) / 'maps'
        map_dir = root / 'unit_map'
        map_dir.mkdir(parents=True)
        # P5 raster rows are stored top-to-bottom.  The bottom row contains
        # free, occupied and unknown cells respectively, making map/world
        # conversion testable without ROS.
        (map_dir / 'map.pgm').write_bytes(
            b'P5\n3 2\n255\n' + bytes([254, 254, 254, 254, 0, 205])
        )
        (map_dir / 'manifest.json').write_text(json.dumps({
            'map_id': 'unit_map',
            'name': 'Unit map',
            'created_at': '2026-07-11T00:00:00+00:00',
            'yaml_file': 'map.yaml',
            'image_file': 'map.pgm',
            'resolution': 1.0,
            'origin': [0.0, 0.0, 0.0],
            'occupied_thresh': 0.65,
            'free_thresh': 0.25,
            'width': 3,
            'height': 2,
            'sha256': {},
        }), encoding='utf-8')
        return MapRepository(str(root))

    def test_p5_reader_keeps_the_first_binary_pixel(self):
        with tempfile.TemporaryDirectory() as directory:
            pgm = Path(directory) / 'map.pgm'
            pgm.write_bytes(b'P5\n2 1\n255\n' + bytes([254, 0]))
            self.assertEqual(_read_pgm(pgm), (2, 1, bytes([254, 0])))

    def test_static_route_validation_accepts_free_cell(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = self._make_repository(directory)
            result = repository.validate_route(_route(0.5, 0.5))

            self.assertTrue(result['valid'])
            self.assertTrue(result['static_validation'])
            self.assertTrue(result['runtime_path_validation_required'])

    def test_static_route_validation_rejects_occupied_unknown_and_outside(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = self._make_repository(directory)
            cases = ((1.5, 0.5, 'OCCUPIED_CELL'), (2.5, 0.5, 'UNKNOWN_CELL'), (3.5, 0.5, 'OUTSIDE_MAP'))
            for x, y, error_code in cases:
                with self.subTest(error_code=error_code):
                    result = repository.validate_route(_route(x, y))
                    self.assertFalse(result['valid'])
                    self.assertEqual(result['errors'][0]['code'], error_code)

    def test_map_id_generation_is_not_limited_to_one_save_per_second(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = MapRepository(str(Path(directory) / 'maps'))
            self.assertNotEqual(repository.create_map_id('same name'), repository.create_map_id('same name'))

    def test_manifest_cannot_escape_its_managed_map_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = self._make_repository(directory)
            manifest_path = Path(directory) / 'maps' / 'unit_map' / 'manifest.json'
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            manifest['image_file'] = '../other_map/map.pgm'
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')

            with self.assertRaises(MapRepositoryError):
                repository.get_map('unit_map')


if __name__ == '__main__':
    unittest.main()
