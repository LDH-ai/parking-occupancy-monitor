"""Verify downloaded assets and save a fresh sample inventory in tmp/."""

import csv
from datetime import date
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from parking_monitor.video import decoded_frames, open_video


ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / "data/manifests"
OUTPUT = ROOT / "tmp/sample_review"
VIDEO_IDS = {
    "faisal-ajao/parking-space-counter-opencv:video.mp4": "shared_carpark",
    "olgarose/ParkingLot:parking_lot/videos/parking_lot_1.mp4": "olgarose_lot_1",
    "olgarose/ParkingLot:parking_lot/videos/parking_lot_2.mp4": "olgarose_lot_2",
}
VIDEO_FIELDS = ("video_id", "source_url", "local_path", "session_id", "width", "height", "fps",
                "captured_at", "usage_terms")


def inspect_video(path, video_id):
    frames = []
    count = 0
    with open_video(path) as capture:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        expected = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if not np.isfinite(fps) or fps <= 0 or expected <= 0:
            raise ValueError(f"Invalid video metadata: {path}")
        wanted = {0, expected // 2}
        for frame_id, frame in enumerate(decoded_frames(capture)):
            if frame_id == 0:
                height, width = frame.shape[:2]
            if frame_id in wanted:
                frames.append(cv2.resize(frame, (320, 200)))
            count = frame_id + 1
        if count == 0:
            raise ValueError(f"No decoded frames: {path}")
        frames.append(cv2.resize(frame, (320, 200)))

    preview = np.hstack(frames)
    cv2.putText(preview, video_id + " | first / middle / last", (5, 18),
                cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 255, 255), 1)
    metadata = {
        "video_id": video_id, "width": width, "height": height, "fps": fps,
        "reported_frames": expected, "decoded_frames": count, "duration_s": count / fps,
        "full_decode": "ok" if count == expected else "frame_count_mismatch",
        "metadata_note": "" if count == expected else
        "Decoded until read failure/EOF; reported and decoded counts differ. Use decoded count and inspect tail before evaluation.",
    }
    return metadata, preview


def main():
    manifest = json.loads((MANIFESTS / "upstream_assets.json").read_text(encoding="utf-8"))
    with (MANIFESTS / "videos.csv").open(encoding="utf-8-sig", newline="") as stream:
        inventory = {row["video_id"]: row for row in csv.DictReader(stream)}

    records, previews = [], []
    for item in manifest["assets"]:
        if item["duplicate"]:
            continue
        path = ROOT / item["local_path"]
        raw = path.read_bytes()
        blob_hash = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
        if len(raw) != item["bytes"] or blob_hash != item["git_blob_sha1"]:
            raise ValueError(f"Integrity failure: {path}")
        result = {"local_path": item["local_path"], "kind": item["kind"],
                  "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        if item["kind"] == "image":
            with Image.open(path) as image:
                result.update(width=image.width, height=image.height, format=image.format)
                image.verify()
        elif item["kind"] == "video":
            video_id = VIDEO_IDS[item["repository"] + ":" + item["source_path"]]
            metadata, preview = inspect_video(path, video_id)
            result.update(metadata)
            previews.append(preview)

            reviewed = inventory.get(video_id, {})
            row = {"video_id": video_id, "source_url": item["url"], "local_path": item["local_path"],
                   "width": str(metadata["width"]), "height": str(metadata["height"]),
                   "fps": str(metadata["fps"]), "session_id": reviewed.get("session_id", ""),
                   "captured_at": reviewed.get("captured_at", ""),
                   "usage_terms": reviewed.get("usage_terms", item["usage_terms"])}
            if reviewed and reviewed != row:
                raise ValueError(f"Existing video record differs: {video_id}")
            inventory[video_id] = row
        records.append(result)

    ok, encoded = cv2.imencode(".jpg", np.vstack(previews))
    if not ok:
        raise ValueError("Cannot encode preview")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / "videos.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=VIDEO_FIELDS)
        writer.writeheader()
        writer.writerows(inventory.values())
    (OUTPUT / "sample_validation.json").write_text(
        json.dumps({"checked_on": date.today().isoformat(), "assets": records},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    encoded.tofile(OUTPUT / "video_contact_sheet.jpg")
    print(json.dumps({"unique_assets": len(records), "total_bytes": sum(r["bytes"] for r in records),
                      "videos": [r for r in records if r["kind"] == "video"]}, indent=2))


if __name__ == "__main__":
    main()
