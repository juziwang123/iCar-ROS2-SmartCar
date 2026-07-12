from pathlib import Path
import sys
import tempfile
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / 'src' / 'car_mission'
sys.path.insert(0, str(PACKAGE_ROOT))

from car_mission.mission_repository import MissionRepository
from car_mission.route_repository import RouteNotFoundError, RouteRepository
from car_mission.route_schema import RouteValidationError, parse_route
from car_mission.state_machine import InvalidTransition, MissionState, MissionStateMachine


def sample_route():
    return {
        'schema_version': 1,
        'route_id': 'lab_route',
        'map_id': 'lab_map',
        'name': 'Lab route',
        'version': 2,
        'loop': False,
        'checkpoints': [
            {
                'checkpoint_id': 'CP-01',
                'sequence': 1,
                'name': 'Start',
                'type': 'checkin',
                'pose': {'frame_id': 'map', 'x': 1.0, 'y': 0.0, 'yaw': 0.0},
                'arrival': {
                    'position_tolerance_m': 0.3,
                    'yaw_tolerance_rad': 0.35,
                    'dwell_sec': 0.0,
                },
                'tasks': [],
                'failure_policy': {'navigation': 'retry_then_wait_operator'},
            },
            {
                'checkpoint_id': 'CP-02',
                'sequence': 2,
                'name': 'End',
                'type': 'transit',
                'pose': {'frame_id': 'map', 'x': 2.0, 'y': 0.0, 'yaw': 0.0},
                'arrival': {
                    'position_tolerance_m': 0.3,
                    'yaw_tolerance_rad': 0.35,
                    'dwell_sec': 0.0,
                },
                'tasks': [],
                'failure_policy': {'navigation': 'retry_then_skip'},
            },
        ],
    }


class TestRouteSchema(unittest.TestCase):
    def test_valid_route_is_normalized(self):
        route = parse_route(sample_route())
        self.assertEqual(route.route_id, 'lab_route')
        self.assertEqual(route.version, 2)
        self.assertEqual(len(route.checkpoints), 2)
        self.assertEqual(route.checkpoints[1].navigation_failure_policy, 'retry_then_skip')

    def test_duplicate_checkpoint_id_is_rejected(self):
        data = sample_route()
        data['checkpoints'][1]['checkpoint_id'] = 'CP-01'
        with self.assertRaises(RouteValidationError):
            parse_route(data)

    def test_non_finite_pose_is_rejected(self):
        data = sample_route()
        data['checkpoints'][0]['pose']['x'] = float('nan')
        with self.assertRaises(RouteValidationError):
            parse_route(data)

    def test_non_continuous_sequence_is_rejected(self):
        data = sample_route()
        data['checkpoints'][1]['sequence'] = 3
        with self.assertRaises(RouteValidationError):
            parse_route(data)

    def test_visual_marker_checkin_is_normalized(self):
        data = sample_route()
        data['checkpoints'][0]['checkin'] = {
            'method': 'visual_marker',
            'marker_type': 'qr',
            'expected_marker_id': 'ICAR:CP-01',
            'timeout_sec': 8.0,
            'retries': 1,
            'confirmation_frames': 2,
        }
        data['checkpoints'][0]['failure_policy']['checkin'] = 'retry_then_wait_operator'
        route = parse_route(data)
        checkin = route.checkpoints[0].checkin
        self.assertEqual(checkin.method, 'visual_marker')
        self.assertEqual(checkin.expected_marker_id, 'ICAR:CP-01')
        self.assertEqual(route.checkpoints[0].checkin_failure_policy, 'retry_then_wait_operator')

    def test_visual_marker_requires_expected_id(self):
        data = sample_route()
        data['checkpoints'][0]['checkin'] = {
            'method': 'visual_marker',
            'marker_type': 'qr',
        }
        with self.assertRaises(RouteValidationError):
            parse_route(data)

    def test_inspection_task_is_normalized_and_uses_required_task_policy(self):
        data = sample_route()
        data['checkpoints'][0]['tasks'] = [{
            'task_id': 'CP-01-T01',
            'type': 'visual_presence',
            'target': 'fire_extinguisher',
            'required': True,
            'capture_count': 3,
            'local_model': 'fire_safety.onnx',
            'use_vlm_fallback': True,
            'confidence_threshold': 0.70,
        }]
        data['checkpoints'][0]['failure_policy']['required_task'] = 'wait_operator'
        route = parse_route(data)
        task = route.checkpoints[0].tasks[0]
        self.assertEqual(task.task_id, 'CP-01-T01')
        self.assertEqual(task.capture_count, 3)
        self.assertTrue(task.use_vlm_fallback)
        self.assertEqual(route.checkpoints[0].required_task_failure_policy, 'wait_operator')

    def test_inspection_task_rejects_unknown_type(self):
        data = sample_route()
        data['checkpoints'][0]['tasks'] = [{
            'task_id': 'CP-01-T01',
            'type': 'arbitrary_shell_command',
            'target': 'fire_extinguisher',
        }]
        with self.assertRaises(RouteValidationError):
            parse_route(data)


