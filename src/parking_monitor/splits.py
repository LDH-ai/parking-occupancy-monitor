"""Time-block validation and reproducible frame sampling (zero-based frames)."""
from collections import defaultdict
import math


def validate_blocks(rows, metadata, minimum_gap_s=10.0):
    groups = defaultdict(list)
    sessions = {}
    hashes = {}
    for row in rows:
        video_id = row["video_id"]
        if video_id not in metadata:
            raise ValueError(f"Unknown video: {video_id}")
        item = metadata[video_id]
        fps = float(item["fps"])
        count = int(item["decoded_frames"])
        if not math.isfinite(fps) or fps <= 0 or count <= 0:
            raise ValueError("Invalid decoded video metadata")
        start, end = float(row["start_s"]), float(row["end_s"])
        if not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end <= count / fps:
            raise ValueError(f"Invalid time bounds: {video_id}")
        if row["split"] not in {"calibration", "validation", "test"}:
            raise ValueError("Unknown split")
        if not row["session_id"]:
            raise ValueError("Missing grouping identifier")
        if video_id in sessions and sessions[video_id] != row["session_id"]:
            raise ValueError("One clip cannot have multiple grouping identifiers")
        sessions[video_id] = row["session_id"]
        digest = item["sha256"]
        if digest in hashes and hashes[digest] != video_id:
            raise ValueError("Duplicate video content registered with another ID")
        hashes[digest] = video_id
        groups[video_id].append(row)
    for video_id, blocks in groups.items():
        blocks = sorted(blocks, key=lambda r: float(r["start_s"]))
        for left, right in zip(blocks, blocks[1:]):
            gap = float(right["start_s"]) - float(left["end_s"])
            if gap < minimum_gap_s - 1e-9:
                raise ValueError(f"Overlapping blocks or gap below {minimum_gap_s}s: {video_id}")
    return True


def sample_frames(row, fps, interval_s=1.0):
    if not math.isfinite(interval_s) or interval_s < 1:
        raise ValueError("Sample interval must be at least one second")
    # Always round upward so actual frame timestamps are at least 1s apart.
    first = math.ceil(float(row["start_s"]) * fps)
    stop = math.ceil(float(row["end_s"]) * fps)
    step = math.ceil(interval_s * fps)
    return [{"video_id": row["video_id"], "session_id": row["session_id"],
             "split": row["split"], "frame_id": frame_id,
             "timestamp_s": format(frame_id / fps, ".12f")}
            for frame_id in range(first, stop, step)]
