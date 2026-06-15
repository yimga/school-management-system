"""Build a faithful standalone reproduction of the control-plane shell so the
copilot rail's real geometry can be rendered + measured in a browser.

It inlines EVERY control-plane stylesheet (in the exact <head> order from
control_plane_skeleton.html) + the inline-critical grid block, and reproduces
the real .rmc-app-shell DOM with the real copilot <aside>. No cherry-picking:
whatever the control plane ships is what this page renders.
"""
import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]  # school-management-system/
SKELETON = ROOT / "templates" / "control_plane_skeleton.html"
STATIC = ROOT / "static"
OUT = ROOT / "var" / "copilot-proof" / "copilot_rail_proof.html"

skeleton_text = SKELETON.read_text(encoding="utf-8")

# Ordered list of every {% static 'css/....css' %} stylesheet link in the head.
css_refs = re.findall(r"{%\s*static\s*'(css/[^']+\.css)'\s*%}", skeleton_text)
# Preserve order, drop dups.
seen = set()
ordered = []
for ref in css_refs:
    if ref not in seen:
        seen.add(ref)
        ordered.append(ref)

inlined = []
missing = []
for ref in ordered:
    p = STATIC / ref
    if p.exists():
        css = p.read_text(encoding="utf-8", errors="replace")
        inlined.append(f"/* ===== {ref} ===== */\n{css}")
    else:
        missing.append(ref)

# The inline-critical grid block lives in a <style id="rmc-cp-copilot-grid-critical">.
m = re.search(
    r'<style[^>]*id="rmc-cp-copilot-grid-critical"[^>]*>(.*?)</style>',
    skeleton_text,
    re.DOTALL,
)
inline_critical = m.group(1) if m else ""

all_css = "\n\n".join(inlined) + "\n\n/* ===== inline-critical (skeleton line ~178) ===== */\n" + inline_critical

# Demo-only paint for the NON-copilot regions so the shell reads clearly in a
# screenshot. The copilot rail itself is left ENTIRELY to the shipped CSS
# (rmc-cp-200x.css etc., already inlined above) so it looks like a real page.
demo_css = """
/* demo-only: make the shell regions visible — does NOT touch the copilot rail */
html, body { margin: 0; height: 100%; }
.rmc-app-shell { height: 100vh; }
.rmc-app-shell__header { background:#11141b; color:#cfd6e4; display:flex; align-items:center; padding:0 16px; font:600 14px/1 Inter,system-ui,sans-serif; }
.rmc-app-shell__sidebar { background:#0e1117; border-right:1px solid #232a36; color:#9aa6b8; padding:12px; font:13px Inter,system-ui,sans-serif; }
.rmc-app-shell__canvas { background:#070a0f; color:#aeb8c8; overflow:auto; }
.rmc-app-shell__canvas-body { padding:18px; font:13px Inter,system-ui,sans-serif; }
.rmc-app-shell__footer { background:#11141b; color:#7e8aa0; display:flex; align-items:center; padding:0 16px; font:12px Inter,system-ui,sans-serif; }
.rmc-proof-bar { position:fixed; top:8px; left:50%; transform:translateX(-50%); z-index:9999; background:#1b2230; color:#e6ecf6; border:1px solid #39455a; border-radius:10px; padding:8px 12px; font:12px Inter,system-ui,sans-serif; display:flex; gap:8px; align-items:center; }
.rmc-proof-bar button { background:#2563eb; color:#fff; border:0; border-radius:7px; padding:6px 10px; cursor:pointer; font:600 12px Inter,sans-serif; }
.rmc-proof-bar code { background:#0e1117; padding:2px 6px; border-radius:5px; }
"""

