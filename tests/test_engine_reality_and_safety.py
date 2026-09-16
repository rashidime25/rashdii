"""Regression tests for the reality/robustness fixes.

Each test here exists because of a bug that was observed on a real deployment,
not because of a style preference:

1. `xray x25519` output changed shape → the parser returned None → no keypair →
   every Reality link shipped with an empty `pbk=` and the inbound was skipped.
2. The link builder wrote the SNI into `spiderX`, which is a *path* field: a real
   Xray client refuses the whole config with `invalid "spiderX": <sni>`.
3. The link advertised `flow=xtls-rprx-vision` while the server-side user had no
   flow, so the tunnel came up and carried nothing.
4. A generated config that the engine rejects could replace a working one.
5. Nothing noticed when the Xray process died.
6. An empty node-sync payload deleted every user on that node.
7. The subscription response carried the same header twice (comma-joined).
8. `active_connections` was hard-wired to 0 because `state.ACTIVE` was never
   populated.
"""
import json
import os
import time
import types
import urllib.parse

import pytest


# --------------------------------------------------------------------------- helpers
def _mod(name):
    """The *panel's* module instance.

    The session fixture re-imports `app.*` against a throwaway data dir, so a bare
    `import app.config` can hand back a different module object than the one the
    running panel actually uses - and monkeypatching that copy would silently do
    nothing. Always take the attribute off the loaded `app.main`.
    """
    import sys
    main = sys.modules.get("app.main")
    if main is not None and hasattr(main, name):
        return getattr(main, name)
    return __import__(f"app.{name}", fromlist=["app"])


def _fake_run(outputs):
    """subprocess.run stand-in returning canned stdout per argv."""
    def run(args, **kwargs):
        key = " ".join(args[1:])
        out = outputs.get(key, "")
        return types.SimpleNamespace(stdout=out, stderr="", returncode=0)
    return run


# --------------------------------------------------------------------------- 1) parser
NEW_OUTPUT = """Choose one Authentication to use, do not mix them. Ephemeral key exchange is Post-Quantum safe anyway.

Authentication: X25519, not Post-Quantum
"decryption": "mlkem768x25519plus.native.600s.NOT-A-KEY"
"encryption": "mlkem768x25519plus.native.0rtt.NOT-A-KEY"

PrivateKey: QGbCa9GiAiEyYlJ-iTZY6H_KjKNvslPxznpbxueSAks
Password (PublicKey): MEehDnGM5xYHom9dzrLxxJsjQYhRRpBSCOYBNmRFj1w
Hash32: tLOso9avSYHcxX4YsUJHI8uo2z_BPeuA-RKV1ce_me0
"""

OLD_OUTPUT = """Private key: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Public key: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
"""


def test_parser_accepts_the_current_xray_output(monkeypatch):
    reality = _mod("reality")
    monkeypatch.setattr(reality.subprocess, "run",
                        _fake_run({"x25519": NEW_OUTPUT}))
    got = reality._xray_x25519()
    assert got == ("QGbCa9GiAiEyYlJ-iTZY6H_KjKNvslPxznpbxueSAks",
                   "MEehDnGM5xYHom9dzrLxxJsjQYhRRpBSCOYBNmRFj1w")


def test_parser_still_accepts_the_legacy_output(monkeypatch):
    reality = _mod("reality")
    monkeypatch.setattr(reality.subprocess, "run", _fake_run({"x25519": OLD_OUTPUT}))
    priv, pub = reality._xray_x25519()
    assert priv.startswith("aaa") and pub.startswith("bbb")


def test_parser_ignores_the_generated_keys_of_other_algorithms(monkeypatch):
    """`xray vlessenc` prints quoted keys — they must never be mistaken for these."""
    reality = _mod("reality")
    monkeypatch.setattr(reality.subprocess, "run", _fake_run({
        "x25519": NEW_OUTPUT,
        "x25519 -i QGbCa9GiAiEyYlJ-iTZY6H_KjKNvslPxznpbxueSAks": "Public key: DERIVED",
    }))
    assert reality._xray_x25519()[0] == "QGbCa9GiAiEyYlJ-iTZY6H_KjKNvslPxznpbxueSAks"


def test_parser_derives_the_public_key_when_only_the_private_one_is_printed(monkeypatch):
    reality = _mod("reality")
    derived = "c" * 43
    monkeypatch.setattr(reality.subprocess, "run", _fake_run({
        "x25519": "PrivateKey: " + "a" * 43 + "\n",
        "x25519 -i " + "a" * 43: f"Public key: {derived}\n",
    }))
    assert reality._xray_x25519() == ("a" * 43, derived)


def test_parser_returns_none_without_a_binary(monkeypatch):
    reality = _mod("reality")

    def boom(*_a, **_k):
        raise FileNotFoundError("no xray here")

    monkeypatch.setattr(reality.subprocess, "run", boom)
    assert reality._xray_x25519() is None


# --------------------------------------------------------------------------- 2) spiderX
def test_reality_link_uses_a_path_for_spiderx_not_the_sni(make_user):
    u = make_user(protocol="vless", transport="tcp", security="reality")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(u["main_link"]).query)
    assert q["spx"] == ["/"], u["main_link"]
    assert q["spx"] != q.get("sni"), "spiderX must not repeat the SNI"


def test_admin_supplied_spiderx_is_normalised_to_a_path(make_user):
    u = make_user(protocol="vless", transport="tcp", security="reality",
                  spider_x="feed")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(u["main_link"]).query)
    assert q["spx"] == ["/feed"], u["main_link"]


