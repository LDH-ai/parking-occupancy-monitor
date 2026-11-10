"""환경 및 저장 영상 입력을 확인하는 개발 CLI. 검출기는 후속 구현한다."""
import argparse
import json
from pathlib import Path
import platform
import sys

import cv2
import numpy as np


def doctor():
    import matplotlib
    image = np.zeros((48, 64, 3), dtype=np.uint8)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    binary = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY_INV, 11, 2)
    kernel = np.ones((3, 3), dtype=np.uint8)
    morph = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    lap = cv2.Laplacian(blurred, cv2.CV_64F)
    mask = np.zeros(gray.shape, dtype=np.uint8)
    cv2.fillPoly(mask, [np.array([[4, 4], [28, 4], [28, 32], [4, 32]])], 255)
    assert mask.any() and morph.shape == gray.shape and np.isfinite(lap).all()
    return {"python": platform.python_version(), "executable": sys.executable,
            "numpy": np.__version__, "opencv": cv2.__version__,
            "matplotlib": matplotlib.__version__, "synthetic_processing": "ok",
            "detector_implemented": False}


def video_info(path):
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"영상 파일을 찾을 수 없습니다: {source}")
    capture = cv2.VideoCapture(str(source))
    try:
        if not capture.isOpened():
            raise ValueError(f"영상을 열 수 없습니다: {source}")
        ok, frame = capture.read()
        if not ok or frame is None:
            raise ValueError(f"첫 프레임을 읽을 수 없습니다: {source}")
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        return {"path": str(source), "width": frame.shape[1], "height": frame.shape[0],
                "fps_reported": fps if np.isfinite(fps) and fps > 0 else None,
                "frame_count_reported": max(frames, 0), "first_frame_decoded": True}
    finally:
        capture.release()


def main(argv=None):
    parser = argparse.ArgumentParser(description="주차면 점유 검출 개발 도구")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="환경 및 합성 영상 연산 확인")
    info = commands.add_parser("video-info", help="저장 영상의 메타데이터와 첫 프레임 확인")
    info.add_argument("path")
    picker = commands.add_parser("roi-pick", help="클릭으로 주차면 ROI 지정·저장·불러오기")
    picker.add_argument("video")
    picker.add_argument("--output", required=True)
    picker.add_argument("--video-id")
    picker.add_argument("--frame", type=int, default=0)
    picker.add_argument("--zone", default="A")
    picker.add_argument("--prefix", default="S")
    preview = commands.add_parser("roi-preview", help="저장한 ROI를 영상 프레임에 표시해 이미지로 검증")
    preview.add_argument("video")
    preview.add_argument("--roi", required=True)
    preview.add_argument("--output", required=True)
    preview.add_argument("--frame", type=int, default=0)
    preview.add_argument("--width", type=int)
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            result = doctor()
        elif args.command == "video-info":
            result = video_info(args.path)
        elif args.command == "roi-pick":
            from .roi_editor import pick_roi
            result = pick_roi(args.video, args.output, args.video_id, args.frame, args.zone, args.prefix)
        else:
            from .roi import preview_roi
            result = preview_roi(args.video, args.roi, args.output, args.frame, args.width)
    except (ValueError, OSError, cv2.error) as error:
        parser.exit(1, f"오류: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