class TestMissionStateMachine(unittest.TestCase):
    def test_happy_path_reaches_completed(self):
        machine = MissionStateMachine()
        for state in (
            MissionState.PREPARING,
            MissionState.LOCALIZING,
            MissionState.NAVIGATING,
            MissionState.ARRIVAL_CONFIRMING,
            MissionState.CHECKING_IN,
            MissionState.CAPTURING,
            MissionState.INSPECTING,
            MissionState.RECORDING,
            MissionState.COMPLETED,
        ):
            machine.transition(state)
        self.assertTrue(machine.terminal)
        self.assertEqual(machine.state, MissionState.COMPLETED)

    def test_unsafe_transition_is_rejected(self):
        machine = MissionStateMachine()
        with self.assertRaises(InvalidTransition):
            machine.transition(MissionState.NAVIGATING)

    def test_pause_and_resume_returns_to_navigation(self):
        machine = MissionStateMachine()
        for state in (MissionState.PREPARING, MissionState.LOCALIZING, MissionState.NAVIGATING):
            machine.transition(state)
        machine.transition(MissionState.PAUSING)
        machine.transition(MissionState.PAUSED)
        machine.transition(MissionState.NAVIGATING)
        self.assertEqual(machine.state, MissionState.NAVIGATING)

    def test_all_skipped_route_can_complete_from_navigation(self):
        machine = MissionStateMachine()
        for state in (MissionState.PREPARING, MissionState.LOCALIZING, MissionState.NAVIGATING):
            machine.transition(state)
        machine.transition(MissionState.COMPLETED)
        self.assertTrue(machine.terminal)


class TestRepositories(unittest.TestCase):
    def test_route_versions_and_mission_events_are_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / 'icar.db')
            route = parse_route(sample_route())
            routes = RouteRepository(database)
            routes.save(route)
            self.assertEqual(routes.load('lab_route').version, 2)
            with self.assertRaises(RouteNotFoundError):
                routes.load('missing_route')

            newer_route_data = sample_route()
            newer_route_data['version'] = 3
            routes.save(parse_route(newer_route_data))
            self.assertEqual(routes.load('lab_route').version, 3)
            self.assertEqual(routes.delete('lab_route', 2), 1)
            self.assertEqual(routes.load('lab_route').version, 3)

            missions = MissionRepository(database)
            missions.create_mission('mission-1', 'lab_route', 2, 'PREPARING', 2)
            missions.update_status(
                'mission-1',
                state='NAVIGATING',
                checkpoint_index=0,
                checkpoint_total=2,
                checkpoint_id='CP-01',
                retry_count=1,
                progress=0.0,
                detail='goal sent',
            )
            missions.append_event(
                'mission-1',
                previous_state='PREPARING',
                state='NAVIGATING',
                checkpoint_id='CP-01',
                code='NAV_GOAL_SENT',
                detail='goal sent',
            )
            mission = missions.get_mission('mission-1')
            self.assertEqual(mission['state'], 'NAVIGATING')
            self.assertEqual(mission['retry_count'], 1)
            self.assertEqual(missions.list_events('mission-1')[0]['code'], 'NAV_GOAL_SENT')
            missions.record_checkin(
                'mission-1',
                checkpoint_id='CP-01',
                attempt=1,
                method='visual_marker',
                outcome='VISUAL_MARKER_VERIFIED',
                success=True,
                marker_type='qr',
                marker_id='ICAR:CP-01',
                confirmation_count=2,
                evidence_path='/tmp/evidence.jpg',
                detail='verified',
            )
            self.assertEqual(missions.list_checkins('mission-1')[0]['marker_id'], 'ICAR:CP-01')
            missions.record_inspection(
                'mission-1',
                checkpoint_id='CP-01',
                task_id='CP-01-T01',
                task_type='visual_presence',
                target='fire_extinguisher',
                success=True,
                conclusion='PRESENT',
                confidence=0.92,
                needs_human_review=False,
                evidence_paths=['/tmp/capture.jpg'],
                detail_json='{"source":"local_model"}',
            )
            self.assertEqual(missions.list_inspections('mission-1')[0]['conclusion'], 'PRESENT')
            self.assertEqual(missions.list_inspections('mission-1')[0]['evidence_paths'], ['/tmp/capture.jpg'])
            report = missions.get_report('mission-1')
            self.assertEqual(report['summary']['checkin_successes'], 1)
            self.assertEqual(report['summary']['inspection_conclusions'], {'PRESENT': 1})
            self.assertFalse(report['inspections'][0]['needs_human_review'])
            self.assertEqual(routes.delete('lab_route'), 1)
            with self.assertRaises(RouteNotFoundError):
                routes.load('lab_route')


if __name__ == '__main__':
    unittest.main()
