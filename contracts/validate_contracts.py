"""Validate syntax, schemas, examples, and cross-contract vocabulary consistency."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate as validate_openapi
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parent


def read_json(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def read_yaml(name: str) -> dict:
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


def read_json_path(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_yaml_path(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def assert_unique(items: list[dict], field: str, collection: str) -> None:
    values = [item[field] for item in items]
    if len(values) != len(set(values)):
        raise ValueError(f"{collection} contains duplicate {field} values")


def definition_hash(document: dict[str, Any]) -> str:
    canonical_document = deepcopy(document)
    canonical_document["metadata"].pop("definitionHash", None)
    canonical = json.dumps(
        canonical_document,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def assert_definition_hash(document: dict[str, Any], name: str) -> None:
    expected = document["metadata"]["definitionHash"]
    actual = definition_hash(document)
    if expected != actual:
        raise ValueError(f"{name} definitionHash mismatch: expected {actual}")


def assert_object_schemas_closed(node: Any, location: str) -> None:
    """Ensure model-facing tool schemas reject unknown object properties."""
    if isinstance(node, dict):
        if node.get("type") == "object" and node.get("additionalProperties") is not False:
            raise ValueError(f"open object schema at {location}")
        for key, value in node.items():
            assert_object_schemas_closed(value, f"{location}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            assert_object_schemas_closed(value, f"{location}/{index}")


def assert_negative(validator: Draft202012Validator, instance: dict, name: str) -> None:
    if validator.is_valid(instance):
        raise ValueError(f"negative fixture unexpectedly validated: {name}")


def assert_plan_dag(steps: list[dict[str, Any]], name: str) -> None:
    step_ids = [step["step_id"] if "step_id" in step else step["id"] for step in steps]
    if len(step_ids) != len(set(step_ids)):
        raise ValueError(f"{name} contains duplicate step IDs")
    dependencies = {
        step["step_id"] if "step_id" in step else step["id"]: set(
            step["depends_on"] if "depends_on" in step else step["dependsOn"]
        )
        for step in steps
    }
    known = set(step_ids)
    for step_id, required in dependencies.items():
        missing = required - known
        if missing:
            raise ValueError(f"{name} step {step_id} has unknown dependencies: {sorted(missing)}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in visiting:
            raise ValueError(f"{name} contains a dependency cycle at {step_id}")
        if step_id in visited:
            return
        visiting.add(step_id)
        for dependency in dependencies[step_id]:
            visit(dependency)
        visiting.remove(step_id)
        visited.add(step_id)

    for step_id in step_ids:
        visit(step_id)


def assert_approval_matches_plan(
    approval: dict[str, Any], plan: dict[str, Any], case: dict[str, Any]
) -> None:
    binding = approval["binding"]
    expected = {
        "case_id": case["case_id"],
        "current_state_hash": case["current_state_hash"],
        "plan_id": plan["plan_id"],
        "plan_version": plan["version"],
        "plan_hash": plan["plan_hash"],
        "workflow": plan["workflow"],
        "agent_versions": plan["agent_versions"],
        "tool_scopes": plan["tool_permissions"],
        "data_scope": [
            {
                "case_source_id": source["case_source_id"],
                "source_version_id": source["source_version_id"],
                "source_hash": source["source_hash"],
            }
            for source in plan["source_pins"]
        ],
        "budget": plan["budget"],
    }
    for field, value in expected.items():
        if binding[field] != value:
            raise ValueError(f"stale or altered approval binding field: {field}")


def validate_agent_os_contracts(format_checker: FormatChecker) -> tuple[int, int, int]:
    schema_paths = sorted(
        path
        for directory in ("cases", "agents", "workflows", "tools", "skills")
        for path in (ROOT / directory).glob("*.schema.json")
    )
    schemas = [read_json_path(path) for path in schema_paths]
    registry = Registry()
    for schema in schemas:
        Draft202012Validator.check_schema(schema)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))

    validators = {
        path.name: Draft202012Validator(
            schema, format_checker=format_checker, registry=registry
        )
        for path, schema in zip(schema_paths, schemas, strict=True)
    }

    case = read_json_path(ROOT / "cases/examples/case.valid.json")
    case_source = read_json_path(ROOT / "cases/examples/case-source.valid.json")
    case_event = read_json_path(ROOT / "cases/examples/case-event.valid.json")
    case_plan = read_json_path(ROOT / "cases/examples/case-plan.valid.json")
    approval = read_json_path(ROOT / "cases/examples/approval-binding.valid.json")
    case_run = read_json_path(ROOT / "cases/examples/case-run.valid.json")
    stale_approval = read_json_path(
        ROOT / "cases/examples/approval-binding.invalid-stale-plan.json"
    )
    validators["case.schema.json"].validate(case)
    validators["case-source.schema.json"].validate(case_source)
    validators["case-event.schema.json"].validate(case_event)
    validators["case-plan.schema.json"].validate(case_plan)
    validators["approval-binding.schema.json"].validate(approval)
    validators["case-run.schema.json"].validate(case_run)
    validators["approval-binding.schema.json"].validate(stale_approval)
    assert_negative(
        validators["case.schema.json"],
        read_json_path(ROOT / "cases/examples/case.invalid-unknown-property.json"),
        "case.invalid-unknown-property.json",
    )

    if case_source["case_id"] != case["case_id"] or case_event["case_id"] != case["case_id"]:
        raise ValueError("case fixtures do not share one case_id")
    if case_run["case_id"] != case["case_id"]:
        raise ValueError("case run fixture does not share the case_id")
    pin = case_plan["source_pins"][0]
    for field in ("case_source_id", "source_version_id", "source_hash", "trust_level"):
        if pin[field] != case_source[field]:
            raise ValueError(f"case plan source pin drifted from CaseSource: {field}")
    assert_plan_dag(case_plan["steps"], "case-plan.valid.json")
    assert_approval_matches_plan(approval, case_plan, case)
    try:
        assert_approval_matches_plan(stale_approval, case_plan, case)
    except ValueError:
        pass
    else:
        raise ValueError("stale approval fixture unexpectedly matched the current plan")

    workflow_path = ROOT / "workflows/regulatory-impact-review.v1.0.0.yaml"
    workflow = read_yaml_path(workflow_path)
    agent_paths = sorted((ROOT / "agents").glob("*.v*.yaml"))
    tool_bundle_paths = sorted((ROOT / "tools").glob("*.v*.yaml"))
    skill_library = read_yaml_path(ROOT / "skills/initial-skills.v1.0.0.yaml")
    agents = [(path, read_yaml_path(path)) for path in agent_paths]
    tool_bundles = [(path, read_yaml_path(path)) for path in tool_bundle_paths]
    for path, definition in agents:
        validators["agent-definition.schema.json"].validate(definition)
        assert_definition_hash(definition, path.name)
    validators["workflow-definition.schema.json"].validate(workflow)
    for path, definition in tool_bundles:
        validators["tool-bundle.schema.json"].validate(definition)
        assert_definition_hash(definition, path.name)
    validators["skill-library.schema.json"].validate(skill_library)
    assert_unique(skill_library["skills"], "name", "skill library")
    assert_definition_hash(workflow, workflow_path.name)

    checked_documents = [
        *((definition, "agent-definition.schema.json", path.name) for path, definition in agents),
        (workflow, "workflow-definition.schema.json", workflow_path.name),
        *((definition, "tool-bundle.schema.json", path.name) for path, definition in tool_bundles),
    ]
    for document, validator_name, label in checked_documents:
        mutated = deepcopy(document)
        mutated["spec"]["modelMayExpandAuthority"] = True
        assert_negative(validators[validator_name], mutated, f"{label} unknown property")

    tools = [
        tool
        for _path, bundle in tool_bundles
        for tool in bundle["spec"]["tools"]
    ]
    assert_unique(tools, "name", "MCP tools")
    tool_index = {(tool["name"], tool["version"]): tool for tool in tools}
    skill_index = {
        (skill["name"], skill["version"])
        for skill in skill_library["skills"]
    }
    required_runtime_context = {
        "user_id",
        "tenant_id",
        "case_id",
        "run_id",
        "agent_name",
        "agent_version",
        "runtime_service",
        "idempotency_key",
    }
    for _path, bundle in tool_bundles:
        for tool in bundle["spec"]["tools"]:
            if tool["defaultPolicy"] != "DENY":
                raise ValueError(f"{tool['name']} is not deny-by-default")
            if set(tool["permission"]["requiredRuntimeContext"]) != required_runtime_context:
                raise ValueError(f"{tool['name']} runtime attribution context is incomplete")
            for schema_name in ("inputSchema", "resultSchema"):
                schema = tool[schema_name]
                Draft202012Validator.check_schema(schema)
                assert_object_schemas_closed(schema, f"{tool['name']}/{schema_name}")

    for _path, agent_definition in agents:
        for skill_ref in agent_definition["spec"]["skills"]:
            key = (skill_ref["name"], skill_ref["version"])
            if key not in skill_index:
                raise ValueError(f"agent references unknown skill version: {key}")
        for tool_ref in agent_definition["spec"]["tools"]:
            key = (tool_ref["name"], tool_ref["version"])
            if key not in tool_index:
                raise ValueError(f"agent references unknown tool version: {key}")
            manifest = tool_index[key]
            if tool_ref["riskClass"] != manifest["riskClass"]:
                raise ValueError(f"agent risk class drift for {tool_ref['name']}")
            if tool_ref["requiredScopes"] != manifest["permission"]["requiredScopes"]:
                raise ValueError(f"agent scope drift for {tool_ref['name']}")

    workflow_steps = workflow["spec"]["steps"]
    assert_plan_dag(workflow_steps, workflow_path.name)
    states = set(workflow["spec"]["states"])
    if workflow["spec"]["initialState"] not in states:
        raise ValueError("workflow initialState is not declared")
    if not set(workflow["spec"]["terminalStates"]).issubset(states):
        raise ValueError("workflow terminalStates are not all declared")
    for step in workflow_steps:
        if step["state"] not in states:
            raise ValueError(f"workflow step {step['id']} uses undeclared state")
        for tool_ref in step["tools"]:
            if (tool_ref["name"], tool_ref["version"]) not in tool_index:
                raise ValueError(f"workflow references unknown MCP tool: {tool_ref}")
    if workflow["metadata"]["releaseState"] == "DRAFT" and workflow["spec"]["executionEnabled"]:
        raise ValueError("draft workflow must not be executable")

    return len(schemas), 6, len(tools)


def main() -> None:
    summary_schema = read_json("summary_schema.json")
    taxonomy_schema = read_json("taxonomy_schema.json")
    taxonomy = read_yaml("taxonomy.yaml")
    api_contract = read_yaml("api_contract.yaml")

    Draft202012Validator.check_schema(summary_schema)
    Draft202012Validator.check_schema(taxonomy_schema)
    format_checker = FormatChecker()
    taxonomy_validator = Draft202012Validator(
        taxonomy_schema, format_checker=format_checker
    )
    taxonomy_validator.validate(taxonomy)

    summary_validator = Draft202012Validator(
        summary_schema, format_checker=format_checker
    )
    valid_example = read_json("examples/summary.valid.json")
    invalid_example = read_json("examples/summary.invalid-no-drugs.json")
    summary_validator.validate(valid_example)
    if summary_validator.is_valid(invalid_example):
        raise ValueError("negative summary example unexpectedly passed Drug scope validation")

    for collection in ("categories", "drug_subtypes", "process_lenses"):
        assert_unique(taxonomy[collection], "id", collection)
        assert_unique(taxonomy[collection], "label", collection)
    assert_unique(taxonomy["attention_levels"]["levels"], "id", "attention_levels")

    category_labels = {item["label"] for item in taxonomy["categories"]}
    schema_categories = set(summary_schema["$defs"]["category"]["enum"])
    if category_labels != schema_categories:
        raise ValueError("summary-schema categories have drifted from taxonomy.yaml")

    subtype_labels = {item["label"] for item in taxonomy["drug_subtypes"]}
    schema_subtypes = set(
        summary_schema["$defs"]["scope"]["properties"]["drug_subtypes"]["items"][
            "enum"
        ]
    )
    if subtype_labels != schema_subtypes:
        raise ValueError("summary-schema drug subtypes have drifted from taxonomy.yaml")

    lens_ids = {item["id"] for item in taxonomy["process_lenses"]}
    schema_lenses = set(
        summary_schema["$defs"]["violation"]["properties"]["process_lenses"][
            "items"
        ]["enum"]
    )
    if lens_ids != schema_lenses:
        raise ValueError("summary-schema process lenses have drifted from taxonomy.yaml")

    validate_openapi(api_contract)
    agent_os_schema_count, case_fixture_count, tool_count = validate_agent_os_contracts(
        format_checker
    )
    print(
        "Validated OpenAPI, JSON Schemas, examples, taxonomy, vocabulary parity, "
        f"{agent_os_schema_count} Agent OS schemas, {case_fixture_count} positive "
        f"case fixtures, approval freshness, and {tool_count} deny-by-default MCP tools."
    )


if __name__ == "__main__":
    main()
