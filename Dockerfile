FROM python:3.10-slim

# ----- Directories -----
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Create necessary directories
RUN mkdir -p /app/input /app/output

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . /app

# Set environment variables
ENV PYTHONPATH=/app

# Command to run the application
CMD ["python", "pdf_processor.py"]

# Document volumes
VOLUME ["/app/input", "/app/output"]

# Document ports
EXPOSE 8000
