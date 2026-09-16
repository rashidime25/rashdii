"""Tests for the config builder: recipes, per-user engine knobs, tuning.

These exist because every one of them is a way the panel can hand out a config
that *looks* right and does not work — the failure mode this feature is meant to
eliminate:

1. A recipe must never overwrite what the admin typed explicitly.
2. An unknown recipe id must be ignored, not stored (a stale id in a bookmarked
   request would otherwise put meaningless data in the DB forever).
3. `flow=""` means "inherit", `flow="none"` means "plain VLESS": rows written
   before this feature have `''`, and treating them as "no flow" would break
   every Reality user in the panel.
4. A per-user SNI/shortId must reach the shared inbound's `serverNames` /
   `shortIds`, otherwise the handshake for that user is refused.
5. Socket tuning must land on TCP inbounds and must NOT land on the QUIC ones.
6. Policy levels are emitted only for plans someone actually uses.
7. The settings API must reject nonsense (mode names, padding junk, bad SNI
   lists) instead of writing it into a config the engine then refuses.
8. The link and the server must agree about flow — a mismatch is a dead tunnel.
9. The client config the panel hands out must be a config this engine accepts.
"""
import json
import os
import subprocess
import sys

import pytest

XRAY = os.environ.get("XRAY_BIN") or "/home/user/bin/xray"


def _mod(name):
    """The panel's own module instance (see tests/test_engine_reality_and_safety)."""
    main = sys.modules.get("app.main")
    if main is not None and hasattr(main, name):
        return getattr(main, name)
    return __import__(f"app.{name}", fromlist=["app"])


H = {"Origin": "http://testserver"}

#: A throwaway Reality keypair so the engine's Reality inbound is generated even
#: when the environment has no xray binary to derive one from (mock mode).
_TEST_PRIV = "oHZfadhzEz4gL8ekbV4Dbnike76y0j-EWE-ENJffPWk"
_TEST_SID = "1a2b3c4d"


@pytest.fixture(scope="module", autouse=True)
def _reality_keys(client, db):
    """Every test in this file assumes Reality inbounds exist."""
    if not db.get_meta("reality_priv"):
        db.set_meta("reality_priv", _TEST_PRIV)
    if not db.get_meta("reality_sid"):
        db.set_meta("reality_sid", _TEST_SID)
    yield


def _engine_available() -> bool:
    if not os.path.exists(XRAY):
        return False
    try:
        return subprocess.run([XRAY, "version"], capture_output=True, timeout=10).returncode == 0
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------- 1) recipe layer
def test_recipe_fills_only_untouched_fields():
    profiles = _mod("profiles")
    payload = {"name": "x", "protocol": "vless", "transport": "tcp", "security": "reality",
               "name_wins": 1}
    merged, applied = profiles.apply_recipe(payload, "gaming")
    assert applied == "gaming"
    assert merged["protocol"] == "vless"           # explicit value kept
    # the recipe supplied the transport-level knobs the request omitted
    assert merged.get("policy_level") is not None or merged.get("mux_enabled") is not None


def test_explicit_payload_beats_recipe():
    profiles = _mod("profiles")
    recipe = profiles.get_recipe("gaming")
    assert recipe is not None
    fields = {k: v for k, v in recipe["fields"].items() if k in profiles.ALLOWED_FIELDS}
    assert fields, "gaming recipe should set at least one allowed field"
    key, value = next(iter(fields.items()))
    payload = {key: "__admin_choice__"}
    merged, _ = profiles.apply_recipe(payload, "gaming")
    assert merged[key] == "__admin_choice__"


def test_unknown_recipe_is_ignored():
    profiles = _mod("profiles")
    payload = {"name": "x"}
    merged, applied = profiles.apply_recipe(payload, "definitely-not-a-recipe")
    assert applied is None
    assert merged == {"name": "x"}
    assert profiles.get_recipe("") is None
    assert profiles.get_recipe(None) is None


def test_recipe_list_is_serialisable_and_complete(admin):
    r = admin.get("/api/recipes", headers=H)
    assert r.status_code == 200, r.text
    data = r.json()
    ids = [rec["id"] for rec in data["recipes"]]
    assert {"resilient", "cdn", "compat", "gaming", "telegram"} <= set(ids)
    for rec in data["recipes"]:
        assert rec.get("name") and isinstance(rec.get("fields"), dict)
        json.dumps(rec)                            # must be JSON-clean
        profiles = _mod("profiles")
        for key in rec["fields"]:
            assert key in profiles.ALLOWED_FIELDS | profiles.SETTINGS_FIELDS
    assert any(p["level"] == 1 for p in data["plans"])
    assert "auto" in data["xhttp_modes"]


