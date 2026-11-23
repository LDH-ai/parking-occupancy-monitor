"""공통 특징 추출, 시간 판정, 영상별 측정을 수행한다."""

from collections import defaultdict
from dataclasses import dataclass, replace
from itertools import islice
import math
from statistics import median
from time import perf_counter

import cv2
import numpy as np

from parking_monitor.baseline import calibrate, decide, evaluate
from parking_monitor.pixel_ratio import pixel_ratios, postprocess, threshold_smoothed
from parking_monitor.video import open_video

from .inputs import DIRECTIONS, OPPOSITE, Event


@dataclass(frozen=True)
class Features:
    pixels: dict
    laplacian: dict


def frame_features(frame, masks, pixel_configs, laplacian):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    smoothed = {}
    binaries = {}
    pixels = {}
    for area, config in pixel_configs.items():
        kernel = config.gaussian_kernel
        if kernel not in binaries:
            smoothed[kernel] = cv2.GaussianBlur(gray, kernel, 0)
            binaries[kernel] = threshold_smoothed(smoothed[kernel], config)
        pixels[area] = pixel_ratios(postprocess(binaries[kernel], config), masks)
    lap_values = {}
    if laplacian is not None:
        kernel, ksize = laplacian
        smooth = smoothed.get(kernel)
        if smooth is None:
            smooth = cv2.GaussianBlur(gray, kernel, 0)
        absolute = np.abs(cv2.Laplacian(smooth, cv2.CV_64F, ksize=ksize))
        lap_values = {slot: cv2.mean(absolute, mask=mask)[0] for slot, mask in masks.items()}
    return Features(pixels, lap_values)


def feature_settings(manifest, candidates):
    pixels = {item.min_component_area_px: replace(manifest.pixel, min_component_area_px=item.min_component_area_px)
              for item in candidates if item.uses_pixel}
    laplacian = ((manifest.laplacian_kernel, manifest.laplacian_ksize)
                 if any(item.uses_laplacian for item in candidates) else None)
    return pixels, laplacian


def iter_frames(video, phase):
    """비교에 포함된 블록의 프레임과 디코딩 시작 시각을 반환한다."""
    with open_video(video.source.path) as capture:
        position = 0
        for block in (item for item in video.blocks if item.split == phase):
            for frame_id in range(position, block.stop):
                started = perf_counter() if frame_id >= block.start else None
                ok, frame = capture.read()
                if not ok or frame is None:
                    raise ValueError(f"평가 중 프레임을 읽지 못했습니다: {video.source.video_id}/{frame_id}")
                if started is not None:
                    if (frame.shape[1], frame.shape[0]) != video.size:
                        raise ValueError(f"평가 중 영상 해상도가 바뀌었습니다: {video.source.video_id}/{frame_id}")
                    yield block, frame_id, frame, started
            position = block.stop


def calibrate_candidates(manifest, videos, labels):
    pixel_configs, laplacian = feature_settings(manifest, manifest.candidates)
    samples = defaultdict(lambda: defaultdict(list))
    for video_id, video in videos.items():
        by_frame = defaultdict(dict)
        for (frame_id, slot), truth in labels.get(video_id, {}).items():
            by_frame[frame_id][slot] = truth
        if not by_frame:
            continue
        view_samples = samples[video.source.view_id]
        for _, frame_id, frame, _ in iter_frames(video, "calibration"):
            truth = by_frame.pop(frame_id, None)
            if not truth:
                continue
            masks = {slot: video.masks[slot] for slot in truth}
            result = frame_features(frame, masks, pixel_configs, laplacian)
            for area, values in result.pixels.items():
                view_samples[("pixel", area)].extend((slot, value, truth[slot])
                                                       for slot, value in values.items())
            view_samples[("laplacian", None)].extend((slot, value, truth[slot])
                                                        for slot, value in result.laplacian.items())
            if not by_frame:
                break

    fitted = {
        view: {key: calibrate(data, manifest.min_per_class,
                              upper_bound=1.0 if key[0] == "pixel" else None)[0]
               for key, data in features.items()}
        for view, features in samples.items()
    }
    thresholds = {}
    for candidate in manifest.candidates:
        thresholds[candidate.id] = {}
        for view, features in fitted.items():
            branches = {}
            if candidate.uses_pixel:
                branches["pixel"] = features.get(("pixel", candidate.min_component_area_px), {})
            if candidate.uses_laplacian:
                branches["laplacian"] = features.get(("laplacian", None), {})
            thresholds[candidate.id][view] = branches
    return thresholds


