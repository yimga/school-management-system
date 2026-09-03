"""The certificate had a backup. The children's records did not.

`deploy/selfhost/edge-bootstrap.sh` and section C of `box-audit.sh` give the box's TLS
certificate authority an encrypted off-box backup, a passphrase kept deliberately apart
from it, a gate that FAILS the box when the backup is missing, a gate that FAILS when
the backup does not match the live CA, a gate that FAILS if a wrong passphrase opens it,
and a gate that FAILS when there is no verified read-back on record. That is the right
discipline, and until 2026-08-31 it was applied to a certificate while the fee ledger,
the marks, the attendance and the uploaded documents had nothing at all.

The compose file ran `db, valkey, web, worker, beat, edge-tls` over `pgdata, valkeydata,
mediadata, edgetlsdata, edgecaddydata, edgecaddyconfig`. No backup service. No backup
volume. No `pg_dump` anywhere under deploy/selfhost/. A dead SSD was total loss.

WHAT THESE TESTS CAN AND CANNOT DO, said plainly, because the honest boundary matters
more than the coverage number. There is no Docker here and no box, so nothing below
runs a container, takes a real dump, or restores one. What they DO run is real: the
retention arithmetic and the byte cap are lifted verbatim out of the shipped script and
executed by bash against synthetic input, and the encryption contract is exercised
through the script's own `openssl` invocation on real bytes. Everything else is a
STRUCTURAL pin on deploy configuration that cannot execute on a laptop -- which is the
honest way to hold config that only a box can run, and is exactly how
`test_box_rebuild_stamp_guard_2026_08_27.py` pins the compose file's Caddy mount.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import tempfile
import datetime

from django.test import SimpleTestCase

REPO = pathlib.Path(__file__).resolve().parents[3]
#: Patchable so the same assertions can be run against an older tree (that is how the
#: failing-first evidence for this file was produced -- the HEAD copies of the compose
#: file and the audit were materialised into a temp directory and these very tests were
#: pointed at it).
SELFHOST = REPO / "deploy" / "selfhost"

BACKUP_NAME = "box-backup.sh"
RESTORE_NAME = "box-restore.sh"
AUDIT_NAME = "box-audit.sh"
COMPOSE_NAME = "docker-compose.yml"

#: The two scripts this gap added. Both execute on Linux, on a box, as root.
NEW_SCRIPTS = (BACKUP_NAME, RESTORE_NAME)


def _p(name: str) -> pathlib.Path:
    return SELFHOST / name


def _text(name: str) -> str:
    return _p(name).read_text(encoding="utf-8")


def _need_bash(case):
    if shutil.which("bash") is None:
        case.skipTest("bash not available; these assert real shell behaviour")


def _extract(script: str, func: str) -> str:
    """Lift one shell function's BODY verbatim out of the real script.

    The closing brace is excluded on purpose: the body is spliced into a harness, and a
    stray `}` is a syntax error rather than a failed assertion. Same technique the
    box-rebuild stamp-parser tests use, and for the same reason -- a retention rule that
    is only READ is a retention rule nobody has ever run.
    """
    text = _text(script)
    start = text.index(func + "() {")
    open_at = text.index("{", start)
    end = text.index("\n}", start)
    return text[open_at + 1 : end]


def _run_shell_func(case, script, func, stdin="", env=None):
    _need_bash(case)
    body = _extract(script, func)
    harness = "%s() {%s\n}\n%s\n" % (func, body, func)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".sh", delete=False, newline="\n", encoding="utf-8"
    ) as fh:
        fh.write(harness)
        path = fh.name
    try:
        full = {"PATH": "/usr/bin:/bin:/usr/local/bin"}
        full.update(env or {})
        proc = subprocess.run(
            ["bash", path], input=stdin, capture_output=True, text=True, env=full
        )
    finally:
        pathlib.Path(path).unlink(missing_ok=True)
    return proc


def _dump_names(end: datetime.date, days: int):
    """`days` consecutive daily dumps, newest first, in the real filename shape."""
    return [
        "rmc-box-db-%sT020000Z.dump.enc" % (end - datetime.timedelta(days=k)).strftime("%Y%m%d")
        for k in range(days)
    ]


# ---------------------------------------------------------------------------
# The compose file. Structural, because it cannot be executed here.
# ---------------------------------------------------------------------------
class TheComposeFileMustDeclareTheBackupTests(SimpleTestCase):
    """The gap was a missing SERVICE and a missing VOLUME. Pin both."""

    def setUp(self):
        import yaml

        self.raw = _text(COMPOSE_NAME)
        self.doc = yaml.safe_load(self.raw)
        self.services = self.doc.get("services") or {}
        self.volumes = self.doc.get("volumes") or {}

    def test_a_backup_service_exists_at_all(self):
        self.assertIn(
            "backup",
            self.services,
            "deploy/selfhost/docker-compose.yml declares no backup service, so the "
            "school's database has no copy anywhere",
        )

    def test_it_takes_a_pg_dump(self):
        # The mechanism, not just the name. A service called `backup` that runs
        # something else is the same gap wearing a label.
        self.assertIn("pg_dump", _text(BACKUP_NAME))

    def test_the_dumps_land_on_a_volume_that_is_not_pgdata(self):
        mounts = self.services["backup"]["volumes"]
        targets = {m.split(":")[1] for m in mounts if ":" in m}
        sources = {m.split(":")[0] for m in mounts}
        self.assertIn("/backups", targets)
        self.assertIn(
            "backupdata",
            sources,
            "the dumps must go to a volume of their own",
        )
        self.assertNotIn(
            "pgdata",
            sources,
            "a backup on the same volume as the data is not a backup: one "
            "`docker compose down -v` takes the original and the copy together",
        )

    def test_every_volume_the_service_names_is_declared(self):
        mounts = self.services["backup"]["volumes"]
        for mount in mounts:
            source = mount.split(":")[0]
            if source.startswith(".") or source.startswith("/") or "${" in source:
                continue  # bind mount or an interpolated host path
            with self.subTest(volume=source):
                self.assertIn(source, self.volumes)

    def test_the_key_lives_in_a_different_volume_from_the_dumps(self):
        # The whole point of the CA arrangement, applied here: `docker compose cp
        # backup:/backups .` must carry the dumps off the box WITHOUT the key.
        mounts = self.services["backup"]["volumes"]
        pairs = {m.split(":")[1]: m.split(":")[0] for m in mounts if ":" in m}
        self.assertIn("/keys", pairs)
        self.assertNotEqual(pairs["/keys"], pairs["/backups"])

    def test_it_is_not_behind_a_profile(self):
        # edge-tls is opt-in because a school may reasonably choose plain HTTP on its
        # own LAN. No school reasonably chooses to have no copy of its fee ledger, so a
        # bare `docker compose up -d` has to start this.
        self.assertNotIn(
            "profiles",
            self.services["backup"],
            "a profiled backup service is one a plain `up -d` does not start",
        )

    def test_it_runs_the_same_postgres_image_as_the_server(self):
        # pg_dump refuses to dump a server newer than itself. Reusing the db image also
        # means an offline box pulls nothing new to gain a backup service.
        self.assertEqual(
            self.services["backup"]["image"],
            self.services["db"]["image"],
            "the dumper and the server must move versions together",
        )

    def test_the_media_tree_is_mounted_read_only(self):
        mounts = self.services["backup"]["volumes"]
        media = [m for m in mounts if m.startswith("mediadata:")]
        self.assertTrue(media, "media is not reachable, so it can never be archived")
        self.assertTrue(
            media[0].endswith(":ro"),
            "the backup service must never be able to modify a school's uploads",
        )

    def test_web_reads_the_backup_record_but_not_the_passphrase(self):
        # The onboarding runbook refuses go-dark without a verified dump. The web
        # process must see backup-state.json and must never see the key volume.
        mounts = self.services["web"]["volumes"]
        backup_data = [m for m in mounts if m.startswith("backupdata:")]
        self.assertTrue(
            backup_data,
            "web has no backupdata mount, so Django cannot read backup-state.json",
        )
        self.assertTrue(
            any("/backups:ro" in m for m in backup_data),
            "the backup record must be read-only on web",
        )
        self.assertFalse(
            any("backupkeys" in m for m in mounts),
            "the passphrase volume must not be mounted on web",
        )

    def test_it_cannot_take_the_box_down(self):
        # Same house rule as entrypoint.web.sh, where a boot helper must never fail the
        # boot. Nothing may depend on this service, and it must not publish a health
        # claim that something could be made to depend on.
        self.assertNotIn("healthcheck", self.services["backup"])
        for name, body in self.services.items():
            if name == "backup" or not isinstance(body, dict):
                continue
            with self.subTest(service=name):
                self.assertNotIn("backup", body.get("depends_on") or {})

    def test_the_images_own_cmd_cannot_leak_into_the_arguments(self):
        # Overriding `entrypoint` does NOT clear the image's CMD -- docker appends it.
        # This image's CMD is `postgres`, so entrypoint [..., "loop"] with no `command`
        # would have run `box-backup.sh loop postgres`.
        backup = self.services["backup"]
        self.assertEqual(backup["entrypoint"], ["bash", "/usr/local/bin/box-backup.sh"])
        self.assertEqual(backup["command"], ["loop"])

    def test_the_script_it_mounts_actually_exists(self):
        # A compose file that mounts a missing script produces a container that
        # restart-loops, which on a box is indistinguishable from one that works.
        mounts = self.services["backup"]["volumes"]
        local = [m for m in mounts if m.startswith("./")]
        self.assertTrue(local)
        for mount in local:
            with self.subTest(mount=mount):
                self.assertTrue(_p(mount.split(":")[0][2:]).is_file())

    def test_the_off_box_default_is_safe_on_a_box_with_no_such_path(self):
        # A required host bind mount whose source cannot be created fails the whole
        # `up`, which would mean adding backups took the box down. The default has to be
        # a volume NAME (no "/"), which compose accepts everywhere; an operator's
        # absolute path replaces it through the same line.
        mounts = self.services["backup"]["volumes"]
        offbox = [m for m in mounts if m.endswith(":/offbox")]
        self.assertTrue(offbox)
        self.assertIn("RMC_BOX_BACKUP_OFFBOX_DIR", offbox[0])
        default = offbox[0].split(":-")[1].split("}")[0]
        self.assertNotIn("/", default)
        self.assertIn(default, self.volumes)


# ---------------------------------------------------------------------------
# The audit gate.
# ---------------------------------------------------------------------------
class TheAuditMustGateOnAReadBackTests(SimpleTestCase):
    """It is not a backup until it has been read back, and the box must say so."""

    def setUp(self):
        self.text = _text(AUDIT_NAME)
        marker = "RESTORE-DRILL GATE"
        if marker not in self.text:
            self.section = ""
        else:
            start = self.text.index(marker)
            self.section = self.text[start : self.text.index('\nsec "D.', start)]

    def test_there_is_a_restore_drill_gate(self):
        self.assertIn(
            "RESTORE-DRILL GATE",
            self.text,
            "box-audit.sh has no gate on the school's database backup",
        )

    def test_a_missing_read_back_is_a_FAIL_not_a_warning(self):
        # Section C's exact phrasing for the CA, because it is exactly the same claim.
        self.assertIn(
            'bad "no verified read-back on record -- this box cannot show its backup '
            'was ever read back"',
            self.section,
        )

    def test_a_read_back_of_an_OLDER_dump_is_a_FAIL(self):
        # "we verified something once" is not "we verified the newest one". A box whose
        # dumps started failing after the check would otherwise stay green forever.
        self.assertRegex(
            self.section,
            r'bad "the verified read-back is for \$verf, not the newest dump \$lastf',
        )

    def test_a_listed_but_unread_archive_is_a_FAIL(self):
        self.assertIn("never read END TO END", self.section)

    def test_a_box_with_no_backup_service_is_a_FAIL(self):
        self.assertIn("NOTHING is copying the school database", self.section)

    def test_the_added_section_keeps_the_single_quotes_balanced(self):
        """An apostrophe in this file is not a typo, it is a live grenade.

        test_box_rebuild_stamp_guard_2026_08_27 scans box-audit.sh for variables that
        would abort it under `set -u`, and it finds shell-quoted spans with a naive
        `'[^']*'`. Section F runs `sh -c '...'` whose body legitimately expands
        $RMC_EDGE_CREDENTIAL inside the CONTAINER -- correctly ignored, but only while
        the quote pairing lines up. Five prose apostrophes ("the school's records")
        made the count odd, re-paired every span after them, and that scan then
        reported two perfectly-assigned variables as unassigned.

        The failure names variables in section F, so nothing about it points at the
        section that broke it. This test does.
        """
        import re as _re

        nocomment = _re.sub(r"(?m)#.*$", "", self.section)
        self.assertEqual(
            nocomment.count("'") % 2,
            0,
            "the C2 section has an odd number of single quotes, which re-pairs every "
            "quoted span after it and makes the box-audit variable scan lie",
        )

    def test_it_proves_the_encryption_the_way_section_C_does(self):
        self.assertIn("WRONGPASS_OPENS", self.section)
        self.assertIn("it is not actually encrypted", self.section)

    def test_it_warns_when_the_key_sits_beside_the_backups(self):
        # The same warning section C gives about the CA bundle, for the same reason.
        self.assertIn("KEY_ON_BOX", self.section)

    def test_it_says_whether_the_off_box_copy_is_really_off_box(self):
        # Everything on the backup volume dies with the disk. A box whose "off-box"
        # target is a volume on that same disk must be told so, not congratulated.
        self.assertIn("SAME filesystem", self.section)

    def test_the_gate_changes_nothing(self):
        # An audit that took a backup to find out whether backups work would have
        # destroyed the thing it was measuring. Same regex box-audit.sh is already held
        # to by test_box_rebuild_stamp_guard_2026_08_27.
        mutating = re.compile(
            r"^\s*(?:\"\$\{COMPOSE\[@\]\}\"\s+(?:up|down|restart|build|stop|start|rm)"
            r"|docker\s+(?:rm|rmi|kill|stop|start|restart)"
            r"|git\s+(?:checkout|reset|clean|stash|merge|pull)"
            r"|rm\s+-[rf]|mv\s|>\s*/)",
            re.M,
        )
        self.assertEqual(mutating.findall(self.section), [])

    def test_it_never_asks_the_box_to_restore_during_an_audit(self):
        self.assertNotIn("box-backup.sh restore", self.section)
        self.assertNotIn("box-backup.sh once", self.section.split("on demand")[0])

    def test_the_verdict_no_longer_speaks_only_of_the_certificate(self):
        self.assertIn("The CA and the school database are both backed up", self.text)


# ---------------------------------------------------------------------------
# Retention: the real function, executed.
# ---------------------------------------------------------------------------
class TheRetentionArithmeticTests(SimpleTestCase):
    """Run the shipped rule. A retention rule nobody has run either fills a disk or
    silently empties itself, and both look identical from a code review."""

    def _keep(self, names, **env):
        proc = _run_shell_func(
            self, BACKUP_NAME, "retention_keep", stdin="\n".join(names) + "\n", env=env
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return [x for x in proc.stdout.split() if x]

    def test_a_year_of_daily_dumps_settles_at_a_bounded_set(self):
        kept = self._keep(_dump_names(datetime.date(2026, 8, 31), 400))
        # 7 daily + 4 weekly + 3 monthly, overlapping: the newest dump is all three at
        # once, so the theoretical ceiling is 12 and the measured figure is 11.
        self.assertGreaterEqual(len(kept), 9)
        self.assertLessEqual(len(kept), 12)

    def test_the_newest_is_always_kept(self):
        names = _dump_names(datetime.date(2026, 8, 31), 400)
        self.assertIn(names[0], self._keep(names))

    def test_the_last_seven_days_are_all_kept(self):
        names = _dump_names(datetime.date(2026, 8, 31), 400)
        kept = set(self._keep(names))
        for name in names[:7]:
            with self.subTest(name=name):
                self.assertIn(name, kept)

    def test_history_survives_past_the_daily_window(self):
        # The point of the monthly tier: something from two months ago is still here.
        kept = self._keep(_dump_names(datetime.date(2026, 8, 31), 400))
        self.assertTrue(
            any(name.startswith("rmc-box-db-202606") for name in kept),
            "nothing older than the daily window survived: %r" % kept,
        )

    def test_a_shorter_history_keeps_everything_it_has(self):
        names = _dump_names(datetime.date(2026, 8, 31), 5)
        self.assertEqual(sorted(self._keep(names)), sorted(names))

    def test_the_tiers_are_configurable(self):
        names = _dump_names(datetime.date(2026, 8, 31), 400)
        kept = self._keep(names, RET_DAILY="1", RET_WEEKLY="1", RET_MONTHLY="1")
        self.assertEqual(kept, [names[0]])

    def test_a_file_that_is_not_a_dump_is_never_kept(self):
        # The state file and the work directory live in the same place. A retention pass
        # that "kept" backup-state.json would delete it on the next sweep.
        names = _dump_names(datetime.date(2026, 8, 31), 3) + [
            "backup-state.json",
            "rmc-box-media-20260830T020000Z.tar.enc",
            "README",
        ]
        kept = self._keep(names)
        self.assertNotIn("backup-state.json", kept)
        self.assertNotIn("README", kept)

    def test_nothing_in_means_nothing_out(self):
        self.assertEqual(self._keep([""]), [])


class TheByteCapTests(SimpleTestCase):
    """The bound that matters on cheap hardware: bytes, not file count."""

    def _keep(self, rows, cap):
        stdin = "".join("%d\t%s\n" % (b, n) for b, n in rows)
        proc = _run_shell_func(
            self, BACKUP_NAME, "cap_keep", stdin=stdin, env={"CAP_BYTES": str(cap)}
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return [x for x in proc.stdout.split() if x]

    def test_it_stops_at_the_cap(self):
        rows = [(100, "a"), (100, "b"), (100, "c"), (100, "d")]
        self.assertEqual(self._keep(rows, 250), ["a", "b"])

    def test_the_newest_survives_even_when_it_alone_exceeds_the_cap(self):
        # A retention rule that can delete the only backup is worse than no rule. A
        # school whose database outgrew the cap must still have last night's copy.
        self.assertEqual(self._keep([(5_000_000, "only")], 10), ["only"])

    def test_a_zero_cap_means_no_cap(self):
        rows = [(100, "a"), (100, "b")]
        self.assertEqual(self._keep(rows, 0), ["a", "b"])

    def test_a_generous_cap_keeps_everything(self):
        rows = [(100, "a"), (100, "b"), (100, "c")]
        self.assertEqual(self._keep(rows, 10_000), ["a", "b", "c"])


class TheScheduleTests(SimpleTestCase):
    """A school box is switched off at four o'clock. The window has to survive that."""

    def _due(self, last_epoch, interval_hours=None, **env):
        body = _extract(BACKUP_NAME, "is_due")
        helpers = "now_epoch() { date -u +%s; }\n"
        call = "is_due %d%s" % (
            last_epoch,
            "" if interval_hours is None else " %d" % interval_hours,
        )
        harness = "%sis_due() {%s\n}\nif %s; then echo DUE; else echo NOT; fi\n" % (
            helpers,
            body,
            call,
        )
        with tempfile.NamedTemporaryFile(
            "w", suffix=".sh", delete=False, newline="\n", encoding="utf-8"
        ) as fh:
            fh.write(harness)
            path = fh.name
        try:
            full = {"PATH": "/usr/bin:/bin", "INTERVAL_HOURS": "24",
                    "WINDOW_START": "1", "WINDOW_END": "5"}
            full.update(env)
            proc = subprocess.run(
                ["bash", path], capture_output=True, text=True, env=full
            )
        finally:
            pathlib.Path(path).unlink(missing_ok=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.strip()

    def setUp(self):
        _need_bash(self)
        self.now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())

    def test_a_fresh_backup_is_not_due(self):
        self.assertEqual(self._due(self.now - 3600), "NOT")

    def test_a_box_that_is_never_awake_in_the_window_still_gets_backed_up(self):
        # THE ARM THAT MATTERS. A window-only rule would fire never on a box that is
        # switched off every evening, which is most of them -- so half an interval past
        # due, the data matters more than the quiet.
        self.assertEqual(
            self._due(self.now - 40 * 3600, WINDOW_START="1", WINDOW_END="2"),
            "DUE",
        )

    def test_a_box_that_has_never_been_backed_up_is_due_immediately(self):
        self.assertEqual(self._due(0), "DUE")

    def test_an_always_open_window_takes_a_backup_as_soon_as_it_is_due(self):
        self.assertEqual(
            self._due(self.now - 25 * 3600, WINDOW_START="0", WINDOW_END="24"),
            "DUE",
        )

    def test_a_longer_interval_is_honoured(self):
        # Media is weekly, the drill monthly. Both go through this same rule.
        week = 168
        self.assertEqual(self._due(self.now - 3 * 24 * 3600, week), "NOT")
        self.assertEqual(
            self._due(self.now - 8 * 24 * 3600, week, WINDOW_START="0", WINDOW_END="24"),
            "DUE",
        )

    def test_the_heavy_jobs_go_through_the_window_rule_too(self):
        # A whole-tree tar and a whole-database restore are the two heaviest things
        # this service does. A bare age comparison would start one at eleven on a
        # Tuesday morning, on a mini-PC a school is teaching from.
        loop = _extract(BACKUP_NAME, "run_loop")
        self.assertIn('is_due "${S_MEDIA_EPOCH:-0}" "$MEDIA_INTERVAL_HOURS"', loop)
        self.assertIn('is_due "${S_DRILL_EPOCH:-0}"', loop)


