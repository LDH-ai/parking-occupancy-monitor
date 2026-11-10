"""OpenCV mouse editor; editing state is separate from the window."""
from copy import deepcopy
from pathlib import Path

import cv2
import numpy as np

from .roi import check_source, draw_roi, load_roi, read_frame, save_roi, source_hash, validate_roi


class EditorState:
    def __init__(self, document, zone="A", prefix="S"):
        self.document = deepcopy(validate_roi(document, allow_empty=True))
        self.zone, self.prefix = zone, prefix
        self.pending = []
        self.dirty = False

    def add_point(self, x, y):
        width, height = self.document["reference_size"]
        if not (0 <= x < width and 0 <= y < height):
            return
        candidate = self.pending + [[int(x), int(y)]]
        if len(candidate) == 4:
            ids = {slot["slot_id"] for slot in self.document["slots"]}
            number = 1
            while f"{self.prefix}{number:02d}" in ids:
                number += 1
            slot = {"slot_id": f"{self.prefix}{number:02d}", "zone": self.zone, "vertices": candidate}
            updated = deepcopy(self.document)
            updated["slots"].append(slot)
            validate_roi(updated)
            self.document = updated
            self.pending = []
        else:
            self.pending = candidate
        self.dirty = True

    def undo(self):
        if self.pending:
            self.pending.pop()
        elif self.document["slots"]:
            self.pending = self.document["slots"].pop()["vertices"][:3]
        else:
            return
        self.dirty = True

    def delete_last(self):
        if self.pending:
            self.pending = []
            self.dirty = True
        elif self.document["slots"]:
            self.document["slots"].pop()
            self.dirty = True

    def save(self, path):
        if self.pending:
            raise ValueError("Finish four points or press D to cancel the pending slot")
        self.document["status"] = "draft_manual_roi"
        save_roi(path, self.document)
        self.dirty = False


def pick_roi(video, output, video_id=None, frame_id=0, zone="A", prefix="S"):
    if Path(video).resolve() == Path(output).resolve() or Path(output).suffix.lower() != ".json":
        raise ValueError("ROI output must be a separate JSON file")
    frame = read_frame(video, frame_id)
    size = [frame.shape[1], frame.shape[0]]
    if Path(output).exists():
        document = load_roi(output, allow_empty=True)
        check_source(document, video)
        if document["reference_size"] != size:
            raise ValueError("Existing ROI uses another reference resolution")
        if video_id and document.get("source", {}).get("video_id") != video_id:
            raise ValueError("video-id differs from existing ROI")
    else:
        document = {"schema_version": 1, "status": "draft_manual_roi", "reference_size": size,
                    "source": {"video_id": video_id or Path(video).stem, "video_sha256": source_hash(video),
                               "annotation_frame_id": frame_id}, "slots": []}
    state = EditorState(document, zone, prefix)
    # AUTOSIZE keeps mouse coordinates tied to the displayed pixel grid.
    scale = min(1.0, 1280 / size[0], 700 / size[1])
    dw, dh = round(size[0] * scale), round(size[1] * scale)
    message = "Click four corners around each bay. ROI outlines are NOT occupancy predictions."
    quit_armed = False
    title = "Parking ROI editor"
    cv2.namedWindow(title, cv2.WINDOW_AUTOSIZE)

    def mouse(event, x, y, flags, userdata):
        nonlocal message, quit_armed
        try:
            if event == cv2.EVENT_LBUTTONDOWN and 0 <= x < dw and 80 <= y < dh + 80:
                state.add_point(min(size[0] - 1, int(x * size[0] / dw)),
                                min(size[1] - 1, int((y - 80) * size[1] / dh)))
                message = "Corner added" if state.pending else "Slot added; S saves"
                quit_armed = False
            elif event == cv2.EVENT_RBUTTONDOWN:
                state.undo()
        except ValueError as error:
            message = str(error)

    cv2.setMouseCallback(title, mouse)
    try:
        while True:
            image = draw_roi(frame, state.document)
            if state.pending:
                points = np.array(state.pending, dtype=np.int32)
                cv2.polylines(image, [points], False, (255, 150, 0), 2)
                for point in points:
                    cv2.circle(image, tuple(point), 4, (255, 150, 0), -1)
            canvas = np.zeros((dh + 80, dw, 3), dtype=np.uint8)
            canvas[80:] = cv2.resize(image, (dw, dh))
            disk_state = "UNSAVED" if state.dirty else ("saved" if Path(output).exists() else "NEW - NOT SAVED")
            for i, text in enumerate([f"Slots: {len(state.document['slots'])} / target 10-20 | Pending: {len(state.pending)}/4 | {disk_state}",
                                      "Left: corner | Right/U: undo | D: delete last/cancel | S: save | Q/ESC: quit", message]):
                cv2.putText(canvas, text, (8, 20 + i * 24), cv2.FONT_HERSHEY_SIMPLEX, .46, (230, 230, 230), 1)
            cv2.imshow(title, canvas)
            key = cv2.waitKey(30) & 0xFF
            if cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1:
                break
            try:
                if key in (ord("s"), ord("S")):
                    state.save(output)
                    message = f"Saved {len(state.document['slots'])} slots. Reopen this command to reload."
                    quit_armed = False
                elif key in (ord("u"), ord("U")):
                    state.undo()
                    quit_armed = False
                elif key in (ord("d"), ord("D")):
                    state.delete_last()
                    quit_armed = False
                elif key in (27, ord("q"), ord("Q")):
                    if state.dirty and not quit_armed:
                        message = "Unsaved edits: S saves; Q/ESC again discards."
                        quit_armed = True
                    else:
                        break
            except (ValueError, OSError) as error:
                message = str(error)
    finally:
        cv2.destroyWindow(title)
    return {"saved_file": str(output) if Path(output).exists() else None,
            "unsaved_changes": state.dirty}
