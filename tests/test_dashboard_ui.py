"""The premium layer of the *served* dashboard.

`templates/dashboard.html` ships the shell and the styles, `static/js/titan-bridge.js`
fills it with real data — those two files are what the panel actually serves. These
tests pin the parts that were asked for: premium icon actions instead of buttons
carrying a Persian word (users / configs / subscriptions), a luxury server card per
node, and none of it breaking the render.
"""

import pathlib
import re
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
DASHBOARD = (REPO / "templates" / "dashboard.html").read_text(encoding="utf-8")
BRIDGE = (REPO / "static" / "js" / "titan-bridge.js").read_text(encoding="utf-8")

PERSIAN = re.compile(r"[\u0600-\u06FF]")


def _section(name: str) -> str:
    start = DASHBOARD.index(f'<section class="section-view" data-section="{name}">')
    end = DASHBOARD.find('<section class="section-view"', start + 10)
    return DASHBOARD[start:end if end > 0 else len(DASHBOARD)]


def _buttons(chunk: str) -> list[str]:
    return re.findall(r"<button\b.*?</button>", chunk, re.S)


def test_the_dashboard_ships_the_premium_layer():
    assert '<style id="titan-premium">' in DASHBOARD
    for cls in (".ico-btn", ".node-lux", ".nl-dial", ".nl-cap", "rg-fg", ".ping.good", ".sr-medal"):
        assert cls in DASHBOARD, f"{cls} is not styled in the served dashboard"


@pytest.mark.parametrize("section", ["users", "configs", "servers"])
def test_the_primary_action_is_a_premium_icon(section):
    """The bridge binds to `.section-btn.primary`, so keep it and drop the word."""
    chunk = _section(section)
    head = chunk[: chunk.index("</div></div>") + 12]
    primary = [b for b in _buttons(head) if "section-btn primary" in b]
    assert primary, f"{section}: no primary action left"
    assert "ico-btn" in primary[0], f"{section}: the primary action is not an icon button"
    label = re.sub(r"<[^>]+>", "", primary[0]).strip()
    assert label == "", f"{section}: the primary action still shows the text {label!r}"
    assert "<svg" in primary[0], f"{section}: the primary action has no icon"


@pytest.mark.parametrize("section", ["users", "configs", "subscriptions"])
def test_no_action_button_in_those_sections_carries_a_persian_word(section):
    for btn in _buttons(_section(section)):
        classes = re.search(r'class="([^"]*)"', btn)
        classes = classes.group(1) if classes else ""
        # Filter chips ("فعال", "منقضی") stay words on purpose: an icon cannot say them.
        if "section-btn" in classes and "ico-btn" not in classes:
            continue
        text = re.sub(r"<[^>]+>", "", btn).strip()
        assert not PERSIAN.search(text), f"{section}: {text!r} is still written on the button"


def test_the_bridge_renders_icon_actions_and_luxury_cards():
    assert "function icoBtn(" in BRIDGE and "function nodeCard(" in BRIDGE
    assert "class=\"mini-btn\"" not in BRIDGE, "a row or modal still renders a text button"
    # the two actions the new tables added: QR and on/off, in both sections
    for act in ('"data-act":"qr"', '"data-act":"power"', '"data-act":"configs"'):
        assert act in BRIDGE, f"{act} is not wired"
    assert "openSubConfigModal" in BRIDGE and "openNodeSetupModal" in BRIDGE
    assert "const ICONS" in BRIDGE and BRIDGE.count("'<path") + BRIDGE.count("'<rect") >= 10


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_bridge_renders_every_section():
    """Runs the real bridge against a stub DOM and a real API shape."""
    r = subprocess.run([shutil.which("node"), str(REPO / "scripts" / "bridge_smoke.js")],
                       cwd=str(REPO), capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin:/usr/local/bin", "TITAN_REPO": str(REPO)})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "bridge rendered every section" in r.stdout
