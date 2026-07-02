#!/usr/bin/env python3
"""Client-side offline endurance legs (sovereign Wave 4, v1 — REAL browser).

Companion to ``apps/platform_runtime/tests/test_seven_day_offline_endurance.py``
(server rails). These are the legs a Django test cannot prove: that the
CLIENT survives a full browser restart and storage pressure. Runs the real
``static/js/rmc-offline-auth-vault.js`` in Chrome (selenium manages the
driver) against a persistent user-data-dir:

  LEG 1 — restart persistence: seal a capability with a PIN (PBKDF2 +
          AES-GCM), save it, KILL the browser, relaunch on the same
          profile — the sealed blob, the mint-throttle state, and a
          localStorage outbox row must all survive and the capability
          must decrypt with the right PIN (and refuse a wrong one).
  LEG 2 — storage pressure: fill localStorage to quota; saveSealed must
          not throw (quota is caught) and the pre-pressure sealed blob
          must still open.

Local evidence tool (Chrome required) — same posture as the axe harness,
NOT CI-wired. Exit 0 = both legs pass.
"""

from __future__ import annotations

import http.server
import socketserver
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIN = "482913"
CAPABILITY = "cap-token-seven-day-endurance-proof"


def build_page(workdir: Path) -> None:
    vault_js = (ROOT / "static/js/rmc-offline-auth-vault.js").read_text(encoding="utf-8")
    (workdir / "endurance.html").write_text(
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<title>offline endurance</title></head><body>"
        f"<script>{vault_js}</script></body></html>",
        encoding="utf-8",
    )


def new_driver(profile_dir: str):
    from selenium import webdriver

    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument(f"--user-data-dir={profile_dir}")
    opts.add_argument("--no-first-run")
    return webdriver.Chrome(options=opts)


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="rmc-endurance-"))
    build_page(workdir)
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(  # noqa: E731
        *a, directory=str(workdir), **kw
    )
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/endurance.html"
    profile = str(workdir / "chrome-profile")
    failures: list[str] = []

    # Session 1: seal + persist client state, then a REAL browser kill.
    driver = new_driver(profile)
    try:
        driver.get(url)
        sealed_kind = driver.execute_async_script(
            """
            const done = arguments[arguments.length - 1];
            (async () => {
              const sealed = await RMCOfflineAuthVault.sealCapability(
                  arguments[0], arguments[1]);
              RMCOfflineAuthVault.saveSealed(sealed);
              localStorage.setItem('rmc_offline_capability_mint_state',
                  JSON.stringify({minted_at: '2026-07-02T00:00:00Z',
                                  expires_at: '2026-07-09T00:00:00Z'}));
              localStorage.setItem('rmc_offline_outbox_probe',
                  JSON.stringify([{action_type: 'support.ticket',
                                   idempotency_key: 'endu-probe-1'}]));
              done(typeof sealed.cipher);
            })().catch((e) => done('ERR:' + e));
            """,
            PIN,
            CAPABILITY,
        )
        if sealed_kind != "object":
            failures.append(f"LEG1 seal failed: {sealed_kind}")
    finally:
        driver.quit()  # full browser shutdown = device/browser restart

    # Session 2: same profile — everything must have survived the restart.
    driver = new_driver(profile)
    try:
        driver.get(url)
        result = driver.execute_async_script(
            """
            const done = arguments[arguments.length - 1];
            (async () => {
              const out = {};
              const sealed = RMCOfflineAuthVault.loadSealed();
              out.sealed_survived = !!(sealed && sealed.cipher);
              out.mint_state_survived =
                  !!localStorage.getItem('rmc_offline_capability_mint_state');
              out.outbox_survived =
                  !!localStorage.getItem('rmc_offline_outbox_probe');
              try {
                out.opened = await RMCOfflineAuthVault.openCapability(
                    arguments[0], sealed);
              } catch (e) { out.opened = 'ERR:' + e.name; }
              try {
                await RMCOfflineAuthVault.openCapability('000000', sealed);
                out.wrong_pin = 'DECRYPTED (BAD)';
              } catch (e) { out.wrong_pin = 'refused:' + e.name; }
              // LEG 2 — storage pressure: fill to quota, then re-save.
              let quota_hit = false;
              const junk = 'x'.repeat(1024 * 1024);
              for (let i = 0; i < 20000; i++) {
                try { localStorage.setItem('pressure-' + i, junk); }
                catch (e) { quota_hit = true; break; }
              }
              out.quota_hit = quota_hit;
              try {
                RMCOfflineAuthVault.saveSealed(sealed);
                out.save_under_pressure = 'no-throw';
              } catch (e) { out.save_under_pressure = 'THREW:' + e.name; }
              try {
                out.opened_after_pressure = await RMCOfflineAuthVault
                    .openCapability(arguments[0], RMCOfflineAuthVault.loadSealed());
              } catch (e) { out.opened_after_pressure = 'ERR:' + e.name; }
              done(out);
            })().catch((e) => done({fatal: String(e)}));
            """,
            PIN,
        )
    finally:
        driver.quit()
        httpd.shutdown()

    checks = [
        ("sealed blob survives browser restart", result.get("sealed_survived") is True),
        ("mint-throttle state survives restart", result.get("mint_state_survived") is True),
        ("outbox row survives restart", result.get("outbox_survived") is True),
        ("capability decrypts with correct PIN", result.get("opened") == CAPABILITY),
        ("wrong PIN is refused", str(result.get("wrong_pin", "")).startswith("refused:")),
        ("storage quota was actually reached", result.get("quota_hit") is True),
        ("saveSealed never throws under pressure", result.get("save_under_pressure") == "no-throw"),
        ("capability still opens after pressure", result.get("opened_after_pressure") == CAPABILITY),
    ]
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
        if not ok:
            failures.append(label)

    if failures:
        print(f"verify_client_offline_endurance: FAIL ({len(failures)})", file=sys.stderr)
        return 1
    print("verify_client_offline_endurance: CLIENT_ENDURANCE_PASS (restart + pressure)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
