"""Strict, ROS-independent schemas for visual inspection results."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Optional


CONCLUSIONS = frozenset({
    'PRESENT', 'ABSENT', 'ABNORMAL', 'UNKNOWN', 'NEEDS_HUMAN_REVIEW',
})
VLM_CONDITIONS = frozenset({'normal', 'abnormal', 'unknown'})


class InspectionSchemaError(ValueError):
    """A model response or local detection payload is not trustworthy."""


@dataclass(frozen=True)
class VlmReview:
    task: str
    present: bool
    confidence: float
    condition: str
    reason: str
    needs_human_review: bool


@dataclass(frozen=True)
class LocalObservation:
    status: str
    confidence: float
    model: str
    detail: str


@dataclass(frozen=True)
class InspectionDecision:
    conclusion: str
    confidence: float
    needs_human_review: bool
    source: str
    reason: str


def parse_vlm_review(value: Any, expected_task: str) -> VlmReview:
    if not isinstance(value, dict):
        raise InspectionSchemaError('VLM response must be an object')
    task = _text(value.get('task'), 'task')
    if task != expected_task:
        raise InspectionSchemaError(f'VLM task must equal {expected_task!r}')
    present = _boolean(value.get('present'), 'present')
    confidence = _probability(value.get('confidence'), 'confidence')
    condition = _text(value.get('condition'), 'condition').lower()
    if condition not in VLM_CONDITIONS:
        raise InspectionSchemaError('condition must be normal, abnormal, or unknown')
    reason = _text(value.get('reason'), 'reason')
    if len(reason) > 1000:
        raise InspectionSchemaError('reason must be at most 1000 characters')
    needs_human_review = _boolean(value.get('needs_human_review'), 'needs_human_review')
    return VlmReview(task, present, confidence, condition, reason, needs_human_review)


def local_observation_from_payload(
    payload: Any,
    *,
    target: str,
    confidence_threshold: float,
    allow_absent: bool,
    expected_model: str = '',
) -> LocalObservation:
    """Convert a stamped, possibly multi-model YOLO payload conservatively."""
    if not isinstance(payload, dict):
        return LocalObservation('UNAVAILABLE', 0.0, '', 'detection payload is unavailable')
    model = payload.get('model') if isinstance(payload.get('model'), str) else ''
    error = payload.get('error')
    if isinstance(error, str) and error.strip():
        return LocalObservation('UNAVAILABLE', 0.0, model, error.strip())
    detections = payload.get('detections')
    if not isinstance(detections, list):
        return LocalObservation('UNAVAILABLE', 0.0, model, 'detections must be an array')
    active_models = {
        value.strip() for value in payload.get('active_models', [])
        if isinstance(value, str) and value.strip()
    }
    has_per_detection_model = any(
        isinstance(item, dict) and isinstance(item.get('model'), str) and item['model'].strip()
        for item in detections
    )
    if expected_model and active_models and expected_model not in active_models:
        return LocalObservation(
            'UNAVAILABLE', 0.0, model,
            f'expected registered model {expected_model!r} is not active',
        )
    if expected_model and not active_models and not has_per_detection_model and model != expected_model:
        # Compatibility for the former single-model payload, where ``model``
        # was the model filename rather than a registry name.
        return LocalObservation(
            'UNAVAILABLE', 0.0, model,
            f'expected local model {expected_model!r}, received {model!r}',
        )
    target_normalized = target.strip().casefold()
    best = 0.0
    best_model = expected_model or model
    for item in detections:
        if not isinstance(item, dict):
            continue
        detection_model = item.get('model') if isinstance(item.get('model'), str) else ''
        if expected_model and has_per_detection_model and detection_model != expected_model:
            continue
        label = item.get('label')
        confidence = item.get('confidence')
        if not isinstance(label, str) or label.strip().casefold() != target_normalized:
            continue
        try:
            numeric_confidence = float(confidence)
        except (TypeError, ValueError):
            continue
        if math.isfinite(numeric_confidence):
            if numeric_confidence > best:
                best = numeric_confidence
                best_model = detection_model or model
    if best >= confidence_threshold:
        return LocalObservation('PRESENT', best, best_model, 'target detected above local threshold')
    if allow_absent:
        return LocalObservation('ABSENT', best, best_model, 'target not detected by validated local model')
    return LocalObservation(
        'NEGATIVE_UNVERIFIED', best, best_model,
        'local negative detection is not enabled as an absence decision',
    )


def fuse_observations(
    local: LocalObservation,
    review: Optional[VlmReview],
) -> InspectionDecision:
    """Fuse only typed outputs; model failures always degrade to UNKNOWN."""
    if local.status == 'PRESENT':
        return InspectionDecision('PRESENT', local.confidence, False, 'local_model', local.detail)
    if local.status == 'ABSENT':
        return InspectionDecision('ABSENT', local.confidence, False, 'local_model', local.detail)
    if review is None:
        reason = local.detail or 'no structured model result is available'
        return InspectionDecision('UNKNOWN', local.confidence, True, 'none', reason)
    if review.needs_human_review:
        return InspectionDecision(
            'NEEDS_HUMAN_REVIEW', review.confidence, True, 'vlm', review.reason
        )
    if review.condition == 'abnormal':
        return InspectionDecision('ABNORMAL', review.confidence, True, 'vlm', review.reason)
    if review.condition == 'unknown':
        return InspectionDecision('UNKNOWN', review.confidence, True, 'vlm', review.reason)
    if review.present:
        return InspectionDecision('PRESENT', review.confidence, False, 'vlm', review.reason)
    return InspectionDecision('ABSENT', review.confidence, False, 'vlm', review.reason)


def decision_to_mapping(decision: InspectionDecision) -> Dict[str, Any]:
    return {
        'conclusion': decision.conclusion,
        'confidence': decision.confidence,
        'needs_human_review': decision.needs_human_review,
        'source': decision.source,
        'reason': decision.reason,
    }


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InspectionSchemaError(f'{field} must be a non-empty string')
    return value.strip()


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise InspectionSchemaError(f'{field} must be a boolean')
    return value


def _probability(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise InspectionSchemaError(f'{field} must be a number between zero and one')
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise InspectionSchemaError(f'{field} must be a number between zero and one') from exc
    if not math.isfinite(number) or number < 0.0 or number > 1.0:
        raise InspectionSchemaError(f'{field} must be a number between zero and one')
    return number
