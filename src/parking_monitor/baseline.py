"""픽셀 비율 기준선(11주차)의 정답 읽기·보정·판정·평가 논리.

영상·OpenCV에 의존하지 않는 순수 논리만 둔다(작은 입력으로 검증하기 위함).
정답과 출력은 free/occupied/unknown을 사용한다. 출력의 unknown은 판정 보류다.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
import math

import numpy as np

STATES = ("free", "occupied", "unknown")


@dataclass(frozen=True)
class LabelRow:
    video_id: str
    frame_id: int          # 0부터 시작하는 원본 프레임 번호
    timestamp_s: float
    slot_id: str
    label: str


@dataclass(frozen=True)
class Threshold:
    """칸 하나의 판정 기준. r <= low 빈자리, r >= high 점유, 그 사이 보류."""
    low: float
    high: float
    n_free: int
    n_occupied: int
    source: str            # "slot" | "pooled"
    separable: bool        # 보정 표본이 겹치지 않았는가
    note: str = ""
    upper_bound: float | None = 1.0

    def __post_init__(self):
        if not (math.isfinite(self.low) and math.isfinite(self.high) and 0 <= self.low < self.high):
            raise ValueError(f"하한은 상한보다 작아야 합니다: low={self.low}, high={self.high}")
        if self.upper_bound is not None and self.high > self.upper_bound:
            raise ValueError(f"임계값이 특징 범위를 벗어났습니다: high={self.high}")


def read_labels(path) -> list[LabelRow]:
    """저장소 형식의 0 기반 프레임 정답을 읽는다."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        if not {"video_id", "frame_id", "timestamp_s", "slot_id", "label"} <= fields:
            raise ValueError(f"알 수 없는 정답 CSV 열 구성입니다: {sorted(fields)}")
        rows = []
        for number, row in enumerate(reader, start=2):
            video_id = (row["video_id"] or "").strip()
            slot_id = (row["slot_id"] or "").strip()
            label = (row["label"] or "").strip().lower()
            try:
                frame_id = int(row["frame_id"])
                timestamp = float(row["timestamp_s"])
            except (ValueError, TypeError) as error:
                raise ValueError(f"{path}:{number}: 잘못된 프레임 번호 또는 시각") from error
            if not video_id or not slot_id or label not in STATES:
                raise ValueError(f"{path}:{number}: 잘못된 영상 ID, 칸 ID 또는 정답 상태")
            if frame_id < 0 or not math.isfinite(timestamp) or timestamp < 0:
                raise ValueError(f"{path}:{number}: 프레임 번호와 시각은 0 이상이어야 합니다")
            rows.append(LabelRow(video_id, frame_id, timestamp, slot_id, label))
    keys = [(r.video_id, r.frame_id, r.slot_id) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("같은 (영상, 프레임, 칸) 정답이 중복되어 있습니다")
    return rows


def _threshold_from(free: list[float], occupied: list[float], source: str,
                    upper_bound: float | None) -> Threshold:
    v = np.asarray(free, dtype=float)
    o = np.asarray(occupied, dtype=float)
    if v.max() < o.min():
        # 보정 표본이 분리됨: 빈자리 최댓값 ~ 점유 최솟값 사이가 보류 구간이다.
        return Threshold(float(v.max()), float(o.min()), len(v), len(o), source, True,
                         upper_bound=upper_bound)
    note = "보정 표본이 겹침"
    if np.median(v) >= np.median(o):
        note += "; 빈자리 중앙값이 점유 중앙값 이상(특징 방향 가정 위반 가능)"
    low = float(np.percentile(v, 90))
    high = float(np.percentile(o, 10))
    if low >= high:
        mid = (low + high) / 2.0
        eps = max(1e-6, abs(mid) * 1e-6)
        low, high = max(0.0, mid - eps), mid + eps
        if upper_bound is not None:
            high = min(upper_bound, high)
        note += "; 보류 구간 없음(거의 단일 기준)"
    return Threshold(low, high, len(v), len(o), source, False, note, upper_bound)


def calibrate(samples: list[tuple[str, float, str]], min_per_class: int = 3,
              allow_pooled: bool = False, *,
              upper_bound: float | None = 1.0) -> tuple[dict[str, Threshold], list[str]]:
    """보정 표본 (slot_id, r, label)로 칸별 하한·상한을 정한다.

    unknown 표본은 쓰지 않는다. 한 상태라도 min_per_class 미만이면 그 칸은 기준을 만들지 않고
    insufficient 목록에 넣는다(데이터부터 보완). allow_pooled=True이면 전체 칸을 합친 기준을
    임시로 대신 쓰며 source="pooled"로 표시한다(코드 동작 확인용, 성능 보고용 아님).
    """
    if type(min_per_class) is not int or min_per_class < 1:
        raise ValueError("상태별 최소 표본 수는 양의 정수여야 합니다")
    per_slot: dict[str, dict[str, list[float]]] = {}
    for slot_id, r, label in samples:
        if label == "unknown":
            continue
        per_slot.setdefault(slot_id, {"free": [], "occupied": []})[label].append(r)
    thresholds: dict[str, Threshold] = {}
    insufficient: list[str] = []
    for slot_id, groups in sorted(per_slot.items()):
        if len(groups["free"]) >= min_per_class and len(groups["occupied"]) >= min_per_class:
            thresholds[slot_id] = _threshold_from(groups["free"], groups["occupied"], "slot", upper_bound)
        else:
            insufficient.append(slot_id)
    if allow_pooled and insufficient:
        all_v = [r for g in per_slot.values() for r in g["free"]]
        all_o = [r for g in per_slot.values() for r in g["occupied"]]
        if len(all_v) >= min_per_class and len(all_o) >= min_per_class:
            pooled = _threshold_from(all_v, all_o, "pooled", upper_bound)
            for slot_id in insufficient:
                thresholds[slot_id] = pooled
            insufficient = []
    return thresholds, insufficient


def decide(r: float, threshold: Threshold | None) -> str:
    """r <= 하한 빈자리, r >= 상한 점유, 그 사이 보류."""
    if threshold is None:
        return "unknown"
    if r <= threshold.low:
        return "free"
    if r >= threshold.high:
        return "occupied"
    return "unknown"


def _ratio(numerator: float, denominator: float):
    return None if denominator == 0 else numerator / denominator


def evaluate(pairs: list[tuple[str, str]]) -> dict:
    """(정답, 출력) 쌍으로 지표를 계산한다. 빈자리를 양성으로 둔다.

    정답 unknown은 분류 지표에서 제외하고 수만 센다. 분모가 0인 지표는 None(N/A)이다.
    빈자리 정답의 보류 출력은 FN에 포함한다. 보류를 제외한 정확도로 성능을 대신하지 않는다.
    """
    confusion = {gt: {p: 0 for p in STATES} for gt in ("free", "occupied")}
    n_unknown = 0
    for gt, pred in pairs:
        if gt not in STATES:
            raise ValueError(f"알 수 없는 정답 값: {gt}")
        if pred not in STATES:
            raise ValueError(f"알 수 없는 출력 값: {pred}")
        if gt == "unknown":
            n_unknown += 1
            continue
        confusion[gt][pred] += 1
    tp = confusion["free"]["free"]
    fp = confusion["occupied"]["free"]
    fn = confusion["free"]["occupied"] + confusion["free"]["unknown"]
    n_free = sum(confusion["free"].values())
    n_occupied = sum(confusion["occupied"].values())
    n_eval = n_free + n_occupied
    confirmed = sum(confusion[gt][p] for gt in confusion for p in ("free", "occupied"))
    return {
        "n_eval": n_eval,
        "n_gt_free": n_free,
        "n_gt_occupied": n_occupied,
        "n_gt_unknown_excluded": n_unknown,
        "confusion": confusion,
        "tp": tp, "fp": fp, "fn": fn,
        "precision": _ratio(tp, tp + fp),
        "recall": _ratio(tp, tp + fn),
        "f1": _ratio(2 * tp, 2 * tp + fp + fn),
        "false_vacant_rate": _ratio(fp, n_occupied),
        "confirmed_ratio": _ratio(confirmed, n_eval),
        "hold_ratio": _ratio(sum(confusion[gt]["unknown"] for gt in confusion), n_eval),
    }


def evaluate_samples(samples, thresholds):
    """칸별 임계값을 적용한다. 미보정 칸의 검증 표본도 보류로 집계한다."""
    pairs = [(truth, decide(r, thresholds.get(slot))) for slot, r, truth in samples]
    metrics = evaluate(pairs)
    metrics["n_eval_without_threshold"] = sum(
        slot not in thresholds and truth != "unknown" for slot, _, truth in samples)
    return metrics
