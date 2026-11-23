import numpy as np
import pytest

from parking_monitor.pixel_ratio import (
    PixelRatioConfig, binarize, frame_ratios, pixel_ratios, postprocess,
)
from parking_monitor.roi import roi_masks


def mask():
    roi = {"schema_version": 1, "reference_size": [40, 40],
           "slots": [{"slot_id": "A", "zone": "A",
                      "vertices": [[10, 10], [29, 10], [29, 29], [10, 29]]}]}
    return roi_masks(roi, (40, 40))


def test_ratio_uses_mask_area_as_denominator_and_ignores_outside():
    masks = mask()
    binary = np.zeros((40, 40), dtype=np.uint8)
    binary[10:20, 10:30] = 255
    binary[0:5, 0:5] = 255
    assert pixel_ratios(binary, masks)["A"] == 0.5


def test_ratio_is_zero_for_black_and_one_for_white():
    masks = mask()
    assert pixel_ratios(np.zeros((40, 40), dtype=np.uint8), masks)["A"] == 0.0
    assert pixel_ratios(np.full((40, 40), 255, dtype=np.uint8), masks)["A"] == 1.0


def test_ratio_rejects_empty_mask():
    binary = np.zeros((40, 40), dtype=np.uint8)
    with pytest.raises(ValueError, match="비어"):
        pixel_ratios(binary, {"A": np.zeros_like(binary)})


def test_frame_ratios_checks_size_and_flat_frame_is_zero():
    masks = mask()
    flat = np.full((40, 40, 3), 128, dtype=np.uint8)
    assert frame_ratios(flat, masks, PixelRatioConfig())["A"] == 0.0
    with pytest.raises(ValueError, match="크기"):
        frame_ratios(flat[:30], masks, PixelRatioConfig())


def test_dilation_does_not_reduce_white_pixels():
    rng = np.random.default_rng(0)
    frame = (rng.random((80, 80, 3)) * 255).astype(np.uint8)
    without_morphology = np.count_nonzero(binarize(frame, PixelRatioConfig(morphology="none")))
    dilated = np.count_nonzero(binarize(frame, PixelRatioConfig(morphology="dilate")))
    assert dilated >= without_morphology


def test_component_filter_keeps_diagonally_connected_pixels_at_minimum_area():
    binary = np.zeros((40, 40), dtype=np.uint8)
    binary[10, 10] = binary[11, 11] = binary[12, 12] = 255
    binary[20, 20:22] = 255
    config = PixelRatioConfig(morphology="none", min_component_area_px=3)
    filtered = postprocess(binary, config)
    assert filtered[10, 10] == filtered[11, 11] == filtered[12, 12] == 255
    assert np.count_nonzero(filtered) == 3
    assert pixel_ratios(filtered, mask())["A"] == 3 / 400


def test_config_validation_and_roundtrip():
    with pytest.raises(ValueError):
        PixelRatioConfig(morphology="erode")
    with pytest.raises(ValueError):
        PixelRatioConfig(median_kernel=4)
    with pytest.raises(ValueError):
        PixelRatioConfig(adaptive_block_size=24)
    with pytest.raises(ValueError, match="min_component_area_px"):
        PixelRatioConfig(min_component_area_px=-1)
    config = PixelRatioConfig(morphology="open", median_kernel=7, min_component_area_px=12)
    assert PixelRatioConfig.from_dict(config.to_dict()) == config
    with pytest.raises(ValueError):
        PixelRatioConfig.from_dict({"unknown_key": 1})
