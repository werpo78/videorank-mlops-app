FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[ml]"

USER app

EXPOSE 8080

CMD ["uvicorn", "videorank.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]

