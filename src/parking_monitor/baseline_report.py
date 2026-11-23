"""픽셀 기준선의 CSV, JSON, 그래프를 기록한다."""

import csv
from dataclasses import asdict
import json
from pathlib import Path
import tempfile

import numpy as np

from .baseline import STATES, decide


def _write_csv(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def _write_json(path, result):
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8", newline="\n")


def _pixel_threshold_record(threshold):
    record = asdict(threshold)
    del record["upper_bound"]
    return record


def _plot_distribution(path, samples, split):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib import colormaps

    fig = Figure(figsize=(7, 4.5))
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    rng = np.random.default_rng(0)
    slots = sorted({slot for slot, _, _ in samples})
    colors = colormaps["tab10"]
    for index, slot in enumerate(slots):
        name = slot
        for position, state in enumerate(STATES):
            values = [r for s, r, truth in samples if s == slot and truth == state]
            if values:
                offsets = position + rng.uniform(-0.18, 0.18, len(values))
                ax.scatter(offsets, values, s=28, color=colors(index % 10), label=name)
                name = None
    if slots:
        ax.legend(title="Slot", fontsize=8)
    else:
        ax.text(0.5, 0.5, "No labeled samples", transform=ax.transAxes, ha="center")
    ax.set_xticks(range(3), ["Free", "Occupied", "Unknown"])
    ax.set_ylabel("White pixels / ROI pixels")
    ax.set_title(f"Pixel-ratio distribution ({split})")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)


def _morphology_result(name, samples, metrics):
    free = [r for _, r, truth in samples if truth == "free"]
    occupied = [r for _, r, truth in samples if truth == "occupied"]
    return [name, metrics["n_eval"], len(free), len(occupied), metrics["n_gt_unknown_excluded"],
            np.mean(free) if free else None, np.mean(occupied) if occupied else None,
            min(occupied) - max(free) if free and occupied else None,
            metrics["n_eval_without_threshold"], metrics["f1"], metrics["false_vacant_rate"],
            metrics["confirmed_ratio"]]


def _write_series(out, series, slot_ids, video_id, fps):
    _write_csv(out / "r_timeseries.csv", ["video_id", "frame_id", "timestamp_s", *slot_ids],
               ([video_id, frame_id, f"{frame_id / fps:.12f}", *(ratios[slot] for slot in slot_ids)]
                for frame_id, ratios in series.items()))
    activity = []
    if series:
        for slot in slot_ids:
            values = np.array([ratios[slot] for ratios in series.values()])
            activity.append([slot, values.min(), values.max(), np.ptp(values), values.std()])
    activity.sort(key=lambda row: (-row[3], row[0]))
    _write_csv(out / "slot_activity.csv", ["slot_id", "r_min", "r_max", "r_range", "r_std"], activity)


def _prediction_rows(samples, thresholds, morphology, eval_split, fps):
    for sample in samples:
        label = sample.label
        r = sample.ratios[morphology]
        threshold = thresholds.get(label.slot_id)
        features = [label.video_id, label.frame_id, f"{label.frame_id / fps:.12f}", label.slot_id,
                    label.label, sample.split, r]
        prediction = [threshold.source if threshold else "",
                      threshold.low if threshold else None, threshold.high if threshold else None,
                      decide(r, threshold), int(sample.split == eval_split and label.label != "unknown")]
        yield features, [*features, *prediction]


def write_results(out, measurements, comparisons, metrics, run_info, slot_ids):
    morphology = run_info["config"]["morphology"]
    eval_split = metrics["eval_split"]
    calibration_split = "all" if run_info["in_sample_evaluation"] else "calibration"
    thresholds, _, _ = comparisons[morphology]
    rows = list(_prediction_rows(measurements.samples, thresholds, morphology,
                                 eval_split, measurements.fps))
    comparison = [_morphology_result(name, features, scores)
                  for name, (_, features, scores) in comparisons.items()]
    calibration_samples = [sample.feature(morphology) for sample in measurements.samples
                           if sample.split == calibration_split]

    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as temporary:
        staged = Path(temporary) / "run"
        staged.mkdir()
        header = ["video_id", "frame_id", "timestamp_s", "slot_id", "gt", "split", "r"]
        _write_csv(staged / "r_features.csv", header, (row for row, _ in rows))
        _write_csv(staged / "predictions.csv", [*header, "threshold_source", "low", "high",
                                               "pred", "evaluated"], (row for _, row in rows))
        _write_csv(staged / "morph_comparison.csv",
                   ["morphology", "split", "n_eval", "n_free", "n_occupied", "n_unknown",
                    "mean_r_free", "mean_r_occupied", "pooled_gap", "n_eval_without_threshold",
                    "f1", "false_vacant_rate", "confirmed_ratio"],
                   ([result[0], eval_split, *result[1:]] for result in comparison))
        _write_json(staged / "thresholds.json",
                    {slot: _pixel_threshold_record(t) for slot, t in sorted(thresholds.items())})
        _write_json(staged / "metrics.json", metrics)
        _write_json(staged / "run_info.json", run_info)
        _plot_distribution(staged / "r_distribution.png", calibration_samples, calibration_split)
        if run_info["timeseries"]:
            _write_series(staged, measurements.series, slot_ids, run_info["video_id"], measurements.fps)
        staged.rename(out)
