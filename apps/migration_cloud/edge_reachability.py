"""Before an import writes to a box: say what will never leave it.

THE FAILURE THIS EXISTS TO END
------------------------------
The edge delta rail registers 17 entities. 370 models carry a ``school`` relation, so
353 of them are on no rail at all. A model that is not registered does not fail to
sync loudly -- it produces **no error, no conflict and no refusal**. The rows are
written, the import reports APPLIED, the board is green, and the data simply stays
where it was written, forever, with nothing anywhere saying so.

That silence is the whole problem. An operator importing a school's history onto an
appliance is making a decision about where that school's records live, and today the
decision is made FOR them, by which landers happen to write which models, and they
find out when the box dies.

Measured on 2026-09-02 (``scripts/audit_lander_write_reachability.py``): of the 35
tenant models the landers write, **23 are on no rail**, and **21 of the 33 canonical
domains a school can import put NOTHING on the cloud** except the importer's own
bookkeeping. Health records, library loans, bus routes, hostel rooms, meal balances,
discipline incidents, staff payroll, transcripts, athletics fixtures, every message
ever sent, and every guardian account an import creates land on the box and stop
there. All 33 domains strand something, because the residual-capture net writes
``DynamicFieldValue`` behind every one of them.

WHAT THIS MODULE DOES
---------------------
Answers, for one bundle, before the first write: which domains it will land, how many
rows those are, and which of the models behind them can reach the cloud. Then it says
so somewhere a person will see -- the Review & Import page, the live event stream, and
a durable record on the bundle -- rather than in a log line on a machine in a
cupboard.

IT DOES NOT BLOCK BY DEFAULT, AND THAT IS DELIBERATE
----------------------------------------------------
A box being the system of record for a domain is a legitimate, common, often correct
choice: a school with no reliable uplink genuinely wants its library on the appliance.
Refusing that import would be wrong. What is not acceptable is making that choice by
accident. So the default is ``warn`` -- loud, durable, operator-visible -- and a
deployment that wants the stricter posture sets the policy to ``refuse``, at which
point an unacknowledged stranding stops the import instead of quietly completing it.

Acknowledging is the third state and the point of the whole design: an operator who
has read the warning records the decision on the bundle, and from then on the import
proceeds under ``refuse`` too, with the choice attributable rather than assumed.

ON A CLOUD DEPLOYMENT THIS IS INERT
------------------------------------
The cloud IS the destination; nothing written there is stranded. The guard is scoped
to a sovereign box (``sync_engine.edge_enabled``) so a multi-tenant deployment pays
nothing and sees nothing.

WHY THE ROW COUNTS CAN BE A FLOOR
----------------------------------
``MigrationArtifact.row_count`` is null for a format the profiler could not count
rows in (PDF, binary, pre-profile). Those artifacts are counted SEPARATELY and the
total is labelled a FLOOR, never presented as a total. A number printed next to a
pile of things that could not be read is not a measurement.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from django.utils.translation import gettext_lazy as _

from .landers.write_targets import is_import_bookkeeping, write_targets_for

logger = logging.getLogger(__name__)

#: Configuration key, resolved through ``apps.migration_cloud.defaults`` (tenant
#: SiteSettings -> env -> RuntimeDefaults -> seed), never read from a literal here.
POLICY_KEY = "migration_cloud.edge.stranded_write_policy"

POLICY_OFF = "off"
POLICY_WARN = "warn"
POLICY_REFUSE = "refuse"
VALID_POLICIES = (POLICY_OFF, POLICY_WARN, POLICY_REFUSE)

#: Where the assessment is recorded on the bundle so the review page, the API and a
#: later audit all read the same answer.
SUMMARY_KEY = "edge_stranded_writes"
#: Where an operator's explicit "this box is the system of record for these domains"
#: decision is recorded.
ACK_KEY = "edge_stranded_ack"


class StrandedWriteRefused(Exception):
    """Raised when policy is ``refuse`` and the stranding was never acknowledged."""


def _humanise(names: list[str]) -> str:
    """``["a"]`` -> ``"a"``; ``["a","b","c"]`` -> ``"a, b and c"``."""
    names = sorted(names)
    if len(names) <= 1:
        return names[0] if names else ""
    return "%s and %s" % (", ".join(names[:-1]), names[-1])


def _uncounted(domains: list["DomainStranding"]) -> int:
    return sum(d.artifacts_without_row_count for d in domains)


def _rows_phrase(rows: int, uncounted: int) -> str:
    """``"120 rows"`` or ``"at least 120 rows (1 file could not be row-counted)"``.

    Says FLOOR wherever a file could not be counted, and gets the plural right:
    "1 files" in a warning about data loss reads as a machine nobody proof-read,
    which is exactly when a person stops believing the number next to it.
    """
    unit = "row" if rows == 1 else "rows"
    if not uncounted:
        return "%d %s" % (rows, unit)
    files = "file" if uncounted == 1 else "files"
    return "at least %d %s (%d %s could not be row-counted)" % (
        rows, unit, uncounted, files,
    )


@dataclass
class DomainStranding:
    """One canonical domain in this bundle, and where its rows can end up."""

    domain: str
    artifacts: int = 0
    rows: int = 0
    #: Artifacts whose ``row_count`` this deployment could not determine. Their rows
    #: are real; they are simply not in ``rows``, which is why ``rows`` is a floor
    #: whenever this is non-zero.
    artifacts_without_row_count: int = 0
    reaches_cloud: tuple[str, ...] = ()
    insert_held: tuple[str, ...] = ()
    stranded: tuple[str, ...] = ()
    stranded_bookkeeping: tuple[str, ...] = ()
    acknowledged: bool = False

    @property
    def counts_are_complete(self) -> bool:
        return self.artifacts_without_row_count == 0

    @property
    def nothing_reaches_cloud(self) -> bool:
        """No model this domain writes can be created on the cloud.

        This is the distinction that decides what an operator is told, and
        collapsing it is how a warning stops meaning anything. A ``students``
        artifact lands ``people.StudentProfile``, which rides: the ROWS reach the
        cloud and only the unmapped source COLUMNS stay behind. A ``library``
        artifact lands ``schoolops.LibraryItem``, which rides nothing: the rows
        themselves never leave. Telling a school "900 student rows will stay on this
        box" because their spreadsheet had one column nobody mapped would be false,
        and the next real warning would be ignored.
        """
        return not self.reaches_cloud

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "nothing_reaches_cloud": self.nothing_reaches_cloud,
            "artifacts": self.artifacts,
            "rows": self.rows,
            "artifacts_without_row_count": self.artifacts_without_row_count,
            "counts_are_complete": self.counts_are_complete,
            "reaches_cloud": list(self.reaches_cloud),
            "insert_held": list(self.insert_held),
            "stranded": list(self.stranded),
            "stranded_bookkeeping": list(self.stranded_bookkeeping),
            "acknowledged": self.acknowledged,
        }


@dataclass
class StrandedWriteReport:
    """What this import will put on this box that can never leave it."""

    is_edge: bool = False
    policy: str = POLICY_WARN
    domains: list[DomainStranding] = field(default_factory=list)
    #: True when the rail could not be resolved on this deployment. The report then
    #: carries NO figures at all rather than a reassuring zero.
    rail_unavailable: bool = False

    @property
    def stranding_domains(self) -> list[DomainStranding]:
        return [d for d in self.domains if d.stranded]

    @property
    def box_only_domains(self) -> list[DomainStranding]:
        """Domains where the ROWS themselves can never leave."""
        return [d for d in self.stranding_domains if d.nothing_reaches_cloud]

    @property
    def partial_domains(self) -> list[DomainStranding]:
        """Domains whose rows sync but whose unmapped source columns do not."""
        return [d for d in self.stranding_domains if not d.nothing_reaches_cloud]

    @property
    def insert_held_domains(self) -> list[DomainStranding]:
        """Domains writing a model the rail carries but refuses to CREATE."""
        return [d for d in self.domains if d.insert_held]

    @property
    def rows_box_only(self) -> int:
        return sum(d.rows for d in self.box_only_domains)

    @property
    def rows_partial(self) -> int:
        return sum(d.rows for d in self.partial_domains)

    @property
    def rows_stranded(self) -> int:
        """Rows whose CONTENT cannot leave. The two buckets add up to this.

        Deliberately NOT the sum over every domain that strands anything: that
        figure counted a fully-syncing student roster as lost because one column
        did not map, and a number that overstates is discarded exactly as fast as
        one that understates.
        """
        return self.rows_box_only

    @property
    def artifacts_without_row_count(self) -> int:
        return sum(d.artifacts_without_row_count for d in self.stranding_domains)

    @property
    def counts_are_complete(self) -> bool:
        return self.artifacts_without_row_count == 0

    @property
    def acknowledged(self) -> bool:
        """True only when EVERY stranding domain was acknowledged.

        Partial acknowledgement is not acknowledgement: a domain nobody has ruled on
        is exactly the case this module exists to surface.
        """
        stranding = self.stranding_domains
        return bool(stranding) and all(d.acknowledged for d in stranding)

    @property
    def has_finding(self) -> bool:
        return bool(self.stranding_domains)

    def stranded_models(self) -> list[str]:
        out: set[str] = set()
        for d in self.stranding_domains:
            out.update(d.stranded)
        return sorted(out)

    def operator_message(self) -> str:
        """What a person needs, in the order they need it. Never a bare total.

        Written in English and NOT translated on purpose: this exact string is
        recorded on the bundle and emitted into the import's durable event stream,
        so a sentence written during a French session would read in French forever
        to whoever opens the record later. The page TITLE beside it is translated.
        """
        if not self.has_finding:
            return ""
        parts: list[str] = []
        if self.box_only_domains:
            parts.append(
                "This appliance cannot sync %s. Importing here writes %s that will "
                "stay on this box and can never reach the cloud copy of this school."
                % (
                    _humanise([d.domain for d in self.box_only_domains]),
                    _rows_phrase(self.rows_box_only,
                                 _uncounted(self.box_only_domains)),
                )
            )
        if self.partial_domains:
            parts.append(
                "%s will sync, but the source columns that did not map to a field "
                "(%s) stay on this box."
                % (
                    _rows_phrase(self.rows_partial,
                                 _uncounted(self.partial_domains)).capitalize(),
                    _humanise([d.domain for d in self.partial_domains]),
                )
            )
        if self.insert_held_domains:
            parts.append(
                "Records this import creates in %s cannot be created on the cloud at "
                "all, even though the rail carries that model: creating them is an "
                "authentication decision the cloud will not delegate."
                % _humanise([d.domain for d in self.insert_held_domains])
            )
        return " ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_edge": self.is_edge,
            "policy": self.policy,
            "rail_unavailable": self.rail_unavailable,
            "has_finding": self.has_finding,
            "acknowledged": self.acknowledged,
            "rows_stranded": self.rows_stranded,
            "rows_box_only": self.rows_box_only,
            "rows_partial": self.rows_partial,
            "box_only_domains": [d.domain for d in self.box_only_domains],
            "partial_domains": [d.domain for d in self.partial_domains],
            "insert_held_domains": [d.domain for d in self.insert_held_domains],
            "artifacts_without_row_count": self.artifacts_without_row_count,
            "counts_are_complete": self.counts_are_complete,
            "stranded_models": self.stranded_models(),
            "domains": [d.to_dict() for d in self.domains],
            "message": self.operator_message(),
        }


# --- Deployment + policy ----------------------------------------------------

def deployment_is_edge() -> bool:
    """Is this deployment an appliance, where "cannot leave" is a real outcome?

    Asks ``sync_engine.edge_enabled`` rather than re-deriving: a sovereign box is one
    OR a paired one, and that answer already has one owner. A box that is sovereign
    but not yet paired is very much an edge deployment -- more so, if anything, since
    nothing it holds is leaving at all.
    """
    try:
        from apps.sync_engine.edge_enabled import edge_sync_enabled, is_sovereign_box

        return bool(is_sovereign_box() or edge_sync_enabled())
    except Exception:  # noqa: BLE001 -- an unbootable sync app must not break an import
        logger.debug("edge_reachability: could not determine deployment shape", exc_info=True)
        return False


def stranded_write_policy() -> str:
    """``off`` / ``warn`` (default) / ``refuse``, from the configurability cascade."""
    try:
        from . import defaults as mc_defaults

        raw = str(mc_defaults.get(POLICY_KEY) or "").strip().lower()
    except Exception:  # noqa: BLE001 -- bootstrap / unmigrated DB
        logger.debug("edge_reachability: policy lookup failed, defaulting to warn",
                     exc_info=True)
        return POLICY_WARN
    return raw if raw in VALID_POLICIES else POLICY_WARN


def _rail_labels() -> tuple[set[str], set[str]] | None:
    """(labels on the rail, labels the rail refuses to CREATE), lower-cased.

    ``None`` when the rail cannot be resolved here. That is reported as
    ``rail_unavailable`` and suppresses every figure: a coverage report that could
    not read the registry must not print zero stranded rows, because zero and
    "I could not look" are the same shape and opposite meanings.
    """
    try:
        from apps.sync_engine.rail_coverage import rail_entity_config
    except Exception:  # noqa: BLE001
        logger.debug("edge_reachability: rail_coverage unavailable", exc_info=True)
        return None
    try:
        config = rail_entity_config()
    except Exception:  # noqa: BLE001
        logger.debug("edge_reachability: rail registry could not be derived", exc_info=True)
        return None

    held_entities: set[str] = set()
    try:
        from apps.api import sync_services

        held_entities = {
            str(e) for e in (getattr(sync_services, "_INSERT_HELD_ENTITIES", None) or ())
        }
    except Exception:  # noqa: BLE001 -- an unreadable hold list is not a rail failure
        logger.debug("edge_reachability: insert-hold list unavailable", exc_info=True)

    on_rail: set[str] = set()
    insert_held: set[str] = set()
    for entity, (model, _fields) in config.items():
        label = model._meta.label_lower
        on_rail.add(label)
        if str(entity) in held_entities:
            insert_held.add(label)
    return on_rail, insert_held


# --- Assessment -------------------------------------------------------------

def acknowledged_domains(bundle: Any) -> set[str]:
    """Domains an operator has explicitly accepted as box-resident.

    Stored on the bundle rather than in settings on purpose: the decision is about
    THIS school's THIS import, and a deployment-wide switch would let one
    acknowledgement silence every future import of every domain.
    """
    summary = getattr(bundle, "mapping_summary", None) or {}
    ack = summary.get(ACK_KEY) or {}
    domains = ack.get("domains") if isinstance(ack, dict) else None
    if not isinstance(domains, (list, tuple, set)):
        return set()
    return {str(d).strip() for d in domains if str(d).strip()}


def assess(bundle: Any, jobs: Any) -> StrandedWriteReport:
    """What ``jobs`` will write, and how much of it can never leave this box.

    ``jobs`` is the orchestrator's ``list[_ArtifactJob]`` -- taken as an argument
    rather than rebuilt, so the guard measures exactly the work the apply is about
    to do, not a second opinion about it.
    """
    report = StrandedWriteReport(
        is_edge=deployment_is_edge(),
        policy=stranded_write_policy(),
    )
    if not report.is_edge or report.policy == POLICY_OFF:
        # Nothing is stranded where the cloud IS the destination, and the review page
        # polls this. Answer before touching the rail registry, so a multi-tenant
        # deployment pays nothing per request for a question that does not apply to it.
        return report
    rails = _rail_labels()
    if rails is None:
        report.rail_unavailable = True
        return report
    on_rail, insert_held_labels = rails
    acked = acknowledged_domains(bundle)

    by_domain: dict[str, DomainStranding] = {}
    for job in jobs or ():
        domain = str(getattr(job, "domain", "") or "").strip() or "custom_fields"
        entry = by_domain.get(domain)
        if entry is None:
            entry = _classify_domain(domain, on_rail, insert_held_labels)
            entry.acknowledged = domain in acked
            by_domain[domain] = entry
        entry.artifacts += 1
        rows = getattr(getattr(job, "artifact", None), "row_count", None)
        if rows is None:
            entry.artifacts_without_row_count += 1
        else:
            try:
                entry.rows += int(rows)
            except (TypeError, ValueError):
                entry.artifacts_without_row_count += 1

    report.domains = [by_domain[d] for d in sorted(by_domain)]
    return report


def _classify_domain(domain: str, on_rail: set[str],
                     insert_held_labels: set[str]) -> DomainStranding:
    reaches, held, stranded, bookkeeping = [], [], [], []
    for label in write_targets_for(domain):
        lower = label.lower()
        if lower not in on_rail:
            (bookkeeping if is_import_bookkeeping(label) else stranded).append(label)
        elif lower in insert_held_labels:
            # Registered, but the rail refuses to CREATE it on the cloud -- minting a
            # login is an authentication decision, not a replication one. Registered
            # is not the same as insertable, and reporting it as "reaches the cloud"
            # would be a lie an operator acts on.
            held.append(label)
        else:
            reaches.append(label)
    return DomainStranding(
        domain=domain,
        reaches_cloud=tuple(sorted(reaches)),
        insert_held=tuple(sorted(held)),
        stranded=tuple(sorted(stranded)),
        stranded_bookkeeping=tuple(sorted(bookkeeping)),
    )


def preview_for_bundle(bundle: Any) -> StrandedWriteReport:
    """The same assessment, for a page rendered BEFORE anyone presses Apply.

    Builds the jobs the way the orchestrator would. Read-only.
    """
    try:
        from .orchestrator import _build_jobs

        jobs = _build_jobs(bundle)
    except Exception:  # noqa: BLE001 -- a preview must never break the review page
        logger.debug("edge_reachability: could not build jobs for preview", exc_info=True)
        return StrandedWriteReport(is_edge=deployment_is_edge(),
                                   policy=stranded_write_policy())
    return assess(bundle, jobs)


# --- The guard ---------------------------------------------------------------

def guard_before_apply(bundle: Any, jobs: Any, *, dry_run: bool = False,
                       emit: Any = None) -> StrandedWriteReport:
    """Warn (or refuse) BEFORE the first tenant row is written.

    Called from ``orchestrator._apply_bundle_inner`` after the jobs are built and
    before the dependency waves run -- the one point every entry path converges on
    (the wizard's Apply, the customer self-serve approval, the DRF endpoint, the
    Celery task, the HeavyWorkOutbox drain, ``repair_bundle``, the transfer FSM and
    ``mc_recover_import``). Putting it on the button would have covered one of those.

    Raises :class:`StrandedWriteRefused` only when the policy is ``refuse`` AND the
    operator has not acknowledged the stranding. Never raises under the default.
    """
    report = assess(bundle, jobs)
    if not report.is_edge or report.policy == POLICY_OFF:
        return report
    if report.rail_unavailable:
        logger.warning(
            "edge_reachability: bundle %s -- the sync rail could not be resolved on "
            "this deployment, so no stranded-write assessment was possible. This is "
            "NOT a finding of zero.",
            getattr(bundle, "pk", None),
        )
        return report
    if not report.has_finding:
        return report

    _record(bundle, report)
    message = report.operator_message()
    if emit is not None:
        try:
            emit(
                bundle_id=getattr(bundle, "pk", None),
                kind="warning",
                stage="APPLYING",
                message=message,
            )
        except Exception:  # noqa: BLE001 -- surfacing a warning never breaks an apply
            logger.debug("edge_reachability: progress emit failed", exc_info=True)

    # A dry run is a PREVIEW: its entire job is to show what a real apply would do,
    # and refusing one would flip the bundle to FAILED for a run that was never going
    # to write anything. The orchestrator keeps a dry run's durable status untouched
    # for exactly this reason; refusing here would undo that.
    if report.policy == POLICY_REFUSE and not report.acknowledged and not dry_run:
        raise StrandedWriteRefused(message)

    logger.warning(
        "edge_reachability: bundle %s -- %s (policy=%s, acknowledged=%s, dry_run=%s)",
        getattr(bundle, "pk", None), message, report.policy,
        report.acknowledged, dry_run,
    )
    return report


def _record(bundle: Any, report: StrandedWriteReport) -> None:
    """Persist the assessment on the bundle so it outlives the log buffer."""
    try:
        bundle.mapping_summary = {
            **(getattr(bundle, "mapping_summary", None) or {}),
            SUMMARY_KEY: report.to_dict(),
        }
        bundle.save(update_fields=["mapping_summary", "updated_at"])
    except Exception:  # noqa: BLE001 -- recording the warning must not break the apply
        logger.debug("edge_reachability: could not record the assessment", exc_info=True)


def acknowledge(bundle: Any, domains: Any, *, actor: str = "") -> set[str]:
    """Record an operator's decision that this box owns these domains.

    Returns the full acknowledged set. Additive: acknowledging ``library`` does not
    un-acknowledge ``health``, and acknowledging nothing changes nothing.
    """
    wanted = {str(d).strip() for d in (domains or ()) if str(d).strip()}
    if not wanted:
        return acknowledged_domains(bundle)
    merged = acknowledged_domains(bundle) | wanted
    from django.utils import timezone

    summary = dict(getattr(bundle, "mapping_summary", None) or {})
    summary[ACK_KEY] = {
        "domains": sorted(merged),
        "acknowledged_at": timezone.now().isoformat(),
        "acknowledged_by": str(actor or ""),
    }
    bundle.mapping_summary = summary
    bundle.save(update_fields=["mapping_summary", "updated_at"])
    return merged


# --- Operator-facing copy ----------------------------------------------------

def review_notice(bundle: Any) -> dict[str, Any] | None:
    """The banner the Review & Import page shows BEFORE Apply is pressed.

    ``None`` on a cloud deployment, when the policy is off, when nothing is stranded,
    or when the rail could not be read (in which case the caller is told so through
    ``rail_unavailable`` rather than shown a reassuring absence).

    TITLES ARE TRANSLATED; THE MESSAGE IS NOT, AND THAT IS ON PURPOSE. A title is
    per-request UI copy. The message is the same sentence recorded durably on the
    bundle and emitted into the import's event stream, so translating it would mean a
    record written during a French session reads in French forever, to whoever opens
    it later. Lazy proxies are resolved to ``str`` here because this dict is
    JSON-serialised into the page and into the poller response.
    """
    report = preview_for_bundle(bundle)
    if not report.is_edge or report.policy == POLICY_OFF:
        return None
    if report.rail_unavailable:
        return {
            "kind": "edge_stranding_unknown",
            "title": str(_("This appliance could not check what it can sync")),
            "message": str(_(
                "The sync rail could not be read on this box, so we cannot tell you "
                "which of these records would be able to reach the cloud. This is not "
                "a clean result -- it is a check that did not run."
            )),
            "domains": [],
            "blocking": False,
        }
    if not report.has_finding:
        return None
    return {
        "kind": "edge_stranding",
        "title": str(_("Some of this import will stay on this appliance")),
        "message": report.operator_message(),
        "rows": report.rows_stranded,
        "rows_partial": report.rows_partial,
        "counts_are_complete": report.counts_are_complete,
        "artifacts_without_row_count": report.artifacts_without_row_count,
        "acknowledged": report.acknowledged,
        "blocking": report.policy == POLICY_REFUSE and not report.acknowledged,
        "domains": [
            {
                "domain": d.domain,
                "rows": d.rows,
                "counts_are_complete": d.counts_are_complete,
                "nothing_reaches_cloud": d.nothing_reaches_cloud,
                "stranded": list(d.stranded),
                "acknowledged": d.acknowledged,
            }
            for d in report.stranding_domains
        ],
    }


__all__ = [
    "ACK_KEY",
    "DomainStranding",
    "POLICY_KEY",
    "POLICY_OFF",
    "POLICY_REFUSE",
    "POLICY_WARN",
    "SUMMARY_KEY",
    "StrandedWriteRefused",
    "StrandedWriteReport",
    "acknowledge",
    "acknowledged_domains",
    "assess",
    "deployment_is_edge",
    "guard_before_apply",
    "preview_for_bundle",
    "review_notice",
    "stranded_write_policy",
]
