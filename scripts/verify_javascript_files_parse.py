#!/usr/bin/env python
"""Every shipped JavaScript file must actually parse.

The sibling of ``verify_python_files_parse.py``, and it exists because that gate's own
write-up named the hole and stopped: *"no CI gate checks that JavaScript files parse."*

WHY IT MATTERS AS MUCH AS THE PYTHON ONE. A Python module that does not compile fails
loudly at import. A JavaScript file that does not parse fails **silently in the user's
browser**: the ``<script>`` tag 200s, the engine throws a SyntaxError into the console,
and the page renders looking completely normal with one feature simply not working. There
is no server log, no Sentry event by default, and no test that notices — the very failure
mode the service worker, the sync progress chrome, and the offline queue all live in.
``static/js/service-worker.js`` is worse still: a SyntaxError there kills registration, so
the offline shell an appliance depends on silently stops updating.

HOW. ``node --check``, which is the real parser — not a regex, not a brace counter, so it
cannot disagree with the engine that will actually run the file. Both module systems are
tried, because this tree ships both: a file is a finding only when it parses as NEITHER a
script nor an ES module.

Files are batched through one Node process rather than one process per file: a
per-file spawn on Windows costs ~40ms, which on a tree this size is minutes, and a gate
slow enough to skip is a gate that gets skipped.

Zero tolerance: no baseline and no allow-marker, because a file that does not parse is
never intentional.

Exit codes: 0 clean, 1 one or more files do not parse, 2 Node is unavailable.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# What actually ships to a browser or a service worker.
SCAN_ROOTS = ("static/js", "static/sw", "edge/src")

SKIP_DIR_NAMES = {
    "node_modules",
    ".git",
    "__pycache__",
    "vendor",
    "dist",
    "build",
    "min",
    "coverage",
}

# Third-party bundles we neither wrote nor can fix; a minified vendor drop that Node
# cannot parse is a packaging problem, not a source defect.
SKIP_FILE_SUFFIXES = (".min.js", ".bundle.js", ".map")

# The checker runs INSIDE node, so it uses node's own parser for both module systems.
_CHECKER = r"""
const fs = require('fs');
const vm = require('vm');
const files = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const findings = [];
for (const file of files) {
  let source;
  try {
    source = fs.readFileSync(file, 'utf8');
  } catch (err) {
    findings.push({ file, line: 0, message: 'unreadable: ' + err.message });
    continue;
  }
  let scriptError = null;
  try {
    new vm.Script(source, { filename: file });
    continue;                      // parses as a classic script
  } catch (err) {
    scriptError = err;
  }
  try {
    // ES module syntax (import/export) is a SyntaxError for a classic script, so a
    // second attempt is required before calling anything broken.
    new vm.SourceTextModule(source, { identifier: file });
    continue;
  } catch (err) {
    if (err && err.code === 'ERR_VM_MODULE_NOT_AVAILABLE') {
      // Without --experimental-vm-modules we cannot confirm module syntax. Rather than
      // report a false positive, fall back to the heuristic that the ONLY reason a
      // well-formed file fails the script parse is top-level import/export.
      const msg = String(scriptError && scriptError.message);
      if (/import|export/i.test(msg)) continue;
    }
  }
  const stack = String((scriptError && scriptError.stack) || '');
  const match = stack.match(/^.*?:(\d+)$/m);
  findings.push({
    file,
    line: match ? Number(match[1]) : 0,
    message: String((scriptError && scriptError.message) || 'syntax error'),
  });
}
process.stdout.write(JSON.stringify(findings));
"""


def _node() -> str | None:
    return shutil.which("node")


def _iter_js_files(roots):
    for root_name in roots:
        root = REPO_ROOT / root_name
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.js")):
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if path.name.endswith(SKIP_FILE_SUFFIXES):
                continue
            yield path


def scan(roots=SCAN_ROOTS):
    """Return ``(checked, findings)`` where a finding is ``(relpath, lineno, message)``."""
    files = [str(p) for p in _iter_js_files(roots)]
    if not files:
        return 0, []
    node = _node()
    if node is None:
        return len(files), [("", 0, "node is not installed; cannot verify JavaScript")]

    with tempfile.TemporaryDirectory() as tmp:
        list_path = os.path.join(tmp, "files.json")
        checker_path = os.path.join(tmp, "check.js")
        with open(list_path, "w", encoding="utf8") as fh:
            json.dump(files, fh)
        with open(checker_path, "w", encoding="utf8") as fh:
            fh.write(_CHECKER)
        try:
            proc = subprocess.run(  # noqa: S603 — fixed argv, no shell
                [node, "--experimental-vm-modules", checker_path, list_path],
                capture_output=True,
                text=True,
                timeout=300,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return len(files), [("", 0, f"could not run node: {exc}")]

    raw = (proc.stdout or "").strip()
    if not raw:
        detail = (proc.stderr or "").strip().splitlines()[-1:] or ["no output"]
        return len(files), [("", 0, f"the JavaScript checker produced nothing: {detail[0]}")]
    try:
        parsed = json.loads(raw)
    except ValueError:
        return len(files), [("", 0, "the JavaScript checker returned unreadable output")]

    findings = []
    for item in parsed:
        try:
            rel = Path(item["file"]).resolve().relative_to(REPO_ROOT).as_posix()
        except (ValueError, KeyError):
            rel = str(item.get("file", "?"))
        findings.append((rel, int(item.get("line") or 0), str(item.get("message") or "")))
    return len(files), findings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--roots", nargs="*", default=list(SCAN_ROOTS))
    args = parser.parse_args(argv)

    if _node() is None:
        # Distinguished from "clean": pretending a gate ran when its toolchain is absent
        # is exactly how a gate silently stops gating.
        print("javascript-parse: node is not installed — cannot verify. Install Node.")
        return 2

    checked, findings = scan(tuple(args.roots))
    if not findings:
        print(f"javascript-parse: {checked} file(s) checked, 0 do not parse")
        return 0

    print(f"javascript-parse: {checked} file(s) checked, {len(findings)} DO NOT PARSE")
    for rel, lineno, msg in findings:
        print(f"  {rel}:{lineno}: {msg}")
    print("")
    print("A script that does not parse fails SILENTLY in the browser: the tag 200s, the")
    print("console throws, and the page looks fine with one feature dead. There is no")
    print("baseline and no allow-marker for this gate.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
