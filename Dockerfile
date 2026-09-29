FROM python:3.12.14-alpine3.24 AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apk add --no-cache \
        build-base \
        cmake \
        ninja

COPY pyproject.toml README.md ./
COPY researchos ./researchos
COPY financial_research_lab ./financial_research_lab
COPY scripts ./scripts
COPY docs ./docs

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip wheel --no-cache-dir ".[saas]" --wheel-dir /wheels


FROM python:3.12.14-alpine3.24

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY researchos ./researchos
COPY financial_research_lab ./financial_research_lab
COPY scripts ./scripts
COPY docs ./docs
COPY --from=builder /wheels /wheels

RUN python -m pip install --upgrade --force-reinstall pip "setuptools>=78.1.1" \
    && python -m pip install --no-cache-dir /wheels/researchos-*.whl \
    && rm -rf /wheels

EXPOSE 8000

USER nobody

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).read()"

CMD ["uvicorn", "researchos.saas.runtime:app", "--host", "0.0.0.0", "--port", "8000"]
