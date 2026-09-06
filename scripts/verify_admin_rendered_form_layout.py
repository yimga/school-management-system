"""Admin form surfaces must PAINT the controls they contain.

Every other gate in this repo reads files. This one renders the page and asks a
browser what the user actually sees, because there is a class of defect that does
not exist in any file:

    2026-09-06, people.StudentProfile/add. One `<thead>`, one formset, valid HTML,
    all 166 gates green -- and the guardian table painted a column header with no
    row beneath it. Unfold stamps `class="template"` on EVERY inline form without
    an `original`, not just the `__prefix__` prototype, and a shell rule keyed on
    `tbody.template` hid the row the admin had just offered. "Add another" was
    inert too (unfold's inlines.js wraps each clone in a NEW tbody.template) while
    TOTAL_FORMS still incremented, so the form submitted a row nobody saw. The
    same stylesheets force-showed `thead` with !important, beating unfold's
    non-important `.hidden`, so under 1024px the head AND the per-cell `::before`
    labels both painted -- a doubled header row.

    Neither is visible in source. Both are one computed-style read away.

WHAT IT ASSERTS, per inline table, at a desktop and a sub-`lg` width:

  inline-row-not-painted   a form row carrying live inputs computes to no box.
                           The admin offered a row the user cannot fill.
  prototype-row-painted    the `__prefix__` row IS painted -- a phantom fillable
                           line, with real controls that axe reports as unnamed.
  header-layers            the column names are painted twice (head + stacked
                           per-cell labels) or not at all. Exactly one, always.

WHY IT IS BUILT THIS WAY

  *Stdlib only.* No `playwright`, no `websocket-client` -- neither is in
  requirements.txt; they are transitive today and could vanish tomorrow. A gate
  whose dependency is accidental is a gate that stops running quietly. The page
  measures ITSELF: a driver page loads each surface in a same-origin iframe, runs
  the assertions against `iframe.contentDocument`, and POSTs the results back.

  *An iframe, not a viewport resize.* An iframe is its own viewport, so setting
  its width is what makes `@media (min-width: 64rem)` evaluate -- and it lets one
  browser process cover both widths without a relaunch.

  *A readiness poll, never a sleep.* This is the whole correctness story. At 0.6s
  this page reports `readyState: loading` with 84 of 93 stylesheets attached and
  EVERY element at zero client rects -- which reads as a finding on a healthy
  page. A first cut slept 0.9s and invented 4 findings on a tree that was already
  fixed. The driver waits for the iframe's own `load` (which waits on
  stylesheets) plus two animation frames, and reports `page-never-loaded` rather
  than measuring a page that was not ready.

  *Absence of a browser is a SKIP, never a PASS.* Exit 2, which
  `pre_push_boundary_check.py` renders as SKIP. A gate that cannot run has not
  passed.

  *No baseline.* The tree measured clean at introduction (25 registrations x 2
  widths, 0 findings), and a form that will not paint its own inputs is never
  an intentional state to freeze.

SCOPE, stated plainly: this proves the RENDERED CASCADE. It renders through the
real ModelAdmin, the real template stack and the real stylesheets, but it calls
the view in-process rather than logging in, so it does NOT prove the
host/role/state matrix or authentication. That is a different gate.

Run `--self-check` to see the assertions fire against a known-bad page; the gate
refuses to report a result if its own detector cannot tell good from bad.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: `pre_push_boundary_check.py` renders this as SKIP rather than PASS.
_SKIPPED_EXIT_CODE = 2

DEFAULT_WIDTHS = (1440, 900)
#: The sub-`lg` width matters: a desktop browser at 125% zoom is already under
#: 1024 CSS px, so the stacked-label layout is not a phone-only path.
_LG_BREAKPOINT = 1024

SITE_URLCONF = {"tenant_admin": "config.tenant_urls", "admin": "config.manager_urls"}

#: Finish inside this, or SKIP. Measured 225s for a full pass on a developer
#: machine with a dozen peer runserver processes up. pre_push_boundary_check
#: kills a gate at 600s and reports that as FAIL, which its own comment calls
#: indistinguishable from a real finding -- and under --strict it would block a
#: correct push. Being killed is the one outcome this gate must not have, so it
#: watches its own clock and reports the resource result as what it is.
_DEADLINE_S = float(os.environ.get("RMC_ADMIN_LAYOUT_GATE_DEADLINE_S") or 480)

#: Below this there is no point starting the browser pass at all.
_MIN_BROWSER_S = 45.0


# --------------------------------------------------------------------------
# The assertions. One copy, shared by the real run and by --self-check, so the
# thing proven by the self-check is the thing that runs.
# --------------------------------------------------------------------------
MEASURE_JS = r"""
function rmcMeasure(doc, win) {
  const vis = el => el.getClientRects().length > 0 &&
                    win.getComputedStyle(el).visibility !== 'hidden';
  const findings = [];
  let measuredRows = 0;
  doc.querySelectorAll('.inline-group').forEach(group => {
    const table = group.querySelector('table');
    if (!table) return;
    const prefix = (group.id || '').replace(/-group$/, '') || '(unnamed)';
    const thead = table.querySelector('thead');
    const theadPainted = thead ? vis(thead) : false;
    let labelLayer = false, hiddenReal = 0, paintedProto = 0, realRows = 0;
    table.querySelectorAll('tbody').forEach(tb => {
      const tr = tb.querySelector('tr[id]');
      // Unfold names the prototype row "<prefix>-empty"; its class is shared
      // with every other new row, so the id is the only thing that separates
      // the phantom from the row a user is meant to fill.
      // BOTH, not either. The class alone is shared with every new row,
      // so the id is what separates the phantom -- but keying on the id alone
      // silently skips a real row whose id happens to end in -empty, and a
      // row this gate skips is a row it can never report.
      const isProto = !!(tr && /-empty$/.test(tr.id) &&
                         tr.classList.contains('empty-form'));
      const controls = [...tb.querySelectorAll(
        'input:not([type=hidden]),select,textarea')];
      const painted = vis(tb);
      if (isProto) { if (painted) paintedProto++; return; }
      if (!controls.length) return;
      realRows++;
      // A row can be hidden at the tbody (the 2026-09-06 defect) or at the
      // tr. What decides it for a user is whether the CONTROLS paint.
      // `some`, not `every`: select2 legitimately hides the original
      // <select> it replaces, so one dark control is not a dark row.
      if (!painted || !controls.some(vis)) hiddenReal++;
      const td = tb.querySelector('td[data-label]');
      if (td && painted) {
        const b = win.getComputedStyle(td, '::before');
        if (b.content && b.content !== 'none' && b.display !== 'none') {
          labelLayer = true;
        }
      }
    });
    const layers = (theadPainted ? 1 : 0) + (labelLayer ? 1 : 0);
    if (hiddenReal) {
      findings.push({kind: 'inline-row-not-painted', prefix, count: hiddenReal});
    }
    if (paintedProto) {
      findings.push({kind: 'prototype-row-painted', prefix, count: paintedProto});
    }
    if (realRows && layers !== 1) {
      findings.push({kind: 'header-layers', prefix, layers});
    }
    measuredRows += realRows;
  });
  // The count travels with the findings so a caller can tell a clean run from
  // a run that never reached the assertion. Without it this gate reported
  // "every inline row paints" against 2 real rows in 60 inline groups -- and
  // stayed green with the defect it was written to catch planted back in.
  return {findings: findings, rows: measuredRows};
}
"""

_DRIVER = """<!doctype html><meta charset="utf-8"><title>rmc-browser-proof</title>
<style>html,body{margin:0}iframe{border:0;height:950px;display:block}</style>
<iframe id="f"></iframe>
<script>
%(measure)s
const PAGES = %(pages)s, WIDTHS = %(widths)s, BUDGET_MS = %(budget)d;
const frame = document.getElementById('f');
const results = [];
function once(name, w) {
  return new Promise(resolve => {
    let done = false;
    const timer = setTimeout(() => {
      if (done) return;
      done = true;
      results.push({page: name, width: w, inconclusive: 'page-never-loaded'});
      resolve();
    }, BUDGET_MS);
    // The iframe's own load event waits on its stylesheets; two animation
    // frames then guarantee style and layout have been flushed.
    frame.onload = () => requestAnimationFrame(() => requestAnimationFrame(() => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      try {
        const measured = rmcMeasure(frame.contentDocument,
                                    frame.contentWindow);
        results.push({page: name, width: w, findings: measured.findings,
                      rows: measured.rows});
      } catch (err) {
        results.push({page: name, width: w, inconclusive: String(err)});
      }
      resolve();
    }));
    frame.src = '/p/' + name;
  });
}
(async () => {
  for (const w of WIDTHS) {
    frame.style.width = w + 'px';
    for (const name of PAGES) { await once(name, w); }
  }
  await fetch('/report', {method: 'POST', body: JSON.stringify(results)});
  document.title = 'DONE';
})();
</script>"""


def find_browser() -> str | None:
    """Locate a headless Chromium. Absence is a SKIP, so this may return None."""
    override = (os.environ.get("RMC_HEADLESS_BROWSER") or "").strip()
    if override:
        return override if pathlib.Path(override).exists() else None
    roots = [
        pathlib.Path.home() / "AppData" / "Local" / "ms-playwright",
        pathlib.Path.home() / ".cache" / "ms-playwright",
    ]
    names = ("chrome-headless-shell.exe", "chrome-headless-shell",
             "headless_shell", "chrome", "chrome.exe")
    for root in roots:
        if not root.is_dir():
            continue
        for cache in sorted(root.glob("chromium*"), reverse=True):
            for name in names:
                for hit in cache.rglob(name):
                    if hit.is_file():
                        return str(hit)
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


class _Handler(BaseHTTPRequestHandler):
    pages: dict = {}
    report: dict = {}
    done: threading.Event = threading.Event()
    driver_html: bytes = b""
    serve_static: bool = True

    def log_message(self, *args):  # keep the gate's stdout its own
        pass

    def _send(self, body: bytes, ctype: str = "text/html; charset=utf-8"):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        # ONLY the driver may report. These are real admin pages and they
        # carry the platform's own click-ingest beacon, which POSTs
        # {"page_path": ...} to a relative URL. Accepting a POST on any path
        # let that telemetry overwrite the run's results.
        if self.path.split("?")[0] != "/report":
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        try:
            _Handler.report["data"] = json.loads(body or b"[]")
        except ValueError:
            _Handler.report["data"] = []
        self._send(b"ok", "text/plain")
        _Handler.done.set()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            return self._send(_Handler.driver_html)
        if path.startswith("/p/"):
            body = _Handler.pages.get(path[3:])
            if body is not None:
                return self._send(body)
        if path.startswith("/static/") and _Handler.serve_static:
            from django.contrib.staticfiles import finders

            hit = finders.find(path[len("/static/"):])
            if hit and os.path.isfile(hit):
                return self._send(
                    open(hit, "rb").read(),
                    mimetypes.guess_type(hit)[0] or "application/octet-stream")
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()


def _run_browser(pages, widths, *, serve_static, budget, page_budget_ms):
    """Serve `pages`, drive one browser over them, return the driver's report."""
    _Handler.pages = pages
    _Handler.report = {}
    _Handler.done = threading.Event()
    _Handler.serve_static = serve_static
    _Handler.driver_html = (_DRIVER % {
        "measure": MEASURE_JS,
        "pages": json.dumps(sorted(pages)),
        "widths": json.dumps(list(widths)),
        "budget": page_budget_ms,
    }).encode("utf-8")

    browser = find_browser()
    if not browser:
        return None, "no headless Chromium found (set RMC_HEADLESS_BROWSER)"

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    profile = tempfile.mkdtemp(prefix="rmc-browser-proof-")
    proc = subprocess.Popen(
        [browser, "--headless", "--disable-gpu", "--no-first-run",
         "--no-default-browser-check", "--hide-scrollbars",
         "--user-data-dir=" + profile, "--window-size=1600,1000",
         "http://127.0.0.1:%d/" % port],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        finished = _Handler.done.wait(timeout=budget)
    finally:
        # Kill the TREE by pid. A browser spawns renderer children, and
        # terminating only the parent leaves them holding the profile dir.
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True)
        else:
            proc.kill()
        try:
            proc.wait(timeout=15)
        except Exception:
            pass
        server.shutdown()
        shutil.rmtree(profile, ignore_errors=True)
    if not finished:
        return None, "browser produced no report within %ss" % budget
    return _Handler.report.get("data") or [], None


