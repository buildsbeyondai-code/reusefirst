"""UEUIS checks that need no browser: theme token contrast (§7.1, §8) and page structure (§7)."""
import re
import unittest
from pathlib import Path

from tests import helpers  # noqa: F401  (import path)

STATIC = Path(__file__).resolve().parent.parent / "plugins/req-analyzer/app/reqanalyzer/static"
CSS = (STATIC / "app.css").read_text()
HTML = (STATIC / "index.html").read_text()


def tokens(block: str) -> dict:
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", block))


def themes() -> dict:
    light = tokens(CSS.split("@media (prefers-color-scheme: dark)")[0])
    sys_dark = tokens(re.search(r":root:not\(\[data-theme=\"light\"\]\) \{(.*?)\}", CSS, re.S).group(1))
    forced_dark = tokens(re.search(r":root\[data-theme=\"dark\"\] \{(.*?)\}", CSS, re.S).group(1))
    return {"light": light, "dark": {**light, **sys_dark}, "dark (chosen)": {**light, **forced_dark}}


def lum(h: str) -> float:
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class ThemeTokens(unittest.TestCase):
    def test_dark_theme_is_the_same_whether_chosen_or_from_the_system(self):
        t = themes()
        self.assertEqual(t["dark"], t["dark (chosen)"])

    def test_text_contrast_at_least_4_5_in_every_theme(self):
        roles = ("text", "muted", "accent", "success", "warning", "danger", "info", "violet", "hi", "mid", "lo", "warn")
        for name, t in themes().items():
            for fg in roles:
                for bg in ("bg", "panel", "sunken"):
                    with self.subTest(theme=name, fg=fg, bg=bg):
                        self.assertGreaterEqual(contrast(t[fg], t[bg]), 4.5)
            # chips and banners: each role's text on its own subtle tint (UEUIS §8.2)
            for role in ("success", "warning", "danger", "info", "violet", "accent"):
                with self.subTest(theme=name, chip=role):
                    self.assertGreaterEqual(contrast(t[role], t[role + "-subtle"]), 4.5)
            pairs = [("accent-text", "accent"), ("accent-text", "accent-hover"), ("warn", "warn-bg"), ("text", "accent-subtle"),
                     ("on-header", "header-bg"), ("on-header-muted", "header-bg")]
            for fg, bg in pairs:
                with self.subTest(theme=name, pair=(fg, bg)):
                    self.assertGreaterEqual(contrast(t[fg], t[bg]), 4.5)

    def test_control_borders_and_focus_at_least_3_to_1(self):
        for name, t in themes().items():
            pairs = [(fg, bg) for fg in ("ctl", "accent") for bg in ("bg", "panel", "sunken")]       # controls, focus
            pairs += [(fg, bg) for fg in ("hi", "info", "mid", "lo", "text")                       # bullet value + target
                      for bg in ("bar", "q1", "q2", "q3", "q4")]
            for fg, bg in pairs:
                with self.subTest(theme=name, fg=fg, bg=bg):
                    self.assertGreaterEqual(contrast(t[fg], t[bg]), 3.0)


class EnterprisePalette(unittest.TestCase):
    """UEUIS §8.16-§8.17: solid, restrained palettes; one primary; categorical colours for identity only."""

    def test_five_categorical_colours_per_theme(self):
        for name, t in themes().items():
            for i in range(1, 6):
                with self.subTest(theme=name, c=i):
                    self.assertGreaterEqual(contrast(t[f"c{i}"], t["panel"]), 4.5)
                    self.assertGreaterEqual(contrast(t[f"c{i}"], t[f"c{i}-subtle"]), 4.5)

    def test_primary_is_not_generic_blue_and_palettes_differ(self):
        import colorsys
        t = themes()
        def hue(h):
            r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
            return colorsys.rgb_to_hls(r, g, b)[0] * 360
        for name in ("light", "dark"):
            self.assertFalse(200 <= hue(t[name]["accent"]) <= 260, (name, t[name]["accent"]))
        self.assertNotEqual([t["light"][f"c{i}"] for i in range(1, 6)], [t["dark"][f"c{i}"] for i in range(1, 6)])
        # categorical colours never equal a status colour (status colours carry meaning only)
        for name, tt in t.items():
            status = {tt[k] for k in ("success", "warning", "danger", "info")}
            self.assertFalse({tt[f"c{i}"] for i in range(1, 6)} & status, name)


