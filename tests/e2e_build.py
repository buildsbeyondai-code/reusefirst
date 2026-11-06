"""REAL build E2E (opt-in; spends Claude usage): python e2e_build.py <base_url> <screenshot_dir> <requirement>
Drives the Build tab: list inputs (real Claude), submit, wait for the real headless build to finish, launch it."""
import sys
import time

from playwright.sync_api import sync_playwright

BASE, SHOTS, REQ = sys.argv[1], sys.argv[2], sys.argv[3]
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 1000})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(BASE)
    pg.fill("#req", REQ)
    pg.click("#tab-build")
    pg.click("#list-inputs")
    pg.wait_for_selector("#inputs:not([hidden])", timeout=300000)
    print("inputs:", pg.text_content("#bstatus"), flush=True)
    assert pg.locator(".checklist input:checked").count() >= 1, "no reuse candidate pre-ticked"
    pg.fill("#in-budget_usd", "4")
    pg.fill("#in-max_minutes", "30")
    pg.screenshot(path=f"{SHOTS}/build-inputs.png", full_page=True)
    pg.click("#create")
    pg.wait_for_selector("#job:not([hidden]), #bstatus.err", timeout=30000)
    assert pg.locator("#job").is_visible(), "build did not start: " + pg.text_content("#bstatus")
    t0 = time.time()
    while time.time() - t0 < 35 * 60:
        st = pg.text_content("#job-head")
        if any(s in st for s in ("succeeded", "failed", "timed-out", "cancelled", "interrupted")):
            break
        time.sleep(10)
    print("status:", pg.text_content("#job-head"), "|", pg.text_content("#job-meta"), flush=True)
    pg.screenshot(path=f"{SHOTS}/build-done.png", full_page=True)
    assert "succeeded" in pg.text_content("#job-head")
    assert not pg.locator("#report-wrap").is_hidden(), "no completion report shown"
    if pg.locator("#launch").is_visible():
        pg.click("#launch")
        pg.wait_for_function("document.querySelector('#launch-out').textContent.length > 0", timeout=15000)
        print("launch:", pg.text_content("#launch-out"))
    assert not errors, errors
    b.close()
print("BUILD E2E PASS")