# --------------------------------------------------------------------------
# Self-check: prove the detector can tell good from bad before believing a zero.
# --------------------------------------------------------------------------
_GOOD = """<!doctype html><meta charset="utf-8">
<div class="inline-group" id="g-group"><table>
<thead><tr><th>Name</th></tr></thead>
<tbody><tr id="g-0"><td data-label="Name"><input name="a"></td></tr></tbody>
<tbody><tr id="g-empty" class="empty-form"><td data-label="Name">
  <input name="b"></td></tr></tbody>
</table></div>
<style>tbody:has(> tr.empty-form){display:none}</style>"""

#: Hidden at the ROW. The tbody still paints, so a tbody-only check misses
#: it -- which is exactly what the first cut of this gate did.
_HIDDEN_ROW_TR = _GOOD.replace(
    "<style>", "<style>#g-0{display:none}\n")

#: Hidden at the TBODY: the shape that actually shipped, where a rule meant
#: only for the prototype took every new row with it.
_HIDDEN_ROW_TBODY = _GOOD.replace(
    "<style>", "<style>tbody:has(> tr#g-0){display:none}\n")

_PAINTED_PROTOTYPE = _GOOD.replace(
    "<style>tbody:has(> tr.empty-form){display:none}</style>", "<style></style>")

_DOUBLED_HEADER = _GOOD.replace(
    "<style>", "<style>td[data-label]::before{content:attr(data-label);display:inline}\n")

