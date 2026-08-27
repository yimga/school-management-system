"""OTA read its bearer credential from a Django setting that does not exist.

FOUND ON A LIVE BOX. `manage.py edge_apply_upgrade` ended in:

    File "/app/apps/sync_engine/local_upgrade.py", line 235, in fetch_target_manifest
      with urllib.request.urlopen(request, timeout=60) as response:
    urllib.error.HTTPError: HTTP Error 401: Unauthorized

The same endpoint, asked with the credential the rest of sync_engine uses, answers:

    HTTP 409 {"ok":false,"error":"not_released",
              "detail":"not yet released to stable (currently canary)"}

So the box was never unauthorised. `RMC_EDGE_SYNC_TOKEN` occurred exactly twice in
the tree -- the line that read it, and the --token help text that documented it --
and was defined in neither settings.py, the settings registry, nor
.env.edge.example. It always resolved to "", so every unattended upgrade sent
`Authorization: Bearer ` with nothing after it.

WHY IT SURVIVED: a wrong setting NAME fails identically to a revoked token. Both are
a bare 401, and the box holds a credential that demonstrably works for sync -- so
every reading of that 401 pointed at the cloud, or at the credential, or at pairing.
Nothing pointed at the one place the credential was being read from.

These are SimpleTestCase: resolving a credential is a lookup, and the moment it
matters is a box coming up, possibly before anything else is ready.
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.sync_engine.local_upgrade import LocalRuntimeUpgradeManager

BINDING = "apps.sync_engine.edge_binding.edge_credential"
PAIRED = "paired-credential-from-the-database"
FROM_ENV = "credential-from-the-environment"


class TheUpgradeManagerResolvesTheRealCredentialTests(SimpleTestCase):
    def test_it_uses_the_credential_the_rest_of_sync_engine_uses(self):
        with mock.patch(BINDING, return_value=PAIRED):
            self.assertEqual(LocalRuntimeUpgradeManager().token, PAIRED)

    def test_a_paired_box_is_covered_and_an_env_var_would_not_have_been(self):
        # A box that was PAIRED rather than configured by hand keeps its credential in
        # the database. Reading the environment finds nothing there, so an env-only
        # fix would leave exactly the boxes the pairing flow was built for still 401ing.
        with mock.patch.dict("os.environ", {"RMC_EDGE_CREDENTIAL": ""}, clear=False):
            with mock.patch(BINDING, return_value=PAIRED):
                self.assertEqual(LocalRuntimeUpgradeManager().token, PAIRED)

    def test_an_explicit_token_still_wins(self):
        # `--token` exists so an operator can drive one upgrade by hand without
        # touching the box's stored identity.
        with mock.patch(BINDING, return_value=PAIRED):
            manager = LocalRuntimeUpgradeManager(token="typed-by-hand")
            self.assertEqual(manager.token, "typed-by-hand")

    @override_settings(RMC_EDGE_SYNC_TOKEN="a-setting-nobody-defines")
    def test_the_setting_that_never_existed_is_not_consulted_again(self):
        # Someone reading the old code could conclude RMC_EDGE_SYNC_TOKEN is the
        # supported knob and set it. It must not silently take precedence over the
        # box's real credential -- that would rebuild the same failure with a
        # plausible-looking value in it, which is worse than an empty one.
        with mock.patch(BINDING, return_value=PAIRED):
            self.assertEqual(LocalRuntimeUpgradeManager().token, PAIRED)

    def test_an_unbootable_registry_falls_back_instead_of_raising(self):
        # This module is importable from an entrypoint. A credential lookup must not
        # be the thing that turns a half-booted box into a traceback -- the box needs
        # to reach a state where somebody can log in and see what is wrong.
        with mock.patch(BINDING, side_effect=RuntimeError("apps not loaded")):
            with mock.patch.dict(
                "os.environ", {"RMC_EDGE_CREDENTIAL": FROM_ENV}, clear=False
            ):
                self.assertEqual(LocalRuntimeUpgradeManager().token, FROM_ENV)

    def test_no_credential_anywhere_is_empty_and_not_a_crash(self):
        # An unpaired box is a normal state, not an error. run() guards on an empty
        # token; it must get an empty string to guard on.
        with mock.patch(BINDING, return_value=""):
            with mock.patch.dict("os.environ", {"RMC_EDGE_CREDENTIAL": ""}, clear=False):
                self.assertEqual(LocalRuntimeUpgradeManager().token, "")


class TheDeadSettingIsGoneFromTheTreeTests(SimpleTestCase):
    def test_nothing_reads_RMC_EDGE_SYNC_TOKEN_any_more(self):
        # A grep-style assertion on purpose. The defect was not that the value was
        # wrong -- it was that a name nobody defines looked like configuration, in
        # source and in `--help`. Re-introducing it anywhere should fail here.
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[2]
        offenders = []
        for path in root.rglob("*.py"):
            if "test_ota_credential" in path.name:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if "RMC_EDGE_SYNC_TOKEN" in line and not line.lstrip().startswith("#"):
                    offenders.append("%s:%d" % (path.relative_to(root), number))
        self.assertEqual(offenders, [], "RMC_EDGE_SYNC_TOKEN is defined nowhere; " "reading it always yields an empty bearer token")
