FROM python:3.11-slim

# Install system dependencies for reportlab (if needed, though usually standard fonts are enough)
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose the Tornado port
EXPOSE 8888

# Command to run the application
CMD ["python", "server.py"]
