FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \\
    && apt-get install -y --no-install-recommends \\
        build-essential \\
        cmake \\
        ninja-build \\
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY researchos ./researchos
COPY scripts ./scripts
COPY docs ./docs

RUN python -m pip install --upgrade pip \\
    && python -m pip install ".[saas]" \\
    && python -m pip freeze --all | LC_ALL=C sort > /app/pip-freeze.txt

RUN groupadd --system --gid 10001 researchos \\
    && useradd --system --uid 10001 --gid 10001 --home-dir /app --no-create-home researchos \\
    && chown -R researchos:researchos /app

EXPOSE 8000

USER researchos

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \\
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).read()"

CMD ["uvicorn", "researchos.saas.runtime:app", "--host", "0.0.0.0", "--port", "8000"]