dom = """
<div class="rmc-proof-bar">
  <strong>Copilot rail proof</strong>
  <button onclick="setState('collapsed')">Collapsed (44px)</button>
  <button onclick="setState('expanded')">Expanded (360px)</button>
  <button onclick="dropAttr()">Drop attribute (test :has fallback)</button>
  <span id="readout"></span>
</div>

<div class="rmc-app-shell rmc-app-shell--with-copilot" data-copilot="collapsed" data-rmc-app-shell-copilot="1">
  <header class="rmc-app-shell__header" role="banner">RunMyCampus · MANAGER — control plane header (grid row 1, full width)</header>
  <aside class="rmc-app-shell__sidebar" aria-label="Control plane navigation">
    <div>START</div><div>Platform backoffice</div><div>Control plane</div><div>Config center</div>
    <div style="margin-top:12px">WORKFLOWS</div><div>Workflow Flight Deck</div>
  </aside>
  <div class="rmc-app-shell__canvas">
    <div class="rmc-app-shell__canvas-body">
      <h2 style="color:#e6ecf6;font:600 18px Inter,sans-serif">Operator workspace</h2>
      <p>Canvas content (grid column 2). The AI copilot rail must dock as a vertical strip on the RIGHT — grid column 3 — not as a horizontal band below this canvas.</p>
    </div>
  </div>

  <aside class="rmc-app-shell__copilot" aria-label="AI copilot"
         data-rmc-copilot-rail data-rmc-cockpit-region="rail" data-rmc-copilot-active-tab="chat">
    <div class="lx-copilot">
      <!-- Collapsed state — 44px vertical icon rail (verbatim from _ai_copilot_rail.html) -->
      <div class="lx-copilot__collapsed">
        <button class="lx-copilot__toggle" type="button" data-rmc-copilot-toggle data-rmc-copilot-tab="chat" title="Open AI copilot" aria-label="Open AI copilot">&#10022;</button>
        <button class="lx-copilot__rail-icon" type="button" data-rmc-copilot-tab="lens" title="Context lens — selection & compare" aria-label="Context lens">&#9673;</button>
        <button class="lx-copilot__rail-icon" type="button" data-rmc-copilot-tab="actions" title="Suggested actions" aria-label="Suggested actions">&#9889;</button>
        <button class="lx-copilot__rail-icon" type="button" data-rmc-copilot-tab="threads" title="Recent threads" aria-label="Recent threads">&#8984;</button>
        <button class="lx-copilot__rail-icon" type="button" data-rmc-copilot-tab="shortcuts" title="Shortcuts & pinned" aria-label="Shortcuts &amp; pinned">&#9872;</button>
        <button class="lx-copilot__rail-icon" type="button" data-rmc-copilot-tab="today" title="Today — agenda & due" aria-label="Today — agenda &amp; due">&#9680;</button>
        <button class="lx-copilot__rail-icon lx-copilot__rail-icon--context" type="button" data-rmc-copilot-tab="context" title="Context — about this page" aria-label="Context — about this page">&#9672;</button>
        <button class="lx-copilot__rail-icon" type="button" data-rmc-operator-notebook-toggle title="Toggle operator notebook" aria-label="Toggle operator notebook">&#9998;</button>
        <a class="lx-copilot__rail-icon lx-copilot__rail-icon--help" href="#" data-rmc-page-help title="Need help on this page?" aria-label="Need help on this page?">?</a>
        <div class="lx-copilot__kbd" aria-hidden="true">&#8984; K</div>
      </div>

      <!-- Expanded state — 360px panel (verbatim structure from _ai_copilot_rail.html) -->
      <div class="lx-copilot__expanded">
        <div class="lx-copilot__header">
          <div class="lx-copilot__title">
            <span class="lx-copilot__title-mark" aria-hidden="true">&#10022;</span>
            <span>Copilot <span class="lx-copilot__title-em">— <em>operator</em></span></span>
          </div>
          <div class="lx-copilot__header-actions">
            <span class="lx-copilot__posture" data-rmc-copilot-rail-posture data-state="unknown" aria-label="AI source">
              <span class="lx-copilot__posture-dot" aria-hidden="true"></span>
              <span data-rmc-copilot-rail-posture-label>Checking…</span>
            </span>
            <button class="lx-copilot__close" type="button" data-rmc-copilot-toggle aria-label="Collapse copilot rail">&#8594;</button>
          </div>
        </div>
        <nav class="lx-copilot__tabs" role="tablist" aria-label="Copilot sections">
          <button type="button" class="lx-copilot__tab" data-rmc-copilot-tab="chat" role="tab">Chat</button>
          <button type="button" class="lx-copilot__tab" data-rmc-copilot-tab="lens" role="tab">Lens</button>
          <button type="button" class="lx-copilot__tab" data-rmc-copilot-tab="actions" role="tab">Actions</button>
          <button type="button" class="lx-copilot__tab" data-rmc-copilot-tab="threads" role="tab">Threads</button>
          <button type="button" class="lx-copilot__tab" data-rmc-copilot-tab="shortcuts" role="tab">Shortcuts</button>
          <button type="button" class="lx-copilot__tab" data-rmc-copilot-tab="today" role="tab">Today</button>
          <button type="button" class="lx-copilot__tab" data-rmc-copilot-tab="context" role="tab">Context</button>
        </nav>
        <div class="lx-copilot__quickstats" role="group" aria-label="At a glance">
          <a class="lx-copilot__quickstat" href="#" title="Unread messages"><span class="lx-copilot__quickstat-icon" aria-hidden="true">&#9993;</span><span class="lx-copilot__quickstat-value">0</span><span class="lx-copilot__quickstat-label">Msg</span></a>
          <a class="lx-copilot__quickstat" href="#" title="Unread notifications"><span class="lx-copilot__quickstat-icon" aria-hidden="true">&#9679;</span><span class="lx-copilot__quickstat-value">0</span><span class="lx-copilot__quickstat-label">Alerts</span></a>
          <span class="lx-copilot__quickstat" title="Pending approvals"><span class="lx-copilot__quickstat-icon" aria-hidden="true">&#9670;</span><span class="lx-copilot__quickstat-value">0</span><span class="lx-copilot__quickstat-label">Pending</span></span>
          <span class="lx-copilot__quickstat" title="Due today"><span class="lx-copilot__quickstat-icon" aria-hidden="true">&#9635;</span><span class="lx-copilot__quickstat-value">0</span><span class="lx-copilot__quickstat-label">Due</span></span>
        </div>
        <div class="lx-copilot__insights-wrap px-3 pb-2">
          <div class="lx-copilot__insights-head d-flex align-items-center justify-content-between gap-2 mb-1">
            <span class="small text-uppercase text-secondary">Pulse</span>
          </div>
          <ul class="lx-copilot__insights-list list-unstyled mb-0">
            <li class="lx-copilot__insight">All systems operational — 3 of 3 schools live.</li>
            <li class="lx-copilot__insight">1 provisioning run needs attention.</li>
          </ul>
        </div>
        <div class="lx-copilot__thread" data-rmc-copilot-pane="chat">
          <div class="lx-copilot__msg lx-copilot__msg--ai">How can I help on this page?</div>
          <div class="lx-copilot__suggestions" role="group" aria-label="Suggested actions">
            <button type="button" class="lx-copilot__suggestion">Summarise incidents</button>
            <button type="button" class="lx-copilot__suggestion">Show stuck workflows</button>
          </div>
        </div>
      </div>
    </div>
  </aside>

  <footer class="rmc-app-shell__footer">RunMyCampus Manager Backoffice — operator footer (grid row 3, full width)</footer>
</div>

<script>
function readout(){
  var a = document.querySelector('.rmc-app-shell__copilot');
  var s = document.querySelector('.rmc-app-shell');
  var r = a.getBoundingClientRect();
  var vertical = r.height > r.width && (r.right > window.innerWidth - 5);
  document.getElementById('readout').innerHTML =
    'aside: <code>x='+Math.round(r.x)+' y='+Math.round(r.y)+' w='+Math.round(r.width)+' h='+Math.round(r.height)+'</code> '
    + (vertical ? '✅ VERTICAL right-dock' : '❌ NOT a right-dock');
}
function setState(st){
  var s = document.querySelector('.rmc-app-shell');
  s.setAttribute('data-copilot', st);
  setTimeout(readout, 30);
}
function dropAttr(){
  var s = document.querySelector('.rmc-app-shell');
  s.removeAttribute('data-rmc-app-shell-copilot');
  setTimeout(readout, 30);
}
window.addEventListener('load', function(){ setTimeout(readout, 50); });
</script>
"""

html = f"""<!doctype html>
<html lang="en" data-rmc-isomorphic-template="operator-control-plane" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Copilot rail geometry proof — control plane</title>
<style>
{all_css}
{demo_css}
</style>
</head>
<body class="control-plane-shell cp-surface" data-rmc-shell-body="control-plane-skeleton" data-rmc-shell-main="control-plane">
{dom}
</body>
</html>
"""

OUT.write_text(html, encoding="utf-8")
print(f"wrote {OUT}")
print(f"inlined {len(inlined)} stylesheets; missing {len(missing)}: {missing}")
print(f"inline-critical block found: {bool(inline_critical)} ({len(inline_critical)} chars)")