class EnterpriseRestraint(unittest.TestCase):
    """UEUIS §8.17: no decorative gradients, gradient text, glows, glass or coloured shadows."""

    def test_only_data_gradients(self):
        rules = re.findall(r"([^{}]+)\{([^{}]*gradient\([^{}]*)\}", CSS)
        offenders = [sel.strip() for sel, body in rules if ".bullet" not in sel]
        self.assertEqual(offenders, [], "decorative gradients are not allowed")

    def test_no_gradient_text_glass_or_coloured_shadows(self):
        for bad in ("background-clip: text", "-webkit-text-fill-color", "backdrop-filter", "--glow", "--title-", "--btn-"):
            self.assertNotIn(bad, CSS)
        for shadow in re.findall(r"--e[12]: ([^;]+);", CSS):
            for r, g, b in re.findall(r"rgba\((\d+), (\d+), (\d+)", shadow):
                self.assertLessEqual(max(int(r), int(g), int(b)) - min(int(r), int(g), int(b)), 12, "shadows must be neutral")

    def test_solid_header_differs_between_themes(self):
        t = themes()
        self.assertGreater(lum(t["light"]["header-bg"]) - lum(t["dark"]["header-bg"]), 0.6)
        self.assertIn(".appbar { background: var(--header-bg);", CSS)


class Layout(unittest.TestCase):
    """v1.9: a roomy requirement box; history is its own tab; no step tracker duplicating the numbered tabs."""

    def test_layout(self):
        self.assertIn('<textarea id="req" rows="8"', HTML)
        self.assertIn("textarea#req { height: max(200px, calc(100vh - 270px)); }", CSS)  # fills the free height
        self.assertIn(".card.lead { margin-top: var(--s2); padding: 0; border: 0;", CSS)   # no outer frame
        self.assertIn("html.has-results textarea#req", CSS)                             # yields room to results
        self.assertNotIn('id="starter"', HTML)                                          # examples live in the card
        self.assertNotIn('id="stepper"', HTML)
        self.assertNotIn('id="kw"', HTML)                               # no keywords box: the requirement is enough
        self.assertLess(HTML.index('id="panel-history"'), HTML.index('id="panel-build"'))
        # the tabs (including "Past requirements") sit at the top, directly under the header, above the requirement box
        self.assertLess(HTML.index("</header>"), HTML.index('id="navbar"'))
        self.assertLess(HTML.index('id="navbar"'), HTML.index('class="card lead"'))
        self.assertIn("3 · Past requirements", HTML)
        self.assertNotIn('id="ht"', HTML[HTML.index('id="panel-analyze"'):HTML.index('id="panel-history"')])


class Polish(unittest.TestCase):
    """UEUIS §8.14: the professional-polish checklist is implemented."""

    def test_polish_features(self):
        js = (STATIC / "app.js").read_text()
        for needle in ('role="radiogroup"', 'id="navbar"', 'id="examples"', 'id="req-count"', 'id="filter"',
                       'rel="icon"', 'id="foot-meta"', "<kbd>"):
            self.assertIn(needle, HTML)
        for needle in ("function setBusy(", "function applyFilter(", "function clampCell(", "function labelCells(",
                       "function compact(", "All systems ready", "document.title", "requestSubmit()", 'class: "va"'):
            self.assertIn(needle, js)
        for needle in ("@media print", ".navbar", "td[data-label]::before", ".clamp", ".spin"):
            self.assertIn(needle, CSS)

    def test_button_restraint(self):
        """UEUIS §8.15: one primary per view; tertiary actions are text or icon buttons; no duplicate actions."""
        js = (STATIC / "app.js").read_text()
        self.assertNotIn('id="to-build"', HTML)                 # duplicate of the verdict's "Build reusing it"
        self.assertIn('class="seg icons"', HTML)               # theme switcher is icon-only
        self.assertIn('class: "ghost copy"', js)
        self.assertIn('class: "ghost danger-ic"', js)
        self.assertIn('class: "textbtn open-link"', js)
        self.assertNotIn('"Hide details"', js)                 # the status summary is its own toggle
        self.assertEqual(HTML.count('class="textbtn"'), 3)      # examples are text links, not chips

    def test_descriptions_switch(self):
        """UEUIS §8.18: a remembered switch hides explanatory text, never data or errors."""
        js = (STATIC / "app.js").read_text()
        theme_js = (STATIC / "theme.js").read_text()
        self.assertIn('id="desc-toggle" role="switch" aria-checked="false"', HTML)
        self.assertIn('|| "hide"', theme_js)                            # explanatory text starts hidden
        self.assertIn("function setDesc(", js)
        self.assertIn('classList.add("hide-desc")', theme_js)          # applied before first paint
        self.assertIn("html.hide-desc .hint:not(.err)", CSS)            # errors stay visible
        hidden = re.search(r"(html\.hide-desc[^{]+)\{", CSS).group(1)
        for never in (".value", ".verdict", ".err", "td", ".tile"):
            self.assertNotIn(never + ",", hidden)

    def test_no_interactive_nesting(self):
        js = (STATIC / "app.js").read_text()
        self.assertNotRegex(js, r'el\("a"[^;]*el\("button"')


