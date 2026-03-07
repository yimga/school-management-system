# Patches for follow-up commits

Apply these after the referenced base commit is on your branch.

## ops-watch-extras (follow-up commit)

**Base:** After committing "Dashboard: tuning only" (compact empty states, overview meta/delta, Quick Links empty state).

**What it does:** Adds four optional rows to Operations watch when the user has access and count > 0:
- Pending Signatures
- Contact Requests
- Unread Messages
- Announcements (pending)

**Apply manually:** Open `apps/dashboard/context.py`, find the line `    ]` that closes the `operations_watch = [...]` list, and **before** the next line `    perms = {` paste the code from `ops-watch-extras-snippet.py` (skip the comment lines at the top of the snippet file).

Then commit with message: `Ops watch: add Signatures, Contact Requests, Messages, Announcements`
