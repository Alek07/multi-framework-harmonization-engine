"""UCM-46 - The signed baseline as a declaration of applicability, read off the ledger.

The engine already produced everything a recognised baseline document has to
show — inclusions and exclusions with written justifications, explicit gaps,
provenance and jurisdiction, tiers and phases, a human signature with its reason.
What it did not do was *emit* it as the artefact a reviewer expects to see. That
is all this module is: a projection, in the same sense as `listing.py`, and with
the same property behind it — it computes nothing and stores nothing, so it
cannot say anything the trail does not already say.

Three decisions shape the document, and each is a claim the TFM has to be able to
defend rather than a convenience.

* **The unit is the capability, and only mechanisms can be excluded.** An
  ISO/IEC 27001 Statement of Applicability has the control as its unit and asks
  for each one whether it applies. Here gating removes mechanisms and never
  required capabilities (UCM-9), so no row of this document can say that a
  requirement does not apply: what the rows carry is *how* each requirement is
  met, and each mechanism underneath carries its own disposition — chosen,
  ratified, compensatory, merely offered, discarded, or excluded by a named rule
  on an observed premise. The correspondence with the SoA is therefore exact at
  the level of the discipline (justified inclusion, justified exclusion, nothing
  silent) and deliberately not at the level of the unit.
* **Everything the run touched is listed, not only what was signed.** Every
  capability of every zone leaves a row, because the invariant this project
  measures is 0 silent omissions and a document that only listed the chosen ones
  could not be checked against it. What was *not* part of the signature — Tier 1
  the operator did not decide about — is listed as `roadmap` and flagged
  `in_signed_baseline=False`, so the reader can tell a recommendation from a
  commitment.
* **The mechanisms nobody took stay in.** A declaration that lists only the
  chosen control cannot show that there was anything to choose between, and
  equivalent options side by side is the central contribution (UCM-16). They are
  listed as `offered`, which is a fact about the composition and not a leftover.

The document reports the catalog and rules recorded in the ledger, not the ones
installed today. That is a consequence of projecting rather than recomputing, and
it is the right behaviour: the baseline was signed under those versions and the
same signature over another catalog would be another baseline (invariant 3).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from app.audit.schemas import (
    AuditActor,
    AuditEventRead,
    AuditEventType,
    ChainVerification,
)
from app.baseline.schemas import (
    INCLUDED_DISPOSITIONS,
    BaselineStatement,
    CapabilityOutcome,
    MechanismDisposition,
    StatementCounts,
    StatementGap,
    StatementMandate,
    StatementMechanism,
    StatementRow,
    StatementZone,
)
from app.core.config import settings
from app.core.wording import say, strength_words
from app.engine.schemas import CapabilityStatus, PriorityTier

# The engine entries a row is built from. One `MANDATE_RECORDED` or
# `PRIORITY_ASSIGNED` exists per capability per zone — prioritisation walks every
# capability of the catalog — so this is also what guarantees the row set is
# complete without the document having to consult the catalog.
_PRIORITY_EVENTS = frozenset(
    {AuditEventType.MANDATE_RECORDED, AuditEventType.PRIORITY_ASSIGNED}
)

_HUMAN_DISPOSITIONS: dict[AuditEventType, MechanismDisposition] = {
    AuditEventType.OPTION_SELECTED: MechanismDisposition.SELECTED,
    AuditEventType.OPTION_REJECTED: MechanismDisposition.REJECTED,
    AuditEventType.COMPENSATORY_DECLARED: MechanismDisposition.COMPENSATORY,
}

# What this document does not claim. Carried inside the artefact so that it
# cannot be cited as something it never said it was.
LIMITATIONS = (
    "No es un anexo de conformidad de ninguna norma. Es la línea base compuesta y firmada en "
    "este motor, presentada con las disciplinas que esas normas exigen para documentarla.",
    "La unidad de cada fila es la capacidad, no el control: en este motor el gating excluye "
    "mecanismos y nunca capacidades exigidas, así que ninguna fila puede declarar que un "
    "requisito no aplica. Las exclusiones justificadas viven un nivel más abajo, en cada "
    "mecanismo.",
    "Las descripciones del catálogo están parafraseadas y nunca son literales de las normas; "
    "los identificadores oficiales se citan para poder localizar el control en su fuente.",
    "Se proyecta de la bitácora, así que refleja las versiones de catálogo y reglas que "
    "gobernaron la firma — no las instaladas hoy. Si difieren, la que da fe es la de la firma.",
)


class StatementNotFoundError(LookupError):
    """No signature for that baseline in this ledger — so there is nothing to declare."""


def statement_of(
    events: list[AuditEventRead], baseline_id: UUID, chain: ChainVerification
) -> BaselineStatement:
    """The declaration for one signed baseline, projected from its own trail.

    `events` is what `GET /baseline/{id}/audit-log` serves: the engine's run *and*
    the human's decisions on top of it, in ledger order.
    """
    return _Projection(events, baseline_id).document(chain)


class _Projection:
    """Indexes one baseline's trail once, then reads the document off it."""

    def __init__(self, events: list[AuditEventRead], baseline_id: UUID) -> None:
        self.baseline_id = baseline_id
        self.signed = _signature(events, baseline_id)
        self.run_id = self.signed.run_id

        # The engine's entries are the run's — they are written before a baseline
        # exists, which is why they carry no baseline id. The human's are stamped
        # with it, and filtering on it is what keeps a second composition over
        # another run from leaking into this document.
        self.engine = [
            event
            for event in events
            if event.actor is AuditActor.ENGINE and event.run_id == self.run_id
        ]
        self.human = [
            event
            for event in events
            if event.actor is AuditActor.HUMAN and event.baseline_id == baseline_id
        ]

        self.mapped = self._one_per_capability(AuditEventType.CAPABILITY_MAPPED)
        self.retrieved = self._one_per_capability(AuditEventType.CANDIDATES_RETRIEVED)
        self.status = self._one_per_capability(AuditEventType.CAPABILITY_STATUS_SET)
        self.priority = self._one_per_capability(*_PRIORITY_EVENTS)
        self.gaps = self._many_per_capability(AuditEventType.GAP_DECLARED)
        self.excluded = self._many_per_capability(AuditEventType.MECHANISM_EXCLUDED)
        self.decisions = self._human_decisions()

    # --- the document ---------------------------------------------------------

    def document(self, chain: ChainVerification) -> BaselineStatement:
        payload = self.signed.payload or {}
        zones = [self._zone(event) for event in self._zone_events()]
        counts = _totalled(zone.counts for zone in zones)

        return BaselineStatement(
            baseline_id=self.baseline_id,
            run_id=self.run_id,
            profile_id=self.signed.profile_id,
            profile_name=str(payload.get("profile_name") or self.signed.profile_id),
            signed_by=self.signed.actor_ref or "",
            signed_at=self.signed.recorded_at,
            signature_rationale=self.signed.rationale,
            versions=dict(self.signed.versions or {}),
            tier_0_complete=bool(payload.get("tier_0_complete", False)),
            zones=zones,
            counts=counts,
            chain=chain,
            audit_log_path=(
                f"{settings.API_V1_PREFIX}/baseline/{self.baseline_id}/audit-log"
            ),
            rationale=_document_rationale(counts, len(zones)),
            limitations=list(LIMITATIONS),
        )

    def _zone(self, derived: AuditEventRead) -> StatementZone:
        payload = derived.payload or {}
        zone_id = derived.zone_id or str(payload.get("zone_id", ""))
        rows = [
            self._row(zone_id, event)
            for event in self.priority.values()
            if event.zone_id == zone_id
        ]
        counts = _counted(rows)
        # Read off the rows rather than taken from the signature's own tally: a
        # document that quoted the claim it is meant to evidence would evidence
        # nothing.
        complete = not any(
            row.tier is PriorityTier.TIER_0 and row.outcome is CapabilityOutcome.OPEN_GAP
            for row in rows
        )

        return StatementZone(
            zone_id=zone_id,
            domain=_optional_str(payload.get("domain")),
            target_sl=_optional_int(payload.get("target_sl")),
            safety_relevant=_optional_bool(payload.get("safety_relevant")),
            role=_optional_str(payload.get("role")),
            tier_0_complete=complete,
            rows=rows,
            counts=counts,
            rationale=_zone_rationale(zone_id, payload, counts, complete),
        )

    def _row(self, zone_id: str, priority: AuditEventRead) -> StatementRow:
        capability_id = priority.capability_id or ""
        key = (zone_id, capability_id)
        payload = priority.payload or {}

        decisions = self.decisions.get(key, [])
        # Ratifying is not choosing, and the document has to be able to say which
        # happened — so the operator's *choices* are the entries that are not
        # ratifications. A row ratified at signing is included in the baseline and
        # is still not one the operator decided; claiming otherwise would put a
        # deliberation on the record that never took place (UCM-16).
        choices = [
            event
            for event in decisions
            if event.event_type is not AuditEventType.MECHANISM_RATIFIED
        ]
        mechanisms = self._mechanisms(key, decisions)
        gap = self._gap(key, payload)
        gap_accepted = any(
            event.event_type is AuditEventType.GAP_ACCEPTED for event in decisions
        )
        status = _status(payload.get("status"))
        tier = _tier(payload.get("tier"))
        # The same rule the signed baseline is composed under (`service._zone`):
        # all of Tier 0, plus the discretionary capabilities the operator decided
        # about. Anything else is a recommendation, and is labelled as one.
        signed = tier is PriorityTier.TIER_0 or bool(decisions)

        included = [m for m in mechanisms if m.included]
        return StatementRow(
            zone_id=zone_id,
            capability_id=capability_id,
            capability_name=self._name(key, capability_id),
            tier=tier,
            phase=_optional_int(payload.get("phase")),
            priority=_optional_str(payload.get("priority")),
            layer=_optional_str(payload.get("layer")),
            status=status,
            outcome=_outcome(signed, gap_accepted, mechanisms, status),
            in_signed_baseline=signed,
            outstanding=bool(payload.get("outstanding", False)),
            coverage=_optional_float(payload.get("coverage")),
            mandates=_mandates(payload.get("mandates")),
            jurisdictions=_distinct(m.jurisdiction for m in included),
            frameworks=_distinct(m.framework for m in included),
            mechanisms=mechanisms,
            gap=gap,
            gap_accepted=gap_accepted,
            decided_by_human=bool(choices),
            human_rationale=_joined(event.rationale for event in choices) or None,
            engine_rationale=priority.rationale,
            audit_sequences=sorted(
                {priority.sequence}
                | {event.sequence for event in decisions}
                | {event.sequence for event in self.excluded.get(key, [])}
                | {event.sequence for event in self.gaps.get(key, [])}
            ),
        )

    # --- mechanisms -----------------------------------------------------------

    def _mechanisms(
        self, key: tuple[str, str], decisions: list[AuditEventRead]
    ) -> list[StatementMechanism]:
        """Every mechanism this capability ever had on the table, in ledger order.

        Built in three passes that layer over one another — what the catalog
        offered, what gating ruled out, what the human decided — because that is
        the order in which the three actually happen and the later one is allowed
        to contradict the earlier one *on the record*.
        """
        mechanisms: dict[str, dict[str, Any]] = {}
        for option in self._options(key):
            self._offer(mechanisms, option)
        for event in self.excluded.get(key, []):
            self._exclude(mechanisms, event)
        for event in decisions:
            self._decide(mechanisms, key, event)
        return [StatementMechanism(**fields) for fields in mechanisms.values()]

    def _offer(self, mechanisms: dict[str, dict[str, Any]], option: dict[str, Any]) -> None:
        control = option.get("control") or {}
        mapping = option.get("mapping") or {}
        control_id = str(control.get("id") or "")
        if not control_id:  # pragma: no cover - a candidate always names its control
            return

        provenance = mapping.get("provenance") or {}
        mechanisms[control_id] = {
            "control_id": control_id,
            "official_id": _optional_str(control.get("official_id")),
            "framework": _optional_str(control.get("framework")),
            "jurisdiction": _optional_str(control.get("jurisdiction")),
            "strength": _strength(control.get("strength")),
            "mapping_type": _optional_str(mapping.get("type") or mapping.get("mapping_type")),
            "coverage_weight": _optional_float(mapping.get("coverage_weight")),
            "provenance": _optional_str(provenance.get("source")),
            "disposition": MechanismDisposition.OFFERED,
            "included": False,
            "rationale": str(option.get("status_reason") or ""),
            "audit_sequences": [],
        }

    def _exclude(self, mechanisms: dict[str, dict[str, Any]], event: AuditEventRead) -> None:
        control_id = event.control_id or ""
        if not control_id:  # pragma: no cover - an exclusion always names its mechanism
            return

        payload = event.payload or {}
        outcome = str(payload.get("outcome") or "")
        fields = mechanisms.setdefault(control_id, _unknown_mechanism(control_id))
        fields.update(
            disposition=_disposition(outcome),
            included=False,
            rule_id=event.rule_id,
            evidence=[str(item) for item in payload.get("evidence") or []],
            compensation=_optional_str(payload.get("compensation")),
            deferred_to=_optional_str(payload.get("deferred_to")),
            rationale=event.rationale,
        )
        fields["audit_sequences"] = [*fields["audit_sequences"], event.sequence]

    def _decide(
        self,
        mechanisms: dict[str, dict[str, Any]],
        key: tuple[str, str],
        event: AuditEventRead,
    ) -> None:
        """The operator's word, over anything the engine said about the mechanism.

        Ratification is read from the payload rather than from `control_id`: it is
        one entry that may cover several retained mechanisms, and it is a
        different act from choosing — which is precisely why it has its own event
        type (UCM-16).
        """
        payload = event.payload or {}
        if event.event_type is AuditEventType.MECHANISM_RATIFIED:
            for control_id in payload.get("ratified_control_ids") or []:
                self._apply(
                    mechanisms, key, str(control_id), MechanismDisposition.RATIFIED, event
                )
            return

        disposition = _HUMAN_DISPOSITIONS.get(event.event_type)
        if disposition is None or not event.control_id:
            # `gap_accepted` — the one human decision that names no mechanism,
            # because accepting a gap is accepting that there is none.
            return
        self._apply(mechanisms, key, event.control_id, disposition, event)

    def _apply(
        self,
        mechanisms: dict[str, dict[str, Any]],
        key: tuple[str, str],
        control_id: str,
        disposition: MechanismDisposition,
        event: AuditEventRead,
    ) -> None:
        payload = event.payload or {}
        fields = mechanisms.get(control_id)
        if fields is None:
            # Not among the catalog's candidates for this capability: an adopted
            # suggestion. What is known about it comes from the retrieval entry,
            # and it is never given a mapping type or a coverage weight — it has
            # neither, and lending it one would launder it into a mapping.
            fields = self._suggested(key, control_id)
            mechanisms[control_id] = fields

        fields.update(
            disposition=disposition,
            included=disposition in INCLUDED_DISPOSITIONS,
            rationale=event.rationale,
        )
        if payload.get("origin") == "adopted_suggestion":
            fields["adopted"] = True
        if payload.get("gating_excluded"):
            fields["despite_gating"] = str(payload["gating_excluded"])
        fields["audit_sequences"] = [*fields["audit_sequences"], event.sequence]

    def _suggested(self, key: tuple[str, str], control_id: str) -> dict[str, Any]:
        """A control the RAG pass offered and the catalog does not map here."""
        fields = _unknown_mechanism(control_id)
        event = self.retrieved.get(key)
        if event is None:
            return fields

        for suggestion in (event.payload or {}).get("suggestions") or []:
            if str(suggestion.get("control_id")) != control_id:
                continue
            fields.update(
                official_id=_optional_str(suggestion.get("official_id")),
                framework=_optional_str(suggestion.get("framework")),
                jurisdiction=_optional_str(suggestion.get("jurisdiction")),
            )
            break
        return fields

    def _options(self, key: tuple[str, str]) -> list[dict[str, Any]]:
        event = self.mapped.get(key)
        if event is None:
            return []
        options = (event.payload or {}).get("options")
        return [option for option in options if isinstance(option, dict)] if options else []

    # --- what the ledger says about one capability ----------------------------

    def _gap(self, key: tuple[str, str], payload: dict[str, Any]) -> StatementGap | None:
        """The gap as prioritisation carried it, or the last one declared for it.

        Prioritisation's own copy is preferred because it is the reading that
        survived the whole pipeline; the declared entries are the fallback for a
        gap that never reached it.
        """
        declared = payload.get("gap")
        if isinstance(declared, dict):
            return StatementGap.model_validate(declared)

        events = self.gaps.get(key, [])
        if not events:
            return None
        return StatementGap.model_validate(events[-1].payload or {})

    def _name(self, key: tuple[str, str], capability_id: str) -> str:
        for source in (self.mapped.get(key), self.retrieved.get(key)):
            if source is None:
                continue
            name = (source.payload or {}).get("capability_name")
            if name:
                return str(name)
        return capability_id

    # --- indexes --------------------------------------------------------------

    def _zone_events(self) -> list[AuditEventRead]:
        seen: set[str] = set()
        zones: list[AuditEventRead] = []
        for event in self.engine:
            if event.event_type is not AuditEventType.ZONE_DERIVED:
                continue
            zone_id = event.zone_id or ""
            if zone_id in seen:
                continue
            seen.add(zone_id)
            zones.append(event)
        return zones

    def _one_per_capability(
        self, *event_types: AuditEventType
    ) -> dict[tuple[str, str], AuditEventRead]:
        """The last entry of these types per (zone, capability). Insertion-ordered.

        Last rather than first so that a stage which revisits a capability is read
        at its final word; the ledger is append-only, so "revisited" is itself on
        the record.
        """
        wanted = frozenset(event_types)
        index: dict[tuple[str, str], AuditEventRead] = {}
        for event in self.engine:
            if event.event_type not in wanted:
                continue
            key = _key(event)
            if key is not None:
                index[key] = event
        return index

    def _many_per_capability(
        self, event_type: AuditEventType
    ) -> dict[tuple[str, str], list[AuditEventRead]]:
        index: dict[tuple[str, str], list[AuditEventRead]] = {}
        for event in self.engine:
            if event.event_type is not event_type:
                continue
            key = _key(event)
            if key is not None:
                index.setdefault(key, []).append(event)
        return index

    def _human_decisions(self) -> dict[tuple[str, str], list[AuditEventRead]]:
        """The operator's per-capability entries, in the order they made them.

        The signature itself is not one of them: it closes the whole baseline
        rather than deciding a capability, and counting it as a decision would
        make every capability look individually decided.
        """
        index: dict[tuple[str, str], list[AuditEventRead]] = {}
        for event in self.human:
            if event.event_type is AuditEventType.BASELINE_SIGNED:
                continue
            key = _key(event)
            if key is not None:
                index.setdefault(key, []).append(event)
        return index


