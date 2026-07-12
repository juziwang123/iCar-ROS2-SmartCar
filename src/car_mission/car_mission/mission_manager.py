"""Action-driven, persistent Nav2 patrol mission manager with P3 check-ins."""

from __future__ import annotations

import math
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Optional, Sequence

import rclpy
from action_msgs.msg import GoalStatus
from car_interfaces.action import ExecutePatrol, VerifyCheckpoint
from car_interfaces.msg import MissionStatus, PatrolEvent
from car_interfaces.srv import MissionControl
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from rclpy.action import ActionClient, ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.task import Future
from std_msgs.msg import Bool, String

from .mission_repository import MissionRepository
from .navigation_adapter import NavigationAdapter
from .route_repository import RouteNotFoundError, RouteRepository
from .route_schema import Checkpoint, RouteDefinition
from .state_machine import MissionState, MissionStateMachine, TERMINAL_STATES


@dataclass
class MissionRuntime:
    mission_id: str
    route: RouteDefinition
    goal_handle: Any
    state_machine: MissionStateMachine
    checkpoint_index: int
    loop: bool
    completed_checkpoints: int = 0
    failed_checkpoints: int = 0
    skipped_checkpoints: int = 0
    retry_count: int = 0
    checkin_attempt: int = 0
    pause_requested: bool = False
    cancel_requested: bool = False
    estop_active: bool = False
    active_nav_goal_handle: Optional[Any] = None
    active_checkin_goal_handle: Optional[Any] = None
    resume_future: Optional[Future] = None


