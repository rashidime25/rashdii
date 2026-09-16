"""Generate the Xray-core config.json from the user database and manage the
Xray process. Reads live traffic stats from the Xray API."""
import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import time

from . import config, db, sskeys
from . import nodes as nodesync

log = logging.getLogger("titan.xray")

_previous_stats: dict[str, dict] = {}
_xray_process: subprocess.Popen | None = None
_stats_lock = asyncio.Lock()
_version_cache: str = ""
_last_exit: dict = {}


class ConfigError(RuntimeError):
    """The freshly generated config did not pass `xray run -test`.

    Nothing was written or restarted: the previously working config keeps
    serving traffic. Callers may surface ``str(exc)`` to the admin.
    """


def xray_version() -> str:
    """`Xray 26.9.9 …` — cached, shown in the UI so a pinned version is visible."""
    global _version_cache
    if _version_cache or not xray_available():
        return _version_cache
    try:
        out = subprocess.run([config.XRAY_BIN, "version"], capture_output=True,
                             text=True, timeout=15).stdout or ""
        _version_cache = out.splitlines()[0].strip() if out.strip() else ""
    except Exception as e:  # noqa: BLE001
        log.warning("xray version failed: %s", e)
    return _version_cache


def verify_config(path: str | None = None) -> tuple[bool, str]:
    """Validate a config file with the engine itself (`xray run -test`).

    Used before applying anything: a typo in an admin setting or a key the
    engine no longer accepts must never replace a config that is currently
    serving users.
    """
    path = path or config.XRAY_CONFIG_PATH
    if not xray_available() or not os.path.exists(path):
        return True, "skipped (no binary or no config)"
    try:
        proc = subprocess.run([config.XRAY_BIN, "run", "-test", "-c", path],
                              capture_output=True, text=True, timeout=30)
    except Exception as e:  # noqa: BLE001
        return False, f"xray -test failed to run: {e}"
    if proc.returncode == 0:
        return True, ""
    detail = (proc.stdout + proc.stderr).strip()
    # keep the useful part: the engine prints the failing line last
    lines = [ln for ln in detail.splitlines() if ln.strip()]
    return False, (lines[-1] if lines else "unknown config error")[:400]


def last_exit() -> dict:
    """How/when the engine last died — used by the watchdog + diagnostics."""
    return dict(_last_exit)


def xray_available() -> bool:
    return os.path.exists(config.XRAY_BIN)


def xray_running() -> bool:
    """True when the Xray process we spawned is still alive."""
    return bool(_xray_process and _xray_process.poll() is None)


# ----------------------------------------------------------------- routing rules
def _blocked_rules(settings: dict) -> list:
    """Build Xray routing rules for the domain-blocking feature."""
    rules = []
    if settings.get("block_ads"):
        rules.append({
            "type": "field",
            "domain": ["geosite:category-ads-all"],
            "outboundTag": "block-ads",
        })
    if settings.get("block_iran_sites"):
        rules.append({
            "type": "field",
            "domain": ["geosite:category-iran"],
            "outboundTag": "block-iran",
        })
    if settings.get("restrict_ips"):
        # Block connecting to private/LAN ranges (anti-abuse).
        rules.append({
            "type": "field",
            "ip": ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8"],
            "outboundTag": "block",
        })
    return rules


def _xray_users() -> list[dict]:
    """Users whose traffic this process must proxy (role-aware, see nodes.py)."""
    return nodesync.local_users()


