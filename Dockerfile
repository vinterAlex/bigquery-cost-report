# BigQuery Cost Report - community edition (CLI) container.
FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ /app/src/
COPY config.yaml /app/config.yaml

RUN mkdir -p /app/secrets /app/output

# CLI entrypoint. Run with the client's secret key mounted at /app/secrets
# and an output folder mounted at /app/output.
ENTRYPOINT ["python", "src/app.py"]
