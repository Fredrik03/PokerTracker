# === Stage 1: build ===
FROM python:3.11-slim AS builder

# Set a working directory
WORKDIR /app

# Cache and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your application code
COPY . .

# === Stage 2: runtime ===
FROM python:3.11-slim

WORKDIR /app

# If you need environment variables, you can define defaults here
ENV PYTHONUNBUFFERED=1 \
    TZ=Europe/Stockholm

# Expose the port Uvicorn will listen on
EXPOSE 8000

# Run uvicorn as the container entrypoint
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