def generate_xray_config() -> dict:
    """Build the full Xray config dict. Persisted to disk by write_xray_config."""
    users = _xray_users()
    settings = db.get_settings()

    def mk_client(u, flow: str = ""):
        c = {"id": u["uuid"], "email": u["uid"]}
        if flow:
            c["flow"] = flow
        if u.get("password"):
            c["password"] = u["password"]
        return c

    vless_clients = [mk_client(u) for u in users if u["enabled"] and u["protocol"] == "vless"]
    vmess_clients = [mk_client(u) for u in users if u["enabled"] and u["protocol"] == "vmess"]
    trojan_clients = [
        {"password": u["uuid"], "email": u["uid"]}
        for u in users if u["enabled"] and u["protocol"] == "trojan"
    ]
    # Shadowsocks users share the ss inbound via method+password pairs.
    ss_users = [u for u in users if u["enabled"] and u["protocol"] == "shadowsocks"]

    # TLS certificate presence gates every TLS-terminating inbound (raw-TCP TLS,
    # Hysteria2, single-port fallback). Computed up front so the WS inbounds can
    # opt into PROXY-protocol when the fallback outer forwards to them.
    tls_ok = config.tls_ready()
    fallback_mode = bool(config.FALLBACK_PORT) and tls_ok

    outbounds = [
        {"protocol": "freedom", "tag": "direct"},
        {"protocol": "blackhole", "tag": "block"},
        {"protocol": "blackhole", "tag": "block-ads"},
        {"protocol": "blackhole", "tag": "block-iran"},
        {"protocol": "blackhole", "tag": "block-adult"},
        {"protocol": "blackhole", "tag": "block-custom"},
    ]

    routing_rules = [
        {"type": "field", "inboundTag": ["api"], "outboundTag": "api"},
    ]
    routing_rules.extend(_blocked_rules(settings))

    inbounds = [
        {
            "listen": "127.0.0.1",
            "port": config.XRAY_API_PORT,
            "protocol": "dokodemo-door",
            "settings": {"address": "127.0.0.1"},
            "tag": "api",
        },
    ]

    if vless_clients:
        inbounds.append({
            "listen": "127.0.0.1",
            "port": config.XRAY_VLESS_WS_PORT,
            "protocol": "vless",
            "settings": {"clients": vless_clients, "decryption": "none"},
            "streamSettings": {"network": "ws", "wsSettings": {"path": "/vl-ws", "acceptProxyProtocol": fallback_mode}},
            "tag": "in-vless-ws",
        })
    if vmess_clients:
        inbounds.append({
            "listen": "127.0.0.1",
            "port": config.XRAY_VMESS_WS_PORT,
            "protocol": "vmess",
            "settings": {"clients": vmess_clients},
            "streamSettings": {"network": "ws", "wsSettings": {"path": "/vm-ws", "acceptProxyProtocol": fallback_mode}},
            "tag": "in-vmess-ws",
        })
    if trojan_clients:
        inbounds.append({
            "listen": "127.0.0.1",
            "port": config.XRAY_TROJAN_WS_PORT,
            "protocol": "trojan",
            "settings": {"clients": trojan_clients},
            "streamSettings": {"network": "ws", "wsSettings": {"path": "/tr-ws", "acceptProxyProtocol": fallback_mode}},
            "tag": "in-trojan-ws",
        })

    # XHTTP inbound shared by VLESS + VMess users.
    xhttp_vless = [c for c in vless_clients]
    xhttp_vmess = [c for c in vmess_clients]
    if xhttp_vless:
        inbounds.append({
            "listen": "127.0.0.1",
            "port": config.XRAY_XHTTP_PORT,
            "protocol": "vless",
            "settings": {"clients": xhttp_vless, "decryption": "none"},
            "streamSettings": {"network": "xhttp", "xhttpSettings": {"path": "/xhttp"}},
            "tag": "in-vless-xhttp",
        })
    if xhttp_vmess:
        inbounds.append({
            "listen": "127.0.0.1",
            "port": config.XRAY_XHTTP_PORT,
            "protocol": "vmess",
            "settings": {"clients": xhttp_vmess},
            "streamSettings": {"network": "xhttp", "xhttpSettings": {"path": "/xhttp"}},
            "tag": "in-vmess-xhttp",
        })

    # HTTPUpgrade inbound shared by VLESS + VMess users (like XHTTP, lighter).
    hup_vless = [c for c in vless_clients]
    hup_vmess = [c for c in vmess_clients]
    if hup_vless:
        inbounds.append({
            "listen": "127.0.0.1",
            "port": config.XRAY_HTTPUPGRADE_PORT,
            "protocol": "vless",
            "settings": {"clients": hup_vless, "decryption": "none"},
            "streamSettings": {"network": "httpupgrade", "httpupgradeSettings": {"path": "/hup"}},
            "tag": "in-vless-httpupgrade",
        })
    if hup_vmess:
        inbounds.append({
            "listen": "127.0.0.1",
            "port": config.XRAY_HTTPUPGRADE_PORT,
            "protocol": "vmess",
            "settings": {"clients": hup_vmess},
            "streamSettings": {"network": "httpupgrade", "httpupgradeSettings": {"path": "/hup"}},
            "tag": "in-vmess-httpupgrade",
        })

    # gRPC inbound shared by VLESS + VMess users.
    grpc_vless = [c for c in vless_clients]
    grpc_vmess = [c for c in vmess_clients]
    if grpc_vless:
        inbounds.append({
            "listen": "127.0.0.1",
            "port": config.XRAY_GRPC_PORT,
            "protocol": "vless",
            "settings": {"clients": grpc_vless, "decryption": "none"},
            "streamSettings": {"network": "grpc", "grpcSettings": {"serviceName": "titan"}},
            "tag": "in-vless-grpc",
        })
    if grpc_vmess:
        inbounds.append({
            "listen": "127.0.0.1",
            "port": config.XRAY_GRPC_PORT,
            "protocol": "vmess",
            "settings": {"clients": grpc_vmess},
            "streamSettings": {"network": "grpc", "grpcSettings": {"serviceName": "titan"}},
            "tag": "in-vmess-grpc",
        })

    # Shadowsocks inbounds. Legacy AEAD methods share one inbound (per-client
    # method/password); the 2022 methods use a separate inbound with a shared
    # server PSK and per-user PSKs (SIP008).
    if ss_users:
        ss_methods = {
            u.get("ss_method") or settings.get("ss_method") or config.DEFAULT_SS_METHOD
            for u in ss_users
        }
        legacy = [u for u in ss_users
                  if (u.get("ss_method") or settings.get("ss_method") or config.DEFAULT_SS_METHOD)
                  not in config.SS_2022_METHODS]
        ss2022 = [u for u in ss_users
                  if (u.get("ss_method") or settings.get("ss_method") or config.DEFAULT_SS_METHOD)
                  in config.SS_2022_METHODS]
        if legacy:
            ss_clients = []
            for u in legacy:
                method = (u.get("ss_method") or settings.get("ss_method")
                          or config.DEFAULT_SS_METHOD)
                ss_clients.append({
                    "email": u["uid"],
                    "method": method,
                    "password": sskeys.psk_inbound(u["uuid"], method),
                })
            inbounds.append({
                "listen": "127.0.0.1",
                "port": config.XRAY_SS_PORT,
                "protocol": "shadowsocks",
                "settings": {"clients": ss_clients, "network": "tcp,udp"},
                "tag": "in-ss",
            })
        if ss2022:
            ss2022_methods = ss_methods & config.SS_2022_METHODS
            method = next(iter(ss2022_methods)) if ss2022_methods else config.DEFAULT_SS_METHOD
            method = method if method in config.SS_2022_METHODS else config.DEFAULT_SS_METHOD
            inbounds.append({
                "listen": "127.0.0.1",
                "port": config.XRAY_SS_2022_PORT,
                "protocol": "shadowsocks",
                "settings": {
                    "method": method,
                    "password": sskeys.server_psk(method),
                    "clients": [{
                        "email": u["uid"],
                        "password": sskeys.psk_inbound(u["uuid"], method),
                    } for u in ss2022],
                    "network": "tcp,udp",
                },
                "tag": "in-ss-2022",
            })

    # ---------------- raw TCP inbounds (plain / TLS / Reality) ----------------
    tcp_users = [u for u in users if u.get("transport") == "tcp"]
    vless_tcp_plain = [mk_client(u) for u in tcp_users
                       if u["protocol"] == "vless" and (u.get("security") or "none") == "none"]
    vless_tcp_tls = [mk_client(u) for u in tcp_users
                     if u["protocol"] == "vless" and (u.get("security") or "") == "tls"]
    # The links built for this inbound advertise `flow=xtls-rprx-vision`. If the
    # server-side user carries no flow, a real client that follows its own link
    # opens a Vision tunnel the server refuses to carry: the connection is
    # established in the client UI but no traffic ever passes (verified against a
    # real Xray client). Keep both sides in sync.
    vless_tcp_reality = [mk_client(u, flow="xtls-rprx-vision") for u in tcp_users
                         if u["protocol"] == "vless" and (u.get("security") or "") == "reality"]
    vmess_tcp_plain = [mk_client(u) for u in tcp_users
                       if u["protocol"] == "vmess" and (u.get("security") or "none") == "none"]
    vmess_tcp_tls = [mk_client(u) for u in tcp_users
                     if u["protocol"] == "vmess" and (u.get("security") or "") == "tls"]
    trojan_tcp = [{"password": u["uuid"], "email": u["uid"]} for u in tcp_users
                  if u["protocol"] == "trojan"]

    if vless_tcp_plain:
        inbounds.append({
            "listen": "0.0.0.0", "port": config.XRAY_TCP_VLESS_PORT, "protocol": "vless",
            "settings": {"clients": vless_tcp_plain, "decryption": "none"},
            "streamSettings": {"network": "tcp", "security": "none"},
            "tag": "in-vless-tcp",
        })
    if vmess_tcp_plain:
        inbounds.append({
            "listen": "0.0.0.0", "port": config.XRAY_TCP_VMESS_PORT, "protocol": "vmess",
            "settings": {"clients": vmess_tcp_plain},
            "streamSettings": {"network": "tcp", "security": "none"},
            "tag": "in-vmess-tcp",
        })

    # TLS over raw TCP — needs a certificate Xray can present.
    if (vless_tcp_tls or vmess_tcp_tls or trojan_tcp) and not tls_ok:
        log.warning("TCP-TLS users exist but no certificate is configured "
                    "(TITAN_TLS_CERT / TITAN_TLS_KEY) — TLS inbounds skipped")
    if tls_ok:
        tls_settings = {
            "certificates": [{
                "certificateFile": config.TLS_CERT_FILE,
                "keyFile": config.TLS_KEY_FILE,
            }],
            "alpn": ["h2", "http/1.1"],
        }
        if vless_tcp_tls and not fallback_mode:
            inbounds.append({
                "listen": "0.0.0.0", "port": config.XRAY_TCP_VLESS_TLS_PORT, "protocol": "vless",
                "settings": {"clients": vless_tcp_tls, "decryption": "none"},
                "streamSettings": {"network": "tcp", "security": "tls", "tlsSettings": tls_settings},
                "tag": "in-vless-tcp-tls",
            })
        if vmess_tcp_tls:
            inbounds.append({
                "listen": "0.0.0.0", "port": config.XRAY_TCP_VMESS_TLS_PORT, "protocol": "vmess",
                "settings": {"clients": vmess_tcp_tls},
                "streamSettings": {"network": "tcp", "security": "tls", "tlsSettings": tls_settings},
                "tag": "in-vmess-tcp-tls",
            })
        if trojan_tcp:
            inbounds.append({
                "listen": "0.0.0.0", "port": config.XRAY_TCP_TROJAN_PORT, "protocol": "trojan",
                "settings": {"clients": trojan_tcp},
                "streamSettings": {"network": "tcp", "security": "tls", "tlsSettings": tls_settings},
                "tag": "in-trojan-tcp",
            })

    # ---------------- single-port fallback (VLESS-TLS + WS paths on one port) --
    # One VLESS(TCP+TLS) inbound terminates TLS and offloads the WS paths to the
    # local plain WS inbounds (PROXY protocol), so VLESS-TLS, VLESS-WS, VMess-WS
    # and Trojan-WS can all be reached through a single port.
    if fallback_mode:
        if not vless_tcp_tls:
            log.warning("TITAN_FALLBACK_PORT set but no VLESS(TCP+TLS) users — "
                        "fallback inbound skipped")
        else:
            fb_fallbacks = [
                {"path": "/vl-ws", "dest": config.XRAY_VLESS_WS_PORT, "xver": 1},
                {"path": "/vm-ws", "dest": config.XRAY_VMESS_WS_PORT, "xver": 1},
                {"path": "/tr-ws", "dest": config.XRAY_TROJAN_WS_PORT, "xver": 1},
            ]
            inbounds.append({
                "listen": "0.0.0.0", "port": config.FALLBACK_PORT, "protocol": "vless",
                "settings": {
                    "clients": vless_tcp_tls,
                    "decryption": "none",
                    "fallbacks": fb_fallbacks,
                },
                "streamSettings": {
                    "network": "tcp", "security": "tls",
                    "tlsSettings": {
                        "certificates": [{
                            "certificateFile": config.TLS_CERT_FILE,
                            "keyFile": config.TLS_KEY_FILE,
                        }],
                        "alpn": ["http/1.1"],
                    },
                },
                "tag": "in-vless-fallback",
            })

    if vless_tcp_reality:
        priv = db.get_meta("reality_priv")
        sid = db.get_meta("reality_sid") or ""
        # serverNames must cover the SNI the links advertise. reality.ensure_keys
        # seeds the setting from config, but an admin who edits it (or a Railway
        # redeploy that changes TITAN_REALITY_SNI) would otherwise produce links
        # Reality rejects outright.
        snis = sorted({s for s in (config.REALITY_SNI,
                                   db.get_settings().get("reality_sni") or "") if s})
        if priv:
            inbounds.append({
                "listen": "0.0.0.0", "port": config.XRAY_TCP_VLESS_REALITY_PORT, "protocol": "vless",
                "settings": {"clients": vless_tcp_reality, "decryption": "none"},
                "streamSettings": {"network": "tcp", "security": "reality", "realitySettings": {
                    "show": False,
                    "dest": config.REALITY_DEST,
                    "xver": 0,
                    "serverNames": snis or [config.REALITY_SNI],
                    "privateKey": priv,
                    "shortIds": [sid],
                }},
                "tag": "in-vless-reality",
            })
        else:
            log.warning("Reality users exist but no private key is available — "
                        "Reality inbound skipped")

    # ---------------- Hysteria2 (QUIC / UDP) ----------------
    hy2_users = [u for u in users if u["enabled"] and u["protocol"] == "hysteria2"]
    if hy2_users:
        if not tls_ok:
            log.warning("Hysteria2 users exist but no certificate is configured "
                        "(TITAN_TLS_CERT / TITAN_TLS_KEY) — Hysteria2 inbound skipped")
        else:
            hy2_stream = {
                "network": "hysteria",
                "security": "tls",
                "tlsSettings": {
                    "certificates": [{
                        "certificateFile": config.TLS_CERT_FILE,
                        "keyFile": config.TLS_KEY_FILE,
                    }],
                    "alpn": ["h3"],
                },
                "hysteriaSettings": {"version": 2},
            }
            if config.HY2_OBFS:
                # Salamander UDP masking (needs a recent Xray-core build).
                hy2_stream["udpmasks"] = [{
                    "type": "salamander",
                    "settings": {"password": config.HY2_OBFS},
                }]
            if config.HY2_MASQUERADE_URL:
                hy2_stream["hysteriaSettings"]["masquerade"] = {
                    "type": "proxy",
                    "url": config.HY2_MASQUERADE_URL,
                    "rewriteHost": True,
                }
            inbounds.append({
                "listen": "0.0.0.0",
                "port": config.XRAY_HY2_PORT,
                "protocol": "hysteria",
                "settings": {"version": 2, "users": [
                    {"auth": u["uuid"], "level": 0, "email": u["uid"]} for u in hy2_users
                ]},
                "streamSettings": hy2_stream,
                "tag": "in-hysteria2",
            })

    return {
        "log": {"loglevel": "warning"},
        "dns": {
            "servers": [
                "https+local://1.1.1.1/dns-query",
                "https+local://8.8.8.8/dns-query",
                "1.1.1.1",
                "8.8.8.8",
                "localhost",
            ],
            "queryStrategy": "UseIPv4",
        },
        "api": {"tag": "api", "services": ["StatsService"]},
        "stats": {},
        "policy": {
            # statsUserOnline feeds `xray api statsonline(iplist)` — the only way
            # to know who is really connected (state.ACTIVE never was populated).
            "levels": {"0": {"statsUserUplink": True, "statsUserDownlink": True,
                             "statsUserOnline": True}},
            "system": {"statsInboundUplink": True, "statsInboundDownlink": True},
        },
        "inbounds": inbounds,
        "outbounds": outbounds,
        "routing": {"rules": routing_rules},
    }


