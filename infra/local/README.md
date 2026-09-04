# Local data services

This Compose stack provides PostgreSQL 16 + pgvector, password-protected Redis, and a versioned MinIO bucket for development with public/synthetic FDA fixtures only. Every published port binds to loopback by default. It is not a production topology.

From the repository root:

```powershell
Copy-Item infra/local/.env.example infra/local/.env
# Replace the three local-only password placeholders in infra/local/.env.
docker compose --env-file infra/local/.env -f infra/local/compose.yaml config --quiet
docker compose --env-file infra/local/.env -f infra/local/compose.yaml up -d --wait
docker compose --env-file infra/local/.env -f infra/local/compose.yaml ps
```

Enable the optional durable agent workflow services with the `agent-platform`
profile. Temporal persists its event history in the same local PostgreSQL service,
while application activity results remain idempotently journaled in the application
schema:

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml --profile agent-platform up -d --wait
$env:TEMPORAL_ENABLED = "true"
$env:TEMPORAL_ADDRESS = "127.0.0.1:7233"
Push-Location services/api
.\.venv\Scripts\pharma-temporal-worker.exe
Pop-Location
```

The PostgreSQL container starts with an empty application database. The richer
`contracts/schema.sql` is an architectural reference and is deliberately not
mounted into the runtime database because its normalized analytical model is not
the SQLAlchemy service schema. Bootstrap the exact runnable schema once with the
migration identity after installing the API:

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://fda_local:YOUR_URL_ENCODED_PASSWORD@127.0.0.1:5432/fda_intel"
Push-Location services/api
.\.venv\Scripts\python.exe -m app.cli init-db
Pop-Location
```

`init-db` enables pgvector before creating the exact runtime tables. For retained
data, use an approved forward migration; do not rerun a reference schema over the
database. To deliberately rebuild disposable local data, stop the stack and remove
its named volumes explicitly:

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml down
docker compose --env-file infra/local/.env -f infra/local/compose.yaml down --volumes
```

The second command permanently removes only this Compose project's local database, queue, and object data. Confirm the Compose project name is `fda-drug-intel-local` before running it.

Local endpoints are PostgreSQL `127.0.0.1:5432`, Redis `127.0.0.1:6379`, MinIO S3 `http://127.0.0.1:9000`, MinIO console `http://127.0.0.1:9001`, Temporal `127.0.0.1:7233`, and the optional Temporal UI `http://127.0.0.1:8233`. MinIO bucket initialization enables object versioning and disables anonymous access.

The pinned MinIO community container is a local S3-compatible emulator only; the upstream community container line is archived. Production must use a Daewoong-approved, supported, private, versioned object-storage service with managed encryption and tested restore—not this container.
