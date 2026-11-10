from copy import deepcopy
import json

import cv2
import numpy as np
import pytest

from parking_monitor.roi import (check_source, load_roi, preview_roi, roi_masks,
                                 save_roi, source_hash, validate_roi)
from parking_monitor.roi_editor import EditorState, pick_roi


def config():
    return {"schema_version": 1, "reference_size": [64, 48],
            "slots": [{"slot_id": "S01", "zone": "A", "vertices": [[4, 4], [24, 4], [24, 24], [4, 24]]}]}


@pytest.mark.parametrize("points", [
    [[4, 4], [24, 24], [24, 4], [4, 24]],  # crossed
    [[4, 4], [4, 4], [24, 24], [4, 24]],  # duplicate
    [[-1, 4], [24, 4], [24, 24], [4, 24]],
    [[4, 4], [64, 4], [24, 24], [4, 24]],
    [[4, 4], [24, 4], [24, 24]],
    [[4.5, 4], [24, 4], [24, 24], [4, 24]],
])
def test_invalid_geometry(points):
    document = config()
    document["slots"][0]["vertices"] = points
    with pytest.raises(ValueError):
        validate_roi(document)


def test_overlap_and_duplicate_ids_rejected():
    document = config()
    document["slots"].append(deepcopy(document["slots"][0]))
    with pytest.raises(ValueError, match="unique"):
        validate_roi(document)
    document["slots"][1]["slot_id"] = "S02"
    with pytest.raises(ValueError, match="overlap"):
        validate_roi(document)


def test_empty_template_not_valid_for_detection():
    document = config()
    document["slots"] = []
    validate_roi(document, allow_empty=True)
    with pytest.raises(ValueError):
        validate_roi(document)


def test_unicode_round_trip_and_invalid_save_preserves_existing(tmp_path):
    path = tmp_path / "주차면.json"
    document = config()
    document["slots"][0]["zone"] = "오른쪽"
    save_roi(path, document)
    assert load_roi(path) == document
    original = path.read_bytes()
    document["slots"][0]["vertices"][0] = [-1, 0]
    with pytest.raises(ValueError):
        save_roi(path, document)
    assert path.read_bytes() == original


def test_mask_scaling_and_aspect_ratio():
    document = config()
    masks = roi_masks(document, (32, 24))
    assert masks["S01"].shape == (24, 32)
    assert masks["S01"][2, 2] == 255 and masks["S01"][12, 12] == 255
    assert masks["S01"][0, 0] == 0
    with pytest.raises(ValueError, match="aspect"):
        roi_masks(document, (32, 48))


def test_editor_pending_undo_and_save(tmp_path):
    document = config()
    document["slots"] = []
    state = EditorState(document)
    state.add_point(4, 4)
    with pytest.raises(ValueError, match="four"):
        state.save(tmp_path / "partial.json")
    for point in [(24, 4), (24, 24), (4, 24)]:
        state.add_point(*point)
    assert len(state.document["slots"]) == 1
    assert not document["slots"]  # caller state not mutated
    state.undo()
    assert not state.document["slots"] and len(state.pending) == 3
    state.add_point(4, 24)
    path = tmp_path / "roi.json"
    state.save(path)
    assert not state.dirty and len(load_roi(path)["slots"]) == 1


def test_editor_invalid_fourth_click_keeps_pending_state():
    document = config()
    document["slots"] = []
    state = EditorState(document)
    for point in [(4, 4), (24, 24), (24, 4)]:
        state.add_point(*point)
    with pytest.raises(ValueError):
        state.add_point(4, 24)
    assert len(state.pending) == 3 and not state.document["slots"]


def test_source_binding_and_video_preview(tmp_path):
    video = tmp_path / "input.avi"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48))
    assert writer.isOpened()
    for value in (0, 100, 200):
        writer.write(np.full((48, 64, 3), value, dtype=np.uint8))
    writer.release()
    document = config()
    document["source"] = {"video_sha256": source_hash(video)}
    path = tmp_path / "roi.json"
    save_roi(path, document)
    result = preview_roi(video, path, tmp_path / "미리보기.png", frame_id=2, width=32)
    assert result["slots"] == 1 and result["size"] == [32, 24]
    assert all(value > 0 for value in result["mask_pixels"].values())
    with pytest.raises(ValueError, match="frame"):
        preview_roi(video, path, tmp_path / "bad.png", frame_id=999)
    document["source"]["video_sha256"] = "wrong"
    with pytest.raises(ValueError, match="hash"):
        check_source(document, video)


def test_picker_mouse_to_source_mapping_and_save(monkeypatch, tmp_path):
    # Exercise GUI callbacks without requiring a display in automated tests.
    video = tmp_path / "source.mp4"
    video.write_bytes(b"test source identity")
    output = tmp_path / "roi.json"
    callbacks = {}
    ticks = iter([ord("s"), ord("q")])
    monkeypatch.setattr("parking_monitor.roi_editor.read_frame", lambda *args: np.zeros((720, 1100, 3), np.uint8))
    for name in ("namedWindow", "imshow", "destroyWindow"):
        monkeypatch.setattr(cv2, name, lambda *args: None)
    monkeypatch.setattr(cv2, "getWindowProperty", lambda *args: 1)
    monkeypatch.setattr(cv2, "setMouseCallback", lambda title, callback: callbacks.update(mouse=callback))
    clicked = False

    def wait(delay):
        nonlocal clicked
        if not clicked:
            # Display is 1069x700 plus an 80px toolbar for this source.
            for x, y in [(100, 180), (200, 180), (200, 280), (100, 280)]:
                callbacks["mouse"](cv2.EVENT_LBUTTONDOWN, x, y, 0, None)
            clicked = True
        return next(ticks)

    monkeypatch.setattr(cv2, "waitKey", wait)
    result = pick_roi(video, output, video_id="test")
    document = load_roi(output)
    assert document["slots"][0]["vertices"][0] == [102, 102]
    assert result["unsaved_changes"] is False