class Stabilizer:
    def __init__(self, duration):
        self.duration = duration
        self.candidates = {}

    def update(self, slot, candidate, timestamp):
        if not self.duration:
            return candidate
        previous, start = self.candidates.get(slot, (None, timestamp))
        if candidate != previous:
            start = timestamp
        self.candidates[slot] = (candidate, start)
        if candidate == "unknown" or timestamp - start + 1e-9 < self.duration:
            return "unknown"
        return candidate


def predict(slot, features, thresholds, candidate):
    r = features.pixels.get(candidate.min_component_area_px, {}).get(slot)
    laplacian = features.laplacian.get(slot)
    pixel_threshold = thresholds.get("pixel", {}).get(slot)
    lap_threshold = thresholds.get("laplacian", {}).get(slot)
    if not candidate.uses_laplacian:
        return r, laplacian, decide(r, pixel_threshold), pixel_threshold is None
    lap_state = decide(laplacian, lap_threshold)
    if not candidate.uses_pixel:
        return r, laplacian, lap_state, lap_threshold is None
    pixel_state = decide(r, pixel_threshold)
    confirmed = pixel_state if pixel_state == lap_state else "unknown"
    return r, laplacian, confirmed, pixel_threshold is None or lap_threshold is None


@dataclass
class EventResult:
    event: Event
    target: str
    confirmed_frame: int | None = None
    early: bool = False

    def update(self, frame_id, prediction, previous):
        if prediction != self.target:
            return
        if frame_id < self.event.frame_id:
            self.early = True
        elif self.confirmed_frame is None and previous != self.target:
            self.confirmed_frame = frame_id

    def row(self, fps):
        event, confirmed = self.event, self.confirmed_frame
        return {
            "event_id": event.id, "video_id": event.video_id, "slot_id": event.slot_id,
            "direction": event.direction, "frame_id": event.frame_id, "timestamp_s": event.frame_id / fps,
            "confirmed_frame": confirmed, "confirmed_s": None if confirmed is None else confirmed / fps,
            "delay_s": None if confirmed is None else (confirmed - event.frame_id) / fps,
            "early": self.early, "missed": confirmed is None,
        }


def event_windows(events, fps):
    by_slot = defaultdict(list)
    for event in sorted(events, key=lambda item: item.frame_id):
        by_slot[event.slot_id].append(event)
    results, observations = [], defaultdict(list)
    for slot_events in by_slot.values():
        for index, event in enumerate(slot_events):
            next_frame = slot_events[index + 1].frame_id if index + 1 < len(slot_events) else event.stop
            stop = min(event.stop, next_frame, event.frame_id + math.floor(10 * fps + 1e-9) + 1)
            start = max(event.start, slot_events[index - 1].frame_id) if index else event.start
            result = EventResult(event, DIRECTIONS[event.direction])
            results.append(result)
            for frame_id in range(start, stop):
                observations[frame_id].append(result)
    return results, observations


@dataclass
class Stability:
    stable_seconds: float = 0.0
    false_transitions: int = 0
    hold_entries: int = 0

    def observe(self, truth, prediction, prior_truth, prior_prediction, fps):
        if truth != prior_truth:
            return
        self.stable_seconds += 1 / fps
        if prediction == prior_prediction:
            return
        if prediction == "unknown":
            self.hold_entries += 1
        elif prediction != truth:
            self.false_transitions += 1


def _warmup(video, phase, pixel_configs, laplacian, thresholds, candidate):
    stabilizer = Stabilizer(candidate.stabilization_s)
    with_frames = iter_frames(video, phase)
    try:
        for _, frame_id, frame, _ in islice(with_frames, 30):
            features = frame_features(frame, video.masks, pixel_configs, laplacian)
            for slot in video.masks:
                _, _, state, _ = predict(slot, features, thresholds, candidate)
                stabilizer.update(slot, state, frame_id / video.fps)
    finally:
        with_frames.close()


