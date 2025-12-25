FROM python:3.11-slim

WORKDIR /app

# Install uv package manager
RUN pip install --no-cache-dir uv

# Copy dependency files first for better caching
COPY pyproject.toml ./

# Install dependencies using uv (generate lock file if not present)
RUN uv sync

# Copy application code
COPY . .

# Expose port
EXPOSE 5002

# Set environment variables
ENV FLASK_HOST=0.0.0.0
ENV FLASK_PORT=5002

# Run the application
CMD ["uv", "run", "python", "run.py"]
