FROM python:3.10-slim

WORKDIR /app

# Install system dependencies for psycopg2
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn uvicorn

# Copy project files
COPY . .

# Create directory for uploaded images to avoid permission/missing folder issues
RUN mkdir -p /app/uploaded_images

# Expose port (Render uses this to help identify the service)
EXPOSE 8000

# Run with Gunicorn using Uvicorn workers for production performance
# Using shell form to support the $PORT environment variable from Render
CMD gunicorn -w 4 -k uvicorn.workers.UvicornWorker backend.main:app --bind 0.0.0.0:${PORT:-8000}