def write_xray_config(validate: bool = True) -> dict:
    """Generate the config and put it in place — but only if it is valid.

    The previous config is kept as ``config.json.bak``, and an invalid candidate
    is rejected *before* it can replace a working configuration (``ConfigError``),
    so a bad setting or a key the engine rejects cannot take the proxy down.
    """
    cfg = generate_xray_config()
    os.makedirs(os.path.dirname(config.XRAY_CONFIG_PATH), exist_ok=True)
    # The candidate must keep a `.json` suffix: `xray run -test` infers the config
    # format from the file extension and refuses anything else
    # ("Failed to get format of config.json.tmp" — hit while testing this fix).
    tmp = config.XRAY_CONFIG_PATH[:-5] + ".candidate.json" \
        if config.XRAY_CONFIG_PATH.endswith(".json") else config.XRAY_CONFIG_PATH + ".candidate.json"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

    if validate:
        ok, detail = verify_config(tmp)
        if not ok:
            try:
                os.remove(tmp)
            except OSError:
                pass
            db.add_event("error", "config-invalid",
                         f"config rejected by `xray run -test`: {detail}"[:300])
            log.error("generated Xray config is invalid, keeping the running one: %s", detail)
            raise ConfigError(detail)

    if os.path.exists(config.XRAY_CONFIG_PATH):
        try:
            shutil.copyfile(config.XRAY_CONFIG_PATH, config.XRAY_CONFIG_PATH + ".bak")
        except OSError:
            pass
    os.replace(tmp, config.XRAY_CONFIG_PATH)
    return cfg


