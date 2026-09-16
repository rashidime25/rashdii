FROM alpine:3.20

# Runtime dependencies
RUN apk add --no-cache python3 py3-pip nginx curl unzip jq bash tzdata

# Build dependencies for Pillow / psutil
RUN apk add --no-cache --virtual .build-deps \
    gcc musl-dev python3-dev zlib-dev jpeg-dev freetype-dev linux-headers

WORKDIR /app
COPY requirements.txt .

RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt \
    && apk del .build-deps

# Install Xray-core — PINNED, never `latest`.
# `releases/latest` is what silently broke REALITY: the engine changed its
# `xray x25519` output and the panel stopped generating a keypair, so every
# Reality link shipped with an empty pbk=. A pinned, reviewed version is the
# only way a redeploy cannot change engine behaviour under your feet.
# Bump this ARG deliberately and re-run `pytest` + the panel's connection test.
ARG XRAY_VERSION=26.9.9
RUN set -eux; \
    curl -fsSL -o xray.zip "https://github.com/XTLS/Xray-core/releases/download/v${XRAY_VERSION}/Xray-linux-64.zip"; \
    unzip -o xray.zip -d /tmp/xray; \
    mv /tmp/xray/xray /usr/local/bin/xray; \
    chmod +x /usr/local/bin/xray; \
    # geodata assets are NOT optional: the panel's ad/IR blocking rules use
    # `geosite:category-ads-all` and `geosite:category-iran`, and the engine
    # refuses to load a config when geosite.dat is missing (verified:
    # "failed to open geosite.dat"). Keep them in one explicit, documented place.
    mkdir -p /usr/local/share/xray; \
    mv /tmp/xray/geoip.dat /tmp/xray/geosite.dat /usr/local/share/xray/; \
    rm -rf /tmp/xray xray.zip; \
    xray version | head -1; \
    xray version | grep -q "${XRAY_VERSION}" || { echo "FATAL: installed Xray != v${XRAY_VERSION}"; exit 1; }

ENV XRAY_LOCATION_ASSET=/usr/local/share/xray
ENV TITAN_XRAY_VERSION=${XRAY_VERSION}

# Optional userspace WireGuard server (AmneziaWG). Runs only on VPS/Docker with
# NET_ADMIN + /dev/net/tun; the panel skips it gracefully when absent.
RUN curl -fsSL -o /usr/local/bin/amnezia-wg-go "https://github.com/amnezia-vpn/amnezia-wg-go/releases/latest/download/amnezia-wg-go-linux-amd64" \
    && chmod +x /usr/local/bin/amnezia-wg-go \
    || echo "amnezia-wg-go download skipped (WireGuard will be disabled)"

COPY . /app
COPY nginx.conf /etc/nginx/nginx.conf

RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

CMD ["/app/entrypoint.sh"]
