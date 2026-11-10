"""Verify downloaded assets, decode entire videos and register observed metadata."""
import csv
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT / "data/manifests/upstream_assets.json").read_text(encoding="utf-8"))
    records, rows, previews = [], [], []
    identifiers = {"faisal-ajao/parking-space-counter-opencv:video.mp4": "shared_carpark",
                   "olgarose/ParkingLot:parking_lot/videos/parking_lot_1.mp4": "olgarose_lot_1",
                   "olgarose/ParkingLot:parking_lot/videos/parking_lot_2.mp4": "olgarose_lot_2"}
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
            capture = cv2.VideoCapture(str(path))
            try:
                if not capture.isOpened():
                    raise ValueError(f"Cannot open video: {path}")
                fps = float(capture.get(cv2.CAP_PROP_FPS))
                expected = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
                if not np.isfinite(fps) or fps <= 0 or expected <= 0:
                    raise ValueError(f"Invalid video metadata: {path}")
                count, frames = 0, []
                wanted = {0, expected // 2}
                last_frame = None
                width, height = None, None
                while True:
                    ok, frame = capture.read()
                    if not ok:
                        break
                    if width is None:
                        height, width = frame.shape[:2]
                    if count in wanted:
                        frames.append(cv2.resize(frame, (320, 200)))
                    last_frame = frame
                    count += 1
                if count == 0:
                    raise ValueError(f"No decoded frames: {path}")
                frames.append(cv2.resize(last_frame, (320, 200)))
            finally:
                capture.release()
            video_id = identifiers[item["repository"] + ":" + item["source_path"]]
            result.update(video_id=video_id, width=width, height=height, fps=fps,
                          reported_frames=expected, decoded_frames=count,
                          duration_s=count / fps,
                          full_decode="ok" if count == expected else "frame_count_mismatch",
                          metadata_note="" if count == expected else
                          "Decoded until read failure/EOF; reported and decoded counts differ. Use decoded count and inspect tail before evaluation.")
            preview = np.hstack(frames)
            cv2.putText(preview, video_id + " | first / middle / last", (5, 18),
                        cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 255, 255), 1)
            previews.append(preview)
            # Session independence and capture date cannot be inferred from filenames.
            rows.append({"video_id": video_id, "source_url": item["url"],
                         "local_path": item["local_path"], "session_id": "",
                         "width": width, "height": height, "fps": fps,
                         "captured_at": "", "usage_terms": item["usage_terms"]})
        records.append(result)
    csv_path = ROOT / "data/manifests/videos.csv"
    fields = ["video_id", "source_url", "local_path", "session_id", "width", "height", "fps", "captured_at", "usage_terms"]
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        existing = list(csv.DictReader(stream))
    by_id = {row["video_id"]: row for row in existing}
    for row in rows:
        row = {field: str(value) for field, value in row.items()}
        if row["video_id"] in by_id:
            # Preserve human-reviewed rights, capture dates and session assignments.
            for field in ("usage_terms", "session_id", "captured_at"):
                row[field] = by_id[row["video_id"]][field]
        if row["video_id"] in by_id and by_id[row["video_id"]] != row:
            raise ValueError(f"Existing video record differs: {row['video_id']}")
        by_id[row["video_id"]] = row
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(by_id.values())
    (ROOT / "data/manifests/sample_validation.json").write_text(
        json.dumps({"checked_on": "2026-11-02", "assets": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output = ROOT / "tmp/sample_review"
    output.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".jpg", np.vstack(previews))
    if not ok:
        raise ValueError("Cannot encode preview")
    encoded.tofile(output / "video_contact_sheet.jpg")
    print(json.dumps({"unique_assets": len(records), "total_bytes": sum(r["bytes"] for r in records),
                      "videos": [r for r in records if r["kind"] == "video"]}, indent=2))


if __name__ == "__main__":
    main()
