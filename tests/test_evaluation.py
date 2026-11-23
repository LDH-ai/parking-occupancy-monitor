import csv
import json

import cv2
import numpy as np
import pytest

from evaluation.engine import Stabilizer
from parking_monitor.baseline import calibrate
from parking_monitor.cli import main
from parking_monitor.roi import save_roi, source_hash


def _clip(folder, name, fps, frame_count, occupied, *, marker=0):
    video = folder / f"{name}.avi"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), fps, (80, 60))
    assert writer.isOpened()
    try:
        for frame_id in range(frame_count):
            frame = np.full((60, 80, 3), 230, dtype=np.uint8)
            if frame_id in occupied:
                frame[15:32, 15:30] = 0
            frame[48:, 58:] = marker
            writer.write(frame)
    finally:
        writer.release()
    roi = folder / f"{name}.json"
    save_roi(roi, {
        "schema_version": 1, "reference_size": [80, 60],
        "source": {"video_id": name, "video_sha256": source_hash(video)},
        "slots": [{"slot_id": "S1", "zone": "north", "vertices": [[5, 5], [45, 5], [45, 41], [5, 41]]}],
    })
    return video, roi


def _csv(path, headings, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(headings)
        writer.writerows(rows)


def _rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def test_stabilizer_uses_seconds_and_holds_again_after_candidate_change():
    state = Stabilizer(0.5)
    assert state.update("S1", "free", 0.0) == "unknown"
    assert state.update("S1", "free", 0.49) == "unknown"
    assert state.update("S1", "free", 0.5) == "free"
    assert state.update("S1", "occupied", 0.6) == "unknown"
    assert state.update("S1", "free", 0.7) == "unknown"
    assert state.update("S1", "free", 1.2) == "free"
    assert Stabilizer(0.5).update("S1", "free", 11.2) == "unknown"


def test_laplacian_calibration_supports_overlapping_values_above_one():
    samples = [("S1", value, truth) for truth in ("free", "occupied") for value in (12.0, 16.0, 19.0)]
    threshold, missing = calibrate(samples, upper_bound=None)
    assert missing == []
    assert 1 < threshold["S1"].low < threshold["S1"].high


def test_validate_freeze_and_test_with_separate_clips_and_labels(tmp_path):
    clip, roi = _clip(tmp_path, "school_a", 10, 160, {*range(8, 20), *range(130, 145)})
    manifest = tmp_path / "experiment.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "videos": [
            {"video_id": "school_a", "view_id": "front", "path": clip.name, "roi": roi.name},
            {"video_id": "school_b", "view_id": "front", "path": "school_b.avi", "roi": "school_b.json"},
        ],
        "splits": "splits.csv",
        "labels": {"calibration": "calibration.csv", "validation": "validation.csv", "test": "test.csv"},
        "events": {"validation": "validation_events.csv", "test": "test_events.csv"},
    }), encoding="utf-8")
    splits = tmp_path / "splits.csv"
    _csv(splits, ["video_id", "session_id", "split", "start_s", "end_s"], [
        ("school_a", "session_a", "calibration", 0, 2),
        ("school_a", "session_a", "validation", 12, 16),
        ("school_b", "session_b", "test", 0, 4),
    ])
    labels = ["video_id", "frame_id", "timestamp_s", "slot_id", "label"]
    event_fields = ["event_id", "video_id", "slot_id", "direction", "frame_id",
                    "observe_start_frame", "observe_end_frame"]
    calibration = [("school_a", i, i / 10, "S1", "free" if i < 8 else "occupied")
                   for i in (0, 2, 4, 10, 12, 14)]
    validation = [("school_a", i, i / 10, "S1", state)
                  for i, state in ((127, "free"), (137, "occupied"), (154, "free"), (155, "unknown"))]
    _csv(tmp_path / "calibration.csv", labels, calibration)
    _csv(tmp_path / "validation.csv", labels, validation)
    _csv(tmp_path / "validation_events.csv", event_fields, [
        ("entry-a", "school_a", "S1", "entry", 130, 120, 144),
        ("exit-a", "school_a", "S1", "exit", 145, 139, 160),
    ])

    validation_out = tmp_path / "validation"
    validate = ["evaluate", "validate", "--manifest", str(manifest), "--out", str(validation_out)]
    assert main(validate) == 0
    scores = {row["candidate_id"]: row for row in _rows(validation_out / "comparison.csv")}
    assert set(scores) == {"A", "A-CC", "B", "C", "D-0.5", "D-1.0", "D-CC-0.5", "D-CC-1.0"}
    assert all(row["n_eval"] == "3" for row in scores.values())
    non_temporal = [row for row in _rows(validation_out / "events.csv") if row["candidate_id"] == "C"]
    stable = [row for row in _rows(validation_out / "events.csv") if row["candidate_id"] == "D-0.5"]
    assert [float(row["delay_s"]) for row in non_temporal] == [0.0, 0.0]
    assert [float(row["delay_s"]) for row in stable] == [0.5, 0.5]

    baseline_labels = tmp_path / "baseline_labels.csv"
    baseline_out = tmp_path / "baseline"
    _csv(baseline_labels, labels, calibration + validation)
    assert main(["pixel-baseline", "--video", str(clip), "--roi", str(roi), "--labels", str(baseline_labels),
                 "--splits", str(splits), "--out", str(baseline_out)]) == 0
    baseline_predictions = {row["frame_id"]: (float(row["r"]), row["pred"])
                            for row in _rows(baseline_out / "predictions.csv") if row["split"] == "validation"}
    evaluated = {row["frame_id"]: (float(row["r"]), row["prediction"])
                 for row in _rows(validation_out / "predictions.csv") if row["candidate_id"] == "A" and row["gt"]}
    assert evaluated == baseline_predictions

    frozen = tmp_path / "frozen.json"
    assert main(["evaluate", "freeze", "--validation-run", str(validation_out), "--out", str(frozen)]) == 0
    saved = json.loads(frozen.read_text(encoding="utf-8"))
    assert saved["selection"]["meets_validation_requirements"]
    _clip(tmp_path, "school_b", 12, 48, range(14, 30), marker=110)
    _csv(tmp_path / "test.csv", labels, [("school_b", i, i / 12, "S1", state)
                                        for i, state in ((8, "free"), (23, "occupied"), (42, "free"))])
    _csv(tmp_path / "test_events.csv", event_fields, [
        ("entry-b", "school_b", "S1", "entry", 14, 0, 30),
        ("exit-b", "school_b", "S1", "exit", 30, 24, 48),
    ])
    test_out = tmp_path / "test"
    command = ["evaluate", "test", "--manifest", str(manifest), "--frozen", str(frozen),
               "--out", str(test_out)]
    assert main(command) == 0
    assert (test_out / "thresholds.json").read_bytes() == (validation_out / "thresholds.json").read_bytes()
    assert {row["video_id"] for row in _rows(test_out / "predictions.csv")} == {"school_b"}
    assert {row["event_id"] for row in _rows(test_out / "events.csv")} == {"entry-b", "exit-b"}
    assert any(row["selected"] == "True" for row in _rows(test_out / "comparison.csv"))
    info = json.loads((test_out / "run_info.json").read_text(encoding="utf-8"))
    assert info["sample_counts"]["classification_frames"] == 3
    assert info["warnings"] and info["event_labels_sha256"]
    assert saved["thresholds"]["B"]["front"]["laplacian"]["S1"]["high"] > 1
    assert main(command[:-1] + [str(tmp_path / "test-repeat")]) == 0
    for name in ("predictions.csv", "events.csv", "thresholds.json"):
        assert (test_out / name).read_bytes() == (tmp_path / "test-repeat" / name).read_bytes()

    with splits.open("a", encoding="utf-8") as stream:
        stream.write("\n")
    with pytest.raises(SystemExit):
        main(command[:-1] + [str(tmp_path / "test-after-change")])
    assert not (tmp_path / "test-after-change").exists()
