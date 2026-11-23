"""저장 영상의 정량 평가, 검증 설정 동결 및 최종 테스트."""

import csv
from dataclasses import asdict
import json
import os
from pathlib import Path
import platform
from tempfile import TemporaryDirectory, NamedTemporaryFile

import cv2
import numpy as np

from parking_monitor.baseline import Threshold
from parking_monitor.roi import source_hash

from .engine import Stability, calibrate_candidates, measure_video, summarize_video
from .inputs import load_events, load_labels, load_videos, read_blocks, read_json, read_manifest


PREDICTION_FIELDS = ("candidate_id", "video_id", "frame_id", "timestamp_s", "slot_id", "gt", "r", "laplacian",
                     "candidate", "prediction", "evaluated", "missing_threshold")
EVENT_FIELDS = ("candidate_id", "event_id", "video_id", "slot_id", "direction", "frame_id", "timestamp_s",
                "confirmed_frame", "confirmed_s", "delay_s", "early", "missed")
CODE_FILES = ("parking_monitor/baseline.py", "parking_monitor/pixel_ratio.py", "parking_monitor/roi.py",
              "parking_monitor/splits.py", "parking_monitor/video.py", "evaluation/inputs.py",
              "evaluation/engine.py", "evaluation/runner.py")


def _code_hashes():
    source_root = Path(__file__).resolve().parents[1]
    return {name: source_hash(source_root / name) for name in CODE_FILES}


def _settings(manifest):
    return {"pixel_ratio": manifest.pixel.to_dict(),
            "laplacian": {"gaussian_kernel": list(manifest.laplacian_kernel), "ksize": manifest.laplacian_ksize},
            "min_per_class": manifest.min_per_class,
            "candidates": [asdict(item) for item in manifest.candidates]}


def _threshold_record(thresholds):
    return {candidate: {view: {branch: {slot: asdict(value) for slot, value in slots.items()}
                               for branch, slots in features.items()}
                        for view, features in views.items()}
            for candidate, views in thresholds.items()}


def _restore_thresholds(data):
    return {candidate: {view: {branch: {slot: Threshold(**value) for slot, value in slots.items()}
                               for branch, slots in features.items()}
                        for view, features in views.items()}
            for candidate, views in data.items()}


def _input_record(videos):
    return {key: {"video_sha256": video.video_sha256, "roi_sha256": video.roi_sha256,
                  "view_id": video.source.view_id, "width": video.size[0], "height": video.size[1],
                  "fps": video.fps, "decoded_frames": video.frame_count, "slots": len(video.masks)}
            for key, video in videos.items()}


