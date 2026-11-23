"""Validate frozen split inputs and regenerate candidate indices in tmp/."""
from collections import Counter
import csv
import json
from pathlib import Path

from parking_monitor.roi import source_hash
from parking_monitor.splits import sample_frames, validate_blocks

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / "data/manifests"
OUTPUT = ROOT / "tmp/split_review"


def main():
    splits_path = MANIFESTS / "splits.csv"
    policy = json.loads((MANIFESTS / "split_policy.json").read_text(encoding="utf-8"))
    if source_hash(splits_path) != policy["splits_sha256"]:
        raise ValueError("Split list changed; review and version the split policy")
    with splits_path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    validation = json.loads((MANIFESTS / "sample_validation.json").read_text(encoding="utf-8"))
    metadata = {item["video_id"]: item for item in validation["assets"] if item["kind"] == "video"}
    validate_blocks(rows, metadata, minimum_gap_s=policy["minimum_gap_s"])
    with (MANIFESTS / "videos.csv").open(encoding="utf-8", newline="") as stream:
        videos = {row["video_id"]: row for row in csv.DictReader(stream)}
    for row in rows:
        if row["session_id"] != videos[row["video_id"]]["session_id"]:
            raise ValueError("Split group differs from video manifest")
    # Recheck content identity before trusting recorded frame counts.
    for video_id in {row["video_id"] for row in rows}:
        path = ROOT / metadata[video_id]["local_path"]
        if source_hash(path) != metadata[video_id]["sha256"]:
            raise ValueError(f"Video content changed: {video_id}")
    samples = [sample for row in rows
               for sample in sample_frames(row, float(metadata[row["video_id"]]["fps"]),
                                           interval_s=policy["sample_interval_s"])]
    keys = [(sample["video_id"], sample["frame_id"]) for sample in samples]
    if len(keys) != len(set(keys)):
        raise ValueError("Repeated sampled frame")
    rights = json.loads((MANIFESTS / "rights_review.json").read_text(encoding="utf-8"))
    clearance = {row["video_id"]: row["approved_for_final_dataset"] for row in rights["videos"]}
    counts = dict(Counter(sample["split"] for sample in samples))
    report = {"status": policy["status"], "mechanical_validation": "passed",
              "split_blocks": len(rows), "sample_counts": counts,
              "test_frame_goal": 200, "test_frame_shortfall": max(0, 200 - counts.get("test", 0)),
              "all_sources_cleared": all(clearance.get(row["video_id"], False) for row in rows),
              "source_adoption_basis": rights.get("conclusion"),
              "event_boundary_review": policy["event_boundary_review"],
              "note": "Candidate frame indices only; no ground-truth labels or occupancy balance established."}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / "frame_samples.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["video_id", "session_id", "split", "frame_id", "timestamp_s"])
        writer.writeheader()
        writer.writerows(samples)
    (OUTPUT / "split_validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
