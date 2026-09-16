"""REALITY (VLESS) key management.

REALITY needs a stable x25519 keypair per panel. We generate it once with the
Xray binary (``xray x25519``) and persist it in the database so connection links
stay valid across restarts. The private key lives in `meta` (never exposed to the
frontend); the public key + short id are stored as settings so the link builder
can read them.

Keeping those keys valid across a *redeploy* therefore depends on the database
surviving it - i.e. on a persistent Volume (`/app/data` on Railway). Without one,
every deploy generates a new keypair and previously published `pbk` values die.
"""
import logging
import secrets
import subprocess

from . import config, db

log = logging.getLogger("titan.reality")


def _xray_x25519() -> tuple[str, str] | None:
    """Return (private_key, public_key) from `xray x25519`, or None.

    Xray changed this output between releases:

        old (<= 24.x)   "Private key: <b64>"  /  "Public key: <b64>"
        new (>= 25.x)   "PrivateKey: <b64>"   /  "Password (PublicKey): <b64>"
                                              (+ optional "Hash32: <b64>")

    The strict match on the old spelling silently returned None against current
    Xray builds, which meant no keypair was ever generated: every Reality link
    was emitted with an empty ``pbk=`` and the Reality inbound was skipped
    entirely. Parse by label instead of by exact string, keep the old spelling
    working, and derive the public key from the private one as a fallback.
    """
    import re as _re

    def run(args):
        try:
            return subprocess.run([config.XRAY_BIN, *args], capture_output=True,
                                  text=True, timeout=20).stdout or ""
        except Exception as e:  # noqa: BLE001
            log.warning("xray %s failed: %s", " ".join(args), e)
            return ""

    priv = pub = ""
    for line in run(["x25519"]).splitlines():
        if ":" not in line:
            continue
        label, _, value = line.partition(":")
        label = label.strip().lower().replace(" ", "").replace("(", "").replace(")", "")
        value = value.strip()
        if len(value) < 40 or not _re.fullmatch(r"[A-Za-z0-9_+/=-]{40,}", value):
            continue  # not a key (e.g. the "Choose one Authentication" header)
        if label.startswith("private"):
            priv = value
        elif label.startswith("public") or "publickey" in label or label.startswith("password"):
            pub = value

    if priv and not pub:
        # `xray x25519 -i <private>` prints the matching public key.
        for line in run(["x25519", "-i", priv]).splitlines():
            low = line.strip().lower().replace(" ", "").replace("(", "").replace(")", "")
            if low.startswith("public") or "publickey" in low:
                cand = line.split(":", 1)[-1].strip()
                if len(cand) >= 40:
                    pub = cand
                    break

    if priv and pub:
        return priv, pub
    return None


def ensure_reality_keys() -> dict | None:
    """Return {priv, pub, sid, sni, dest} for the panel, generating once.

    Returns None when no Xray binary is available (dev/mock mode) and no keys
    have been generated yet — Reality inbounds are then skipped.
    """
    priv = db.get_meta("reality_priv")
    if priv:
        pub = db.get_meta("reality_pub") or ""
        if not pub:
            # self-heal: a stored private key without its public half (an older
            # broken version, or a node that synced an empty pub) would keep
            # publishing links with an empty `pbk=`. Re-derive it.
            derived = _xray_x25519()
            if derived and derived[0] == priv:
                pub = derived[1]
            elif derived is None:
                pub = ""
            if pub:
                db.set_meta("reality_pub", pub)
                db.set_setting("reality_pub", pub)
                log.warning("Reality public key was missing — derived it from the stored private key")
        return {
            "priv": priv,
            "pub": pub,
            "sid": db.get_meta("reality_sid") or "",
            "sni": config.REALITY_SNI,
            "dest": config.REALITY_DEST,
        }
    keys = _xray_x25519()
    if not keys:
        return None
    priv, pub = keys
    sid = secrets.token_hex(4)
    db.set_meta("reality_priv", priv)
    db.set_meta("reality_pub", pub)
    db.set_meta("reality_sid", sid)
    # public values → settings, so get_settings() carries them to link builder
    db.set_setting("reality_pub", pub)
    db.set_setting("reality_sid", sid)
    db.set_setting("reality_sni", config.REALITY_SNI)
    db.set_setting("reality_dest", config.REALITY_DEST)
    log.info("Reality keypair generated (sni=%s dest=%s)", config.REALITY_SNI, config.REALITY_DEST)
    return {"priv": priv, "pub": pub, "sid": sid, "sni": config.REALITY_SNI, "dest": config.REALITY_DEST}


def apply_reality_config(data: dict) -> None:
    """Node side: accept the main panel's reality keypair + short id."""
    if not data or not data.get("priv"):
        return
    if not str(data["priv"]).strip():
        log.warning("reality payload carried an empty private key — ignored")
        return
    db.set_meta("reality_priv", data["priv"])
    db.set_meta("reality_pub", data.get("pub", ""))
    db.set_meta("reality_sid", data.get("sid", ""))
    db.set_setting("reality_pub", data.get("pub", ""))
    db.set_setting("reality_sid", data.get("sid", ""))
    db.set_setting("reality_sni", config.REALITY_SNI)
    db.set_setting("reality_dest", config.REALITY_DEST)
