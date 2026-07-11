"""Pure single-client manual-control lease management."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import uuid


class LeaseError(ValueError):
    """Raised for invalid, expired, or foreign control leases."""


@dataclass(frozen=True)
class ControlLease:
    lease_id: str
    session_id: str
    expires_at: float


class ControlLeaseManager:
    def __init__(self, timeout_sec: float) -> None:
        if timeout_sec <= 0.0:
            raise ValueError('timeout_sec must be positive')
        self.timeout_sec = float(timeout_sec)
        self._lease: Optional[ControlLease] = None

    def acquire(self, session_id: str, now: float) -> ControlLease:
        self.expire(now)
        if self._lease is not None and self._lease.session_id != session_id:
            raise LeaseError('manual control is held by another client')
        self._lease = ControlLease(
            lease_id=uuid.uuid4().hex,
            session_id=session_id,
            expires_at=now + self.timeout_sec,
        )
        return self._lease

    def heartbeat(self, session_id: str, lease_id: str, now: float) -> ControlLease:
        self._validate(session_id, lease_id, now)
        self._lease = ControlLease(
            lease_id=lease_id,
            session_id=session_id,
            expires_at=now + self.timeout_sec,
        )
        return self._lease

    def release(self, session_id: str, lease_id: Optional[str], now: float) -> bool:
        self.expire(now)
        if self._lease is None:
            return False
        if self._lease.session_id != session_id:
            raise LeaseError('manual control is held by another client')
        if lease_id is not None and self._lease.lease_id != lease_id:
            raise LeaseError('lease_id does not match the active control lease')
        self._lease = None
        return True

    def expire(self, now: float) -> bool:
        if self._lease is not None and now >= self._lease.expires_at:
            self._lease = None
            return True
        return False

    def snapshot(self, now: float) -> dict:
        self.expire(now)
        if self._lease is None:
            return {'active': False}
        return {
            'active': True,
            'lease_id': self._lease.lease_id,
            'expires_in_sec': max(0.0, self._lease.expires_at - now),
        }

    def _validate(self, session_id: str, lease_id: str, now: float) -> None:
        self.expire(now)
        if self._lease is None:
            raise LeaseError('manual control lease is required')
        if self._lease.session_id != session_id:
            raise LeaseError('manual control is held by another client')
        if self._lease.lease_id != lease_id:
            raise LeaseError('lease_id does not match the active control lease')
