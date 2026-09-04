from __future__ import annotations

import pytest
from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON
from sqlalchemy.dialects import postgresql, sqlite

from app.vector import PortableVector


def test_portable_vector_uses_json_for_sqlite_and_pgvector_for_postgres() -> None:
    vector = PortableVector(1_536)

    assert isinstance(vector.load_dialect_impl(sqlite.dialect()), JSON)
    assert isinstance(vector.load_dialect_impl(postgresql.dialect()), Vector)


def test_portable_vector_rejects_dimension_mismatch() -> None:
    vector = PortableVector(3)

    assert vector.process_bind_param([1.0, 2.0, 3.0], sqlite.dialect()) == [1.0, 2.0, 3.0]
    with pytest.raises(ValueError, match="exactly 3"):
        vector.process_bind_param([1.0], sqlite.dialect())