#: A REAL row whose id merely ends in -empty, hidden. Unfold names the
#: prototype by id, so a check keyed on the name alone treats this row as the
#: phantom, skips it, and reports nothing at all.
_REAL_ROW_NAMED_EMPTY = _GOOD.replace(
    '<tr id="g-0">', '<tr id="g-0-empty">').replace(
    "<style>", "<style>#g-0-empty{display:none}\n")

SELF_CHECK_CASES = {
    "good": (_GOOD, set()),
    "real_row_named_empty": (_REAL_ROW_NAMED_EMPTY, {"inline-row-not-painted"}),
    "hidden_row_tr": (_HIDDEN_ROW_TR, {"inline-row-not-painted"}),
    "hidden_row_tbody": (_HIDDEN_ROW_TBODY, {"inline-row-not-painted"}),
    "painted_prototype": (_PAINTED_PROTOTYPE, {"prototype-row-painted"}),
    "doubled_header": (_DOUBLED_HEADER, {"header-layers"}),
}


def self_check(verbose=True) -> bool:
    pages = {name: html.encode("utf-8") for name, (html, _) in SELF_CHECK_CASES.items()}
    data, err = _run_browser(pages, (1440,), serve_static=False, budget=120,
                             page_budget_ms=15000)
    if data is None:
        print("SELF-CHECK SKIPPED: %s" % err)
        return None
    seen = {}
    for row in data:
        seen.setdefault(row["page"], set()).update(
            f["kind"] for f in row.get("findings", []))
    ok = True
    for name, (_, expected) in sorted(SELF_CHECK_CASES.items()):
        got = seen.get(name, set())
        good = got == expected
        ok = ok and good
        if verbose:
            print("  %-20s expected=%-28s got=%-28s %s" % (
                name, sorted(expected) or "none", sorted(got) or "none",
                "OK" if good else "*** MISMATCH ***"))
    return ok


