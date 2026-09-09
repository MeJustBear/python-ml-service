FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PDM_CHECK_UPDATE=false

RUN pip install --no-cache-dir "pdm>=2.26"

WORKDIR /project
COPY pyproject.toml pdm.lock README.md ./
COPY src/ src/
RUN pdm install --prod --no-editable --frozen-lockfile


FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/project/.venv/bin:$PATH" \
    MLWRAP_HOST=0.0.0.0 \
    MLWRAP_PORT=8000 \
    MLWRAP_LOG_FORMAT=json

RUN groupadd --gid 1000 app && useradd --uid 1000 --gid 1000 --create-home app

WORKDIR /project
COPY --from=builder --chown=app:app /project/.venv /project/.venv
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app migrations/ migrations/
COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/entrypoint.sh

USER app
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3).status == 200 else 1)"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["mlwrap", "serve"]
