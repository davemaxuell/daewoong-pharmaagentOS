"""Validate a rendered Kubernetes environment before applying it. Never deploys."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml


def inspect_documents(documents: list[dict]) -> list[str]:
    errors = []
    configs = [item.get("data", {}) for item in documents if item.get("kind") == "ConfigMap"]
    for config in configs:
        for name, value in config.items():
            if "example.invalid" in str(value) or "replace-before-deploy" in str(value):
                errors.append(f"Configure {name} for the target environment")
        if config.get("APP_ENV") == "production":
            for name in ("DEV_AUTH_ENABLED", "AUTO_CREATE_SCHEMA"):
                if config.get(name) != "false":
                    errors.append(f"Production requires {name}=false")
    for document in documents:
        kind = document.get("kind")
        spec = document.get("spec", {})
        if kind == "CronJob":
            spec = spec.get("jobTemplate", {}).get("spec", {})
        pod = spec.get("template", {}).get("spec", {})
        for container in pod.get("containers", []):
            image = container.get("image", "")
            if not re.fullmatch(r"[^\s]+@sha256:[a-f0-9]{64}", image):
                errors.append(f"Pin {document['metadata']['name']}/{container['name']} by digest")
            elif "example.invalid" in image or image.endswith("0" * 64):
                errors.append(f"Replace placeholder image for {document['metadata']['name']}")
    policies = [item for item in documents if item.get("kind") == "NetworkPolicy"]
    if policies and not any(
        port.get("port") == 5432
        for policy in policies
        for rule in policy.get("spec", {}).get("egress", [])
        for port in rule.get("ports", [])
    ):
        errors.append("Add restricted PostgreSQL egress for the actual database destination")
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path, help="Output from kubectl kustomize the target overlay")
    args = parser.parse_args()
    documents = [doc for doc in yaml.safe_load_all(args.manifest.read_text()) if doc]
    errors = inspect_documents(documents)
    if errors:
        print("Deployment preflight BLOCKED:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Manifest preflight passed. Verify target secrets, connectivity and release evidence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