class MissionManager(Node):
    def __init__(self) -> None:
        super().__init__('mission_manager')
        self._declare_parameters()

        self._callback_group = ReentrantCallbackGroup()
        self._lock = threading.RLock()
        self._runtime: Optional[MissionRuntime] = None
        self._effective_estop_active = False
        self._last_localization_time_ns: Optional[int] = None

        database_path = str(self.get_parameter('database_path').value)
        self.route_repository = RouteRepository(database_path)
        self.mission_repository = MissionRepository(database_path)
        self._import_configured_route()

        self.goal_publisher = self.create_publisher(
            PoseStamped, str(self.get_parameter('goal_topic').value), 10
        )
        self.mode_publisher = self.create_publisher(
            String, str(self.get_parameter('mode_topic').value), 10
        )
        self.status_publisher = self.create_publisher(
            MissionStatus, str(self.get_parameter('status_topic').value), 10
        )
        self.event_publisher = self.create_publisher(
            PatrolEvent, str(self.get_parameter('event_topic').value), 10
        )
        self.create_subscription(
            PoseWithCovarianceStamped,
            str(self.get_parameter('localization_topic').value),
            self._on_localization,
            10,
            callback_group=self._callback_group,
        )
        self.create_subscription(
            Bool,
            str(self.get_parameter('effective_estop_topic').value),
            self._on_effective_estop,
            10,
            callback_group=self._callback_group,
        )

        self.navigation = NavigationAdapter(
            self,
            str(self.get_parameter('navigation_action').value),
            self._callback_group,
        )
        self.checkpoint_verifier = ActionClient(
            self,
            VerifyCheckpoint,
            str(self.get_parameter('checkin_action').value),
            callback_group=self._callback_group,
        )
        self.action_server = ActionServer(
            self,
            ExecutePatrol,
            str(self.get_parameter('action_name').value),
            execute_callback=self._execute_patrol,
            goal_callback=self._goal_callback,
            cancel_callback=self._cancel_callback,
            callback_group=self._callback_group,
        )
        self.control_service = self.create_service(
            MissionControl,
            str(self.get_parameter('control_service').value),
            self._on_mission_control,
            callback_group=self._callback_group,
        )
        self.get_logger().info('Mission manager is ready')

    def _declare_parameters(self) -> None:
        self.declare_parameter('route_file', '')
        self.declare_parameter('auto_import_route', True)
        self.declare_parameter('database_path', '~/.icar/icar.db')
        self.declare_parameter('action_name', 'execute_patrol')
        self.declare_parameter('control_service', '/mission/control')
        self.declare_parameter('navigation_action', 'navigate_to_pose')
        self.declare_parameter('goal_topic', '/goal_pose')
        self.declare_parameter('mode_topic', '/mode_select')
        self.declare_parameter('navigation_mode', 'nav')
        self.declare_parameter('status_topic', '/mission/status')
        self.declare_parameter('event_topic', '/mission/event')
        self.declare_parameter('effective_estop_topic', '/control/effective_estop')
        self.declare_parameter('localization_topic', '/amcl_pose')
        self.declare_parameter('require_localization', False)
        self.declare_parameter('localization_max_age_sec', 2.0)
        self.declare_parameter('nav_server_timeout_sec', 2.0)
        self.declare_parameter('max_nav_retries', 2)
        self.declare_parameter('checkin_action', 'verify_checkpoint')
        self.declare_parameter('checkin_server_timeout_sec', 2.0)

    def _import_configured_route(self) -> None:
        route_file = str(self.get_parameter('route_file').value).strip()
        if not route_file or not bool(self.get_parameter('auto_import_route').value):
            return
        try:
            route = self.route_repository.import_yaml(route_file, replace=True)
        except Exception as exc:
            self.get_logger().error(f'Could not import route file {route_file!r}: {exc}')
            return
        self.get_logger().info(
            f'Imported route {route.route_id} version {route.version} from {route_file}'
        )

    # Action callbacks ----------------------------------------------------
    def _goal_callback(self, _goal_request) -> GoalResponse:
        with self._lock:
            if self._runtime is not None:
                self.get_logger().warn('Rejecting patrol goal because another mission is active')
                return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _cancel_callback(self, _cancel_request) -> CancelResponse:
        self._request_cancel('Action cancellation requested')
        return CancelResponse.ACCEPT

    async def _execute_patrol(self, goal_handle) -> ExecutePatrol.Result:
        request = goal_handle.request
        route_id = request.route_id.strip()
        if not route_id:
            goal_handle.abort()
            return self._result('', False, MissionState.FAILED, 0, 0, 0, 'route_id is required')

        try:
            route = self.route_repository.load(
                route_id,
                int(request.route_version) if int(request.route_version) > 0 else None,
            )
        except RouteNotFoundError as exc:
            goal_handle.abort()
            return self._result('', False, MissionState.FAILED, 0, 0, 0, str(exc))

        start_index = int(request.start_checkpoint_index)
        if start_index >= len(route.checkpoints):
            goal_handle.abort()
            return self._result(
                '', False, MissionState.FAILED, 0, 0, 0,
                f'start_checkpoint_index must be below {len(route.checkpoints)}',
            )

        runtime = MissionRuntime(
            mission_id=f'mission_{uuid.uuid4().hex}',
            route=route,
            goal_handle=goal_handle,
            state_machine=MissionStateMachine(),
            checkpoint_index=start_index,
            loop=bool(route.loop or request.loop),
        )
        with self._lock:
            if self._runtime is not None:
                goal_handle.abort()
                return self._result('', False, MissionState.FAILED, 0, 0, 0, 'another mission is active')
            self._runtime = runtime

        try:
            self.mission_repository.create_mission(
                runtime.mission_id,
                route.route_id,
                route.version,
                MissionState.IDLE.value,
                len(route.checkpoints),
            )
            self._transition(runtime, MissionState.PREPARING, 'MISSION_STARTED', 'Mission accepted')
            self._transition(runtime, MissionState.LOCALIZING, 'LOCALIZATION_CHECK', 'Checking localization')
            if not await self._ensure_localization(runtime):
                return self._finalize_cancelled(runtime, 'Mission cancelled while waiting for localization')

            self._select_navigation_mode()
            while True:
                if self._cancel_requested(runtime):
                    return self._finalize_cancelled(runtime, 'Mission cancelled')
                if runtime.checkpoint_index >= len(route.checkpoints):
                    if runtime.loop:
                        runtime.checkpoint_index = 0
                        self._sync_status(runtime, 'Starting the next patrol loop')
                    else:
                        return self._finalize_success(runtime, 'All checkpoints reached')

                if not await self._wait_if_stopped(runtime):
                    return self._finalize_cancelled(runtime, 'Mission cancelled while paused')

                checkpoint = route.checkpoints[runtime.checkpoint_index]
                outcome = await self._navigate_checkpoint(runtime, checkpoint)
                if outcome == 'cancelled':
                    return self._finalize_cancelled(runtime, 'Mission cancelled')
                if outcome == 'failed':
                    runtime.failed_checkpoints += 1
                    return self._finalize_failed(runtime, f'Navigation failed at {checkpoint.checkpoint_id}')
                if outcome == 'skipped':
                    runtime.skipped_checkpoints += 1
                    runtime.failed_checkpoints += 1
                    self._record_checkpoint(runtime, checkpoint, 'CHECKPOINT_SKIPPED', 'Navigation failure policy skipped checkpoint')
                    runtime.retry_count = 0
                    runtime.checkpoint_index += 1
                    continue

                self._transition(
                    runtime,
                    MissionState.ARRIVAL_CONFIRMING,
                    'NAVIGATION_SUCCEEDED',
                    f'Nav2 reached {checkpoint.checkpoint_id}',
                )
                checkin_outcome = await self._verify_checkpoint(runtime, checkpoint)
                if checkin_outcome == 'cancelled':
                    return self._finalize_cancelled(runtime, 'Mission cancelled during checkpoint check-in')
                if checkin_outcome == 'failed':
                    runtime.failed_checkpoints += 1
                    return self._finalize_failed(runtime, f'Check-in failed at {checkpoint.checkpoint_id}')
                if checkin_outcome == 'restart_navigation':
                    # A pause, emergency stop, or operator decision always
                    # re-enters the checkpoint through Nav2 rather than
                    # trusting a stale arrival/marker observation.
                    continue
                self._transition(
                    runtime,
                    MissionState.RECORDING,
                    'CHECKPOINT_RECORDED',
                    f'Checkpoint {checkpoint.checkpoint_id} recorded after {checkin_outcome}',
                )
                runtime.completed_checkpoints += 1
                code = (
                    'CHECKPOINT_COMPLETED_WITH_CHECKIN_FAILURE'
                    if checkin_outcome == 'continued_after_failure'
                    else 'CHECKPOINT_COMPLETED'
                )
                self._record_checkpoint(
                    runtime,
                    checkpoint,
                    code,
                    f'Checkpoint completed after {checkin_outcome}',
                )
                runtime.retry_count = 0
                runtime.checkin_attempt = 0
                runtime.checkpoint_index += 1
        except Exception as exc:
            self.get_logger().error(f'Mission {runtime.mission_id} failed: {exc}')
            return self._finalize_failed(runtime, str(exc))
        finally:
            with self._lock:
                if self._runtime is runtime:
                    self._runtime = None

    # Mission execution ---------------------------------------------------
    async def _ensure_localization(self, runtime: MissionRuntime) -> bool:
        if not bool(self.get_parameter('require_localization').value):
            return True
        while not self._has_fresh_localization():
            self._transition(
                runtime,
                MissionState.WAITING_OPERATOR,
                'LOCALIZATION_UNAVAILABLE',
                'Localization is stale; set an initial pose and resume the mission',
            )
            if not await self._await_resume(runtime):
                return False
            self._transition(
                runtime,
                MissionState.LOCALIZING,
                'LOCALIZATION_RECHECK',
                'Rechecking localization after operator resume',
            )
        return True

    async def _navigate_checkpoint(self, runtime: MissionRuntime, checkpoint: Checkpoint) -> str:
        while True:
            if self._cancel_requested(runtime):
                return 'cancelled'
            if not await self._wait_if_stopped(runtime):
                return 'cancelled'

            self._transition(
                runtime,
                MissionState.NAVIGATING,
                'NAV_GOAL_SENT',
                f'Sending navigation goal for {checkpoint.checkpoint_id}',
            )
            self._select_navigation_mode()
            if not self.navigation.wait_for_server(
                timeout_sec=float(self.get_parameter('nav_server_timeout_sec').value)
            ):
                outcome = await self._handle_navigation_failure(
                    runtime, checkpoint, 'navigate_to_pose action server is unavailable'
                )
                if outcome != 'retry':
                    return outcome
                continue

            pose = self._build_pose(checkpoint)
            self.goal_publisher.publish(pose)
            nav_goal_handle = await self.navigation.send_goal_async(pose)
            if not nav_goal_handle.accepted:
                outcome = await self._handle_navigation_failure(
                    runtime, checkpoint, 'Nav2 rejected the goal'
                )
                if outcome != 'retry':
                    return outcome
                continue

            with self._lock:
                runtime.active_nav_goal_handle = nav_goal_handle
                should_cancel = runtime.cancel_requested or runtime.pause_requested or runtime.estop_active
            if should_cancel:
                self.navigation.cancel(nav_goal_handle)

            result = await nav_goal_handle.get_result_async()
            with self._lock:
                runtime.active_nav_goal_handle = None

            if self._cancel_requested(runtime):
                return 'cancelled'
            if runtime.estop_active or runtime.pause_requested:
                continue
            if int(result.status) == GoalStatus.STATUS_SUCCEEDED:
                runtime.retry_count = 0
                return 'succeeded'

            outcome = await self._handle_navigation_failure(
                runtime,
                checkpoint,
                f'Nav2 returned status {int(result.status)}',
            )
            if outcome != 'retry':
                return outcome

    async def _verify_checkpoint(self, runtime: MissionRuntime, checkpoint: Checkpoint) -> str:
        """Run the P3 proof action after Nav2 has reached a checkpoint."""
        checkin = checkpoint.checkin
        self._transition(
            runtime,
            MissionState.CHECKING_IN,
            'CHECKIN_STARTED',
            f'Starting {checkin.method} check-in for {checkpoint.checkpoint_id}',
        )
        if checkin.method == 'none':
            self._persist_checkin(
                runtime,
                checkpoint,
                success=True,
                outcome='NOT_REQUIRED',
                marker_id='',
                confirmation_count=0,
                evidence_path='',
                detail='No P3 check-in method is configured for this checkpoint',
            )
            return 'not_required'

        while True:
            if self._cancel_requested(runtime):
                return 'cancelled'
            if runtime.pause_requested or runtime.estop_active:
                return 'restart_navigation'
            if not self.checkpoint_verifier.wait_for_server(
                timeout_sec=float(self.get_parameter('checkin_server_timeout_sec').value)
            ):
                outcome = await self._handle_checkin_failure(
                    runtime,
                    checkpoint,
                    action_outcome='VERIFIER_UNAVAILABLE',
                    marker_id='',
                    confirmation_count=0,
                    evidence_path='',
                    detail='verify_checkpoint action server is unavailable',
                )
                if outcome == 'retry':
                    continue
                return outcome

            goal = VerifyCheckpoint.Goal()
            goal.mission_id = runtime.mission_id
            goal.checkpoint_id = checkpoint.checkpoint_id
            goal.target_x = checkpoint.pose.x
            goal.target_y = checkpoint.pose.y
            goal.target_yaw = checkpoint.pose.yaw
            goal.position_tolerance_m = checkpoint.position_tolerance_m
            goal.yaw_tolerance_rad = checkpoint.yaw_tolerance_rad
            goal.max_pose_covariance = checkpoint.max_pose_covariance
            goal.dwell_sec = checkpoint.dwell_sec
            goal.method = checkin.method
            goal.marker_type = checkin.marker_type
            goal.expected_marker_id = checkin.expected_marker_id
            goal.timeout_sec = checkin.timeout_sec
            goal.confirmation_frames = checkin.confirmation_frames
            checkin_goal_handle = await self.checkpoint_verifier.send_goal_async(goal)
            if not checkin_goal_handle.accepted:
                outcome = await self._handle_checkin_failure(
                    runtime,
                    checkpoint,
                    action_outcome='VERIFIER_REJECTED',
                    marker_id='',
                    confirmation_count=0,
                    evidence_path='',
                    detail='verify_checkpoint action server rejected the goal',
                )
                if outcome == 'retry':
                    continue
                return outcome

            with self._lock:
                runtime.active_checkin_goal_handle = checkin_goal_handle
                should_cancel = (
                    runtime.cancel_requested or runtime.pause_requested or runtime.estop_active
                )
            if should_cancel:
                checkin_goal_handle.cancel_goal_async()
            result_wrapper = await checkin_goal_handle.get_result_async()
            with self._lock:
                runtime.active_checkin_goal_handle = None

            if self._cancel_requested(runtime):
                return 'cancelled'
            if runtime.pause_requested or runtime.estop_active:
                return 'restart_navigation'
            result = result_wrapper.result
            if int(result_wrapper.status) == GoalStatus.STATUS_SUCCEEDED and bool(result.success):
                self._persist_checkin(
                    runtime,
                    checkpoint,
                    success=True,
                    outcome=result.outcome,
                    marker_id=result.marker_id,
                    confirmation_count=int(result.confirmation_count),
                    evidence_path=result.evidence_path,
                    detail=result.detail,
                )
                self._record_checkpoint(
                    runtime,
                    checkpoint,
                    'CHECKIN_VERIFIED',
                    f'{result.outcome}: {result.detail}',
                )
                return 'verified'

            outcome = await self._handle_checkin_failure(
                runtime,
                checkpoint,
                action_outcome=result.outcome or f'ACTION_STATUS_{int(result_wrapper.status)}',
                marker_id=result.marker_id,
                confirmation_count=int(result.confirmation_count),
                evidence_path=result.evidence_path,
                detail=result.detail or 'Checkpoint verifier returned failure',
            )
            if outcome == 'retry':
                continue
            return outcome

    async def _handle_checkin_failure(
        self,
        runtime: MissionRuntime,
        checkpoint: Checkpoint,
        *,
        action_outcome: str,
        marker_id: str,
        confirmation_count: int,
        evidence_path: str,
        detail: str,
    ) -> str:
        runtime.retry_count += 1
        self._persist_checkin(
            runtime,
            checkpoint,
            success=False,
            outcome=action_outcome,
            marker_id=marker_id,
            confirmation_count=confirmation_count,
            evidence_path=evidence_path,
            detail=detail,
        )
        if runtime.retry_count <= checkpoint.checkin.retries:
            self._record_checkpoint(
                runtime,
                checkpoint,
                'CHECKIN_RETRY',
                f'{action_outcome}; retry {runtime.retry_count}/{checkpoint.checkin.retries}',
            )
            return 'retry'

        policy = checkpoint.checkin_failure_policy
        if policy == 'abort_mission':
            return 'failed'
        if policy == 'retry_then_wait_operator':
            self._transition(
                runtime,
                MissionState.WAITING_OPERATOR,
                'CHECKIN_WAITING_OPERATOR',
                f'{action_outcome}; waiting for operator resume',
            )
            return 'restart_navigation' if await self._await_resume(runtime) else 'cancelled'

        runtime.failed_checkpoints += 1
        self._record_checkpoint(
            runtime,
            checkpoint,
            'CHECKIN_FAILED_CONTINUED',
            f'{action_outcome}; continuing by policy {policy}: {detail}',
        )
        return 'continued_after_failure'

    def _persist_checkin(
        self,
        runtime: MissionRuntime,
        checkpoint: Checkpoint,
        *,
        success: bool,
        outcome: str,
        marker_id: str,
        confirmation_count: int,
        evidence_path: str,
        detail: str,
    ) -> None:
        runtime.checkin_attempt += 1
        self.mission_repository.record_checkin(
            runtime.mission_id,
            checkpoint_id=checkpoint.checkpoint_id,
            attempt=runtime.checkin_attempt,
            method=checkpoint.checkin.method,
            outcome=outcome,
            success=success,
            marker_type=checkpoint.checkin.marker_type,
            marker_id=marker_id,
            confirmation_count=confirmation_count,
            evidence_path=evidence_path,
            detail=detail,
        )

    async def _handle_navigation_failure(
        self,
        runtime: MissionRuntime,
        checkpoint: Checkpoint,
        detail: str,
    ) -> str:
        runtime.retry_count += 1
        max_retries = int(self.get_parameter('max_nav_retries').value)
        if runtime.retry_count <= max_retries:
            self._transition(
                runtime,
                MissionState.RECOVERING,
                'NAV_RETRY',
                f'{detail}; retry {runtime.retry_count}/{max_retries}',
            )
            return 'retry'

        policy = checkpoint.navigation_failure_policy
        if policy == 'abort_mission':
            return 'failed'
        if policy in {'retry_then_continue', 'retry_then_skip'}:
            return 'skipped'

        self._transition(
            runtime,
            MissionState.WAITING_OPERATOR,
            'NAVIGATION_BLOCKED',
            f'{detail}; waiting for operator decision',
        )
        return 'retry' if await self._await_resume(runtime) else 'cancelled'

    async def _wait_if_stopped(self, runtime: MissionRuntime) -> bool:
        if runtime.estop_active:
            if runtime.state_machine.state != MissionState.ESTOPPED:
                self._transition(
                    runtime,
                    MissionState.ESTOPPED,
                    'EFFECTIVE_ESTOP',
                    'Safety stop is active; explicit resume is required after release',
                )
            return await self._await_resume(runtime)
        if runtime.pause_requested:
            if runtime.state_machine.state != MissionState.PAUSING:
                self._transition(runtime, MissionState.PAUSING, 'PAUSE_REQUESTED', 'Pausing mission')
            self._transition(runtime, MissionState.PAUSED, 'MISSION_PAUSED', 'Mission is paused')
            return await self._await_resume(runtime)
        return True

    async def _await_resume(self, runtime: MissionRuntime) -> bool:
        with self._lock:
            if runtime.resume_future is None or runtime.resume_future.done():
                runtime.resume_future = Future()
            future = runtime.resume_future
        self._sync_status(runtime, 'Waiting for operator resume or cancellation')
        resumed = await future
        with self._lock:
            runtime.resume_future = None
            if runtime.cancel_requested:
                return False
            if resumed:
                runtime.pause_requested = False
                runtime.estop_active = False
        return bool(resumed)

    # Control and safety callbacks ---------------------------------------
    def _on_mission_control(self, request, response):
        command = request.command.strip().lower()
        with self._lock:
            runtime = self._runtime
        if runtime is None or request.mission_id != runtime.mission_id:
            response.accepted = False
            response.state = MissionState.IDLE.value
            response.message = 'No matching active mission'
            return response

        if command == 'pause':
            if runtime.state_machine.state in TERMINAL_STATES:
                response.accepted = False
                response.state = runtime.state_machine.state.value
                response.message = 'Terminal missions cannot be paused'
                return response
            if runtime.state_machine.state == MissionState.ESTOPPED:
                response.accepted = False
                response.state = runtime.state_machine.state.value
                response.message = 'Release the effective emergency stop before changing mission state'
                return response
            if runtime.state_machine.state == MissionState.PAUSED:
                response.accepted = True
                response.state = runtime.state_machine.state.value
                response.message = 'Mission is already paused'
                return response
            runtime.pause_requested = True
            if runtime.state_machine.state != MissionState.PAUSING:
                self._transition(runtime, MissionState.PAUSING, 'PAUSE_REQUESTED', 'Pause requested by operator')
            self._cancel_active_navigation(runtime)
            self._cancel_active_checkin(runtime)
            response.accepted = True
            response.state = runtime.state_machine.state.value
            response.message = 'Pause requested; waiting for navigation cancellation'
            return response

        if command == 'resume':
            if self._effective_estop_active:
                response.accepted = False
                response.state = runtime.state_machine.state.value
                response.message = 'Cannot resume while effective emergency stop is active'
                return response
            if runtime.state_machine.state not in {
                MissionState.PAUSED,
                MissionState.WAITING_OPERATOR,
                MissionState.ESTOPPED,
            }:
                response.accepted = False
                response.state = runtime.state_machine.state.value
                response.message = 'Mission is not waiting for an operator resume'
                return response
            if runtime.resume_future is None or runtime.resume_future.done():
                response.accepted = False
                response.state = runtime.state_machine.state.value
                response.message = 'Mission is still stopping; retry resume after paused status is published'
                return response
            runtime.resume_future.set_result(True)
            response.accepted = True
            response.state = runtime.state_machine.state.value
            response.message = 'Resume accepted; navigation will restart at the current checkpoint'
            return response

        if command == 'cancel':
            self._request_cancel('Mission cancellation requested through control service')
            response.accepted = True
            response.state = runtime.state_machine.state.value
            response.message = 'Cancellation requested'
            return response

        response.accepted = False
        response.state = runtime.state_machine.state.value
        response.message = 'command must be pause, resume, or cancel'
        return response

    def _on_effective_estop(self, msg: Bool) -> None:
        self._effective_estop_active = bool(msg.data)
        if not self._effective_estop_active:
            return
        with self._lock:
            runtime = self._runtime
            if runtime is None or runtime.state_machine.state in TERMINAL_STATES:
                return
            runtime.estop_active = True
        if runtime.state_machine.state != MissionState.ESTOPPED:
            self._transition(
                runtime,
                MissionState.ESTOPPED,
                'EFFECTIVE_ESTOP',
                'Safety mux reported an effective emergency stop',
            )
        self._cancel_active_navigation(runtime)
        self._cancel_active_checkin(runtime)

    def _on_localization(self, _msg: PoseWithCovarianceStamped) -> None:
        self._last_localization_time_ns = self.get_clock().now().nanoseconds

    # State, persistence, and feedback ----------------------------------
    def _transition(
        self,
        runtime: MissionRuntime,
        target: MissionState,
        code: str,
        detail: str,
    ) -> None:
        with self._lock:
            current = runtime.state_machine.state
            if current == target:
                self._sync_status(runtime, detail)
                return
            previous = runtime.state_machine.transition(target)
        self._sync_status(runtime, detail)
        self.mission_repository.append_event(
            runtime.mission_id,
            previous_state=previous.value,
            state=target.value,
            checkpoint_id=self._checkpoint_id(runtime),
            code=code,
            detail=detail,
        )
        event = PatrolEvent()
        event.header.stamp = self.get_clock().now().to_msg()
        event.mission_id = runtime.mission_id
        event.previous_state = previous.value
        event.state = target.value
        event.checkpoint_id = self._checkpoint_id(runtime)
        event.code = code
        event.detail = detail
        self.event_publisher.publish(event)
        self._publish_feedback(runtime, detail)

    def _record_checkpoint(
        self,
        runtime: MissionRuntime,
        checkpoint: Checkpoint,
        code: str,
        detail: str,
    ) -> None:
        self._sync_status(runtime, detail)
        self.mission_repository.append_event(
            runtime.mission_id,
            previous_state=runtime.state_machine.state.value,
            state=runtime.state_machine.state.value,
            checkpoint_id=checkpoint.checkpoint_id,
            code=code,
            detail=detail,
        )
        self._publish_feedback(runtime, detail)

    def _sync_status(self, runtime: MissionRuntime, detail: str) -> None:
        checkpoint_id = self._checkpoint_id(runtime)
        total = len(runtime.route.checkpoints)
        progress = float(runtime.completed_checkpoints + runtime.skipped_checkpoints) / float(total)
        self.mission_repository.update_status(
            runtime.mission_id,
            state=runtime.state_machine.state.value,
            checkpoint_index=runtime.checkpoint_index,
            checkpoint_total=total,
            checkpoint_id=checkpoint_id,
            retry_count=runtime.retry_count,
            progress=progress,
            detail=detail,
        )
        status = MissionStatus()
        status.header.stamp = self.get_clock().now().to_msg()
        status.mission_id = runtime.mission_id
        status.route_id = runtime.route.route_id
        status.route_version = runtime.route.version
        status.state = runtime.state_machine.state.value
        status.checkpoint_id = checkpoint_id
        status.checkpoint_index = runtime.checkpoint_index
        status.checkpoint_total = total
        status.progress = progress
        status.retry_count = runtime.retry_count
        status.detail = detail
        self.status_publisher.publish(status)

    def _publish_feedback(self, runtime: MissionRuntime, detail: str) -> None:
        feedback = ExecutePatrol.Feedback()
        total = len(runtime.route.checkpoints)
        feedback.mission_id = runtime.mission_id
        feedback.state = runtime.state_machine.state.value
        feedback.checkpoint_id = self._checkpoint_id(runtime)
        feedback.checkpoint_index = runtime.checkpoint_index
        feedback.checkpoint_total = total
        feedback.progress = float(runtime.completed_checkpoints + runtime.skipped_checkpoints) / float(total)
        feedback.retry_count = runtime.retry_count
        feedback.detail = detail
        runtime.goal_handle.publish_feedback(feedback)

    # Helpers -------------------------------------------------------------
    def _request_cancel(self, detail: str) -> None:
        with self._lock:
            runtime = self._runtime
            if runtime is None:
                return
            runtime.cancel_requested = True
            future = runtime.resume_future
        self._cancel_active_navigation(runtime)
        self._cancel_active_checkin(runtime)
        if future is not None and not future.done():
            future.set_result(False)
        self.get_logger().info(detail)

    def _cancel_active_navigation(self, runtime: MissionRuntime) -> None:
        with self._lock:
            goal_handle = runtime.active_nav_goal_handle
        self.navigation.cancel(goal_handle)

    def _cancel_active_checkin(self, runtime: MissionRuntime) -> None:
        with self._lock:
            goal_handle = runtime.active_checkin_goal_handle
        if goal_handle is not None:
            goal_handle.cancel_goal_async()

    def _cancel_requested(self, runtime: MissionRuntime) -> bool:
        return bool(runtime.cancel_requested or runtime.goal_handle.is_cancel_requested)

    def _has_fresh_localization(self) -> bool:
        if self._last_localization_time_ns is None:
            return False
        maximum_age_ns = int(float(self.get_parameter('localization_max_age_sec').value) * 1e9)
        return self.get_clock().now().nanoseconds - self._last_localization_time_ns <= maximum_age_ns

    def _select_navigation_mode(self) -> None:
        mode = str(self.get_parameter('navigation_mode').value).strip().lower()
        self.mode_publisher.publish(String(data=mode))

    def _build_pose(self, checkpoint: Checkpoint) -> PoseStamped:
        pose = PoseStamped()
        pose.header.frame_id = checkpoint.pose.frame_id
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = checkpoint.pose.x
        pose.pose.position.y = checkpoint.pose.y
        pose.pose.orientation.z = math.sin(checkpoint.pose.yaw / 2.0)
        pose.pose.orientation.w = math.cos(checkpoint.pose.yaw / 2.0)
        return pose

    @staticmethod
    def _result(
        mission_id: str,
        success: bool,
        state: MissionState,
        completed: int,
        failed: int,
        skipped: int,
        message: str,
    ) -> ExecutePatrol.Result:
        result = ExecutePatrol.Result()
        result.mission_id = mission_id
        result.success = success
        result.final_state = state.value
        result.completed_checkpoints = completed
        result.failed_checkpoints = failed
        result.skipped_checkpoints = skipped
        result.report_path = ''
        result.message = message
        return result

    def _finalize_success(self, runtime: MissionRuntime, detail: str) -> ExecutePatrol.Result:
        self._transition(runtime, MissionState.COMPLETED, 'MISSION_COMPLETED', detail)
        runtime.goal_handle.succeed()
        return self._result(
            runtime.mission_id,
            True,
            MissionState.COMPLETED,
            runtime.completed_checkpoints,
            runtime.failed_checkpoints,
            runtime.skipped_checkpoints,
            detail,
        )

    def _finalize_cancelled(self, runtime: MissionRuntime, detail: str) -> ExecutePatrol.Result:
        self._transition(runtime, MissionState.CANCELLED, 'MISSION_CANCELLED', detail)
        runtime.goal_handle.canceled()
        return self._result(
            runtime.mission_id,
            False,
            MissionState.CANCELLED,
            runtime.completed_checkpoints,
            runtime.failed_checkpoints,
            runtime.skipped_checkpoints,
            detail,
        )

    def _finalize_failed(self, runtime: MissionRuntime, detail: str) -> ExecutePatrol.Result:
        self._transition(runtime, MissionState.FAILED, 'MISSION_FAILED', detail)
        runtime.goal_handle.abort()
        return self._result(
            runtime.mission_id,
            False,
            MissionState.FAILED,
            runtime.completed_checkpoints,
            runtime.failed_checkpoints,
            runtime.skipped_checkpoints,
            detail,
        )

    @staticmethod
    def _checkpoint_id(runtime: MissionRuntime) -> str:
        if 0 <= runtime.checkpoint_index < len(runtime.route.checkpoints):
            return runtime.route.checkpoints[runtime.checkpoint_index].checkpoint_id
        return ''


def main(args: Optional[Sequence[str]] = None) -> None:
    rclpy.init(args=args)
    node = MissionManager()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()
