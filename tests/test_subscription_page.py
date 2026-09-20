"""The page behind a subscription link (/p/<token>).

The admin uploaded a design (profile, usage ring, subscription box, add-to-client
grid, config list, downloads, contact menu) and asked for exactly one thing to
happen to it: fill it with the real data of the link. These tests pin that — the
page is served as-is, the data comes from the panel, the profile set in the
dashboard is what shows up, and a switched-off link still opens but hands out
nothing. The subscription link itself carries the page too: a browser opening
/s/<token> sees it, while a client at the same address still gets its configs.
"""
import base64
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402

ORIGIN = {"Origin": "http://testserver"}
#: a person opening the link in a browser
BROWSER = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
           "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document",
           "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
#: a client importing a subscription
CLIENT = {"Accept": "*/*", "User-Agent": "v2rayNG/1.9.16"}


def _is_html(r) -> bool:
    return "text/html" in r.headers.get("content-type", "")


def _is_payload(r) -> bool:
    return r.headers.get("content-type", "").startswith("text/plain")
UID_ZERO = "00000000-0000-0000-0000-000000000001"


@pytest.fixture()
def panel(admin):
    created: list = []

    class _Panel:
        def __init__(self, client):
            self._c = client

        def __getattr__(self, item):
            method = getattr(self._c, item)
            if item not in ("get", "post", "patch", "delete"):
                return method

            def _wrapped(url, **kw):
                r = method(url, **kw)
                if item == "post" and url == "/api/subscriptions" and r.status_code == 200:
                    created.append(r.json()["subscription"]["id"])
                return r

            return _wrapped

    try:
        yield _Panel(admin)
    finally:
        for sub_id in created:
            db.delete_subscription(sub_id)


def _user(panel, name, **extra):
    body = {"name": f"{name}-{base64.b32encode(name.encode()).decode()[:4]}",
            "protocol": "vless", "transport": "ws", "security": "tls", **extra}
    r = panel.post("/api/users", json=body, headers=ORIGIN)
    assert r.status_code == 200, r.text
    return r.json()["user"]["uid"], body["name"]


def _link(panel, uids, name="pack", **extra):
    r = panel.post("/api/subscriptions", json={
        "name": name, "items": [{"uid": u, "configs": []} for u in uids], **extra},
        headers=ORIGIN)
    assert r.status_code == 200, r.text
    return r.json()["subscription"]


def test_the_page_is_served_with_the_uploaded_design_intact(panel):
    uid, _ = _user(panel, "page")
    sub = _link(panel, [uid])
    r = panel.get(f"/p/{sub['token']}")
    assert r.status_code == 200, r.text
    assert "text/html" in r.headers["content-type"]
    html = r.text
    # the design the admin uploaded: every section, id and behaviour still there
    for anchor in ('id="subLink"', 'id="addClients"', 'id="addTabs"', 'id="downloadTabs"',
                   'id="downloads"', 'id="latest"', 'id="allConfigs"', 'id="modal"',
                   'id="toast"', 'id="supportMenu"', 'id="supportButton"', 'id="langSwitch"',
                   'class="ring"', 'class="profile-halo"', 'class="crown"'):
        assert anchor in html, anchor
    # ... and the page is wired, not a mock-up
    assert "v2rayng://install-sub" in html and "v2box://install-sub" in html
    assert "hiddify://install-sub" in html and "streisand://import/" in html
    assert "/p/'+encodeURIComponent(state.token)+'/data" in html, "reads the panel"
    assert "کلاینت مورد نظر روی سیستم عامل شما نصب نیست" in html
    assert r.headers.get("cache-control", "").startswith("no-store")


def test_the_page_carries_the_contact_links_the_admin_gave(panel):
    uid, _ = _user(panel, "contact")
    sub = _link(panel, [uid])
    html = panel.get(f"/p/{sub['token']}").text
    assert "https://github.com/mr-rashidi" in html
    assert "https://t.me/Code_Shield" in html


def test_the_page_data_is_the_real_subscription(panel):
    ali, ali_name = _user(panel, "pageali", expire_days=7, quota_gb=50)
    sara, _ = _user(panel, "pagesara", expire_days=30, quota_gb=50)
    sub = _link(panel, [ali, sara], name="پک خانواده")
    d = panel.get(f"/p/{sub['token']}/data").json()

    assert d["profile"]["name"] == "پک خانواده"
    assert d["subscription"]["enabled"] is True and d["subscription"]["serves_links"] is True
    assert d["subscription"]["url"].endswith("/s/" + sub["token"])
    assert d["subscription"]["page_url"].endswith("/p/" + sub["token"])
    assert d["counts"]["users"] == 2
    assert d["counts"]["configs"] == len(d["configs"]) > 0
    for c in d["configs"]:
        assert c["link"].startswith(("vless://", "vmess://", "trojan://", "ss://"))
        assert c["name"].startswith("TiTaN-") and c["name"][-3] == "-"
        assert c["target"] in ("panel", "node")
        assert "city" in c and "country_code" in c
    # the numbers are the users' numbers, summed
    u = d["usage"]
    assert u["total_bytes"] == sum(int(db.get_user(x)["quota_bytes"] or 0) for x in (ali, sara))
    assert u["used_bytes"] == sum(int(db.get_user(x)["used_up"] or 0)
                                  + int(db.get_user(x)["used_down"] or 0) for x in (ali, sara))
    assert u["active"] is True and u["expire_at"] > 0 and u["days_left"] is not None
    assert ali_name.split("-")[0] in {v["name"].split("-")[0] for v in d["users"]}


