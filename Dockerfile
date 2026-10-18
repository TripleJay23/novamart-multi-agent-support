# Build with: docker buildx build --platform linux/arm64 --load -t novamart-support:dev .
FROM ghcr.io/astral-sh/uv:0.11.14 AS uv
FROM python:3.12-slim-bookworm

COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY README.md ./
COPY src/ ./src/
RUN uv sync --locked --no-dev --no-editable \
    && groupadd --gid 10001 novamart \
    && useradd --uid 10001 --gid 10001 --create-home novamart

USER 10001:10001
EXPOSE 8080
CMD ["/app/.venv/bin/python", "-m", "novamart_support.agentcore"]
