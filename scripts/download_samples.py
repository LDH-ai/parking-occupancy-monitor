"""Download pinned upstream sample assets without running upstream code."""
import hashlib
import json
from pathlib import Path
import urllib.request


ROOT = Path(__file__).resolve().parents[1]


def git_hash(path):
    digest = hashlib.sha1()
    digest.update(f"blob {path.stat().st_size}\0".encode())
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    manifest = json.loads((ROOT / "data/manifests/upstream_assets.json").read_text(encoding="utf-8"))
    unique = [item for item in manifest["assets"] if not item["duplicate"]]
    for index, item in enumerate(unique, 1):
        target = (ROOT / item["local_path"]).resolve()
        if not target.is_relative_to((ROOT / "data/raw").resolve()):
            raise ValueError("Asset path outside data/raw")
        if target.exists():
            if git_hash(target) != item["git_blob_sha1"]:
                raise ValueError(f"Existing asset differs: {target}")
            print(f"[{index}/{len(unique)}] verified {item['local_path']}", flush=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".part")
        request = urllib.request.Request(item["url"], headers={"User-Agent": "parking-occupancy-monitor"})
        with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as stream:
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                stream.write(chunk)
        if temporary.stat().st_size != item["bytes"] or git_hash(temporary) != item["git_blob_sha1"]:
            raise ValueError(f"Download verification failed: {temporary}")
        temporary.rename(target)
        print(f"[{index}/{len(unique)}] downloaded {item['local_path']}", flush=True)


if __name__ == "__main__":
    main()
