from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(SERVICE_ROOT / ".env", SERVICE_ROOT / ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "FDA Drug Warning Letter Intelligence API"
    app_version: str = "0.1.0"
    app_env: Literal["local", "development", "staging", "production", "test"] = "local"
    debug: bool = False
    database_url: str = Field(
        default=f"sqlite+aiosqlite:///{(SERVICE_ROOT / 'data' / 'fda_intel.db').as_posix()}",
        validation_alias=AliasChoices("database_url", "DATABASE_URL", "POSTGRES_URL"),
    )
    auto_create_schema: bool = True
    object_store_backend: Literal["local", "s3", "supabase"] = "local"
    object_store_path: Path = SERVICE_ROOT / "data" / "objects"
    object_store_s3_endpoint: str | None = None
    object_store_s3_bucket: str | None = None
    object_store_s3_access_key_id: SecretStr | None = None
    object_store_s3_secret_access_key: SecretStr | None = None
    object_store_s3_region: str = "auto"
    object_store_s3_url_style: Literal["virtual", "path"] = "virtual"
    object_store_supabase_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "object_store_supabase_url",
            "OBJECT_STORE_SUPABASE_URL",
            "SUPABASE_URL",
        ),
    )
    object_store_supabase_secret_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "object_store_supabase_secret_key",
            "OBJECT_STORE_SUPABASE_SECRET_KEY",
            "SUPABASE_SECRET_KEY",
        ),
    )
    object_store_supabase_bucket: str = "fda-evidence"
    # Local convenience only. Production runs the durable worker as a separate
    # process so API scaling cannot duplicate long-running ingestion work.
    embedded_worker_enabled: bool = False

    dev_auth_enabled: bool = True
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    oidc_public_key: str | None = None
    oidc_hs256_secret: SecretStr | None = None
    oidc_algorithms: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["RS256"]
    )
    oidc_role_claim: str = "roles"
    oidc_group_role_map: dict[str, str] = Field(default_factory=dict)

    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    allowed_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver"]
    )
    max_request_bytes: int = 1_048_576
    max_rag_query_chars: int = 2_000
    default_page_size: int = 25
    max_page_size: int = 100

    fda_allowed_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["www.fda.gov", "fda.gov"]
    )
    fda_user_agent: str = "Daewoong-FDA-Drug-Intel/0.1 (contact: configure-before-network-use)"
    fda_request_delay_seconds: float = 30.0
    fda_max_response_bytes: int = 15 * 1024 * 1024
    fda_max_redirects: int = 5
    fda_timeout_seconds: float = 30.0
    fda_robots_cache_seconds: int = 3_600
    fda_robots_max_response_bytes: int = 256 * 1024
    fda_robots_fail_closed: bool = True
    fda_listing_url: str = (
        "https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/"
        "compliance-actions-and-activities/warning-letters"
    )
    fda_source_client_version: str = "fda-source-v2"
    drug_scope_rule_version: str = "drug-scope-v1"
    parser_version: str = "fda-html-datatables-v3"
    taxonomy_version: str = "drug-taxonomy-v1.0.0"
    chunker_version: str = "structure-v1"

    # The discovery window and active-corpus retention period are deliberately
    # separate. Source versions and change events are retained when a letter
    # ages out; only its eligibility for active browsing/RAG is revoked.
    corpus_backfill_years: int = Field(default=3, ge=1, le=20)
    corpus_active_retention_years: int = Field(default=5, ge=1, le=50)

    # Email uses a transactional outbox. SMTP is opt-in so local/test execution
    # cannot send mail merely because a warning letter fixture was ingested.
    notification_default_recipient: str = "grisellacrystabel@gmail.com"
    smtp_enabled: bool = False
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65_535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from_email: str | None = None
    smtp_from_name: str = "Daewoong FDA Warning Letter Update"
    smtp_starttls: bool = True
    smtp_use_ssl: bool = False
    smtp_timeout_seconds: float = Field(default=15.0, gt=0, le=60)

    # AI generation is opt-in. The API key is loaded only from the server-side
    # environment/.env file and is represented as SecretStr to prevent accidental
    # disclosure through settings repr/logging.
    llm_provider: Literal["none", "gemini"] = "none"
    llm_model_id: str = "gemini-3.1-flash-lite"
    # Chat clients select a profile, never an arbitrary provider model ID. Auto routing maps
    # each request to one of these server-controlled allowlist entries.
    chat_fast_model_id: str = "gemini-3.1-flash-lite"
    chat_balanced_model_id: str = "gemini-3.5-flash"
    chat_deep_model_id: str = "gemini-3.7-flash"
    embedding_enabled: bool = False
    embedding_model_id: str = "gemini-embedding-2"
    embedding_dimensions: int = 1_536
    embedding_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    embedding_batch_size: int = Field(default=32, ge=1, le=250)
    llm_prompt_version: str = "rag-grounded-v1"
    llm_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    llm_max_output_tokens: int = Field(default=1_200, ge=128, le=8_192)
    # Document translation and structured analysis intentionally use a separate,
    # stable GA model profile. They are persisted and reused, so correctness and
    # output headroom take precedence over the chat model's low latency.
    document_ai_model_id: str = "gemini-3.7-flash"
    document_ai_fallback_model_ids: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["gemini-3.6-flash", "gemini-3.5-flash"]
    )
    document_ai_prompt_version: str = "letter-artifacts-bilingual-v2"
    # Regulatory translation prefers 3.7, then uses 3.6/3.5 and the high-volume 3.1 Lite model
    # only behind strict v3 language, structure, protected-token, date, and closing validation.
    document_translation_model_id: str = "gemini-3.7-flash"
    document_translation_fallback_model_ids: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
        ]
    )
    document_translation_prompt_version: str = "letter-translation-ko-v4"
    document_ai_timeout_seconds: float = Field(default=90.0, gt=0, le=180)
    document_ai_max_output_tokens: int = Field(default=16_384, ge=1_024, le=65_536)
    document_ai_attempts_per_model: int = Field(default=2, ge=1, le=3)
    document_ai_validation_attempts: int = Field(default=3, ge=1, le=4)
    document_ai_retry_backoff_seconds: float = Field(default=0.5, ge=0, le=5)
    document_ai_rate_limit_backoff_seconds: float = Field(default=2.0, ge=0, le=60)
    gemini_api_key: SecretStr | None = None

    rag_rate_limit_per_minute: int = 30
    document_ai_rate_limit_per_minute: int = 10
    admin_rate_limit_per_minute: int = 20

    # Agent-runtime admission controls are enforced from durable run records, so
    # horizontal API replicas share the same quotas.
    agent_run_rate_limit_per_hour: int = Field(default=20, ge=1, le=10_000)
    agent_active_runs_per_subject: int = Field(default=5, ge=1, le=100)

    # Temporal is the production outer workflow. The database queue remains the
    # local/test fallback and activity-level recovery journal.
    temporal_enabled: bool = False
    temporal_address: str = "temporal:7233"
    temporal_namespace: str = "pharma-agent-os"
    temporal_task_queue: str = "pharma-case-workflows"
    temporal_tls_enabled: bool = False
    temporal_tls_ca_path: Path | None = None
    temporal_tls_cert_path: Path | None = None
    temporal_tls_key_path: Path | None = None

    # Central telemetry is opt-in locally. Production exports OTLP to the private
    # collector endpoint and does not include prompt/document bodies in spans.
    otel_service_name: str = "pharma-agent-api"
    otel_exporter_otlp_endpoint: str | None = None

    # Environment secrets support local development only; Kubernetes/production
    # should use workload identity plus the configured external provider.
    secret_provider: Literal["environment", "aws"] = "environment"
    secrets_aws_region: str | None = None
    secrets_aws_prefix: str = "pharma-agent-os/"

    @field_validator(
        "allowed_origins",
        "allowed_hosts",
        "fda_allowed_hosts",
        "oidc_algorithms",
        "document_ai_fallback_model_ids",
        "document_translation_fallback_model_ids",
        mode="before",
    )
    @classmethod
    def parse_list_setting(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("["):
                return json.loads(value)
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("oidc_group_role_map", mode="before")
    @classmethod
    def parse_role_map(cls, value: object) -> object:
        if isinstance(value, str):
            return json.loads(value) if value.strip() else {}
        return value

    @field_validator("oidc_public_key", mode="before")
    @classmethod
    def normalize_public_key_pem(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.replace("\\n", "\n").strip()
            return normalized or None
        return value

    @field_validator("fda_allowed_hosts")
    @classmethod
    def normalize_hosts(cls, value: list[str]) -> list[str]:
        return sorted({host.rstrip(".").lower() for host in value})

    @field_validator(
        "llm_model_id",
        "chat_fast_model_id",
        "chat_balanced_model_id",
        "chat_deep_model_id",
        "embedding_model_id",
        "document_ai_model_id",
        "document_translation_model_id",
    )
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        value = value.strip()
        if not value or not all(character.isalnum() or character in "-._" for character in value):
            raise ValueError("LLM_MODEL_ID contains unsupported characters")
        return value

    @field_validator("embedding_dimensions")
    @classmethod
    def validate_embedding_dimensions(cls, value: int) -> int:
        # The database contract is vector(1536). Changing this setting requires a controlled
        # full-corpus re-embedding and schema migration; accepting another value here would make
        # PostgreSQL writes fail at runtime and could mix incompatible vector spaces.
        if value != 1_536:
            raise ValueError("EMBEDDING_DIMENSIONS must be 1536")
        return value

    def chat_model_id(self, profile: Literal["fast", "balanced", "deep"]) -> str:
        return {
            "fast": self.chat_fast_model_id,
            "balanced": self.chat_balanced_model_id,
            "deep": self.chat_deep_model_id,
        }[profile]

    @field_validator("document_ai_fallback_model_ids", "document_translation_fallback_model_ids")
    @classmethod
    def validate_fallback_model_ids(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw in value:
            model_id = raw.strip()
            if not model_id or not all(
                character.isalnum() or character in "-._" for character in model_id
            ):
                raise ValueError("Document AI fallback list contains an invalid model ID")
            if model_id not in normalized:
                normalized.append(model_id)
        return normalized

    @model_validator(mode="after")
    def validate_security_posture(self) -> Settings:
        if self.object_store_backend == "s3":
            required_s3_values = {
                "OBJECT_STORE_S3_ENDPOINT": self.object_store_s3_endpoint,
                "OBJECT_STORE_S3_BUCKET": self.object_store_s3_bucket,
                "OBJECT_STORE_S3_ACCESS_KEY_ID": self.object_store_s3_access_key_id,
                "OBJECT_STORE_S3_SECRET_ACCESS_KEY": self.object_store_s3_secret_access_key,
            }
            missing = [name for name, value in required_s3_values.items() if not value]
            if missing:
                raise ValueError(f"S3 object storage is missing: {', '.join(missing)}")
            endpoint = urlsplit(self.object_store_s3_endpoint or "")
            if endpoint.scheme not in {"http", "https"} or not endpoint.hostname:
                raise ValueError("OBJECT_STORE_S3_ENDPOINT must be an HTTP(S) endpoint")
            if self.app_env in {"staging", "production"} and endpoint.scheme != "https":
                raise ValueError("S3 object storage must use HTTPS outside local development")
        if self.object_store_backend == "supabase":
            required_supabase_values = {
                "SUPABASE_URL": self.object_store_supabase_url,
                "SUPABASE_SECRET_KEY": self.object_store_supabase_secret_key,
                "OBJECT_STORE_SUPABASE_BUCKET": self.object_store_supabase_bucket,
            }
            missing = [name for name, value in required_supabase_values.items() if not value]
            if missing:
                raise ValueError(f"Supabase object storage is missing: {', '.join(missing)}")
            endpoint = urlsplit(self.object_store_supabase_url or "")
            if endpoint.scheme not in {"http", "https"} or not endpoint.hostname:
                raise ValueError("SUPABASE_URL must be an HTTP(S) endpoint")
            if self.app_env in {"staging", "production"} and endpoint.scheme != "https":
                raise ValueError("Supabase object storage must use HTTPS outside local development")
        if self.llm_provider == "gemini" and not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")
        if self.embedding_enabled and not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required when EMBEDDING_ENABLED=true")
        if self.corpus_active_retention_years < self.corpus_backfill_years:
            raise ValueError("CORPUS_ACTIVE_RETENTION_YEARS must be at least CORPUS_BACKFILL_YEARS")
        if self.smtp_enabled and not (self.smtp_host and self.smtp_from_email):
            raise ValueError("SMTP_HOST and SMTP_FROM_EMAIL are required when SMTP_ENABLED=true")
        if self.smtp_starttls and self.smtp_use_ssl:
            raise ValueError("SMTP_STARTTLS and SMTP_USE_SSL cannot both be true")
        if self.secret_provider == "aws" and not self.secrets_aws_region:
            raise ValueError("SECRETS_AWS_REGION is required when SECRET_PROVIDER=aws")
        if self.app_env == "production":
            if self.dev_auth_enabled:
                raise ValueError("DEV_AUTH_ENABLED must be false in production")
            if not (self.oidc_issuer and self.oidc_audience):
                raise ValueError("OIDC issuer and audience are required in production")
            if not (self.oidc_jwks_url or self.oidc_public_key):
                raise ValueError("OIDC JWKS URL or public key is required in production")
            if self.auto_create_schema:
                raise ValueError("AUTO_CREATE_SCHEMA must be false in production")
            if "*" in self.allowed_origins:
                raise ValueError("Wildcard CORS origins are forbidden in production")
            if not self.otel_exporter_otlp_endpoint:
                raise ValueError("OTEL_EXPORTER_OTLP_ENDPOINT is required in production")
            if self.secret_provider == "environment":
                raise ValueError("A workload-identity secret provider is required in production")
            if self.temporal_enabled and not (
                self.temporal_tls_enabled
                and self.temporal_tls_ca_path
                and self.temporal_tls_cert_path
                and self.temporal_tls_key_path
            ):
                raise ValueError("Production Temporal requires a complete mTLS configuration")
        return self


def get_settings() -> Settings:
    return Settings()
