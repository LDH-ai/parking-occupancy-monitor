import cv2
import numpy as np
import pytest

from parking_monitor.cli import doctor, video_info


def test_required_processing_available():
    assert doctor()["synthetic_processing"] == "ok"


def test_video_round_trip(tmp_path):
    path = tmp_path / "input.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48))
    assert writer.isOpened()
    try:
        for value in (0, 80, 160):
            writer.write(np.full((48, 64, 3), value, dtype=np.uint8))
    finally:
        writer.release()
    info = video_info(path)
    assert (info["width"], info["height"]) == (64, 48)
    assert info["first_frame_decoded"]
    assert info["fps_reported"] == pytest.approx(10)
    assert info["frame_count_reported"] == 3


def test_missing_video(tmp_path):
    with pytest.raises(ValueError, match="찾을 수 없습니다"):
        video_info(tmp_path / "missing.mp4")


def test_corrupt_video(tmp_path):
    path = tmp_path / "broken.mp4"
    path.write_bytes(b"not a video")
    with pytest.raises(ValueError, match="열 수 없습니다"):
        video_info(path)
