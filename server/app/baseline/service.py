"""Sovereign composition: the human chooses, the engine verifies, both sign.

The central contribution of the TFM. The engine has already laid equivalent
options side by side (`POST /candidates`); this endpoint takes the operator's
choices, checks the one thing that is not negotiable, and records the whole thing
with the operator's name and reasons on it. It never picks a control.

Four checks stand between a request and a signature:

1. The run exists and is this profile's — the composition chains onto it.
2. The versioned inputs have not moved since the run; otherwise the options on
   screen are not the ones this process would compute now.
3. The mandatory block is complete: every outstanding mandate is closed by the
   human, and the signature is refused while any is open.
4. A run is signed once — a second signature would produce two baselines over the
   same evidence.

The core is re-run offline from the profile (same catalog + rules + profile ⇒
same result), so a baseline can be composed and signed with no Ollama and no
Qdrant. The AI layer widens what the operator sees; it is never a precondition
for what they can sign.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from functools import cached_property
from uuid import UUID, uuid4

from app.assets.schemas import AssetProfile
from app.audit.models import AuditEvent
from app.audit.schemas import AuditEventType
from app.audit.service import AuditService
from app.baseline.schemas import (
    ChoiceKind,
    ComposedBaseline,
    ComposedCapability,
    ComposedZone,
    ComposeRequest,
    CompositionChoice,
)
from app.baseline.trail import trail_for_composition
from app.catalog.loader import get_catalog
from app.catalog.schemas import Catalog
from app.core.config import settings
from app.core.exceptions import AppException, ConflictError
from app.core.wording import say
from app.engine.schemas import (
    CapabilityGating,
    CapabilityPriority,
    PriorityTier,
    ProfileGating,
    ProfilePrioritization,
    ZoneGating,
    ZonePrioritization,
)
from app.engine.service import gate_profile, prioritize_profile, resolve_profile

# Decisions that actually close a capability. Rejecting a candidate is recorded —
# it is part of the decision record — but it does not put a mechanism in the
# baseline, so it can never close a mandate on its own.
CLOSING_KINDS = frozenset(
    {ChoiceKind.OPTION_SELECTED, ChoiceKind.COMPENSATORY_DECLARED, ChoiceKind.GAP_ACCEPTED}
)


class CompositionRequestError(AppException):
    """The composition names something the engine cannot act on."""

    status_code = 422


class CompositionConflictError(ConflictError):
    """The composition is well formed but cannot be signed as things stand."""


class BaselineCompositionService:
    """Human choices in, signed baseline out. No AI, no network, no ranking."""

    def __init__(self, catalog: Catalog | None = None):
        self._catalog = catalog

    @property
    def catalog(self) -> Catalog:
        if self._catalog is None:
            self._catalog = get_catalog()
        return self._catalog

    # --- entry point ----------------------------------------------------------

    async def compose(
        self,
        profile: AssetProfile,
        request: ComposeRequest,
        audit: AuditService,
        baseline_id: UUID | None = None,
    ) -> ComposedBaseline:
        """Verify the run, verify Tier 0, record every decision, and sign."""
        baseline_id = baseline_id if baseline_id is not None else uuid4()

        recorded = await audit.log_for_run(request.run_id)
        self._check_run(request, profile, recorded)

        gating, prioritization = await asyncio.to_thread(self._core, profile)
        self._check_versions(request.run_id, recorded, prioritization)

        choices = self._check_choices(profile, request.choices)
        self._check_mandates(prioritization, choices)

        baseline = self._baseline(
            baseline_id, request, profile, gating, prioritization, choices
        )
        ratified = [
            (zone, capability)
            for zone in baseline.zones
            for capability in zone.capabilities
            if self._is_ratified(capability)
        ]

        entries = trail_for_composition(
            baseline,
            request.choices,
            request.signature,
            ratified,
            self._mapped,
            self._gating_exclusions(gating),
        )
        appended = await audit.repository.append_many(entries)

        # `signed_at` is the ledger's own stamp, not this process' clock: the moment
        # of a signature is the moment it was written down. The placeholder the
        # baseline was built with never reaches the trail — no entry reads it.
        return baseline.model_copy(
            update={"signed_at": appended[-1].recorded_at, "audit_events": len(appended)}
        )

    # --- the deterministic core, re-run offline -------------------------------

    def _core(self, profile: AssetProfile) -> tuple[ProfileGating, ProfilePrioritization]:
        resolution = resolve_profile(profile, self.catalog)
        gating = gate_profile(profile, resolution, catalog=self.catalog)
        return gating, prioritize_profile(profile, gating, catalog=self.catalog)

    # --- checks ---------------------------------------------------------------

    def _check_run(
        self, request: ComposeRequest, profile: AssetProfile, recorded: list[AuditEvent]
    ) -> None:
        """The composition has to hang from an engine run the ledger has seen."""
        if not recorded:
            raise CompositionRequestError(
                f"La bitácora no tiene ninguna ejecución con identificador '{request.run_id}'. "
                "Una composición se encadena a la ejecución del motor de la que salieron las "
                "opciones: vuelva a pedir los candidatos del perfil y componga sobre esa "
                "ejecución."
            )

        run_profile = recorded[0].profile_id
        if run_profile != profile.id:
            raise CompositionRequestError(
                f"La ejecución '{request.run_id}' se hizo sobre el perfil '{run_profile}' y la "
                f"composición dice ser del perfil '{profile.id}'. Firmar la línea base de un "
                "activo con las decisiones de otro no es trazable."
            )

        if any(event.event_type is AuditEventType.BASELINE_SIGNED for event in recorded):
            signed = next(
                event for event in recorded if event.event_type is AuditEventType.BASELINE_SIGNED
            )
            raise CompositionConflictError(
                f"La ejecución '{request.run_id}' ya se firmó como línea base "
                f"'{signed.baseline_id}'. Una ejecución se firma una sola vez: dos líneas base "
                "sobre la misma evidencia no dejarían saber cuál está en vigor. Para recomponer, "
                "pida candidatos de nuevo y firme sobre la ejecución nueva."
            )

    def _check_versions(
        self,
        run_id: UUID,
        recorded: list[AuditEvent],
        prioritization: ProfilePrioritization,
    ) -> None:
        """Refuse to sign a composition computed against inputs that have moved."""
        current = {
            "catalog": prioritization.catalog_version,
            "rules": prioritization.rules_version,
            "gating": prioritization.gating_version,
            "prioritization": prioritization.prioritization_version,
        }
        governing = recorded[0].versions or {}
        moved = {
            name: (governing[name], value)
            for name, value in current.items()
            if name in governing and governing[name] != value
        }
        if moved:
            detail = "; ".join(
                f"{name}: la ejecución usó {was} y ahora rige {now}"
                for name, (was, now) in sorted(moved.items())
            )
            raise CompositionConflictError(
                f"Las entradas versionadas cambiaron desde la ejecución '{run_id}' ({detail}). "
                "Las opciones que el operador tenía en pantalla no son las que este proceso "
                "calcularía ahora, así que la firma daría fe de algo que nadie vio. Vuelva a "
                "pedir candidatos y componga sobre la ejecución nueva."
            )

    def _check_choices(
        self, profile: AssetProfile, choices: list[CompositionChoice]
    ) -> dict[tuple[str, str], list[CompositionChoice]]:
        """Every choice must name a zone, a capability and a control that exist.

        Grouped by (zone, capability) on the way out, because that is the unit the
        baseline is composed in and the unit Tier 0 is verified over.
        """
        zones = {zone.id for zone in profile.zones}
        capabilities = {capability.id for capability in self.catalog.capabilities}
        controls = {control.id for control in self.catalog.controls}

        grouped: dict[tuple[str, str], list[CompositionChoice]] = {}
        seen: set[tuple[str, str, str, str | None]] = set()

        for choice in choices:
            if choice.zone_id not in zones:
                raise CompositionRequestError(
                    f"El perfil '{profile.id}' no declara la zona '{choice.zone_id}'. "
                    f"Zonas del perfil: {sorted(zones)}."
                )
            if choice.capability_id not in capabilities:
                raise CompositionRequestError(
                    f"El catálogo {self.catalog.catalog_version} no declara la capacidad "
                    f"'{choice.capability_id}'."
                )
            if choice.control_id is not None and choice.control_id not in controls:
                raise CompositionRequestError(
                    f"El catálogo {self.catalog.catalog_version} no declara el control "
                    f"'{choice.control_id}'. Un mecanismo que no está en el catálogo no es "
                    "auditable: decláre lo como control compensatorio del catálogo o acepte el "
                    "hueco por escrito."
                )

            key = (choice.zone_id, choice.capability_id, choice.kind.value, choice.control_id)
            if key in seen:
                raise CompositionRequestError(
                    f"La decisión de {say(choice.kind)} sobre {choice.capability_id} en "
                    f"{choice.zone_id} está repetida. Una decisión repetida no es una decisión "
                    "distinta: registrarla dos veces haría ilegible la bitácora."
                )
            seen.add(key)
            grouped.setdefault((choice.zone_id, choice.capability_id), []).append(choice)

        for (zone_id, capability_id), group in grouped.items():
            self._check_coherent(zone_id, capability_id, group)
        return grouped

    def _check_coherent(
        self, zone_id: str, capability_id: str, group: list[CompositionChoice]
    ) -> None:
        """Two decisions about the same capability may not say opposite things.

        `control_id` is never `None` on these three kinds — `CompositionChoice`
        refuses to be built otherwise — so the filter below is a type narrowing,
        not a guard against a case that can occur.
        """
        selected = self._controls(group, ChoiceKind.OPTION_SELECTED)
        rejected = self._controls(group, ChoiceKind.OPTION_REJECTED)
        both = selected & rejected
        if both:
            raise CompositionRequestError(
                f"{sorted(both)} aparece(n) a la vez como elegido y descartado para "
                f"{capability_id} en {zone_id}."
            )

        accepted_gap = any(c.kind is ChoiceKind.GAP_ACCEPTED for c in group)
        mechanisms = selected | self._controls(group, ChoiceKind.COMPENSATORY_DECLARED)
        if accepted_gap and mechanisms:
            raise CompositionRequestError(
                f"{capability_id} en {zone_id} acepta el hueco y a la vez adopta "
                f"{sorted(mechanisms)}. Aceptar un hueco es aceptar que la capacidad se queda "
                "sin mecanismo en la capa del activo."
            )

    @staticmethod
    def _controls(group: list[CompositionChoice], kind: ChoiceKind) -> set[str]:
        return {c.control_id for c in group if c.kind is kind and c.control_id is not None}

    def _check_mandates(
        self,
        prioritization: ProfilePrioritization,
        choices: dict[tuple[str, str], list[CompositionChoice]],
    ) -> None:
        """Tier 0 complete, verified before the signature and never after it.

        What has to be closed is exactly the engine's own list of outstanding
        mandates: a Tier 0 capability gating left without an applicable mechanism,
        or with a declared residual. The rest of Tier 0 the core already covered,
        and the signature ratifies it — the operator is not asked to re-justify a
        mechanism nobody questioned, but nothing is adopted anonymously either.
        """
        open_mandates: list[str] = []
        for zone in prioritization.zones:
            for capability in zone.outstanding_mandates:
                group = choices.get((zone.zone.zone_id, capability.capability_id), [])
                if not any(choice.kind in CLOSING_KINDS for choice in group):
                    open_mandates.append(f"{zone.zone.zone_id}/{capability.capability_id}")

        if open_mandates:
            raise CompositionConflictError(
                "No se puede firmar: el bloque obligatorio está incompleto. Quedan "
                f"{len(open_mandates)} mandato(s) sin cerrar — {', '.join(open_mandates)}. "
                "Cada uno se cierra de una de tres formas: eligiendo un mecanismo, declarando un "
                "control compensatorio o aceptando el hueco por escrito. Tier 0 no se prioriza: "
                "se completa, y nada obligatorio puede quedar omitido en silencio."
            )

    # --- assembling the signed baseline ---------------------------------------

    def _baseline(
        self,
        baseline_id: UUID,
        request: ComposeRequest,
        profile: AssetProfile,
        gating: ProfileGating,
        prioritization: ProfilePrioritization,
        choices: dict[tuple[str, str], list[CompositionChoice]],
    ) -> ComposedBaseline:
        zones = [
            self._zone(zone, gating.zone(zone.zone.zone_id), choices)
            for zone in prioritization.zones
        ]
        return ComposedBaseline(
            baseline_id=baseline_id,
            run_id=request.run_id,
            profile_id=profile.id,
            profile_name=profile.name,
            signed_by=request.signature.operator,
            # Replaced by the ledger's stamp once the trail is appended.
            signed_at=datetime.now(UTC),
            versions={
                "catalog": prioritization.catalog_version,
                "rules": prioritization.rules_version,
                "gating": prioritization.gating_version,
                "prioritization": prioritization.prioritization_version,
            },
            # Verified by `_check_mandates`, which refuses the signature otherwise.
            tier_0_complete=True,
            zones=zones,
            audit_log_path=f"{settings.API_V1_PREFIX}/baseline/{baseline_id}/audit-log",
        )

    def _zone(
        self,
        zone: ZonePrioritization,
        gating: ZoneGating,
        choices: dict[tuple[str, str], list[CompositionChoice]],
    ) -> ComposedZone:
        """Tier 0 in full, plus every Tier 1 capability the operator decided about.

        Tier 0 is always listed because the baseline has to show the mandatory block
        complete, capability by capability. Tier 1 is discretionary: what the
        operator did not touch is not part of what they signed, and listing it with
        every field empty would pad the baseline with non-decisions.
        """
        composed = [
            self._capability(
                capability,
                gating.capability(capability.capability_id),
                choices.get((zone.zone.zone_id, capability.capability_id), []),
            )
            for capability in zone.capabilities
            if capability.tier is PriorityTier.TIER_0
            or (zone.zone.zone_id, capability.capability_id) in choices
        ]
        outstanding = [c.capability_id for c in zone.outstanding_mandates]

        return ComposedZone(
            zone_id=zone.zone.zone_id,
            capabilities=composed,
            tier_0_complete=True,
            outstanding_capability_ids=outstanding,
            rationale=self._zone_rationale(zone, composed, outstanding),
        )

    def _capability(
        self,
        priority: CapabilityPriority,
        gating: CapabilityGating,
        group: list[CompositionChoice],
    ) -> ComposedCapability:
        selected = [c.control_id for c in group if c.kind is ChoiceKind.OPTION_SELECTED]
        rejected = [c.control_id for c in group if c.kind is ChoiceKind.OPTION_REJECTED]
        compensatory = [
            c.control_id for c in group if c.kind is ChoiceKind.COMPENSATORY_DECLARED
        ]
        gap_accepted = any(c.kind is ChoiceKind.GAP_ACCEPTED for c in group)
        mapped = self._mapped
        adopted = [
            control_id
            for control_id in selected
            if control_id and not mapped.get((priority.capability_id, control_id), False)
        ]

        capability = ComposedCapability(
            zone_id=priority.zone_id,
            capability_id=priority.capability_id,
            capability_name=self._name(priority.capability_id),
            tier=priority.tier,
            status=priority.status,
            outstanding=priority.outstanding,
            selected_control_ids=[c for c in selected if c],
            rejected_control_ids=[c for c in rejected if c],
            compensatory_control_ids=[c for c in compensatory if c],
            adopted_control_ids=adopted,
            gap_accepted=gap_accepted,
            rationale="",
        )

        # Only a mandate the human did not decide about is ratified — and only
        # mandates. A discretionary capability nobody touched is not in the
        # baseline at all, so there is nothing to ratify.
        ratified = (
            list(gating.retained_control_ids)
            if self._is_ratified(capability)
            else []
        )
        return capability.model_copy(
            update={
                "ratified_control_ids": ratified,
                "rationale": self._capability_rationale(capability, gating, ratified),
            }
        )

    def _is_ratified(self, capability: ComposedCapability) -> bool:
        return capability.tier is PriorityTier.TIER_0 and not capability.decided_by_human

    # --- operator-facing text -------------------------------------------------

    def _capability_rationale(
        self,
        capability: ComposedCapability,
        gating: CapabilityGating,
        ratified: list[str],
    ) -> str:
        where = f"«{capability.capability_name}» en {capability.zone_id}"
        if capability.gap_accepted:
            return (
                f"{where}: hueco aceptado por escrito. La capacidad sigue exigida — aceptar el "
                "hueco no la deroga, deja constancia de que se asume sin mecanismo en la capa "
                "del activo."
            )
        if capability.decided_by_human:
            parts = []
            if capability.selected_control_ids:
                parts.append(f"{len(capability.selected_control_ids)} mecanismo(s) elegido(s)")
            if capability.compensatory_control_ids:
                parts.append(
                    f"{len(capability.compensatory_control_ids)} compensatorio(s) declarado(s)"
                )
            text = f"{where}: {', '.join(parts)} por decisión del humano."
            if capability.adopted_control_ids:
                text += (
                    f" {', '.join(capability.adopted_control_ids)} no está(n) mapeado(s) a esta "
                    "capacidad en el catálogo: es una adopción de sugerencia, registrada como tal."
                )
            if capability.outstanding:
                text += " Cierra un mandato que el motor no podía cerrar solo."
            return text
        if ratified:
            return (
                f"{where}: ratificado el mecanismo retenido por el motor ({', '.join(ratified)}). "
                "No hubo elección entre equivalentes; la firma lo asume y la bitácora lo dice con "
                "un tipo de evento propio."
            )
        return (
            f"{where}: sin mecanismo en la capa del activo, ratificado el cierre del motor "
            f"({say(gating.status)}). {gating.rationale}"
        )

    def _zone_rationale(
        self,
        zone: ZonePrioritization,
        composed: list[ComposedCapability],
        outstanding: list[str],
    ) -> str:
        decided = sum(1 for c in composed if c.decided_by_human)
        ratified = sum(1 for c in composed if c.ratified_control_ids)
        gaps = sum(1 for c in composed if c.gap_accepted)
        return (
            f"Zona {zone.zone.zone_id} ({say(zone.zone.domain)}, SL-objetivo "
            f"{zone.zone.target_sl}): bloque obligatorio completo con {len(zone.tier_0)} "
            f"capacidad(es). {decided} decidida(s) explícitamente por el humano, {ratified} "
            f"ratificada(s) al firmar, {gaps} hueco(s) aceptado(s) por escrito. "
            f"{len(outstanding)} mandato(s) que el motor no podía cerrar solo quedaron cerrados "
            "aquí. La misma zona con otro perfil o con otro SL-objetivo daría otra línea base."
        )

    # --- catalog facts --------------------------------------------------------

    @cached_property
    def _mapped(self) -> dict[tuple[str, str], bool]:
        """Which (capability, control) pairs the catalog actually maps.

        Cached: the catalog is versioned and read-only, and this is consulted once
        per composed capability. A control absent from here is not a mapping — it
        is a suggestion the operator adopted, and the difference is what keeps an
        embedding distance from passing for authored evidence.
        """
        return {(m.capability_id, m.control_id): True for m in self.catalog.mappings}

    @cached_property
    def _names(self) -> dict[str, str]:
        return {capability.id: capability.name for capability in self.catalog.capabilities}

    def _gating_exclusions(self, gating: ProfileGating) -> dict[tuple[str, str, str], str]:
        """(zone, capability, control) -> outcome, for the mechanisms gating ruled out."""
        return {
            (decision.zone_id, decision.capability_id, decision.control_id): say(decision.outcome)
            for decision in gating.decisions
        }

    def _name(self, capability_id: str) -> str:
        return self._names.get(capability_id, capability_id)
