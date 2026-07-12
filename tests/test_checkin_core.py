import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(ROOT / 'car_inspection'))

from car_inspection.checkin_logic import (
    GeofencePolicy,
    MarkerConfirmationTracker,
    MotionSnapshot,
    PoseSnapshot,
    evaluate_geofence,
)
from car_inspection.evidence_store import EvidenceStore, EvidenceStoreError
from car_inspection.marker_protocol import (
    MarkerDetection,
    MarkerProtocolError,
    encode_markers,
    parse_markers,
)


def policy():
    return GeofencePolicy(
        target_x=1.0,
        target_y=2.0,
        target_yaw=0.0,
        position_tolerance_m=0.3,
        yaw_tolerance_rad=0.35,
        max_pose_covariance=0.25,
        max_linear_speed_mps=0.02,
        max_angular_speed_rps=0.03,
        pose_max_age_sec=1.0,
        motion_max_age_sec=0.5,
    )


class TestGeofenceLogic(unittest.TestCase):
    def test_fresh_still_pose_inside_fence_passes(self):
        verdict = evaluate_geofence(
            policy(),
            PoseSnapshot(1.1, 2.0, 0.1, 0.1, 0.1, 0.2, 10.0),
            MotionSnapshot(0.0, 0.01, 10.0),
            10.2,
        )
        self.assertTrue(verdict.passed)
        self.assertAlmostEqual(verdict.distance_m, 0.1)

    def test_geofence_rejects_stale_pose_high_covariance_and_motion(self):
        verdict = evaluate_geofence(
            policy(),
            PoseSnapshot(1.5, 2.0, 1.0, 0.5, 0.1, 0.1, 1.0),
            MotionSnapshot(0.1, 0.0, 2.0),
            3.0,
        )
        self.assertFalse(verdict.passed)
        self.assertIn('POSE_STALE', verdict.reasons)
        self.assertIn('POSITION_OUTSIDE_FENCE', verdict.reasons)
        self.assertIn('YAW_OUTSIDE_FENCE', verdict.reasons)
        self.assertIn('POSE_COVARIANCE_HIGH', verdict.reasons)
        self.assertIn('MOTION_STALE', verdict.reasons)

    def test_marker_confirmation_requires_distinct_consecutive_frames(self):
        tracker = MarkerConfirmationTracker('qr', 'ICAR:CP-01', 2)
        self.assertFalse(tracker.observe('qr', 'ICAR:CP-01', 1))
        self.assertFalse(tracker.observe('qr', 'ICAR:CP-01', 1))
        self.assertEqual(tracker.count, 1)
        self.assertFalse(tracker.observe('qr', 'WRONG', 2))
        self.assertEqual(tracker.count, 0)
        self.assertFalse(tracker.observe('qr', 'ICAR:CP-01', 3))
        self.assertTrue(tracker.observe('qr', 'ICAR:CP-01', 4))


class TestMarkerProtocol(unittest.TestCase):
    def test_marker_payload_round_trip(self):
        payload = encode_markers(
            [MarkerDetection('qr', 'ICAR:CP-01', ((1.0, 2.0), (3.0, 4.0)))],
            stamp_sec=1,
            stamp_nanosec=2,
            frame_id='camera_color_optical_frame',
        )
        markers = parse_markers(payload)
        self.assertEqual(markers[0].marker_type, 'qr')
        self.assertEqual(markers[0].marker_id, 'ICAR:CP-01')
        self.assertEqual(markers[0].polygon[1], (3.0, 4.0))

    def test_marker_payload_rejects_nonfinite_coordinates(self):
        payload = json.dumps({
            'stamp': {'sec': 1, 'nanosec': 0},
            'markers': [{'type': 'qr', 'id': 'x', 'polygon': [[float('nan'), 1]]}],
        })
        with self.assertRaises(MarkerProtocolError):
            parse_markers(payload)

    def test_marker_payload_requires_timestamp_for_image_evidence_binding(self):
        payload = json.dumps({'markers': [{'type': 'qr', 'id': 'x', 'polygon': []}]})
        with self.assertRaises(MarkerProtocolError):
            parse_markers(payload)


class TestEvidenceStore(unittest.TestCase):
    def test_evidence_is_written_with_integrity_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EvidenceStore(directory)
            record = store.store_bytes(
                mission_id='mission_01',
                checkpoint_id='CP-01',
                kind='checkin_marker',
                content=b'jpeg-evidence',
                extension='jpg',
                metadata={'marker_id': 'ICAR:CP-01'},
            )
            self.assertTrue(Path(record['path']).is_file())
            metadata = json.loads(Path(record['metadata_path']).read_text(encoding='utf-8'))
            self.assertEqual(metadata['sha256'], record['sha256'])
            self.assertEqual(metadata['metadata']['marker_id'], 'ICAR:CP-01')

    def test_evidence_rejects_path_traversal_identifiers(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EvidenceStore(directory)
            with self.assertRaises(EvidenceStoreError):
                store.store_bytes(
                    mission_id='../escape',
                    checkpoint_id='CP-01',
                    kind='checkin',
                    content=b'x',
                    extension='jpg',
                    metadata={},
                )


if __name__ == '__main__':
    unittest.main()
