#!/usr/bin/env python3
"""Marketing palette-scope proof (axe finding (a), 2026-07-02).

Runs the REAL ``static/js/theme-preference-bootstrap.js`` in headless
Chrome under a forced dark preference and asserts:

  1. On ``<html data-surface="marketing">`` the body NEVER receives a
     ``portal-backend-*`` palette class (the leak that put dark text
     tokens on the cream editorial canvas — 1.21:1, axe-confirmed).
  2. On a portal-shaped control page the palette IS still applied
     (``portal-backend-dark``) — the fix must not de-theme the backend.

Local evidence tool (Chrome required), same posture as the axe harness.
"""

from __future__ import annotations

import http.server
import socketserver
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build_pages(workdir: Path) -> None:
    js = (ROOT / "static/js/theme-preference-bootstrap.js").read_text(encoding="utf-8")
    shell = (
        "<!doctype html><html lang=\"en\"{attrs}><head><meta charset=\"utf-8\">"
        "<title>palette probe</title>"
        "<script>localStorage.setItem('rmc-theme-preference','dark');"
        "localStorage.setItem('theme','dark');</script>"
        "<script>{js}</script></head><body class=\"{body}\"></body></html>"
    )
    (workdir / "marketing.html").write_text(
        shell.format(attrs=' data-surface="marketing"', js=js, body="marketing-surface"),
        encoding="utf-8",
    )
    (workdir / "portal.html").write_text(
        shell.format(attrs="", js=js, body="portal-body-with-layout"),
        encoding="utf-8",
    )


def main() -> int:
    from selenium import webdriver

    workdir = Path(tempfile.mkdtemp(prefix="rmc-palette-"))
    build_pages(workdir)
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(  # noqa: E731
        *a, directory=str(workdir), **kw
    )
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    driver = webdriver.Chrome(options=opts)
    failures: list[str] = []
    try:
        driver.get(f"{base}/marketing.html")
        mkt = driver.execute_script(
            "return {cls: document.body.className,"
            " leaked: [...document.body.classList].some(c => c.startsWith('portal-backend-'))};"
        )
        if mkt["leaked"]:
            failures.append(f"marketing body still gets backend palette: {mkt['cls']}")
        print(f"  [{'FAIL' if mkt['leaked'] else 'PASS'}] marketing surface stays palette-free ({mkt['cls']!r})")

        driver.get(f"{base}/portal.html")
        portal = driver.execute_script(
            "return document.body.classList.contains('portal-backend-dark');"
        )
        if not portal:
            failures.append("portal control page no longer receives portal-backend-dark")
        print(f"  [{'PASS' if portal else 'FAIL'}] portal control still themed dark")
    finally:
        driver.quit()
        httpd.shutdown()

    if failures:
        print("verify_marketing_palette_scope: FAIL", file=sys.stderr)
        return 1
    print("verify_marketing_palette_scope: MARKETING_PALETTE_SCOPE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