def restart_xray():
    global _xray_process
    if _xray_process and _xray_process.poll() is None:
        _xray_process.terminate()
        try:
            _xray_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _xray_process.kill()
    if xray_available():
        os.makedirs(os.path.dirname(config.XRAY_LOG_PATH), exist_ok=True)
        logf = open(config.XRAY_LOG_PATH, "a", encoding="utf-8")
        _xray_process = subprocess.Popen(
            [config.XRAY_BIN, "run", "-c", config.XRAY_CONFIG_PATH],
            stdout=logf,
            stderr=subprocess.STDOUT,
        )
        log.info("Xray restarted (pid=%s)", _xray_process.pid)
    else:
        log.warning("Xray binary not found — running in dev/mock mode.")


def ensure_running() -> tuple[bool, str]:
    """Start the engine if it is not alive. Returns (ok, reason).

    The watchdog calls this; a panel that stays up while Xray is dead is the
    worst failure mode there is (nobody can connect and nobody is told).
    """
    global _last_exit
    if not xray_available():
        return False, "no-binary"
    if xray_running():
        return True, "alive"

    code = None
    if _xray_process is not None:
        code = _xray_process.poll()
        _last_exit = {"code": code, "at": time.time()}
        log.warning("Xray is not running (exit code %s) — restarting it", code)

    if not os.path.exists(config.XRAY_CONFIG_PATH):
        write_xray_config()
    restart_xray()
    if xray_running():
        db.add_event("warn", "xray-restart",
                     f"engine was down (exit={code}) and has been restarted")
        return True, "restarted"
    return False, "restart-failed"


