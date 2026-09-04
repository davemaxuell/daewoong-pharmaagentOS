from __future__ import annotations

import hashlib
from io import BytesIO

import httpx
import pytest
from botocore.exceptions import ClientError
from pydantic import ValidationError

from app.config import Settings
from app.storage import (
    IntegrityError,
    LocalImmutableObjectStore,
    S3ImmutableObjectStore,
    SupabaseImmutableObjectStore,
)


def _client_error(code: str, status: int, operation: str) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": code},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        operation,
    )


class MemoryS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.metadata: dict[tuple[str, str], dict[str, str]] = {}
        self.checked_buckets: list[str] = []

    def head_bucket(self, *, Bucket: str) -> None:
        self.checked_buckets.append(Bucket)

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        identity = (Bucket, Key)
        if identity not in self.objects:
            raise _client_error("NoSuchKey", 404, "HeadObject")
        return {
            "ContentLength": len(self.objects[identity]),
            "Metadata": self.metadata[identity],
        }

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str,
        Metadata: dict[str, str],
        IfNoneMatch: str,
    ) -> dict[str, str]:
        assert ContentType == "application/octet-stream"
        assert IfNoneMatch == "*"
        identity = (Bucket, Key)
        if identity in self.objects:
            raise _client_error("PreconditionFailed", 412, "PutObject")
        self.objects[identity] = Body
        self.metadata[identity] = Metadata
        return {"ETag": "test"}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, BytesIO]:
        identity = (Bucket, Key)
        if identity not in self.objects:
            raise _client_error("NoSuchKey", 404, "GetObject")
        return {"Body": BytesIO(self.objects[identity])}


def test_local_store_is_content_addressed_and_rejects_missing_keys(tmp_path) -> None:
    store = LocalImmutableObjectStore(tmp_path / "objects")
    content = b"official FDA source"

    key, digest = store.put("fda-html", content)

    assert key == f"fda-html/{digest[:2]}/{digest}"
    assert store.get(key) == content
    assert store.verify(key, digest)
    assert not store.verify("missing/object", digest)
    with pytest.raises(FileNotFoundError):
        store.get("../outside")


def test_s3_store_round_trip_is_idempotent_and_verified() -> None:
    client = MemoryS3Client()
    store = S3ImmutableObjectStore(
        endpoint_url="https://storage.example",
        bucket="fda-objects",
        access_key_id="access",
        secret_access_key="secret",
        client=client,
    )
    content = b"immutable warning letter"

    first = store.put("fda-html", content)
    second = store.put("fda-html", content)
    store.healthcheck()

    assert first == second
    assert store.get(first[0]) == content
    assert store.verify(first[0], first[1])
    assert client.metadata[("fda-objects", first[0])] == {"sha256": first[1]}
    assert client.checked_buckets == ["fda-objects"]


def test_s3_store_fails_closed_when_existing_content_is_corrupt() -> None:
    client = MemoryS3Client()
    store = S3ImmutableObjectStore(
        endpoint_url="https://storage.example",
        bucket="fda-objects",
        access_key_id="access",
        secret_access_key="secret",
        client=client,
    )
    content = b"expected"
    digest = hashlib.sha256(content).hexdigest()
    key = f"fda-html/{digest[:2]}/{digest}"
    client.objects[("fda-objects", key)] = b"corrupt"
    client.metadata[("fda-objects", key)] = {"sha256": digest}

    with pytest.raises(IntegrityError):
        store.put("fda-html", content)


def test_s3_settings_require_complete_https_credentials() -> None:
    with pytest.raises(ValidationError, match="S3 object storage is missing"):
        Settings(app_env="staging", object_store_backend="s3")

    with pytest.raises(ValidationError, match="must use HTTPS"):
        Settings(
            app_env="staging",
            object_store_backend="s3",
            object_store_s3_endpoint="http://storage.example",
            object_store_s3_bucket="fda-objects",
            object_store_s3_access_key_id="access",
            object_store_s3_secret_access_key="secret",
        )


def test_supabase_store_round_trip_is_idempotent_and_uses_api_key_header() -> None:
    objects: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["apikey"] == "sb_secret_test"
        assert "authorization" not in request.headers
        path = request.url.path
        if path == "/storage/v1/bucket/fda-evidence":
            return httpx.Response(200, json={"id": "fda-evidence"})
        prefix = "/storage/v1/object/fda-evidence/"
        assert path.startswith(prefix)
        key = path.removeprefix(prefix)
        if request.method == "GET":
            if key not in objects:
                return httpx.Response(400, json={"code": "NoSuchKey"})
            return httpx.Response(200, content=objects[key])
        assert request.method == "POST"
        assert request.headers["x-upsert"] == "false"
        if key in objects:
            return httpx.Response(409, json={"code": "Duplicate"})
        objects[key] = request.content
        return httpx.Response(200, json={"Key": key})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = SupabaseImmutableObjectStore(
        base_url="https://project.supabase.co",
        bucket="fda-evidence",
        secret_key="sb_secret_test",
        client=client,
    )
    content = b"immutable Supabase warning letter"

    first = store.put("fda-html", content)
    second = store.put("fda-html", content)
    store.healthcheck()

    assert first == second
    assert store.get(first[0]) == content
    assert store.verify(first[0], first[1])


def test_supabase_settings_require_complete_https_credentials() -> None:
    with pytest.raises(ValidationError, match="Supabase object storage is missing"):
        Settings(app_env="staging", object_store_backend="supabase")

    with pytest.raises(ValidationError, match="must use HTTPS"):
        Settings(
            app_env="staging",
            object_store_backend="supabase",
            object_store_supabase_url="http://project.supabase.co",
            object_store_supabase_secret_key="sb_secret_test",
        )
