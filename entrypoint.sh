#!/bin/bash
# Container start: nginx takes the platform's public port and forwards the panel
# to $PANEL_PORT. The routing is derived here, once, and printed - because
# "Application failed to respond" on Railway is nearly always a port mismatch,
# and it used to fail silently.
set -e

PORT="${PORT:-8000}"
PANEL_PORT="${PANEL_PORT:-10000}"
NGINX_CONF="${NGINX_CONF:-/etc/nginx/nginx.conf}"   # the image copies it there

if [ "$PANEL_PORT" = "$PORT" ]; then
  # nginx is about to own $PORT, so the panel cannot also bind it: shift the
  # panel and keep nginx pointed at the new number, instead of crash-looping on
  # "address already in use".
  PANEL_PORT=$((PORT + 1))
  echo "[entrypoint] PORT=$PORT was also PANEL_PORT -> panel moved to $PANEL_PORT"
fi
export PANEL_PORT

# Public listen port, and the panel upstream. The upstream is matched by its
# marker comment so the WS/xhttp/grpc proxies keep their own ports.
if [ -r "$NGINX_CONF" ] && [ -w "$NGINX_CONF" ]; then
  sed -i -E "s/listen [0-9]+;|listen NGINX_PORT;/listen ${PORT};/g" "$NGINX_CONF" || \
    echo "[entrypoint] could not rewrite listen port in $NGINX_CONF"
  sed -i -E "s@(proxy_pass http://127\.0\.0\.1:)[0-9]+;([[:space:]]*#[[:space:]]*titan-panel-upstream)@\1${PANEL_PORT};\2@g" "$NGINX_CONF" || \
    echo "[entrypoint] could not rewrite panel upstream in $NGINX_CONF"
else
  echo "[entrypoint] $NGINX_CONF missing or read-only - skipping rewrite"
fi

# Every step here is allowed to fail without killing the container: a panel that
# answers on its own port is worth far more than a perfectly configured nginx that
# never starts. "Application failed to respond" on a platform edge is almost always
# this exact class of failure, and it used to be a silent, fatal one.
nginx_ok=0
if command -v nginx >/dev/null 2>&1; then
  if [ -r "$NGINX_CONF" ] && nginx -t >/tmp/nginx-t.log 2>&1; then
    nginx -s stop 2>/dev/null || true
    if nginx; then
      nginx_ok=1
      echo "[entrypoint] nginx: ${PORT} -> panel 127.0.0.1:${PANEL_PORT}"
    else
      echo "[entrypoint] nginx failed to start - serving without it"
    fi
  else
    echo "[entrypoint] nginx config not usable - serving without it"
    [ -r "$NGINX_CONF" ] || echo "[entrypoint]   missing $NGINX_CONF"
    sed -n '1,5p' /tmp/nginx-t.log 2>/dev/null | sed 's/^/[entrypoint]   /'
  fi
else
  echo "[entrypoint] no nginx found"
fi

if [ "$nginx_ok" != "1" ]; then
  # Nothing else is listening on $PORT, so the panel takes it directly instead of
  # hiding behind a proxy that is not there.
  export PANEL_PORT="$PORT"
  echo "[entrypoint] panel itself will serve PORT=${PORT}"
fi

echo "[entrypoint] routing: PORT=${PORT} PANEL_PORT=${PANEL_PORT}"
echo "[entrypoint] storage: TITAN_DATA_DIR=${TITAN_DATA_DIR:-/app/data} (a Volume must be mounted here)"
# Railway healthcheck probe - log whether /healthz is reachable via nginx and directly
(
  sleep 6
  echo "[entrypoint] health probe: nginx http://127.0.0.1:${PORT}/healthz"
  curl -s -m 3 -i http://127.0.0.1:${PORT}/healthz | head -n 5 || echo "[entrypoint] nginx healthz FAILED"
  echo "[entrypoint] health probe: panel http://127.0.0.1:${PANEL_PORT}/healthz"
  curl -s -m 3 -i http://127.0.0.1:${PANEL_PORT}/healthz | head -n 5 || echo "[entrypoint] panel healthz FAILED"
  echo "[entrypoint] env: PORT=${PORT} PANEL_PORT=${PANEL_PORT} RAILWAY_PUBLIC_DOMAIN=${RAILWAY_PUBLIC_DOMAIN:-}"
  ls -ld "${TITAN_DATA_DIR:-/app/data}" 2>&1 | head -n 2 || true
) &

exec python3 -m app.main
