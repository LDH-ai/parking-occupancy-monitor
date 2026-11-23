"""픽셀 비율 특징(11주차 기준선).

처리 순서: 그레이스케일 → 가우시안 평활 → 적응형 역이진화 → 미디언 → 형태학 → 연결성분 면적 필터
→ 칸 마스크 내부 흰 픽셀 수 / 칸 마스크 픽셀 수 = r.

- 마스크는 특징 통계에만 쓴다. 필터는 프레임 전체에 먼저 적용해 마스크 경계에
  인공 경계가 생기지 않게 한다.
- r은 흰 픽셀의 비율일 뿐 실제 차량 면적 비율이 아니다.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import cv2
import numpy as np

MORPHOLOGY_CHOICES = ("none", "dilate", "open", "close")


@dataclass(frozen=True)
class PixelRatioConfig:
    """전처리 설정. 값은 시작 예시이며 검증 구간에서 선택한다."""
    gaussian_kernel: tuple[int, int] = (5, 5)
    adaptive_block_size: int = 25
    adaptive_c: float = 16.0
    median_kernel: int = 5
    morphology: str = "dilate"
    morphology_kernel: tuple[int, int] = (3, 3)
    min_component_area_px: int = 0

    def __post_init__(self):
        if self.morphology not in MORPHOLOGY_CHOICES:
            raise ValueError(f"morphology는 {MORPHOLOGY_CHOICES} 중 하나여야 합니다: {self.morphology}")
        if (type(self.adaptive_block_size) is not int or self.adaptive_block_size < 3
                or self.adaptive_block_size % 2 == 0):
            raise ValueError("adaptive_block_size는 3 이상의 홀수여야 합니다")
        if not isinstance(self.adaptive_c, (int, float)) or not math.isfinite(self.adaptive_c):
            raise ValueError("adaptive_c는 유한한 수여야 합니다")
        if type(self.median_kernel) is not int or self.median_kernel < 3 or self.median_kernel % 2 == 0:
            raise ValueError("median_kernel은 3 이상의 홀수여야 합니다")
        if type(self.min_component_area_px) is not int or self.min_component_area_px < 0:
            raise ValueError("min_component_area_px는 0 이상의 정수여야 합니다")
        for k in (self.gaussian_kernel, self.morphology_kernel):
            if len(k) != 2 or any(type(v) is not int or v < 1 or v % 2 == 0 for v in k):
                raise ValueError(f"커널 크기는 1 이상의 홀수 두 개여야 합니다: {k}")

    def to_dict(self) -> dict:
        return {
            "gaussian_kernel": list(self.gaussian_kernel),
            "adaptive_block_size": self.adaptive_block_size,
            "adaptive_c": self.adaptive_c,
            "median_kernel": self.median_kernel,
            "morphology": self.morphology,
            "morphology_kernel": list(self.morphology_kernel),
            "min_component_area_px": self.min_component_area_px,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PixelRatioConfig":
        if not isinstance(data, dict):
            raise ValueError("pixel_ratio 설정은 JSON 객체여야 합니다")
        allowed = {"gaussian_kernel", "adaptive_block_size", "adaptive_c", "median_kernel",
                   "morphology", "morphology_kernel", "min_component_area_px"}
        extra = set(data) - allowed
        if extra:
            raise ValueError(f"알 수 없는 설정 키: {sorted(extra)}")
        values = dict(data)
        for key in ("gaussian_kernel", "morphology_kernel"):
            if key in values:
                if not isinstance(values[key], (tuple, list)):
                    raise ValueError(f"{key}은 두 정수의 배열이어야 합니다")
                values[key] = tuple(values[key])
        return cls(**values)


def preprocess(frame_bgr: np.ndarray, config: PixelRatioConfig) -> np.ndarray:
    """프레임 전체를 평활·이진화하고 미디언 필터를 적용한다."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    smooth = cv2.GaussianBlur(gray, config.gaussian_kernel, 0)
    return threshold_smoothed(smooth, config)


def threshold_smoothed(smooth: np.ndarray, config: PixelRatioConfig) -> np.ndarray:
    """평활한 그레이 영상에서 픽셀 비율용 이진 영상을 만든다."""
    binary = cv2.adaptiveThreshold(smooth, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, config.adaptive_block_size,
                                   config.adaptive_c)
    return cv2.medianBlur(binary, config.median_kernel)


def apply_morphology(binary: np.ndarray, config: PixelRatioConfig) -> np.ndarray:
    if config.morphology == "none":
        return binary
    kernel = np.ones(config.morphology_kernel, dtype=np.uint8)
    if config.morphology == "dilate":
        return cv2.dilate(binary, kernel)
    op = cv2.MORPH_OPEN if config.morphology == "open" else cv2.MORPH_CLOSE
    return cv2.morphologyEx(binary, op, kernel)


def postprocess(binary: np.ndarray, config: PixelRatioConfig) -> np.ndarray:
    """형태학 처리 후 프레임에서 작은 8-연결 흰색 성분을 제거한다."""
    shaped = apply_morphology(binary, config)
    if config.min_component_area_px <= 1:
        return shaped
    _, labels, stats, _ = cv2.connectedComponentsWithStats(shaped, connectivity=8)
    keep = stats[:, cv2.CC_STAT_AREA] >= config.min_component_area_px
    keep[0] = False
    return keep[labels].astype(np.uint8) * 255


def binarize(frame_bgr: np.ndarray, config: PixelRatioConfig) -> np.ndarray:
    """프레임 전체에 적용하는 전처리. 반환값은 0/255 이진 영상이다."""
    return postprocess(preprocess(frame_bgr, config), config)


def pixel_ratios(binary: np.ndarray, masks: dict[str, np.ndarray]) -> dict[str, float]:
    """저장소의 0/255 마스크에서 칸별 흰 픽셀 비율을 계산한다."""
    ratios = {}
    for slot_id, mask in masks.items():
        if binary.shape != mask.shape:
            raise ValueError(f"{slot_id}: 이진 영상과 마스크 크기가 다릅니다")
        area = cv2.countNonZero(mask)
        if area == 0:
            raise ValueError(f"{slot_id}: 마스크가 비어 있습니다")
        ratios[slot_id] = cv2.countNonZero(cv2.bitwise_and(binary, mask)) / area
    return ratios


def frame_ratios(frame_bgr: np.ndarray, masks: dict[str, np.ndarray],
                 config: PixelRatioConfig) -> dict[str, float]:
    """한 프레임의 칸별 r. 프레임 크기와 마스크 크기가 같아야 한다."""
    return pixel_ratios(binarize(frame_bgr, config), masks)
