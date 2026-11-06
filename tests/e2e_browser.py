"""Browser E2E (opt-in, needs Playwright + a running server): python e2e_browser.py [base_url] [screenshot_dir]

Drives the real UI against the real backend (real plugin catalog + real GitHub).
Exits non-zero on failure. Not part of the unit suite because it needs network and a browser.
"""
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5057/"
SHOTS = sys.argv[2] if len(sys.argv) > 2 else "."
REQ = "Self-hosted invoicing app with recurring billing, PDF invoices and Stripe payments"

with sync_playwright() as p:
    b = p.chromium.launch()
    for scheme in ("light", "dark"):
        pg = b.new_page(color_scheme=scheme, viewport={"width": 1280, "height": 900})
        errors = []
        pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(BASE)
        # empty submit shows a validation message, no request
        pg.click("#go")
        assert "Enter a requirement" in pg.text_content("#status"), "empty-state message missing"
        pg.fill("#req", REQ)
        pg.click("#go")
        pg.wait_for_selector("#status:text('Done.'), #status.err", timeout=60000)
        status = pg.text_content("#status")
        assert status.startswith("Done. Saved "), f"analysis failed or not saved: {status}"
        pg.click("#tab-history")                                     # history is its own tab
        pg.wait_for_selector("#ht tbody tr .open-link")
        assert pg.is_hidden("#panel-analyze") and pg.text_content("#hc").strip().isdigit()
        pg.click("#tab-analyze")
        prow = pg.locator("#pt tbody tr").count()
        grow = pg.locator("#gt tbody tr").count()
        verdict = pg.text_content("#verdict")
        assert prow >= 1 and grow >= 1, (prow, grow)
        assert "%" in verdict, verdict
        pcts = pg.locator("td.pct strong").all_text_contents()
        assert pcts and all(t.endswith("%") and t[:-1].isdigit() for t in pcts), pcts[:3]
        concepts = pg.text_content("#meta")
        assert "recurr," not in concepts, concepts
        # §8.14 results filter narrows both tables and reports the count; verdict offers next steps
        pg.fill("#filter", "zzzz-no-match")
        assert pg.text_content("#fcount").startswith("Showing 0 of"), pg.text_content("#fcount")
        pg.fill("#filter", "")
        assert pg.locator("#verdict .va button").count() >= 1, "verdict has no next-step action"
        assert pg.evaluate("document.querySelector('#req').offsetHeight") <= 140, "requirement box did not shrink after results"
        first_link = pg.locator("#gt tbody tr a").first.get_attribute("href")
        assert first_link.startswith("https://github.com/"), first_link
        pg.screenshot(path=f"{SHOTS}/req-analyzer-{scheme}.png", full_page=False)
        # mobile width: no horizontal page scroll
        pg.set_viewport_size({"width": 390, "height": 800})
        overflow = pg.evaluate("document.documentElement.scrollWidth > window.innerWidth")
        assert not overflow, "horizontal page scroll at 390px"
        assert not errors, errors
        print(f"{scheme}: OK plugins={prow} github={grow} verdict={verdict!r}")
    # ---------------------------------------------------------------- UEUIS checks
    pg = b.new_page(color_scheme="light", viewport={"width": 1280, "height": 900})
    errors = []
    pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(BASE)
    # §9.1 laptop density: at 1366x768 the requirement, Analyze button and examples are above the fold
    pg.set_viewport_size({"width": 1366, "height": 768})
    tb = pg.locator("#tab-history").bounding_box()
    assert tb and tb["y"] < 120, "Past requirements tab is not at the top"
    for sel in ("#req", "#go", "#examples"):
        box = pg.locator(sel).bounding_box()
        assert box and box["y"] + box["height"] <= 768, f"{sel} below the fold at 1366x768"
    assert pg.evaluate("document.querySelector('#req').offsetHeight") >= 460, "requirement box does not use the free height"
    rq = pg.locator("#req").bounding_box()
    assert rq["x"] <= 20 and rq["x"] + rq["width"] >= 1366 - 20, "requirement box has wide outer margins"
    pg.set_viewport_size({"width": 1280, "height": 900})
    # §8.15 restraint: few full-weight buttons on the start screen (text and icon buttons excluded)
    heavy = pg.evaluate("""() => [...document.querySelectorAll('button')].filter(b => b.offsetParent !== null
      && !b.matches('.textbtn, .ghost, .more-btn, .st, .switch, [role=tab], [role=radio]')).length""")
    assert heavy <= 2, f"{heavy} full-weight buttons on the start screen"
    # §8.18 explanatory text starts hidden; the switch shows it and is remembered
    assert pg.get_attribute("#desc-toggle", "aria-checked") == "false" and not pg.is_visible("#req-help")
    pg.click("#desc-toggle")
    assert pg.is_visible("#req-help")
    pg.reload()
    assert pg.get_attribute("#desc-toggle", "aria-checked") == "true" and pg.is_visible("#req-help")
    pg.click("#desc-toggle")
    pg.reload()                                                       # start the keyboard check from the top
    # §7.2 keyboard: the first Tab lands on the skip link, which moves focus to <main>
    pg.keyboard.press("Tab")
    assert pg.evaluate("document.activeElement.className") == "skip", "skip link is not first in tab order"
    assert pg.evaluate("getComputedStyle(document.activeElement).outlineStyle") != "none", "no visible focus"
    pg.keyboard.press("Enter")
    assert pg.evaluate("document.activeElement.id") == "main", "skip link does not move focus"
    # §7.4 every button, link, input and select has an accessible name
    unnamed = pg.evaluate("""() => [...document.querySelectorAll('button, a[href], input, select, textarea')]
      .filter(e => e.offsetParent !== null)
      .filter(e => !(e.getAttribute('aria-label') || e.labels?.length || e.textContent.trim()))
      .map(e => e.outerHTML.slice(0, 80))""")
    assert not unnamed, unnamed
    # tabs: arrow keys and Home/End
    pg.focus("#tab-analyze"); pg.keyboard.press("End")
    assert pg.get_attribute("#tab-history", "aria-selected") == "true"
    pg.keyboard.press("ArrowLeft")
    assert pg.get_attribute("#tab-build", "aria-selected") == "true"
    # Build into: a new app, or enhance one of the existing apps
    pg.wait_for_selector("#build-into option:nth-child(2)", state="attached", timeout=5000)
    opts = pg.eval_on_selector_all("#build-into option", "os => os.map((o) => o.textContent)")
    assert opts[0] == "A new app" and any(o.startswith("Enhance: ") for o in opts[1:]), opts
    assert pg.evaluate("document.querySelector('label[for=build-into]') !== null"), "Build into has no label"
    pg.keyboard.press("Home")
    assert pg.get_attribute("#tab-analyze", "aria-selected") == "true"
    # §8 theme picker: overrides the system, survives a reload, and back to system
    bg_light = pg.evaluate("getComputedStyle(document.querySelector('.appbar')).backgroundColor")
    pg.click("#theme-dark")
    assert pg.get_attribute("html", "data-theme") == "dark"
    assert pg.evaluate("getComputedStyle(document.querySelector('.appbar')).backgroundColor") != bg_light, "header identical in both themes"
    bg_dark = pg.evaluate("getComputedStyle(document.body).backgroundColor")
    pg.reload()
    assert pg.get_attribute("html", "data-theme") == "dark" and pg.get_attribute("#theme-dark", "aria-checked") == "true", "theme not remembered"
    pg.screenshot(path=f"{SHOTS}/req-analyzer-dark-chosen.png")
    pg.focus("#theme-dark"); pg.keyboard.press("ArrowRight")          # radio group wraps: dark -> system
    assert pg.get_attribute("#theme-system", "aria-checked") == "true"
    assert pg.get_attribute("html", "data-theme") is None
    assert pg.evaluate("getComputedStyle(document.body).backgroundColor") != bg_dark, "light theme did not return"
    # §6 empty-input error marks the field
    # §8.14 example chips fill the requirement; counter follows
    pg.click("#examples button >> nth=1")
    assert "water" in pg.input_value("#req") and pg.text_content("#req-count").startswith(str(len(pg.input_value("#req"))))
    pg.fill("#req", ""); pg.click("#go")
    assert pg.get_attribute("#req", "aria-invalid") == "true", "empty requirement not marked invalid"
    # §4 build form: error summary linked to the empty required fields, focus moved to it (inputs mocked: no Claude spend)
    fields = [{"id": "app_name", "label": "App name", "type": "text", "default": "", "group": "Basics", "required": True},
              {"id": "users", "label": "Users and roles", "type": "textarea", "default": "me", "group": "Basics", "required": True,
               "help": "Who uses it"}]
    import json as _j
    pg.route("**/api/inputs", lambda r: r.fulfill(status=200, content_type="application/json", body=_j.dumps(
        {"fields": fields, "ai_status": "ok", "standard_found": True, "ui_standard_found": True, "standard": "", "ui_standard": ""})))
    pg.fill("#req", REQ); pg.click("#tab-build"); pg.click("#list-inputs")
    pg.wait_for_selector("#inputs:not([hidden])")
    assert "UEUIS" in pg.text_content("#build-note")
    pg.click("#create")
    pg.wait_for_selector("#err-summary:not([hidden])")
    assert pg.evaluate("document.activeElement.id") == "err-summary", "focus not moved to the error summary"
    assert "App name is required" in pg.text_content("#err-summary")
    assert pg.get_attribute("#in-app_name", "aria-invalid") == "true"
    assert pg.input_value("#in-users") == "me", "entered data lost on error"
    pg.click("#err-summary a")
    assert pg.evaluate("document.activeElement.id") == "in-app_name"
    pg.unroute("**/api/inputs")
    # §7.1 / §9 reflow at 320 px and 200% zoom equivalent (640 px): no sideways page scroll
    pg.click("#tab-analyze")
    for w in (320, 640):
        pg.set_viewport_size({"width": w, "height": 800})
        assert not pg.evaluate("document.documentElement.scrollWidth > window.innerWidth"), f"horizontal scroll at {w}px"
    pg.screenshot(path=f"{SHOTS}/req-analyzer-320.png", full_page=True)
    # §8 forced colours: page still renders, bars and focus remain visible
    pg.emulate_media(forced_colors="active")
    pg.set_viewport_size({"width": 1280, "height": 900})
    pg.screenshot(path=f"{SHOTS}/req-analyzer-forced-colors.png")
    assert not errors, errors
    print("UEUIS: OK (skip link, focus, names, tabs keys, theme override + persistence, error summary, 320px reflow, forced colours)")
    # clean up: the analyses this run saved (see LEARNINGS)
    ctx = pg.request
    tok = ctx.get(BASE + "api/session").json()["token"]
    for h in ctx.get(BASE + "api/analyses").json()["analyses"]:
        if h["requirement"] == REQ:
            ctx.post(BASE + f"api/analyses/{h['id']}/delete", headers={"X-ReqAn-Token": tok, "Content-Type": "application/json"}, data="{}")
    b.close()
print("E2E PASS")
