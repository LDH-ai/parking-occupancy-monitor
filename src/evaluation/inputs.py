"""정량 평가 입력 목록, 영상, 시간 블록과 정답을 검증한다."""

from collections import defaultdict
import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path

import cv2

from parking_monitor.baseline import read_labels
from parking_monitor.pixel_ratio import PixelRatioConfig
from parking_monitor.roi import check_source, load_roi, roi_masks, source_hash
from parking_monitor.splits import validate_blocks
from parking_monitor.video import decoded_frames, open_video


PHASES = ("calibration", "validation", "test")
DIRECTIONS = {"entry": "occupied", "exit": "free"}
OPPOSITE = {"free": "occupied", "occupied": "free"}


@dataclass(frozen=True)
class Candidate:
    id: str
    method: str
    min_component_area_px: int = 0
    stabilization_s: float = 0.0

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("구성 ID를 지정하세요")
        if self.method not in ("pixel", "laplacian", "combined"):
            raise ValueError(f"{self.id}: method는 pixel, laplacian, combined 중 하나여야 합니다")
        if type(self.min_component_area_px) is not int or self.min_component_area_px < 0:
            raise ValueError(f"{self.id}: 연결성분 최소 면적은 0 이상의 정수여야 합니다")
        if not self.uses_pixel and self.min_component_area_px:
            raise ValueError(f"{self.id}: 픽셀 비율을 사용하는 구성에만 면적을 지정하세요")
        if (type(self.stabilization_s) not in (int, float) or not math.isfinite(self.stabilization_s)
                or self.stabilization_s < 0):
            raise ValueError(f"{self.id}: 안정화 시간은 0 이상의 유한한 수여야 합니다")

    @property
    def uses_pixel(self):
        return self.method in ("pixel", "combined")

    @property
    def uses_laplacian(self):
        return self.method in ("laplacian", "combined")


def default_candidates(min_area):
    return [
        Candidate("A", "pixel"), Candidate("A-CC", "pixel", min_area),
        Candidate("B", "laplacian"), Candidate("C", "combined"),
        Candidate("D-0.5", "combined", stabilization_s=0.5),
        Candidate("D-1.0", "combined", stabilization_s=1.0),
        Candidate("D-CC-0.5", "combined", min_area, 0.5),
        Candidate("D-CC-1.0", "combined", min_area, 1.0),
    ]


@dataclass(frozen=True)
class VideoInput:
    video_id: str
    view_id: str
    path: Path
    roi: Path


@dataclass(frozen=True)
class Manifest:
    path: Path
    videos: dict[str, VideoInput]
    splits: Path
    labels: dict[str, Path]
    events: dict[str, Path]
    pixel: PixelRatioConfig
    laplacian_kernel: tuple[int, int]
    laplacian_ksize: int
    min_per_class: int
    candidates: list[Candidate]


@dataclass(frozen=True)
class Block:
    start: int
    stop: int
    split: str


@dataclass(frozen=True)
class Video:
    source: VideoInput
    fps: float
    frame_count: int
    size: tuple[int, int]
    masks: dict
    blocks: tuple[Block, ...]
    video_sha256: str
    roi_sha256: str
    geometry: dict

    def block_at(self, frame_id):
        return next((block for block in self.blocks if block.start <= frame_id < block.stop), None)


@dataclass(frozen=True)
class Event:
    id: str
    video_id: str
    slot_id: str
    direction: str
    frame_id: int
    start: int
    stop: int


def read_json(path):
    with Path(path).open(encoding="utf-8-sig") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"JSON 객체가 필요합니다: {path}")
    return value


