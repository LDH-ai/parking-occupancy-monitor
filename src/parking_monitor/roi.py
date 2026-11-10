"""Validated quadrilateral ROI files and resolution-aware rendering."""
import hashlib
import json
import os
from pathlib import Path
import tempfile

import cv2
import numpy as np


def validate_roi(document, allow_empty=False):
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("ROI schema_version must be 1")
    size = document.get("reference_size")
    if not isinstance(size, list) or len(size) != 2 or any(type(x) is not int or x < 2 for x in size):
        raise ValueError("reference_size must be [width, height] positive integers")
    slots = document.get("slots")
    if not isinstance(slots, list) or (not slots and not allow_empty):
        raise ValueError("At least one completed parking slot is required")
    ids, polygons = set(), []
    for slot in slots:
        if not isinstance(slot, dict):
            raise ValueError("Invalid slot record")
        slot_id, zone = slot.get("slot_id"), slot.get("zone")
        if not isinstance(slot_id, str) or not slot_id.strip() or slot_id in ids:
            raise ValueError("slot_id must be nonempty and unique")
        if not isinstance(zone, str) or not zone.strip():
            raise ValueError("zone must be nonempty")
        points = slot.get("vertices")
        if not isinstance(points, list) or len(points) != 4:
            raise ValueError("Each slot needs four perimeter-ordered vertices")
        for point in points:
            if not isinstance(point, list) or len(point) != 2 or any(type(x) is not int for x in point):
                raise ValueError("Vertices must be integer [x,y] pairs")
            if not (0 <= point[0] < size[0] and 0 <= point[1] < size[1]):
                raise ValueError("Vertex outside reference image")
        polygon = np.array(points, dtype=np.int32)
        if len({tuple(p) for p in points}) != 4 or not cv2.isContourConvex(polygon):
            raise ValueError("Slot must be a convex non-crossing quadrilateral")
        if cv2.contourArea(polygon) < 4:
            raise ValueError("Slot has insufficient area")
        for other in polygons:
            area, _ = cv2.intersectConvexConvex(polygon.astype(np.float32), other.astype(np.float32))
            if area > 0.01:
                raise ValueError("Parking slots overlap")
        polygons.append(polygon)
        ids.add(slot_id)
    return document


def load_roi(path, allow_empty=False):
    with Path(path).open(encoding="utf-8-sig") as stream:
        return validate_roi(json.load(stream), allow_empty=allow_empty)


def save_roi(path, document):
    validate_roi(document)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # A partial write cannot replace the last valid configuration.
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, target)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()


def source_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check_source(document, video):
    expected = document.get("source", {}).get("video_sha256")
    if not expected or source_hash(video) != expected:
        raise ValueError("ROI source video hash missing or different; use the correct camera/video ROI")


def read_frame(video, frame_id=0):
    if type(frame_id) is not int or frame_id < 0:
        raise ValueError("frame must be a nonnegative integer")
    if not Path(video).is_file():
        raise ValueError(f"Video not found: {video}")
    capture = cv2.VideoCapture(str(video))
    try:
        if not capture.isOpened():
            raise ValueError(f"Cannot open video: {video}")
        if frame_id and not capture.set(cv2.CAP_PROP_POS_FRAMES, frame_id):
            raise ValueError("Cannot seek requested frame")
        ok, frame = capture.read()
        if not ok or frame is None:
            raise ValueError(f"Cannot decode frame {frame_id}")
        return frame
    finally:
        capture.release()


def scaled_polygons(document, target_size):
    validate_roi(document, allow_empty=True)
    width, height = target_size
    rw, rh = document["reference_size"]
    if width < 2 or height < 2 or abs(width / rw - height / rh) > 1 / min(rw, rh):
        raise ValueError("ROI resize must preserve image aspect ratio")
    result = []
    for slot in document["slots"]:
        points = np.rint(np.array(slot["vertices"], dtype=np.float64) * [width / rw, height / rh]).astype(np.int32)
        points[:, 0] = np.clip(points[:, 0], 0, width - 1)
        points[:, 1] = np.clip(points[:, 1], 0, height - 1)
        result.append(points)
    return result


def roi_masks(document, target_size):
    width, height = target_size
    masks = {}
    for slot, polygon in zip(document["slots"], scaled_polygons(document, target_size)):
        mask = np.zeros((height, width), dtype=np.uint8)
        cv2.fillPoly(mask, [polygon], 255)
        if not mask.any():
            raise ValueError("Empty ROI mask")
        masks[slot["slot_id"]] = mask
    return masks


def draw_roi(frame, document):
    output = frame.copy()
    for slot, polygon in zip(document["slots"], scaled_polygons(document, (frame.shape[1], frame.shape[0]))):
        cv2.polylines(output, [polygon], True, (0, 220, 255), 2)
        center = np.mean(polygon, axis=0).astype(int)
        cv2.putText(output, slot["slot_id"], tuple(center), cv2.FONT_HERSHEY_SIMPLEX, .45, (0, 0, 0), 3)
        cv2.putText(output, slot["slot_id"], tuple(center), cv2.FONT_HERSHEY_SIMPLEX, .45, (0, 220, 255), 1)
    return output


def preview_roi(video, roi, output, frame_id=0, width=None):
    document = load_roi(roi)
    check_source(document, video)
    frame = read_frame(video, frame_id)
    if [frame.shape[1], frame.shape[0]] != document["reference_size"]:
        raise ValueError("Source resolution differs from ROI reference_size")
    if width is not None:
        if width < 2:
            raise ValueError("Preview width must be at least 2")
        height = round(frame.shape[0] * width / frame.shape[1])
        frame = cv2.resize(frame, (width, height))
    masks = roi_masks(document, (frame.shape[1], frame.shape[0]))
    target = Path(output)
    if target.suffix.lower() not in (".png", ".jpg", ".jpeg"):
        raise ValueError("Preview output must be PNG or JPEG")
    if target.resolve() in {Path(video).resolve(), Path(roi).resolve()}:
        raise ValueError("Preview cannot overwrite input")
    image = draw_roi(frame, document)
    ok, encoded = cv2.imencode(target.suffix, image)
    if not ok:
        raise ValueError("Cannot encode preview")
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded.tofile(target)
    return {"slots": len(masks), "frame_id": frame_id, "size": [frame.shape[1], frame.shape[0]],
            "mask_pixels": {key: int(np.count_nonzero(value)) for key, value in masks.items()}, "output": str(target)}
