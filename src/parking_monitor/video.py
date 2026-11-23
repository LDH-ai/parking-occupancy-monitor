"""저장 영상 열기와 순차 디코딩."""

from contextlib import contextmanager
from pathlib import Path

import cv2


@contextmanager
def open_video(path):
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"영상 파일을 찾을 수 없습니다: {source}")
    capture = cv2.VideoCapture(str(source))
    try:
        if not capture.isOpened():
            raise ValueError(f"영상을 열 수 없습니다: {source}")
        yield capture
    finally:
        capture.release()


def decoded_frames(capture):
    while True:
        ok, frame = capture.read()
        if not ok or frame is None:
            return
        yield frame
