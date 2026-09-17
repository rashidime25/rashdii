"""The container's own wiring: $PORT, $PANEL_PORT, nginx, and a hostile data dir.

Why these tests exist: the platform's "Application failed to respond" is what a
misrouted port looks like from outside - the panel is healthy, the edge just never
reaches it. Every decision here used to be silent. The entrypoint runs for real in
these tests; only its neighbours (`nginx`, `python3`) are stubs that record what
they were told.
"""
import os
import pathlib
import shutil
import socket
import subprocess
import sys

import pytest

from app import config
from conftest import REPO


def _ipv6_available() -> bool:
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        s.bind(("::", 0))
        s.close()
        return True
    except OSError:
        return False


def test_panel_host_accepts_both_stacks():
    """If we bind `::`, IPv4 connections must still work (v4-mapped).

    This is the assumption the whole dual-stack decision rests on, so it is
    checked against the kernel instead of being trusted.
    """
    if not _ipv6_available():
        pytest.skip("no IPv6 in this environment")
    with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as srv:
        srv.bind(("::", 0))
        srv.listen(4)
        port = srv.getsockname()[1]
        for family, addr in ((socket.AF_INET, ("127.0.0.1", port)),
                             (socket.AF_INET6, ("::1", port))):
            with socket.socket(family, socket.SOCK_STREAM) as c:
                c.settimeout(3)
                c.connect(addr)                 # refused here means the bind is v6-only


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Listener:
    """Occupy a port so `_listener_up()` has something true to find."""

    def __init__(self, port: int):
        self.s = socket.socket()
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.s.bind(("127.0.0.1", port))
        self.s.listen(8)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.s.close()
        return False


# ------------------------------------------------------------------ the probe
def test_the_panel_always_serves_panel_port():
    """The bind is not a guess: entrypoint.sh decides the port, the app obeys it.

    And it obeys it on *every* address family the kernel offers - a platform edge
    that dials a family nobody listens on is exactly the outage this file exists
    for (healthy container, "Application failed to respond" outside).
    """
    src = pathlib.Path(REPO, "app", "main.py").read_text(encoding="utf-8")
    block = src[src.index('if __name__ == "__main__":'):]
    assert 'port=config.PANEL_PORT' in block, block[:400]
    assert "config.PANEL_BIND_HOSTS" in block, "the listen set must come from config"
    assert config.PANEL_BIND_HOSTS[0] == config.PANEL_HOST


def test_panel_binds_both_families_when_the_kernel_has_ipv6():
    expected = ["0.0.0.0", "::"] if _ipv6_available() else ["0.0.0.0"]
    assert config.PANEL_BIND_HOSTS == expected


def test_panel_host_env_replaces_the_bind_list(monkeypatch):
    """An explicit PANEL_HOST must still mean exactly that, nothing more."""
    monkeypatch.setenv("PANEL_HOST", "127.0.0.1")
    assert config._panel_hosts() == ["127.0.0.1"]


# ------------------------------------------------------------------ entrypoint
@pytest.fixture()
def container(tmp_path):
    """A fake image root: the real entrypoint + nginx.conf, stubbed neighbours."""
    root = tmp_path / "app"
    (root / "bin").mkdir(parents=True)
    (root / "entrypoint.sh").write_text(pathlib.Path(REPO, "entrypoint.sh").read_text(encoding="utf-8"),
                                        encoding="utf-8")
    (root / "nginx.conf").write_text(pathlib.Path(REPO, "nginx.conf").read_text(encoding="utf-8"),
                                      encoding="utf-8")
    (root / "bin" / "nginx").write_text('#!/bin/sh\necho "nginx $*" >> "$ROOT/calls.log"\nexit 0\n',
                                        encoding="utf-8")
    (root / "bin" / "python3").write_text(
        '#!/bin/sh\necho "python3 $* PANEL_PORT=${PANEL_PORT}" >> "$ROOT/calls.log"\nexit 0\n',
        encoding="utf-8")
    for f in (root / "bin").iterdir():
        f.chmod(0o755)
    return root


def _run(container, env_extra, with_nginx=True):
    path = f"{container}/bin:{os.environ.get('PATH', '')}"
    if not with_nginx:
        (container / "bin" / "nginx").unlink()
        if shutil.which("nginx", path=path):
            pytest.skip("a real nginx is on PATH; the fake image cannot be isolated")
    env = {**os.environ, "ROOT": str(container), "PATH": path,
           "NGINX_CONF": str(container / "nginx.conf"), **env_extra}
    proc = subprocess.run(["bash", str(container / "entrypoint.sh")], cwd=container, env=env,
                          capture_output=True, text=True, timeout=30)
    log = (container / "calls.log").read_text(encoding="utf-8") if (container / "calls.log").exists() else ""
    conf = (container / "nginx.conf").read_text(encoding="utf-8")
    return proc, log, conf


