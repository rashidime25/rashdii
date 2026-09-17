#!/bin/bash
# Container start: nginx takes the platform's public port and forwards the panel
# to $PANEL_PORT. The routing is derived here, once, and printed - because
# "Application failed to respond" on Railway is nearly always a port mismatch,
# and it used to fail silently.
set -e

PORT="${PORT:-8000}"
PANEL_PORT="${PANEL_PORT:-10000}"
NGINX_CONF="${NGINX_CONF:-/etc/nginx/nginx.conf}"   # the image copies it there

# The platform edge decides for itself which container port public traffic goes
# to, and it can disagree with PORT in either direction. A disagreement looks
# like a perfectly healthy container from the inside and `Application failed to
# respond` from the outside - so the panel listens on the platform port *plus*
# the ports an edge is known to default to. TITAN_EXTRA_LISTEN_PORTS="" disables
# the extra listeners once the right target port is pinned in the platform UI.
EXTRA_LISTEN_PORTS="${TITAN_EXTRA_LISTEN_PORTS-443,8080,8000,3000,80}"
# Ports that must never be taken by nginx: Xray's inbounds (bound to 127.0.0.1,
# but 0.0.0.0 would still clash), the stats API, the fallback and the panel.
RESERVED_PORTS="10001,10002,10003,10004,10005,10006,10007,10008,10009,10010,10011,10012,10013,10085,${PANEL_PORT}"
for var in TITAN_FALLBACK_PORT XRAY_VLESS_WS_PORT XRAY_VMESS_WS_PORT XRAY_TROJAN_WS_PORT \
           XRAY_XHTTP_PORT XRAY_GRPC_PORT XRAY_SS_PORT XRAY_API_PORT XRAY_HTTPUPGRADE_PORT \
           XRAY_TCP_VLESS_PORT XRAY_TCP_VLESS_TLS_PORT XRAY_TCP_VLESS_REALITY_PORT \
           XRAY_TCP_VMESS_PORT XRAY_TCP_VMESS_TLS_PORT XRAY_TCP_TROJAN_PORT; do
  eval "val=\${$var:-}"
  if [ -n "$val" ]; then RESERVED_PORTS="${RESERVED_PORTS},${val}"; fi
done

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
  sed -i -E "s@(proxy_pass http://127\.0\.0\.1:)[0-9]+;([[:space:]]*#[[:space:]]*titan-panel-upstream)@\1${PANEL_PORT};\2@g" "$NGINX_CONF" || \
    echo "[entrypoint] could not rewrite panel upstream in $NGINX_CONF"
  # Build the listen set: the platform port first, then the candidates, minus
  # anything Xray or the panel already owns. Duplicates collapse.
  LISTEN_PORTS=""
  for p in $(echo "${PORT},${EXTRA_LISTEN_PORTS}" | tr ',' ' '); do
    case "$p" in ''|*[!0-9]*) continue ;; esac
    case ",${RESERVED_PORTS}," in *",${p},"*) continue ;; esac
    case ",${LISTEN_PORTS}," in *",${p},"*) continue ;; esac
    LISTEN_PORTS="${LISTEN_PORTS:+${LISTEN_PORTS},}${p}"
  done
  # IPv6 lines only where the kernel actually has IPv6: a `listen [::]:443;` on a
  # container with the v6 stack disabled is a fatal nginx error, and losing nginx
  # would be a worse outage than the one we are fixing.
  V6_SUPPORTED=0
  if [ -f /proc/net/if_inet6 ]; then V6_SUPPORTED=1; fi
  LISTEN_BLOCK="$(mktemp)"
  for p in $(echo "$LISTEN_PORTS" | tr ',' ' '); do
    printf '        listen %s;\n' "$p" >> "$LISTEN_BLOCK"
    if [ "$V6_SUPPORTED" = "1" ]; then
      printf '        listen [::]:%s;\n' "$p" >> "$LISTEN_BLOCK"
    fi
  done
  awk -v marker="titan-listen-marker" -v blockfile="$LISTEN_BLOCK" '
    BEGIN { injected = 0; injecting = 0 }
    {
      if (!injected && index($0, marker) > 0) {
        while ((getline line < blockfile) > 0) print line
        close(blockfile)
        injected = 1; injecting = 1; next        # the marked line itself is dropped
      }
      if (injecting) {
        if ($0 ~ /^[ \t]*listen[ \t]/) next
        injecting = 0
      }
      print
    }
  ' "$NGINX_CONF" > "${NGINX_CONF}.titan" && mv "${NGINX_CONF}.titan" "$NGINX_CONF" \
    || echo "[entrypoint] listen rewrite failed - nginx may only answer PORT=${PORT}"
  rm -f "$LISTEN_BLOCK"
  if [ "$V6_SUPPORTED" = "1" ]; then
    echo "[entrypoint] panel listens on: ${LISTEN_PORTS} (v4+v6)"
  else
    echo "[entrypoint] panel listens on: ${LISTEN_PORTS} (v4 only - this kernel has no IPv6)"
  fi
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
  # hiding behind a proxy that is not there. (The app also falls back to PORT by
  # itself; setting it here keeps both halves of the container in agreement.)
  export PANEL_PORT="$PORT"
  echo "[entrypoint] panel itself will serve PORT=${PORT}"
fi
# Prove the port is really being served, from inside the container, and say so in
# the deploy log - instead of leaving the platform edge to report a timeout.
(
  sleep 8
  code=$(curl -s -o /dev/null -w '%{http_code}' -m 4 "http://127.0.0.1:${PANEL_PORT}/healthz" || true)
  echo "[entrypoint] self-check: /healthz on 127.0.0.1:${PANEL_PORT} -> ${code:-no answer}"
  code6=$(curl -s -o /dev/null -w '%{http_code}' -m 4 "http://[::1]:${PANEL_PORT}/healthz" || true)
  echo "[entrypoint] self-check: /healthz on [::1]:${PANEL_PORT} -> ${code6:-no answer}"
  if [ "$nginx_ok" = "1" ]; then
    for p in $(echo "${LISTEN_PORTS}" | tr ',' ' '); do
      [ -n "$p" ] || continue
      c4=$(curl -s -o /dev/null -w '%{http_code}' -m 3 "http://127.0.0.1:${p}/healthz" || true)
      c6=$(curl -s -o /dev/null -w '%{http_code}' -m 3 "http://[::1]:${p}/healthz" || true)
      echo "[entrypoint] listen check: port ${p} -> v4 ${c4:-—} / v6 ${c6:-—}"
    done
  fi
) &

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
