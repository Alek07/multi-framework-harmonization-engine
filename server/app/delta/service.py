"""UCM-17 - The regional delta: the same zone, composed under two jurisdictions.

The service computes nothing of its own. For each reading it filters the zone's
candidates by jurisdiction and hands them to the *same* `resolve_capability` the
deterministic core uses (UCM-8), so every number in the response — coverage, full
mechanism, declared gap — is the engine's own arithmetic over a smaller set of
options. What this module adds is the comparison between the readings, and the
sentences that make it legible.

Two things about the result are worth stating before anyone reads it as a bug.

**The readings are cumulative.** `?regions=US,EU` means "the US reading" and then
"the same, plus the European obligation overlay" — the `+` of "+EU" (UCM-3).
Every jurisdiction not under comparison is common ground and appears in both:
IEC 62443 as the common OT standard, IMO as the maritime one. A reading of "EU
alone" would be a baseline with no CIS and no CSF, which is not what NIS2 says.

**Adding EU does not move coverage, and that is the finding.** Every NIS2 mapping
in this catalog is `contextual` with a low weight — a legal obligation over a
capability the common ground already covers technically — and contextual options
are excluded from coverage by the core (`conflicts._effective`). So the honest
report is not "nothing changed": it is that what changes is *exigencia*, not
mechanism. A US operator meets incident reporting with CSF RS.CO-02 as good
practice; an operator under NIS2 additionally owes Article 23 with statutory
24 h / 72 h / one-month deadlines. Both facts travel together in
`RegionalRequirement`, precisely so neither can be read alone and mislead.

Nothing here is written to the audit log. A delta is a *view*: it decides nothing,
changes no baseline and belongs to no run. The composition it informs is what gets
recorded, with the human's name on it (UCM-16).
"""

from __future__ import annotations

from app.assets.schemas import AssetProfile, Zone
from app.catalog.loader import get_catalog
from app.catalog.schemas import Capability, Catalog, Framework, Jurisdiction, MappingType
from app.core.exceptions import AppException
from app.core.wording import say, say_all
from app.delta.schemas import (
    CapabilityDelta,
    CapabilityRegionView,
    RegionalDelta,
    RegionalRequirement,
)
from app.engine.conflicts import resolve_capability
from app.engine.mapping import build_options
from app.engine.rules import RuleSet, get_rules
from app.engine.schemas import CandidateOption, CapabilityResolution, ZoneContext
from app.engine.zones import zone_context
from app.retrieval.schemas import PayloadFilter


class UnknownZoneError(AppException):
    """The profile does not declare the zone the delta was asked about."""

    status_code = 422


