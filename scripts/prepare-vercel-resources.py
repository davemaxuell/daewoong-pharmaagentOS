"""Copy only reviewed runtime data into the Python service before Vercel packaging."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def bundle_resources(
    root: Path = ROOT, destination: Path | None = None
) -> dict[str, str]:
    destination = destination or root / "services/api/app/_resources"
    sources = [
        path
        for path in (root / "contracts").rglob("*")
        if path.is_file() and path.suffix in {".json", ".yaml", ".yml", ".sql"}
    ]
    sources.append(root / "fixtures/internal_quality/synthetic_quality_system.v1.yaml")
    if not (root / "contracts/agents").is_dir():
        raise RuntimeError("Reviewed contracts are missing from the deployment upload")
    hashes = {}
    for source in sorted(sources):
        if source.is_symlink() or not source.resolve().is_relative_to(root.resolve()):
            raise ValueError("Runtime resource must be an ordinary workspace file")
        relative = source.relative_to(root)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        hashes[relative.as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
    (destination / "manifest.json").write_text(
        json.dumps(hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return hashes


if __name__ == "__main__":
    print(f"Bundled {len(bundle_resources())} reviewed runtime resources")
