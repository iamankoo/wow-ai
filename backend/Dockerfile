FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=120 -r requirements.txt

COPY app ./app

EXPOSE 8000

# Shell form (not exec form) so $PORT expands - Render injects its own PORT
# (10000 by default) and health-checks that port, not the EXPOSEd 8000;
# local docker-compose.yml doesn't set PORT, so this still falls back to
# 8000 there.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
