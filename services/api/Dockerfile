FROM ghcr.io/astral-sh/uv:0.11.26@sha256:3d868e555f8f1dbc324afa005066cd11e1053fc4743b9808ca8025283e65efa5 AS uv
FROM cgr.dev/chainguard/python:latest-dev@sha256:df9eb3812f118b33f8fd0bafb7efa0112d6a0810b40b2707337a4c432845f7b4 AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    AUTO_CREATE_SCHEMA=false \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONPATH=/srv/pharma/services/api \
    PATH=/srv/pharma/services/api/.venv/bin:$PATH

USER root
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /srv/pharma/services/api
COPY services/api/pyproject.toml services/api/uv.lock services/api/README.md ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache
COPY services/api/app ./app
COPY contracts /srv/pharma/contracts
COPY fixtures/internal_quality /srv/pharma/fixtures/internal_quality
RUN uv sync --frozen --no-dev --no-editable --no-cache
FROM build AS test
RUN uv sync --frozen --extra dev --no-cache
COPY services/api/tests ./tests
COPY tests/fixtures /srv/pharma/tests/fixtures
COPY evals /srv/pharma/evals
COPY fixtures/synthetic-quality /srv/pharma/fixtures/synthetic-quality
COPY infra/migrations /srv/pharma/infra/migrations
COPY infra/policies /srv/pharma/infra/policies
COPY infra/deployment/kubernetes/base /srv/pharma/infra/deployment/kubernetes/base
COPY scripts/deployment-preflight.py /srv/pharma/scripts/deployment-preflight.py
COPY scripts/prepare-vercel-resources.py /srv/pharma/scripts/prepare-vercel-resources.py
COPY infra/deployment/vercel/supabase-data-api-boundary.sql /srv/pharma/infra/deployment/vercel/supabase-data-api-boundary.sql
ENV APP_ENV=test OBJECT_STORE_PATH=/tmp/objects
ENTRYPOINT []
CMD ["python", "-m", "pytest", "--tb=short"]

FROM cgr.dev/chainguard/python:latest@sha256:780029a86e72bf3a58b1795cb77ab73b8f48dfea8c94ab154345396dc3d3237a AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    AUTO_CREATE_SCHEMA=false \
    PYTHONPATH=/srv/pharma/services/api \
    PATH=/srv/pharma/services/api/.venv/bin:$PATH
WORKDIR /srv/pharma/services/api
COPY --from=build /srv/pharma /srv/pharma
USER 65532:65532
EXPOSE 8000
ENTRYPOINT []
CMD ["python", "-m", "app.serve"]