# --- reading one payload field ------------------------------------------------


def _signature(events: Iterable[AuditEventRead], baseline_id: UUID) -> AuditEventRead:
    for event in events:
        if (
            event.event_type is AuditEventType.BASELINE_SIGNED
            and event.baseline_id == baseline_id
        ):
            return event
    raise StatementNotFoundError(str(baseline_id))


def _key(event: AuditEventRead) -> tuple[str, str] | None:
    if event.zone_id is None or event.capability_id is None:
        return None
    return (event.zone_id, event.capability_id)


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _optional_int(value: Any) -> int | None:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_float(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _optional_bool(value: Any) -> bool | None:
    return bool(value) if isinstance(value, bool) else None


def _strength(value: Any) -> str | None:
    """The Spanish phrase for a control's declared demand, from its stored shape."""
    if not isinstance(value, dict):
        return _optional_str(value)
    kind = value.get("kind")
    if kind is None:
        return None
    level = _optional_int(value.get("level"))
    return strength_words(str(kind), level, str(value.get("note") or ""))


def _status(value: Any) -> CapabilityStatus | None:
    try:
        return CapabilityStatus(value)
    except ValueError:
        return None


def _tier(value: Any) -> PriorityTier:
    """Tier 1 when the ledger does not say, because Tier 0 is a claim, not a default."""
    try:
        return PriorityTier(value)
    except ValueError:
        return PriorityTier.TIER_1


def _disposition(outcome: str) -> MechanismDisposition:
    try:
        return MechanismDisposition(outcome)
    except ValueError:  # pragma: no cover - gating has exactly three outcomes
        return MechanismDisposition.NOT_APPLICABLE


def _unknown_mechanism(control_id: str) -> dict[str, Any]:
    return {
        "control_id": control_id,
        "disposition": MechanismDisposition.OFFERED,
        "included": False,
        "rationale": "",
        "audit_sequences": [],
    }


def _mandates(value: Any) -> list[StatementMandate]:
    if not isinstance(value, list):
        return []
    return [
        StatementMandate.model_validate(item) for item in value if isinstance(item, dict)
    ]


def _distinct(values: Iterable[str | None]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen


def _joined(values: Iterable[str]) -> str:
    return " · ".join(value for value in values if value)


# --- the two derived judgements -----------------------------------------------


def _outcome(
    signed: bool,
    gap_accepted: bool,
    mechanisms: list[StatementMechanism],
    status: CapabilityStatus | None,
) -> CapabilityOutcome:
    """How the capability ended up, in the order the ledger settles it.

    The order is not arbitrary. A written acceptance of the gap is the strongest
    statement the operator can make about a capability and it excludes the rest
    (`service._check_coherent` refuses a composition that says both); a declared
    compensatory control is the next, because it says the objective stands and the
    mechanism does not exist here; only then does a chosen or ratified mechanism
    count. Gating's own reading is the fallback for a capability nobody had to
    decide.
    """
    if not signed:
        return CapabilityOutcome.ROADMAP
    if gap_accepted:
        return CapabilityOutcome.ACCEPTED_GAP
    if any(m.disposition is MechanismDisposition.COMPENSATORY for m in mechanisms):
        return CapabilityOutcome.COMPENSATED
    if any(m.included for m in mechanisms):
        return CapabilityOutcome.IMPLEMENTED
    if status is CapabilityStatus.DEFERRED_TO_ORGANIZATIONAL_LAYER:
        return CapabilityOutcome.DEFERRED
    if status is CapabilityStatus.COMPENSATORY_REQUIRED:
        return CapabilityOutcome.COMPENSATED
    return CapabilityOutcome.OPEN_GAP


def _counted(rows: list[StatementRow]) -> StatementCounts:
    outcomes = [row.outcome for row in rows]
    mechanisms = [mechanism for row in rows for mechanism in row.mechanisms]
    dispositions = [mechanism.disposition for mechanism in mechanisms]

    return StatementCounts(
        capabilities=len(rows),
        tier_0=sum(1 for row in rows if row.tier is PriorityTier.TIER_0),
        tier_1=sum(1 for row in rows if row.tier is PriorityTier.TIER_1),
        signed=sum(1 for row in rows if row.in_signed_baseline),
        implemented=outcomes.count(CapabilityOutcome.IMPLEMENTED),
        compensated=outcomes.count(CapabilityOutcome.COMPENSATED),
        deferred=outcomes.count(CapabilityOutcome.DEFERRED),
        accepted_gaps=outcomes.count(CapabilityOutcome.ACCEPTED_GAP),
        open_gaps=outcomes.count(CapabilityOutcome.OPEN_GAP),
        roadmap=outcomes.count(CapabilityOutcome.ROADMAP),
        included_mechanisms=sum(1 for mechanism in mechanisms if mechanism.included),
        offered_not_taken=dispositions.count(MechanismDisposition.OFFERED),
        rejected_mechanisms=dispositions.count(MechanismDisposition.REJECTED),
        justified_exclusions=dispositions.count(MechanismDisposition.NOT_APPLICABLE),
        compensatory_requirements=dispositions.count(
            MechanismDisposition.OBJECTIVE_WITHOUT_MECHANISM
        ),
        organizational_deferrals=dispositions.count(MechanismDisposition.WRONG_SCOPE),
    )


def _totalled(counts: Iterable[StatementCounts]) -> StatementCounts:
    totals = dict.fromkeys(StatementCounts.model_fields, 0)
    for zone in counts:
        for field in totals:
            totals[field] += int(getattr(zone, field))
    return StatementCounts(**totals)


# --- the sentences the document reads as --------------------------------------


def _zone_rationale(
    zone_id: str, payload: dict[str, Any], counts: StatementCounts, complete: bool
) -> str:
    domain = say(str(payload.get("domain", "")))
    target = payload.get("target_sl")
    return (
        f"Zona {zone_id} ({domain}, SL-objetivo {target}): {counts.capabilities} capacidad(es) "
        f"exigida(s) del catálogo, {counts.signed} dentro de lo firmado. "
        f"{counts.implemented} cubierta(s) por un mecanismo elegido o ratificado, "
        f"{counts.compensated} por un control compensatorio, {counts.deferred} diferida(s) a la "
        f"capa organizativa y {counts.accepted_gaps} hueco(s) asumido(s) por escrito. El bloque "
        f"obligatorio de esta zona está {'completo' if complete else 'incompleto'}. "
        f"{counts.justified_exclusions} exclusión(es) justificada(s) de mecanismos: no son huecos, "
        "son un entregable de la línea base — cada una con su regla declarada y la premisa del "
        "perfil que la disparó."
    )


def _document_rationale(counts: StatementCounts, zones: int) -> str:
    return (
        f"Declaración de aplicabilidad de la línea base firmada: {counts.capabilities} "
        f"capacidad(es) exigida(s) en {zones} zona(s), cada una con su decisión, su justificación "
        f"escrita y su referencia a la bitácora. {counts.included_mechanisms} mecanismo(s) "
        f"incorporado(s), {counts.offered_not_taken} ofrecido(s) y no tomado(s), "
        f"{counts.justified_exclusions} excluido(s) con justificación, "
        f"{counts.compensatory_requirements} objetivo(s) sin mecanismo en el activo y "
        f"{counts.organizational_deferrals} desplazado(s) a la capa organizativa. Ninguna "
        "capacidad exigida desaparece del documento: el gating quita mecanismos, nunca "
        "capacidades, y lo que no se cubre se declara como hueco con su residuo. El documento se "
        "proyecta de la bitácora firmada y no recalcula nada, así que no puede decir nada que la "
        "traza no diga."
    )
