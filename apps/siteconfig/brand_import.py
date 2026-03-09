"""
Website / competitor brand import — fetch URL and extract logo, colors, site name.
Non-negotiable: Strategy Report Phase 2; HOW_WE_SCOPE_WEBSITE_IMPORT.
"""
import logging
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10
USER_AGENT = "RunMyCampus-BrandImport/1.0"


class MetaParser(HTMLParser):
    """Extract meta theme-color, og:image, og:title, and title."""

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.theme_color = None
        self.og_image = None
        self.og_title = None
        self.title = None

    def handle_starttag(self, tag, attrs):
        if tag != "meta":
            return
        d = dict(attrs)
        name = (d.get("name") or d.get("property") or "").strip().lower()
        content = (d.get("content") or "").strip()
        if not content:
            return
        if name in ("theme-color", "msapplication-tilecolor"):
            if not self.theme_color:
                self.theme_color = content
        elif name == "og:image":
            self.og_image = content
        elif name == "og:title":
            self.og_title = content

    def handle_endtag(self, tag):
        pass

    def handle_data(self, data):
        pass

    def set_title(self, title: str):
        if title and not self.og_title:
            self.og_title = title.strip()


def fetch_and_parse_brand_url(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """
    Fetch URL and parse HTML for theme-color, og:image, og:title/title.
    Returns dict with primary_color, logo_url, site_name, and optional error.
    """
    result = {"primary_color": None, "logo_url": None, "site_name": None, "error": None}
    if not url or not url.strip():
        result["error"] = "URL is required"
        return result
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            result["error"] = "Invalid URL"
            return result
    except Exception as e:
        result["error"] = "Invalid URL"
        return result

    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        resp.raise_for_status()
        html = resp.text
        base = f"{parsed.scheme}://{parsed.netloc}"
    except requests.RequestException as e:
        logger.warning("Brand import fetch failed: %s", e)
        result["error"] = "Could not fetch URL. Check the address and try again."
        return result
    except Exception as e:
        logger.exception("Brand import unexpected error")
        result["error"] = "Import failed. Use manual upload instead."
        return result

    try:
        parser = MetaParser(base)
        parser.feed(html[: 500 * 1024])
        if parser.theme_color:
            result["primary_color"] = _normalize_hex_color(parser.theme_color)
        if parser.og_image:
            result["logo_url"] = urljoin(base, parser.og_image)
        if parser.og_title:
            result["site_name"] = parser.og_title[: 200] or None
        if not result["site_name"]:
            m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I | re.DOTALL)
            if m:
                result["site_name"] = (m.group(1).strip() or "")[:200] or None
    except Exception as e:
        logger.warning("Brand import parse failed: %s", e)
        result["error"] = "Could not read page. Use manual upload instead."

    return result


def _normalize_hex_color(s: str) -> str | None:
    """Return #RRGGBB or None."""
    s = (s or "").strip()
    m = re.match(r"#?([0-9A-Fa-f]{6})\b", s)
    if m:
        return "#" + m.group(1).lower()
    m = re.match(r"#?([0-9A-Fa-f]{3})\b", s)
    if m:
        r, g, b = m.group(1)
        return "#" + r + r + g + g + b + b
    return None