def _json_text(data):
    return json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _write_rows(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _goal_results(metrics):
    return {"f1_at_least_0_90": None if metrics["f1"] is None else metrics["f1"] >= 0.90,
            "false_vacant_at_most_0_05": (None if metrics["false_vacant_rate"] is None
                                         else metrics["false_vacant_rate"] <= 0.05),
            "confirmed_at_least_0_95": (None if metrics["confirmed_ratio"] is None
                                       else metrics["confirmed_ratio"] >= 0.95)}


def _comparison_row(candidate, overall, selected):
    return {
        "candidate_id": candidate.id, "selected": candidate.id == selected,
        "method": candidate.method, "min_component_area_px": candidate.min_component_area_px,
        "stabilization_s": candidate.stabilization_s, "n_eval": overall["n_eval"],
        "f1": overall["f1"], "false_vacant_rate": overall["false_vacant_rate"],
        "confirmed_ratio": overall["confirmed_ratio"], "fps": overall["timing"]["fps"],
        "algorithm_median_ms": overall["timing"]["algorithm"]["median_ms"],
        "algorithm_p95_ms": overall["timing"]["algorithm"]["p95_ms"],
        "loop_median_ms": overall["timing"]["loop"]["median_ms"],
        "loop_p95_ms": overall["timing"]["loop"]["p95_ms"],
        "entry_median_delay_s": overall["events"]["entry"]["median_delay_s"],
        "exit_median_delay_s": overall["events"]["exit"]["median_delay_s"],
        "entry_missed": overall["events"]["entry"]["missed"],
        "exit_missed": overall["events"]["exit"]["missed"],
        "false_transitions_per_slot_minute": overall["events"]["false_transitions_per_slot_minute"],
        "hold_entries_per_slot_minute": overall["events"]["hold_entries_per_slot_minute"],
    }


def _measure_candidate(manifest, candidate, phases, phase, labels, events, thresholds, writer):
    aggregate_pairs, event_rows, algorithm_times, loop_times = [], [], [], []
    stability = Stability()
    missing_total = 0
    by_video = {}
    for video_id, video in phases.items():
        pairs, missing, rows, algorithm, loop, stats = measure_video(
            manifest, video, phase, labels.get(video_id, {}), events.get(video_id, []),
            candidate, thresholds.get(video.source.view_id, {}), writer,
        )
        by_video[video_id] = summarize_video(pairs, missing, rows, algorithm, loop, stats)
        aggregate_pairs.extend(pairs)
        event_rows.extend(rows)
        algorithm_times.extend(algorithm)
        loop_times.extend(loop)
        missing_total += missing
        stability.stable_seconds += stats.stable_seconds
        stability.false_transitions += stats.false_transitions
        stability.hold_entries += stats.hold_entries
    overall = summarize_video(aggregate_pairs, missing_total, event_rows, algorithm_times, loop_times, stability)
    return {"overall": overall, "by_video": by_video, "goals": _goal_results(overall)}, event_rows


def _load_state(manifest, phase, frozen_path):
    if phase == "validation":
        return None
    frozen = read_json(frozen_path)
    if frozen.get("schema_version") != 1 or frozen.get("source_phase") != "validation":
        raise ValueError("validate 결과에서 만든 동결 파일을 지정하세요")
    if frozen["manifest_sha256"] != source_hash(manifest.path) or frozen["splits_sha256"] != source_hash(manifest.splits):
        raise ValueError("평가 목록 또는 분할이 바뀌었습니다. 다시 검증하고 설정을 동결하세요")
    if frozen["settings"] != _settings(manifest) or frozen["code_sha256"] != _code_hashes():
        raise ValueError("동결 당시의 알고리즘 설정과 코드가 다릅니다")
    if frozen["selection"]["candidate_id"] not in {item.id for item in manifest.candidates}:
        raise ValueError("동결 파일에 올바른 시연 구성 ID가 필요합니다")
    if set(frozen["thresholds"]) != {item.id for item in manifest.candidates}:
        raise ValueError("동결 파일의 임계값과 비교 구성이 일치하지 않습니다")
    return frozen


def _sample_counts(labels, events, videos):
    values = [label for video in labels.values() for label in video.values()]
    spaced_frames = spaced_slot_frames = 0
    for video_id, video_labels in labels.items():
        fps = videos[video_id].fps
        frames = {}
        for (frame_id, _), truth in video_labels.items():
            frames[frame_id] = frames.get(frame_id, 0) + (truth != "unknown")
        last = None
        for frame_id, known in sorted(frames.items()):
            if known and (last is None or (frame_id - last) / fps + 1e-9 >= 1):
                spaced_frames += 1
                spaced_slot_frames += known
                last = frame_id
    return {"classification_frames": sum(len({frame for frame, _ in video}) for video in labels.values()),
            "labeled_slot_frames": len(values), "known_slot_frames": sum(value != "unknown" for value in values),
            "ground_truth_unknown": values.count("unknown"),
            "known_frames_at_least_one_second_apart": spaced_frames,
            "known_slot_frames_at_least_one_second_apart": spaced_slot_frames,
            "events": sum(len(video_events) for video_events in events.values())}


def _run_info(manifest, phase, labels, events, videos, geometries, frozen, frozen_path):
    sample_counts = _sample_counts(labels, events, videos)
    warnings = []
    if not sample_counts["known_slot_frames"]:
        warnings.append("확정 정답이 없습니다. 분류 지표를 계산할 수 없습니다.")
    if not sample_counts["events"]:
        warnings.append("입·출차 사건 정답이 없어 사건별 지연을 계산할 수 없습니다.")
    if phase == "test" and (sample_counts["known_frames_at_least_one_second_apart"] < 200
                            or sample_counts["known_slot_frames_at_least_one_second_apart"] < 2000
                            or sample_counts["events"] < 10):
        warnings.append("최종 테스트 목표 표본 규모(200프레임, 2000칸·프레임, 입·출차 10건)에 미달합니다.")
    input_phases = ("calibration", "validation") if phase == "validation" else ("test",)
    return {"schema_version": 1, "phase": phase, "manifest_sha256": source_hash(manifest.path),
            "splits_sha256": source_hash(manifest.splits), "settings": _settings(manifest),
            "inputs": _input_record(videos), "view_geometries": geometries,
            "labels_sha256": {name: source_hash(manifest.labels[name]) for name in input_phases},
            "event_labels_sha256": source_hash(manifest.events[phase]) if phase in manifest.events else None,
            "frozen_sha256": source_hash(frozen_path) if frozen is not None else None,
            "selection": frozen["selection"] if frozen is not None else None,
            "code_sha256": _code_hashes(), "sample_counts": sample_counts,
            "versions": {"python": platform.python_version(), "opencv": cv2.__version__, "numpy": np.__version__},
            "timing_profile": {"device": "CPU", "processor": platform.processor(), "display": False,
                               "csv_logging": True, "warmup_frames_per_video_up_to": 30,
                               "measured": "해당 구간의 디코딩, 검출, 판정, CSV 기록. 구간 밖 디코딩 제외"},
            "warnings": warnings}


def run_evaluation(manifest_path, out, *, phase, frozen_path=None):
    out = Path(out).resolve()
    if out.exists():
        raise ValueError(f"새 결과 폴더를 지정하세요: {out}")
    manifest = read_manifest(manifest_path)
    frozen = _load_state(manifest, phase, frozen_path)
    phases = {"calibration", "validation"} if phase == "validation" else {"test"}
    videos, geometries = load_videos(
        manifest, read_blocks(manifest), phases,
        known_geometries=frozen["view_geometries"] if frozen is not None else None,
        known_inputs=frozen["inputs"] if frozen is not None else None,
    )
    active = {key: video for key, video in videos.items() if any(block.split == phase for block in video.blocks)}
    if not active:
        raise ValueError(f"분할 CSV에 {phase} 구간을 지정하세요")
    labels = load_labels(manifest, videos, phase)
    events = load_events(manifest, videos, phase)
    if frozen is None:
        thresholds = calibrate_candidates(manifest, videos, load_labels(manifest, videos, "calibration"))
    else:
        thresholds = _restore_thresholds(frozen["thresholds"])
    info = _run_info(manifest, phase, labels, events, videos, geometries, frozen, frozen_path)
    selected = info["selection"]["candidate_id"] if info["selection"] else None

    out.parent.mkdir(parents=True, exist_ok=True)
    lock = out.with_name(f".{out.name}.lock")
    with lock.open("x"):
        pass
    try:
        with TemporaryDirectory(dir=out.parent) as tmp:
            staged = Path(tmp) / "run"
            staged.mkdir()
            scores, all_events, comparison = {}, [], []
            with (staged / "predictions.csv").open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream, lineterminator="\n")
                writer.writerow(PREDICTION_FIELDS)
                for candidate in manifest.candidates:
                    result, event_rows = _measure_candidate(
                        manifest, candidate, active, phase, labels, events, thresholds[candidate.id], writer,
                    )
                    scores[candidate.id] = result
                    all_events.extend(event_rows)
                    comparison.append(_comparison_row(candidate, result["overall"], selected))
            _write_rows(staged / "comparison.csv", list(comparison[0]), comparison)
            _write_rows(staged / "events.csv", EVENT_FIELDS, all_events)
            (staged / "metrics.json").write_text(_json_text(scores), encoding="utf-8", newline="\n")
            (staged / "run_info.json").write_text(_json_text(info), encoding="utf-8", newline="\n")
            (staged / "thresholds.json").write_text(_json_text(_threshold_record(thresholds)),
                                                    encoding="utf-8", newline="\n")
            if out.exists():
                raise ValueError(f"새 결과 폴더를 지정하세요: {out}")
            staged.rename(out)
    finally:
        lock.unlink()
    return {"phase": phase, "out": str(out), "candidate_count": len(comparison),
            "sample_counts": info["sample_counts"], "selected": selected, "warnings": info["warnings"]}