def read_manifest(path):
    path = Path(path).resolve()
    data = read_json(path)
    if data.get("schema_version") != 1:
        raise ValueError("평가 목록 schema_version은 1이어야 합니다")

    def resolve(value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("평가 목록의 파일 경로를 지정하세요")
        return (path.parent / value).resolve()

    videos = {}
    for item in data["videos"]:
        video_id, view = item["video_id"], item["view_id"]
        if (not isinstance(video_id, str) or not video_id.strip()
                or not isinstance(view, str) or not view.strip() or video_id in videos):
            raise ValueError(f"영상 ID 또는 고정 시점 ID가 잘못되었거나 중복됩니다: {item}")
        videos[video_id] = VideoInput(video_id, view, resolve(item["path"]), resolve(item["roi"]))
    if not videos:
        raise ValueError("평가 목록에 영상을 한 개 이상 지정하세요")

    pixel = PixelRatioConfig.from_dict(data.get("pixel_ratio", {}))
    laplacian = data.get("laplacian", {})
    gauss = laplacian.get("gaussian_kernel", pixel.gaussian_kernel)
    if (not isinstance(gauss, (list, tuple)) or len(gauss) != 2
            or any(type(n) is not int or n < 1 or not n % 2 for n in gauss)):
        raise ValueError("laplacian.gaussian_kernel은 양의 홀수 두 개여야 합니다")
    ksize = laplacian.get("ksize", 1)
    if type(ksize) is not int or not 1 <= ksize <= 31 or not ksize % 2:
        raise ValueError("laplacian.ksize는 1~31의 홀수여야 합니다")
    min_per_class = data.get("min_per_class", 3)
    if type(min_per_class) is not int or min_per_class < 1:
        raise ValueError("min_per_class는 양의 정수여야 합니다")
    if "candidates" in data:
        candidates = [Candidate(**item) for item in data["candidates"]]
    else:
        candidates = default_candidates(data.get("component_area_px", 12))
    if not candidates or len({item.id for item in candidates}) != len(candidates):
        raise ValueError("최소 한 개의 구성을 지정하고 구성 ID를 중복 없이 사용하세요")
    labels = {key: resolve(value) for key, value in data["labels"].items()}
    events = {key: resolve(value) for key, value in data.get("events", {}).items()}
    if set(labels) - set(PHASES) or set(events) - {"validation", "test"}:
        raise ValueError("정답 또는 사건 파일의 구간 이름을 확인하세요")
    if len(set(labels.values())) != len(labels) or len(set(events.values())) != len(events):
        raise ValueError("구간별 정답 파일과 사건 파일에 서로 다른 경로를 지정하세요")
    return Manifest(path, videos, resolve(data["splits"]), labels, events, pixel, tuple(gauss),
                    ksize, min_per_class, candidates)


def csv_rows(path, required):
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not required <= set(reader.fieldnames or []):
            raise ValueError(f"CSV에 필요한 열이 없습니다: {path} ({', '.join(sorted(required))})")
        return list(reader)


def read_blocks(manifest):
    rows = csv_rows(manifest.splits, {"video_id", "session_id", "split", "start_s", "end_s"})
    for row in rows:
        if row["video_id"] not in manifest.videos or row["split"] not in PHASES:
            raise ValueError(f"분할의 영상 ID 또는 구간을 확인하세요: {row}")
        row["start_s"] = float(row["start_s"])
        row["end_s"] = float(row["end_s"])
        if not (math.isfinite(row["start_s"]) and math.isfinite(row["end_s"])
                and 0 <= row["start_s"] < row["end_s"]):
            raise ValueError(f"유효하지 않은 분할 시작·종료 시각: {row}")
    return rows


def _probe(source, rows):
    roi = load_roi(source.roi)
    if roi["source"].get("video_id") != source.video_id:
        raise ValueError(f"영상과 ROI의 video_id가 다릅니다: {source.video_id}")
    check_source(roi, source.path)
    with open_video(source.path) as capture:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError(f"FPS를 읽을 수 없습니다: {source.video_id}")
        expected = tuple(roi["reference_size"])
        frame_count = 0
        for frame in decoded_frames(capture):
            frame_count += 1
            if (frame.shape[1], frame.shape[0]) != expected:
                raise ValueError(f"ROI 해상도와 다른 프레임: {source.video_id}/{frame_count - 1}")
    digest = roi["source"]["video_sha256"]
    metadata = {"fps": fps, "decoded_frames": frame_count, "sha256": digest}
    blocks = tuple(Block(math.ceil(row["start_s"] * fps - 1e-9),
                         math.ceil(row["end_s"] * fps - 1e-9), row["split"])
                   for row in sorted(rows, key=lambda item: item["start_s"]))
    if any(block.start >= block.stop for block in blocks):
        raise ValueError(f"프레임이 들어 있지 않은 분할 구간이 있습니다: {source.video_id}")
    geometry = {"size": list(expected), "slots": {slot["slot_id"]: slot["vertices"]
                                                   for slot in roi["slots"]}}
    masks = roi_masks(roi, expected)
    if not masks or any(not cv2.countNonZero(mask) for mask in masks.values()):
        raise ValueError(f"사용할 주차면 ROI가 비어 있습니다: {source.video_id}")
    return Video(source, fps, frame_count, expected, masks, blocks, digest, source_hash(source.roi),
                 geometry), metadata


def load_videos(manifest, rows, phases, known_geometries=None, known_inputs=None):
    active = {r["video_id"] for r in rows if r["split"] in phases}
    relevant = [r for r in rows if r["video_id"] in active]
    metadata, videos = {}, {}
    geometries = dict(known_geometries or {})
    earlier = known_inputs or {}
    previous_hashes = {record["video_sha256"]: video_id for video_id, record in earlier.items()}
    for video_id in sorted(active):
        video, metadata[video_id] = _probe(manifest.videos[video_id],
                                           [r for r in relevant if r["video_id"] == video_id])
        if video_id in earlier:
            record = earlier[video_id]
            if (video.video_sha256, video.roi_sha256) != (record["video_sha256"], record["roi_sha256"]):
                raise ValueError(f"동결 전후 영상 또는 ROI가 바뀌었습니다: {video_id}")
        if previous_hashes.get(video.video_sha256, video_id) != video_id:
            raise ValueError(f"다른 영상 ID로 등록된 동일한 입력입니다: {video_id}")
        view = video.source.view_id
        if geometries.setdefault(view, video.geometry) != video.geometry:
            raise ValueError(f"같은 view_id의 ROI 좌표·칸 ID·기준 해상도가 다릅니다: {view}")
        videos[video_id] = video
    validate_blocks(relevant, metadata)
    return videos, geometries


def load_labels(manifest, videos, phase):
    if phase not in manifest.labels:
        raise ValueError(f"평가 목록에 {phase} 정답 CSV를 지정하세요")
    grouped = defaultdict(dict)
    for label in read_labels(manifest.labels[phase]):
        video = videos.get(label.video_id)
        if video is None or label.slot_id not in video.masks:
            raise ValueError(f"정답의 영상 또는 ROI 칸 ID가 등록되지 않았습니다: {label}")
        block = video.block_at(label.frame_id)
        if block is None or block.split != phase:
            raise ValueError(f"정답이 {phase} 구간 밖에 있습니다: {label.video_id}/{label.frame_id}")
        if abs(label.frame_id / video.fps - label.timestamp_s) > 0.000501:
            raise ValueError(f"정답 시각과 frame_id/FPS가 다릅니다: {label.video_id}/{label.frame_id}")
        grouped[label.video_id][(label.frame_id, label.slot_id)] = label.label
    return grouped


def load_events(manifest, videos, phase):
    grouped = defaultdict(list)
    if phase not in manifest.events:
        return grouped
    ids, keys = set(), set()
    rows = csv_rows(manifest.events[phase],
                    {"event_id", "video_id", "slot_id", "direction", "frame_id",
                     "observe_start_frame", "observe_end_frame"})
    for row in rows:
        event = Event(row["event_id"], row["video_id"], row["slot_id"], row["direction"],
                      int(row["frame_id"]), int(row["observe_start_frame"]), int(row["observe_end_frame"]))
        key = (event.video_id, event.slot_id, event.frame_id)
        if not event.id.strip() or event.id in ids or key in keys or event.direction not in DIRECTIONS:
            raise ValueError(f"입·출차 사건 ID, 방향 또는 프레임이 잘못되었습니다: {event}")
        video = videos.get(event.video_id)
        if video is None or event.slot_id not in video.masks or not event.start < event.frame_id < event.stop:
            raise ValueError(f"사건의 영상, 주차면 또는 관측 범위가 잘못되었습니다: {event}")
        block = video.block_at(event.frame_id)
        if block is None or block.split != phase or not block.start <= event.start < event.stop <= block.stop:
            raise ValueError(f"사건 관측 구간은 하나의 {phase} 블록 안에 있어야 합니다: {event.id}")
        grouped[event.video_id].append(event)
        ids.add(event.id)
        keys.add(key)
    return grouped