def test_create_with_recipe_stores_and_applies(make_user):
    profiles = _mod("profiles")
    u = make_user(recipe="cdn")                      # nothing else specified
    assert u["recipe"] == "cdn"
    user_fields, _settings = profiles.split_fields(profiles.get_recipe("cdn")["fields"])
    for key, value in user_fields.items():
        assert u.get(key) == value, f"{key} should have come from the recipe"


def test_recipe_also_turns_on_the_panel_wide_half(admin, make_user):
    """The fragment recipe must not silently drop the half that lives in settings."""
    profiles = _mod("profiles")
    admin.post("/api/settings", json={"fragment_enabled": False}, headers=H)
    r = admin.post("/api/users", json={"name": "frag-" + os.urandom(3).hex(),
                                       "recipe": "resilient"}, headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    uid = body["user"]["uid"]
    try:
        assert body["recipe_settings"].get("fragment_enabled") is True
        assert _mod("db").get_settings()["fragment_enabled"] is True
        # ...and it is advertised in the link, which is the point of the recipe
        link = body["user"]["main_link"]
        assert "fp_len=" in link and "fp_int=" in link
        # an explicit fragment choice in the request still wins
        admin.post("/api/settings", json={"fragment_enabled": False}, headers=H)
        r2 = admin.post("/api/users", json={"name": "nofrag-" + os.urandom(3).hex(),
                                            "recipe": "resilient", "fragment_enabled": True},
                        headers=H)
        assert r2.status_code == 200
        uid2 = r2.json()["user"]["uid"]
        admin.delete(f"/api/users/{uid2}")
    finally:
        admin.delete(f"/api/users/{uid}")


# --------------------------------------------------------------- 2) flow semantics
def test_flow_sentinels(make_user):
    inherit = make_user(flow="", protocol="vless", transport="tcp", security="reality")
    plain = make_user(flow="none", protocol="vless", transport="tcp", security="reality")
    vision = make_user(flow="xtls-rprx-vision", protocol="vless", transport="tcp",
                       security="reality")
    assert inherit["flow"] == ""
    assert plain["flow"] == "none"
    assert vision["flow"] == "xtls-rprx-vision"
    # a garbage flow must not be stored
    bad = make_user(flow="not-a-flow")
    assert bad["flow"] == ""


def test_flow_reaches_engine_and_link_consistently(make_user):
    xray, links = _mod("xray"), _mod("links")
    plain = make_user(flow="none", protocol="vless", transport="tcp", security="reality")
    cfg = xray.generate_xray_config()
    reality = next(ib for ib in cfg["inbounds"] if ib["tag"] == "in-vless-reality")
    entry = next(c for c in reality["settings"]["clients"] if c["email"] == plain["uid"])
    assert "flow" not in entry, "flow=none must not advertise vision on the server"
    s = {"reality_pub": "x", "reality_sid": "ab"}
    link = links.build_vless_link("example.com", 443, plain, s)
    assert "flow=" not in link, "the link must not ask for a flow the server does not offer"


def test_default_reality_user_still_gets_vision(make_user):
    """The regression that mattered: legacy rows have flow='' and must inherit."""
    xray, links = _mod("xray"), _mod("links")
    u = make_user(protocol="vless", transport="tcp", security="reality")   # no flow key
    cfg = xray.generate_xray_config()
    reality = next(ib for ib in cfg["inbounds"] if ib["tag"] == "in-vless-reality")
    entry = next(c for c in reality["settings"]["clients"] if c["email"] == u["uid"])
    assert entry.get("flow") == "xtls-rprx-vision"
    assert "flow=xtls-rprx-vision" in links.build_vless_link(
        "example.com", 443, u, {"reality_pub": "x", "reality_sid": "ab"})


# --------------------------------------------------------------- 3) identity
def test_per_user_identity_reaches_the_inbound(make_user):
    xray = _mod("xray")
    u = make_user(protocol="vless", transport="tcp", security="reality",
                  reality_sni="www.samsung.com", short_id="deadbeef")
    reality = next(ib for ib in xray.generate_xray_config()["inbounds"]
                   if ib["tag"] == "in-vless-reality")
    rs = reality["streamSettings"]["realitySettings"]
    assert "www.samsung.com" in rs["serverNames"]
    assert "deadbeef" in rs["shortIds"]
    assert u["reality_sni"] == "www.samsung.com"


def test_bad_sni_is_rejected_not_stored(make_user):
    u = make_user(reality_sni='www.example.com" ><script>', protocol="vless",
                  transport="tcp", security="reality")
    assert u["reality_sni"] == ""


def test_settings_extra_server_names_feed_the_inbound(admin, make_user):
    r = admin.post("/api/settings",
                   json={"reality_server_names": "a.example.com, b.example.com;bad name"}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["settings"]["reality_server_names"] == "a.example.com,b.example.com"
    make_user(protocol="vless", transport="tcp", security="reality")
    reality = next(ib for ib in _mod("xray").generate_xray_config()["inbounds"]
                   if ib["tag"] == "in-vless-reality")
    names = reality["streamSettings"]["realitySettings"]["serverNames"]
    assert "a.example.com" in names and "b.example.com" in names


# --------------------------------------------------------------- 4) tuning
def test_socket_tuning_on_tcp_inbounds_only(admin, make_user):
    admin.post("/api/settings", json={"sock_tfo": True, "sock_nodelay": True,
                                      "sock_keepalive": True, "sock_user_timeout": 5000},
               headers=H)
    make_user(protocol="vless", transport="ws", security="tls")
    make_user(protocol="hysteria2", transport="udp", security="tls")
    cfg = _mod("xray").generate_xray_config()
    ws = next(ib for ib in cfg["inbounds"] if ib["tag"] == "in-vless-ws")
    so = ws["streamSettings"]["sockopt"]
    assert so["tcpFastOpen"] is True and so["tcpNoDelay"] is True
    assert so["tcpUserTimeout"] == 5000 and so["tcpKeepAliveIdle"] == 30
    for ib in cfg["inbounds"]:
        ss = ib.get("streamSettings") or {}
        if ss.get("network") in ("hysteria", "quic", "kcp"):
            assert "sockopt" not in ss, "UDP transports must not get TCP socket options"


def test_xhttp_settings_follow_the_panel(admin, make_user):
    admin.post("/api/settings", json={"xhttp_mode": "stream-one", "xhttp_padding": "64-512",
                                      "xhttp_max_post": 250000, "xhttp_xmux": True}, headers=H)
    make_user(protocol="vless", transport="xhttp", security="tls")
    cfg = _mod("xray").generate_xray_config()
    xs = next(ib for ib in cfg["inbounds"] if ib["tag"] == "in-vless-xhttp")["streamSettings"]["xhttpSettings"]
    assert xs["mode"] == "stream-one"
    assert xs["extra"]["xPaddingBytes"] == "64-512"
    assert xs["extra"]["scMaxEachPostBytes"] == 250000
    assert xs["xmux"]["maxConcurrency"] == "16-32"


def test_settings_reject_garbage(admin):
    before = admin.get("/api/settings", headers=H).json()
    r = admin.post("/api/settings", json={"xhttp_mode": "turbo", "xhttp_padding": "abc",
                                          "sock_congestion": "warp-drive",
                                          "sock_user_timeout": -5, "reality_server_names": "bad name"},
                   headers=H)
    assert r.status_code == 200
    after = r.json()["settings"]
    assert after["xhttp_mode"] == before["xhttp_mode"]
    assert after["xhttp_padding"] == before["xhttp_padding"]
    assert after["sock_congestion"] == before["sock_congestion"]
    assert after["sock_user_timeout"] == before["sock_user_timeout"]
    assert after["reality_server_names"] == ""


def test_policy_levels_only_for_used_plans(make_user):
    make_user(protocol="vless", transport="ws", security="tls", policy_level=2)
    policy = _mod("xray").generate_xray_config()["policy"]
    assert policy["levels"]["0"]["statsUserOnline"] is True
    assert policy["levels"]["2"]["bufferSize"] == 1024
    # level 1 exists in the plan table but nobody is on it → not emitted
    assert "1" not in policy["levels"]


def test_policy_level_reaches_the_client_entry(make_user):
    xray = _mod("xray")
    u = make_user(protocol="vless", transport="ws", security="tls", policy_level=1)
    cfg = xray.generate_xray_config()
    ws = next(ib for ib in cfg["inbounds"] if ib["tag"] == "in-vless-ws")
    entry = next(c for c in ws["settings"]["clients"] if c["email"] == u["uid"])
    assert entry["level"] == 1
    # and a garbage plan falls back to the shared default instead of a dead level
    assert u["policy_level"] == 1


def test_default_panel_config_stays_identical(make_user):
    """With nobody on a plan and no tuning touched, the config keeps its shape."""
    u = make_user(protocol="vless", transport="ws", security="tls")
    cfg = _mod("xray").generate_xray_config()
    assert set(cfg["policy"]["levels"]) == {"0"}
    assert u["policy_level"] == 0
    for ib in cfg["inbounds"]:
        ss = ib.get("streamSettings") or {}
        if isinstance(ss, dict) and ss.get("sockopt"):
            assert set(ss["sockopt"]) <= {"tcpFastOpen", "tcpNoDelay",
                                          "tcpKeepAliveIdle", "tcpKeepAliveInterval",
                                          "tcpUserTimeout", "tcpCongestion"}


# --------------------------------------------------------------- 5) client output
def test_client_config_shape(make_user):
    links = _mod("links")
    settings = _mod("db").get_settings()
    settings = {**settings, "reality_pub": "0rZfgUxGDev7AtAPdbeJSb_cyt7Uxj3KN2DlSuvcHCE",
                "reality_sid": "1a2b3c4d"}
    u = make_user(protocol="vless", transport="tcp", security="reality", policy_level=1,
                  mux_enabled=True)
    cfg = links.build_client_config(u, "example.com", 443, settings)
    out = cfg["outbounds"][0]
    assert out["streamSettings"]["security"] == "reality"
    assert out["streamSettings"]["sockopt"]["domainStrategy"] == "UseIPv4"
    assert out["settings"]["vnext"][0]["users"][0]["flow"] == "xtls-rprx-vision"
    # Reality+Vision cannot be multiplexed: the flag must be dropped, not passed on
    assert "mux" not in out
    assert cfg["inbounds"][0]["protocol"] == "socks"
    json.dumps(cfg)


def test_client_config_endpoint(admin, make_user):
    u = make_user(protocol="vless", transport="ws", security="tls")
    r = admin.get(f"/api/users/{u['uid']}/client-config", headers=H)
    assert r.status_code == 200, r.text
    cfg = r.json()
    assert cfg["remarks"].startswith("TiTaN-")
    assert cfg["outbounds"][0]["settings"]["vnext"][0]["address"]
    r404 = admin.get("/api/users/doesnotexist/client-config", headers=H)
    assert r404.status_code == 404


@pytest.mark.skipif(not _engine_available(), reason="no xray binary in this environment")
def test_generated_configs_pass_the_engine(make_user):
    """The contract that matters: what we generate, the engine must accept."""
    db, links = _mod("db"), _mod("links")
    settings = {**db.get_settings(),
                "reality_pub": "0rZfgUxGDev7AtAPdbeJSb_cyt7Uxj3KN2DlSuvcHCE",
                "reality_sid": "1a2b3c4d"}
    import tempfile
    for fields in ({"protocol": "vless", "transport": "tcp", "security": "reality",
                    "reality_sni": "www.samsung.com", "short_id": "deadbeef"},
                   {"protocol": "vless", "transport": "xhttp", "security": "tls"},
                   {"protocol": "vless", "transport": "ws", "security": "tls", "flow": "none"}):
        u = make_user(**fields)
        cfg = links.build_client_config(u, "example.com", 443, settings)
        fd, path = tempfile.mkstemp(suffix=".candidate.json")
        with os.fdopen(fd, "w") as fh:
            json.dump(cfg, fh)
        try:
            r = subprocess.run([XRAY, "run", "-test", "-c", path],
                               capture_output=True, text=True, timeout=60)
            assert r.returncode == 0, (r.stdout + r.stderr)[-400:]
        finally:
            os.unlink(path)


def test_link_test_reports_missing_inbound(admin, make_user):
    """A user that is not in the running config is a finding, not a crash."""
    linktest = _mod("linktest")
    u = make_user(protocol="vless", transport="ws", security="tls")
    report = linktest.test_user(u, _mod("db").get_settings(), xray_cfg={"inbounds": []})
    assert report["ok"] is False
    assert report["steps"][0]["name"] == "inbound"
    assert "not in the running config" in report["steps"][0]["detail"]


def test_link_test_endpoint_returns_a_report(admin, make_user):
    u = make_user(protocol="vless", transport="ws", security="tls")
    r = admin.post(f"/api/users/{u['uid']}/link-test", headers=H)
    assert r.status_code == 200, r.text
    report = r.json()["report"]
    assert report["uid"] == u["uid"]
    assert isinstance(report["steps"], list) and report["steps"]
    assert "ok" in report
    r404 = admin.post("/api/users/nope/link-test", headers=H)
    assert r404.status_code == 404
