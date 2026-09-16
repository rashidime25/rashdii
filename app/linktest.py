"""Server-side "does this config actually work?" check.

The panel builds a link and hands it over. Until now nobody ever *proved* that
link connects: a typo in an SNI, a flow the server does not offer, a client
pinned to a transport its inbound does not serve — all of those produce a link
that looks perfect and dies on connect, and the admin only hears about it from
the user.

This module closes that loop. It:

1. reads the config the engine is *actually running* and finds the inbound that
   serves this user (the same lookup the engine does, so "user missing from the
   config" is itself a finding),
2. spawns a throwaway client from the panel's own ``build_client_config`` — the
   same generator the "download JSON" button uses,
3. dials through it over SOCKS5 and fetches the panel's test target,
4. reports status + time-to-first-byte, and tears everything down.

No third-party dependency: the SOCKS5 handshake is a dozen lines of raw socket
work, because adding a `requests[socks]` requirement to a one-container panel
would be a poor trade.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import struct
import subprocess
import tempfile
import time

from . import config, links

log = logging.getLogger("titan.linktest")

# a test target that is tiny, everywhere, and answers with a content-free 204
DEFAULT_TARGET = "https://www.gstatic.com/generate_204"
_TEST_TIMEOUT = 8.0


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ------------------------------------------------------------------ socks5 client
def _socks5_connect(proxy_port: int, host: str, port: int, timeout: float = 5.0) -> socket.socket:
    """Open a TCP tunnel through a local SOCKS5 proxy (CONNECT, no auth, IPv4)."""
    s = socket.create_connection(("127.0.0.1", proxy_port), timeout=timeout)
    s.settimeout(timeout)
    s.sendall(b"\x05\x01\x00")                     # version 5, one method: no auth
    if s.recv(2) != b"\x05\x00":
        raise OSError("socks5: no acceptable auth method")
    try:
        addr = socket.inet_aton(socket.gethostbyname(host))
        req = b"\x05\x01\x00\x01" + addr + struct.pack("!H", port)
    except OSError:
        # the proxy resolves the name itself (SOCKS5h), which is what we want for
        # a target that may only be reachable from the server's own egress
        name = host.encode("idna")[:255]
        req = b"\x05\x01\x00\x03" + bytes([len(name)]) + name + struct.pack("!H", port)
    s.sendall(req)
    reply = s.recv(4)
    if len(reply) < 4 or reply[1] != 0:
        raise OSError(f"socks5: connect refused (code {reply[1] if len(reply) > 1 else '?'})")
    atyp = reply[3]
    s.recv(4 if atyp == 1 else (16 if atyp == 4 else s.recv(1)[0]))
    s.recv(2)
    return s


def _http_probe(proxy_port: int, url: str, timeout: float = _TEST_TIMEOUT) -> dict:
    """Minimal HTTP/1.1 GET through the tunnel. Returns {ok, code, ms, error}."""
    scheme, _, rest = url.partition("://")
    if scheme not in ("http", "https"):
        return {"ok": False, "code": None, "ms": None, "error": "unsupported-scheme"}
    hostport, _, path = rest.partition("/")
    host, _, port_s = hostport.partition(":")
    port = int(port_s or (443 if scheme == "https" else 80))
    t0 = time.time()
    try:
        raw = _socks5_connect(proxy_port, host, port, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - surfaced to the admin verbatim
        return {"ok": False, "code": None, "ms": None, "error": f"proxy: {exc}"[:180]}
    try:
        if scheme == "https":
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE   # we measure reachability, not trust
            sock = ctx.wrap_socket(raw, server_hostname=host)
        else:
            sock = raw
        sock.settimeout(timeout)
        sock.sendall(
            f"GET /{path or ''} HTTP/1.1\r\nHost: {host}\r\n"
            f"User-Agent: TiTaN-link-test\r\nConnection: close\r\n\r\n".encode()
        )
        head = sock.recv(64)
        ms = int((time.time() - t0) * 1000)
        code = None
        try:
            code = int(head.split(b" ")[1])
        except (IndexError, ValueError):
            pass
        sock.close()
        return {"ok": code is not None and 200 <= code < 400, "code": code, "ms": ms,
                "error": "" if code else "no-http-response"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "code": None, "ms": None, "error": str(exc)[:180]}
    finally:
        try:
            raw.close()
        except Exception:  # noqa: BLE001
            pass


# ------------------------------------------------------------------ inbound lookup
def find_inbound(user: dict, xray_cfg: dict) -> dict | None:
    """The inbound the engine would use for this user, or None if absent.

    A user that is in the database but not in the running config is the single
    most common "why doesn't my config work" answer, so it is reported as a
    finding rather than raised.
    """
    wanted_net = (user.get("transport") or "").lower()
    matches = []
    for ib in xray_cfg.get("inbounds") or []:
        clients = ((ib.get("settings") or {}).get("clients")) or []
        ss = ib.get("streamSettings") or {}
        for c in clients:
            if c.get("email") == user.get("uid"):
                matches.append((ib, ss))
                break
        else:
            if ss.get("network") == "hysteria" and user.get("protocol") == "hysteria2":
                matches.append((ib, ss))
    if not matches:
        return None
    for ib, ss in matches:
        ss = ib.get("streamSettings") or {}
        if wanted_net and ss.get("network") == wanted_net:
            return ib
    return matches[0][0]


def _port_of(ib: dict) -> int:
    try:
        return int(ib.get("port") or 0)
    except (TypeError, ValueError):
        return 0


# ------------------------------------------------------------------ public entry
def test_user(user: dict, settings: dict, xray_cfg: dict | None = None,
              target: str | None = None, host: str = "127.0.0.1") -> dict:
    """Run the whole check. Never raises: the caller stores the report."""
    target = target or settings.get("link_test_target") or DEFAULT_TARGET
    report: dict = {"uid": user.get("uid"), "name": user.get("name"), "target": target,
                    "steps": [], "ok": False}

    def step(name: str, ok: bool, detail: str = "") -> None:
        report["steps"].append({"name": name, "ok": ok, "detail": detail})

    if xray_cfg is None:
        cfg_path = config.XRAY_CONFIG_PATH
        try:
            with open(cfg_path, "r", encoding="utf-8") as fh:
                xray_cfg = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            step("read-config", False, str(exc)[:120])
            return report

    ib = find_inbound(user, xray_cfg)
    port = _port_of(ib) if ib else 0
    step("inbound", bool(ib), f"port {port}" if ib else "user is not in the running config")
    if not ib:
        return report
    step("engine-port", port > 0 and _tcp_open(host, port), f"{host}:{port}")

    client_cfg = links.build_client_config(user, host, port, settings)
    socks_port = _free_port()
    for inb in client_cfg["inbounds"]:
        inb["port"] = socks_port if inb.get("protocol") == "socks" else socks_port + 1
    step("client-config", True, f"{client_cfg['outbounds'][0]['streamSettings']['network']}")

    proc = None
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(prefix="titan-linktest-", suffix=".candidate.json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(client_cfg, fh)
        xray_bin = config.XRAY_BIN
        try:
            proc = subprocess.Popen([xray_bin, "run", "-c", tmp], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
        except OSError as exc:
            step("spawn-client", False, str(exc)[:120])
            return report
        ok = _wait_port(socks_port, timeout=4.0)
        step("spawn-client", ok, "client engine up" if ok else "client engine did not open its proxy port")
        if not ok:
            return report
        probe = _http_probe(socks_port, target)
        step("handshake", probe["ok"], probe.get("error") or f"HTTP {probe['code']}")
        step("fetch", probe["ok"], f"{probe.get('ms')} ms" if probe.get("ms") else (probe.get("error") or ""))
        report["latency_ms"] = probe.get("ms")
        report["http_code"] = probe.get("code")
        report["transport"] = (ib.get("streamSettings") or {}).get("network")
        report["security"] = (ib.get("streamSettings") or {}).get("security", "none")
        report["ok"] = bool(probe["ok"])
    finally:
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:  # noqa: BLE001
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
    return report


def _tcp_open(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_port(port: int, timeout: float = 4.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _tcp_open("127.0.0.1", port, timeout=0.4):
            return True
        time.sleep(0.15)
    return False
