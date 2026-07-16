# GLB → USDZ converter sidecar. Heavy USD tooling (headless Blender) lives here so
# the backend image stays lean. Exchanges files with the backend over the shared
# /media volume (paths in, paths out) — no large HTTP bodies, no docker-in-docker.
FROM python:3.12-slim

WORKDIR /srv

# Pin Blender 4.2 LTS and verify against Blender's published md5.
ENV BLENDER_VERSION=4.2.22 \
    BLENDER_MD5=28a4cc3247eb33b7c16a04d59a1764c1

# Blender headless runtime libraries (it still dlopens GL/X libs under `-b`).
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl xz-utils \
      libgl1 libglu1-mesa libx11-6 libxext6 libxrender1 libxi6 \
      libxxf86vm1 libxfixes3 libxkbcommon0 libsm6 libice6 \
 && rm -rf /var/lib/apt/lists/*

# Download + checksum-verify + install Blender.
RUN curl -fSL -o /tmp/blender.tar.xz \
      "https://download.blender.org/release/Blender4.2/blender-${BLENDER_VERSION}-linux-x64.tar.xz" \
 && echo "${BLENDER_MD5}  /tmp/blender.tar.xz" | md5sum -c - \
 && mkdir -p /opt/blender \
 && tar -xJf /tmp/blender.tar.xz -C /opt/blender --strip-components=1 \
 && rm /tmp/blender.tar.xz \
 && ln -s /opt/blender/blender /usr/local/bin/blender

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py glb_to_usdz.py ./

EXPOSE 9000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000"]
