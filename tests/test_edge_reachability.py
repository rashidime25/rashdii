"""What a client is handed must be reachable — measured, not assumed.

Why this file exists: a Railway (or any HTTP-edge) deployment *accepts* TCP on
every port of its edge IP and then answers nothing. Measured on the live service:
connect() to 10009 succeeds, zero bytes come back, the client hangs until its own
timeout. The panel used to write exactly such a port into every raw (TCP/Reality/
SS) link, so "the config times out on MCI/IRANCEL" had a server-side cause that
no client setting could fix.

These tests pin the rule: on an HTTP-only edge a link carries only what the edge
can carry, and raw ports come back the moment a TCP proxy (or a real host) exists.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from conftest import REPO  # noqa: E402
from app import config  # noqa: E402

H = {"Origin": "http://testserver"}
#: Every port that only exists inside the container.
RAW_PORTS = (10001, 10002, 10003, 10004, 10005, 10006, 10007, 10008, 10009,
             10010, 10011, 10012, 10013, 10014, 10085, 51820)


@pytest.fixture()
def edge_only(monkeypatch):
    """The Railway shape: an HTTP edge, no TCP proxy."""
    monkeypatch.setattr(config, "EDGE_HTTP_ONLY", True)
    monkeypatch.setattr(config, "TCP_PROXY_DOMAIN", "")
    monkeypatch.setattr(config, "TCP_PROXY_PORT", 0)
    yield


def _no_raw_port(link: str) -> bool:
    return not any(f":{p}" in link for p in RAW_PORTS)


def test_a_raw_config_is_stored_as_something_the_edge_can_serve(admin, make_user, edge_only):
    """Reality over raw TCP cannot work here, so it must not be what gets stored.

    The admin asked for the strongest thing they know; handing them a link that
    hangs forever is not respecting that choice.
    """
    u = make_user(protocol="vless", transport="tcp", security="reality")
    assert u["transport"] in config.EDGE_TRANSPORTS, u["transport"]
    assert u["security"] == "tls"
    assert _no_raw_port(u["main_link"]), u["main_link"]
    assert ":443" in u["main_link"] or f":{config.PUBLIC_PORT}" in u["main_link"]


def test_every_served_transport_stays_untouched(admin, make_user, edge_only):
    """The mapping must not touch configs that already work."""
    for transport in ("ws", "xhttp", "httpupgrade", "grpc"):
        u = make_user(protocol="vless", transport=transport, security="tls")
        assert u["transport"] == transport
        assert _no_raw_port(u["main_link"])


def test_a_stored_raw_config_is_link_mapped(admin, make_user, edge_only, monkeypatch):
    """Rows created before this fix (or by a node) still must not hang a client."""
    u = make_user(protocol="vless", transport="ws", security="tls")
    # Force a raw row straight into the DB: that is what an older version stored.
    from app import db
    db.update_user(u["uid"], {"transport": "tcp", "security": "reality"})
    shown = admin.get(f"/api/users/{u['uid']}", headers=H).json()
    link = shown["main_link"]
    assert _no_raw_port(link), link
    assert "type=xhttp" in link or "type=ws" in link, link
    assert "security=tls" in link
    assert shown.get("edge_warnings"), "the admin must be told the link was remapped"


def test_a_tcp_proxy_brings_raw_transports_back(admin, make_user, monkeypatch):
    """Railway injects RAILWAY_TCP_PROXY_* once a TCP proxy exists - one variable
    decides whether Reality is advertised as Reality."""
    monkeypatch.setattr(config, "EDGE_HTTP_ONLY", True)
    monkeypatch.setattr(config, "TCP_PROXY_DOMAIN", "shuttle.proxy.rlwy.net")
    monkeypatch.setattr(config, "TCP_PROXY_PORT", 23456)
    u = make_user(protocol="vless", transport="tcp", security="reality")
    assert u["transport"] == "tcp" and u["security"] == "reality"
    assert "shuttle.proxy.rlwy.net:23456" in u["main_link"], u["main_link"]


def test_a_railway_node_keeps_only_its_edge_port(admin, edge_only):
    """A node's address port is its *internal* port - unreachable from outside."""
    r = admin.post("/api/nodes", headers=H, json={
        "name": "edge-node", "address": "titan-node-abc.up.railway.app:443",
        "city": "Frankfurt", "country": "Germany", "country_code": "DE"})
    assert r.status_code == 200, r.text
    node_id = r.json()["node"]["id"]
    r2 = admin.post("/api/users", headers=H, json={
        "name": "node-user", "protocol": "vless", "transport": "tcp",
        "security": "reality", "node_id": node_id})
    assert r2.status_code == 200, r2.text
    u = r2.json()["user"]
    link = u["main_link"]
    assert "titan-node-abc.up.railway.app" in link
    assert ":443" in link, link
    assert _no_raw_port(link), link
    assert "type=xhttp" in link and "security=tls" in link
    admin.delete(f"/api/nodes/{node_id}")


def test_a_vps_node_with_an_exposed_port_keeps_it(admin, edge_only):
    """The opposite case must keep working: a plain host with a real open port."""
    r = admin.post("/api/nodes", headers=H, json={
        "name": "vps-node", "address": "203.0.113.9:8443",
        "city": "Tehran", "country": "Iran", "country_code": "IR"})
    node_id = r.json()["node"]["id"]
    r2 = admin.post("/api/users", headers=H, json={
        "name": "vps-user", "protocol": "vless", "transport": "tcp",
        "security": "reality", "node_id": node_id})
    u = r2.json()["user"]
    assert ":8443" in u["main_link"], u["main_link"]
    assert "security=reality" in u["main_link"]
    admin.delete(f"/api/nodes/{node_id}")


def test_edge_check_names_the_cause(admin, edge_only):
    """The endpoint an admin runs when a config times out."""
    r = admin.get("/api/edge-check", headers=H)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["edge_http_only"] is True
    assert "proxy_in_front" in data
    assert data["public"]["port"] == config.PUBLIC_PORT or data["public"]["port"] == 443
    assert set(data["transports"]) >= {"vless+ws", "vless+xhttp", "vless+grpc"}
    for name, info in data["transports"].items():
        assert "status" in info and "alive" in info
    assert data["raw_ports"]["XRAY_TCP_VLESS_REALITY_PORT"] == config.XRAY_TCP_VLESS_REALITY_PORT
    assert "TCP proxy" in data["note"] or "TCP proxy" in data["note"]


def test_the_public_host_used_for_links_is_never_a_raw_port(make_user, edge_only):
    u = make_user(protocol="vless", transport="tcp", security="tls")
    assert _no_raw_port(u["main_link"])
    assert _no_raw_port(u["qr_data"])
    for link in u["links"]:
        assert _no_raw_port(link), link