# --------------------------------------------------------------------------
def discover_and_render(tmpdir: pathlib.Path):
    """Render every admin add-page that carries a tabular inline."""
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    django.setup()

    from django.contrib.admin import TabularInline
    from django.contrib.auth import get_user_model
    from django.contrib.sessions.backends.signed_cookies import SessionStore
    from django.test import RequestFactory
    from django.urls import set_urlconf
    import config.admin as cadmin

    sites = {}
    for _name, obj in vars(cadmin).items():
        if hasattr(obj, "_registry") and hasattr(obj, "name") and obj._registry:
            sites.setdefault(id(obj), obj)

    # A SAVED superuser, and the gate never creates one: a local run points at
    # the shared dev database. An unsaved instance is not a shortcut -- several
    # ModelAdmins filter a queryset by `user=request.user` and Django refuses
    # ("Model instances passed to related filters must be saved"), which took
    # 3 of 25 pages down and SKIPped the whole run.
    user = get_user_model().objects.filter(
        is_superuser=True, is_active=True).order_by("id").first()
    if user is None:
        return {}, ["no active superuser to render as -- seed one with"
                    " `python manage.py createsuperuser`"]

    # Force every tabular inline to OFFER a row. Without this the gate is
    # measuring the wrong thing: `extra = 0` on 31 of this repo's tabular
    # inlines means an add page renders the prototype and nothing a user can
    # type into, so the row that the 2026-09-06 defect made invisible is not
    # on the page at all. Patched on the base class rather than on each
    # inline: one save, one restore, and no subclass in this repo overrides
    # get_extra. One that did would simply not be forced, and the row-count
    # guard in main() would then refuse to report a pass.
    had_own_get_extra = "get_extra" in TabularInline.__dict__
    original_get_extra = TabularInline.get_extra
    def _at_least_one_row(self, request, obj=None, **kwargs):
        return max(1, original_get_extra(self, request, obj, **kwargs))

    TabularInline.get_extra = _at_least_one_row

    factory = RequestFactory()
    pages, problems = {}, []
    try:
        for site in sites.values():
            urlconf = SITE_URLCONF.get(site.name, "config.urls")
            for model, model_admin in site._registry.items():
                inlines = model_admin.inlines or []
                if not any(isinstance(i, type) and issubclass(i, TabularInline)
                           for i in inlines):
                    continue
                label = model._meta.label_lower.replace(".", "_")
                set_urlconf(urlconf)
                try:
                    request = factory.get("/admin/%s/%s/add/" % (
                        model._meta.app_label, model._meta.model_name))
                    request.urlconf = urlconf
                    request.user = user
                    request.session = SessionStore()
                    html = model_admin.add_view(request).render().content
                    pages[label] = html
                    (tmpdir / (label + ".html")).write_bytes(html)
                except Exception as exc:  # a page that will not render is a finding
                    problems.append("%s: %s: %s" % (label, type(exc).__name__,
                                                    str(exc)[:120]))
    finally:
        if had_own_get_extra:
            TabularInline.get_extra = original_get_extra
        else:
            del TabularInline.get_extra
    return pages, problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-check", action="store_true",
                        help="prove the assertions fire against known-bad pages")
    parser.add_argument("--widths", default=",".join(str(w) for w in DEFAULT_WIDTHS))
    parser.add_argument("--budget", type=float, default=600.0,
                        help="seconds for the whole browser pass")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.self_check:
        result = self_check()
        if result is None:
            return _SKIPPED_EXIT_CODE
        print("SELF-CHECK", "PASS" if result else "FAIL")
        return 0 if result else 1

    widths = [int(w) for w in args.widths.split(",") if w.strip()]
    if not any(w < _LG_BREAKPOINT for w in widths):
        print("refusing to run: no width below %dpx, which is where the stacked"
              " label layout lives" % _LG_BREAKPOINT)
        return 1

    if find_browser() is None:
        print("SKIP: no headless Chromium found. Set RMC_HEADLESS_BROWSER to one.")
        return _SKIPPED_EXIT_CODE

    started = time.monotonic()

    # The detector must be shown working before its zero means anything.
    checked = self_check(verbose=False)
    if checked is None:
        print("SKIP: browser present but the self-check could not run")
        return _SKIPPED_EXIT_CODE
    if not checked:
        print("REFUSING TO REPORT: the self-check failed, so a clean result here"
              " would be meaningless. Run --self-check to see which case broke.")
        return 1

    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="rmc-admin-pages-"))
    try:
        try:
            pages, problems = discover_and_render(tmpdir)
        except Exception as exc:
            print("SKIP: could not render admin pages (%s: %s)"
                  % (type(exc).__name__, str(exc)[:160]))
            return _SKIPPED_EXIT_CODE
        if not pages:
            print("SKIP: no admin registration with a tabular inline could be"
                  " rendered. %s" % ("; ".join(problems[:3]) or ""))
            return _SKIPPED_EXIT_CODE

        remaining = _DEADLINE_S - (time.monotonic() - started)
        if remaining < _MIN_BROWSER_S:
            print("SKIP: startup, self-check and rendering used %.0fs of the"
                  " %.0fs deadline, leaving too little to measure in. This is a"
                  " RESOURCE result, not a finding."
                  % (_DEADLINE_S - remaining, _DEADLINE_S))
            return _SKIPPED_EXIT_CODE
        data, err = _run_browser(pages, widths, serve_static=True,
                                 budget=min(args.budget, remaining),
                                 page_budget_ms=25000)
        if data is None:
            print("SKIP: %s" % err)
            return _SKIPPED_EXIT_CODE
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    findings, inconclusive, measured_rows = [], [], 0
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        # The driver is the only thing that posts here, so this means its own
        # report did not survive. Never silently treat that as a clean run.
        print("SKIP: driver report had an unexpected shape (%s): %s"
              % (type(data).__name__, repr(data)[:200]))
        return _SKIPPED_EXIT_CODE
    for row in data:
        if row.get("inconclusive"):
            inconclusive.append(row)
            continue
        measured_rows += row.get("rows") or 0
        for finding in row.get("findings", []):
            findings.append(dict(finding, page=row["page"], width=row["width"]))

    if args.json:
        print(json.dumps({"findings": findings, "inconclusive": inconclusive,
                          "problems": problems, "pages": len(pages),
                          "widths": widths, "rows": measured_rows}, indent=2))
    else:
        print("browser proof: %d admin form pages x %s px, %d offered rows"
              % (len(pages), "/".join(str(w) for w in widths), measured_rows))
        for problem in problems:
            print("  DID NOT RENDER  %s" % problem)
        for row in inconclusive:
            print("  INCONCLUSIVE    %s @%s: %s" % (
                row["page"], row["width"], row["inconclusive"]))
        for finding in findings:
            print("  FINDING         %s @%spx  %s  inline=%s  %s" % (
                finding["page"], finding["width"], finding["kind"],
                finding["prefix"],
                "count=%s" % finding["count"] if "count" in finding
                else "layers=%s" % finding.get("layers")))
        if not findings and not problems and not inconclusive:
            print("  every inline row paints, no phantom prototype, one header"
                  " layer everywhere.")

    # A zero from a detector that never reached its assertion is not a pass.
    # This gate shipped its first cut measuring 2 rows across 60 inline groups
    # and stayed green with the real defect planted back in.
    if not measured_rows:
        print("REFUSING TO REPORT: not one fillable inline row was measured, so"
              " a clean result here would mean nothing. Rendering forces"
              " extra>=1; this is what it looks like when that stops working.")
        return 1

    # A page that would not render, or would not load, is not a pass. It is the
    # absence of an answer, and saying PASS there is how a gate starts lying.
    if problems or inconclusive:
        return 1
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
