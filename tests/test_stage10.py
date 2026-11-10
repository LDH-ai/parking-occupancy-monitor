"""Guard the frozen dataset against silent edits and unrecorded label revisions."""
import csv
import hashlib
import json
from pathlib import Path
import runpy
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
validate = runpy.run_path(str(ROOT / "scripts/validate_stage10.py"))["validate"]


@pytest.fixture
def snapshot(tmp_path):
    manifest = "data/manifests/stage10.freeze.json"
    frozen = json.loads((ROOT / manifest).read_text(encoding="utf-8"))
    for name in [manifest, *frozen["files"]]:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return tmp_path


def test_changed_frozen_roi_is_rejected(snapshot):
    target = snapshot / "configs/roi.shared_carpark.final.json"
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="Frozen artifact changed"):
        validate(snapshot)


def test_unrecorded_label_change_is_rejected_even_with_updated_digest(snapshot):
    name = "data/labels/pilot.shared_carpark.reviewed.csv"
    target = snapshot / name
    with target.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows[0]["label"] = "occupied"  # A07 was free; no review record authorizes this change.
    with target.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    path = snapshot / "data/manifests/stage10.freeze.json"
    frozen = json.loads(path.read_text(encoding="utf-8"))
    frozen["files"][name] = hashlib.sha256(target.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    path.write_text(json.dumps(frozen), encoding="utf-8")
    with pytest.raises(ValueError, match="Unrecorded label revision"):
        validate(snapshot)
