from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable

DIMENSIONS = 64
TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]+")


def tokens(value: str) -> list[str]:
    """Return bounded, deterministic lexical units for local hybrid retrieval."""

    return TOKEN_PATTERN.findall(value.casefold())[:4_000]


def deterministic_embedding(value: str, *, dimensions: int = DIMENSIONS) -> list[float]:
    """Feature-hash text without an external model or non-reproducible network call."""

    vector = [0.0] * dimensions
    for token in tokens(value):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        direction = 1.0 if digest[4] & 1 else -1.0
        vector[index] += direction
    magnitude = math.sqrt(sum(component * component for component in vector))
    return vector if magnitude == 0 else [component / magnitude for component in vector]


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    left_values = list(left)
    right_values = list(right)
    if len(left_values) != len(right_values):
        return 0.0
    return sum(a * b for a, b in zip(left_values, right_values, strict=True))
