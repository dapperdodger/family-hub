FROM python:3.12-slim
WORKDIR /app
# requirements.txt is the short list the app imports; requirements.lock pins
# every package (and what those pull in) to the versions the hub was tested
# with, so a rebuild can't quietly pick up a newer release.
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.txt -c requirements.lock
COPY src/ src/
# The version the running app reads for /api/version + family_hub.__version__
# (family_hub.version resolves VERSION at the repo root, which is /app here).
# WITHOUT it the debug readout falls back to "0.0.0+unknown". (CHANGELOG.md is a
# GitHub doc, not read at runtime, so it isn't baked in.)
COPY VERSION ./
# Bake the EXAMPLE config as the in-image default so `docker build` works from a
# clean clone (the real config.json is gitignored). docker-compose bind-mounts
# the operator's real ./config.json over this at runtime; baking their private
# config instead would both couple the build to a gitignored file and leave real
# calendar IDs / LAN IPs sitting in an image layer.
COPY config.example.json config.json
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh
ENV PYTHONPATH=/app/src CONFIG_PATH=/app/config.json DB_PATH=/data/hub.db TOKEN_PATH=/data/token.json
# Run as a fixed non-root uid:gid, the same default docker-compose.yml's
# `user:` uses (compose's HUB_UID/HUB_GID still override it). Everything the
# app writes lives in /data, which compose bind-mounts from ./data (owned by
# that user); /data is created here too so a bare `docker run` can write it.
RUN mkdir -p /data && chown 1000:1000 /data
USER 1000:1000
EXPOSE 8138
# TLS_CERT_FILE/TLS_KEY_FILE (see docker-entrypoint.sh) can put the app on
# HTTPS instead of HTTP. The cert is issued for the tailnet HOSTNAME, not
# 127.0.0.1, so a real (hostname-checking) TLS context would fail this
# loopback call on a hostname mismatch even with a perfectly valid cert —
# this is only proving the process answers on its own port, not validating
# the cert chain a real client would see, so hostname/CA checks are off on
# purpose. Plain http:// still answers 200 directly when TLS isn't set.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "\
import os, ssl, urllib.request; \
tls = os.environ.get('TLS_CERT_FILE'); \
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT); \
ctx.check_hostname = False; \
ctx.verify_mode = ssl.CERT_NONE; \
urllib.request.urlopen('https://127.0.0.1:8138/health', context=ctx) \
if tls else urllib.request.urlopen('http://127.0.0.1:8138/health')"
ENTRYPOINT ["/app/docker-entrypoint.sh"]
