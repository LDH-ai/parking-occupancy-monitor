import csv
import json

import cv2
import numpy as np
import pytest

from parking_monitor.baseline import Threshold, calibrate, decide, evaluate, read_labels
from parking_monitor.cli import main
from parking_monitor.roi import save_roi, source_hash


def test_read_labels_repo_format_preserves_zero_based_frame(tmp_path):
    path = tmp_path / "labels.csv"
    path.write_text("video_id,frame_id,timestamp_s,slot_id,label,reason,reviewed_by\n"
                    "camera,0,0.000,A01,free,,me\ncamera,1,0.100,A02,unknown,가림,me\n",
                    encoding="utf-8-sig")
    rows = read_labels(path)
    assert [(r.video_id, r.frame_id, r.label) for r in rows] == [
        ("camera", 0, "free"), ("camera", 1, "unknown")]


@pytest.mark.parametrize("rows", ["v,1,0,A,maybe\n", "v,1,0,A,free\nv,1,0,A,occupied\n"])
def test_read_labels_rejects_bad_value_and_duplicates(tmp_path, rows):
    path = tmp_path / "labels.csv"
    path.write_text("video_id,frame_id,timestamp_s,slot_id,label\n" + rows, encoding="utf-8")
    with pytest.raises(ValueError):
        read_labels(path)


def test_calibrate_separable_sets_low_to_max_vacant_and_high_to_min_occupied():
    samples = [("A", 0.01, "free"), ("A", 0.03, "free"), ("A", 0.02, "free"),
               ("A", 0.30, "occupied"), ("A", 0.40, "occupied"), ("A", 0.35, "occupied")]
    th, insufficient = calibrate(samples)
    assert insufficient == [] and th["A"].separable
    assert th["A"].low == 0.03 and th["A"].high == 0.30 and th["A"].low < th["A"].high


def test_calibrate_flags_slot_missing_one_class():
    samples = [("A", 0.01, "free")] * 3 + [("B", 0.01, "free")] * 3 + [("B", 0.5, "occupied")] * 3
    th, insufficient = calibrate(samples)
    assert insufficient == ["A"] and "B" in th and "A" not in th


def test_calibrate_ignores_unknown_and_uses_pooled_only_when_allowed():
    samples = ([("A", 0.01, "free")] * 3 + [("A", 0.9, "unknown")] * 5
               + [("B", 0.01, "free")] * 3 + [("B", 0.5, "occupied")] * 3)
    th, insufficient = calibrate(samples, allow_pooled=True)
    assert insufficient == [] and th["A"].source == "pooled" and th["B"].source == "slot"


def test_calibrate_overlap_still_keeps_low_below_high():
    samples = [("A", r, "free") for r in (0.1, 0.2, 0.3)] + [("A", r, "occupied") for r in (0.1, 0.2, 0.3)]
    th, _ = calibrate(samples)
    assert not th["A"].separable and th["A"].low < th["A"].high


def test_threshold_rejects_low_not_below_high():
    with pytest.raises(ValueError):
        Threshold(0.2, 0.2, 1, 1, "slot", True)


def test_decide_boundaries_and_hold_zone():
    th = Threshold(0.05, 0.30, 3, 3, "slot", True)
    assert decide(0.05, th) == "free" and decide(0.0, th) == "free"
    assert decide(0.30, th) == "occupied" and decide(0.9, th) == "occupied"
    assert decide(0.06, th) == "unknown" and decide(0.29, th) == "unknown"


def test_evaluate_counts_hold_on_vacant_as_fn_and_excludes_unknown():
    pairs = [("free", "free"), ("free", "unknown"), ("free", "occupied"),
             ("occupied", "free"), ("occupied", "occupied"), ("occupied", "unknown"),
             ("unknown", "free")]
    m = evaluate(pairs)
    assert (m["tp"], m["fp"], m["fn"]) == (1, 1, 2)
    assert m["n_eval"] == 6 and m["n_gt_unknown_excluded"] == 1
    assert m["precision"] == 1 / 2 and m["recall"] == 1 / 3
    assert m["f1"] == 2 * 1 / (2 * 1 + 1 + 2)           # 2TP/(2TP+FP+FN)
    assert m["false_vacant_rate"] == 1 / 3               # FP / 실제 점유 3
    assert m["confirmed_ratio"] == 4 / 6                 # 보류 2개 제외


