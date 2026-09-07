import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from app.agent_platform.registry import bundled, workflows
from app.internal_knowledge.seed import load_synthetic_corpus

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "prepare_vercel_resources", ROOT / "scripts/prepare-vercel-resources.py"
)
assert spec and spec.loader
packaging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packaging)


def test_service_bundle_loads_reviewed_contracts_without_repository_paths(tmp_path, monkeypatch):
    target = tmp_path / "service/app/_resources"
    manifest = packaging.bundle_resources(ROOT, target)
    assert manifest == json.loads((target / "manifest.json").read_text())
    for relative, digest in manifest.items():
        assert hashlib.sha256((target / relative).read_bytes()).hexdigest() == digest
    monkeypatch.setattr(bundled, "ROOT", target)
    monkeypatch.setattr(workflows, "resource_root", lambda: target)
    for filename in bundled.AGENT_FILES:
        assert bundled._load_versioned_contract(target / "contracts/agents" / filename)
    assert workflows.load_bundled_workflow()["metadata"]["name"]
    assert load_synthetic_corpus(
        target / "fixtures/internal_quality/synthetic_quality_system.v1.yaml"
    )
    assert all(Path(name).suffix in {".json", ".yaml", ".yml", ".sql"} for name in manifest)


def test_missing_contract_upload_fails_build(tmp_path):
    with pytest.raises(RuntimeError, match="contracts are missing"):
        packaging.bundle_resources(tmp_path, tmp_path / "output")