def test_the_profile_set_in_the_dashboard_is_the_one_shown(panel):
    uid, _ = _user(panel, "prof", avatar="gallery:g1")
    sub = _link(panel, [uid])
    # no picture on the link yet: the user's own one stands in
    d = panel.get(f"/p/{sub['token']}/data").json()
    assert d["profile"]["kind"] == "user" and d["profile"]["avatar"] == f"/s/{sub['token']}/avatar"
    r = panel.get(f"/s/{sub['token']}/avatar")
    assert r.status_code == 200 and r.content, "the picture is served without a session"

    # set on the link: it wins, and it is what the API reports back
    upd = panel.patch(f"/api/subscriptions/{sub['id']}",
                      json={"avatar": "gallery:g1", "plan": "Ultra 100GB"},
                      headers=ORIGIN).json()["subscription"]
    assert upd["avatar"] == "gallery:g1" and upd["plan"] == "Ultra 100GB"
    assert upd["page_url"].endswith("/p/" + sub["token"])
    assert upd["avatar_url"].endswith("g1.svg")
    d2 = panel.get(f"/p/{sub['token']}/data").json()
    assert d2["profile"]["kind"] == "subscription" and d2["plan"] == "Ultra 100GB"


def test_a_switched_off_link_opens_but_serves_nothing(panel):
    uid, _ = _user(panel, "off")
    sub = _link(panel, [uid])
    panel.patch(f"/api/subscriptions/{sub['id']}", json={"enabled": False}, headers=ORIGIN)

    # the client face stays exactly as it was: 403, no payload
    assert panel.get(f"/s/{sub['token']}").status_code == 403
    assert panel.get(f"/s/{sub['token']}/json").status_code == 403

    # the human page still opens and tells the truth
    assert panel.get(f"/p/{sub['token']}").status_code == 200
    d = panel.get(f"/p/{sub['token']}/data").json()
    assert d["subscription"]["enabled"] is False
    assert d["subscription"]["serves_links"] is False
    assert d["configs"] == [] and d["subscription"]["url"] == ""
    assert d["profile"]["name"], "the profile is still shown when the link is off"


def test_the_raw_subscription_is_unchanged_for_clients(panel):
    uid, _ = _user(panel, "raw")
    sub = _link(panel, [uid])
    body = panel.get(f"/s/{sub['token']}").text
    lines = [ln for ln in base64.b64decode(body).decode().splitlines()
             if ln.strip() and UID_ZERO not in ln]
    assert lines, "the client still gets the base64 payload"
    j = panel.get(f"/s/{sub['token']}/json").json()
    assert j["name"] and j["users"] and j["links"], "the debug view keeps its old fields"
    assert j["profile"]["name"] and j["usage"]["total_bytes"] >= 0
    assert j["subscription"]["url"].endswith("/s/" + sub["token"])


def test_an_unknown_token_is_a_404_everywhere(panel):
    for path in ("/p/nope", "/p/nope/data", "/s/nope/avatar"):
        assert panel.get(path).status_code == 404, path

def test_the_subscription_link_itself_opens_the_panel_in_a_browser(panel):
    """One address, two faces — and never the wrong one."""
    uid, _ = _user(panel, "both")
    sub = _link(panel, [uid])

    r = panel.get(f"/s/{sub['token']}", headers=BROWSER)
    assert r.status_code == 200 and _is_html(r)
    assert 'id="addClients"' in r.text and 'id="subLink"' in r.text
    assert r.headers.get("cache-control", "").startswith("no-store")

    # the very same address still hands the client its configs
    raw = panel.get(f"/s/{sub['token']}", headers=CLIENT)
    assert raw.status_code == 200 and _is_payload(raw)
    assert base64.b64decode(raw.text)

    # ?raw=1 is always the payload, whatever asks
    assert _is_payload(panel.get(f"/s/{sub['token']}?raw=1", headers=BROWSER))

    # the debug and base64 faces never turn into html
    assert panel.get(f"/s/{sub['token']}/json", headers=BROWSER).json()["counts"]["users"] == 1
    assert _is_payload(panel.get(f"/s/{sub['token']}/base64", headers=BROWSER))

    # a switched-off link: the person still gets the page, the client gets 403
    panel.patch(f"/api/subscriptions/{sub['id']}", json={"enabled": False}, headers=ORIGIN)
    assert panel.get(f"/s/{sub['token']}", headers=BROWSER).status_code == 200
    assert panel.get(f"/s/{sub['token']}", headers=CLIENT).status_code == 403
    assert panel.get(f"/s/{sub['token']}?raw=1", headers=BROWSER).status_code == 403

