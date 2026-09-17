"""UI-wiring tests for the config builder.

The hard requirement for this feature was that it lands *inside* the existing
dashboard without disturbing it. That is not something a screenshot can prove,
so these tests check the three mechanical things that would actually break the
theme:

1. the new card is inside the configs section (not orphaned at the end of the
   body) and the new script is loaded after the bridge,
2. every element the modal already had is still there — the new fields are
   additions, never renames,
3. every CSS class the new UI uses exists in the panel's stylesheet, so the new
   markup cannot render as unstyled boxes next to the themed cards.
"""
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parent.parent
H = {"Origin": "http://testserver"}

CSS_CLASS = re.compile(r"\.([a-zA-Z][\w-]*)")


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def test_dashboard_loads_the_builder(admin):
    r = admin.get("/dashboard")
    assert r.status_code == 200, r.text
    html = r.text
    assert "/static/js/titan-config-builder.js" in html
    # after the bridge, so the DOM it augments already exists
    assert html.index("titan-bridge.js") < html.index("titan-config-builder.js")


def test_new_card_lives_inside_the_configs_section(admin):
    html = admin.get("/dashboard").text
    start = html.index('data-section="configs"')
    end = html.index('data-section="reports"')
    assert 'id="cb-workshop"' in html[start:end], "the workshop card must sit in the configs section"


def test_builder_assets_are_served(admin):
    r = admin.get("/static/js/titan-config-builder.js")
    assert r.status_code == 200
    js = r.text
    for endpoint in ("/api/recipes", "/client-config", "/link-test"):
        assert endpoint in js, f"the UI should talk to {endpoint}"
    assert "/api/settings" not in js, "the settings form was reverted; nothing may post to it"
    assert "mu_recipe" in js and "mu_flow" in js


def test_existing_modal_fields_survive():
    """The new fields are additions: nothing the panel already rendered moved."""
    js = _read("static/js/titan-bridge.js")
    for element_id in ("avPreview", "avPickBtn", "mu_avatar", "mu_name", "mu_note", "mu_node",
                       "mu_protocol", "mu_transport", "ssRow", "mu_ss", "mu_security", "mu_fp",
                       "mu_alpn", "mu_quota", "mu_expire", "mu_devices", "mu_requests", "mu_ips"):
        assert f'id="{element_id}"' in js, f"{element_id} disappeared from the user modal"
    for new_id in ("mu_recipe", "mu_flow", "mu_plan", "mu_rsni", "mu_mux"):
        assert f'id="{new_id}"' in js, f"{new_id} missing from the user modal"
    # ...and they are actually submitted
    for key in ("recipe:", "flow:", "reality_sni:", "policy_level:", "mux_enabled:"):
        assert key in js, f"{key} is rendered but never sent to the API"


def test_new_ui_sticks_to_the_existing_theme():
    """Class names used by the new markup must exist in the panel's own styles.

    The dashboard's design system lives in `<style>` blocks inside the template
    (dashboard.css belongs to the older login/setup screens), so both are
    collected here: if the new cards used a class nobody defines, they would
    render as bare boxes next to the themed ones — exactly the "panel broke"
    outcome this feature had to avoid.
    """
    html = _read("templates/dashboard.html")
    styles = "\n".join(re.findall(r"<style[^>]*>([\s\S]*?)</style>", html))
    styles += "\n" + _read("static/css/dashboard.css")
    known = set(CSS_CLASS.findall(styles))

    js = _read("static/js/titan-config-builder.js")
    used = set()
    token = re.compile(r"^[a-zA-Z][\w-]*$")
    for chunk in re.findall(r'class="([^"]+)"', js):
        # a chunk may contain JS concatenation (class="pill ' + (ok ? '' : 'warn')):
        # keep the tokens that can only be class names
        used.update(t for t in chunk.split() if token.match(t))
    assert used, "no class attributes found — the test would pass vacuously"
    unknown = sorted(c for c in used if c not in known)
    assert not unknown, f"classes not defined in the panel theme: {unknown}"


def test_the_engine_tuning_form_is_really_gone():
    """The panel settings form was reverted, so the UI must not offer the knobs.

    A field that posts a key the API now ignores is the worst kind of UI: it
    looks like it worked, and nothing happens.
    """
    sysm = __import__("app.config", fromlist=["app"])
    js = _read("static/js/titan-config-builder.js")
    for key in sysm.RETIRED_SETTINGS:
        assert key not in js, f"{key} is still editable in the UI but the API drops it"
        assert key not in sysm.DEFAULT_SETTINGS
    assert "cb-tuning" not in js and "cb-save" not in js


def test_dashboard_html_tags_balanced():
    """A stray tag in the template silently breaks the sidebar layout."""
    from html.parser import HTMLParser

    void = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
            "meta", "param", "source", "track", "wbr"}

    class Checker(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack = []
            self.problems = []

        def handle_starttag(self, tag, attrs):
            if tag not in void:
                self.stack.append(tag)

        def handle_endtag(self, tag):
            if tag in void:
                return
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    self.problems.append(f"unclosed before </{tag}>")
            else:
                self.problems.append(f"stray </{tag}>")

    html = _read("templates/dashboard.html")
    # script/style contents are not HTML; strip them so JS `</div>` strings
    # inside template literals cannot be mistaken for markup
    stripped = re.sub(r"<script[\s\S]*?</script>", "<script></script>", html)
    checker = Checker()
    checker.feed(stripped)
    assert not checker.problems, checker.problems[:5]
    assert not checker.stack, f"unclosed tags: {checker.stack[:5]}"
