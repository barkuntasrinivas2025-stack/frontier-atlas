from __future__ import annotations

from bs4 import BeautifulSoup


ANTI_BOT_MARKERS = (
    "captcha",
    "cf-chl-",
    "cloudflare",
    "datadome",
    "verify you are human",
    "access denied",
)


def is_anti_bot_page(html: str) -> bool:
    text = (html or "").lower()
    return any(marker in text for marker in ANTI_BOT_MARKERS)


def extract_fulltext(html: str) -> str:
    soup = BeautifulSoup(html or "", "lxml")

    for tag in soup(["script", "style", "nav", "footer", "noscript"]):
        tag.decompose()

    main = soup.find("article") or soup.find("main") or soup.body or soup
    return " ".join(main.stripped_strings)


def needs_js_render(html: str) -> bool:
    if not html:
        return True

    text = extract_fulltext(html)

    # A very small shell with scripts but little readable content is a
    # reasonable signal that client-side rendering may be required.
    soup = BeautifulSoup(html, "lxml")
    scripts = len(soup.find_all("script"))

    return len(text) < 500 and scripts >= 3


async def fetch_compliant_page(http, url: str):
    """
    Fetch a page without attempting to defeat access controls.

    If the publisher presents Cloudflare/DataDome/CAPTCHA protection,
    return the response as unavailable rather than attempting a bypass.

    JS-heavy pages are identified for an optional Playwright/browser
    implementation. The browser implementation must still respect the
    publisher's access controls and must never solve or bypass CAPTCHAs.
    """
    status, body, headers = await http.get(url, allow_redirects=True)

    if status != 200:
        return status, body, headers, False

    if is_anti_bot_page(body):
        return status, body, headers, True

    return status, body, headers, needs_js_render(body)