def test_the_builder_knows_each_users_picture(panel):
    """The subscriptions section sets pictures exactly like users/configs do."""
    uid, _ = _user(panel, "catpic", avatar="gallery:g4")
    cat = panel.get("/api/subscriptions/catalog").json()
    row = next(u for u in cat["users"] if u["uid"] == uid)
    assert row["avatar"] == "gallery:g4", "the catalog carries the key"
    assert row["avatar_url"].endswith("g4.svg"), "and a URL the picker can show"

    # changing it from the builder is the plain users endpoint
    r = panel.patch(f"/api/users/{uid}", json={"avatar": "gallery:g2"}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    cat2 = panel.get("/api/subscriptions/catalog").json()
    row2 = next(u for u in cat2["users"] if u["uid"] == uid)
    assert row2["avatar"] == "gallery:g2" and row2["avatar_url"].endswith("g2.svg")

    # the link itself carries a picture too, and it wins over the user's on the page
    sub = _link(panel, [uid], avatar="gallery:g6", plan="Pro")
    link_pic = panel.get(f"/s/{sub['token']}/avatar")
    assert link_pic.status_code == 200 and link_pic.content
    d = panel.get(f"/p/{sub['token']}/data").json()
    assert d["subscription"]["url"].endswith("/s/" + sub["token"])
    assert d["profile"]["kind"] == "subscription" and d["plan"] == "Pro"

    # ... and the row can take it away again: back to the user's own face
    panel.patch(f"/api/subscriptions/{sub['id']}", json={"avatar": ""}, headers=ORIGIN)
    d2 = panel.get(f"/p/{sub['token']}/data").json()
    assert d2["profile"]["kind"] == "user"

def test_every_config_row_carries_a_flag_and_the_name_of_its_place(panel):
    """The config list shows the server's flag and where it lands, by name."""
    from app.main import _entry_place

    # a node carries the place a config lands in; the panel carries its own
    node_place = _entry_place({"target": "node", "node": {"name": "Dubai-Edge", "city": "Dubai",
                                                          "country_code": "AE", "flag": "🇦🇪"}})
    assert node_place == {"place": "Dubai-Edge", "city": "Dubai",
                          "country_code": "ae", "flag": "🇦🇪"}
    local_place = _entry_place({"target": "panel"})
    assert local_place["country_code"] and local_place["place"]

    uid, _ = _user(panel, "flagcity")
    sub = _link(panel, [uid])
    d = panel.get(f"/p/{sub['token']}/data").json()
    for cfg in d["configs"]:
        assert cfg["country_code"], "the page is told which country the config is in"
        assert cfg["flag"] or cfg["country_code"], "so it can draw that country's flag"
        assert cfg["city"] or cfg["place"], "and where the config really lands"
        assert cfg["name"].startswith("TiTaN-")

    # the page turns that into a flag image plus a named location, in both languages
    html = panel.get(f"/p/{sub['token']}").text
    assert "function flagUri" in html and "function locationLabel" in html
    assert "CC_NAMES" in html and "آمریکا" in html and "United States" in html
    assert "flagUri(c[0])" in html, "the row draws the flag of that country"
    assert "esc(place)" in html and "esc(c[2])" in html, "and prints the place, not the code"
    # the design's own flag artwork is reused for the countries it ships
    assert '"us":"data:image/' in html and '"nl":"data:image/' in html and '"de":"data:image/' in html


def test_the_page_never_paints_a_light_layer_over_the_uploaded_background(panel):
    """The design's artwork is the background — nothing may wash it out."""
    uid, _ = _user(panel, "bg")
    sub = _link(panel, [uid])
    html = panel.get(f"/p/{sub['token']}").text
    body_rule = html[html.index("body{"):html.index("body{") + 400]
    assert "linear-gradient(180deg,rgba(2,3,12,.08)" in body_rule, "the design's own veil, untouched"
    # the artwork is declared as what it is: a JPEG (it was labelled image/png,
    # which strict browsers refuse — the art vanished and only the veil stayed)
    assert 'url("data:image/jpeg;base64,/9j/' in html
    assert 'url("data:image/png;base64,/9j/' not in html
    # and the page's base colour is the design's own --bg, never a white wash
    assert "getPropertyValue('--bg')" in html and "document.body.style.backgroundColor" in html
    assert "background:#fff" not in html.lower().replace(" ", "")
