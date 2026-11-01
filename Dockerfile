# Spendtrack в контейнере: данные — в томе /data, наружу — только 127.0.0.1.
#   docker build -t spendtrack .
#   docker run --rm -p 127.0.0.1:8766:8766 -v spendtrack-data:/data spendtrack
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    SPENDTRACK_DATA_DIR=/data \
    SPENDTRACK_CONFIG_DIR=/data/config \
    SPENDTRACK_ALLOW_INSECURE_LAN=1 \
    PATH="/app/.venv/bin:$PATH"
# Container binds 0.0.0.0 for port publishing; Docker network is isolated and host
# publishes to 127.0.0.1. Do not reuse this env outside the container.

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

VOLUME ["/data"]
EXPOSE 8766
CMD ["/app/.venv/bin/spendtrack", "serve", "--host", "0.0.0.0", "--port", "8766"]
