"""Validate a rendered Kubernetes environment before applying it. Never deploys."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
from pathlib import Path

import yaml


def _restricted_database_egress(policies: list[dict]) -> bool:
    for policy in policies:
        for rule in policy.get("spec", {}).get("egress", []):
            if not any(port.get("port") == 5432 for port in rule.get("ports", [])):
                continue
            peers = rule.get("to", [])
            if not peers:
                continue
            for peer in peers:
                if "ipBlock" in peer:
                    try:
                        if ipaddress.ip_network(peer["ipBlock"]["cidr"]).prefixlen == 0:
                            break
                    except (KeyError, ValueError):
                        break
                elif not any(
                    peer.get(key, {}).get("matchLabels")
                    or peer.get(key, {}).get("matchExpressions")
                    for key in ("podSelector", "namespaceSelector")
                ):
                    break
            else:
                return True
    return False


def _inspect_config(config: dict, label: str) -> list[str]:
    errors = []
    for name, value in config.items():
        if any(
            marker in str(value)
            for marker in (
                "example.invalid",
                "replace-before-deploy",
                "YOUR_",
                "${{",
                "<replace",
            )
        ):
            errors.append(f"Configure {label}/{name} for the target environment")
    if config.get("APP_ENV") == "production":
        for name in ("DEV_AUTH_ENABLED", "AUTO_CREATE_SCHEMA"):
            if str(config.get(name)).lower() != "false":
                errors.append(f"Production requires {label}/{name}=false")
        if str(config.get("DEBUG", "false")).lower() != "false":
            errors.append(f"Production requires {label}/DEBUG=false")
        if "*" in str(config.get("ALLOWED_HOSTS", "")):
            errors.append(f"Production requires explicit {label}/ALLOWED_HOSTS")
    if "AUTH_URL" in config:
        mode = config.get("AUTH_ADMISSION_MODE")
        if mode not in {"public", "restricted"}:
            errors.append(f"Select public or restricted {label}/AUTH_ADMISSION_MODE")
        if mode == "restricted":
            try:
                directory = json.loads(
                    str(config.get("AUTH_SUBJECT_ROLE_ASSIGNMENTS_JSON", "{}"))
                )
                if not isinstance(directory, dict) or not directory:
                    raise ValueError
            except (ValueError, TypeError):
                errors.append(
                    f"Configure admitted subjects in {label}/AUTH_SUBJECT_ROLE_ASSIGNMENTS_JSON"
                )
    return errors


def inspect_documents(documents: list[dict]) -> list[str]:
    if not documents or any(
        not isinstance(item, dict) or not item.get("kind") for item in documents
    ):
        return ["Supply a non-empty Kubernetes manifest containing resource objects"]
    errors = []
    configs = {
        (
            item.get("metadata", {}).get("namespace", "default"),
            item["metadata"]["name"],
        ): item.get("data", {})
        for item in documents
        if item.get("kind") == "ConfigMap"
    }
    containers_found = 0
    for document in documents:
        kind = document.get("kind")
        metadata = document.get("metadata", {})
        namespace = metadata.get("namespace", "default")
        spec = document.get("spec", {})
        if kind == "CronJob":
            spec = spec.get("jobTemplate", {}).get("spec", {})
        pod = spec if kind == "Pod" else spec.get("template", {}).get("spec", {})
        for container in pod.get("containers", []) + pod.get("initContainers", []):
            containers_found += 1
            label = f"{metadata.get('name', '<unnamed>')}/{container.get('name', '<unnamed>')}"
            effective = {}
            for source in container.get("envFrom", []):
                ref = source.get("configMapRef")
                if ref:
                    config = configs.get((namespace, ref.get("name")))
                    if config is None:
                        errors.append(f"Include referenced ConfigMap for {label}")
                    else:
                        effective.update(
                            {source.get("prefix", "") + k: v for k, v in config.items()}
                        )
            for entry in container.get("env", []):
                if "value" in entry:
                    effective[entry["name"]] = entry["value"]
                elif "configMapKeyRef" in entry.get("valueFrom", {}):
                    ref = entry["valueFrom"]["configMapKeyRef"]
                    config = configs.get((namespace, ref.get("name")), {})
                    if ref.get("key") not in config:
                        errors.append(
                            f"Include referenced ConfigMap key for {label}/{entry['name']}"
                        )
                    else:
                        effective[entry["name"]] = config[ref["key"]]
                else:
                    # Runtime secret values cannot be qualified by a static manifest.
                    effective.pop(entry["name"], None)
            errors.extend(_inspect_config(effective, label))
            image = container.get("image", "")
            if not re.fullmatch(r"[^\s]+@sha256:[a-f0-9]{64}", image):
                errors.append(f"Pin {label} by digest")
            elif "example.invalid" in image or image.endswith("0" * 64):
                errors.append(f"Replace placeholder image for {label}")
    if not containers_found:
        errors.append("Manifest contains no runnable workload containers")
    policies = [item for item in documents if item.get("kind") == "NetworkPolicy"]
    if not _restricted_database_egress(policies):
        errors.append(
            "Add restricted PostgreSQL egress for the actual database destination"
        )
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "manifest", type=Path, help="Output from kubectl kustomize the target overlay"
    )
    args = parser.parse_args()
    try:
        documents = [
            doc
            for doc in yaml.safe_load_all(args.manifest.read_text(encoding="utf-8-sig"))
            if doc is not None
        ]
        errors = inspect_documents(documents)
    except (OSError, UnicodeError, yaml.YAMLError, KeyError, TypeError, AttributeError):
        # Do not echo parser exceptions: they can contain secret manifest values.
        errors = ["Cannot inspect manifest: provide readable, valid Kubernetes YAML"]
    if errors:
        print("Deployment preflight BLOCKED:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        "Manifest preflight passed. Verify target secrets, connectivity and release evidence."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
