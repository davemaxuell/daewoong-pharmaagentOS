from __future__ import annotations

import json
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
CORPUS_PATH = WORKSPACE_ROOT / "fixtures" / "synthetic-quality" / "corpus.v1.json"


def test_synthetic_quality_seed_is_labeled_anchored_and_closed() -> None:
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))

    assert corpus["classification"] == "FICTIONAL_TEST_DATA"
    assert corpus["display_label"] == "FICTIONAL TEST DATA — NOT A COMPANY RECORD"
    assert "fictional" in corpus["organization"].casefold()
    assert len(corpus["documents"]) >= 3

    documents = {document["document_id"]: document for document in corpus["documents"]}
    assert len(documents) == len(corpus["documents"])

    serialized = json.dumps(corpus, ensure_ascii=False).casefold()
    assert "daewoong" not in serialized
    for document in documents.values():
        assert document["synthetic"] is True
        assert document["revision"]
        assert document["effective_date"]
        assert "fictional" in document["owner"].casefold()
        assert document["status"]
        assert document["acl"]["classification"].startswith("SYNTHETIC_")
        assert document["acl"]["deny_export"] is True

        anchor_ids = [section["anchor_id"] for section in document["sections"]]
        assert anchor_ids
        assert len(anchor_ids) == len(set(anchor_ids))
        assert all(section["text"].strip() for section in document["sections"])

        for relationship in document["relationships"]:
            target = documents[relationship["target_document_id"]]
            assert relationship["target_revision"] == target["revision"]
