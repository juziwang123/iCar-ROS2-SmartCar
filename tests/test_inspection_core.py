from pathlib import Path
import sys
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / 'src' / 'car_inspection'
sys.path.insert(0, str(PACKAGE_ROOT))

from car_inspection.image_capture import ImageBuffer
from car_inspection.inspection_schema import (
    InspectionSchemaError,
    fuse_observations,
    local_observation_from_payload,
    parse_vlm_review,
)
from car_inspection.vlm_client import VlmClient


class TestInspectionSchema(unittest.TestCase):
    def test_stamped_local_detection_can_confirm_presence(self):
        observation = local_observation_from_payload(
            {
                'model': 'fire_safety.onnx',
                'detections': [
                    {'label': 'fire_extinguisher', 'confidence': 0.91},
                    {'label': 'person', 'confidence': 0.99},
                ],
            },
            target='fire_extinguisher',
            confidence_threshold=0.70,
            allow_absent=False,
        )
        decision = fuse_observations(observation, None)
        self.assertEqual(observation.status, 'PRESENT')
        self.assertEqual(decision.conclusion, 'PRESENT')
        self.assertEqual(decision.source, 'local_model')

    def test_local_negative_is_unknown_until_operator_validates_absence(self):
        payload = {'model': 'fire_safety.onnx', 'detections': []}
        conservative = local_observation_from_payload(
            payload, target='fire_extinguisher', confidence_threshold=0.70, allow_absent=False
        )
        allowed = local_observation_from_payload(
            payload, target='fire_extinguisher', confidence_threshold=0.70, allow_absent=True
        )
        self.assertEqual(fuse_observations(conservative, None).conclusion, 'UNKNOWN')
        self.assertEqual(fuse_observations(allowed, None).conclusion, 'ABSENT')

    def test_unexpected_model_cannot_supply_a_presence_decision(self):
        observation = local_observation_from_payload(
            {
                'model': 'general_coco.onnx',
                'detections': [{'label': 'fire_extinguisher', 'confidence': 0.99}],
            },
            target='fire_extinguisher',
            confidence_threshold=0.70,
            allow_absent=False,
            expected_model='site_fire_safety.onnx',
        )
        self.assertEqual(observation.status, 'UNAVAILABLE')
        self.assertEqual(fuse_observations(observation, None).conclusion, 'UNKNOWN')

    def test_vlm_review_is_strict_and_can_resolve_a_local_unknown(self):
        local = local_observation_from_payload(
            {'error': 'model unavailable', 'detections': []},
            target='fire_extinguisher',
            confidence_threshold=0.70,
            allow_absent=False,
        )
        review = parse_vlm_review({
            'task': 'visual_presence',
            'present': True,
            'confidence': 0.88,
            'condition': 'normal',
            'reason': 'target is visible beside the door',
            'needs_human_review': False,
        }, 'visual_presence')
        decision = fuse_observations(local, review)
        self.assertEqual(decision.conclusion, 'PRESENT')
        self.assertEqual(decision.source, 'vlm')
        with self.assertRaises(InspectionSchemaError):
            parse_vlm_review({
                'task': 'wrong_task',
                'present': True,
                'confidence': 1.1,
                'condition': 'normal',
                'reason': 'bad',
                'needs_human_review': False,
            }, 'visual_presence')

    def test_human_review_is_never_silently_promoted_to_present(self):
        local = local_observation_from_payload(
            {'detections': []}, target='target', confidence_threshold=0.7, allow_absent=False
        )
        review = parse_vlm_review({
            'task': 'visual_presence',
            'present': True,
            'confidence': 0.55,
            'condition': 'normal',
            'reason': 'partially occluded',
            'needs_human_review': True,
        }, 'visual_presence')
        decision = fuse_observations(local, review)
        self.assertEqual(decision.conclusion, 'NEEDS_HUMAN_REVIEW')
        self.assertTrue(decision.needs_human_review)


class TestCaptureAndVlmAdapter(unittest.TestCase):
    def test_image_buffer_only_returns_frames_after_action_start(self):
        buffer = ImageBuffer(2)
        buffer.append((1, 0), 1.0, 'old')
        start = buffer.sequence
        buffer.append((2, 0), 2.0, 'first')
        buffer.append((3, 0), 3.0, 'second')
        self.assertEqual([frame.image for frame in buffer.after(start)], ['first', 'second'])

    def test_disabled_vlm_makes_no_network_request(self):
        attempt = VlmClient('', 5.0).review(
            task='visual_presence', target='fire_extinguisher', image_bytes=b'jpeg'
        )
        self.assertIsNone(attempt.review)
        self.assertEqual(attempt.error, 'VLM_DISABLED')


if __name__ == '__main__':
    unittest.main()
