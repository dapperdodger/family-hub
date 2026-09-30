#!/bin/sh
# Serves plain HTTP (today's behavior, unchanged) unless TLS_CERT_FILE AND
# TLS_KEY_FILE are both set, in which case the whole app switches to HTTPS
# on the SAME port using that cert — the only way to make the Google
# reconnect flow's /oauth/google/callback work (Google rejects a plain-HTTP,
# non-localhost redirect_uri outright). See README for how to mint a
# Tailscale cert for this (`tailscale cert`) and where to point these two
# vars (both empty is the default: this whole block is a no-op).
set -e
if [ -n "$TLS_CERT_FILE" ] && [ -n "$TLS_KEY_FILE" ]; then
  exec python -m uvicorn family_hub.app:app --host 0.0.0.0 --port 8138 \
    --ssl-certfile "$TLS_CERT_FILE" --ssl-keyfile "$TLS_KEY_FILE"
fi
exec python -m uvicorn family_hub.app:app --host 0.0.0.0 --port 8138