class RegionalDeltaService:
    """One zone, N cumulative readings, and the difference between them."""

    def __init__(self, catalog: Catalog | None = None, rules: RuleSet | None = None):
        self._catalog = catalog
        self._rules = rules

    @property
    def catalog(self) -> Catalog:
        if self._catalog is None:
            self._catalog = get_catalog()
        return self._catalog

    @property
    def rules(self) -> RuleSet:
        if self._rules is None:
            self._rules = get_rules()
        return self._rules

    # --- entry point ----------------------------------------------------------

    def delta(
        self, profile: AssetProfile, zone_id: str, regions: list[Jurisdiction]
    ) -> RegionalDelta:
        """Read one zone of the profile under each region, and report what changes."""
        self.rules.validate_against(self.catalog)
        zone = zone_context(self._zone(profile, zone_id), profile)

        common = self._common_ground(regions)
        readings = self._readings(regions, common)

        capabilities = [
            self._capability(capability, zone, readings)
            for capability in sorted(self.catalog.capabilities, key=lambda c: c.id)
        ]
        changed = [c.capability_id for c in capabilities if c.changed]
        gaps = [c.capability_id for c in capabilities if self._gap_is_regional(c)]

        return RegionalDelta(
            profile_id=profile.id,
            profile_name=profile.name,
            zone=zone,
            catalog_version=self.catalog.catalog_version,
            rules_version=self.rules.rules_version,
            regions=regions,
            common_jurisdictions=common,
            lenses=[self._lens(region, allowed, index) for index, (region, allowed) in
                    enumerate(readings)],
            capabilities=capabilities,
            changed_capability_ids=changed,
            unchanged_capability_ids=[
                c.capability_id for c in capabilities if not c.changed
            ],
            regional_gap_capability_ids=gaps,
            rationale=self._rationale(zone, regions, capabilities, changed, gaps),
        )

    @staticmethod
    def _gap_is_regional(capability: CapabilityDelta) -> bool:
        """Does the *gap* depend on where the operator answers?

        A gap the deterministic core declares from the common ground — partial or
        residual coverage — appears identically under every reading. Listing it as
        a regional gap would manufacture a finding out of something the region has
        nothing to do with. What counts is a gap one reading has and another does
        not, or a reading with no candidate at all.
        """
        declared = {view.gap is not None for view in capability.regions}
        empty = any(not view.offered_control_ids for view in capability.regions)
        return len(declared) > 1 or empty

    # --- the readings ---------------------------------------------------------

    def _common_ground(self, regions: list[Jurisdiction]) -> list[Jurisdiction]:
        """Every jurisdiction not under comparison. Present in all readings.

        Derived rather than declared, so nothing can be dropped by omission: what
        the question is not about is common ground, and the union of the readings
        is always the whole catalog.
        """
        return [j for j in Jurisdiction if j not in regions]

    def _readings(
        self, regions: list[Jurisdiction], common: list[Jurisdiction]
    ) -> list[tuple[Jurisdiction, set[Jurisdiction]]]:
        """Cumulative jurisdiction sets: reading *i* contains every region up to *i*."""
        readings: list[tuple[Jurisdiction, set[Jurisdiction]]] = []
        allowed = set(common)
        for region in regions:
            allowed = allowed | {region}
            readings.append((region, set(allowed)))
        return readings

    def _lens(
        self, region: Jurisdiction, allowed: set[Jurisdiction], index: int
    ) -> PayloadFilter:
        """The reading expressed as a declared lens, for the record.

        The same `PayloadFilter` the RAG pass uses (UCM-13), built here over the
        catalog rather than over the index: the delta is a reading of authored
        mappings, and the lens is what makes it auditable.
        """
        label = self._label(region, index)
        offered = sorted(allowed, key=lambda jurisdiction: jurisdiction.value)
        return PayloadFilter(
            jurisdictions=[j for j in Jurisdiction if j in allowed],
            rationale=(
                f"Lectura «{label}»: se ofrecen los controles de jurisdicción "
                f"{say_all(offered)}. Las lecturas son "
                "acumulativas — «+EU» es la lectura estadounidense más la capa de obligación "
                "europea, no un catálogo paralelo. Lo que esta lente aparta se devuelve "
                "igualmente, marcado como apartado: apartar no es descartar."
            ),
        )

    @staticmethod
    def _label(region: Jurisdiction, index: int) -> str:
        return region.value if index == 0 else f"+{region.value}"

    # --- one capability, read N times -----------------------------------------

    def _capability(
        self,
        capability: Capability,
        zone: ZoneContext,
        readings: list[tuple[Jurisdiction, set[Jurisdiction]]],
    ) -> CapabilityDelta:
        resolutions = [
            self._reading(capability, zone, allowed) for _, allowed in readings
        ]
        offered = [[o.control_id for o in r.options] for r in resolutions]
        common = [c for c in offered[0] if all(c in later for later in offered[1:])]

        views: list[CapabilityRegionView] = []
        added: list[RegionalRequirement] = []
        for index, ((region, allowed), resolution) in enumerate(zip(readings, resolutions,
                                                                   strict=True)):
            # What *this* reading contributes that no other one does. The first
            # reading contributes nothing in that sense — it is the starting point,
            # and everything it offers the later readings offer too. Listing its
            # whole offer as "only here" would read as a regional difference where
            # there is none.
            earlier = {c for previous in offered[:index] for c in previous}
            only_here = [c for c in offered[index] if c not in earlier] if index else []
            views.append(
                self._view(region, index, allowed, resolution, only_here, capability)
            )
            if index:
                added.extend(
                    self._requirement(region, option, resolution)
                    for option in resolution.options
                    if option.control_id in only_here
                )

        changed = bool(added) or any(len(o) != len(offered[0]) for o in offered)
        changes_coverage = any(r.changes_coverage for r in added)

        return CapabilityDelta(
            capability_id=capability.id,
            capability_name=capability.name,
            zone_id=zone.zone_id,
            common_control_ids=common,
            regions=views,
            added=added,
            changed=changed,
            changes_coverage=changes_coverage,
            rationale=self._capability_rationale(capability, views, added, changed),
        )

    def _reading(
        self, capability: Capability, zone: ZoneContext, allowed: set[Jurisdiction]
    ) -> CapabilityResolution:
        """The core's own resolution over the options this reading offers.

        `build_options` is called per reading rather than filtered in place because
        `resolve_capability` annotates the options it is given (status, reason): two
        readings must never share, and therefore never contaminate, the same objects.
        """
        options = [
            option
            for option in build_options(self.catalog, capability.id, self.rules, zone)
            if option.control.jurisdiction in allowed
        ]
        return resolve_capability(capability, options, self.rules, zone)

    def _view(
        self,
        region: Jurisdiction,
        index: int,
        allowed: set[Jurisdiction],
        resolution: CapabilityResolution,
        only_here: list[str],
        capability: Capability,
    ) -> CapabilityRegionView:
        offered = [option.control_id for option in resolution.options]
        set_aside = [
            mapping.control_id
            for mapping in self.catalog.mappings_for(capability.id)
            if mapping.control_id not in offered
        ]
        return CapabilityRegionView(
            region=region,
            label=self._label(region, index),
            jurisdictions=[j for j in Jurisdiction if j in allowed],
            offered_control_ids=offered,
            only_here_control_ids=only_here,
            set_aside_control_ids=set_aside,
            frameworks=self._frameworks(resolution.options),
            coverage=resolution.coverage,
            has_full_mechanism=resolution.has_full_mechanism,
            gap=resolution.gap,
            rationale=self._view_rationale(
                self._label(region, index),
                capability,
                resolution,
                only_here,
                set_aside,
                first=index == 0,
            ),
        )

    def _requirement(
        self,
        region: Jurisdiction,
        option: CandidateOption,
        resolution: CapabilityResolution,
    ) -> RegionalRequirement:
        """One control a later reading adds, with what it does and does not change."""
        contextual = option.mapping_type is MappingType.CONTEXTUAL
        control = option.control
        if contextual:
            rationale = (
                f"{control.official_id} ({control.framework.value}, {control.jurisdiction.value}) "
                f"añade exigencia, no mecanismo: es un mapeo contextual de peso "
                f"{option.coverage_weight} y la cobertura de «{resolution.capability.name}» no se "
                f"mueve. Lo que cambia es lo que se debe — «{control.strength}» — sobre una "
                "capacidad que el terreno común ya cubre técnicamente."
            )
        else:
            rationale = (
                f"{control.official_id} ({control.framework.value}, {control.jurisdiction.value}) "
                f"añade mecanismo: mapeo {say(option.mapping_type)} de peso "
                f"{option.coverage_weight} sobre «{resolution.capability.name}». La lectura "
                f"anterior no lo ofrecía. Exigencia declarada: «{control.strength}»."
            )
        return RegionalRequirement(
            control_id=control.id,
            official_id=control.official_id,
            framework=control.framework,
            jurisdiction=control.jurisdiction,
            mapping_type=option.mapping_type,
            coverage_weight=option.coverage_weight,
            strength=control.strength,
            added_by=region,
            changes_coverage=not contextual,
            rationale=rationale,
        )

    # --- operator-facing text -------------------------------------------------

    def _view_rationale(
        self,
        label: str,
        capability: Capability,
        resolution: CapabilityResolution,
        only_here: list[str],
        set_aside: list[str],
        first: bool,
    ) -> str:
        text = (
            f"Lectura «{label}» de «{capability.name}»: "
            f"{len(resolution.options)} candidato(s), cobertura {resolution.coverage}."
        )
        if first:
            text += " Es la lectura de partida: sobre ella se suman las regiones siguientes."
        elif only_here:
            text += f" Aporta {only_here} que la lectura anterior no ofrecía."
        else:
            text += " No añade nada a la lectura anterior."
        if set_aside:
            text += (
                f" {len(set_aside)} candidato(s) apartado(s) por la lente de esta lectura "
                f"({set_aside}): pertenecen a una región que todavía no se ha sumado. Apartar "
                "no es descartar — están aquí, con nombre."
            )
        if resolution.gap is not None:
            text += (
                f" Sin candidato en esta lectura: {resolution.gap.rationale} Es un hueco "
                "regional, señalado y no omitido."
            )
        return text

    def _capability_rationale(
        self,
        capability: Capability,
        views: list[CapabilityRegionView],
        added: list[RegionalRequirement],
        changed: bool,
    ) -> str:
        if not changed:
            return (
                f"«{capability.name}»: idéntica en todas las lecturas — "
                f"{len(views[0].offered_control_ids)} candidato(s) del terreno común. La "
                "jurisdicción no cambia lo que se puede componer aquí."
            )
        obligations = [r for r in added if not r.changes_coverage]
        mechanisms = [r for r in added if r.changes_coverage]
        text = f"«{capability.name}»: la lectura cambia con la región. "
        if obligations:
            names = ", ".join(f"{r.official_id} ({r.added_by.value})" for r in obligations)
            text += (
                f"{names} añade(n) obligación sin mover la cobertura: mapeo contextual sobre una "
                "capacidad que el terreno común ya cubre. La diferencia está en la exigencia "
                f"— «{obligations[0].strength}» — no en el mecanismo. "
            )
        if mechanisms:
            names = ", ".join(f"{r.official_id} ({r.added_by.value})" for r in mechanisms)
            text += f"{names} añade(n) mecanismo y sí mueve(n) la cobertura. "
        return text + "El motor no elige por el operador: muestra ambas lecturas lado a lado."

    def _rationale(
        self,
        zone: ZoneContext,
        regions: list[Jurisdiction],
        capabilities: list[CapabilityDelta],
        changed: list[str],
        gaps: list[str],
    ) -> str:
        labels = " → ".join(
            self._label(region, index) for index, region in enumerate(regions)
        )
        obligations = sum(
            1 for c in capabilities if c.changed and not c.changes_coverage
        )
        return (
            f"Delta regional sobre {zone.zone_id} ({say(zone.domain)}, SL-objetivo "
            f"{zone.target_sl}), lecturas {labels}: {len(changed)} de "
            f"{len(capabilities)} capacidades cambian y en {len(gaps)} el hueco depende de la "
            f"región. De las que cambian, {obligations} lo hacen añadiendo obligación sin mover "
            "la cobertura — la diferencia regional de este catálogo es sobre todo legal, no "
            "técnica, y decirlo así es el resultado, no una carencia. Los huecos que declara el "
            "núcleo por cobertura parcial o residual vienen del terreno común y salen iguales "
            "en todas las lecturas: se muestran por lectura, pero no se cuentan como "
            "regionales. Las lecturas son acumulativas: «+EU» es la lectura anterior más la "
            "capa europea, nunca un catálogo paralelo. La comparación se hace sobre una sola "
            "zona: para el resto del activo, repítala zona a zona."
        )

    # --- catalog facts --------------------------------------------------------

    @staticmethod
    def _frameworks(options: list[CandidateOption]) -> list[Framework]:
        seen: list[Framework] = []
        for option in options:
            if option.framework not in seen:
                seen.append(option.framework)
        return seen

    @staticmethod
    def _zone(profile: AssetProfile, zone_id: str) -> Zone:
        for zone in profile.zones:
            if zone.id == zone_id:
                return zone
        raise UnknownZoneError(
            f"El perfil '{profile.id}' no declara la zona '{zone_id}'. "
            f"Zonas: {[z.id for z in profile.zones]}."
        )
