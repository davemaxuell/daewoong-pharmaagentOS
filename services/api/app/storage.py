from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Protocol

import boto3
import httpx
from botocore.config import Config
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from app.config import Settings


class IntegrityError(RuntimeError):
    pass


class ImmutableObjectStore(Protocol):
    def put(self, namespace: str, content: bytes) -> tuple[str, str]: ...

    def get(self, key: str) -> bytes: ...

    def verify(self, key: str, expected_sha256: str) -> bool: ...

    def healthcheck(self) -> None: ...


def _content_address(namespace: str, content: bytes) -> tuple[str, str]:
    digest = hashlib.sha256(content).hexdigest()
    safe_namespace = "".join(c for c in namespace if c.isalnum() or c in "-_") or "source"
    return f"{safe_namespace}/{digest[:2]}/{digest}", digest


def _validated_key(key: str) -> str:
    path = PurePosixPath(key)
    if not key or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise FileNotFoundError(key)
    return path.as_posix()


class LocalImmutableObjectStore:
    """Content-addressed local adapter mirroring immutable object-store semantics."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def put(self, namespace: str, content: bytes) -> tuple[str, str]:
        key, digest = _content_address(namespace, content)
        target = (self.root / key).resolve()
        if self.root not in target.parents:
            raise ValueError("Object key escaped configured store")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise IntegrityError("Existing content-addressed object failed integrity check")
        else:
            temporary = target.with_suffix(f".{os.getpid()}.tmp")
            try:
                with temporary.open("xb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        return key, digest

    def get(self, key: str) -> bytes:
        target = (self.root / _validated_key(key)).resolve()
        if self.root not in target.parents or not target.is_file():
            raise FileNotFoundError(key)
        return target.read_bytes()

    def verify(self, key: str, expected_sha256: str) -> bool:
        try:
            content = self.get(key)
        except FileNotFoundError:
            return False
        return hashlib.sha256(content).hexdigest() == expected_sha256

    def healthcheck(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)


class S3ImmutableObjectStore:
    """Private S3-compatible content-addressed storage with read-after-write checks."""

    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        region: str = "auto",
        url_style: str = "virtual",
        client: Any | None = None,
    ) -> None:
        self.bucket = bucket
        self.client = client or boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
            config=Config(
                connect_timeout=5,
                read_timeout=30,
                retries={"max_attempts": 3, "mode": "standard"},
                s3={"addressing_style": url_style},
            ),
        )

    @staticmethod
    def _missing(exc: ClientError) -> bool:
        error = exc.response.get("Error", {})
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        return status == 404 or str(error.get("Code")) in {"404", "NoSuchKey", "NotFound"}

    def put(self, namespace: str, content: bytes) -> tuple[str, str]:
        key, digest = _content_address(namespace, content)
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if not self._missing(exc):
                raise
        else:
            if not self.verify(key, digest):
                raise IntegrityError("Existing content-addressed object failed integrity check")
            return key, digest

        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content,
                ContentType="application/octet-stream",
                Metadata={"sha256": digest},
                IfNoneMatch="*",
            )
        except ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            code = str(exc.response.get("Error", {}).get("Code"))
            if status != 412 and code not in {"PreconditionFailed", "412"}:
                raise
        if not self.verify(key, digest):
            raise IntegrityError("Uploaded content-addressed object failed integrity check")
        return key, digest

    def get(self, key: str) -> bytes:
        normalized_key = _validated_key(key)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=normalized_key)
        except ClientError as exc:
            if self._missing(exc):
                raise FileNotFoundError(key) from exc
            raise
        body = response["Body"]
        try:
            content = body.read()
        finally:
            close = getattr(body, "close", None)
            if close:
                close()
        if not isinstance(content, bytes):
            raise IntegrityError("Object storage returned a non-binary response")
        return content

    def verify(self, key: str, expected_sha256: str) -> bool:
        try:
            content = self.get(key)
        except FileNotFoundError:
            return False
        return hashlib.sha256(content).hexdigest() == expected_sha256

    def healthcheck(self) -> None:
        self.client.head_bucket(Bucket=self.bucket)


class SupabaseImmutableObjectStore:
    """Private content-addressed storage using Supabase's server-side Storage API."""

    def __init__(
        self,
        *,
        base_url: str,
        bucket: str,
        secret_key: str,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.bucket = _validated_key(bucket)
        self.secret_key = secret_key
        self.client = client or httpx.Client(timeout=httpx.Timeout(30, connect=5))

    def _headers(self, **extra: str) -> dict[str, str]:
        # New sb_secret_* keys are API keys rather than JWTs. Supabase requires
        # them in `apikey`; putting them in Authorization makes JWT middleware
        # reject otherwise valid server requests.
        return {
            "apikey": self.secret_key,
            "User-Agent": "Daewoong-FDA-Drug-Intel/0.1",
            **extra,
        }

    def _object_url(self, key: str) -> str:
        return f"{self.base_url}/storage/v1/object/{self.bucket}/{_validated_key(key)}"

    @staticmethod
    def _missing(response: httpx.Response) -> bool:
        if response.status_code == 404:
            return True
        try:
            code = str(response.json().get("code", ""))
        except (TypeError, ValueError):
            return False
        return code in {"NoSuchKey", "not_found"}

    def put(self, namespace: str, content: bytes) -> tuple[str, str]:
        key, digest = _content_address(namespace, content)
        try:
            existing = self.get(key)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if hashlib.sha256(existing).hexdigest() != digest:
                raise IntegrityError("Existing content-addressed object failed integrity check")
            return key, digest

        response = self.client.post(
            self._object_url(key),
            headers=self._headers(
                **{
                    "Content-Type": "application/octet-stream",
                    "x-upsert": "false",
                    "x-metadata": f'{{"sha256":"{digest}"}}',
                }
            ),
            content=content,
        )
        if response.status_code not in {200, 201}:
            # A concurrent writer may win the immutable insert. Only accept the
            # conflict when the stored bytes still match this content address.
            if response.status_code not in {400, 409} or not self.verify(key, digest):
                response.raise_for_status()
        if not self.verify(key, digest):
            raise IntegrityError("Uploaded content-addressed object failed integrity check")
        return key, digest

    def get(self, key: str) -> bytes:
        response = self.client.get(self._object_url(key), headers=self._headers())
        if self._missing(response):
            raise FileNotFoundError(key)
        response.raise_for_status()
        return response.content

    def verify(self, key: str, expected_sha256: str) -> bool:
        try:
            content = self.get(key)
        except FileNotFoundError:
            return False
        return hashlib.sha256(content).hexdigest() == expected_sha256

    def healthcheck(self) -> None:
        response = self.client.get(
            f"{self.base_url}/storage/v1/bucket/{self.bucket}",
            headers=self._headers(),
        )
        response.raise_for_status()


def build_object_store(settings: Settings) -> ImmutableObjectStore:
    if settings.object_store_backend == "local":
        return LocalImmutableObjectStore(settings.object_store_path)
    if settings.object_store_backend == "supabase":
        assert settings.object_store_supabase_url is not None
        assert settings.object_store_supabase_secret_key is not None
        return SupabaseImmutableObjectStore(
            base_url=settings.object_store_supabase_url,
            bucket=settings.object_store_supabase_bucket,
            secret_key=settings.object_store_supabase_secret_key.get_secret_value(),
        )
    assert settings.object_store_s3_endpoint is not None
    assert settings.object_store_s3_bucket is not None
    assert settings.object_store_s3_access_key_id is not None
    assert settings.object_store_s3_secret_access_key is not None
    return S3ImmutableObjectStore(
        endpoint_url=settings.object_store_s3_endpoint,
        bucket=settings.object_store_s3_bucket,
        access_key_id=settings.object_store_s3_access_key_id.get_secret_value(),
        secret_access_key=settings.object_store_s3_secret_access_key.get_secret_value(),
        region=settings.object_store_s3_region,
        url_style=settings.object_store_s3_url_style,
    )