# ------------------------------------------------------------------- 3) flow consistency
@pytest.fixture()
def reality_user(make_user, db):
    """A Reality user plus the keypair a real deployment would have stored."""
    db.set_meta("reality_priv", "a" * 43)
    db.set_meta("reality_pub", "b" * 43)
    db.set_meta("reality_sid", "0123456789abcdef")
    db.set_setting("reality_pub", "b" * 43)
    db.set_setting("reality_sid", "0123456789abcdef")
    return make_user(protocol="vless", transport="tcp", security="reality")


def test_server_user_declares_the_flow_the_link_advertises(reality_user):
    xray = _mod("xray")
    link_flow = urllib.parse.parse_qs(
        urllib.parse.urlparse(reality_user["main_link"]).query)["flow"][0]
    cfg = xray.generate_xray_config()
    inbound = next(i for i in cfg["inbounds"] if i["tag"] == "in-vless-reality")
    client = next(c for c in inbound["settings"]["clients"]
                  if c["email"] == reality_user["uid"])
    assert client.get("flow") == link_flow == "xtls-rprx-vision"


def test_generated_config_tracks_online_users(reality_user):
    """`xray api statsonline` only answers when this policy flag is on."""
    xray = _mod("xray")
    cfg = xray.generate_xray_config()
    assert cfg["policy"]["levels"]["0"]["statsUserOnline"] is True


# ------------------------------------------------------------------ 4) config safety
@pytest.mark.skipif(not os.path.exists(os.environ.get("XRAY_BIN", "/usr/local/bin/xray")),
                    reason="needs a real Xray binary (XRAY_BIN)")
def test_invalid_config_is_rejected_and_the_previous_one_survives(tmp_path, monkeypatch, db):
    xray = _mod("xray")
    config = _mod("config")
    monkeypatch.setattr(config, "XRAY_BIN", os.environ["XRAY_BIN"])
    target = tmp_path / "config.json"
    monkeypatch.setattr(config, "XRAY_CONFIG_PATH", str(target))
    target.write_text('{"previous": true}')

    # an inbound without a port is something the engine refuses to load
    monkeypatch.setattr(xray, "generate_xray_config",
                        lambda: {"inbounds": [{"protocol": "vless", "tag": "broken",
                                               "settings": {"clients": [], "decryption": "none"}}],
                                 "outbounds": []})
    with pytest.raises(xray.ConfigError):
        xray.write_xray_config()
    assert json.loads(target.read_text()) == {"previous": True}, "the live config was replaced"


@pytest.mark.skipif(not os.path.exists(os.environ.get("XRAY_BIN", "/usr/local/bin/xray")),
                    reason="needs a real Xray binary (XRAY_BIN)")
def test_verify_config_reports_the_engine_error(tmp_path, monkeypatch):
    xray = _mod("xray")
    config = _mod("config")
    monkeypatch.setattr(config, "XRAY_BIN", os.environ["XRAY_BIN"])
    bad = tmp_path / "bad.json"
    bad.write_text('{"inbounds": [{"protocol": "nope"}]}')
    ok, detail = xray.verify_config(str(bad))
    assert ok is False and detail, "an unusable config must not pass validation"


# ------------------------------------------------------------------ 5) watchdog glue
def test_ensure_running_reports_missing_binary(tmp_path, monkeypatch):
    xray = _mod("xray")
    config = _mod("config")
    monkeypatch.setattr(config, "XRAY_BIN", str(tmp_path / "nope"))
    assert xray.ensure_running() == (False, "no-binary")


# ------------------------------------------------------------------ 6) node sync guard
def test_empty_node_sync_does_not_wipe_the_node(admin, db, monkeypatch):
    nodes = _mod("nodes")
    monkeypatch.setattr(nodes, "secret_valid_for_node", lambda _s: True)
    before = {u["uid"] for u in db.list_users()}
    r = admin.post("/api/node/sync", json={"secret": "x", "users": []},
                   headers={"Origin": "http://testserver"})
    assert r.status_code == 200, r.text
    assert r.json().get("skipped") == "empty-payload"
    assert {u["uid"] for u in db.list_users()} == before


# ------------------------------------------------------------------ 7) subscription headers
def test_subscription_sends_each_info_header_once(admin, make_user):
    u = make_user(protocol="vless", transport="ws", security="tls")
    r = admin.get(f"/sub/{u['uid']}")
    assert r.status_code == 200
    assert len(r.headers.get_list("subscription-userinfo")) == 1
    assert len(r.headers.get_list("profile-title")) == 1


# ------------------------------------------------------------------ 8) real online state
def test_status_reports_a_user_as_online_from_engine_traffic(admin, make_user):
    state = _mod("state")
    u = make_user(protocol="vless", transport="ws", security="tls")
    assert admin.get(f"/api/users/{u['uid']}").json()["status"]["online"] is False
    state.LAST_TRAFFIC[u["uid"]] = time.time()
    try:
        st = admin.get(f"/api/users/{u['uid']}").json()["status"]
        assert st["online"] is True and st["active_connections"] == 1
    finally:
        state.LAST_TRAFFIC.pop(u["uid"], None)


def test_health_can_be_trimmed_for_public_exposure(monkeypatch, client):
    config = _mod("config")
    monkeypatch.setattr(config, "HEALTH_MINIMAL", True)
    body = client.get("/health").json()
    assert set(body) == {"status", "ts", "version"}