class PageStructure(unittest.TestCase):
    def test_landmarks_skip_link_language_and_theme_picker(self):
        for needle in ('<html lang="en">', 'class="skip" href="#main"', '<main id="main"', "<header", "<footer>",
                       'id="theme"', '<script src="/theme.js"></script>', 'role="tablist"'):
            self.assertIn(needle, HTML)
        self.assertLess(HTML.index("/theme.js"), HTML.index("/app.css"), "theme must be set before the CSS paints")

    def test_every_input_has_a_label(self):
        for iid in re.findall(r'<(?:input|textarea|select)[^>]*\bid="([^"]+)"', HTML):
            with self.subTest(id=iid):
                self.assertTrue(f'for="{iid}"' in HTML or re.search(rf'<label[^>]*>\s*<input id="{iid}"', HTML))

    def test_scrollable_regions_are_keyboard_reachable_and_named(self):
        for tag in re.findall(r'<div class="(?:tw|events-wrap)"[^>]*>', HTML):
            with self.subTest(tag=tag):
                self.assertIn('tabindex="0"', tag)
                self.assertIn("aria-labelledby", tag)

    def test_no_inline_styles_csp_and_reduced_motion_and_forced_colours(self):
        self.assertNotIn("style=", HTML)
        self.assertIn("prefers-reduced-motion", CSS)
        self.assertIn("forced-colors", CSS)
        self.assertNotRegex(CSS, r"(?m)^\s*body \{[^}]*font: 1[0-3]px")  # body text >= 14px (UEUIS §8.4 dense UI)


if __name__ == "__main__":
    unittest.main()


class VisualFormats(unittest.TestCase):
    """UEUIS §8.7: the standard formats exist, so the UI is not flat."""

    def test_formats_present(self):
        js = (STATIC / "app.js").read_text()
        for needle in ('class="appbar"', 'id="i-logo"', 'class="tiles"', 'class="tabs"', "footer"):
            self.assertIn(needle, HTML)
        for needle in ("function band(", "function tile(", "function statusChip(", "function chip(", '"empty"'):
            self.assertIn(needle, js)
        self.assertIn("tabular-nums", CSS)

    def test_rich_patterns_from_8_11(self):
        js = (STATIC / "app.js").read_text()
        for needle in ('id="statusbar"', 'id="dist"', 'id="toasts"', 'id="tab-history"', 'id="panel-history"'):
            self.assertIn(needle, HTML)
        for needle in ("function bullet(", "function renderDist(", "function skeleton(", "function toast(",
                       "function loadStatus(", "function whenCell(", "function copyBtn(", 'const TABS = ["analyze", "build", "history"]'):
            self.assertIn(needle, js)
        # one score mapping everywhere: the verdict bands
        self.assertIn('p >= 70 ? "p-hi" : p >= 50 ? "p-info" : p >= 30 ? "p-mid" : "p-lo"', js)

    def test_own_identity_not_sysperf(self):
        # UEUIS §8.13: patterns may be shared, the look may not (SysPerf uses a glass card shell and a score ring)
        self.assertNotIn("backdrop-filter", CSS)
        self.assertNotIn("conic-gradient", CSS)
        self.assertIn('"Slate & Teal"', CSS)
        self.assertIn('"Graphite & Mint"', CSS)

    def test_no_colour_literals_outside_token_blocks(self):
        body = re.sub(r":root[^{]*\{.*?\}", "", CSS, flags=re.S)
        body = re.sub(r"@media \(prefers-color-scheme: dark\) \{.*?\}\s*\}", "", body, flags=re.S)
        self.assertEqual(re.findall(r"#[0-9a-fA-F]{6}\b", body), [])