async def get_xray_stats() -> dict:
    """Query the Xray stats API and return per-uid traffic deltas since the
    previous call. Uses the JSON output format."""
    global _previous_stats
    if not xray_available():
        return {}
    async with _stats_lock:
        try:
            proc = await asyncio.create_subprocess_exec(
                config.XRAY_BIN, "api", "statsquery",
                f"--server=127.0.0.1:{config.XRAY_API_PORT}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _stderr = await proc.communicate()
            out = stdout.decode("utf-8", errors="ignore")
            if not out.strip():
                return {}
            try:
                data = json.loads(out)
            except json.JSONDecodeError:
                matches = re.findall(r'name:\s*"([^"]+)"\s*value:\s*(\d+)', out)
                if not matches:
                    return {}
                data = {"stat": [{"name": m[0], "value": int(m[1])} for m in matches]}

            current: dict[str, dict] = {}
            for item in data.get("stat", []):
                name = item.get("name")
                value = item.get("value")
                if not name or value is None:
                    continue
                parts = name.split(">>>")
                if len(parts) == 4 and parts[0] == "user" and parts[2] == "traffic":
                    uid, direction, val = parts[1], parts[3], int(value)
                    current.setdefault(uid, {"up": 0, "down": 0})
                    if direction == "uplink":
                        current[uid]["up"] += val
                    elif direction == "downlink":
                        current[uid]["down"] += val

            deltas: dict[str, dict] = {}
            for uid, s in current.items():
                prev = _previous_stats.get(uid, {"up": 0, "down": 0})
                up = s["up"] - prev["up"]
                down = s["down"] - prev["down"]
                if up < 0:
                    up = s["up"]
                if down < 0:
                    down = s["down"]
                if up > 0 or down > 0:
                    deltas[uid] = {"up": up, "down": down}
            _previous_stats = current
            return deltas
        except Exception as e:  # noqa: BLE001
            log.error("Error querying Xray stats: %s", e)
            return {}