def measure_video(manifest, video, phase, labels, events, candidate, thresholds, writer):
    pixel_configs, laplacian = feature_settings(manifest, [candidate])
    _warmup(video, phase, pixel_configs, laplacian, thresholds, candidate)
    results, observations = event_windows(events, video.fps)
    pairs, processing, loop = [], [], []
    missing = 0
    active_block, previous, previous_truth = None, {}, {}
    stability = Stability()
    video_id = video.source.video_id
    for block, frame_id, frame, started in iter_frames(video, phase):
        work_started = perf_counter()
        if block != active_block:
            stabilizer = Stabilizer(candidate.stabilization_s)
            active_block, previous, previous_truth = block, {}, {}
        timestamp = frame_id / video.fps
        features = frame_features(frame, video.masks, pixel_configs, laplacian)
        predicted = {}
        for slot in video.masks:
            r, lap, state, no_threshold = predict(slot, features, thresholds, candidate)
            final = stabilizer.update(slot, state, timestamp)
            predicted[slot] = (r, lap, state, final, no_threshold)
        processing.append(perf_counter() - work_started)

        event_truths = defaultdict(set)
        for result in observations.get(frame_id, ()):
            slot = result.event.slot_id
            result.update(frame_id, predicted[slot][3], previous.get(slot))
            truth = result.target if frame_id >= result.event.frame_id else OPPOSITE[result.target]
            event_truths[slot].add(truth)
        frame_truth = {slot: next(iter(values)) for slot, values in event_truths.items() if len(values) == 1}
        for slot, (r, lap, state, final, no_threshold) in predicted.items():
            truth = labels.get((frame_id, slot))
            if truth is not None:
                pairs.append((truth, final))
                missing += no_threshold and truth != "unknown"
            if slot in frame_truth:
                stability.observe(frame_truth[slot], final, previous_truth.get(slot), previous.get(slot), video.fps)
            if truth is not None or slot in event_truths:
                writer.writerow([candidate.id, video_id, frame_id, timestamp, slot, truth, r, lap, state,
                                 final, int(truth is not None and truth != "unknown"), int(no_threshold)])
        previous = {slot: values[3] for slot, values in predicted.items()}
        previous_truth = frame_truth
        loop.append(perf_counter() - started)
    if len(pairs) != len(labels):
        raise ValueError(f"출력을 생성하지 못한 정답 프레임이 있습니다: {video_id}/{phase}")
    events = [{"candidate_id": candidate.id, **result.row(video.fps)} for result in results]
    return pairs, missing, events, processing, loop, stability


def summarize_events(rows, stable_seconds, wrong, holds):
    summary = {"false_transitions": wrong, "hold_entries": holds, "stable_slot_seconds": stable_seconds,
               "false_transitions_per_slot_minute": wrong * 60 / stable_seconds if stable_seconds else None,
               "hold_entries_per_slot_minute": holds * 60 / stable_seconds if stable_seconds else None}
    for direction in DIRECTIONS:
        selected = [row for row in rows if row["direction"] == direction]
        delays = [row["delay_s"] for row in selected if row["delay_s"] is not None]
        summary[direction] = {"count": len(selected), "detected": len(delays),
                              "missed": sum(row["missed"] for row in selected),
                              "early": sum(row["early"] for row in selected),
                              "median_delay_s": median(delays) if delays else None,
                              "max_delay_s": max(delays, default=None)}
    return summary


def summarize_timing(processing, loop):
    def milliseconds(values):
        if not values:
            return {"median_ms": None, "p95_ms": None}
        return {"median_ms": median(values) * 1000, "p95_ms": float(np.percentile(values, 95)) * 1000}
    elapsed_s = sum(loop)
    return {"frames": len(loop), "elapsed_s": elapsed_s, "fps": len(loop) / elapsed_s if elapsed_s else None,
            "algorithm": milliseconds(processing), "loop": milliseconds(loop)}


def summarize_video(pairs, missing, events, processing, loop, stability):
    return {
        **evaluate(pairs), "n_eval_without_threshold": missing,
        "timing": summarize_timing(processing, loop),
        "events": summarize_events(events, stability.stable_seconds,
                                    stability.false_transitions, stability.hold_entries),
    }
