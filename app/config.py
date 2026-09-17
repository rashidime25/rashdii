"""Runtime configuration derived from environment variables."""
import os
import socket

# Directory that holds the SQLite DB and generated Xray config.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("TITAN_DATA_DIR", os.path.join(BASE_DIR, "data"))

def _usable_data_dir(path: str) -> str:
    """A data dir we can actually write to - or a loud downgrade instead of a crash.

    The very first thing boot does is open the SQLite file, so an unwritable
    `TITAN_DATA_DIR` (a Volume mounted at the wrong path, or read-only) used to
    raise before anything could answer the healthcheck: the platform then shows a
    generic "Application failed to respond" and the real reason is only in the
    logs. Boot anyway, say why, and make the persistence loss visible.
    """
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".titan-write-test")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("ok")
        os.remove(probe)
        return path
    except OSError as exc:
        import logging
        import tempfile
        fallback = tempfile.mkdtemp(prefix="titan-data-")
        logging.getLogger("titan.config").error(
            "data dir %s is unusable (%s); falling back to %s. The panel will boot and "
            "stay reachable, but users and settings will NOT survive a restart: mount "
            "the Volume at /app/data or point TITAN_DATA_DIR at a writable path.",
            path, exc, fallback)
        return fallback


DATA_DIR = _usable_data_dir(DATA_DIR)
DB_PATH = os.environ.get("TITAN_DB_PATH", os.path.join(DATA_DIR, "titan.db"))
XRAY_CONFIG_PATH = os.environ.get(
    "TITAN_XRAY_CONFIG", "/usr/local/bin/config.json"
)

# Public port of the container (Railway/Render inject PORT). Nginx listens here.
PUBLIC_PORT = int(os.environ.get("PORT", "8000"))

# Ports for the internal services (localhost only).
# Where uvicorn binds inside the container. Precedence matters:
#   1. an explicit PANEL_PORT (what entrypoint.sh exports after putting nginx on
#      the platform port),
#   2. otherwise the platform's own PORT - because a start command that runs the
#      app directly (no nginx, a platform override, a stripped Procfile) would
#      otherwise bind 10000 while the edge waits on PORT, and the only symptom is
#      the least debuggable error there is: "Application failed to respond".
#   3. the historical default.
def _panel_port() -> int:
    for key in ("PANEL_PORT", "PORT"):
        raw = (os.environ.get(key) or "").strip()
        if raw.isdigit() and 1 <= int(raw) <= 65535:
            return int(raw)
    return 10000


PANEL_PORT = _panel_port()


def _ipv6_available() -> bool:
    """True when this kernel can bind an IPv6 socket at all."""
    try:
        probe = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    except OSError:
        return False
    try:
        probe.bind(("::", 0))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def _panel_hosts() -> list:
    """Every address family the panel must answer on.

    Serving one family is invisible from inside the container: a healthcheck on
    127.0.0.1 passes, the logs stay clean, and the admin sees only "Application
    failed to respond" from the platform edge, which may be dialling the other
    family. So the panel binds both whenever the kernel offers both.

    They are two sockets, not one v4-mapped socket: asyncio sets IPV6_V6ONLY on
    the socket it binds, so `uvicorn --host ::` is IPv6-*only* - the trap that
    turns "add IPv6 support" into "IPv4 stops working". See app.main.
    """
    explicit = (os.environ.get("PANEL_HOST") or "").strip()
    if explicit:
        return [explicit]
    return ["0.0.0.0", "::"] if _ipv6_available() else ["0.0.0.0"]


#: Panel settings that were once stored but are no longer supported. A row in
#: the DB would keep being echoed by GET /api/settings (and shown in the UI) even
#: though nothing reads it any more, so it is dropped once at boot - a revert
#: that leaves ghosts behind is not a revert.
RETIRED_SETTINGS = (
    "reality_server_names", "sock_tfo", "sock_nodelay", "sock_keepalive",
    "sock_user_timeout", "sock_congestion", "xhttp_mode", "xhttp_padding",
    "xhttp_max_post", "xhttp_xmux", "link_test_target",
)

