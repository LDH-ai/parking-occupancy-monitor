"""픽셀 기준선 명령의 설정과 인자를 해석한다."""

from dataclasses import replace
import json
from pathlib import Path

from .pixel_experiment import run_baseline
from .pixel_ratio import PixelRatioConfig


def load_config(path):
    if path is None:
        return PixelRatioConfig()
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("픽셀 기준선 설정은 JSON 객체여야 합니다")
    return PixelRatioConfig.from_dict(data.get("pixel_ratio", data))


def add_arguments(parser):
    parser.add_argument("--video", required=True, help="ROI의 원본 저장 영상")
    parser.add_argument("--roi", required=True, help="저장소 ROI JSON")
    parser.add_argument("--labels", required=True, help="저장소 0 기반 정답 CSV")
    parser.add_argument("--out", required=True, help="새 결과 폴더")
    parser.add_argument("--config", help="픽셀 기준선 JSON")
    parser.add_argument("--min-component-area-px", type=int,
                        help="연결성분 최소 면적(픽셀 수). 0으로 필터 해제")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--splits", help="보정·검증 분할 CSV")
    mode.add_argument("--pilot", action="store_true", help="표본 내 동작 확인")
    parser.add_argument("--min-per-class", type=int, default=3)
    parser.add_argument("--allow-pooled", action="store_true",
                        help="파일럿에서만 부족한 칸에 통합 임계값 허용")
    parser.add_argument("--timeseries", action="store_true", help="개발 구간의 칸별 r 시계열 저장")


def run_command(args):
    config = load_config(args.config)
    if args.min_component_area_px is not None:
        config = replace(config, min_component_area_px=args.min_component_area_px)
    return run_baseline(args.video, args.roi, args.labels, args.out, config,
                        splits_path=args.splits, pilot=args.pilot, min_per_class=args.min_per_class,
                        allow_pooled=args.allow_pooled, timeseries=args.timeseries)
