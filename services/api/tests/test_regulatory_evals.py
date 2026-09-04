from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, MutableMapping, MutableSequence
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import yaml

from app.agent_platform.regulatory import (
    AnchorObservation,
    SourcePin,
    ValidationCode,
    parse_regulatory_finding_list,
    validate_declared_output,
    validate_resolved_evidence,
)

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
SUITE_PATH = WORKSPACE_ROOT / "evals" / "regulatory" / "regulatory-agent-release.v3.0.0.yaml"
EXPECTED_CATEGORIES = {"NORMAL", "SOURCE_DRIFT", "DIFFICULT_CITATION", "ADVERSARIAL"}


def _load_suite() -> dict[str, Any]:
    loaded = yaml.safe_load(SUITE_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _records_by_id(records: object) -> dict[str, dict[str, Any]]:
    assert isinstance(records, list)
    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        assert isinstance(record, dict)
        fixture_id = record.get("fixtureId")
        assert isinstance(fixture_id, str) and fixture_id
        assert fixture_id not in indexed
        indexed[fixture_id] = record
    return indexed


def _decode_pointer_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _apply_mutation(document: dict[str, Any], mutation: Mapping[str, object]) -> None:
    operation = mutation.get("operation")
    path = mutation.get("path")
    assert operation in {"add", "replace"}
    assert isinstance(path, str) and path.startswith("/")
    parts = [_decode_pointer_token(part) for part in path.removeprefix("/").split("/")]
    assert parts and all(parts)

    cursor: object = document
    for part in parts[:-1]:
        if isinstance(cursor, MutableMapping):
            assert part in cursor
            cursor = cursor[part]
        else:
            assert isinstance(cursor, MutableSequence)
            cursor = cursor[int(part)]

    leaf = parts[-1]
    value = deepcopy(mutation.get("value"))
    if isinstance(cursor, MutableMapping):
        if operation == "replace":
            assert leaf in cursor
        cursor[leaf] = value
        return

    assert isinstance(cursor, MutableSequence)
    index = int(leaf)
    if operation == "replace":
        assert 0 <= index < len(cursor)
        cursor[index] = value
    else:
        assert 0 <= index <= len(cursor)
        cursor.insert(index, value)


def _execute_case(suite: Mapping[str, Any], case: Mapping[str, Any]) -> tuple[ValidationCode, ...]:
    fixtures = suite["fixtures"]
    assert isinstance(fixtures, Mapping)
    outputs = _records_by_id(fixtures["outputs"])
    source_pins = _records_by_id(fixtures["sourcePins"])
    anchors = _records_by_id(fixtures["anchors"])

    output_fixture_id = case["outputFixtureId"]
    assert isinstance(output_fixture_id, str)
    raw_output = deepcopy(outputs[output_fixture_id]["payload"])
    assert isinstance(raw_output, dict)
    mutations = case["outputMutations"]
    assert isinstance(mutations, list)
    for mutation in mutations:
        assert isinstance(mutation, Mapping)
        _apply_mutation(raw_output, mutation)

    output, parse_issues = parse_regulatory_finding_list(raw_output)
    if output is None:
        return tuple(issue.code for issue in parse_issues)

    pin_fixture_ids = case["sourcePinFixtureIds"]
    assert isinstance(pin_fixture_ids, list)
    pins = tuple(
        SourcePin(
            source_version_id=UUID(source_pins[fixture_id]["sourceVersionId"]),
            source_hash=source_pins[fixture_id]["sourceHash"],
        )
        for fixture_id in pin_fixture_ids
    )
    declared_issues = validate_declared_output(
        output,
        source_pins=pins,
        taxonomy_version="drug-taxonomy-v1.0.0",
    )
    if declared_issues:
        # The runtime does not resolve evidence after a declared-output failure.
        return tuple(issue.code for issue in declared_issues)

    anchor_fixture_ids = case["anchorFixtureIds"]
    assert isinstance(anchor_fixture_ids, list)
    observations: dict[tuple[UUID, str, str], AnchorObservation] = {}
    for fixture_id in anchor_fixture_ids:
        fixture = anchors[fixture_id]
        observation = AnchorObservation(
            source_version_id=UUID(fixture["sourceVersionId"]),
            source_hash=fixture["sourceHash"],
            anchor_id=fixture["anchorId"],
            excerpt=fixture["excerpt"],
            evidence_class=fixture["evidenceClass"],
            access_allowed=fixture["accessAllowed"],
        )
        observations[
            (
                observation.source_version_id,
                observation.source_hash,
                observation.anchor_id,
            )
        ] = observation
    return tuple(issue.code for issue in validate_resolved_evidence(output, observations))


def _case_ids() -> list[str]:
    cases = _load_suite()["cases"]
    assert isinstance(cases, list)
    return [case["caseId"] for case in cases]


def test_development_seed_is_machine_gated_from_release_use() -> None:
    suite = _load_suite()
    metadata = suite["metadata"]
    requirements = suite["releaseRequirements"]
    execution = suite["execution"]

    assert suite["apiVersion"] == "pharmaagent.io/v1"
    assert suite["kind"] == "RegulatoryAgentEvalSuite"
    assert metadata["name"] == "regulatory-agent-release"
    assert metadata["version"] == "3.0.0"
    assert metadata["state"] == "DEVELOPMENT_SEED"
    assert metadata["releaseEligible"] is False
    assert metadata["dataClassification"] == "WHOLLY_SYNTHETIC"
    assert execution["mode"] == "DETERMINISTIC_VALIDATOR_REPLAY"
    assert execution["validatorContract"] == "RegulatoryFindingList@2.0.0"
    assert execution["agentVersion"] == "regulatory-evidence-agent@1.3.0"

    provider_trials = execution["probabilisticTrialsPerCase"]
    minimum_trials = requirements["minimumProbabilisticTrialsPerCase"]
    assert provider_trials == 0
    assert minimum_trials >= 3
    assert provider_trials < minimum_trials

    limitations = " ".join(suite["seedLimitations"]).casefold()
    assert "not" in limitations and "release" in limitations
    assert "provider-model trials" in limitations


def test_development_seed_declares_incomplete_release_coverage() -> None:
    suite = _load_suite()
    cases = suite["cases"]
    assert isinstance(cases, list) and cases
    case_ids = [case["caseId"] for case in cases]
    assert len(case_ids) == len(set(case_ids))
    assert all(case["deterministic"] is True for case in cases)

    actual_counts = Counter(case["category"] for case in cases)
    targets = suite["releaseRequirements"]["targetCaseCounts"]
    assert set(actual_counts) == EXPECTED_CATEGORIES
    assert set(targets) == EXPECTED_CATEGORIES
    assert all(actual_counts[category] < targets[category] for category in EXPECTED_CATEGORIES)


@pytest.mark.parametrize("case_id", _case_ids())
def test_regulatory_agent_seed_case(case_id: str) -> None:
    suite = _load_suite()
    cases = suite["cases"]
    assert isinstance(cases, list)
    case = next(case for case in cases if case["caseId"] == case_id)
    expected = case["expected"]

    actual_codes = set(_execute_case(suite, case))
    expected_codes = {ValidationCode(code) for code in expected["failureCodes"]}
    assert actual_codes == expected_codes
    assert (expected["status"] == "PASS") is (not actual_codes)

    if case["critical"]:
        assert expected["status"] == "FAIL"
        assert actual_codes
