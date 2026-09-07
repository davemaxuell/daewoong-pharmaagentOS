"""Locate reviewed resources in either the workspace or a packaged service."""

from pathlib import Path


def resource_root() -> Path:
    packaged = Path(__file__).resolve().parent / "_resources"
    if packaged.is_dir():
        return packaged
    return Path(__file__).resolve().parents[3]
