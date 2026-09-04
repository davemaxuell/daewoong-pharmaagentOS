FROM ghcr.io/astral-sh/uv:0.11.26@sha256:3d868e555f8f1dbc324afa005066cd11e1053fc4743b9808ca8025283e65efa5 AS uv
FROM cgr.dev/chainguard/python:latest-dev@sha256:afdbadf8d697739ab8e10a4d355d0850daa439cba3e6f0e39a73f7f2d3d839b7 AS build

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
ENV APP_ENV=test OBJECT_STORE_PATH=/tmp/objects
ENTRYPOINT []
CMD ["python", "-m", "pytest", "--tb=short"]

FROM cgr.dev/chainguard/python:latest@sha256:eca30c0ac647bf28beaec7442388609d14fd100984fa63397e6015eaffe22aa1 AS runtime
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
