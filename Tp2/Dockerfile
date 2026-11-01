FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# Sin shell intermedio: python es PID 1 y recibe SIGTERM directo de Docker.
CMD ["python", "-m", "src.main"]