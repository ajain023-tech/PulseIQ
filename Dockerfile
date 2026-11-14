# syntax=docker/dockerfile:1
# ---- builder: install dependencies into a virtualenv -----------------------------
FROM python:3.11-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[ai]"

# ---- runtime ----------------------------------------------------------------------
FROM python:3.11-slim
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PULSEIQ_SIZE=small \
    PULSEIQ_DATA_DIR=/app/data \
    PULSEIQ_ARTIFACTS_DIR=/app/artifacts \
    MPLBACKEND=Agg
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && apt-get clean \
    && useradd --create-home --uid 10001 pulseiq
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=pulseiq:pulseiq warehouse ./warehouse
COPY --chown=pulseiq:pulseiq apps ./apps
COPY --chown=pulseiq:pulseiq .streamlit/config.toml ./.streamlit/config.toml
COPY --chown=pulseiq:pulseiq scripts/bootstrap.sh ./scripts/bootstrap.sh
COPY --chown=pulseiq:pulseiq data/legacy ./data/legacy
RUN mkdir -p /app/data /app/artifacts && chown -R pulseiq:pulseiq /app
USER pulseiq
EXPOSE 8000 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD curl -fsS http://localhost:8000/api/v1/health || curl -fsS http://localhost:8501/_stcore/health || exit 1
ENTRYPOINT ["sh", "scripts/bootstrap.sh"]
CMD ["api"]
