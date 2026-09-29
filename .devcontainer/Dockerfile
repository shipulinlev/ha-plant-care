# Python version must satisfy the homeassistant pin (2026.9 requires >= 3.14.2).
FROM mcr.microsoft.com/devcontainers/python:3.14

# System libraries Home Assistant core needs to start (used by scripts/develop).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libturbojpeg0 libpcap-dev \
    && rm -rf /var/lib/apt/lists/*

# The venv lives outside the workspace so it never clashes with the host's Windows .venv.
ENV VIRTUAL_ENV=/home/vscode/.venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"