def _selection(scores, candidate_id, reason):
    eligible = [name for name, result in scores.items() if (
        result["goals"]["false_vacant_at_most_0_05"] and result["goals"]["confirmed_at_least_0_95"]
        and result["overall"]["f1"] is not None
    )]
    if eligible:
        selected = min(eligible, key=lambda name: (-scores[name]["overall"]["f1"],
                                                   scores[name]["overall"]["timing"]["loop"]["median_ms"], name))
        if candidate_id is not None and candidate_id != selected:
            raise ValueError(f"검증 선택 기준에 따른 구성은 {selected}입니다")
        explanation = "거짓 빈자리율·확정 비율 기준을 충족한 구성 중 F1과 전체 루프 시간으로 선정"
    else:
        if not any(result["overall"]["n_eval"] for result in scores.values()):
            raise ValueError("검증에 사용할 확정 정답이 없어 시연 구성을 선정할 수 없습니다")
        if candidate_id not in scores or not reason or not reason.strip():
            raise ValueError("검증 조건을 충족한 구성이 없습니다. --candidate와 --reason으로 절충안을 기록하세요")
        selected, explanation = candidate_id, reason.strip()
    goals = scores[selected]["goals"]
    return {"candidate_id": selected, "reason": explanation,
            "meets_validation_requirements": selected in eligible,
            "unmet_or_unavailable": [key for key in ("false_vacant_at_most_0_05", "confirmed_at_least_0_95")
                                     if not goals[key]]}


