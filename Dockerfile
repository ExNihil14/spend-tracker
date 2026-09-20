# Spendtrack в контейнере: данные — в томе /data, наружу — только 127.0.0.1.
#   docker build -t spendtrack .
#   docker run --rm -p 127.0.0.1:8766:8766 -v spendtrack-data:/data spendtrack
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    SPENDTRACK_DATA_DIR=/data \
    SPENDTRACK_CONFIG_DIR=/data/config

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

VOLUME ["/data"]
EXPOSE 8766
CMD ["/app/.venv/bin/spendtrack", "serve", "--host", "0.0.0.0", "--port", "8766"]
