"""Playwright smoke test for the Match Center (desktop + mobile). Skipped when Playwright or Chromium is missing.

Install: pip install -e .[e2e] && python -m playwright install chromium
"""
import socket
import threading
import time

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")

from tacticlens.api.app import app  # noqa: E402

VIEWPORTS = {"desktop": {"width": 1366, "height": 900}, "mobile": {"width": 390, "height": 844}}


@pytest.fixture(scope="module")
def base_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # browser binary not installed
            pytest.skip(f"chromium unavailable: {exc}")
        yield b
        b.close()


@pytest.mark.parametrize("vp", list(VIEWPORTS))
def test_match_center(browser, base_url, vp):
    page = browser.new_page(viewport=VIEWPORTS[vp])
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base_url + "#GM01")
    page.wait_for_selector("body[data-ready=true]", timeout=15000)
    expect = sync_api.expect

    expect(page.locator("#home-name")).to_have_text("Northbridge United")
    expect(page.locator("#timeline .mk")).to_have_count(11)
    expect(page.locator("#wp-chart svg path")).to_have_count(3)
    assert page.locator("#cards .card").count() > 0

    # moment -> seek; replay over SSE moves the clock
    page.locator("#timeline .mk").nth(4).click()
    page.select_option("#speed", "256")
    page.click("#play")
    start = page.locator("#clock").inner_text()
    expect(page.locator("#clock")).not_to_have_text(start, timeout=8000)
    page.click("#play")

    # Hindi persona: translation shown beside English
    page.select_option("#persona-form select[name=lang]", "hi")
    expect(page.locator("#cards .bi").first).to_be_visible()
    expect(page.locator("#cards [lang=hi]").first).to_be_visible()

    # what-if (precomputed for this goal)
    page.click("#tab-whatif")
    page.locator("#timeline .mk[data-id='GM01-M05']").click()
    expect(page.locator("#whatif .wi svg")).to_be_visible()

    # overlays JSON
    page.click("#tab-overlays")
    expect(page.locator("#cues-json")).to_contain_text("lower_third")

    # agent trace: kill the explainer -> retries then template fallback
    page.click("#tab-trace")
    page.check("#kill")
    page.click("#rerun")
    expect(page.locator("#trace li.warn").first).to_be_visible()
    expect(page.locator("#trace")).to_contain_text("template fallback")

    assert page.evaluate("document.documentElement.scrollWidth") <= VIEWPORTS[vp]["width"] + 1
    assert not errors, errors
    page.close()
