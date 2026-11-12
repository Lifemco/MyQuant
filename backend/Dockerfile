# syntax=docker/dockerfile:1
FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 QUANT_DATA_DIR=/var/lib/myquant XDG_CACHE_HOME=/tmp/myquant-cache
WORKDIR /app
COPY backend/requirements-lock.txt ./requirements.txt
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r requirements.txt
RUN groupadd -g 10001 quant && useradd -u 10001 -g quant -M quant && \
    mkdir -p /var/lib/myquant && chown quant:quant /var/lib/myquant
COPY --chown=quant:quant backend/app ./app
USER 10001:10001
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--timeout-graceful-shutdown", "25"]
