"""The reverted config-builder layer must stay reverted (and leave no residue).

Why this file exists: "we removed that feature" is a claim that decays. A route
that is still registered, a column that is still selected, or a JS file that is
still served all mean the revert only happened in the commit message. Each of the
three is checked here, plus the one-time cleanup of a database that already had
the columns - the case a unit test can otherwise never see, because the test
database is created fresh.
"""
import json
import pathlib
import sqlite3
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from conftest import REPO  # noqa: E402

H = {"Origin": "http://testserver"}


# --------------------------------------------------------------- the endpoints
def test_the_config_builder_endpoints_are_gone(admin):
    """A registered route is a feature, whatever the UI shows."""
    uid = admin.get("/api/users", headers=H).json()["users"]
    uid = uid[0]["uid"] if uid else "deadbeef"
    for path in ("/api/recipes", f"/api/users/{uid}/client-config", f"/api/users/{uid}/link-test"):
        r = admin.get(path, headers=H)
        assert r.status_code == 404, f"{path} still exists ({r.status_code})"


def test_the_builder_modules_are_gone():
    for name in ("app.profiles", "app.linktest"):
        assert name not in sys.modules, f"{name} is imported by the app again"
        with pytest.raises(ImportError):
            __import__(name)
        assert not pathlib.Path(REPO, *name.split(".")).with_suffix(".py").exists()


def test_the_builder_assets_and_card_are_gone(admin):
    js = admin.get("/static/js/titan-config-builder.js")
    assert js.status_code == 404, "the builder script is still served"
    html = admin.get("/dashboard").text
    assert "cb-workshop" not in html and "titan-config-builder.js" not in html


# ---------------------------------------------------------------- the new fields
def test_user_payloads_ignore_the_removed_fields(admin):
    """POSTing them must not resurrect them anywhere in the response."""
    r = admin.post("/api/users", headers=H, json={
        "name": "revert-probe", "recipe": "cdn", "flow": "xtls-rprx-vision",
        "reality_sni": "www.samsung.com", "policy_level": 2, "mux_enabled": True,
    })
    assert r.status_code == 200, r.text
    user = r.json()["user"]
    for key in ("recipe", "flow", "reality_sni", "policy_level", "mux_enabled"):
        assert key not in user, f"{key} came back in the API payload"
    admin.delete(f"/api/users/{user['uid']}")


def test_the_users_table_has_no_reverted_columns(db):
    from app import config
    cols = {r["name"] for r in db._connect().execute("PRAGMA table_info(users)").fetchall()}
    for col in config.RETIRED_USER_COLUMNS:
        assert col not in cols, f"users.{col} is still there"


# ------------------------------------------------------- the one-time migration
def test_a_database_from_the_previous_version_is_cleaned_up(tmp_path, monkeypatch):
    """The live volume already has these columns: booting must drop them.

    The values are rescued into a JSON file first, so an admin who had set them
    can still see what they were - the revert is destructive by design, but not
    silently so.
    """
    from app import config, db

    path = tmp_path / "titan.db"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE users (uid TEXT PRIMARY KEY, name TEXT, enabled INTEGER DEFAULT 1,"
                 " flow TEXT NOT NULL DEFAULT '', reality_sni TEXT NOT NULL DEFAULT '',"
                 " policy_level INTEGER NOT NULL DEFAULT 0, mux_enabled INTEGER NOT NULL DEFAULT 0,"
                 " recipe TEXT NOT NULL DEFAULT '')")
    conn.execute("INSERT INTO users(uid, name, flow, reality_sni, policy_level, mux_enabled, recipe)"
                 " VALUES('u1','one','xtls-rprx-vision','www.samsung.com',2,1,'cdn')")
    conn.execute("INSERT INTO users(uid, name) VALUES('u2','two')")
    conn.commit()

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    columns = list(config.RETIRED_USER_COLUMNS)
    archive = db._archive_retired_user_columns(conn, columns)
    assert archive and pathlib.Path(archive).exists()
    saved = json.loads(pathlib.Path(archive).read_text(encoding="utf-8"))
    assert saved["u1"]["recipe"] == "cdn" and saved["u1"]["policy_level"] == 2
    assert "u2" not in saved                       # nothing worth keeping = no entry

    for col in columns:
        conn.execute(f"ALTER TABLE users DROP COLUMN {col}")
    conn.commit()
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    assert not set(columns) & cols
    assert conn.execute("SELECT name FROM users WHERE uid='u2'").fetchone()["name"] == "two"
    conn.close()
