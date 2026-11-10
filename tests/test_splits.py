import pytest

from parking_monitor.splits import sample_frames, validate_blocks


def block(start, end, split="calibration", video="a"):
    return dict(video_id=video, session_id="clip_" + video, start_s=start, end_s=end, split=split)


def meta(fps=24, count=2400, sha="source-a"):
    return dict(fps=fps, decoded_frames=count, sha256=sha)


def test_temporal_gap_is_required():
    assert validate_blocks([block(0, 20), block(30, 50, "test")], {"a": meta()})
    with pytest.raises(ValueError, match="gap"):
        validate_blocks([block(0, 20), block(29, 50, "test")], {"a": meta()})


@pytest.mark.parametrize("start,end", [(-1, 10), (10, 10), (20, 10), (0, 101), (0, float("nan"))])
def test_invalid_bounds_rejected(start, end):
    with pytest.raises(ValueError):
        validate_blocks([block(start, end)], {"a": meta()})


def test_duplicate_content_cannot_cross_ids():
    with pytest.raises(ValueError, match="Duplicate"):
        validate_blocks([block(0, 20), block(30, 50, "test", "b")], {"a": meta(), "b": meta()})


def test_fractional_fps_sampling_obeys_half_open_bounds_and_interval():
    fps = 29.970109386924445
    samples = sample_frames(block(75, 120, "test"), fps)
    times = [sample["frame_id"] / fps for sample in samples]
    assert all(75 <= t < 120 for t in times)
    assert all(b - a >= 1 for a, b in zip(times, times[1:]))


def test_count_uses_decoded_frames_instead_of_reported_frames():
    with pytest.raises(ValueError, match="bounds"):
        validate_blocks([block(0, 100)], {"a": meta(count=2399)})
