"""Pick and preview parking-space ROIs in video.mp4."""

import json
from pathlib import Path

import cv2
import numpy as np


PROJECT = Path(__file__).resolve().parent
VIDEO = PROJECT / "video.mp4"
ROI = PROJECT / "roi.json"
WINDOW = "Parking ROI"


def read_frame(video, index):
    video.set(cv2.CAP_PROP_POS_FRAMES, index)
    ok, frame = video.read()
    if not ok:
        raise RuntimeError(f"Could not read frame {index + 1}")
    return frame


def save_roi(spaces, width, height):
    data = {
        "video": VIDEO.name,
        "reference_resolution": {"width": width, "height": height},
        "spaces": spaces,
    }
    ROI.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def draw_preview(frame, spaces, points, label, next_id):
    preview = frame.copy()
    saved_color = (0, 220, 0)
    for space in spaces:
        polygon = np.array(space["points"], dtype=np.int32)
        cv2.polylines(preview, [polygon], True, saved_color, 2)
        x, y = np.mean(polygon, axis=0).astype(int)
        cv2.putText(preview, space["id"], (int(x) - 17, int(y) + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, saved_color, 2, cv2.LINE_AA)
    color = (0, 255, 255)
    if len(points) >= 2:
        polygon = np.array(points, dtype=np.int32)
        cv2.polylines(preview, [polygon], len(points) == 4, color, 2)
    for number, point in enumerate(points, start=1):
        cv2.circle(preview, point, 4, color, -1)
        cv2.putText(preview, str(number), (point[0] + 6, point[1] - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
    cv2.rectangle(preview, (0, 0), (preview.shape[1], 60), (0, 0, 0), -1)
    cv2.putText(preview, f"{label} | Saved: {len(spaces)} | Next: {next_id} ({len(points)}/4)", (10, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)
    cv2.putText(preview, "1-9, 0: frame   Click: corner   U: undo   R: clear draft   S: save space   Q: quit",
                (10, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    return preview


def main():
    video = cv2.VideoCapture(str(VIDEO))
    try:
        frame_count = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
        if frame_count < 1:
            raise RuntimeError(f"Could not open {VIDEO}")
        frames = {}
        for position, digit in enumerate("1234567890"):
            index = round(position * (frame_count - 1) / 9)
            label = f"Key {digit} | Frame {index + 1}/{frame_count}"
            frames[ord(digit)] = (label, read_frame(video, index))
    finally:
        video.release()

    current = ord("1")
    height, width = frames[current][1].shape[:2]
    spaces = []
    points = []
    if ROI.exists():
        data = json.loads(ROI.read_text(encoding="utf-8"))
        if (data["video"] != VIDEO.name
                or data["reference_resolution"] != {"width": width, "height": height}):
            raise RuntimeError(f"{ROI.name} belongs to a different video or resolution.")
        spaces = data["spaces"]
    next_number = max((int(space["id"][1:]) for space in spaces), default=0) + 1

    def on_click(event, x, y, flags, userdata):
        if event == cv2.EVENT_LBUTTONDOWN and len(points) < 4:
            points.append((x, y))

    cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
    try:
        cv2.setMouseCallback(WINDOW, on_click)
        while True:
            next_id = f"A{next_number:02d}"
            label, frame = frames[current]
            cv2.imshow(WINDOW, draw_preview(frame, spaces, points, label, next_id))
            key = cv2.waitKey(30) & 0xFF
            if key in (ord("q"), 27) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
            if key in frames:
                current = key
            elif key == ord("u") and points:
                points.pop()
            elif key == ord("r"):
                points.clear()
            elif key == ord("s"):
                if len(points) == 4 and cv2.isContourConvex(np.array(points, dtype=np.int32)):
                    space = {"id": next_id, "zone": "A", "points": points.copy()}
                    save_roi([*spaces, space], width, height)
                    spaces.append(space)
                    points.clear()
                    next_number += 1
                    print(f"Saved {next_id} to {ROI}", flush=True)
                else:
                    print("Click four distinct corners in clockwise order before saving.", flush=True)
    finally:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
