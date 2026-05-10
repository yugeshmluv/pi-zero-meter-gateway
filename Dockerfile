FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml poetry.lock* ./
COPY acquisition/ ./acquisition/
COPY uploader/ ./uploader/
COPY installer_ui/ ./installer_ui/
COPY common/ ./common/
COPY tests/ ./tests/
COPY .env.example ./.env

# Install dependencies
RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi

# Run tests
CMD ["pytest", "tests/", "-v", "--cov=."]