# ---------------------------------------------------------------------------
# The encryption contract, exercised on real bytes.
# ---------------------------------------------------------------------------
class TheEncryptionIsRealTests(SimpleTestCase):
    """The script's own openssl invocation, run against real bytes.

    No Postgres here, so the payload is a stand-in that starts with the `PGDMP` magic
    the read-back actually checks for. What is under test is the crypto contract, and
    that part is not simulated.
    """

    def setUp(self):
        _need_bash(self)
        if shutil.which("openssl") is None:
            self.skipTest("openssl not available")
        text = _text(BACKUP_NAME)
        self.enc_args = re.search(r"^ENC_ARGS=\(.*\)$", text, re.M).group(0)
        self.wrong = re.search(r'^WRONG_PASS="(.*)"$', text, re.M).group(1)
        self.enc_fn = re.search(r"^encrypt_to\(\) \{.*\}$", text, re.M).group(0)
        self.dec_fn = re.search(r"^decrypt_from\(\) \{.*\}$", text, re.M).group(0)
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="agent-d-enc-"))
        self.addCleanup(shutil.rmtree, self.dir, True)

    def _sh(self, script):
        path = self.dir / "harness.sh"
        path.write_bytes(script.encode())
        return subprocess.run(
            ["bash", str(path)], capture_output=True, text=True,
            env={"PATH": "/usr/bin:/bin:/usr/local/bin:/mingw64/bin"},
        )

    def _prelude(self):
        d = self.dir.as_posix()
        return (
            "set -uo pipefail\n"
            'PASS_FILE="%s/pass.txt"\n' % d
            + "%s\n%s\n%s\n" % (self.enc_args, self.enc_fn, self.dec_fn)
        )

    def test_the_round_trip_returns_exactly_what_went_in(self):
        d = self.dir.as_posix()
        (self.dir / "pass.txt").write_bytes(b"a-real-passphrase-44-chars-long-aaaaaaaaaaaa\n")
        payload = b"PGDMP" + bytes(range(256)) * 40
        (self.dir / "plain.bin").write_bytes(payload)
        proc = self._sh(
            self._prelude()
            + 'encrypt_to "%s/out.enc" < "%s/plain.bin" || exit 1\n' % (d, d)
            + 'decrypt_from "%s/out.enc" "%s/back.bin" || exit 2\n' % (d, d)
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual((self.dir / "back.bin").read_bytes(), payload)

    def test_the_ciphertext_does_not_contain_the_plaintext(self):
        d = self.dir.as_posix()
        (self.dir / "pass.txt").write_bytes(b"a-real-passphrase-44-chars-long-aaaaaaaaaaaa\n")
        secret = b"PGDMP" + b"STUDENT-FEE-LEDGER-ROW" * 200
        (self.dir / "plain.bin").write_bytes(secret)
        proc = self._sh(
            self._prelude() + 'encrypt_to "%s/out.enc" < "%s/plain.bin"\n' % (d, d)
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        blob = (self.dir / "out.enc").read_bytes()
        self.assertNotIn(b"STUDENT-FEE-LEDGER-ROW", blob)
        self.assertNotIn(b"PGDMP", blob)

    def test_the_wrong_passphrase_does_not_produce_a_postgres_archive(self):
        # This is the claim box-audit.sh reports as "the encryption is real". It is
        # asserted here against the literal the script itself tries.
        d = self.dir.as_posix()
        (self.dir / "pass.txt").write_bytes(b"a-real-passphrase-44-chars-long-aaaaaaaaaaaa\n")
        (self.dir / "plain.bin").write_bytes(b"PGDMP" + b"x" * 4096)
        proc = self._sh(
            self._prelude()
            + 'encrypt_to "%s/out.enc" < "%s/plain.bin"\n' % (d, d)
            + 'printf "%s\\n" > "%s/wrong.txt"\n' % (self.wrong, d)
            + 'PASS_FILE="%s/wrong.txt"\n' % d
            + 'decrypt_from "%s/out.enc" "%s/bad.bin"; echo "RC=$?"\n' % (d, d)
        )
        self.assertIn("RC=", proc.stdout)
        bad = self.dir / "bad.bin"
        opened = bad.exists() and bad.read_bytes()[:5] == b"PGDMP"
        self.assertFalse(opened, "a wrong passphrase opened the dump")

    def test_the_iteration_count_is_not_a_token_gesture(self):
        # pbkdf2 with a low iteration count is a passphrase-shaped decoration.
        self.assertIn("-pbkdf2", self.enc_args)
        iters = int(re.search(r"-iter (\d+)", self.enc_args).group(1))
        self.assertGreaterEqual(iters, 100000)
        self.assertIn("-salt", self.enc_args)


# ---------------------------------------------------------------------------
# It must never take the box down.
# ---------------------------------------------------------------------------
class TheBackupMustNeverTakeTheBoxDownTests(SimpleTestCase):
    """entrypoint.web.sh's house rule: a helper must never fail the thing it helps."""

    def setUp(self):
        self.text = _text(BACKUP_NAME)

    def test_the_loop_does_not_run_under_set_e(self):
        # One failed dump must record itself and let the loop continue. An appliance
        # that stops backing up because a single run failed has quietly become an
        # appliance with no backups.
        first = self.text[: self.text.index("# --- configuration")]
        self.assertIn("set -uo pipefail", first)
        self.assertNotIn("set -euo pipefail", first)

    def test_a_failed_or_skipped_run_still_returns_zero(self):
        # Every early exit inside the backup path. A non-zero return under
        # `restart: unless-stopped` is a container restart loop.
        body = self.text[self.text.index("run_backup() {") : self.text.index("# --- media")]
        self.assertNotIn("exit 1", body)
        self.assertGreaterEqual(body.count("return 0"), 3)

    def test_a_full_disk_skips_the_run_instead_of_filling_it(self):
        self.assertIn('S_LAST_STATUS="skipped"', self.text)
        self.assertIn("Filling the disk stops Postgres writing", self.text)

    def test_the_free_space_check_comes_before_the_dump(self):
        space_at = self.text.index('free="$(free_bytes)"')
        dump_at = self.text.index("nice -n 19 pg_dump")
        self.assertLess(space_at, dump_at)

    def test_the_space_requirement_covers_the_dump_and_its_read_back(self):
        # The read-back writes a decrypted copy beside the encrypted one, so one dump's
        # worth of headroom would put the box exactly at zero during verification.
        self.assertIn("need=$(( est * 2 + MIN_FREE_BYTES ))", self.text)

    def test_the_dump_cannot_queue_behind_a_migration_forever(self):
        # pg_dump takes ACCESS SHARE locks; queued behind a migration's ACCESS EXCLUSIVE
        # it blocks everything behind it. Bounded, so a backup is never the reason a
        # teacher's page waits.
        self.assertIn("--lock-wait-timeout", self.text)

    def test_it_yields_the_cpu_of_a_mini_pc(self):
        self.assertIn("nice -n 19 pg_dump", self.text)

    def test_a_dump_that_will_not_read_back_is_deleted_not_kept(self):
        # Keeping it would let retention count it as a backup, and the count is what an
        # operator looks at.
        self.assertIn("the unreadable dump has been deleted", self.text)


class ThePlaintextNeverTouchesTheDiskTests(SimpleTestCase):
    def setUp(self):
        self.text = _text(BACKUP_NAME)

    def test_the_dump_is_piped_straight_into_the_encryptor(self):
        self.assertRegex(self.text, r"pg_dump[^\n]*\n[^\n]*\n?\s*\| encrypt_to")

    def test_pg_dump_is_never_given_an_output_file(self):
        # `pg_dump -f` would write a readable copy of a school's records to the disk,
        # even briefly, and "briefly" on a box means "until the next backup".
        #
        # Scoped to the pg_dump INVOCATION, not to a byte window after it: the cleanup
        # a few lines below is a legitimate `rm -f`, and a window wide enough to reach
        # it would fail on the correct file -- which is how a test teaches people to
        # delete it rather than read it.
        start = self.text.index("nice -n 19 pg_dump")
        command = self.text[start : self.text.index("| encrypt_to", start)]
        for flag in (" -f ", "--file="):
            with self.subTest(flag=flag):
                self.assertNotIn(flag, command)

    def test_a_broken_pipe_leaves_no_partial_file_behind(self):
        self.assertIn("PIPESTATUS", self.text)
        self.assertIn('rm -f "$tmp"', self.text)


# ---------------------------------------------------------------------------
# The read-back contract.
# ---------------------------------------------------------------------------
class TheReadBackContractTests(SimpleTestCase):
    def setUp(self):
        self.text = _text(BACKUP_NAME)
        self.verify = _extract(BACKUP_NAME, "verify_dump")

    def test_it_checks_the_archive_magic(self):
        self.assertIn("PGDMP", self.verify)

    def test_it_reads_the_whole_archive_not_only_the_table_of_contents(self):
        # A dump truncated by a full disk decrypts fine and lists fine. This is the only
        # step that catches it, and it costs no disk because the SQL goes to /dev/null.
        self.assertIn("pg_restore -f /dev/null", self.verify)

    def test_it_refuses_an_archive_that_is_not_this_application(self):
        self.assertIn("EXPECT_TABLE", self.verify)
        self.assertIn("MIN_TOC_ENTRIES", self.verify)

    def test_it_tries_a_wrong_passphrase_on_purpose(self):
        self.assertIn("WRONG_PASS", self.verify)

    def test_the_read_back_is_recorded_where_the_audit_reads_it(self):
        # A record nothing reads is a log line. These three are the gate's evidence.
        for key in ("verified_at", "verified_file", "verified_full_read"):
            with self.subTest(key=key):
                self.assertIn('"%s"' % key, self.text)
                self.assertIn(key, _text(AUDIT_NAME))

    def test_the_encryption_claim_is_proven_live_not_read_from_the_record(self):
        # `encryption_real` IS recorded, for `status` -- but the audit asks the file on
        # disk right now instead of trusting a flag somebody wrote down, exactly as
        # section C re-opens the CA bundle rather than reading a note about it.
        self.assertIn('"encryption_real"', self.text)
        self.assertIn("WRONGPASS_OPENS", _text(AUDIT_NAME))

    def test_a_restore_refuses_a_dump_that_does_not_read_back(self):
        # There is no sense dropping a working database for a file already known bad.
        restore = _extract(BACKUP_NAME, "do_restore")
        self.assertIn("if ! verify_dump", restore)
        self.assertIn("Refusing to drop a working database", restore)

    def test_a_restore_into_the_live_database_needs_the_long_flag(self):
        restore = _extract(BACKUP_NAME, "do_restore")
        self.assertIn("--yes-destroy-current-data", restore)
        self.assertIn("--single-transaction", restore)


class TheHostRestoreScriptTests(SimpleTestCase):
    def setUp(self):
        self.text = _text(RESTORE_NAME)

    def test_it_refuses_without_the_explicit_flag(self):
        self.assertIn("--yes-destroy-current-data", self.text)
        self.assertIn("there is no undo", self.text)

    def test_it_stops_the_writers_before_restoring(self):
        stop_at = self.text.index('"${COMPOSE[@]}" stop "${APP_SERVICES[@]}"')
        restore_at = self.text.index('restore "$WHICH"')
        self.assertLess(stop_at, restore_at)

    def test_the_app_comes_back_on_every_exit_path(self):
        # A failed restore is recoverable. A box nobody restarted is a school locked out
        # until somebody notices.
        self.assertIn("trap restart_app EXIT", self.text)

    def test_it_only_stops_the_writers_never_the_database(self):
        self.assertIn("APP_SERVICES=(web worker beat)", self.text)
        self.assertNotIn("APP_SERVICES=(web worker beat db)", self.text)

    def test_every_subcommand_it_names_is_one_the_backup_script_implements(self):
        # A runbook that names a command which is not there is worse than no runbook.
        implemented = set(
            re.findall(r"^\s{4}([a-z|-]+)\)", _text(BACKUP_NAME), re.M)
        )
        implemented = {part for entry in implemented for part in entry.split("|")}
        used = set(re.findall(r"box-backup\.sh (?:\\\s*\n\s*)?([a-z-]+)", self.text))
        self.assertTrue(used)
        self.assertEqual(used - implemented, set())


# ---------------------------------------------------------------------------
# The scripts have to run on a Linux box.
# ---------------------------------------------------------------------------
class TheNewScriptsMustRunOnTheBoxTests(SimpleTestCase):
    """The usual ways a shell script written on Windows stops working on Linux."""

    def test_both_parse(self):
        _need_bash(self)
        for name in NEW_SCRIPTS:
            with self.subTest(script=name):
                proc = subprocess.run(
                    ["bash", "-n", str(_p(name))], capture_output=True, text=True
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_neither_is_CRLF(self):
        # A CRLF here is `$'\r': command not found` on the first line that matters,
        # which reads as a missing binary rather than a line-ending problem.
        for name in NEW_SCRIPTS:
            with self.subTest(script=name):
                self.assertEqual(_p(name).read_bytes().count(b"\r\n"), 0)

    def test_no_control_characters_survived_an_edit(self):
        for name in NEW_SCRIPTS:
            with self.subTest(script=name):
                raw = _p(name).read_bytes()
                bad = sorted({b for b in raw if b < 9 or (13 < b < 32)})
                self.assertEqual(bad, [])

    def test_every_variable_used_is_one_that_exists(self):
        # `set -u` turns an unbound variable into an abrupt exit, and on the backup
        # script that exit would be silent -- nothing watches this container.
        known = {
            "BASH_SOURCE", "PATH", "HOME", "PWD", "USER", "IFS", "SHELL", "TERM",
            "PIPESTATUS", "LC_ALL", "LANG", "OSTYPE", "HOSTNAME", "TZ",
            "PGHOST", "PGPORT", "PGUSER", "PGPASSWORD",
            # Read bare only inside `if [ -n "${RMC_BOX_BACKUP_PASSPHRASE:-}" ]`, the
            # same shape and the same allowance the CA passphrase already has in
            # test_box_rebuild_stamp_guard_2026_08_27.
            "RMC_BOX_BACKUP_PASSPHRASE",
        }
        for name in NEW_SCRIPTS:
            with self.subTest(script=name):
                text = _text(name)
                assigned = set(
                    re.findall(
                        r"(?:^|;|\bthen\b|\belse\b|\bdo\b|\bexport\b|\blocal\b)\s*"
                        r"([A-Z][A-Z0-9_]*)=",
                        text,
                        re.M,
                    )
                )
                assigned |= set(re.findall(r"\bfor\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\b", text))
                scannable = re.sub(r"(?m)#.*$", "", text)
                scannable = re.sub(r"'[^']*'", "''", scannable)
                used = set(re.findall(r"\$([A-Z][A-Z0-9_]*)\b", scannable))
                used |= set(re.findall(r"\$\{([A-Z][A-Z0-9_]*)[}\[]", scannable))
                missing = sorted(used - assigned - known)
                self.assertEqual(missing, [], "%s uses unassigned %r" % (name, missing))

    def test_the_git_attributes_keep_them_LF_on_a_box(self):
        # The working tree is what the box checks out and executes.
        attrs = (REPO / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("*.sh text eol=lf", attrs)


# ---------------------------------------------------------------------------
# The runbook.
# ---------------------------------------------------------------------------
class TheRunbookTests(SimpleTestCase):
    def setUp(self):
        self.path = REPO / "docs" / "EDGE_BOX_BACKUP_RUNBOOK.md"
        if not self.path.is_file():
            self.fail("docs/EDGE_BOX_BACKUP_RUNBOOK.md is missing")
        self.text = self.path.read_text(encoding="utf-8")

    def test_it_states_the_media_decision(self):
        self.assertIn("Media is backed up", self.text)
        self.assertIn("weekly", self.text.lower())

    def test_it_states_the_disk_bound_with_its_assumptions(self):
        self.assertIn("Worst case on disk", self.text)
        self.assertIn("150 MiB", self.text)

    def test_it_describes_an_automated_mechanism_not_a_manual_procedure(self):
        # The repo's stated preference: automate a runbook rather than document steps a
        # human has to remember at 3am.
        self.assertIn("What happens without anyone doing anything", self.text)

    def test_every_command_it_tells_an_operator_to_run_exists(self):
        for script in re.findall(r"deploy/selfhost/([a-z-]+\.sh)", self.text):
            with self.subTest(script=script):
                self.assertTrue(_p(script).is_file())

    def test_it_names_what_is_deliberately_not_backed_up(self):
        self.assertIn("What it deliberately does not back up", self.text)
        self.assertIn(".env", self.text)

    def test_the_platform_dr_runbook_now_knows_edge_boxes_exist(self):
        # The finding was that DR_BACKUP_RESTORE_RUNBOOK.md contained none of "edge",
        # "box", "selfhost" or "sovereign".
        dr = (REPO / "docs" / "DR_BACKUP_RESTORE_RUNBOOK.md").read_text(encoding="utf-8")
        for word in ("Sovereign", "edge", "box"):
            with self.subTest(word=word):
                self.assertIn(word, dr)
        self.assertIn("EDGE_BOX_BACKUP_RUNBOOK.md", dr)