PANEL_BIND_HOSTS = _panel_hosts()
#: The primary address, for logs/health payloads (the full list is above).
PANEL_HOST = PANEL_BIND_HOSTS[0]
XRAY_VLESS_WS_PORT = int(os.environ.get("XRAY_VLESS_WS_PORT", "10001"))
XRAY_VMESS_WS_PORT = int(os.environ.get("XRAY_VMESS_WS_PORT", "10002"))
XRAY_TROJAN_WS_PORT = int(os.environ.get("XRAY_TROJAN_WS_PORT", "10003"))
XRAY_XHTTP_PORT = int(os.environ.get("XRAY_XHTTP_PORT", "10004"))
XRAY_GRPC_PORT = int(os.environ.get("XRAY_GRPC_PORT", "10005"))
XRAY_SS_PORT = int(os.environ.get("XRAY_SS_PORT", "10006"))
XRAY_SS_2022_PORT = int(os.environ.get("XRAY_SS_2022_PORT", "10014"))
XRAY_API_PORT = int(os.environ.get("XRAY_API_PORT", "10085"))

# ------------------------------------------------------------------ raw TCP
# Raw-TCP inbounds bind on the public interface (they own the socket — no TLS
# termination at the edge). Each protocol × security combo gets its own port.
XRAY_TCP_VLESS_PORT = int(os.environ.get("XRAY_TCP_VLESS_PORT", "10007"))            # none
XRAY_TCP_VLESS_TLS_PORT = int(os.environ.get("XRAY_TCP_VLESS_TLS_PORT", "10008"))    # tls
XRAY_TCP_VLESS_REALITY_PORT = int(os.environ.get("XRAY_TCP_VLESS_REALITY_PORT", "10009"))  # reality
XRAY_TCP_VMESS_PORT = int(os.environ.get("XRAY_TCP_VMESS_PORT", "10010"))            # none
XRAY_TCP_VMESS_TLS_PORT = int(os.environ.get("XRAY_TCP_VMESS_TLS_PORT", "10011"))    # tls
XRAY_TCP_TROJAN_PORT = int(os.environ.get("XRAY_TCP_TROJAN_PORT", "10012"))          # tls

# Xray terminates TLS itself for the TCP-TLS inbounds; point these at a cert.
TLS_CERT_FILE = os.environ.get("TITAN_TLS_CERT", "")
TLS_KEY_FILE = os.environ.get("TITAN_TLS_KEY", "")

IS_RAILWAY = bool(os.environ.get("RAILWAY_SERVICE_ID") or os.environ.get("RAILWAY_PROJECT_ID"))

# Reality (VLESS) — destination to masquerade as + SNI to present.
REALITY_DEST = os.environ.get("TITAN_REALITY_DEST", "1.1.1.1:443")
REALITY_SNI = os.environ.get("TITAN_REALITY_SNI", "www.microsoft.com")

# ------------------------------------------------------------------ Hysteria2
# Hysteria2 runs over QUIC (UDP). The inbound binds on the public interface and
# terminates TLS itself (needs TITAN_TLS_CERT / TITAN_TLS_KEY).
XRAY_HY2_PORT = int(os.environ.get("XRAY_HY2_PORT", "443"))            # UDP
# Salamander obfuscation password ("" = off). Requires a recent Xray-core.
HY2_OBFS = os.environ.get("TITAN_HY2_OBFS", "")
# HTTP/3 masquerade for unauthenticated probes ("" = off): proxy mode only.
HY2_MASQUERADE_URL = os.environ.get("TITAN_HY2_MASQUERADE_URL", "")

# ------------------------------------------------------------------ HTTPUpgrade
# HTTPUpgrade transport (like XHTTP) — served through nginx on the public port.
XRAY_HTTPUPGRADE_PORT = int(os.environ.get("XRAY_HTTPUPGRADE_PORT", "10013"))

# ------------------------------------------------------------------ Fallback
# Single-port fallback: VLESS(TCP+TLS) + WebSocket paths served on one port.
# 0 = disabled. On a VPS/Docker set it to 443; on Railway pick a TCP-proxied
# port (443 is reserved for the HTTPS edge). Needs TITAN_TLS_CERT/_KEY.
FALLBACK_PORT = int(os.environ.get("TITAN_FALLBACK_PORT", "0") or 0)

