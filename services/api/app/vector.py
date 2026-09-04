from __future__ import annotations

from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON
from sqlalchemy.engine import Dialect
from sqlalchemy.sql.type_api import TypeEngine
from sqlalchemy.types import TypeDecorator


class PortableVector(TypeDecorator[list[float]]):
    """Use pgvector in PostgreSQL and JSON in the local SQLite profile."""

    impl = JSON
    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        super().__init__()
        self.dimensions = dimensions

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(self.dimensions))
        return dialect.type_descriptor(JSON())

    def process_bind_param(
        self, value: list[float] | None, dialect: Dialect
    ) -> list[float] | None:
        if value is None:
            return None
        if len(value) != self.dimensions:
            raise ValueError(
                f"Embedding must contain exactly {self.dimensions} values, received {len(value)}"
            )
        return [float(item) for item in value]

    def process_result_value(
        self, value: object, dialect: Dialect
    ) -> list[float] | None:
        if value is None:
            return None
        if hasattr(value, "tolist"):
            value = value.tolist()
        if not isinstance(value, (list, tuple)):
            raise ValueError("Stored embedding is not a vector")
        return [float(item) for item in value]
