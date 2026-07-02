# EUNICE Enterprise — Container image (Week 8)
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies useful for embeddings and PDF parsing
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persist data outside the container layer by default
VOLUME ["/app/data"]

EXPOSE 8000

CMD ["python", "main.py"]
