FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --uid 10001 appuser && mkdir -p /storage && chown -R appuser /app /storage
USER 10001

EXPOSE 8000

# Production default (no --reload). docker-compose overrides this for local dev.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
