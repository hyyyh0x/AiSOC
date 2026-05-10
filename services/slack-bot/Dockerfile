FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir poetry==1.7.1 && \
    poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock* ./
RUN poetry install --no-interaction --no-ansi --no-dev 2>/dev/null || \
    pip install --no-cache-dir \
        fastapi \
        "uvicorn[standard]" \
        pydantic \
        pydantic-settings \
        slack-bolt \
        slack-sdk \
        "aiohttp>=3.9,<4.0" \
        httpx \
        structlog

COPY app/ ./app/

EXPOSE 8089

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8089"]
