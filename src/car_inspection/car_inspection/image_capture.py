"""Bounded image buffering and JPEG capture helpers; no quality scoring."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, List, Tuple


@dataclass(frozen=True)
class BufferedImage:
    sequence: int
    stamp: Tuple[int, int]
    received_at: float
    image: Any


class ImageBuffer:
    def __init__(self, max_frames: int) -> None:
        if max_frames <= 0:
            raise ValueError('max_frames must be positive')
        self._frames: Deque[BufferedImage] = deque(maxlen=max_frames)
        self._sequence = 0

    @property
    def sequence(self) -> int:
        return self._sequence

    def append(self, stamp: Tuple[int, int], received_at: float, image: Any) -> BufferedImage:
        self._sequence += 1
        frame = BufferedImage(self._sequence, stamp, received_at, image)
        self._frames.append(frame)
        return frame

    def after(self, sequence: int) -> List[BufferedImage]:
        return [frame for frame in self._frames if frame.sequence > sequence]


def encode_jpeg(cv2: Any, image: Any) -> bytes:
    encoded, buffer = cv2.imencode('.jpg', image)
    if not encoded:
        raise ValueError('could not JPEG-encode capture')
    return bytes(buffer)