def test_evaluate_zero_denominators_are_none():
    m = evaluate([("occupied", "occupied"), ("occupied", "unknown")])
    assert m["precision"] is None and m["recall"] is None and m["f1"] is None
    assert m["false_vacant_rate"] == 0.0 and m["confirmed_ratio"] == 0.5
    empty = evaluate([("unknown", "unknown")])
    assert empty["n_eval"] == 0 and empty["confirmed_ratio"] is None and empty["false_vacant_rate"] is None


@pytest.mark.parametrize("pair", [("free", "invalid"), ("invalid", "free")])
def test_evaluate_rejects_bad_values(pair):
    with pytest.raises(ValueError):
        evaluate([pair])


def test_baseline_cli_uses_project_keys_and_holds_uncalibrated_slots(tmp_path):
    video = tmp_path / "input.avi"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48))
    assert writer.isOpened()
    try:
        for i in range(207):
            frame = np.full((48, 64, 3), 230, dtype=np.uint8)
            if i in {1, 103, 205}:
                frame[12:27, 10:22] = 0
            writer.write(frame)
    finally:
        writer.release()
    roi = tmp_path / "roi.json"
    save_roi(roi, {
        "schema_version": 1, "reference_size": [64, 48],
        "source": {"video_id": "camera", "video_sha256": source_hash(video)},
        "slots": [
            {"slot_id": "A", "zone": "A", "vertices": [[4, 4], [29, 4], [29, 40], [4, 40]]},
            {"slot_id": "B", "zone": "A", "vertices": [[35, 4], [60, 4], [60, 40], [35, 40]]},
        ],
    })
    splits = tmp_path / "splits.csv"
    splits.write_text("video_id,session_id,split,start_s,end_s\n"
                      "camera,session,calibration,0,0.2\n"
                      "camera,session,validation,10.2,10.5\n"
                      "camera,session,test,20.5,20.7\n", encoding="utf-8")
    labels = tmp_path / "labels.csv"
    labels.write_text("video_id,frame_id,timestamp_s,slot_id,label\n"
                      "camera,0,0,A,free\ncamera,1,0.1,A,occupied\n"
                      "camera,2,0.2,A,occupied\n"
                      "camera,102,10.2,A,free\ncamera,102,10.2,B,free\n"
                      "camera,103,10.3,A,occupied\ncamera,104,10.4,A,unknown\n"
                      "camera,205,20.5,A,free\n", encoding="utf-8")
    out = tmp_path / "result"
    assert main(["pixel-baseline", "--video", str(video), "--roi", str(roi), "--labels", str(labels),
                 "--splits", str(splits), "--out", str(out), "--min-per-class", "1", "--timeseries"]) == 0
    metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["video_id"] == "camera" and metrics["n_eval"] == 3
    assert metrics["n_gt_unknown_excluded"] == metrics["n_eval_without_threshold"] == 1
    assert metrics["slots_without_threshold"] == ["B"]
    assert metrics["confusion"]["free"] == {"free": 1, "occupied": 0, "unknown": 1}
    with (out / "predictions.csv").open(newline="", encoding="utf-8") as stream:
        predictions = list(csv.DictReader(stream))
    assert {int(row["frame_id"]) for row in predictions} == {0, 1, 102, 103, 104}
    assert next(row for row in predictions if row["slot_id"] == "B")["evaluated"] == "1"
    with (out / "morph_comparison.csv").open(newline="", encoding="utf-8") as stream:
        assert {(row["split"], row["n_eval"]) for row in csv.DictReader(stream)} == {("validation", "3")}
    with (out / "r_timeseries.csv").open(newline="", encoding="utf-8") as stream:
        assert {int(row["frame_id"]) for row in csv.DictReader(stream)} == {0, 1, 102, 103, 104}

    filtered_out = tmp_path / "filtered"
    min_area = 64 * 48 + 1
    assert main(["pixel-baseline", "--video", str(video), "--roi", str(roi), "--labels", str(labels),
                 "--splits", str(splits), "--out", str(filtered_out), "--min-per-class", "1",
                 "--min-component-area-px", str(min_area), "--timeseries"]) == 0
    run_info = json.loads((filtered_out / "run_info.json").read_text(encoding="utf-8"))
    assert run_info["config"]["min_component_area_px"] == min_area
    assert any(float(row["r"]) > 0 for row in predictions)
    with (filtered_out / "predictions.csv").open(newline="", encoding="utf-8") as stream:
        filtered_rows = list(csv.DictReader(stream))
        assert len(filtered_rows) == len(predictions)
        assert all(float(row["r"]) == 0 for row in filtered_rows)
    with (filtered_out / "morph_comparison.csv").open(newline="", encoding="utf-8") as stream:
        assert all(float(row["mean_r_occupied"]) == 0 for row in csv.DictReader(stream))