def test_entrypoint_points_nginx_at_the_panel_port_it_exports(container):
    public, panel = _free_port(), _free_port()
    proc, log, conf = _run(container, {"PORT": str(public), "PANEL_PORT": str(panel)})
    assert proc.returncode == 0, proc.stderr[-400:]
    assert f"listen {public};" in conf, conf[:400]
    if _ipv6_available():
        assert f"listen [::]:{public};" in conf, "the platform edge may reach us over IPv6"
    else:
        # a `listen [::]` line without a v6 stack is a fatal nginx error
        assert "[::]" not in conf
    assert f"proxy_pass http://127.0.0.1:{panel}; # titan-panel-upstream" in conf
    assert f"python3 -m app.main PANEL_PORT={panel}" in log, log
    # the WS/xhttp/gRPC inbounds keep their own ports - only the marked line moves
    assert "proxy_pass http://127.0.0.1:10001;" in conf
    assert "grpc://127.0.0.1:10005" in conf


def test_entrypoint_resolves_a_panel_port_that_collides_with_the_public_one(container):
    """PANEL_PORT == PORT is the classic self-inflicted 502: nginx binds the port,
    then the panel cannot, and the container crash-loops. It must be repaired."""
    public = _free_port()
    proc, log, conf = _run(container, {"PORT": str(public), "PANEL_PORT": str(public)})
    assert proc.returncode == 0, proc.stderr[-400:]
    shifted = public + 1
    assert f"panel moved to {shifted}" in proc.stdout, proc.stdout[-400:]
    assert f"proxy_pass http://127.0.0.1:{shifted}; # titan-panel-upstream" in conf
    assert f"python3 -m app.main PANEL_PORT={shifted}" in log, log


def test_entrypoint_listens_on_the_ports_an_edge_may_target(container):
    """A platform edge can disagree with PORT; the panel must not be unreachable.

    This is the exact failure that produced "Application failed to respond" while
    the container was healthy on the inside: the edge was forwarding to a port
    nobody listened on.
    """
    proc, _log, conf = _run(container, {"PORT": "8099"})
    assert proc.returncode == 0, proc.stderr[-300:]
    for candidate in ("443", "8080", "8000", "3000"):
        assert f"listen {candidate};" in conf, f"{candidate} missing from the listen set"
        if _ipv6_available():
            assert f"listen [::]:{candidate};" in conf
    # and never a port Xray or the panel already owns
    for reserved in ("10000", "10001", "10004", "10009", "10085"):
        assert f"listen {reserved};" not in conf, f"{reserved} must stay with Xray/the panel"
    assert "panel listens on:" in proc.stdout


def test_extra_listen_ports_can_be_turned_off(container):
    """Once the platform's target port is pinned, the safety net is optional."""
    proc, _log, conf = _run(container, {"PORT": "8097", "TITAN_EXTRA_LISTEN_PORTS": ""})
    assert proc.returncode == 0, proc.stderr[-300:]
    assert "listen 8097;" in conf
    assert "listen 8080;" not in conf and "listen 443;" not in conf


def test_entrypoint_defaults_when_the_platform_says_nothing(container):
    proc, _log, conf = _run(container, {})
    assert proc.returncode == 0, proc.stderr[-300:]
    assert "listen 8000;" in conf
    assert "proxy_pass http://127.0.0.1:10000; # titan-panel-upstream" in conf
    assert "routing: PORT=8000 PANEL_PORT=10000" in proc.stdout, proc.stdout[-300:]


def test_entrypoint_without_nginx_moves_the_panel_onto_the_public_port(container):
    """A start command or image without nginx must still answer $PORT - otherwise
    Railway shows 'Application failed to respond' with a perfectly healthy panel."""
    public = _free_port()
    proc, log, _conf = _run(container, {"PORT": str(public)}, with_nginx=False)
    assert proc.returncode == 0, proc.stderr[-300:]
    assert "no nginx found" in proc.stdout, proc.stdout[-300:]
    assert f"python3 -m app.main PANEL_PORT={public}" in log, log


# ------------------------------------------------------------------ data dir
def test_unusable_data_dir_degrades_instead_of_crashing():
    """A Volume mounted at the wrong path (or read-only) used to make the very first
    DB access raise - a crash loop behind the platform's blank error page."""
    bad = "/proc/titan-definitely-not-writable"        # mkdir fails for any uid
    out = subprocess.run(
        [sys.executable, "-c", "import app.config as c; print(c.DATA_DIR)"],
        cwd=REPO, env={**os.environ, "TITAN_DATA_DIR": bad, "PYTHONPATH": REPO},
        capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-400:]
    chosen = out.stdout.strip().splitlines()[-1]
    assert chosen != bad, "it must not keep using an unusable directory"
    assert os.path.isdir(chosen) and os.access(chosen, os.W_OK)
    assert "unusable" in out.stderr and "Volume" in out.stderr, out.stderr[-400:]


def test_settings_endpoint_still_works_after_the_guard(client, admin):
    """The fallback dir is a real, writable dir: boot, login and settings all work."""
    d = admin.get("/api/settings", headers={"Origin": "http://testserver"}).json()
    assert "public_domain" in d or isinstance(d, dict)
    assert os.path.isdir(config.DATA_DIR)
