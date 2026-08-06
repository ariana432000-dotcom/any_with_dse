"""
Fetches content from JS-rendered sites (like stocknow.com.bd) without
needing manual DevTools access -- useful since DevTools/F12 is blocked on
managed/school Chrome profiles, but this runs as a standalone script on
your own machine, so that restriction doesn't apply here.

Two things this script does:

  1. capture_api_calls(url) -- opens the page in a real (headless) browser
     and logs every network response that looks like JSON. This is the
     programmatic equivalent of watching the Network tab in DevTools --
     run it once to find stocknow's internal API endpoint(s).

  2. scrape_rendered_news(url) -- fallback that doesn't need the API at
     all. Waits for the page to fully render, then returns the final HTML
     for you to parse with BeautifulSoup like any static page. Slower
     (spins up a real Chromium instance per call) but always works.

Install (run these locally, not in a restricted/managed environment):
    pip install playwright beautifulsoup4 --break-system-packages
    playwright install chromium
"""

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


async def capture_api_calls(url: str, wait_seconds: int = 8, out_file: str = "captured_requests.json"):
    """
    Opens `url` headlessly and records every XHR/fetch response with a
    JSON content-type. Prints each one so you can spot which URL is the
    news feed, and writes full detail to `out_file` for inspection.
    """
    captured = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        async def on_response(response):
            content_type = response.headers.get("content-type", "")
            if "json" not in content_type:
                return
            try:
                body = await response.json()
            except Exception:
                body = None
            captured.append({
                "url": response.url,
                "status": response.status,
                "method": response.request.method,
                "body_preview": json.dumps(body, ensure_ascii=False)[:2000] if body else None,
            })

        page.on("response", on_response)
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(wait_seconds * 1000)  # let lazy/late calls fire
        await browser.close()

    Path(out_file).write_text(json.dumps(captured, indent=2, ensure_ascii=False))
    print(f"Captured {len(captured)} JSON responses -> {out_file}\n")
    for item in captured:
        print(f"[{item['status']}] {item['method']} {item['url']}")
    return captured


async def scrape_rendered_news(url: str, wait_seconds: int = 5) -> str:
    """
    Fallback that skips the API hunt entirely: renders the page like a
    real browser, waits for content to load, then returns the final HTML.
    Feed this straight into BeautifulSoup(html, "html.parser").
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(wait_seconds * 1000)
        html = await page.content()
        await browser.close()
    return html


if __name__ == "__main__":
    # Run this first -- check captured_requests.json / the printed list
    # for a URL that returns the news items (look for keywords like
    # "news", "feed", "announcement" in the URL or body_preview).
    asyncio.run(capture_api_calls("https://stocknow.com.bd/news"))

    # Once you've found and confirmed the API endpoint, you don't need
    # Playwright at all going forward -- just hit that URL directly with
    # `requests`, which is much lighter than spinning up a browser per
    # call. Keep scrape_rendered_news() only as a fallback if the site
    # turns out to have no clean JSON API.