# ------------------------------------------------------------------ Shadowsocks 2022
# 2022 methods use a pre-shared key (like WireGuard); the PSK is derived
# deterministically from the user uuid so main and nodes always agree.
SS_METHODS = [
    "aes-128-gcm", "aes-256-gcm", "chacha20-ietf-poly1305",
    "2022-blake3-aes-128-gcm", "2022-blake3-aes-256-gcm",
    "2022-blake3-chacha20-poly1305",
]
SS_2022_METHODS = {
    "2022-blake3-aes-128-gcm",
    "2022-blake3-aes-256-gcm",
    "2022-blake3-chacha20-poly1305",
}
DEFAULT_SS_METHOD = os.environ.get("XRAY_SS_METHOD", "2022-blake3-aes-128-gcm")

# ------------------------------------------------------------------ WireGuard
# Optional userspace WireGuard/AmneziaWG server (VPS/Docker only — needs a TUN
# device + NET_ADMIN). The panel generates keypairs and the client config, and
# manages a userspace WG process. Skipped gracefully when the binary is absent.
WG_PORT = int(os.environ.get("TITAN_WG_PORT", "51820"))            # UDP
WG_SUBNET = os.environ.get("TITAN_WG_SUBNET", "10.200.0.0/24")
WG_BIN = os.environ.get("TITAN_WG_BIN", "/usr/local/bin/amnezia-wg-go")
WG_CONFIG_PATH = os.environ.get(
    "TITAN_WG_CONFIG", "/usr/local/bin/wg0.conf"
)


def tls_ready() -> bool:
    """True when a certificate pair is configured and present on disk."""
    return bool(
        TLS_CERT_FILE and TLS_KEY_FILE
        and os.path.exists(TLS_CERT_FILE) and os.path.exists(TLS_KEY_FILE)
    )


def fallback_active() -> bool:
    """True when the single-port fallback inbound should be generated."""
    return bool(FALLBACK_PORT) and tls_ready()

# Xray binary location + feature flag (dev mode runs the panel without Xray).
XRAY_BIN = os.environ.get("XRAY_BIN", "/usr/local/bin/xray")

# Where Xray's own stdout/stderr goes (diagnostics).
XRAY_LOG_PATH = os.environ.get("TITAN_XRAY_LOG", os.path.join(DATA_DIR, "xray.log"))
# Watchdog: how often to check that the engine is still alive (seconds).
XRAY_WATCHDOG_INTERVAL = int(os.environ.get("TITAN_XRAY_WATCHDOG_INTERVAL", "30"))
# A user counts as "online" when traffic was seen within this window (seconds).
ONLINE_WINDOW = int(os.environ.get("TITAN_ONLINE_WINDOW", "60"))
# The Xray version the image is pinned to; shown in the panel for verification.
XRAY_PINNED_VERSION = os.environ.get("TITAN_XRAY_VERSION", "26.9.9")
# Set to 1 to hide user count / WG key from the unauthenticated /health payload.
HEALTH_MINIMAL = os.environ.get("TITAN_HEALTH_MINIMAL", "") == "1"

# Session cookie.
SESSION_COOKIE = "titan_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days
# Progressive backoff starts after this many failed logins (see api_login);
# the delay, not a hard lock, is the primary defence because a single-container
# deploy shares one counter across every visitor.
LOGIN_SOFT_FAILS = 3
LOGIN_BACKOFF_CAP_SECONDS = 15
# Hard lock only after this many consecutive failures.
LOGIN_MAX_ATTEMPTS = 8
LOGIN_HARD_LOCK_ATTEMPTS = 30
LOGIN_LOCK_SECONDS = 10 * 60  # 10 minutes

# ------------------------------------------------------------------ multi-node
# TITAN_ROLE=main  -> the control panel (dashboard + DB). Syncs users to nodes.
# TITAN_ROLE=node  -> a pure proxy node: runs Xray for the users the main panel
#                     assigns to it and reports their usage back.
ROLE = os.environ.get("TITAN_ROLE", "main").strip().lower() or "main"
IS_NODE = ROLE == "node"

