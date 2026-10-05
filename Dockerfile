FROM python:3.11-slim

# Metadata
LABEL maintainer="TriageOps"
LABEL description="DevOps Incident Triage Agent"

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
COPY src/ ./src/
COPY runbooks/ ./runbooks/

# Install the package
RUN pip install --no-cache-dir -e ".[dev]"

# Create non-root user
RUN useradd -m -u 1000 triageops
USER triageops

# Environment defaults
ENV TRIAGEOPS_RUNBOOKS_DIR=/app/runbooks
ENV TRIAGEOPS_LOG_LEVEL=INFO

# Expose API port
EXPOSE 8000

# Default: run the API server
CMD ["uvicorn", "triageops.api:app", "--host", "0.0.0.0", "--port", "8000"]
