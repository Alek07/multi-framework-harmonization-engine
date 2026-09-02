"""UCM-17/UCM-50 - The regional delta: the same zone, composed under two jurisdictions.

The service computes nothing of its own. For each reading it filters the zone's
candidates and hands them to the *same* `resolve_capability` the deterministic
core uses (UCM-8), so every number in the response — coverage, full mechanism,
declared gap — is the engine's own arithmetic over a smaller set of options. What
this module adds is the comparison between the readings, and the sentences that
make it legible.

The human chooses two things and the engine obeys (it never applies a lens on its
own initiative):

* `mode` — `cumulative` reads each region *plus* the ones before it, so "+EU" is
  the US reading plus the European overlay; `symmetric` reads each region on its
  own over the common ground and reports the difference in **both** directions.
  The symmetric direction is the one UCM-50 restored: with cumulative readings the
  first region could never report what it alone requires (`only_here` was empty by
  construction), so *"what does the US demand that the EU does not"* was
  inexpressible — exactly the missing half of the delta.
* `regime` — `all` compares by jurisdiction; `legal` makes only the `legal`
  controls of the compared regions the axis and freezes the common technical
  ground (CIS, CSF, IEC 62443) in every reading, so the comparison is
  law-against-law and never mixes voluntary frameworks with obligations.

The engine does one thing on its own initiative here, and it is a determination
rather than a choice: it applies sectoral applicability (UCM-47) so the comparison
is about *the laws that actually govern this asset*. A compared region's control
whose declared sector does not meet the zone's is not a difference this asset has
to answer — TSA governs pipelines, not hospitals — so it does not enter the
comparison at all. That this is not a silent drop is guaranteed by
`regime_applicability`, which reports every compared regime with the engine's
reason for whether it governs the asset: the exclusion is stated there, not
swallowed. This is what makes the delta asset-specific — a pipeline and a hospital
get different comparisons — instead of the same catalog read under two lenses.
Reglas deciden aplicabilidad; humano elige la comparación.

Nothing here is written to the audit log. A delta is a *view*: it decides nothing,
changes no baseline and belongs to no run. The composition it informs is what gets
recorded, with the human's name on it (UCM-16).
"""

from __future__ import annotations

