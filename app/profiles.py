"""Config recipes (سناریوهای آماده) — the "one click, one good config" layer.

Why this exists: both Marzban (raw JSON) and 3X-UI (~40 technical inbound fields)
dump the protocol knowledge on the admin. A named recipe encodes the combination
that is known to work for Iranian networks, and every field it sets can still be
overridden afterwards in the advanced part of the form.

Everything here is *data*, not config generation: a recipe fills fields on the
user payload (protocol/transport/security/flow/…) and the existing generator does
the rest. That keeps one single source of truth for how a config is built.
"""
from __future__ import annotations

# Order matters: this is the order shown in the UI.
RECIPES: list[dict] = [
    {
        "id": "resilient",
        "name": "مقاوم (پیشنهاد اصلی)",
        "emoji": "🛡",
        "tagline": "VLESS + Reality روی TCP — بدون گواهی، بدون دامنه، مقاوم‌ترین حالت امروز",
        "note": "برای همراه اول/ایرانسل/رایتل. روی «پورت خام» (تنها TCP proxy شما) بهترین انتخاب است.",
        "fields": {
            "protocol": "vless",
            "transport": "tcp",
            "security": "reality",
            "fingerprint": "chrome",
            "alpn": "",
            "flow": "xtls-rprx-vision",
            "fragment_enabled": True,
            "fragment_length": "10-30",
            "fragment_interval": "10-20",
            "mux_enabled": False,
        },
    },
    {
        "id": "cdn",
        "name": "CDN (دامنه‌ی خودت)",
        "emoji": "🌐",
        "tagline": "VLESS + XHTTP روی TLS — پشت Cloudflare یا هر دامنه‌ای",
        "note": "وقتی IP سرور تمیز نیست یا مسیر مستقیم بسته است. XHTTP جانشین رسمی WS/gRPC است.",
        "fields": {
            "protocol": "vless",
            "transport": "xhttp",
            "security": "tls",
            "fingerprint": "chrome",
            "alpn": "h2,http/1.1",
            "flow": "",
            "xhttp_mode": "packet-up",
            "mux_enabled": False,
        },
    },
    {
        "id": "compat",
        "name": "سازگاری حداکثری",
        "emoji": "🔀",
        "tagline": "VLESS + WebSocket روی TLS — همه‌ی کلاینت‌ها، همه‌ی شبکه‌ها",
        "note": "برای کاربری که نمی‌دانی با چه اپی وصل می‌شود؛ کم‌ترین ریسک ناسازگاری.",
        "fields": {
            "protocol": "vless",
            "transport": "ws",
            "security": "tls",
            "fingerprint": "chrome",
            "alpn": "http/1.1",
            "flow": "",
            "fragment_enabled": True,
            "mux_enabled": True,
        },
    },
    {
        "id": "gaming",
        "name": "گیم و تماس صوتی",
        "emoji": "🎮",
        "tagline": "Reality بدون mux — کم‌ترین تأخیر ممکن",
        "note": "mux عمداً خاموش است (روی ترافیک سنگین و گیم تأخیر می‌سازد).",
        "fields": {
            "protocol": "vless",
            "transport": "tcp",
            "security": "reality",
            "fingerprint": "chrome",
            "alpn": "",
            "flow": "xtls-rprx-vision",
            "mux_enabled": False,
            "policy_level": 1,
        },
    },
    {
        "id": "telegram",
        "name": "سبک برای تلگرام",
        "emoji": "✈️",
        "tagline": "VLESS + HTTPUpgrade روی TLS — سبک و کم‌مصرف",
        "note": "برای کاربرانی که فقط تلگرام می‌خواهند؛ حجم کم و اتصال پایدار.",
        "fields": {
            "protocol": "vless",
            "transport": "httpupgrade",
            "security": "tls",
            "fingerprint": "chrome",
            "alpn": "http/1.1",
            "flow": "",
            "mux_enabled": True,
        },
    },
]

# Per-user field names a recipe may fill. Anything else is ignored, so a recipe
# can never smuggle in a value the API would not accept anyway.
ALLOWED_FIELDS = {
    "protocol", "transport", "security", "fingerprint", "alpn", "flow",
    "mux_enabled", "policy_level", "short_id", "reality_sni",
    "spider_x", "ss_method",
}

# Knobs that live in panel *settings*, not on a user: fragmentation is applied by
# the client, and the panel advertises it in every link, so it cannot be
# per-user. A recipe that needs them turns them on for the panel and says so in
# its response, instead of silently ignoring half of what it promised.
SETTINGS_FIELDS = {
    "fragment_enabled", "fragment_length", "fragment_interval", "xhttp_mode",
}

BY_ID = {r["id"]: r for r in RECIPES}


def list_recipes() -> list[dict]:
    """Public catalogue for the UI (copy so callers cannot mutate the table)."""
    return [
        {"id": r["id"], "name": r["name"], "emoji": r["emoji"],
         "tagline": r["tagline"], "note": r["note"], "fields": dict(r["fields"])}
        for r in RECIPES
    ]


def get_recipe(recipe_id: str) -> dict | None:
    r = BY_ID.get((recipe_id or "").strip())
    return dict(r) if r else None


def apply_recipe(payload: dict, recipe_id: str | None = None) -> tuple[dict, str | None]:
    """Return (payload, recipe_id) with the recipe's fields filled in.

    Explicit values in ``payload`` always win, so the admin can pick a recipe and
    then tweak one field. Unknown recipe ids are ignored (never an error: an old
    client must not break because a recipe was renamed).
    """
    out = dict(payload or {})
    rid = (recipe_id or out.pop("recipe", "") or "").strip()
    recipe = get_recipe(rid)
    if not recipe:
        return out, None
    for key, value in recipe["fields"].items():
        if key not in ALLOWED_FIELDS:
            continue
        if key not in out or out.get(key) in (None, ""):
            out[key] = value
    return out, recipe["id"]


def split_fields(fields: dict) -> tuple[dict, dict]:
    """(user fields, panel settings) for one recipe, so the API can route them."""
    user, settings = {}, {}
    for key, value in (fields or {}).items():
        if key in ALLOWED_FIELDS:
            user[key] = value
        elif key in SETTINGS_FIELDS:
            settings[key] = value
    return user, settings


def suggest_recipe(*, transport: str = "", security: str = "") -> str | None:
    """Best-effort match of an existing user back to a recipe (for the UI badge)."""
    t, s = (transport or "").lower(), (security or "").lower()
    for r in RECIPES:
        f = r["fields"]
        if f.get("transport") == t and f.get("security") == s:
            return r["id"]
    return None
