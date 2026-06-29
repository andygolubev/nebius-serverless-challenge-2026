# syntax=docker/dockerfile:1.7
FROM nvidia/cuda:12.9.1-runtime-ubuntu24.04 AS base
ARG SOURCE_REVISION=unknown
LABEL org.opencontainers.image.title="Sim2Policy" \
      org.opencontainers.image.revision=$SOURCE_REVISION
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH MUJOCO_GL=egl JAX_DEFAULT_MATMUL_PRECISION=highest
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv ca-certificates ffmpeg libegl1 libgl1 libglvnd0 libosmesa6 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src/ src/
RUN uv sync --frozen --no-dev

FROM base AS sb3
RUN uv sync --frozen --no-dev --extra sb3
COPY configs/ configs/
ENTRYPOINT ["python", "-m"]

FROM base AS mjx
RUN uv sync --frozen --no-dev --extra mjx
COPY configs/ configs/
ENTRYPOINT ["python", "-m"]

