FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3D-model compression toolchain. gltf-transform needs Node >=20; Debian 13 (the
# python:3.12-slim base) ships Node 20 via apt, so no external NodeSource needed.
RUN apt-get update \
 && apt-get install -y --no-install-recommends nodejs npm \
 && npm install -g @gltf-transform/cli@4.4.1 \
 && npm cache clean --force \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY . .

# --proxy-headers + --forwarded-allow-ips: resolve the real client IP from
# X-Forwarded-For, but ONLY when the direct peer is on the Docker network
# (Caddy). Keep the CIDR in sync with TRUSTED_PROXY_IPS (app/core/config.py).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "172.16.0.0/12"]
