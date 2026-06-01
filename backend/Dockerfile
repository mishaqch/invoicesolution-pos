FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps for psycopg + argon2
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps. `pip install -e .` needs an actual project
# tree (not just pyproject.toml), so we COPY the source first.
# We can't isolate the deps install in its own layer here, but with
# the bind-mount in dev the actual code edits happen at runtime
# anyway — layer caching matters most for build-time speed, not
# request-time speed. The trade-off is OK.
COPY . /app/
RUN pip install --upgrade pip && \
    pip install -e ".[dev]"

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
