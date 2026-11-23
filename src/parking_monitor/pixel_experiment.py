"""저장 영상의 픽셀 비율을 추출하고 형태학 설정을 비교한다."""

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass, replace
import math
from pathlib import Path

import cv2
import numpy as np

from .baseline import LabelRow, calibrate, evaluate_samples, read_labels
from .baseline_report import write_results
from .pixel_ratio import MORPHOLOGY_CHOICES, frame_ratios, pixel_ratios, postprocess, preprocess
from .roi import check_source, load_roi, roi_masks, source_hash
from .splits import validate_blocks
from .video import decoded_frames, open_video


DEVELOPMENT_SPLITS = {"calibration", "validation"}
LABEL_TIME_TOLERANCE_S = 0.000501
CODE_FILES = ("baseline.py", "baseline_report.py", "pixel_ratio.py", "pixel_experiment.py",
              "pixel_baseline_cli.py", "roi.py", "splits.py", "video.py")


@dataclass(frozen=True)
class PixelSample:
    label: LabelRow
    split: str
    ratios: dict[str, float]

    def feature(self, morphology):
        return self.label.slot_id, self.ratios[morphology], self.label.label


@dataclass(frozen=True)
class Measurements:
    samples: list[PixelSample]
    series: dict[int, dict[str, float]]
    omitted: Counter
    fps: float
    frames_read: int


