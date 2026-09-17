"""A node link must point at a node that provably has the user.

Why this file exists: "I add a node, pick it (and its location) for the config,
and the config times out" had a panel-side cause. The panel advertised whatever
node the user was assigned to, whether or not that node had ever received them —
and it also served *only* the users assigned to itself, so the two halves of the
system could disagree. Every test here pins one half of the rule that replaced
that: the link follows the evidence, and the panel is always able to serve.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

H = {"Origin": "http://testserver"}


@pytest.fixture()
def edge_only(monkeypatch):
    """The Railway shape: an HTTP edge for the panel, no TCP proxy."""
    from app import config
    monkeypatch.setattr(config, "EDGE_HTTP_ONLY", True)
    monkeypatch.setattr(config, "TCP_PROXY_DOMAIN", "")
    monkeypatch.setattr(config, "TCP_PROXY_PORT", 0)
    yield


def _node(admin, **fields):
    payload = {"name": "n-" + fields.get("address", "x")[:8], **fields}
    r = admin.post("/api/nodes", headers=H, json=payload)
    assert r.status_code == 200, r.text
    return r.json()["node"]["id"]


def _user(admin, node_id, **fields):
    payload = {"name": "u-" + str(node_id), "protocol": "vless",
               "transport": "ws", "security": "tls", "node_id": node_id, **fields}
    r = admin.post("/api/users", headers=H, json=payload)
    assert r.status_code == 200, r.text
    return r.json()["user"]


def _shown(admin, uid):
    return admin.get(f"/api/users/{uid}", headers=H).json()


def test_the_panel_can_serve_every_user_however_they_are_assigned(admin, edge_only):
    """A link that falls back to the panel only works if the panel serves it.

    The panel used to serve *only* its own node's users, so a fallback link (or a
    user on "auto" before any node measurement) pointed at a server that had no
    such user at all — the client connected and waited for its timeout.
    """
    from app import nodes as nodesync
    node_id = _node(admin, address="node-a.up.railway.app", country_code="DE")
    u = _user(admin, node_id)
    assert u["uid"] in {x["uid"] for x in nodesync.local_users()}
    admin.delete(f"/api/nodes/{node_id}")


def test_a_node_that_never_received_the_user_is_not_advertised(admin, edge_only):
    """The exact field case: the node exists but the sync never named this user."""
    node_id = _node(admin, address="node-b.up.railway.app", country_code="DE")
    u = _user(admin, node_id)
    assert "node-b.up.railway.app" not in u["main_link"], u["main_link"]
    assert u["edge_warnings"], "the admin must be told the link fell back to the panel"
    admin.delete(f"/api/nodes/{node_id}")


def test_once_the_node_has_the_user_the_link_points_at_it(admin, edge_only):
    from app import routing
    node_id = _node(admin, address="node-c.up.railway.app", country_code="DE")
    u = _user(admin, node_id)
    routing.record_sync(node_id, True, uids=[u["uid"]])
    link = _shown(admin, u["uid"])["main_link"]
    assert "node-c.up.railway.app" in link, link
    admin.delete(f"/api/nodes/{node_id}")


def test_a_user_created_after_the_last_sync_is_not_claimed_by_the_node(admin, edge_only):
    """A sync is a complete list: a user absent from it is not on the node yet."""
    from app import routing
    node_id = _node(admin, address="node-d.up.railway.app", country_code="DE")
    first = _user(admin, node_id, name="first")
    routing.record_sync(node_id, True, uids=[first["uid"]])
    second = _user(admin, node_id, name="second")
    link = _shown(admin, second["uid"])["main_link"]
    assert "node-d.up.railway.app" not in link, link
    # ... and the user that *was* in the sync still uses the node.
    assert "node-d.up.railway.app" in _shown(admin, first["uid"])["main_link"]
    admin.delete(f"/api/nodes/{node_id}")


def test_a_failed_sync_falls_back_and_names_the_reason(admin, edge_only):
    from app import routing
    node_id = _node(admin, address="node-e.up.railway.app", country_code="DE")
    u = _user(admin, node_id)
    routing.record_sync(node_id, True, uids=[u["uid"]])
    assert "node-e.up.railway.app" in _shown(admin, u["uid"])["main_link"]
    routing.record_sync(node_id, False, err="HTTP 401")
    shown = _shown(admin, u["uid"])
    assert "node-e.up.railway.app" not in shown["main_link"], shown["main_link"]
    assert any("sync" in w and "panel" in w for w in shown["edge_warnings"]), shown["edge_warnings"]
    admin.delete(f"/api/nodes/{node_id}")


def test_a_disabled_node_never_takes_the_link(admin, edge_only):
    node_id = _node(admin, address="node-f.up.railway.app", country_code="DE")
    u = _user(admin, node_id)
    from app import routing
    routing.record_sync(node_id, True, uids=[u["uid"]])
    admin.patch(f"/api/nodes/{node_id}", headers=H, json={"enabled": False})
    assert "node-f.up.railway.app" not in _shown(admin, u["uid"])["main_link"]
    admin.delete(f"/api/nodes/{node_id}")


def test_auto_never_picks_a_node_that_is_not_serving(admin, edge_only):
    """"auto" used to mean "lowest measured latency" — online, synced or not."""
    from app import routing
    node_id = _node(admin, address="node-g.up.railway.app", country_code="DE")
    u = _user(admin, 0, name="auto-user")
    routing.record_latency(node_id, 42, True)          # measured, but nothing synced
    assert "node-g.up.railway.app" not in _shown(admin, u["uid"])["main_link"]
    routing.record_sync(node_id, True, uids=[u["uid"]])
    assert "node-g.up.railway.app" in _shown(admin, u["uid"])["main_link"]
    admin.delete(f"/api/nodes/{node_id}")


def test_the_node_api_reports_what_the_panel_knows(admin, edge_only):
    """The dashboard must be able to explain a fallback without guessing."""
    from app import config, routing
    node_id = _node(admin, address="node-h.up.railway.app", country_code="DE")
    u = _user(admin, node_id)
    routing.record_sync(node_id, True, uids=[u["uid"]])
    routing.record_raw_probe(node_id, {config.XRAY_TCP_VLESS_REALITY_PORT: False})
    routing.record_edge_probe(node_id, "https", 443)
    node = next(n for n in admin.get("/api/nodes", headers=H).json()["nodes"] if n["id"] == node_id)
    assert node["sync"]["ok"] is True
    assert node["sync"]["serving"] == [u["uid"]]
    assert node["raw_open"][str(config.XRAY_TCP_VLESS_REALITY_PORT)] is False
    assert node["edge"]["scheme"] == "https" and node["edge"]["measured"] is True
    admin.delete(f"/api/nodes/{node_id}")
