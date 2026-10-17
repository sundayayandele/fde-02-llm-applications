# syntax=docker/dockerfile:1
# Filing-assistant image: API + UI + CLI + MCP server, with a search index baked in.
# Builds with Docker Desktop, Podman Desktop (podman build) and Rancher Desktop.
# Runs as non-root and is compatible with OpenShift's arbitrary UIDs (group 0).
#
#   docker build -t fde-02-llm-applications:local .                       # sample: 6 filings + demo
#   docker build --build-arg CORPUS=demo -t fde-02-llm-applications:local .  # offline, 2 filings
#   docker build --build-arg CORPUS=full ...                              # all 84 FinanceBench filings
#
# Answers use Mistral when MISTRAL_API_KEY is set at run time, otherwise the offline
# extractive mode. The key is never needed to build.

FROM python:3.12-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip wheel --wheel-dir /wheels .

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 PORT=8000 \
    DATA_DIR=/app/data INDEX_DIR=/app/index LLM_PROVIDERS_FILE=/app/config/providers.yaml
WORKDIR /app
RUN useradd --uid 10001 --gid 0 --no-create-home --shell /usr/sbin/nologin app
COPY --from=build /wheels /wheels
RUN pip install /wheels/*.whl && rm -rf /wheels
COPY app ./app
COPY config ./config

FROM runtime AS index
ARG CORPUS=sample
ARG SAMPLE_DOCS="3M_2018_10K 3M_2022_10K AMD_2022_10K AMERICANEXPRESS_2022_10K BOEING_2022_10K PEPSICO_2022_10K"
# Tesseract is only needed to OCR scanned pages while building the index.
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*
# `.starter` exists only in learner starter repos, where ingestion fails until the
# exercises are done; the image still builds and serves 503 until an index exists.
COPY pyproject.toml .starte[r] ./
RUN set -e; \
    build() { \
      case "$CORPUS" in \
        demo)   filing-assistant ingest --demo --embed lsa ;; \
        sample) filing-assistant download --docs $SAMPLE_DOCS && \
                filing-assistant ingest --financebench --demo --embed lsa ;; \
        full)   filing-assistant download && \
                filing-assistant ingest --financebench --demo --embed lsa ;; \
        *)      echo "unknown CORPUS=$CORPUS" >&2; exit 1 ;; \
      esac; }; \
    if [ -f .starter ]; then build || echo "starter: index not built yet"; else build; fi; \
    mkdir -p index data

FROM runtime AS final
COPY --from=index /app/index /app/index
COPY --from=index /app/data /app/data
RUN chgrp -R 0 /app && chmod -R g=u /app
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health/live')"
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