def freeze_evaluation(run, out, *, candidate_id=None, reason=None):
    run, out = Path(run), Path(out).resolve()
    old = read_json(run / "run_info.json")
    if old.get("schema_version") != 1 or old.get("phase") != "validation":
        raise ValueError("정량 평가 validate 실행의 결과 폴더를 지정하세요")
    scores = read_json(run / "metrics.json")
    thresholds = read_json(run / "thresholds.json")
    expected = {candidate["id"] for candidate in old["settings"]["candidates"]}
    if set(scores) != expected or set(thresholds) != expected:
        raise ValueError("검증 결과 파일의 구성 ID가 일치하지 않습니다")
    selection = _selection(scores, candidate_id, reason)
    frozen = {key: old[key] for key in ("schema_version", "manifest_sha256", "splits_sha256", "settings",
                                        "inputs", "view_geometries", "code_sha256")}
    frozen.update(source_phase="validation", selection=selection, thresholds=thresholds,
                  validation_metrics_sha256=source_hash(run / "metrics.json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=out.parent, delete=False) as stream:
        staged = Path(stream.name)
    try:
        staged.write_text(_json_text(frozen), encoding="utf-8", newline="\n")
        os.link(staged, out)
    except FileExistsError as error:
        raise ValueError(f"새 동결 파일 경로를 지정하세요: {out}") from error
    finally:
        staged.unlink()
    return {"out": str(out), "selection": selection}
