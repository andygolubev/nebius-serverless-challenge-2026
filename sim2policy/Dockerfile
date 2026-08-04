# syntax=docker/dockerfile:1.7
FROM ubuntu:24.04 AS sb3-base
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH MUJOCO_GL=egl
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv ca-certificates ffmpeg git libegl1 libgl1 libglvnd0 libosmesa6 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src/ src/
RUN uv sync --frozen --no-dev --extra sb3
COPY configs/ configs/
COPY scripts/ scripts/

FROM sb3-base AS sb3
ARG SOURCE_REVISION=unknown
LABEL org.opencontainers.image.title="Sim2Policy" \
      org.opencontainers.image.revision=$SOURCE_REVISION
ENTRYPOINT ["python", "-m"]

FROM nvidia/cuda:12.9.1-runtime-ubuntu24.04 AS mjx-base
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH MUJOCO_GL=egl JAX_DEFAULT_MATMUL_PRECISION=highest
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv ca-certificates ffmpeg git libegl1 libgl1 libglvnd0 libosmesa6 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src/ src/
RUN uv sync --frozen --no-dev --extra mjx
# MuJoCo Playground lazily clones this pinned asset repository when a locomotion
# environment is first loaded.  Bake the exact revision it requests into the
# immutable image so an H100 job never depends on outbound GitHub access.
RUN git clone --depth 1 https://github.com/deepmind/mujoco_menagerie.git \
    /opt/venv/lib/python3.12/site-packages/mujoco_playground/external_deps/mujoco_menagerie \
    && git -C /opt/venv/lib/python3.12/site-packages/mujoco_playground/external_deps/mujoco_menagerie \
      fetch --depth 1 origin 1b86ece576591213e2b666ebf59508454200ca97 \
    && git -C /opt/venv/lib/python3.12/site-packages/mujoco_playground/external_deps/mujoco_menagerie \
      checkout --detach 1b86ece576591213e2b666ebf59508454200ca97 \
    && rm -rf /opt/venv/lib/python3.12/site-packages/mujoco_playground/external_deps/mujoco_menagerie/.git
COPY configs/ configs/
COPY scripts/ scripts/

FROM mjx-base AS mjx
ARG SOURCE_REVISION=unknown
LABEL org.opencontainers.image.title="Sim2Policy" \
      org.opencontainers.image.revision=$SOURCE_REVISION
ENTRYPOINT ["python", "-m"]
