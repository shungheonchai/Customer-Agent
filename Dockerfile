FROM ghcr.io/astral-sh/uv:0.12.3 AS uv
FROM python:3.12-slim

COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY bookly ./bookly
RUN useradd --uid 10001 --create-home bookly
USER bookly
EXPOSE 8010
CMD ["uvicorn", "bookly.app:app", "--host", "0.0.0.0", "--port", "8010"]