from app.assets.schemas import AssetProfile, Zone
from app.catalog.loader import get_catalog
from app.catalog.schemas import (
    Capability,
    Catalog,
    ControlType,
    Framework,
    Jurisdiction,
    MappingType,
)
from app.core.exceptions import AppException
from app.core.wording import say, say_all
from app.delta.schemas import (
    CapabilityDelta,
    CapabilityRegionView,
    DeltaMode,
    DeltaRegime,
    RegimeApplicability,
    RegionalDelta,
    RegionalRequirement,
)
from app.engine.applicability import (
    control_applies,
    framework_applicability_reason,
    framework_applies,
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


# One reading: the region that names it and the set of axis-regions it offers.
# In cumulative mode reading *i* includes every region up to *i*; in symmetric
# mode it includes only its own. The common ground is added on top for every
# reading and is not carried in this set.
Reading = tuple[Jurisdiction, set[Jurisdiction]]


class RegionalDeltaService:
    """One zone, N readings, and the difference between them — in either direction."""

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
        self,
        profile: AssetProfile,
        zone_id: str,
        regions: list[Jurisdiction],
        mode: DeltaMode = DeltaMode.CUMULATIVE,
        regime: DeltaRegime = DeltaRegime.ALL,
    ) -> RegionalDelta:
        """Read one zone of the profile under each region, and report what changes."""
        self.rules.validate_against(self.catalog)
        zone = zone_context(self._zone(profile, zone_id), profile)

        common = self._common_ground(regions)
        readings = self._readings(regions, mode)
        excluded = self._sector_excluded(regions, zone)

        capabilities = [
            self._capability(capability, zone, readings, regions, mode, regime, excluded)
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
            mode=mode,
            regime=regime,
            regions=regions,
            common_jurisdictions=common,
            lenses=[
                self._lens(region, included, index, common, mode, regime)
                for index, (region, included) in enumerate(readings)
            ],
            capabilities=capabilities,
            changed_capability_ids=changed,
            unchanged_capability_ids=[
                c.capability_id for c in capabilities if not c.changed
            ],
            regional_gap_capability_ids=gaps,
            regime_applicability=self._applicability(regions, zone),
            rationale=self._rationale(zone, regions, mode, regime, capabilities, changed, gaps),
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

    def _sector_excluded(self, regions: list[Jurisdiction], zone: ZoneContext) -> set[str]:
        """Compared-region controls that do not govern this asset's sectors (UCM-47).

        A control of a region under comparison whose declared scope does not meet
        the zone's sectors is not a difference this asset has to answer, so it is
        kept out of the comparison entirely — not offered, not set aside, not added.
        The exclusion is never silent: `regime_applicability` states, for every
        compared regime, whether it governs the asset and why. Transversal controls
        (CIS/CSF, CIRCIA) and multi-sector ones (NIS2) meet any or many sectors, so
        this only removes a genuinely out-of-scope regime such as TSA on a hospital.
        """
        return {
            control.id
            for control in self.catalog.controls
            if control.jurisdiction in regions and not control_applies(control, zone.sectors)
        }

    def _common_ground(self, regions: list[Jurisdiction]) -> list[Jurisdiction]:
        """Every jurisdiction not under comparison. Present in all readings.

        Derived rather than declared, so nothing can be dropped by omission: what
        the question is not about is common ground, and the union of the readings
        is always the whole catalog.
        """
        return [j for j in Jurisdiction if j not in regions]

    def _readings(self, regions: list[Jurisdiction], mode: DeltaMode) -> list[Reading]:
        """The axis-region sets of each reading, per the chosen mode.

        Cumulative: reading *i* includes every region up to *i*. Symmetric: each
        reading includes only its own region, so the comparison runs both ways.
        """
        if mode is DeltaMode.SYMMETRIC:
            return [(region, {region}) for region in regions]
        readings: list[Reading] = []
        included: set[Jurisdiction] = set()
        for region in regions:
            included = included | {region}
            readings.append((region, set(included)))
        return readings

    def _axis_region(
        self, option: CandidateOption, regions: list[Jurisdiction], regime: DeltaRegime
    ) -> Jurisdiction | None:
        """The region this option is credited to as an axis contribution, or None.

        `None` means the option is common ground — offered by every reading. In
        `all` regime the axis is jurisdiction; in `legal` regime it is legal
        controls of the compared regions only, so every technical control (and any
        legal control of a jurisdiction not under comparison) stays common ground.
        """
        jurisdiction = option.control.jurisdiction
        if regime is DeltaRegime.LEGAL:
            if option.control.control_type is ControlType.LEGAL and jurisdiction in regions:
                return jurisdiction
            return None
        return jurisdiction if jurisdiction in regions else None

    def _offers(
        self,
        option: CandidateOption,
        included: set[Jurisdiction],
        regions: list[Jurisdiction],
        regime: DeltaRegime,
    ) -> bool:
        """Whether a reading including `included` offers this option."""
        axis = self._axis_region(option, regions, regime)
        return axis is None or axis in included

    def _lens(
        self,
        region: Jurisdiction,
        included: set[Jurisdiction],
        index: int,
        common: list[Jurisdiction],
        mode: DeltaMode,
        regime: DeltaRegime,
    ) -> PayloadFilter:
        """The reading expressed as a declared lens, for the record.

        The same `PayloadFilter` the RAG pass uses (UCM-13). In `all` regime the
        lens is a jurisdiction filter and prints its jurisdictions; in `legal`
        regime the restriction is on control type as well as jurisdiction, which is
        not a pure jurisdiction filter, so the structured field is left empty and
        the prose carries the restriction — the delta is auditable through the
        rationale either way.
        """
        label = self._label(region, index, mode)
        jurisdictions = (
            None
            if regime is DeltaRegime.LEGAL
            else [j for j in Jurisdiction if j in set(common) | included]
        )
        return PayloadFilter(
            jurisdictions=jurisdictions,
            rationale=self._lens_rationale(label, included, common, mode, regime),
        )

    def _lens_rationale(
        self,
        label: str,
        included: set[Jurisdiction],
        common: list[Jurisdiction],
        mode: DeltaMode,
        regime: DeltaRegime,
    ) -> str:
        axis = say_all([j for j in Jurisdiction if j in included])
        if regime is DeltaRegime.LEGAL:
            head = (
                f"Lectura «{label}» en modo régimen legal: solo los controles legales de "
                f"jurisdicción {axis} entran como eje de comparación. El terreno técnico común "
                "(CIS, CSF, IEC 62443) queda fijo en toda lectura y no se atribuye a ninguna "
                "región, así la comparación es ley-contra-ley y no mezcla marcos voluntarios con "
                "obligaciones."
            )
        else:
            offered = say_all([j for j in Jurisdiction if j in set(common) | included])
            head = f"Lectura «{label}»: se ofrecen los controles de jurisdicción {offered}."
        if mode is DeltaMode.SYMMETRIC:
            relation = (
                " Comparación simétrica: cada lectura ofrece solo su región sobre el terreno "
                "común y la diferencia se reporta en ambos sentidos."
            )
        else:
            relation = (
                " Las lecturas son acumulativas — «+EU» es la lectura estadounidense más la capa "
                "de obligación europea, no un catálogo paralelo."
            )
        return head + relation + (
            " Lo que esta lente aparta se devuelve igualmente, marcado como apartado: apartar no "
            "es descartar."
        )

    @staticmethod
    def _label(region: Jurisdiction, index: int, mode: DeltaMode) -> str:
        if mode is DeltaMode.SYMMETRIC:
            return region.value
        return region.value if index == 0 else f"+{region.value}"

    # --- one capability, read N times -----------------------------------------

    def _capability(
        self,
        capability: Capability,
        zone: ZoneContext,
        readings: list[Reading],
        regions: list[Jurisdiction],
        mode: DeltaMode,
        regime: DeltaRegime,
        excluded: set[str],
    ) -> CapabilityDelta:
        resolutions = [
            self._reading(capability, zone, included, regions, regime, excluded)
            for _, included in readings
        ]
        offered = [[o.control_id for o in r.options] for r in resolutions]
        common = [c for c in offered[0] if all(c in later for later in offered[1:])]
        common_jurisdictions = set(self._common_ground(regions))

        views: list[CapabilityRegionView] = []
        added: list[RegionalRequirement] = []
        for index, ((region, included), resolution) in enumerate(
            zip(readings, resolutions, strict=True)
        ):
            only_here = self._only_here(offered, index, mode)
            allowed = included | common_jurisdictions
            views.append(
                self._view(
                    region, index, allowed, resolution, only_here, capability, mode, excluded
                )
            )
            # In cumulative mode the first reading contributes nothing exclusive
            # (it is the starting point); in symmetric mode every reading reports
            # its own contribution, which is what expresses both directions.
            if mode is DeltaMode.SYMMETRIC or index:
                added.extend(
                    self._requirement(region, option, resolution, mode)
                    for option in resolution.options
                    if option.control_id in only_here
                )

        changed = bool(added) or any(set(o) != set(offered[0]) for o in offered)
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

    @staticmethod
    def _only_here(offered: list[list[str]], index: int, mode: DeltaMode) -> list[str]:
        """What reading *index* offers that no other one relevant to it does.

        Cumulative: what it adds over the readings *before* it — so the first
        reading adds nothing, everything it offers the later ones offer too.
        Symmetric: what it offers that no *other* reading does, in either
        direction — the half a cumulative reading cannot express (UCM-50).
        """
        if mode is DeltaMode.SYMMETRIC:
            others = {c for j, earlier in enumerate(offered) if j != index for c in earlier}
            return [c for c in offered[index] if c not in others]
        if not index:
            return []
        earlier = {c for previous in offered[:index] for c in previous}
        return [c for c in offered[index] if c not in earlier]

    def _reading(
        self,
        capability: Capability,
        zone: ZoneContext,
        included: set[Jurisdiction],
        regions: list[Jurisdiction],
        regime: DeltaRegime,
        excluded: set[str],
    ) -> CapabilityResolution:
        """The core's own resolution over the options this reading offers.

        `build_options` is called per reading rather than filtered in place because
        `resolve_capability` annotates the options it is given (status, reason): two
        readings must never share, and therefore never contaminate, the same objects.
        Controls a compared regime cannot govern here (UCM-47) are dropped before the
        core sees them, so a law out of the asset's sector never becomes a candidate.
        """
        options = [
            option
            for option in build_options(self.catalog, capability.id, self.rules, zone)
            if option.control_id not in excluded and self._offers(option, included, regions, regime)
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
        mode: DeltaMode,
        excluded: set[str],
    ) -> CapabilityRegionView:
        offered = [option.control_id for option in resolution.options]
        set_aside = [
            mapping.control_id
            for mapping in self.catalog.mappings_for(capability.id)
            if mapping.control_id not in offered and mapping.control_id not in excluded
        ]
        label = self._label(region, index, mode)
        return CapabilityRegionView(
            region=region,
            label=label,
            jurisdictions=[j for j in Jurisdiction if j in allowed],
            offered_control_ids=offered,
            only_here_control_ids=only_here,
            set_aside_control_ids=set_aside,
            frameworks=self._frameworks(resolution.options),
            coverage=resolution.coverage,
            has_full_mechanism=resolution.has_full_mechanism,
            gap=resolution.gap,
            rationale=self._view_rationale(
                label,
                capability,
                resolution,
                only_here,
                set_aside,
                first=index == 0,
                mode=mode,
            ),
        )

    def _requirement(
        self,
        region: Jurisdiction,
        option: CandidateOption,
        resolution: CapabilityResolution,
        mode: DeltaMode,
    ) -> RegionalRequirement:
        """One control a reading adds, with what it does and does not change."""
        contextual = option.mapping_type is MappingType.CONTEXTUAL
        control = option.control
        other = "La otra lectura" if mode is DeltaMode.SYMMETRIC else "La lectura anterior"
        if contextual:
            rationale = (
                f"{control.official_id} ({control.framework.value}, {control.jurisdiction.value}) "
                f"añade exigencia, no mecanismo: es un mapeo contextual de peso "
                f"{option.coverage_weight} y la cobertura de «{resolution.capability.name}» no se "
                f"mueve. Lo que cambia es lo que se debe — «{control.strength.label}» — sobre una "
                "capacidad que el terreno común ya cubre técnicamente."
            )
        else:
            rationale = (
                f"{control.official_id} ({control.framework.value}, {control.jurisdiction.value}) "
                f"añade mecanismo: mapeo {say(option.mapping_type)} de peso "
                f"{option.coverage_weight} sobre «{resolution.capability.name}». {other} no lo "
                f"ofrece. Exigencia declarada: «{control.strength.label}»."
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

    # --- applicability of the compared regimes (UCM-47) -----------------------

    def _applicability(
        self, regions: list[Jurisdiction], zone: ZoneContext
    ) -> list[RegimeApplicability]:
        """Which legal regimes of the compared regions govern this asset, and why.

        The engine does not choose the comparison, but it does determine whether
        each regime applies to the zone's sectors and says so — so the human
        chooses knowing that TSA governs only its sector while CIRCIA is
        transversal. A regime that does not apply is reported, not dropped.
        """
        jurisdiction_of: dict[Framework, Jurisdiction] = {}
        for control in self.catalog.controls:
            if control.control_type is ControlType.LEGAL and control.jurisdiction in regions:
                jurisdiction_of.setdefault(control.framework, control.jurisdiction)

        report: list[RegimeApplicability] = []
        for framework in sorted(jurisdiction_of, key=lambda f: f.value):
            controls = [c for c in self.catalog.controls if c.framework is framework]
            governs = sorted(
                {sector.value for control in controls for sector in control.applies_to_sectors}
            )
            report.append(
                RegimeApplicability(
                    framework=framework,
                    jurisdiction=jurisdiction_of[framework],
                    governs_sectors=governs,
                    applicable=framework_applies(controls, zone),
                    rationale=framework_applicability_reason(framework, controls, zone),
                )
            )
        return report

    # --- operator-facing text -------------------------------------------------

    def _view_rationale(
        self,
        label: str,
        capability: Capability,
        resolution: CapabilityResolution,
        only_here: list[str],
        set_aside: list[str],
        first: bool,
        mode: DeltaMode,
    ) -> str:
        text = (
            f"Lectura «{label}» de «{capability.name}»: "
            f"{len(resolution.options)} candidato(s), cobertura {resolution.coverage}."
        )
        if first and mode is not DeltaMode.SYMMETRIC:
            text += " Es la lectura de partida: sobre ella se suman las regiones siguientes."
        elif only_here:
            other = "la otra lectura" if mode is DeltaMode.SYMMETRIC else "la lectura anterior"
            text += f" Aporta {only_here} que {other} no ofrece."
        else:
            other = "la otra lectura" if mode is DeltaMode.SYMMETRIC else "la lectura anterior"
            text += f" No añade nada que {other} no tenga."
        if set_aside:
            belong = (
                "pertenecen a la otra región de la comparación"
                if mode is DeltaMode.SYMMETRIC
                else "pertenecen a una región que todavía no se ha sumado"
            )
            text += (
                f" {len(set_aside)} candidato(s) apartado(s) por la lente de esta lectura "
                f"({set_aside}): {belong}. Apartar no es descartar — están aquí, con nombre."
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
                f"— «{obligations[0].strength.label}» — no en el mecanismo. "
            )
        if mechanisms:
            names = ", ".join(f"{r.official_id} ({r.added_by.value})" for r in mechanisms)
            text += f"{names} añade(n) mecanismo y sí mueve(n) la cobertura. "
        return text + "El motor no elige por el operador: muestra ambas lecturas lado a lado."

    def _rationale(
        self,
        zone: ZoneContext,
        regions: list[Jurisdiction],
        mode: DeltaMode,
        regime: DeltaRegime,
        capabilities: list[CapabilityDelta],
        changed: list[str],
        gaps: list[str],
    ) -> str:
        labels = " → ".join(
            self._label(region, index, mode) for index, region in enumerate(regions)
        )
        obligations = sum(
            1 for c in capabilities if c.changed and not c.changes_coverage
        )
        head = (
            f"Delta regional sobre {zone.zone_id} ({say(zone.domain)}, SL-objetivo "
            f"{zone.target_sl}), lecturas {labels}: {len(changed)} de "
            f"{len(capabilities)} capacidades cambian y en {len(gaps)} el hueco depende de la "
            f"región. De las que cambian, {obligations} lo hacen añadiendo obligación sin mover "
            "la cobertura — la diferencia regional de este catálogo es sobre todo legal, no "
            "técnica, y decirlo así es el resultado, no una carencia. Los huecos que declara el "
            "núcleo por cobertura parcial o residual vienen del terreno común y salen iguales "
            "en todas las lecturas: se muestran por lectura, pero no se cuentan como regionales. "
        )
        if regime is DeltaRegime.LEGAL:
            head += (
                "En modo régimen legal solo los controles legales diferencian: el terreno técnico "
                "común (CIS/CSF/IEC 62443) queda fijo, así la comparación es ley-contra-ley. "
            )
        if mode is DeltaMode.SYMMETRIC:
            head += (
                "La comparación es simétrica: se reporta qué exige cada región que la otra no, en "
                "ambos sentidos. "
            )
        else:
            head += (
                "Las lecturas son acumulativas: «+EU» es la lectura anterior más la capa europea, "
                "nunca un catálogo paralelo. "
            )
        return head + (
            "La comparación se hace sobre una sola zona: para el resto del activo, repítala zona "
            "a zona."
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
