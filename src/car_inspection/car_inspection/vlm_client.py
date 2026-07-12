"""Optional HTTP VLM adapter with strict response parsing and no ROS access."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Optional, Tuple
from urllib.error import URLError
from urllib.request import Request, urlopen

from .inspection_schema import InspectionSchemaError, VlmReview, parse_vlm_review


@dataclass(frozen=True)
class VlmAttempt:
    review: Optional[VlmReview]
    raw_response: str
    error: str


class VlmClient:
    """A disabled-by-default adapter for a deployment-provided VLM endpoint."""

    def __init__(self, endpoint: str, timeout_sec: float) -> None:
        self.endpoint = endpoint.strip()
        self.timeout_sec = float(timeout_sec)

    def review(
        self,
        *,
        task: str,
        target: str,
        image_bytes: bytes,
    ) -> VlmAttempt:
        if not self.endpoint:
            return VlmAttempt(None, '', 'VLM_DISABLED')
        if self.timeout_sec <= 0.0:
            return VlmAttempt(None, '', 'VLM_TIMEOUT_INVALID')
        request_payload = {
            'task': task,
            'target': target,
            'image_base64': base64.b64encode(image_bytes).decode('ascii'),
        }
        request = Request(
            self.endpoint,
            data=json.dumps(request_payload, separators=(',', ':')).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with urlopen(request, timeout=self.timeout_sec) as response:
                raw = response.read().decode('utf-8')
        except (OSError, URLError, UnicodeDecodeError) as exc:
            return VlmAttempt(None, '', f'VLM_REQUEST_FAILED: {exc}')
        try:
            parsed = json.loads(raw)
            review = parse_vlm_review(parsed, task)
        except (json.JSONDecodeError, InspectionSchemaError) as exc:
            return VlmAttempt(None, raw, f'VLM_RESPONSE_INVALID: {exc}')
        return VlmAttempt(review, raw, '')
