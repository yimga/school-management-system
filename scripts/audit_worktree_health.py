#!/usr/bin/env python
"""Audit the registered git worktrees, and find the ones that are loaded guns.

WHY THIS EXISTS
---------------
Several agents work this repository at once and each one tends to create a
worktree. They are cheap to make and nobody owns cleaning them up, so they
accumulate: 40 registered on 2026-08-28.

That would be untidy rather than dangerous, except for one state git does not
warn about. When a worktree's DIRECTORY still exists but its checkout has been
gutted -- the scratchpad it lived in was cleared, a temp sweeper ran, a killed
``git worktree add`` never finished -- the worktree stays registered and its
index still lists every tracked file. ``git status`` inside it then reports
every one of those files as deleted. On this repository that is 15,620
deletions, and a single ``git commit -a`` in that directory removes the entire
tree. Thirteen worktrees were in exactly that state when this script was
written.

``git worktree prune`` does not help: it only removes worktrees whose directory
is GONE. A hollow directory is, as far as prune is concerned, a live worktree.
One of the forty qualified for prune. Thirteen did not.

WHAT IT REPORTS
---------------
    LIVE     the checkout is there and usable
    GONE     directory missing; ``git worktree prune`` will clear it
    HOLLOW   directory present, checkout gutted -- a mass-deletion hazard
    LOCKED   explicitly locked; never touched without --force

Every HOLLOW and GONE entry is checked for UNMERGED WORK before it is offered
for removal. A worktree whose branch carries commits that are not in
``origin/main`` is reported as KEEP with the commit count, and ``--prune`` will
not touch it. Losing someone's afternoon is the thing this script is for; it
must not become the thing it does.

USAGE
-----
    python scripts/audit_worktree_health.py            # report only
    python scripts/audit_worktree_health.py --prune    # remove safe entries
    python scripts/audit_worktree_health.py --prune --force   # include locked

Dry run is the default, deliberately: this is a destructive tool, and the
preview is produced by the same classification the removal uses rather than
being a second estimate of it.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# A checkout without these is not a checkout of THIS repository, whatever its
# index believes. Two files, so a single deleted file does not condemn a
# worktree somebody is mid-edit in.
CHECKOUT_MARKERS = ("manage.py", "config/settings.py")


@dataclass
class Worktree:
    path: Path
    head: str
    branch: str
    locked: bool
    state: str = "LIVE"
    deletions: int = 0
    unmerged: int = 0
    note: str = ""

    @property
    def removable(self) -> bool:
        # unmerged == -1 means the question could not be ANSWERED (the ref no
        # longer resolves, git errored). A destructive tool must read that as
        # "keep", not as "nothing to lose": an unanswered safety check has the
        # same shape as a scanner reporting zero because it is broken.
        return self.state in {"GONE", "HOLLOW"} and self.unmerged == 0


def _git(*args: str, cwd: Path | None = None) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def discover() -> list[Worktree]:
    _, raw = _git("worktree", "list", "--porcelain")
    found: list[Worktree] = []
    for block in [b for b in raw.split("\n\n") if b.strip()]:
        match = re.search(r"^worktree (.+)$", block, re.M)
        if not match:
            continue
        branch = re.search(r"^branch (.+)$", block, re.M)
        head = re.search(r"^HEAD (.+)$", block, re.M)
        found.append(
            Worktree(
                path=Path(match.group(1)),
                head=(head.group(1)[:9] if head else ""),
                branch=(branch.group(1).replace("refs/heads/", "") if branch else "(detached)"),
                locked="locked" in block,
            )
        )
    return found


def classify(worktree: Worktree, main_checkout: Path) -> None:
    if worktree.path == main_checkout:
        worktree.note = "the main checkout"
        return
    if not worktree.path.exists():
        worktree.state = "GONE"
    elif not all((worktree.path / marker).exists() for marker in CHECKOUT_MARKERS):
        worktree.state = "HOLLOW"
        code, out = _git("status", "--porcelain", cwd=worktree.path)
        if code == 0:
            worktree.deletions = sum(1 for line in out.splitlines() if line[1:2] == "D")
    if worktree.state == "LIVE":
        return
    # Never offer to remove something carrying work that is not on the remote.
    ref = worktree.branch if worktree.branch != "(detached)" else worktree.head
    if not ref:
        worktree.unmerged = -1
        worktree.note = "no branch and no recorded HEAD; cannot check for unmerged work"
        return
    code, out = _git("rev-list", "--count", f"origin/main..{ref}")
    if code == 0 and out.strip().isdigit():
        worktree.unmerged = int(out.strip())
    else:
        worktree.unmerged = -1
        worktree.note = f"could not resolve {ref} against origin/main"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prune", action="store_true", help="remove GONE and HOLLOW entries that carry no unmerged work")
    parser.add_argument("--force", action="store_true", help="include locked worktrees when pruning")
    parser.add_argument("--strict", action="store_true", help="exit 1 while any mass-deletion hazard remains")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    main_checkout = ROOT
    worktrees = discover()
    for worktree in worktrees:
        classify(worktree, main_checkout)

    by_state: dict[str, list[Worktree]] = {}
    for worktree in worktrees:
        by_state.setdefault(worktree.state, []).append(worktree)

    print(f"registered worktrees: {len(worktrees)}")
    for state in ("LIVE", "GONE", "HOLLOW"):
        print(f"  {state:7s} {len(by_state.get(state, []))}")

    hazards = by_state.get("HOLLOW", [])
    if hazards:
        total = sum(w.deletions for w in hazards)
        print(
            f"\n{len(hazards)} HOLLOW worktree(s) -- directory present, checkout gutted."
            f"\n`git status` in these reports {total} deletions in total; a `git commit -a`"
            f"\nin any one of them removes the tree. `git worktree prune` does NOT clear these."
        )
        for worktree in sorted(hazards, key=lambda w: -w.deletions):
            keep = f"  KEEP: {worktree.unmerged} unmerged commit(s)" if worktree.unmerged else ""
            lock = "  [locked]" if worktree.locked else ""
            print(f"    {worktree.deletions:6d} deletions  {worktree.branch:42s}{lock}{keep}")
            print(f"            {worktree.path}")

    gone = by_state.get("GONE", [])
    if gone:
        print(f"\n{len(gone)} GONE worktree(s) -- `git worktree prune` clears these:")
        for worktree in gone:
            print(f"    {worktree.branch:42s} {worktree.path}")

    candidates = [w for w in worktrees if w.removable and (args.force or not w.locked)]
    blocked = [w for w in worktrees if w.state in {"GONE", "HOLLOW"} and not w.removable]
    skipped_locked = [w for w in worktrees if w.removable and w.locked and not args.force]

    if blocked:
        print(f"\n{len(blocked)} entry(ies) NOT offered for removal:")
        for worktree in blocked:
            if worktree.unmerged < 0:
                print(f"    UNKNOWN   {worktree.branch}: {worktree.note}")
            else:
                print(f"    {worktree.unmerged:4d} commit(s) ahead of origin/main  {worktree.branch}")
    if skipped_locked:
        print(f"\n{len(skipped_locked)} locked entry(ies) skipped; pass --force to include them.")

    if not args.prune:
        if candidates:
            print(f"\n{len(candidates)} entry(ies) would be removed. Re-run with --prune to do it.")
        return 1 if (args.strict and hazards) else 0

    removed = 0
    for worktree in candidates:
        code, out = _git("worktree", "remove", "--force", str(worktree.path))
        if code == 0:
            removed += 1
            print(f"  removed  {worktree.path}")
        else:
            print(f"  FAILED   {worktree.path}: {out.strip().splitlines()[-1] if out.strip() else code}")
    _git("worktree", "prune")
    print(f"\nremoved {removed} of {len(candidates)} candidate(s)")

    remaining = [w for w in discover() if w.path.exists() and not all((w.path / m).exists() for m in CHECKOUT_MARKERS)]
    return 1 if (args.strict and remaining) else 0


if __name__ == "__main__":
    raise SystemExit(main())
