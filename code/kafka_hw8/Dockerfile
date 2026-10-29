# Image for the worker and the FastAPI service (HW8). Build context is the repo root (see docker-compose.yml).
FROM python:3.12-slim
WORKDIR /app
COPY code/kafka_hw8/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY code/kafka_hw8/ .
CMD ["python", "worker.py"]