# Shared secret that lets the main panel talk to its nodes (and vice versa).
# Must be identical on every service. If empty, node sync is disabled.
NODE_SECRET = os.environ.get("TITAN_NODE_SECRET", "")

# Per-node credential issued by the main panel's "Quick node setup" wizard.
# When set, the node uses it to authenticate itself (register + usage report)
# and to verify the main panel's sync pushes. Replaces the shared secret.
NODE_TOKEN = os.environ.get("TITAN_NODE_TOKEN", "")

# The node's own public URL (used to self-register with the main panel).
# Auto-derived from Railway's injected RAILWAY_PUBLIC_DOMAIN when available.
def _node_public_url() -> str:
    d = os.environ.get("TITAN_NODE_URL", "").strip()
    if d:
        return d
    d = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if not d:
        return ""
    if d.startswith(("http://", "https://")):
        return d
    return "https://" + d


NODE_URL = _node_public_url()

# On a node: the public URL of the main panel, e.g. https://panel.example.com
MAIN_URL = os.environ.get("TITAN_MAIN_URL", "").strip().rstrip("/")

# How often (seconds) the main panel re-pushes users to its nodes.
NODE_SYNC_INTERVAL = int(os.environ.get("TITAN_NODE_SYNC_INTERVAL", "60"))


# Default settings for newly created users / generated links.
DEFAULT_SETTINGS = {
    "public_domain": "",
    "public_port": 443,
    "admin_avatar": "titan",
    "default_transport": "ws",
    "default_fingerprint": "chrome",
    "default_alpn": "http/1.1",
    "sni_override": "",
    "fragment_enabled": False,
    "fragment_length": "10-30",
    "fragment_interval": "10-20",
    "restrict_ips": True,
    "block_ads": True,
    "block_iran_sites": False,
    "backup_enabled": True,
    "backup_interval_hours": 24,
    # reality (VLESS) — public values, filled when the keypair is generated
    "reality_pub": "",
    "reality_sid": "",
    "reality_sni": "",
    "reality_dest": "",
}

# Which Xray outbound tags are counted as "blocked" domains (for the routing
# feature). Must match the tag names emitted in xray.py::generate_xray_config.
BLOCKED_TAGS = {"block-ads", "block-iran", "block-adult", "block-custom"}

# users.flow: "" (or "__inherit__") = use the panel default for that transport,
# "none" = explicitly no flow (plain VLESS), otherwise the flow string itself.
# The sentinel exists because every row created before this feature has ''.
VALID_FLOWS = {"", "__inherit__", "none", "xtls-rprx-vision", "xtls-rprx-vision-udp443"}
VALID_POLICY_LEVELS = {0, 1, 2}

# Xray `policy.levels` presets a user can be pinned to (users.policy_level).
# Level 0 is the shared default (stats only). A per-user level is how the panel
# offers "gaming" (small buffers, aggressive reconnects) and "stream/download"
# (fat buffers, lazy teardown) without a second inbound per plan.
POLICY_PLANS = {
    1: {"handshake": 2, "connIdle": 900, "uplinkOnly": 0, "downlinkOnly": 0,
        "bufferSize": 256},
    2: {"handshake": 6, "connIdle": 1800, "uplinkOnly": 2, "downlinkOnly": 5,
        "bufferSize": 1024},
}

POLICY_PLAN_LABELS = {
    0: "پیش‌فرض (متعادل)",
    1: "گیمینگ (تأخیر کم)",
    2: "استریم/دانلود (توان بالا)",
}

VALID_FINGERPRINTS = {"chrome", "firefox", "safari", "ios", "android", "edge", "360", "qq", "random", "randomized"}
VALID_ALPNS = {"http/1.1", "h2,http/1.1", "h3,h2,http/1.1", ""}
VALID_TRANSPORTS = {"ws", "xhttp", "grpc", "tcp", "httpupgrade"}
VALID_SECURITY = {"none", "tls", "reality"}
VALID_PROTOCOLS = {"vless", "vmess", "trojan", "shadowsocks", "hysteria2", "wireguard"}
