FROM ghcr.io/astral-sh/uv:0.12.19 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
ENV UV_LINK_MODE=copy PYTHONUNBUFFERED=1 UV_NO_DEV=1
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY . .
RUN mkdir -p /data
EXPOSE 8000
CMD ["sh", "start.sh"]