def _read_blocks(path, video_id):
    with open(path, newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        required = {"video_id", "session_id", "split", "start_s", "end_s"}
        if not required <= set(reader.fieldnames or []):
            raise ValueError("분할 CSV 열은 video_id, session_id, split, start_s, end_s가 필요합니다")
        blocks = [row for row in reader if row["video_id"] == video_id]
    if not blocks:
        raise ValueError(f"분할 CSV에 영상 '{video_id}'의 구간이 없습니다")
    for row in blocks:
        try:
            row["start_s"] = float(row["start_s"])
            row["end_s"] = float(row["end_s"])
        except (TypeError, ValueError) as error:
            raise ValueError(f"분할 구간의 시작·끝 시각이 잘못됐습니다: {video_id}") from error
    return blocks


def _split_at(timestamp, blocks):
    if blocks is None:
        return "all"
    return next((row["split"] for row in blocks
                 if row["start_s"] <= timestamp < row["end_s"]), None)


def _group_labels(labels, fps, blocks, masks):
    by_frame = defaultdict(list)
    omitted = Counter()
    for label in sorted(labels, key=lambda row: (row.frame_id, row.slot_id)):
        timestamp = label.frame_id / fps
        if abs(timestamp - label.timestamp_s) > LABEL_TIME_TOLERANCE_S:
            raise ValueError(f"{label.video_id} 프레임 {label.frame_id}: 정답 시각과 frame_id/FPS가 다릅니다")
        split = _split_at(timestamp, blocks)
        if split == "all" or split in DEVELOPMENT_SPLITS:
            by_frame[label.frame_id].append((label, split))
        else:
            omitted[split or "outside"] += 1

    unknown_slots = {label.slot_id for entries in by_frame.values() for label, _ in entries} - masks.keys()
    if unknown_slots:
        raise ValueError(f"ROI에 없는 칸이 정답에 있습니다: {sorted(unknown_slots)}")
    return by_frame, omitted


def _measure(video, roi, labels, blocks, config, timeseries):
    width, height = roi["reference_size"]
    masks = roi_masks(roi, (width, height))
    variants = [replace(config, morphology=name) for name in MORPHOLOGY_CHOICES]
    samples, series = [], {}
    frames_read = 0

    with open_video(video) as capture:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError(f"영상 FPS를 확인할 수 없습니다: {video}")
        by_frame, omitted = _group_labels(labels, fps, blocks, masks)
        for frame_id, frame in enumerate(decoded_frames(capture)):
            frames_read = frame_id + 1
            if frame.shape[:2] != (height, width):
                raise ValueError(f"프레임 {frame_id}의 해상도가 ROI 기준 해상도와 다릅니다")
            record_series = timeseries and (
                blocks is None or _split_at(frame_id / fps, blocks) in DEVELOPMENT_SPLITS)
            entries = by_frame.get(frame_id)
            if not entries:
                if record_series:
                    series[frame_id] = frame_ratios(frame, masks, config)
                continue

            binary = preprocess(frame, config)
            labeled_masks = {label.slot_id: masks[label.slot_id] for label, _ in entries}
            ratios_by_morph = {}
            for variant in variants:
                name = variant.morphology
                filtered = postprocess(binary, variant)
                include_all_slots = name == config.morphology and record_series
                ratios = pixel_ratios(filtered, masks if include_all_slots else labeled_masks)
                ratios_by_morph[name] = ratios
                if include_all_slots:
                    series[frame_id] = ratios
            for label, split in entries:
                ratios = {name: values[label.slot_id] for name, values in ratios_by_morph.items()}
                samples.append(PixelSample(label, split, ratios))

    if not frames_read:
        raise ValueError(f"첫 프레임을 읽을 수 없습니다: {video}")
    if blocks is not None:
        source = roi["source"]
        validate_blocks(blocks, {source["video_id"]: {"fps": fps, "decoded_frames": frames_read,
                                                      "sha256": source["video_sha256"]}})
    missing = sorted({label.frame_id for label in labels if label.frame_id >= frames_read})
    if missing:
        raise ValueError(f"영상에서 읽지 못한 정답 프레임이 있습니다: {missing[:10]}")
    return Measurements(samples, series, omitted, fps, frames_read)


def _compare(samples, calibration_split, eval_split, min_per_class, allow_pooled):
    calibration = [sample for sample in samples if sample.split == calibration_split]
    validation = [sample for sample in samples if sample.split == eval_split]
    comparisons = {}
    for name in MORPHOLOGY_CHOICES:
        thresholds, _ = calibrate([sample.feature(name) for sample in calibration],
                                  min_per_class, allow_pooled)
        features = [sample.feature(name) for sample in validation]
        comparisons[name] = (thresholds, features, evaluate_samples(features, thresholds))
    return comparisons


def _run_info(roi, labels_path, roi_path, splits_path, config, measurements,
              min_per_class, allow_pooled, pilot, timeseries, warnings):
    source = roi["source"]
    hashes = {"video": source["video_sha256"], "roi": source_hash(roi_path),
              "labels": source_hash(labels_path)}
    if splits_path is not None:
        hashes["splits"] = source_hash(splits_path)
    width, height = roi["reference_size"]
    return {
        "video_id": source["video_id"],
        "video": {"width": width, "height": height, "fps_reported": measurements.fps,
                  "frames_read": measurements.frames_read},
        "inputs_sha256": hashes,
        "config": config.to_dict(),
        "calibration": {"min_per_class": min_per_class, "allow_pooled": allow_pooled},
        "in_sample_evaluation": pilot,
        "timeseries": timeseries,
        "label_counts": dict(sorted(Counter(sample.split for sample in measurements.samples).items())),
        "omitted_label_counts": dict(sorted(measurements.omitted.items())),
        "code_sha256": {name: source_hash(Path(__file__).with_name(name)) for name in CODE_FILES},
        "versions": {"opencv": cv2.__version__, "numpy": np.__version__},
        "warnings": warnings,
    }


def run_baseline(video, roi_path, labels_path, out_dir, config, *, splits_path=None,
                 pilot=False, min_per_class=3, allow_pooled=False, timeseries=False):
    if pilot == (splits_path is not None):
        raise ValueError("--splits 또는 --pilot 중 하나를 지정하세요")
    if allow_pooled and not pilot:
        raise ValueError("--allow-pooled는 --pilot에서만 사용할 수 있습니다")
    if type(min_per_class) is not int or min_per_class < 1:
        raise ValueError("상태별 최소 표본 수는 양의 정수여야 합니다")
    out = Path(out_dir)
    if out.exists():
        raise ValueError(f"결과 폴더가 이미 있습니다. 새 경로를 지정하세요: {out}")

    roi = load_roi(roi_path)
    check_source(roi, video)
    video_id = roi["source"].get("video_id")
    if not isinstance(video_id, str) or not video_id.strip():
        raise ValueError("ROI의 source.video_id를 지정하세요")
    labels = [row for row in read_labels(labels_path) if row.video_id == video_id]
    if not labels:
        raise ValueError(f"정답 CSV에 영상 '{video_id}'의 행이 없습니다")
    blocks = None if pilot else _read_blocks(splits_path, video_id)
    measurements = _measure(video, roi, labels, blocks, config, timeseries)

    calibration_split, eval_split = ("all", "all") if pilot else ("calibration", "validation")
    comparisons = _compare(measurements.samples, calibration_split, eval_split,
                           min_per_class, allow_pooled)
    thresholds, _, scores = comparisons[config.morphology]
    slot_ids = [slot["slot_id"] for slot in roi["slots"]]
    metrics = {
        **scores,
        "video_id": video_id,
        "eval_split": eval_split,
        "n_target_slots": len(slot_ids),
        "n_slots_with_own_threshold": sum(threshold.source == "slot" for threshold in thresholds.values()),
        "slots_without_threshold": sorted(set(slot_ids) - thresholds.keys()),
    }
    warnings = []
    if pilot:
        warnings.append("표본 내 파일럿입니다. 같은 정답으로 보정하고 평가하므로 성능 근거로 사용할 수 없습니다.")
    if not metrics["n_eval"]:
        warnings.append("평가할 확정 정답이 없어 지표를 산출하지 않았습니다.")
    if metrics["slots_without_threshold"]:
        warnings.append("일부 칸의 보정 표본이 부족합니다. 해당 칸의 출력은 보류입니다.")

    run_info = _run_info(roi, labels_path, roi_path, splits_path, config, measurements,
                         min_per_class, allow_pooled, pilot, timeseries, warnings)
    write_results(out, measurements, comparisons, metrics, run_info, slot_ids)
    return {"out": str(out), "metrics": metrics, "warnings": warnings}
