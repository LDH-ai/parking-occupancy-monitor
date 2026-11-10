"""Verify the frozen stage10 development artifacts; optionally decode source videos."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

import cv2

from parking_monitor.roi import load_roi, roi_masks, source_hash
from parking_monitor.splits import sample_frames, validate_blocks

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def normalized_digest(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def validate(root=ROOT, with_videos=False):
    root = Path(root).resolve()
    freeze = read_json(root / "data/manifests/stage10.freeze.json")
    require(freeze["stage10_minimum_gate"] == "complete", "Stage10 gate is not accepted")
    require(freeze["digest_kind"] == "sha256_normalized_lf", "Unknown digest scheme")
    for name, expected in freeze["files"].items():
        path = (root / name).resolve()
        require(path.is_relative_to(root), "Frozen path escapes project")
        require(normalized_digest(path) == expected, f"Frozen artifact changed: {name}")
    report = read_json(root / "data/manifests/stage10_review.json")
    roi = load_roi(root / report["active_roi"])
    ids = [s["slot_id"] for s in roi["slots"]]
    require(ids == report["selected_slot_ids"] and 10 <= len(ids) <= 20,
            "Reviewed bay selection differs from accepted 10-20 bays")
    for size in (roi["reference_size"], [550, 360]):
        require(len(roi_masks(roi, tuple(size))) == len(ids), "ROI mask count differs")
    inventory = {r["video_id"]: r for r in read_csv(root / "data/manifests/videos.csv")}
    metadata = {r["video_id"]: r for r in read_json(root / "data/manifests/sample_validation.json")["assets"]
                if r["kind"] == "video"}
    source = roi["source"]["video_id"]
    require(roi["source"]["video_sha256"] == metadata[source]["sha256"], "ROI video identity differs")
    require(roi["reference_size"] == [int(inventory[source]["width"]), int(inventory[source]["height"])],
            "ROI reference resolution differs")
    blocks = read_csv(root / "data/manifests/splits.csv")
    policy = read_json(root / "data/manifests/split_policy.json")
    require(policy["split_list_frozen_for_stage10"] and not policy["frozen_for_final_evaluation"],
            "Incorrect scope of split freeze")
    validate_blocks(blocks, metadata, float(policy["minimum_gap_s"]))
    require(source_hash(root / "data/manifests/splits.csv") == policy["splits_sha256"], "Split byte hash differs")
    for block in blocks:
        require(block["session_id"] == inventory[block["video_id"]]["session_id"], "Clip grouping differs")
    samples = [s for b in blocks for s in sample_frames(b, float(metadata[b["video_id"]]["fps"]))]
    require([{k: str(v) for k, v in s.items()} for s in samples] == read_csv(root / "data/manifests/frame_samples.csv"),
            "Sampling list differs from split policy")
    labels = read_csv(root / report["reviewed_labels"])
    previous = read_csv(root / report["team_labels"])
    require(len(labels) == len(previous) == 30, "Pilot label count differs")
    require(len({(r["video_id"], r["frame_id"], r["slot_id"]) for r in labels}) == len(labels), "Duplicate label key")
    changes = {(c["frame_id"], c["slot_id"]): c for c in report["label_changes"]}
    observed_changes = set()
    for old, row in zip(previous, labels):
        require(all(old[k] == row[k] for k in ("video_id", "frame_id", "timestamp_s", "slot_id")),
                "Pilot key changed in review")
        require(row["video_id"] == source and row["slot_id"] in ids, "Label references unselected source/bay")
        frame = int(row["frame_id"])
        nominal = frame / float(metadata[source]["fps"])
        require(0 <= frame < metadata[source]["decoded_frames"], "Label frame outside decoded source")
        require(abs(float(row["timestamp_s"]) - nominal) <= .00051, "Label timestamp differs")
        require(any(b["video_id"] == source and b["split"] == "calibration"
                    and float(b["start_s"]) <= nominal < float(b["end_s"]) for b in blocks),
                "Reviewed pilot label is outside calibration")
        require(row["reviewed_by"] == "agent_visual_review", "Review provenance differs")
        require(row["label"] in {"free", "occupied", "unknown"}, "Unknown label value")
        if row["label"] != old["label"]:
            key = (frame, row["slot_id"])
            require(key in changes and changes[key]["from"] == old["label"] and changes[key]["to"] == row["label"]
                    and bool(row["reason"]), "Unrecorded label revision")
            observed_changes.add(key)
    require(observed_changes == set(changes), "Label change log differs")
    counts = dict(Counter(r["label"] for r in labels))
    require({k: counts.get(k, 0) for k in report["reviewed_label_counts"]} == report["reviewed_label_counts"],
            "Label class counts differ")
    handoff = read_json(root / "data/manifests/team_handoff_validation.json")
    for name, record in handoff["original_files"].items():
        require(source_hash(root / "data/handoffs/shared_carpark_2026-11-10" / name) == record["sha256"],
                f"Original team handoff changed: {name}")
    decoded = {}
    if with_videos:
        for video_id, item in metadata.items():
            video = root / item["local_path"]
            require(source_hash(video) == item["sha256"], f"Source video changed: {video_id}")
            capture = cv2.VideoCapture(str(video))
            count = 0
            try:
                require(capture.isOpened(), f"Cannot open {video_id}")
                while True:
                    ok, frame = capture.read()
                    if not ok:
                        break
                    require(list(frame.shape[:2][::-1]) == [item["width"], item["height"]],
                            f"Decoded resolution differs: {video_id}")
                    count += 1
            finally:
                capture.release()
            require(count == item["decoded_frames"], f"Decoded frame count differs: {video_id}")
            decoded[video_id] = count
    return {"stage10_minimum_gate": "complete", "scope": "reviewed development snapshot",
            "frozen_files_verified": len(freeze["files"]), "selected_bays": len(ids),
            "reviewed_pilot_rows": len(labels), "label_counts": counts,
            "split_sample_counts": dict(Counter(s["split"] for s in samples)),
            "video_decode_counts": decoded, "independent_human_review": False,
            "final_evaluation_frozen": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-videos", action="store_true", help="Hash and decode all local source videos")
    args = parser.parse_args()
    print(json.dumps(validate(with_videos=args.with_videos), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
