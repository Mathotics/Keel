# Portable Keel image for environments other than the Raspberry Pi.
# The Pi stays on systemd. See docs/adr/docker-container.md.
#
# The install stays editable and the source tree stays in the image because
# keel.paths resolves migrations, assets, and LICENSE from that tree.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    KEEL_HOST=0.0.0.0 \
    KEEL_PORT=8000 \
    KEEL_RELOAD=false \
    KEEL_LOG_LEVEL=info \
    KEEL_DATABASE_URL=sqlite+pysqlite:////data/keel.db

WORKDIR /app

RUN groupadd --system keel \
    && useradd --system --gid keel --home-dir /home/keel --create-home keel \
    && mkdir -p /data \
    && chown keel:keel /data

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY migrations ./migrations
COPY assets ./assets
COPY deploy/docker-entrypoint.sh /usr/local/bin/keel-docker-entrypoint

RUN pip install --no-cache-dir -e . \
    && sed -i 's/\r$//' /usr/local/bin/keel-docker-entrypoint \
    && chmod 755 /usr/local/bin/keel-docker-entrypoint

USER keel
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; port=os.environ.get('KEEL_PORT', '8000'); urllib.request.urlopen('http://127.0.0.1:' + port + '/health', timeout=3)"]

ENTRYPOINT ["keel-docker-entrypoint"]
